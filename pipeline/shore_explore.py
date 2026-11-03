"""Koeajo: rantatieto yhdelle kunnalle (oletus Tammela 834). Ei vaikuta julkaistuun sivuun.

Käyttö: MML_API_KEY=... python -m pipeline.shore_explore 834 tulos/
Tulostaa vesialueiden kokoelmat, ajoajat ja yhteenvedon sekä kirjoittaa CSV:n tarkistusta varten.
"""
import csv
import os
import resource
import sys
import time
from collections import Counter, defaultdict

from . import build, mml, mml_files, ryhti, shore
from .tm35 import tm35_to_latlon


def main():
    muni = sys.argv[1] if len(sys.argv) > 1 else "834"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "rantatesti"
    os.makedirs(out_dir, exist_ok=True)
    T = {}
    client = mml_files.MMLFiles()

    cols = client.get_json(shore.MTK_BASE + "/collections?f=json").get("collections", [])
    ids = [c["id"] for c in cols]
    print("Maastotietokannan kokoelmia:", len(ids))
    print("Vesiin liittyvät:", [i for i in ids if any(s in i for s in ("jarvi", "meri", "vesi", "joki", "lampi", "ranta", "virta"))])
    water_cols = [c for c in ("jarvi", "meri", "virtavesialue") if c in ids]
    print("Käytetään:", water_cols)

    t = time.time()
    blds = [b for b in ryhti.buildings(muni) if build.keep(b)]
    addr = defaultdict(list)
    for a in ryhti.addresses(muni):
        if a.get("address_fin"):
            addr[a["building_key"]].append(a["address_fin"])
    T["ryhti"] = time.time() - t
    print(f"Asuinrakennuksia {len(blds)}")

    t = time.time()
    parcels = mml_files.municipality_parcels(client, muni, out_dir)
    T["palstat_lataus"] = time.time() - t
    print(f"Palstoja {len(parcels)}")

    xs, ys = [b["_x"] for b in blds], [b["_y"] for b in blds]
    pad = 2000
    bbox = (min(xs) - pad, min(ys) - pad, max(xs) + pad, max(ys) + pad)
    t = time.time()
    water = shore.fetch_water(client, water_cols, bbox)
    T["vesialueet_lataus"] = time.time() - t
    print(f"Vesialueita {len(water)}; esimerkkiominaisuudet: {[w[3] for w in water[:2]]}")

    t = time.time()
    index = mml.ParcelIndex(parcels)
    by_ref = defaultdict(list)
    for p in parcels:
        by_ref[p["ref"]].append(p)
    W = shore.Water(water)
    T["indeksit"] = time.time() - t

    t = time.time()
    cache = {}

    def cls(p):
        if p["id"] not in cache:
            cache[p["id"]] = W.classify(shore.parcel_geom(p["polys"]))
        return cache[p["id"]]
    rows = []
    for b in blds:
        kt = b.get("property_identifier") or ""
        par = index.find(b["_x"], b["_y"], prefer_ref=kt)
        r = {"rakennustunnus": b.get("permanent_building_identifier"), "osoite": " / ".join(addr.get(b["building_key"], [])),
             "kiinteistotunnus": build.fmt_kt(kt), "tyyppi": ryhti.code(b.get("main_purpose"))}
        if not par:
            r["tulos"] = "ei palstaa"
        else:
            c = cls(par)
            r.update(c)
            r["tulos"] = c["luokka"]
            if c["luokka"] != "ranta":
                # kiinteistön muu palsta (esim. erillinen rantapalsta tien toisella puolella)
                others = [cls(q) for q in by_ref.get(par["ref"], []) if q["id"] != par["id"]]
                if any(o["luokka"] == "ranta" for o in others):
                    r["tulos"] = "erillinen rantapalsta"
                    r["rantaviiva"] = max(o["rantaviiva"] for o in others if o["luokka"] == "ranta")
        lat, lon = tm35_to_latlon(b["_x"], b["_y"])
        r["kartta"] = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
        r["karttapaikka"] = (f"https://asiointi.maanmittauslaitos.fi/karttapaikka/?lang=fi&share=customMarker"
                             f"&n={round(b['_y'])}&e={round(b['_x'])}&title=&desc=&zoom=12")
        rows.append(r)
    T["laskenta"] = time.time() - t

    cnt = Counter(r["tulos"] for r in rows)
    by_type = Counter((r["tyyppi"], r["tulos"]) for r in rows)
    print("\n== Tulos (asuinrakennukset):", dict(cnt))
    print("  tyypeittäin (01 vapaa-ajan, 05 pientalo, 06 kerrostalo):", sorted(by_type.items()))
    print("  rannan lähin vesialue:", Counter(r.get("laji") for r in rows if r["tulos"] in ("ranta", "todennäköisesti")))
    print("  rantaviiva (m) rantatonteilla, mediaani:",
          sorted(r["rantaviiva"] for r in rows if r["tulos"] == "ranta")[cnt["ranta"] // 2] if cnt["ranta"] else "-")
    print("  pienen vesialueen (< 1 ha) rannat:", sum(1 for r in rows if r["tulos"] == "ranta" and (r.get("vesiala_ha") or 0) < 1))
    print("\n== Ajoajat (s):", {k: round(v, 1) for k, v in T.items()})
    print(f"   laskettuja palstoja {len(cache)}, {1000 * T['laskenta'] / max(1, len(cache)):.1f} ms/palsta")
    print(f"   muistin huippukäyttö {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} Mt")

    fields = ["tulos", "osoite", "kiinteistotunnus", "tyyppi", "rantaviiva", "etaisyys", "laji", "vesiala_ha",
              "rakennustunnus", "kartta", "karttapaikka"]
    path = os.path.join(out_dir, f"rantatesti_{muni}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["tulos"], r["osoite"])))
    print("CSV:", path)


if __name__ == "__main__":
    main()
