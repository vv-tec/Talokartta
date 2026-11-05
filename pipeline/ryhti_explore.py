"""Selvitysajo: mitä tietoja Ryhtin avoimissa rakennusaineistoissa on.

Tulostaa kokoelmat, kunkin kokoelman kentät ja esimerkkiarvot sekä koodikenttien arvojakauman yhdestä kunnasta.
Käyttö: python -m pipeline.ryhti_explore 834
"""
import json
import sys
from collections import Counter, defaultdict

from .config import RYHTI_BASE
from .net import get


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


def main():
    muni = sys.argv[1] if len(sys.argv) > 1 else "834"
    if muni == "delta":
        return delta()
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
