"""Selvitysajo: mitä tietoja Ryhtin avoimissa rakennusaineistoissa on.

Tulostaa kokoelmat, kunkin kokoelman kentät ja esimerkkiarvot sekä koodikenttien arvojakauman yhdestä kunnasta.
Käyttö: python -m pipeline.selvitykset.ryhti_explore 834
(tai "maakunnat": vertaa config.REGIONS Tilastokeskuksen kunta–maakunta-luokitukseen)
"""
import json
import sys
from collections import Counter, defaultdict

from ..config import RYHTI_BASE
from ..yhteiset.net import get


def delta():
    """Testaa muutoshakua: toimiiko aikaleimasuodatus ja millaisia määriä palautuu."""
    tests = [
        ("open_building", "modified_timestamp_utc > '2026-11-01T00:00:00Z'"),
        ("open_building", "modified_timestamp_utc AFTER 2026-11-01T00:00:00Z"),
        ("open_building", "modified_timestamp_utc > '2026-10-01T00:00:00Z'"),
        ("open_building", "modified_timestamp_utc > '2026-11-01T00:00:00Z' AND municipality_number IN ('091','834','853')"),
        ("open_address", "modified_timestamp_utc > '2026-11-01T00:00:00Z'"),
        ("open_address", "modified_timestamp_utc > '2026-10-01T00:00:00Z'"),
        ("open_address_deleted", "modified_timestamp_utc > '2026-10-01T00:00:00Z'"),
    ]
    for col, flt in tests:
        try:
            j = get(f"{RYHTI_BASE}/{col}/items", {"f": "application/json", "limit": "1000", "filter-lang": "cql-text",
                                                   "filter": flt}, tries=2).json()
            fs = j.get("features", [])
            ts = sorted(f["properties"].get("modified_timestamp_utc") or "" for f in fs)
            munis = Counter(f["properties"].get("municipality_number") for f in fs)
            nxt = any(l.get("rel") == "next" for l in j.get("links", []))
            print(f"{col} | {flt}\n  numberMatched={j.get('numberMatched')} sivulla={len(fs)} seuraava={nxt} "
                  f"aikaleimat {ts[:1]}…{ts[-1:]} kunnat {munis.most_common(5)}")
        except Exception as e:  # noqa: BLE001
            print(f"{col} | {flt}\n  VIRHE {str(e)[:300]}")
    j = get(f"{RYHTI_BASE}/open_building/items", {"f": "application/json", "limit": "2", "filter-lang": "cql-text",
            "filter": "municipality_number='834'", "properties": "building_key,modified_timestamp_utc,volume"}).json()
    print("properties-parametri:", [f["properties"] for f in j["features"]])


def missing(muni):
    """Kunta, jolta open_building palauttaa 0 rakennusta: onko tiedot toisella kuntanumerolla tai toisessa kokoelmassa?"""
    tests = [
        ("open_building", f"municipality_number='{muni}'"),
        ("open_building", f"property_identifier LIKE '{muni}%'"),
        ("open_address", f"municipality_number='{muni}'"),
        ("avoimet_rakennukset", f"kuntanumero='{muni}'"),
        ("avoimet_rakennukset", f"sijaintikiinteisto LIKE '{muni}%'"),
    ]
    for col, flt in tests:
        try:
            j = get(f"{RYHTI_BASE}/{col}/items", {"f": "application/json", "limit": "1000", "filter-lang": "cql-text",
                                                   "filter": flt}, tries=2).json()
            fs = j.get("features", [])
            munis = Counter(f["properties"].get("municipality_number") or f["properties"].get("kuntanumero") for f in fs)
            purp = Counter(f["properties"].get("main_purpose") or f["properties"].get("paaasiallinen_kayttotarkoitus")
                           for f in fs)
            print(f"{col} | {flt}\n  numberMatched={j.get('numberMatched')} sivulla={len(fs)} kunnat {munis.most_common(5)} "
                  f"käyttötarkoitus {purp.most_common(4)}")
        except Exception as e:  # noqa: BLE001
            print(f"{col} | {flt}\n  VIRHE {str(e)[:300]}")


