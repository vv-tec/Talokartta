"""Metsakartta: metsätilojen yöajo (tiekartan kohta 6). Koodi on täällä, ajo ja julkaisu repositoriossa vv-tec/Metsakartta.

Kulku (python -m pipeline.metsa --out dist --cache cache --work work):
  1. Kunnat, joiden tulos puuttuu tai on yli METSA_MAX_AGE_DAYS vanha, haetaan uudelleen (vanhimmat ensin, aikaraja):
     MML:n kiinteistörekisterikartta (palstat → kiinteistöt), Metsäkeskuksen metsävarakuviot (MV/Kunta, uusi tietomalli),
     Ryhti (rakennukset kiinteistöittäin). Kuviot jaetaan kiinteistöille leikkauksen alan mukaan.
     Talteen vain metsätilat (metsämaata yli METSA_MIN_FOREST_HA): määrät puutavaralajeittain, alat, luokkaosuudet,
     yleistetty raja (lon/lat). Välimuisti cache/metsa/<kunta>.json.gz.
  2. Luken viimeisimmät kantohinnat (joka ajo) → puuston arvo pystykaupan hinnoin ja hakkuutavan hinnoin.
  3. Valmiit maakunnat (kaikki kunnat tallessa) → f-<maakunta>.pmtiles (rajat), fp.pmtiles (pisteet), meta.json,
     esikatselusivu (metsa_web/).
"""
import argparse
import collections
import datetime as dt
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import time
import zipfile

from shapely.ops import unary_union
from shapely.strtree import STRtree

from . import config, net, ryhti
from .build import fail, fmt_kt, keep, slug
from .metsa_laske import ASSORT, PRICE_AREA, PRICE_AREA_MUNI, luke_prices, price_group, read_stands, to_shape
from .mml_files import MMLFiles, municipality_parcels
from .tm35 import tm35_to_latlon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VERSION = 1  # kunnan tuloksen laskentaversio; muutos → kunnat lasketaan uudelleen (vanhimmasta alkaen)
MV_BASE = "https://avoin.metsakeskus.fi/aineistot/MV/Kunta/"
DRAINED = {"3", "7", "8", "9"}        # ojitettu kangas, ojikko, muuttuma, turvekangas
PEAT = {"2", "3", "4", "5"}           # korpi, räme, neva, letto
DEV_KEYS = {"A0": "da", "S0": "da", "T1": "dt", "T2": "dt", "Y1": "dt", "02": "d2", "03": "d3", "04": "d4",
            "05": "d5", "ER": "de"}
SPECIES_KEY = {"manty": "m", "kuusi": "k", "koivu": "b", "lehti": "l"}


def log(*a):
    print(*a, flush=True)


def trade_of(dc):
    """Kehitysluokka → kauppatapa, jonka hinnoin 'arvo hakkuutavan hinnoin' lasketaan."""
    if dc in ("04", "05", "ER", "S0", "Y1"):
        return "UUD"
    if dc == "03":
        return "HAR"
    if dc == "02":
        return "ENS"
    return "PKAUP"


def muni_names():
    """Kuntien nimet config.py:n kommenteista ("834",  # Tammela)."""
    src = open(os.path.join(ROOT, "pipeline", "config.py"), encoding="utf-8").read()
    return {m: n.strip() for m, n in re.findall(r'"(\d{3})",\s*#\s*([^\n]+)', src)}


def norm(name):
    t = name.lower().translate(str.maketrans({"ä": "a", "ö": "o", "å": "a", "é": "e"}))
    return re.sub(r"[^a-z]", "", t)


def mv_index():
    r = net.get(MV_BASE)
    files = sorted(set(re.findall(r'href="(?:[^"]*/)?(MV_[^"/?]+\.zip)"', r.text)))
    return {norm(f[3:-4]): f for f in files}


# ---------- yhden kunnan laskenta ----------

def mv_download(fname, workdir):
    dest = os.path.join(workdir, fname)
    with net.session().get(MV_BASE + fname, stream=True, timeout=900) as r:
        r.raise_for_status()
        modified = r.headers.get("Last-Modified", "")
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    with zipfile.ZipFile(dest) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".gpkg"))
        z.extract(name, workdir)
    os.remove(dest)
    return os.path.join(workdir, name), modified


