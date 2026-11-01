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
         "gross_floor_area": 120, "total_area": 189, "number_of_storeys": 2, "apartment_count": 1},
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

    g = build.density([(1050, 1050, 0, 0, {}), (1060, 1060, 0, 0, {}), (9000, 9000, 0, 0, {})], 1000)
    assert len(g) == 2 and sorted(f["properties"]["n"] for f in g) == [1, 2]
    assert all("tippecanoe" not in f for f in build.building_features(recs))
    print("selftest OK")


if __name__ == "__main__":
    run()