def regions_check():
    """Vertaa config.REGIONS-kuntalistoja Tilastokeskuksen viralliseen kunta–maakunta-luokitukseen."""
    from ..config import REGIONS
    data, used = None, None
    for year in ("2026", "2025"):
        url = (f"https://data.stat.fi/api/classifications/v2/correspondenceTables/"
               f"kunta_1_{year}0101%23maakunta_1_{year}0101/maps")
        try:
            data = get(url, {"content": "data", "format": "json", "lang": "fi"}).json()
            used = year
            break
        except Exception as e:  # noqa: BLE001
            print(f"luokitus {year}: VIRHE {str(e)[:200]}")
    if not data:
        print("::error::Tilastokeskuksen luokitusta ei saatu")
        return 1
    def nm(item):
        names = item.get("classificationItemNames") or []
        return names[0].get("name") if names else "?"
    official = defaultdict(dict)  # maakunta -> {kuntanumero: nimi}
    names = {}
    for row in data:
        src, tgt = row["sourceItem"], row["targetItem"]
        official[nm(tgt)][src["code"]] = nm(src)
        names[src["code"]] = nm(src)
    print(f"Tilastokeskus {used}: {len(names)} kuntaa, {len(official)} maakuntaa")
    bad = 0
    for region, codes in REGIONS.items():
        off = official.get(region)
        if off is None:
            print(f"{region}: EI LÖYDY luokituksesta"); bad += 1; continue
        extra = [c for c in codes if c not in off]
        miss = [c for c in off if c not in codes]
        status = "OK" if not extra and not miss else "EROJA"
        bad += status != "OK"
        print(f"{region}: {status} ({len(codes)} meillä / {len(off)} virallisesti)")
        for c in extra:
            print(f"  ylimääräinen {c} {names.get(c, '(ei kuntaa tällä numerolla)')}")
        for c in miss:
            print(f"  puuttuu {c} {off[c]}")
    todo = [r for r in sorted(official) if r not in REGIONS]
    for r in todo:
        print(f"lisäämättä: {r}: " + ", ".join(f"{c} {n}" for c, n in sorted(official[r].items())))
    print("Kaikki lisätyt maakunnat vastaavat luokitusta." if not bad else f"::error::{bad} maakunnassa eroja")
    return 0


def main():
    muni = sys.argv[1] if len(sys.argv) > 1 else "834"
    if muni == "delta":
        return delta()
    if muni == "maakunnat":
        return regions_check()
    if muni.startswith("puuttuu:"):
        return missing(muni.split(":", 1)[1])
    cols = get(RYHTI_BASE, {"f": "application/json"}).json()
    names = [c["id"] for c in cols.get("collections", [])]
    print("Kokoelmat:", names)
    for c in cols.get("collections", []):
        print(" ", c["id"], "–", c.get("title"), "|", (c.get("description") or "")[:200])
    for name in names:
        try:
            j = get(f"{RYHTI_BASE}/{name}/items", {"f": "application/json", "limit": "500", "filter-lang": "cql-text",
                                                    "filter": f"municipality_number='{muni}'"}).json()
        except Exception as e:  # noqa: BLE001
            print(f"\n== {name}: kuntasuodatus ei onnistunut ({e}); ilman suodatusta")
            j = get(f"{RYHTI_BASE}/{name}/items", {"f": "application/json", "limit": "200"}).json()
        feats = j.get("features", [])
        print(f"\n== {name}: {len(feats)} kohdetta näytteessä")
        vals = defaultdict(Counter)
        for f in feats:
            for k, v in (f.get("properties") or {}).items():
                vals[k][json.dumps(v, ensure_ascii=False)[:90]] += 1
        for k, cnt in vals.items():
            filled = sum(n for v, n in cnt.items() if v not in ("null", '""', "[]"))
            print(f"  {k}: täytetty {filled}/{len(feats)}; yleisimmät {cnt.most_common(4)}")


if __name__ == "__main__":
    main()