def lonlat_geom(g):
    """Shapely-geometria (EPSG:3067) → GeoJSON MultiPolygon -koordinaatit (lon, lat; 6 desimaalia ≈ 0,1 m)."""
    out = []
    for p in getattr(g, "geoms", [g]):
        if p.geom_type != "Polygon" or p.is_empty:
            continue
        rings = []
        for ring in (p.exterior, *p.interiors):
            pts = []
            for x, y in ring.coords:
                lat, lon = tm35_to_latlon(x, y)
                pts.append([round(lon, 6), round(lat, 6)])
            rings.append(pts)
        out.append(rings)
    return out


def compute_kunta(muni, mv_file, client, workdir):
    """Palauttaa kunnan metsätilat välimuistiin tallennettavassa muodossa."""
    t0 = time.time()
    gp, modified = mv_download(mv_file, workdir)
    try:
        stands, _ = read_stands(gp, verbose=False)
    finally:
        os.remove(gp)
    t_mv = time.time() - t0
    raw = municipality_parcels(client, muni, workdir, log=log)
    parcels = []
    for p in raw:
        if p["ref"].startswith(muni.zfill(3)):
            g = to_shape(p["polys"])
            if g is not None and not g.is_empty:
                parcels.append((p["ref"], g))
    t_mml = time.time() - t0 - t_mv
    allb, resb = collections.Counter(), collections.Counter()
    for b in ryhti.buildings(muni):
        k = b.get("property_identifier")
        if k:
            allb[k] += 1
            resb[k] += keep(b)

    P = collections.defaultdict(lambda: collections.defaultdict(float))
    palstat = collections.defaultdict(list)
    for kt, g in parcels:
        P[kt]["ka"] += g.area / 1e4
        palstat[kt].append(g)
    inv = collections.defaultdict(list)
    tree = STRtree([g for _, g in parcels])
    for s in stands.values():
        g = s["geom"]
        for i in tree.query(g, predicate="intersects"):
            kt, pg = parcels[i]
            a = g.intersection(pg).area
            if a < 1:
                continue
            ha = a / 1e4
            T = P[kt]
            mg = s.get("mg")
            if mg == "1":
                T["mm"] += ha
            elif mg in ("2", "3"):
                T["kj"] += ha
            else:
                T["mk"] += ha
            if mg == "1":
                dc = s.get("dc") or ""
                T["dc_" + dc] += ha
                T["fc_" + str(s.get("fc"))] += ha
                T["tu"] += ha if s.get("sg") in PEAT else 0
                T["oj"] += ha if s.get("dr") in DRAINED else 0
                T["hr"] += ha if s.get("restr") else 0
            if s.get("inv"):
                inv[kt].append(s["inv"][:7])
            if "vol" not in s:
                continue
            vol, saw, pulp = s["vol"] * ha, s["saw"] * ha, s["pulp"] * ha
            T["v"] += vol
            if s.get("age") is not None:
                T["ia"] += s["age"] * ha
                T["ih"] += ha
            for grp, sh in s["share"]["vol"].items():
                T["sp_" + grp] += vol * sh
            trade = trade_of(s.get("dc") or "")
            for kind, amount in (("tukki", saw), ("kuitu", pulp)):
                for grp, sh in s["share"]["saw" if kind == "tukki" else "pulp"].items():
                    T[f"am_{trade}|{ASSORT[(price_group(grp), kind)]}"] += amount * sh

    tilat = []
    for kt, T in P.items():
        grp = kt[6:10]
        if grp == "0876" or grp.startswith("99") or T["mm"] <= config.METSA_MIN_FOREST_HA:
            continue
        geom = unary_union([g.simplify(1.0) for g in palstat[kt]])
        big = max(palstat[kt], key=lambda g: g.area).representative_point()
        lat, lon = tm35_to_latlon(big.x, big.y)
        rec = {k: round(v, 3) for k, v in T.items() if v}
        rec.update(k=kt, pn=len(palstat[kt]), rb=allb.get(kt, 0), ab=resb.get(kt, 0),
                   pt=[round(lon, 6), round(lat, 6)], g=lonlat_geom(geom))
        if inv.get(kt):
            rec["i0"], rec["i1"] = min(inv[kt]), max(inv[kt])
        tilat.append(rec)
    log(f"  kunta {muni}: {len(stands)} kuviota, {len(parcels)} palstaa, {len(tilat)} metsätilaa; "
        f"Metsäkeskus {t_mv:.0f} s, MML {t_mml:.0f} s, yhteensä {time.time() - t0:.0f} s")
    return {"date": dt.date.today().isoformat(), "v": VERSION, "mv": modified, "n": len(tilat), "tilat": tilat}


