"""Data-ajo: hakee rekisteritiedot, yhdistää ne ja tekee karttatiilet sekä valmiin sivuston.

Käyttö (repositorion juuresta):
    python -m pipeline.build --out dist
"""
import argparse
import datetime as dt
import json
import os
import shutil
import subprocess
import sys
import time
from collections import Counter, defaultdict

from . import config, mml, mml_files, net, ryhti, ryhti_store
from .tm35 import tm35_to_latlon

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def fmt_kt(k):
    """'83440400030064' -> '834-404-3-64'"""
    if not k or len(k) != 14 or not k.isdigit():
        return k or ""
    return f"{int(k[0:3])}-{int(k[3:6])}-{int(k[6:10])}-{int(k[10:14])}"


def keep(p):
    return (
        ryhti.code(p.get("main_purpose")) in config.RESIDENTIAL
        and ryhti.code(p.get("usage_status")) not in config.EXCLUDED_STATUS
        and not p.get("demolition_date")
    )


def known(uri):
    c = ryhti.code(uri)
    return None if c in ("", "00") else c


CODE_KEYS = ("m", "fa", "r", "h", "e")  # koodikentät, joiden jakauma kirjataan meta.jsoniin suodattimia varten


def make_records(buildings, addresses, presults, shore_res=None):
    """Yhdistää rakennukset, osoitteet ja palstatulokset ({building_key: [pa, ka, pn]}, ks. mml.parcel_results).
    Palauttaa listan (x, y, lat, lon, props)."""
    addr = defaultdict(list)
    for a in addresses:
        if a.get("address_fin") and a["address_fin"] not in [s for s, _, _ in addr[a["building_key"]]]:
            addr[a["building_key"]].append((a["address_fin"], a.get("postal_code") or "", a.get("postal_office_fin") or ""))

    per_property = Counter(b.get("property_identifier") for b in buildings)
    out = []
    for b in buildings:
        x, y = b["_x"], b["_y"]
        lat, lon = tm35_to_latlon(x, y)
        kt = b.get("property_identifier") or ""
        date = (b.get("completion_date") or "")[:10]
        a = addr.get(b.get("building_key"), [])
        props = {
            "id": b.get("permanent_building_identifier") or "",
            "k": fmt_kt(kt),
            "a": " / ".join(s for s, _, _ in a),
            "pc": a[0][1] if a else "",
            "po": a[0][2].title() if a else "",
            "p": ryhti.code(b.get("main_purpose")),
            "s": ryhti.code(b.get("usage_status")),
            "d": date,
            "y": int(date[:4]) if date[:4].isdigit() else None,
            "g": b.get("gross_floor_area") or None,
            "t": b.get("total_area") or None,
            "f": b.get("number_of_storeys") or None,
            "n": b.get("apartment_count") if b.get("apartment_count") is not None else None,
            "c": per_property[kt] if kt else None,
            # rakenteet ja lämmitys koodeina (selitteet web/app.js); "00" = ei tiedossa -> jätetään pois
            "m": known(b.get("material_of_load_bearing_structures")),
            "fa": known(b.get("facade_material")),
            "r": known(b.get("construction_method")),
            "h": known(b.get("heating_method")),
            "e": known(b.get("heating_energy_source")),
            "v": b.get("volume") or None,
            "ha": b.get("floor_area") or None,
            "sj": {True: 1, False: 0}.get(b.get("is_protected")),
            "ex": round(x), "ny": round(y),
        }
        pa, ka, pn = presults.get(b.get("building_key")) or (None, None, None)
        props.update(pa=pa, ka=ka, pn=pn)
        sr = (shore_res or {}).get(b.get("building_key"))
        if sr:  # RANTA: ra luokka, rl rantaviiva m, rd etäisyys vedestä m, rw vesilaji, rwa vesialueen ala ha
            ra, rl, rd, rw, rwa = sr
            props.update(ra=ra, rl=rl or None, rd=rd, rw=rw, rwa=rwa)
        out.append((x, y, lat, lon, {k: v for k, v in props.items() if v not in (None, "")}))
    return out


