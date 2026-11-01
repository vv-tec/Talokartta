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

from . import config, mml, ryhti
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


def make_records(buildings, addresses, parcels):
    """Yhdistää rakennukset, osoitteet ja palstat. Palauttaa listan (x, y, lat, lon, props)."""
    addr = defaultdict(list)
    for a in addresses:
        if a.get("address_fin") and a["address_fin"] not in [s for s, _, _ in addr[a["building_key"]]]:
            addr[a["building_key"]].append((a["address_fin"], a.get("postal_code") or "", a.get("postal_office_fin") or ""))

    ref_area, ref_n = defaultdict(float), Counter()
    for p in parcels:
        p.setdefault("area", mml.parcel_area(p))
        ref_area[p["ref"]] += p["area"]
        ref_n[p["ref"]] += 1
    index = mml.ParcelIndex(parcels) if parcels else None

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
            "ex": round(x), "ny": round(y),
        }
        par = index.find(x, y, prefer_ref=kt) if index else None
        if par:
            props["pa"] = round(par["area"])
        ref = kt if kt in ref_area else (par["ref"] if par else None)
        if ref:
            props["ka"] = round(ref_area[ref])
            props["pn"] = ref_n[ref]
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


def make_tiles(work, out_file):
    """Jokainen taso tehdään omana ajonaan omille zoomeilleen ja yhdistetään lopuksi.
    (Ominaisuuskohtaiset "tippecanoe"-zoomit saivat tippecanoe 2.49:n jättämään vain yhden pisteen tiiltä kohden.)"""
    parts = [("b", "b.geojsonl", config.BUILDING_MINZOOM, 14)]
    parts += [("g", f"g{c['size']}.geojsonl", c["minzoom"], c["maxzoom"]) for c in config.DENSITY_GRIDS]
    mbt = []
    for layer, src, zmin, zmax in parts:
        out = os.path.join(work, src.replace(".geojsonl", ".mbtiles"))
        cmd = ["tippecanoe", "-o", out, "--force", "--quiet", f"-Z{zmin}", f"-z{zmax}", "-r1",
               "--no-feature-limit", "--no-tile-size-limit", "-l", layer, os.path.join(work, src)]
        log(" ".join(cmd))
        subprocess.run(cmd, check=True)
        mbt.append(out)
    cmd = ["tile-join", "-o", out_file, "--force", "--quiet", "--no-tile-size-limit",
           "-n", "Talokartta", "-A", "SYKE Ryhti (CC BY 4.0), Maanmittauslaitos (CC BY 4.0)", *mbt]
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)


def meta(records, municipalities):
    lats = [r[2] for r in records]
    lons = [r[3] for r in records]
    years = [r[4]["y"] for r in records if "y" in r[4]]
    return {
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "count": len(records),
        "municipalities": municipalities,
        "bounds": [min(lons), min(lats), max(lons), max(lats)],
        "years": [min(years), max(years)] if years else None,
        "title": config.REGION_TITLE,
        "building_minzoom": config.BUILDING_MINZOOM,
        "by_type": Counter(r[4].get("p", "") for r in records),
        "by_status": Counter(r[4].get("s", "") for r in records),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--work", default="work")
    ap.add_argument("--cache", default="cache")
    args = ap.parse_args(argv)
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(os.path.join(args.out, "data"), exist_ok=True)

    blds, addrs, tiles = [], [], set()
    pad = config.PARCEL_BBOX_PAD_M
    for m in config.MUNICIPALITIES:
        mb = [b for b in ryhti.buildings(m) if keep(b)]
        if not mb:  # jokaisessa kunnassa on asuinrakennuksia; tyhjä tulos = haku epäonnistui
            sys.exit(f"Kunta {m}: ei yhtään asuinrakennusta, julkaisua ei tehdä.")
        keys = {b.get("building_key") for b in mb}
        ma = [a for a in ryhti.addresses(m) if a.get("building_key") in keys]
        log(f"Kunta {m}: {len(mb)} asuinrakennusta, {len(ma)} osoitetta")
        blds += mb
        addrs += ma
        xs, ys = [b["_x"] for b in mb], [b["_y"] for b in mb]
        tiles |= mml.tiles_for_bbox(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)

    log(f"Kiinteistöpalstat: {len(tiles)} hakuruutua")
    cache = mml.ParcelCache(os.path.join(args.cache, "parcels.json.gz"), config.PARCEL_MAX_AGE_DAYS, log=log)
    parcels = cache.get(tiles)
    cache.save()
    log(f"  palstoja käytössä {len(parcels)}")
    records = make_records(blds, addrs, parcels)
    log(f"Valmis: {len(records)} rakennusta, joista palsta löytyi {sum(1 for r in records if 'pa' in r[4])}")

    if len(records) < 100:
        sys.exit(f"Liian vähän rakennuksia ({len(records)}); jotain meni pieleen, julkaisua ei tehdä.")

    write_lines(os.path.join(args.work, "b.geojsonl"), building_features(records))
    for c in config.DENSITY_GRIDS:
        write_lines(os.path.join(args.work, f"g{c['size']}.geojsonl"), density(records, c["size"]))
    make_tiles(args.work, os.path.join(args.out, "data", "talot.pmtiles"))
    with open(os.path.join(args.out, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta(records, config.MUNICIPALITIES), f, ensure_ascii=False)
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