# ---------- välimuisti ----------

def cache_path(cache, muni):
    return os.path.join(cache, "metsa", f"{muni}.json.gz")


def load_kunta(cache, muni):
    p = cache_path(cache, muni)
    if not os.path.exists(p):
        return None
    with gzip.open(p, "rt", encoding="utf-8") as f:
        return json.load(f)


def kunta_info(cache, muni):
    """Kevyt tila (päivä, versio) ilman koko tiedoston lukemista: tallennetaan erilliseen hakemistoon."""
    p = os.path.join(cache, "metsa", "state.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8")).get(muni)
    return None


def save_kunta(cache, muni, data):
    os.makedirs(os.path.join(cache, "metsa"), exist_ok=True)
    tmp = cache_path(cache, muni) + ".tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, cache_path(cache, muni))
    sp = os.path.join(cache, "metsa", "state.json")
    state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    state[muni] = {"date": data["date"], "v": data["v"], "n": data["n"], "mv": data["mv"]}
    json.dump(state, open(sp, "w", encoding="utf-8"), indent=0, sort_keys=True)
    with open(os.path.join(cache, "metsa.stamp"), "w") as f:  # välimuistin avain (workflow)
        f.write(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))


def due(cache, munis, today):
    """Haettavat kunnat: puuttuvat ensin, sitten vanhentuneet / vanhalla laskentaversiolla vanhimmasta alkaen."""
    out = []
    for m in munis:
        info = kunta_info(cache, m)
        if not info or not os.path.exists(cache_path(cache, m)):
            out.append(("0000-00-00", m))
        elif info["v"] != VERSION or (today - dt.date.fromisoformat(info["date"])).days >= config.METSA_MAX_AGE_DAYS:
            out.append((info["date"], m))
    return [m for _, m in sorted(out)]


# ---------- julkaisutiedostot ----------

def price_table(areas):
    """{alue: {(kauppatapa, puutavaralaji): (hinta, kuukausi)}} – yksi Luke-kysely per hinta-alue."""
    out = {}
    for a in sorted(set(areas)):
        out[a] = luke_prices(a)[0]
    return out


def props(rec, prices, area):
    def pr(trade, ptl):
        for t in (trade, "HAR", "PKAUP"):
            if (t, ptl) in prices:
                return prices[(t, ptl)][0]
        return 0.0
    mm = rec.get("mm", 0)
    e_t = e_k = e_h = 0.0
    saw = pulp = 0.0
    for key, amount in rec.items():
        if not key.startswith("am_"):
            continue
        trade, ptl = key[3:].split("|")
        p_avg = pr("PKAUP", ptl)
        if ptl.startswith("TUK"):
            e_t += amount * p_avg
            saw += amount
        else:
            e_k += amount * p_avg
            pulp += amount
        e_h += amount * pr(trade, ptl)
    e = e_t + e_k
    v = rec.get("v", 0)
    p = {
        "k": fmt_kt(rec["k"]), "ka": round(rec.get("ka", 0), 1), "mm": round(mm, 1), "kj": round(rec.get("kj", 0), 1),
        "mu": round(max(0.0, rec.get("ka", 0) - mm - rec.get("kj", 0) - rec.get("mk", 0)), 1),
        "mt": round(100 * (mm + rec.get("kj", 0) + rec.get("mk", 0)) / rec["ka"]) if rec.get("ka") else 0,
        "pn": rec.get("pn", 1), "e": round(e), "eh": round(e / mm) if mm else 0, "eu": round(e_h),
        "et": round(e_t), "ek": round(e_k), "t": round(saw), "ku": round(pulp),
        "v": round(v), "vh": round(v / mm) if mm else 0, "pa": area,
        "rb": rec.get("rb", 0), "ab": rec.get("ab", 0),
    }
    sp = {SPECIES_KEY[g]: rec.get("sp_" + g, 0) for g in SPECIES_KEY}
    for key, val in sp.items():
        if val >= 0.5:
            p["s" + key] = round(val)
    if v > 0:
        p["ps"] = max(sp, key=sp.get)
    if rec.get("ih"):
        p["ik"] = round(rec["ia"] / rec["ih"])
    dev = collections.Counter()
    for code, key in DEV_KEYS.items():
        dev[key] += rec.get("dc_" + code, 0)
    for key, ha in dev.items():
        if mm and ha:
            p[key] = round(100 * ha / mm)
    fcs = {k[3:]: val for k, val in rec.items() if k.startswith("fc_") and k[3:] not in ("", "None")}
    if fcs:
        p["kp"] = int(max(fcs, key=fcs.get))
    for key in ("tu", "oj", "hr"):
        p[key] = round(100 * rec.get(key, 0) / mm) if mm else 0
    for key in ("i0", "i1"):
        if rec.get(key):
            p[key] = rec[key]
    return p


