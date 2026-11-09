"""Selvitysajo: Ryhtin koodistojen arvot ja selitteet (koodistot.suomi.fi) sekä vertailu tekstimuotoiseen aineistoon."""
import json
from collections import Counter, defaultdict

from ..config import RYHTI_BASE
from ..yhteiset.net import get

SCHEMES = [("rytj", "kantavanrakenteenrakennusaine"), ("rytj", "julkisivunrakennusaine"), ("rytj", "lammitystapa"),
           ("rytj", "lammitysenergianlahde"), ("vtj", "Rake_runkotapa"), ("vtj", "rake_kaytossaolotilanne"),
           ("rytj", "avoin_rakennusluokitus")]
FIELDS = {"material_of_load_bearing_structures": "kantavien_rakenteiden_rakennusaine", "facade_material": "julkisivumateriaali",
          "heating_method": "lammitystapa", "heating_energy_source": "lammitysenergian_lahde", "construction_method": "rakentamistapa"}


def main():
    for reg, sch in SCHEMES:
        print(f"\n== {reg}/{sch}")
        for url in (f"https://koodistot.suomi.fi/codelist-api/api/v1/coderegistries/{reg}/codeschemes/{sch}/codes/?format=json",
                    f"http://uri.suomi.fi/codelist/{reg}/{sch}?format=json"):
            try:
                j = get(url, tries=2).json()
                for c in j.get("results", []):
                    print(f"  {c.get('codeValue')}: {(c.get('prefLabel') or {}).get('fi')}")
                break
            except Exception as e:  # noqa: BLE001
                print("  ei onnistunut:", url, str(e)[:150])
    # vertailu: samat rakennukset koodina (open_building) ja tekstinä (avoimet_rakennukset)
    q = {"f": "application/json", "limit": "3000", "filter-lang": "cql-text"}
    ob = get(f"{RYHTI_BASE}/open_building/items", {**q, "filter": "municipality_number='091'"}).json()["features"]
    try:
        tx = get(f"{RYHTI_BASE}/avoimet_rakennukset/items", {**q, "filter": "kuntanumero='091'"}).json()["features"]
    except Exception as e:  # noqa: BLE001
        print("tekstiaineisto ei onnistunut:", e)
        return
    txt = {f["properties"]["pysyva_rakennustunnus"]: f["properties"] for f in tx}
    pairs = defaultdict(Counter)
    for f in ob:
        p = f["properties"]
        t = txt.get(p.get("permanent_building_identifier"))
        if not t:
            continue
        for a, b in FIELDS.items():
            if p.get(a):
                pairs[a][(p[a].rsplit("/", 1)[-1], t.get(b))] += 1
    print(f"\nVertailu: {len(ob)} / {len(tx)} rakennusta")
    for a, c in pairs.items():
        print(a)
        for (code, label), n in sorted(c.items()):
            print(f"  {code} -> {label}: {n}")


if __name__ == "__main__":
    main()
