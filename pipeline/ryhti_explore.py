"""Selvitysajo: mitä tietoja Ryhtin avoimissa rakennusaineistoissa on.

Tulostaa kokoelmat, kunkin kokoelman kentät ja esimerkkiarvot sekä koodikenttien arvojakauman yhdestä kunnasta.
Käyttö: python -m pipeline.ryhti_explore 834
"""
import json
import sys
from collections import Counter, defaultdict

from .config import RYHTI_BASE
from .net import get


def main():
    muni = sys.argv[1] if len(sys.argv) > 1 else "834"
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