def write_features(path, feats):
    with open(path, "w", encoding="utf-8") as f:
        for ft in feats:
            f.write(json.dumps(ft, ensure_ascii=False, separators=(",", ":")) + "\n")


def tippecanoe(src, out, layer, zmin, zmax, extra=()):
    cmd = ["tippecanoe", "-o", out, "--force", "--quiet", f"-Z{zmin}", f"-z{zmax}", "-l", layer,
           "--no-tile-size-limit", "--no-feature-limit", *extra, src]
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)
    size = os.path.getsize(out) / 1e6
    if size > 95:
        fail(f"{os.path.basename(out)} on {size:.1f} Mt, yli GitHub Pagesin rajan")
    return size


def previous_meta():
    try:
        return net.get(config.METSA_SITE_URL + "data/meta.json", {"t": str(int(time.time()))}, tries=3, timeout=30).json()
    except Exception as e:  # noqa: BLE001
        log(f"  julkaistua meta.jsonia ei saatu ({e}); turvatarkistus ohitetaan")
        return None


def publish_problems(prev, regions_ready, muni_counts):
    if not prev:
        return []
    out = []
    for r in prev.get("regions", []):
        if r["name"] in config.METSA_REGIONS and r["name"] not in regions_ready:
            out.append(f"Maakunta {r['name']} on julkaistu, mutta sen tiedot ovat nyt kesken; se putoaisi pois")
    for m, old in (prev.get("muni_counts") or {}).items():
        if m in muni_counts:
            lost = old - muni_counts[m]
            if lost > max(config.DROP_MIN, old * config.DROP_PCT / 100):
                out.append(f"Kunta {m}: metsätiloja {muni_counts[m]}, edellisessä julkaisussa {old} (−{lost})")
    return out


