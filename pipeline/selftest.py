"""Nopeat tarkistukset ilman verkkoyhteyttä: python -m pipeline.selftest"""
from . import build, mml
from .tm35 import tm35_to_latlon

GML = """<?xml version="1.0" encoding="UTF-8"?>
<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:gml="http://www.opengis.net/gml/3.2"
 xmlns:cp="http://inspire.ec.europa.eu/schemas/cp/4.0" xmlns:base="http://inspire.ec.europa.eu/schemas/base/3.3"
 numberMatched="2" numberReturned="2">
 <wfs:member><cp:CadastralParcel gml:id="A">
  <cp:geometry><gml:Polygon srsName="EPSG:3067"><gml:exterior><gml:LinearRing>
   <gml:posList>1000 1000 1100 1000 1100 1100 1000 1100 1000 1000</gml:posList>
  </gml:LinearRing></gml:exterior><gml:interior><gml:LinearRing>
   <gml:posList>1010 1010 1020 1010 1020 1020 1010 1020 1010 1010</gml:posList>
  </gml:LinearRing></gml:interior></gml:Polygon></cp:geometry>
  <cp:inspireId><base:Identifier><base:localId>1</base:localId></base:Identifier></cp:inspireId>
  <cp:nationalCadastralReference>83440400030064</cp:nationalCadastralReference>
 </cp:CadastralParcel></wfs:member>
 <wfs:member><cp:CadastralParcel gml:id="B">
  <cp:geometry><gml:MultiSurface><gml:surfaceMember><gml:Polygon><gml:exterior><gml:LinearRing>
   <gml:posList>2000 2000 2050 2000 2050 2050 2000 2050 2000 2000</gml:posList>
  </gml:LinearRing></gml:exterior></gml:Polygon></gml:surfaceMember></gml:MultiSurface></cp:geometry>
  <cp:inspireId><base:Identifier><base:localId>2</base:localId></base:Identifier></cp:inspireId>
  <cp:nationalCadastralReference>83440400030064</cp:nationalCadastralReference>
 </cp:CadastralParcel></wfs:member>
</wfs:FeatureCollection>"""


