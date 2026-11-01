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


def density(records):
    feats = []
    for cfg in config.DENSITY_GRIDS:
        s = cfg["size"]
        cells = Counter((int(x // s), int(y // s)) for x, y, *_ in records)
        for (i, j), n in cells.items():
            lat, lon = tm35_to_latlon((i + 0.5) * s, (j + 0.5) * s)
            feats.append({
                "type": "Feature",
                "tippecanoe": {"minzoom": cfg["minzoom"], "maxzoom": cfg["maxzoom"]},
                "properties": {"n": n, "s": s},
                "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
            })
    return feats


def building_features(records):
    for x, y, lat, lon, props in records:
        yield {
            "type": "Feature",
            "tippecanoe": {"minzoom": config.BUILDING_MINZOOM},
            "properties": props,
            "geometry": {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]},
        }


def write_lines(path, feats):
    with open(path, "w", encoding="utf-8") as f:
        for ft in feats:
            f.write(json.dumps(ft, ensure_ascii=False, separators=(",", ":")) + "\n")


def make_tiles(work, out_file):
    cmd = [
        "tippecanoe", "-o", out_file, "--force", "--quiet",
        # -B0: kaikki pisteet mukaan kaikilla zoomeilla (tippecanoe 2.49:n -r1 jätti vain yhden pisteen per tiili)
        "-Z0", "-z14", "-B0", "--no-feature-limit", "--no-tile-size-limit",
        "-n", "Talokartta",
        "--attribution", "SYKE Ryhti (CC BY 4.0), Maanmittauslaitos (CC BY 4.0)",
        "-L", json.dumps({"file": os.path.join(work, "b.geojsonl"), "layer": "b"}),
        "-L", json.dumps({"file": os.path.join(work, "g.geojsonl"), "layer": "g"}),
    ]
    log("tippecanoe:", " ".join(cmd))
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
        "building_minzoom": config.BUILDING_MINZOOM,
        "by_type": Counter(r[4].get("p", "") for r in records),
        "by_status": Counter(r[4].get("s", "") for r in records),
    }


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--work", default="work")
    args = ap.parse_args(argv)
    os.makedirs(args.work, exist_ok=True)
    os.makedirs(os.path.join(args.out, "data"), exist_ok=True)

    records = []
    for m in config.MUNICIPALITIES:
        log(f"Kunta {m}: rakennukset")
        blds = [b for b in ryhti.buildings(m) if keep(b)]
        log(f"  asuinrakennuksia {len(blds)}")
        if not blds:
            continue
        log(f"Kunta {m}: osoitteet")
        keys = {b.get("building_key") for b in blds}
        addrs = [a for a in ryhti.addresses(m) if a.get("building_key") in keys]
        log(f"  osoitteita {len(addrs)}")
        pad = config.PARCEL_BBOX_PAD_M
        xs, ys = [b["_x"] for b in blds], [b["_y"] for b in blds]
        log(f"Kunta {m}: kiinteistöpalstat")
        parcels = mml.parcels_in_bbox(min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad, log=log)
        recs = make_records(blds, addrs, parcels)
        with_plot = sum(1 for r in recs if "pa" in r[4])
        log(f"  valmis: {len(recs)} rakennusta, joista palsta löytyi {with_plot}")
        records.extend(recs)

    if len(records) < 100:
        sys.exit(f"Liian vähän rakennuksia ({len(records)}); jotain meni pieleen, julkaisua ei tehdä.")

    write_lines(os.path.join(args.work, "b.geojsonl"), building_features(records))
    write_lines(os.path.join(args.work, "g.geojsonl"), density(records))
    make_tiles(args.work, os.path.join(args.out, "data", "talot.pmtiles"))
    with open(os.path.join(args.out, "data", "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta(records, config.MUNICIPALITIES), f, ensure_ascii=False)
    shutil.copytree(os.path.join(ROOT, "web"), args.out, dirs_exist_ok=True)
    log("Sivusto valmis:", args.out)


if __name__ == "__main__":
    main()
