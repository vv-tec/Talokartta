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
    recs = build.make_records(blds, addrs, mml.parcel_results(blds, parcels))
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
    ryhti_store_tests(parcels)
    shore_tests()
    print("selftest OK")


def shore_tests():
    """RANTA: luokitus yksinkertaisilla geometrioilla (ohitetaan, jos Shapely ei ole asennettu)."""
    try:
        from shapely.geometry import Polygon
    except ImportError:
        print("  (rantatestit ohitettu: Shapely puuttuu)")
        return
    from . import shore
    sq = lambda x0, y0, x1, y1: [[[(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]]]
    lake = Polygon([(0, 0), (100, 0), (100, 100), (0, 100)])
    from shapely.geometry import LineString
    water = [(lake, "jarvi", lake.area, {}),
             (LineString([(490, 525), (560, 525)]), shore.STREAM_COLLECTION, 0, {"kohdeluokka": 36311}),  # puro G:n läpi
             (LineString([(320, 300), (330, 300)]), shore.STREAM_COLLECTION, 0, {"kohdeluokka": 36311})]  # E:n rajalla, lyhyt
    parcels = [
        {"id": "A", "ref": "83400100010001", "polys": sq(100, 0, 150, 50)},     # rajautuu veteen
        {"id": "B", "ref": "83400100020001", "polys": sq(110, 60, 160, 100)},   # 10 m vesijättöä välissä
        {"id": "C", "ref": "83400100030001", "polys": sq(20, -60, 80, -10)},    # välissä naapurin kaistale D
        {"id": "D", "ref": "83400100040001", "polys": sq(0, -10, 100, 0)},
        {"id": "E", "ref": "83400100050001", "polys": sq(300, 300, 350, 350)},  # kaukana, mutta saman kiinteistön F rannassa
        {"id": "F", "ref": "83400100050001", "polys": sq(-50, 0, 0, 50)},
        {"id": "G", "ref": "83400100060001", "polys": sq(500, 500, 550, 550)},  # kaukana
    ]
    b = lambda k, x, y, ref: {"building_key": k, "_x": x, "_y": y, "property_identifier": ref}
    blds = [b("a", 120, 20, "83400100010001"), b("b", 130, 80, "83400100020001"), b("c", 50, -30, "83400100030001"),
            b("e", 320, 320, "83400100050001"), b("g", 520, 520, "83400100060001"), b("x", 9000, 9000, "")]
    res = shore.compute(blds, parcels, water)
    got = {k: v[0] for k, v in res.items()}
    assert got == {"a": 2, "b": 3, "c": 1, "e": 4, "g": 5}, got
    assert res["g"][1] == 60 and res["g"][3] == "j", res["g"]  # puroa 50 m palstalla + 2 × 5 m sallittu väli; lähin vesi järvi
    assert 50 <= res["a"][1] <= 60 and res["a"][3] == "j" and 50 <= res["e"][1] <= 60 and res["b"][2] == 10, res
    assert shore.compute(blds, parcels, [])["a"][0] == 0  # ei vesialueita alueella
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        st = shore.ShoreResults(os.path.join(d, "s.json.gz"), log=lambda *a: None)
        st.put("834", res); st.save()
        st = shore.ShoreResults(os.path.join(d, "s.json.gz"), log=lambda *a: None)
        assert st.has("834") and st.collect(["834"])["a"][0] == 2 and st.version("834") == shore.VERSION
        st.data["munis"]["834"].pop("v"); assert st.version("834") == 1  # vanha tallenne = versio 1
        st.prune([]); assert not st.has("834")


def ryhti_store_tests(parcels):
    """Rakennusten muutoshaku ja palstatulokset (verkkohaut korvattu testidatalla)."""
    import datetime as dt, os, tempfile
    from . import ryhti, ryhti_store
    U = "http://uri.suomi.fi/codelist/rytj/avoin_rakennusluokitus/code/"

    def b(key, muni, purpose="05", ts="2026-11-01T10:00:00Z", x=1050, **kw):
        return {"building_key": key, "municipality_number": muni, "main_purpose": U + purpose,
                "usage_status": ".../code/01", "modified_timestamp_utc": ts, "property_identifier": "83440400030064",
                "_x": x, "_y": 1050, "facade_material": ".../code/05", **kw}

    def a(key, bkey, muni, text, ts="2026-11-01T10:00:00Z"):
        return {"address_key": key, "building_key": bkey, "municipality_number": muni, "address_fin": text,
                "postal_code": "31300", "postal_office_fin": "TAMMELA", "modified_timestamp_utc": ts}
    src = {"b": {"834": [b("b1", "834"), b("b2", "834", purpose="03")], "235": [b("b3", "235")]},
           "a": {"834": [a("a1", "b1", "834", "Tie 1"), a("a2", "b2", "834", "Liiteri")], "235": [a("a3", "b3", "235", "Katu 3")]},
           "cb": [], "ca": [], "da": [], "for": []}
    calls = []
    orig = {k: getattr(ryhti, k) for k in ("buildings", "addresses", "changed_buildings", "changed_addresses",
                                            "deleted_addresses", "addresses_for")}
    ryhti.buildings = lambda m: calls.append(("full", m)) or [dict(x) for x in src["b"][m]]
    ryhti.addresses = lambda m: [dict(x) for x in src["a"][m]]
    ryhti.changed_buildings = lambda since: calls.append(("delta", since)) or src["cb"]
    ryhti.changed_addresses = lambda since: src["ca"]
    ryhti.deleted_addresses = lambda since: src["da"]
    ryhti.addresses_for = lambda keys: [x for x in src["for"] if x["building_key"] in keys]
    try:
        with tempfile.TemporaryDirectory() as d:
            path, day = os.path.join(d, "r.json.gz"), dt.date(2026, 11, 3)
            mk = lambda t: ryhti_store.RyhtiStore(path, 30, keep=build.keep, today=t, log=lambda *x: None)
            st = mk(day); st.update(["834", "235"]); st.save()
            assert calls == [("full", "834"), ("full", "235")] or calls == [("full", "235"), ("full", "834")], calls
            assert sorted(x["building_key"] for x in st.buildings()) == ["b1", "b3"]  # talousrakennus pois
            assert st.buildings("834")[0]["main_purpose"] == "05" and st.buildings("834")[0]["facade_material"] == "05"
            assert [x["address_fin"] for x in st.addresses()] == ["Tie 1", "Katu 3"]
            assert st.data["mark"] == "2026-11-01T10:00:00Z"
            # seuraava yö: vain muutokset, päivän päällekkäisyydellä
            calls.clear()
            src["cb"] = [b("b1", "834", ts="2026-11-02T08:00:00Z", x=1060),         # muuttunut
                         b("b4", "834", ts="2026-11-02T09:00:00Z"),                 # uusi
                         b("b3", "235", purpose="02", ts="2026-11-02T09:30:00Z"),   # ei enää asuinrakennus
                         b("b9", "091", ts="2026-11-02T11:00:00Z")]                 # muu kunta
            src["ca"] = [a("a1", "b1", "834", "Tie 1 A", ts="2026-11-02T08:00:00Z")]
            src["for"] = [a("a4", "b4", "834", "Uusi tie 4")]
            st = mk(day + dt.timedelta(days=1)); st.update(["834", "235"])
            assert calls == [("delta", "2026-10-31T10:00:00Z")], calls
            assert {x["building_key"]: x["_x"] for x in st.buildings()} == {"b1": 1060, "b4": 1050}
            assert sorted(x["address_fin"] for x in st.addresses()) == ["Tie 1 A", "Uusi tie 4"]
            assert st.data["mark"] == "2026-11-02T11:00:00Z" and st.stats["removed_b"] == 1
            src["da"] = [{"address_key": "a4"}]
            st.changes("2026-11-02T00:00:00Z", {"834"})
            assert [x["address_fin"] for x in st.addresses()] == ["Tie 1 A"]
            # kuukauden päästä: täysi haku 1/30 kunnista (vähintään yksi), vanhin ensin; muut muutoshaulla
            calls.clear()
            st = mk(day + dt.timedelta(days=31)); st.update(["834", "235"])
            assert [c[0] for c in calls] == ["full", "delta"], calls
            # kunta poistettu asetuksista
            st.update(["834"]); assert all(x["municipality_number"] == "834" for x in st.buildings())
            # täysi haku vertaa tallessa olleeseen tietoon (muutoshaun luotettavuus)
            src["b"]["834"] = [b("b1", "834", x=1070)]
            st.full("834"); assert st.stats["drift"]["834"] == {"uusia": 0, "poistuneita": 1, "muuttuneita": 1}, st.stats
            # aikaraja: uusi kunta jää kesken, valmiit kunnat saavat silti muutoshaun
            calls.clear()
            st.update(["834", "235"], deadline=1)
            assert st.missing == ["235"] and not st.ready("235") and st.ready("834") and calls[-1][0] == "delta", calls

            # palstatulokset kunnittain: tallessa vain [pa, ka, pn]
            fetched = []
            pr_path = os.path.join(d, "p.json.gz")
            bm = {"834": [{"building_key": "b1", "_x": 1050, "_y": 1050, "property_identifier": "83440400030064"},
                          {"building_key": "bx", "_x": 9000, "_y": 9000}]}
            fetch = lambda m: fetched.append(m) or [dict(p) for p in parcels]
            pr = mml.ParcelResults(pr_path, 7, fetch, today=day, log=lambda *x: None)
            res = pr.get(["834"], bm); pr.save()
            assert res == {"b1": [9900, 12400, 2]} and fetched == ["834"], res
            pr = mml.ParcelResults(pr_path, 7, fetch, today=day + dt.timedelta(days=2), log=lambda *x: None)
            assert pr.get(["834"], bm) == res and fetched == ["834"]          # tallesta
            boom = lambda m: (_ for _ in ()).throw(RuntimeError("katko"))
            pr = mml.ParcelResults(pr_path, 7, boom, today=day + dt.timedelta(days=9), log=lambda *x: None)
            assert pr.get(["834", "235"], bm) == res and pr.missing == ["235"]  # virhe: vanha tulos säilyy
            # päivitettävät kunnat (esim. rantalaskennan uusi versio) vain yön kiintiön vapaisiin paikkoihin
            fetched.clear(); bm3 = {**bm, "235": []}
            pr = mml.ParcelResults(pr_path, 7, fetch, today=day + dt.timedelta(days=3), log=lambda *x: None)
            pr.get(["834", "235"], bm3, upgrade=["834"]); assert fetched == ["235"], fetched  # kiintiö (1) puuttuvalle
            pr.get(["834", "235"], bm3, upgrade=["834"]); assert fetched == ["235", "834"], fetched  # nyt tilaa
            # uusi rakennus: palstatieto heti pienellä aluehaulla, ei koko kunnan latausta
            boxes = []
            fb = lambda *bb: boxes.append(bb) or [dict(p) for p in parcels]
            pr = mml.ParcelResults(pr_path, 14, boom, today=day + dt.timedelta(days=3), log=lambda *x: None)
            bm2 = {"834": bm["834"] + [{"building_key": "bn", "_x": 2010, "_y": 2010, "property_identifier": "83440400030064"},
                                       {"building_key": "bn2", "_x": 2040, "_y": 2040, "property_identifier": "83440400030064"}]}
            assert pr.fill_new(["834"], bm2, fb) == 2 and len(boxes) == 2    # lähekkäiset bn+bn2 yhdellä haulla, bx omalla
            assert pr.collect(["834"])["bn"] == [2500, 12400, 2], pr.collect(["834"])
            assert pr.data["munis"]["834"]["tried"] == {"bx": (day + dt.timedelta(days=3)).isoformat()}  # ei palstaa
            boxes.clear(); assert pr.fill_new(["834"], bm2, fb) == 0 and boxes == []  # ei uusintayritystä heti
            pr.today = day + dt.timedelta(days=11); pr.fill_new(["834"], bm2, fb); assert len(boxes) == 1  # viikon päästä uudelleen
            # vanhan rajavälimuistin muunnos tuloksiksi
            old = mml.ParcelCache(os.path.join(d, "parcels-mml.json.gz"), 7, lambda k: [dict(p) for p in parcels],
                                  today=day, log=lambda *x: None)
            old.get(["834"]); old.save()
            pr = mml.ParcelResults(os.path.join(d, "p2.json.gz"), 7, boom, today=day, log=lambda *x: None)
            build.migrate_parcel_cache(d, pr, bm)
            assert pr.get(["834"], bm) == res and not os.path.exists(os.path.join(d, "parcels-mml.json.gz"))
        # turvatarkistus ennen julkaisua
        from . import config
        prev = {"regions": [{"name": "Kanta-Häme", "count": 1000}, {"name": "Uusimaa", "count": 5000}],
                "muni_counts": {"834": 1000, "091": 5000}}
        assert build.publish_problems(None, [], {}, {}) == []
        assert build.publish_problems(prev, ["Kanta-Häme", "Uusimaa"], {"834": 990, "091": 4800}, {}) == []
        p = build.publish_problems(prev, ["Kanta-Häme"], {"834": 900}, {})
        assert len(p) == 2 and "Uusimaa" in p[0] and "834" in p[1], p     # maakunta putoaisi + kunnan pudotus 10 %
        assert build.publish_problems({"regions": prev["regions"]}, ["Kanta-Häme", "Uusimaa"], {},
                                      {"Kanta-Häme": 1000, "Uusimaa": 4000})[0].startswith("Maakunta Uusimaa")
        assert config.DROP_MIN >= 20  # pienet kunnat: muutaman rakennuksen vaihtelu ei estä julkaisua
        assert build.publish_problems({"regions": [], "muni_counts": {"235": 100}}, [], {"235": 85}, {}) == []
    finally:
        for k, v in orig.items():
            setattr(ryhti, k, v)


if __name__ == "__main__":
    run()
