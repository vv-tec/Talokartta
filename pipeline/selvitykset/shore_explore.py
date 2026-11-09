"""Koeajo: rantatieto yhdelle kunnalle (oletus Tammela 834). Ei vaikuta julkaistuun sivuun.

Käyttö: MML_API_KEY=... python -m pipeline.selvitykset.shore_explore 834 tulos/
Tulostaa vesialueiden kokoelmat, ajoajat ja yhteenvedon sekä kirjoittaa CSV:n tarkistusta varten.
"""
import csv
import os
import resource
import sys
import time
from collections import Counter, defaultdict  # noqa: F401

from ..talot import mml, shore
from ..yhteiset import mml_files, ryhti
from ..yhteiset.julkaisu import fmt_kt
from ..yhteiset.tm35 import tm35_to_latlon


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
    blds = [b for b in ryhti.buildings(muni) if ryhti.keep(b)]
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
    W = shore.Water(water, shore.Land(parcels))
    # diagnostiikka: minkä kiinteistöjen palstat ovat lähes kokonaan vettä (tunnuksen 3. osa) -> vesialueiden tunnistus
    wt = shore.STRtree([g for g, *_ in water])
    wat = Counter()
    for p in parcels[:200000]:
        g = shore.parcel_geom(p["polys"])
        if g.area > 0:
            cov = sum(g.intersection(water[int(i)][0]).area for i in wt.query(g, predicate="intersects"))
            if cov / g.area > 0.8:
                wat[p["ref"][6:10]] += 1
    print("Palstat, jotka ovat yli 80 % vettä – tunnuksen 3. osa:", wat.most_common(8))
    T["indeksit"] = time.time() - t

    t = time.time()
    cache = {}

    def cls(p):
        if p["id"] not in cache:
            cache[p["id"]] = W.classify(shore.parcel_geom(p["polys"]), p["ref"])
        return cache[p["id"]]
    rows = []
    for b in blds:
        kt = b.get("property_identifier") or ""
        par = index.find(b["_x"], b["_y"], prefer_ref=kt)
        r = {"rakennustunnus": b.get("permanent_building_identifier"), "osoite": " / ".join(addr.get(b["building_key"], [])),
             "kiinteistotunnus": fmt_kt(kt), "tyyppi": ryhti.code(b.get("main_purpose")),
             "_key": b["building_key"]}
        if not par:
            r["tulos"] = "ei palstaa"
        else:
            c = cls(par)
            r.update(c)
            r["tulos"] = c["luokka"]
            if not c["luokka"].startswith("ranta"):
                # kiinteistön muu palsta (esim. erillinen rantapalsta tien toisella puolella)
                others = [cls(q) for q in by_ref.get(par["ref"], []) if q["id"] != par["id"]]
                if any(o["luokka"].startswith("ranta") for o in others):
                    r["tulos"] = "erillinen rantapalsta"
                    r["rantaviiva"] = max(o["rantaviiva"] for o in others if o["luokka"].startswith("ranta"))
        lat, lon = tm35_to_latlon(b["_x"], b["_y"])
        r["kartta"] = f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}"
        r["karttapaikka"] = (f"https://asiointi.maanmittauslaitos.fi/karttapaikka/?lang=fi&share=customMarker"
                             f"&n={round(b['_y'])}&e={round(b['_x'])}&title=&desc=&zoom=12")
        rows.append(r)
    T["laskenta"] = time.time() - t

    # PURO: maastotietokannan kapeat virtavedet (viivat) – luokat ja vaikutus
    t = time.time()
    streams = shore.fetch_water(client, (shore.STREAM_COLLECTION,), bbox)
    T["purot_lataus"] = time.time() - t
    kl = Counter(w[3].get("kohdeluokka") for w in streams)
    km = defaultdict(float)
    for w in streams:
        km[w[3].get("kohdeluokka")] += w[0].length / 1000
    print(f"\n== Purot: {len(streams)} viivaa; kohdeluokat {dict(kl)}; km {({k: round(v) for k, v in km.items()})}")
    print("  ominaisuuksia:", [w[3] for w in streams[:3]])
    t = time.time()
    prod = shore.compute(blds, parcels, water + streams)
    T["tuotantolaskenta_puroineen"] = time.time() - t
    print("  tuotantoluokat (ra) oletusasetuksilla:", sorted(Counter(v[0] for v in prod.values()).items()))
    # kapeiden (36311) mutkaisuus: suorat ojat vs. luonnontilaiset purot
    narrow = [w for w in streams if w[3].get("kohdeluokka") == shore.NARROW_CLASS]
    for lo in (0, 100, 300):
        sub = [w for w in narrow if w[0].length >= lo]
        sins = sorted(shore.sinuosity(w[0]) for w in sub)
        if sins:
            q = lambda f: round(sins[int(f * (len(sins) - 1))], 3)
            print(f"  36311 pituus >= {lo} m: {len(sub)} kpl, mutkaisuus p10 {q(.1)} p25 {q(.25)} mediaani {q(.5)} "
                  f"p75 {q(.75)} p90 {q(.9)}; osuus >= 1.05: {sum(s >= 1.05 for s in sins) / len(sins):.0%}, "
                  f">= 1.1: {sum(s >= 1.1 for s in sins) / len(sins):.0%}, >= 1.2: {sum(s >= 1.2 for s in sins) / len(sins):.0%}")
    keep = (shore.STREAM_CLASSES, shore.NARROW_MIN_SINUOSITY, shore.NARROW_MIN_LEN)
    variants = [("kaikki", None, None, 0), ("vain 2–5 m", {36312}, None, 0)] + [
        (f"2–5 m + alle 2 m mutkaisuus >= {s}, >= {ln} m", {36312}, s, ln)
        for s in (1.05, 1.1, 1.2) for ln in (50, 100, 200)]
    for name, cl, s_, ln in variants:
        shore.STREAM_CLASSES, shore.NARROW_MIN_SINUOSITY, shore.NARROW_MIN_LEN = cl, s_, ln
        km_ = sum(w[0].length for w in streams if shore.is_stream(w)) / 1000
        n = sum(1 for v in shore.compute(blds, parcels, water + streams).values() if v[0] == shore.STREAM)
        print(f"  VAIHTOEHTO {name}: puroa {km_:.0f} km, puron varrella {n}")
    shore.STREAM_CLASSES, shore.NARROW_MIN_SINUOSITY, shore.NARROW_MIN_LEN = keep
    # tarkistettavaksi: oletusasetuksilla puron varrella olevat ja ne, jotka pudotettiin (kaikki purot -> oletus)
    shore.STREAM_CLASSES = None
    allp = shore.compute(blds, parcels, water + streams)
    shore.STREAM_CLASSES = keep[0]
    prod = shore.compute(blds, parcels, water + streams)
    shore.NARROW_MIN_SINUOSITY = shore.NARROW_CANDIDATE
    cand = shore.compute(blds, parcels, water + streams)
    shore.NARROW_MIN_SINUOSITY = keep[1]
    for r in rows:
        k = r.pop("_key")
        v, vc, va = prod.get(k), cand.get(k), allp.get(k)
        if v and v[0] == shore.STREAM:
            r["tulos"], r["puro_m"] = "puro 2–5 m", v[1]
        elif vc and vc[0] == shore.STREAM:
            r["tulos"], r["puro_m"] = "kapea mutkainen puro (ehdolla)", vc[1]
        elif va and va[0] == shore.STREAM:
            r["tulos"], r["puro_m"] = "kapea suora – oja? (ei mukana)", va[1]
    by_type5 = Counter((r["tyyppi"], r["tulos"]) for r in rows if "puro" in r["tulos"] or "oja" in r["tulos"])
    print("  puron varrella tyypeittäin:", dict(by_type5))

    cnt = Counter(r["tulos"] for r in rows)
    by_type = Counter((r["tyyppi"], r["tulos"]) for r in rows)
    print("\n== Tulos (asuinrakennukset):", dict(cnt))
    print("  tyypeittäin (01 vapaa-ajan, 05 pientalo, 06 kerrostalo):", sorted(by_type.items()))
    print("  rannan lähin vesialue:", Counter(r.get("laji") for r in rows if r["tulos"].startswith("ranta")))
    print("  välin kiinteistöt (tunnuksen 3. osa):", W.gap_owners.most_common(10))
    CHECK = ("Vahaksentie 151", "Härkätie 710", "Himokorventie 81", "Heinisuontie 54", "Hirvikuja 5", "Karkauslammintie 17")
    for r in rows:
        if r["osoite"] in CHECK:
            print(f"  TARKISTUS {r['osoite']}: {r['tulos']}, etäisyys {r.get('etaisyys')} m, rantaviiva {r.get('rantaviiva')} m")
    print("  rantaviiva (m) rantatonteilla, mediaani:",
          sorted(r["rantaviiva"] for r in rows if r["tulos"] == "ranta")[cnt["ranta"] // 2] if cnt["ranta"] else "-")
    print("  pienen vesialueen (< 1 ha) rannat:", sum(1 for r in rows if r["tulos"] == "ranta" and (r.get("vesiala_ha") or 0) < 1))
    print("\n== Ajoajat (s):", {k: round(v, 1) for k, v in T.items()})
    print(f"   laskettuja palstoja {len(cache)}, {1000 * T['laskenta'] / max(1, len(cache)):.1f} ms/palsta")
    print(f"   muistin huippukäyttö {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} Mt")

    fields = ["tulos", "osoite", "kiinteistotunnus", "tyyppi", "rantaviiva", "puro_m", "etaisyys", "laji", "vesiala_ha",
              "rakennustunnus", "kartta", "karttapaikka"]
    path = os.path.join(out_dir, f"rantatesti_{muni}.csv")
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(rows, key=lambda r: (r["tulos"], r["osoite"])))
    print("CSV:", path)


if __name__ == "__main__":
    main()