def density(records, size):
    """Tiheysruudut: rakennusten määrä kussakin size×size-metrin ruudussa, piste ruudun keskellä."""
    feats = []
    cells = Counter((int(x // size), int(y // size)) for x, y, *_ in records)
    for (i, j), n in cells.items():
        lat, lon = tm35_to_latlon((i + 0.5) * size, (j + 0.5) * size)
        feats.append({
            "type": "Feature",
            "properties": {"n": n, "s": size},
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        })
    return feats


def building_features(records):
    for x, y, lat, lon, props in records:
        yield {
            "type": "Feature",
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        }


def write_lines(path, feats):
    with open(path, "w", encoding="utf-8") as f:
        for ft in feats:
            f.write(json.dumps(ft, ensure_ascii=False, separators=(",", ":")) + "\n")


MAX_FILE_MB = 95  # GitHub Pagesin raja on 100 Mt tiedostoa kohden


def slug(name):
    """'Kanta-Häme' -> 'kanta-hame' (tiedostonimiin)."""
    t = name.lower().translate(str.maketrans({"ä": "a", "ö": "o", "å": "a"}))
    return "".join(c if c.isalnum() else "-" for c in t).strip("-")


def run(cmd):
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)


def tippecanoe(src, out, layer, zmin, zmax):
    # Ei ominaisuuskohtaisia "tippecanoe"-zoomeja: ne saivat tippecanoe 2.49:n jättämään vain yhden pisteen tiiltä kohden.
    run(["tippecanoe", "-o", out, "--force", "--quiet", f"-Z{zmin}", f"-z{zmax}", "-r1",
         "--no-feature-limit", "--no-tile-size-limit", "-l", layer,
         "-n", "Talokartta", "-A", "SYKE Ryhti (CC BY 4.0), Maanmittauslaitos (CC BY 4.0)", src])


def make_tiles(records, regions, work, data_dir):
    """Rakennukset: oma tiedosto maakunnittain (b-<maakunta>.pmtiles). Tiheysruudut: yksi yhteinen g.pmtiles."""
    out = []
    for name in sorted(set(regions)):
        recs = [r for r, reg in zip(records, regions) if reg == name]
        src = os.path.join(work, f"b-{slug(name)}.geojsonl")
        write_lines(src, building_features(recs))
        fname = f"b-{slug(name)}.pmtiles"
        tippecanoe(src, os.path.join(data_dir, fname), "b", config.BUILDING_MINZOOM, 14)
        lats, lons = [r[2] for r in recs], [r[3] for r in recs]
        out.append({"name": name, "file": fname, "count": len(recs),
                    "bounds": [min(lons), min(lats), max(lons), max(lats)]})
    parts = []
    for c in config.DENSITY_GRIDS:
        src = os.path.join(work, f"g{c['size']}.geojsonl")
        write_lines(src, density(records, c["size"]))
        mbt = src.replace(".geojsonl", ".mbtiles")
        tippecanoe(src, mbt, "g", c["minzoom"], c["maxzoom"])
        parts.append(mbt)
    run(["tile-join", "-o", os.path.join(data_dir, "g.pmtiles"), "--force", "--quiet", "--no-tile-size-limit", *parts])
    for f in sorted(os.listdir(data_dir)):
        mb = os.path.getsize(os.path.join(data_dir, f)) / 1e6
        log(f"  {f}: {mb:.1f} Mt")
        if mb > MAX_FILE_MB:
            fail(f"{f} on {mb:.0f} Mt, yli GitHub Pagesin rajan. Alue pitää jakaa pienempiin osiin.")
    return out


def meta(records, region_files, regions=None, muni_counts=None, shore_regions=None):
    lats = [r[2] for r in records]
    lons = [r[3] for r in records]
    years = [r[4]["y"] for r in records if "y" in r[4]]
    return {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "count": len(records),
        "municipalities": list(muni_counts) if muni_counts else config.MUNICIPALITIES,
        "muni_counts": muni_counts or {},
        "regions": region_files,
        "grid": "g.pmtiles",
        "bounds": [min(lons), min(lats), max(lons), max(lats)],
        "years": [min(years), max(years)] if years else None,
        "title": "Asuinrakennukset: " + ", ".join(regions) if regions else config.REGION_TITLE,
        "building_minzoom": config.BUILDING_MINZOOM,
        "by_type": Counter(r[4].get("p", "") for r in records),
        "by_status": Counter(r[4].get("s", "") for r in records),
        "by": {k: Counter(r[4].get(k, "") for r in records) for k in CODE_KEYS + ("ra",)},
        "shore_regions": shore_regions or [],
    }


def migrate_parcel_cache(cache_dir, pres, by_muni):
    """Kertaluonteinen siirto: vanhasta rajavälimuistista (parcels-mml.json.gz) lasketaan tulokset ilman uutta latausta."""
    old = os.path.join(cache_dir, "parcels-mml.json.gz")
    if not os.path.exists(old):
        return
    pc = mml.ParcelCache(old, 10 ** 6, None, log=log, label="kunta")
    for m, ids in pc.data["keys"].items():
        if m in pres.data["munis"]:
            continue
        parcels = [{"id": i, "ref": pc.data["parcels"][i]["ref"],
                    "polys": [[[tuple(c) for c in r] for r in rs] for rs in pc.data["parcels"][i]["polys"]]} for i in ids]
        pres.put(m, by_muni.get(m, []), parcels, date=pc.data["dates"][m])
    log(f"  vanhat palstarajat muunnettu tuloksiksi ({len(pc.data['keys'])} kuntaa); rajavälimuisti poistetaan")
    del pc
    os.remove(old)


def fail(msg):
    """Lopettaa ajon ilman julkaisua. GitHub Actionsissa viesti näkyy virheenä, ja ilmoitus (issue) poimii sen."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=Julkaisua ei tehty::{msg}", flush=True)
    sys.exit(msg)


def previous_meta():
    """Julkaistun sivun meta.json vertailua varten (None, jos ei saatavilla, esim. ensimmäinen julkaisu)."""
    try:
        return net.get(config.SITE_URL + "data/meta.json", {"t": str(int(time.time()))}, tries=3, timeout=30).json()
    except Exception as e:  # noqa: BLE001
        log(f"  julkaistua meta.jsonia ei saatu ({e}); turvatarkistus ohitetaan")
        return None


def publish_problems(prev, regions_ready, muni_counts, region_counts):
    """Turvatarkistus ennen julkaisua: estää vajaan kartan julkaisemisen rekisterihäiriön sattuessa.

    - asetuksissa oleva maakunta, joka on jo sivulla, ei saa pudota pois (esim. kesken jäänyt haku)
    - kunnan (tai vanhassa metassa maakunnan) rakennusmäärä ei saa pudota yli DROP_PCT % (vähintään DROP_MIN rakennusta)
    """
    if not prev:
        return []
    out = []

    def drop(name, old, new):
        lost = old - new
        if lost > max(config.DROP_MIN, old * config.DROP_PCT / 100):
            out.append(f"{name}: rakennuksia {new}, edellisessä julkaisussa {old} (−{lost}, {100 * lost / old:.1f} %)")
    for r in prev.get("regions", []):
        if r["name"] in config.REGIONS and r["name"] not in regions_ready:
            out.append(f"Maakunta {r['name']} on sivulla, mutta sen tiedot ovat nyt kesken; se putoaisi pois")
    if prev.get("muni_counts"):
        for m, old in prev["muni_counts"].items():
            if m in muni_counts:
                drop(f"Kunta {m}", old, muni_counts[m])
    else:
        for r in prev.get("regions", []):
            if r["name"] in region_counts:
                drop(f"Maakunta {r['name']}", r["count"], region_counts[r["name"]])
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--work", default="work")
    ap.add_argument("--cache", default="cache")
    args = ap.parse_args(argv)
    t0 = time.time()
    ryhti_deadline = t0 + config.RYHTI_TIME_BUDGET_MIN * 60
    deadline = t0 + config.PARCEL_TIME_BUDGET_MIN * 60
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(os.path.join(args.out, "data"), exist_ok=True)

    region_of = {m: r for r, ms in config.REGIONS.items() for m in ms}
    # RANTA: maakunnat, joille rantatieto lasketaan (tyhjä = pois päältä; ks. pipeline/shore.py)
    shore_munis = [m for r in config.SHORE_REGIONS if r in config.REGIONS for m in config.REGIONS[r]]
    shore_store = None

    # 1) Rakennukset ja osoitteet: tallessa olevaan tilaan vain muutokset (täysi haku kunnittain kuukauden välein).
    store = ryhti_store.RyhtiStore(os.path.join(args.cache, "ryhti.json.gz"), config.RYHTI_FULL_DAYS, keep=keep, log=log)
    store.update(config.MUNICIPALITIES, ryhti_deadline)
    by_muni = defaultdict(list)
    for b in store.buildings():
        by_muni[b["municipality_number"]].append(b)
    for m in config.MUNICIPALITIES:
        if store.ready(m) and not by_muni.get(m):  # jokaisessa kunnassa on asuinrakennuksia; tyhjä = haku epäonnistui
            fail(f"Kunta {m}: ei yhtään asuinrakennusta, julkaisua ei tehdä.")
    ryhti_ready = [m for m in config.MUNICIPALITIES if store.ready(m)]
    log(f"Rakennuksia {sum(len(by_muni[m]) for m in ryhti_ready)} ({len(ryhti_ready)}/{len(config.MUNICIPALITIES)} kuntaa valmiina)")

    # 2) Kiinteistöpalstat: tallessa vain rakennuskohtaiset tulokset (palstan ala, kiinteistön ala, palstojen määrä).
    #    Haetaan vain kunnille, joiden rakennukset ovat valmiina (tulokset lasketaan rakennuksille).
    if os.environ.get("MML_API_KEY"):
        log(f"Kiinteistöpalstat: MML:n tiedostopalvelu, {len(ryhti_ready)} kuntaa")
        client = None

        def get_client():
            nonlocal client
            client = client or mml_files.MMLFiles(log=log)
            return client

        def fetch(code):
            return mml_files.municipality_parcels(get_client(), code, args.work, log)
        pres = mml.ParcelResults(os.path.join(args.cache, "parcel-results.json.gz"), config.PARCEL_MAX_AGE_DAYS, fetch, log=log)
        migrate_parcel_cache(args.cache, pres, by_muni)
        force = []
        if shore_munis:  # RANTA (irrotettava lisäosa): lasketaan aina, kun kunnan palstat ladataan
            from . import shore  # Shapely tarvitaan vain tällöin
            shore_store = shore.ShoreResults(os.path.join(args.cache, "shore-results.json.gz"), log=log)

            def on_parcels(m, blds_m, parcels):
                if m not in shore_munis:
                    return
                t = time.time()
                water = shore.municipality_water(get_client(), blds_m, log)
                res = shore.compute(blds_m, parcels, water)
                shore_store.put(m, res)
                n = sum(1 for v in res.values() if v[0] in (2, 3))
                log(f"    ranta {m}: {len(water)} vesialuetta, {n}/{len(res)} omalla rannalla, {time.time() - t:.0f} s")
            pres.on_parcels = on_parcels
            # käyttöönotto: kunnat, joilta rantatulos puuttuu, haetaan heti (muuten vasta 14 pv kierrossa)
            force = [m for m in shore_munis if m in ryhti_ready and not shore_store.has(m)]
        presults = pres.get(ryhti_ready, by_muni, deadline, force=force)
        # uusille rakennuksille palstatieto heti pienellä aluehaulla (koko kunta haetaan vain PARCEL_MAX_AGE_DAYS välein)
        if pres.fill_new(ryhti_ready, by_muni, mml._fetch_box, deadline, limit=config.NEW_BUILDINGS_MAX_PER_RUN):
            presults = pres.collect(ryhti_ready)
        pres.prune(config.MUNICIPALITIES)
        parcels_ready = pres.ready
    else:
        # Varatapa ilman API-avainta: INSPIRE WFS ruuduittain (rajat tallessa ruuduittain); kaikki tai ei mitään.
        pad, tiles = config.PARCEL_BBOX_PAD_M, set()
        for m in ryhti_ready:
            xs, ys = [b["_x"] for b in by_muni[m]], [b["_y"] for b in by_muni[m]]
            tiles |= mml.tiles_for_bbox(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
        log(f"Kiinteistöpalstat: WFS, {len(tiles)} hakuruutua")
        pres = mml.ParcelCache(os.path.join(args.cache, "parcels.json.gz"), config.PARCEL_MAX_AGE_DAYS,
                               mml.wfs_tile_fetch, log=log, label="ruutu")
        presults = mml.parcel_results([b for m in ryhti_ready for b in by_muni[m]],
                                      pres.get((f"{i},{j}" for i, j in tiles), deadline))
        complete = not pres.missing
        parcels_ready = lambda m: complete  # noqa: E731
    # Tila tallennetaan joka ajossa (myös kun jotain puuttuu), jotta seuraava ajo jatkaa siitä.
    store.save()
    pres.save()
    shore_res = {}
    if shore_store:
        shore_store.prune(shore_munis)
        shore_store.save()
        shore_res = shore_store.collect(shore_munis)
    with open(os.path.join(args.cache, "parcels.stamp"), "w") as f:
        f.write(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))

    # 3) Julkaistaan maakunnat, joiden kaikki kunnat ovat valmiina; keskeneräiset tulevat sivulle myöhemmin.
    ready = {m for m in ryhti_ready if parcels_ready(m)}
    regions_ready = [r for r, ms in config.REGIONS.items() if all(m in ready for m in ms)]
    for r, ms in config.REGIONS.items():
        if r not in regions_ready:
            log(f"Maakunta {r} kesken: valmiina {sum(m in ready for m in ms)}/{len(ms)} kuntaa; julkaistaan, kun kaikki ovat valmiit")
    if not regions_ready:
        fail("Yksikään maakunta ei ole vielä valmis; haetut tiedot tallennettiin ja seuraava ajo jatkaa.")
    pub_munis = [m for r in regions_ready for m in config.REGIONS[r]]
    blds = [b for m in pub_munis for b in by_muni[m]]
    keys = {b["building_key"] for b in blds}
    addrs = [a for a in store.addresses() if a["building_key"] in keys]
    muni_counts = {m: len(by_muni[m]) for m in pub_munis}
    region_counts = {r: sum(muni_counts[m] for m in config.REGIONS[r]) for r in regions_ready}

    problems = publish_problems(previous_meta(), regions_ready, muni_counts, region_counts)
    if problems:
        if os.environ.get("SKIP_CHECKS") == "true":
            log("Turvatarkistuksen huomiot ohitettu käsiajon valinnalla:\n  " + "\n  ".join(problems))
        else:
            fail("Turvatarkistus esti julkaisun (tarkista, onko muutos todellinen; tarvittaessa käsiajo "
                 "valinnalla 'ohita_tarkistukset'): " + "; ".join(problems))

    for b in blds:
        b["_region"] = region_of[b["municipality_number"]]
    records = make_records(blds, addrs, presults, shore_res)
    log(f"Valmis: {len(records)} rakennusta, joista palsta löytyi {sum(1 for r in records if 'pa' in r[4])}")

    if len(records) < 100:
        fail(f"Liian vähän rakennuksia ({len(records)}); jotain meni pieleen, julkaisua ei tehdä.")

    region_files = make_tiles(records, [b["_region"] for b in blds], args.work, os.path.join(args.out, "data"))
    with open(os.path.join(args.out, "data", "meta.json"), "w", encoding="utf-8") as f:
        shore_regions = [r for r in regions_ready if r in config.SHORE_REGIONS
                         and shore_store and all(shore_store.has(m) for m in config.REGIONS[r])]
        json.dump(meta(records, region_files, regions_ready, muni_counts, shore_regions), f, ensure_ascii=False)
    shutil.copytree(os.path.join(ROOT, "web"), args.out, dirs_exist_ok=True)
    # versionumero tiedostonimiin, jotta selaimet hakevat päivitetyn sivun eivätkä käytä vanhaa välimuistista
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    idx = os.path.join(args.out, "index.html")
    html = open(idx, encoding="utf-8").read()
    html = html.replace('src="app.js"', f'src="app.js?v={stamp}"').replace('href="style.css"', f'href="style.css?v={stamp}"')
    open(idx, "w", encoding="utf-8").write(html)
    log("Sivusto valmis:", args.out)


if __name__ == "__main__":
    main()