def build_site(cache, out, work, regions_ready):
    data_dir = os.path.join(out, "data")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    region_of = {m: r for r in regions_ready for m in config.REGIONS[r]}
    areas = {m: PRICE_AREA_MUNI.get(m, PRICE_AREA[r]) for m, r in region_of.items()}
    prices = price_table(areas.values())
    for a, tab in prices.items():
        log(f"Kantohinnat {a}: " + ", ".join(f"{k[0]}/{k[1]} {v[0]} ({v[1]})" for k, v in sorted(tab.items())))
        if not tab:
            fail(f"Luken kantohintoja ei saatu hinta-alueelle {a}")

    regions_meta, muni_counts, munis_meta = [], {}, {}
    pts = os.path.join(work, "fp.geojsonl")
    total = 0
    with open(pts, "w", encoding="utf-8") as fp:
        for r in regions_ready:
            src = os.path.join(work, f"f-{slug(r)}.geojsonl")
            n = 0
            lons, lats = [], []
            with open(src, "w", encoding="utf-8") as fpoly:
                for m in config.REGIONS[r]:
                    data = load_kunta(cache, m)
                    muni_counts[m] = len(data["tilat"])
                    munis_meta[m] = {"date": data["date"], "mv": data["mv"]}
                    for rec in data["tilat"]:
                        p = props(rec, prices[areas[m]], areas[m])
                        if rec["g"]:
                            fpoly.write(json.dumps({"type": "Feature", "properties": p, "geometry":
                                                    {"type": "MultiPolygon", "coordinates": rec["g"]}},
                                                   ensure_ascii=False, separators=(",", ":")) + "\n")
                        fp.write(json.dumps({"type": "Feature", "properties": p, "geometry":
                                             {"type": "Point", "coordinates": rec["pt"]}},
                                            ensure_ascii=False, separators=(",", ":")) + "\n")
                        lons.append(rec["pt"][0])
                        lats.append(rec["pt"][1])
                        n += 1
            fname = f"f-{slug(r)}.pmtiles"
            size = tippecanoe(src, os.path.join(data_dir, fname), "f", config.METSA_POLY_MINZOOM, 14,
                              ["--detect-shared-borders"])
            log(f"Maakunta {r}: {n} metsätilaa, {fname} {size:.1f} Mt")
            regions_meta.append({"name": r, "file": fname, "count": n,
                                 "bounds": [min(lons), min(lats), max(lons), max(lats)] if n else None})
            total += n
    size = tippecanoe(pts, os.path.join(data_dir, "fp.pmtiles"), "fp", 6, config.METSA_POLY_MINZOOM - 1, ["-r1"])
    log(f"Pisteet: fp.pmtiles {size:.1f} Mt")

    used = {}
    for a, tab in prices.items():
        used[a] = {f"{k[0]}|{k[1]}": v for k, v in tab.items()}
    meta = {
        "updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": total, "regions": regions_meta, "muni_counts": muni_counts, "munis": munis_meta,
        "prices": used, "poly_minzoom": config.METSA_POLY_MINZOOM, "min_forest_ha": config.METSA_MIN_FOREST_HA,
        "version": VERSION,
    }
    with open(os.path.join(data_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False)
    shutil.copytree(os.path.join(ROOT, "metsa_web"), out, dirs_exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    idx = os.path.join(out, "index.html")
    html = open(idx, encoding="utf-8").read().replace('src="esikatselu.js"', f'src="esikatselu.js?v={stamp}"')
    open(idx, "w", encoding="utf-8").write(html)
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--cache", default="cache")
    ap.add_argument("--work", default="work")
    args = ap.parse_args(argv)
    t0 = time.time()
    os.makedirs(args.work, exist_ok=True)
    today = dt.date.today()
    munis = [m for r in config.METSA_REGIONS for m in config.REGIONS[r]]
    names = muni_names()
    todo = due(args.cache, munis, today)
    log(f"Metsakartta: maakunnat {config.METSA_REGIONS}, kuntia {len(munis)}, haettavana {len(todo)}")
    errors = []
    if todo:
        index = mv_index()
        client = MMLFiles(log=log)
        for i, m in enumerate(todo):
            if time.time() - t0 > config.METSA_TIME_BUDGET_MIN * 60:
                log(f"Aikaraja {config.METSA_TIME_BUDGET_MIN} min: {len(todo) - i} kuntaa jää seuraavaan ajoon")
                break
            fname = index.get(norm(names.get(m, m)))
            if not fname:
                errors.append(f"kunta {m} ({names.get(m)}): Metsäkeskuksen tiedostoa ei löytynyt")
                log("  VIRHE " + errors[-1])
                continue
            try:
                save_kunta(args.cache, m, compute_kunta(m, fname, client, args.work))
            except Exception as e:  # noqa: BLE001 – yksi kunta ei kaada muita; jää haettavaksi seuraavaan ajoon
                errors.append(f"kunta {m} ({names.get(m)}): {type(e).__name__}: {e}"[:300])
                log("  VIRHE " + errors[-1])

    ready = [r for r in config.METSA_REGIONS if all(os.path.exists(cache_path(args.cache, m)) for m in config.REGIONS[r])]
    waiting = [r for r in config.METSA_REGIONS if r not in ready]
    if waiting:
        log(f"Kesken (julkaistaan, kun kaikki kunnat ovat valmiina): {waiting}")
    if not ready:
        fail("Yhtään maakuntaa ei ole valmiina julkaistavaksi. " + "; ".join(errors))
    counts = {m: (kunta_info(args.cache, m) or {}).get("n", 0) for r in ready for m in config.REGIONS[r]}
    problems = publish_problems(previous_meta(), ready, counts)
    if problems and os.environ.get("SKIP_CHECKS") != "true":
        fail("Turvatarkistus esti julkaisun: " + "; ".join(problems))
    meta = build_site(args.cache, args.out, args.work, ready)
    log(f"Valmis: {meta['count']} metsätilaa, maakunnat {[r['name'] for r in meta['regions']]}, {time.time() - t0:.0f} s")
    import resource
    log(f"Muistin huippu: ohjelma {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} Mt, "
        f"aliprosessit {resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024:.0f} Mt")
    if errors:
        fail(f"{len(errors)} kunnan haku epäonnistui (yritetään seuraavassa ajossa): " + "; ".join(errors))


if __name__ == "__main__":
    main(sys.argv[1:])