def run():
    lat, lon = tm35_to_latlon(332010, 6748150)
    assert abs(lat - 60.83305349) < 1e-4 and abs(lon - 23.90942712) < 1e-4, (lat, lon)

    n, parcels = mml.parse_parcels(GML)
    assert n == 2 and len(parcels) == 2
    assert abs(mml.parcel_area(parcels[0]) - (10000 - 100)) < 1e-6
    assert abs(mml.parcel_area(parcels[1]) - 2500) < 1e-6
    idx = mml.ParcelIndex(parcels)
    assert idx.find(1050, 1050)["id"] == "1"
    assert idx.find(1015, 1015) is None  # reiän sisällä
    assert idx.find(5000, 5000) is None

    blds = [
        {"_x": 1050, "_y": 1050, "building_key": "k1", "permanent_building_identifier": "100721088B",
         "property_identifier": "83440400030064", "completion_date": "2004-07-05Z",
         "main_purpose": "http://uri.suomi.fi/codelist/rytj/avoin_rakennusluokitus/code/05",
         "usage_status": "http://uri.suomi.fi/codelist/vtj/rake_kaytossaolotilanne/code/01",
         "gross_floor_area": 120, "total_area": 189, "number_of_storeys": 2, "apartment_count": 1,
         "material_of_load_bearing_structures": "http://uri.suomi.fi/codelist/rytj/kantavanrakenteenrakennusaine/code/04",
         "facade_material": "http://uri.suomi.fi/codelist/rytj/julkisivunrakennusaine/code/00",
         "heating_energy_source": "http://uri.suomi.fi/codelist/rytj/lammitysenergianlahde/code/1101",
         "construction_method": ".../code/02", "volume": 450, "floor_area": 0, "is_protected": False},
        {"_x": 9000, "_y": 9000, "building_key": "k2", "permanent_building_identifier": "X",
         "property_identifier": "", "completion_date": None,
         "main_purpose": ".../code/01", "usage_status": ".../code/03"},
    ]
    assert build.keep(blds[0]) and build.keep(blds[1])
    assert not build.keep({**blds[0], "usage_status": ".../code/07"})
    assert not build.keep({**blds[0], "main_purpose": ".../code/04"})
    addrs = [{"building_key": "k1", "address_fin": "Testitie 1", "postal_code": "31300", "postal_office_fin": "TAMMELA"},
             {"building_key": "k1", "address_fin": "Testitie 1", "postal_code": "31300", "postal_office_fin": "TAMMELA"}]
    recs = build.make_records(blds, addrs, parcels)
    p0, p1 = recs[0][4], recs[1][4]
    assert p0["k"] == "834-404-3-64" and p0["a"] == "Testitie 1" and p0["po"] == "Tammela", p0
    assert p0["y"] == 2004 and p0["d"] == "2004-07-05" and p0["p"] == "05" and p0["s"] == "01"
    assert p0["pa"] == 9900 and p0["ka"] == 12400 and p0["pn"] == 2 and p0["c"] == 1, p0
    assert "y" not in p1 and "pa" not in p1 and "k" not in p1, p1
    assert p0["m"] == "04" and "fa" not in p0 and p0["e"] == "1101" and p0["r"] == "02" and "h" not in p0, p0
    assert p0["v"] == 450 and "ha" not in p0 and p0["sj"] == 0 and "sj" not in p1, p0
    mt = build.meta(recs, [])
    assert mt["by"]["m"] == {"04": 1, "": 1} and mt["by"]["e"]["1101"] == 1, mt["by"]

    g = build.density([(1050, 1050, 0, 0, {}), (1060, 1060, 0, 0, {}), (9000, 9000, 0, 0, {})], 1000)
    assert len(g) == 2 and sorted(f["properties"]["n"] for f in g) == [1, 2]
    assert all("tippecanoe" not in f for f in build.building_features(recs))
    # palstojen välimuisti: toinen ajo ei hae uudelleen, vanhentunut hakee
    import datetime as dt, tempfile, os
    calls = []
    fetch = lambda key: calls.append(key) or [dict(p) for p in parcels]
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "parcels.json.gz")
        day = dt.date(2026, 11, 1)
        c = mml.ParcelCache(path, 7, fetch, today=day, log=lambda *a: None)
        got = c.get(["0,0", "1,0"]); c.save()
        assert len(calls) == 2 and len(got) == 2  # sama palsta kahdessa erässä tallennetaan kerran
        assert sorted(round(mml.parcel_area(p)) for p in got) == [2500, 9900]
        c = mml.ParcelCache(path, 7, fetch, today=day + dt.timedelta(days=3), log=lambda *a: None)
        assert len(c.get(["0,0"])) == 2 and len(calls) == 2  # välimuistista
        c.get(["0,0", "235"]); assert len(calls) == 3        # vain puuttuva erä haetaan
        c = mml.ParcelCache(path, 7, fetch, today=day + dt.timedelta(days=8), log=lambda *a: None)
        c.get(["0,0"]); assert len(calls) == 4               # vanhentunut -> haetaan uudelleen
        c.save()
        # vanha välimuistimuoto ({"fetched", "tiles"}) luetaan edelleen
        import gzip, json
        with gzip.open(path, "wt") as f:
            json.dump({"fetched": "2026-11-01", "tiles": {str(i): [] for i in range(14)}, "parcels": {}}, f)
        calls.clear()
        c = mml.ParcelCache(path, 7, fetch, today=day + dt.timedelta(days=10), log=lambda *a: None)
        c.get(str(i) for i in range(14)); c.save()
        assert len(calls) == 2 and not c.missing             # 14 vanhentunutta / 7 pv -> 2 erää per ajo
        c = mml.ParcelCache(path, 7, fetch, today=day + dt.timedelta(days=11), log=lambda *a: None)
        c.get(str(i) for i in range(14))
        assert len(calls) == 4 and not ({"0", "1"} & set(calls[2:]))  # vanhimmat ensin, juuri haettuja ei uudelleen
        # epäonnistunut haku ja aikaraja: muut erät säilyvät, puuttuvat jäävät seuraavaan ajoon
        def flaky(key):
            if key == "b":
                raise RuntimeError("palvelu ei vastaa")
            return [dict(p, id=p["id"] + key) for p in parcels]
        c = mml.ParcelCache(os.path.join(d, "x.json.gz"), 7, flaky, today=day, log=lambda *a: None)
        assert len(c.get(["a", "b", "c"])) == 4 and c.missing == ["b"]
        c.save(); s1 = c.stamp()
        c = mml.ParcelCache(os.path.join(d, "x.json.gz"), 7, flaky, today=day, log=lambda *a: None)
        assert c.get(["a", "b", "d"], deadline=1) and c.missing == ["b", "d"]
        c.save(); assert c.stamp() == s1                     # ei muutoksia -> sama tunniste
        assert mml.tiles_for_bbox(0, 0, 4000, 2000) == {(0, 0), (1, 0)}
    assert build.slug("Kanta-Häme") == "kanta-hame" and build.slug("Etelä-Pohjanmaa") == "etela-pohjanmaa"
    # GeoPackage-geometria: GP-otsake (ei kehystä) + WKB-polygon, pikkupäinen
    import struct
    from . import mml_files
    ring = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    wkb = b"\x01" + struct.pack("<I", 3) + struct.pack("<I", 1) + struct.pack("<I", 5) + b"".join(struct.pack("<dd", *p) for p in ring)
    blob = b"GP\x00\x01" + struct.pack("<i", 3067) + wkb
    polys = mml_files.gpkg_polys(blob)
    assert polys == [[ring]] and mml.parcel_area({"polys": polys}) == 100
    multi = b"\x01" + struct.pack("<I", 6) + struct.pack("<I", 2) + wkb + wkb
    assert len(mml_files.gpkg_polys(b"GP\x00\x01" + struct.pack("<i", 3067) + multi)) == 2
    import sqlite3
    with tempfile.TemporaryDirectory() as d:
        gp = os.path.join(d, "t.gpkg")
        con = sqlite3.connect(gp)
        con.execute('CREATE TABLE "PalstanSijaintitiedot" (fid INTEGER, geom BLOB, kiinteistotunnus TEXT)')
        con.execute('INSERT INTO "PalstanSijaintitiedot" VALUES (1, ?, ?)', (blob, "23500100010001"))
        con.execute('INSERT INTO "PalstanSijaintitiedot" VALUES (2, ?, NULL)', (blob,))
        con.commit(); con.close()
        ps = mml_files.read_parcels(gp)
        assert len(ps) == 1 and ps[0]["ref"] == "23500100010001" and mml.parcel_area(ps[0]) == 100
    print("selftest OK")


if __name__ == "__main__":
    run()
