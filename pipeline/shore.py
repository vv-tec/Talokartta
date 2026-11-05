"""Rantatieto: rajautuuko asuinrakennuksen tontti vesialueeseen.

IRROTETTAVA LISÄOSA: käytössä vain `config.SHORE_REGIONS`-maakunnissa. Tyhjä lista = pois päältä (build ei silloin
edes tuo tätä moduulia eikä Shapelya). Kokonaan poisto: tämä tiedosto, requirements-shore.txt ja web/app.js:n RANTA-osat.

Vaatii Shapely-kirjaston (vain tämä moduuli; muu ajo ei tarvitse sitä). Vesialueet Maanmittauslaitoksen
maastotietokannasta (OGC API Features), palstat kiinteistörekisterikartasta (mml_files).

Luokitus palstalle (etäisyys lähimpään vesialueeseen):
  "ranta"             etäisyys <= TOL_SHORE m (rajat eri mittauksista, joten pieni sallittu väli)
  "ranta (vesijättö)" etäisyys <= TOL_GAP m ja palstan ja veden välissä ei ole toisen kiinteistön maa-aluetta
                      (väli on vesialuekiinteistöä tai rekisteröimätöntä = tyypillisesti vesijättöä)
  "ei (toinen kiinteistö välissä)"  etäisyys <= TOL_GAP m, mutta välissä on toisen kiinteistön maapalsta
                      (naapuri, yhteinen ranta-alue, tie)
  "ei"                muuten
Jos rakennuksen palsta ei ole rannassa (eikä kiinteistöllä ole erillistä rantapalstaa), tarkistetaan puro:
  "puron varrella"    puro (maastotietokannan kapea virtavesi, viiva) kulkee palstalla tai sen rajalla (<= TOL_STREAM m)
                      vähintään MIN_STREAM_M metrin matkalla
"""
import datetime as dt
import gzip
import json
import os
import time
from collections import Counter

from shapely import get_parts, make_valid, shortest_line
from shapely.geometry import LineString, MultiPolygon, Polygon, box, shape
from shapely.ops import nearest_points
from shapely.strtree import STRtree

TOL_SHORE = 3.0
TOL_GAP = 20.0
WATER_TALO = {"0876"}  # kiinteistötunnuksen 3. osa: yhteinen vesialue (tarkistetaan koeajon diagnostiikasta)


def is_water_ref(ref):
    return len(ref or "") == 14 and ref[6:10] in WATER_TALO


MTK_BASE = "https://avoin-paikkatieto.maanmittauslaitos.fi/maastotiedot/features/v1"
CRS_3067 = "http://www.opengis.net/def/crs/EPSG/0/3067"


def parcel_geom(polys):
    g = MultiPolygon([Polygon(rs[0], rs[1:]) for rs in polys]) if len(polys) > 1 else Polygon(polys[0][0], polys[0][1:])
    return g if g.is_valid else make_valid(g)


def fetch_water(client, collections, bbox, log=print):
    """Vesialueet bboxin sisältä (EPSG:3067). Palauttaa listan (geom leikattuna bboxiin, laji, koko alueen ala m², ominaisuudet)."""
    x0, y0, x1, y1 = bbox
    clip = box(x0, y0, x1, y1)
    out = []
    for col in collections:
        url = f"{MTK_BASE}/collections/{col}/items"
        params = {"bbox": f"{x0},{y0},{x1},{y1}", "bbox-crs": CRS_3067, "crs": CRS_3067, "limit": "1000", "f": "json"}
        n, t0 = 0, time.time()
        while url:
            j = client._req("GET", url, params=params).json()
            for f in j.get("features", []):
                if not f.get("geometry"):
                    continue
                g = shape(f["geometry"])
                if not g.is_valid:
                    g = make_valid(g)
                area = g.area
                g = g.intersection(clip)
                if not g.is_empty:
                    out.append((g, col, area, f.get("properties") or {}))
                    n += 1
            url = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
            params = None
        log(f"  vesialueet {col}: {n} kohdetta, {time.time() - t0:.0f} s")
    return out


class Land:
    """Kaikki palstat (myös naapurit) välin omistajan tarkistukseen."""

    def __init__(self, parcels):
        self.refs = [p["ref"] for p in parcels]
        self.tree = STRtree([parcel_geom(p["polys"]) for p in parcels])

    def owners(self, pt):
        return {self.refs[int(i)] for i in self.tree.query(pt, predicate="within")}


class Water:
    def __init__(self, items, land=None):
        self.items = items
        self.land = land
        self.tree = STRtree([g for g, *_ in items])
        self.gap_owners = Counter()  # diagnostiikka: välin kiinteistöjen tunnuksen 3. osa

    def _gap_ok(self, geom, w, d, own_ref):
        """Onko palstan ja veden välissä toisen kiinteistön maata? Tarkistetaan muutamasta kohdasta rantaa."""
        if self.land is None:
            return True
        near = geom.boundary.intersection(w.intersection(box(*geom.buffer(d + 5).bounds)).buffer(d + 3))
        lines = [g for g in get_parts(near) if g.geom_type in ("LineString", "LinearRing") and g.length > 0]
        pts = []
        if lines:
            ln = max(lines, key=lambda g: g.length)  # pisin veden puoleinen rajan osa
            pts = [ln.interpolate(f, normalized=True) for f in (0.1, 0.3, 0.5, 0.7, 0.9)]
        if not pts:
            pts = [shortest_line(geom, w).interpolate(0, normalized=True)]
        ok = 0
        for p in pts:
            q = nearest_points(p, w)[1]
            line = LineString([p, q])
            bad = False
            for f in (0.35, 0.65):
                for ref in self.land.owners(line.interpolate(f, normalized=True)):
                    self.gap_owners[ref[6:10] if len(ref) == 14 else "?"] += 1
                    if ref != own_ref and not is_water_ref(ref):
                        bad = True
            ok += not bad
        return ok * 2 > len(pts)

    def classify(self, geom, own_ref=None):
        """Palauttaa dict: luokka, etäisyys (m), rantaviivaa (m), lähimmän vesialueen laji ja ala."""
        idx = self.tree.query(geom, predicate="dwithin", distance=TOL_GAP)
        if len(idx) == 0:
            near = self.tree.query_nearest(geom, max_distance=5000, return_distance=True)
            if len(near[0]) == 0:
                return {"luokka": "ei", "etaisyys": None, "rantaviiva": 0, "laji": "", "vesiala_ha": None}
            i, d = int(near[0][0]), float(near[1][0])
            return {"luokka": "ei", "etaisyys": round(d), "rantaviiva": 0, "laji": self.items[i][1],
                    "vesiala_ha": round(self.items[i][2] / 1e4, 1)}
        best, bd = None, None
        for i in idx:
            d = geom.distance(self.items[int(i)][0])
            if bd is None or d < bd:
                best, bd = int(i), d
        tol = TOL_SHORE if bd <= TOL_SHORE else bd + 3  # vesijätön kohdalla rantaviiva mitataan välin yli
        boundary, area_box = geom.boundary, box(*geom.buffer(tol + 1).bounds)
        shore = 0.0
        for i in idx:
            w = self.items[int(i)][0]
            if geom.distance(w) <= tol:
                local = w.intersection(area_box)  # iso järvi: vain palstan kohdalta, muuten puskurointi on raskasta
                if not local.is_empty:
                    shore += boundary.intersection(local.buffer(tol)).length
        if bd <= TOL_SHORE:
            luokka = "ranta"
        elif self._gap_ok(geom, self.items[best][0], bd, own_ref):
            luokka = "ranta (vesijättö)"
        else:
            luokka, shore = "ei (toinen kiinteistö välissä)", 0.0
        return {"luokka": luokka, "etaisyys": round(bd, 1), "rantaviiva": round(shore), "laji": self.items[best][1],
                "vesiala_ha": round(self.items[best][2] / 1e4, 1)}


class Streams:
    """Purot (viivat): kuinka pitkä matka puroa kulkee palstalla tai sen rajalla."""

    def __init__(self, items):
        self.items = items
        self.tree = STRtree([g for g, *_ in items])

    def length(self, geom):
        idx = self.tree.query(geom, predicate="dwithin", distance=TOL_STREAM)
        if len(idx) == 0:
            return 0.0
        zone = geom.buffer(TOL_STREAM)
        return sum(zone.intersection(self.items[int(i)][0]).length for i in idx)


# ---------- tuotantokäyttö (build.py) ----------

# PURO POIS KÄYTÖSTÄ 5.11.2026: omistajan pistokoe Tammelassa (18 kohdetta) – myös 2–5 m uomat olivat "suuria ojia"
# tai ojia, yksikään ei puro. Maastotietokanta ei erota puroa ojasta → luokkaa ei näytetä eikä uomia haeta.
# Koodi jätetty mahdollista myöhempää selvitystä varten (shore_explore.py käyttää sitä). Jos palautetaan (True),
# nosta myös VERSION 3:een, jotta kunnat lasketaan uudelleen yön kiintiössä.
STREAMS_ENABLED = False
VERSION = 2  # laskennan versio (2 = puron varrella mukana); vanhemmat kunnat päivitetään vähitellen (vain jos STREAMS_ENABLED)
STREAM_COLLECTION = "virtavesikapea"
# Maastotietokannan kapeat virtavedet: 36312 = 2–5 m leveä (puro / pieni joki) lasketaan aina. 36311 = alle 2 m sisältää
# myös metsä- ja peltoojat (Tammelassa 6 400 km, 806 taloa "puron varrella"), joten se on toistaiseksi pois. Ehdolla:
# vain mutkittelevat osuudet (NARROW_MIN_SINUOSITY 1.1, NARROW_MIN_LEN 100 → Tammelassa +334 taloa), odottaa omistajan
# pistokoetta. Jos asetusta muutetaan, nosta VERSION → kunnat lasketaan uudelleen yön kiintiössä.
STREAM_CLASSES = {36312}
NARROW_CLASS = 36311
NARROW_MIN_SINUOSITY = None  # pituus / päätepisteiden etäisyys; suora oja ~1,0 (None = kapeat eivät mukana)
NARROW_CANDIDATE = 1.1  # selvitysajon ehdokasasetus
NARROW_MIN_LEN = 100.0
TOL_STREAM = 5.0
MIN_STREAM_M = 10.0
WATER_COLLECTIONS = ("jarvi", "meri", "virtavesialue")
WATER_CODE = {"jarvi": "j", "meri": "m", "virtavesialue": "v"}
# tiilien `ra`: 0 ei, 1 ei – toinen kiinteistö välissä, 2 ranta, 3 ranta (vesijättö), 4 erillinen rantapalsta,
# 5 puron varrella (rl = puron pituus palstalla m; rd/rw/rwa kertovat silloinkin lähimmän vesialueen)
CLASS_CODE = {"ei": 0, "ei (toinen kiinteistö välissä)": 1, "ranta": 2, "ranta (vesijättö)": 3}
SEPARATE = 4
STREAM = 5
WATER_PAD_M = 2000


def municipality_water(client, buildings, log=print):
    """Kunnan rakennusten alueen (+2 km) vesialueet ja purot maastotietokannasta."""
    xs, ys = [b["_x"] for b in buildings], [b["_y"] for b in buildings]
    bbox = (min(xs) - WATER_PAD_M, min(ys) - WATER_PAD_M, max(xs) + WATER_PAD_M, max(ys) + WATER_PAD_M)
    cols = WATER_COLLECTIONS + ((STREAM_COLLECTION,) if STREAMS_ENABLED else ())
    return fetch_water(client, cols, bbox, log=lambda *a: None)


def sinuosity(g):
    """Viivan mutkaisuus: pituus jaettuna päätepisteiden etäisyydellä (osat yhteenlaskettuina)."""
    length = chord = 0.0
    for part in get_parts(g):
        if part.geom_type == "LineString" and len(part.coords) > 1:
            length += part.length
            (x0, y0), (x1, y1) = part.coords[0], part.coords[-1]
            chord += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
    return length / chord if chord > 0 else 1.0


def is_stream(item):
    g, col, _, props = item
    if col != STREAM_COLLECTION:
        return False
    k = props.get("kohdeluokka")
    if STREAM_CLASSES is None or k in STREAM_CLASSES:
        return True
    return (k == NARROW_CLASS and NARROW_MIN_SINUOSITY is not None and g.length >= NARROW_MIN_LEN
            and sinuosity(g) >= NARROW_MIN_SINUOSITY)


def compute(buildings, parcels, water_items):
    """Rakennuksille rantatulos {building_key: [ra, rantaviiva m, etäisyys m, vesilaji, vesialueen ala ha]}.
    water_items voi sisältää myös purot (STREAM_COLLECTION), ne erotellaan tässä."""
    from . import mml  # palstan haku pisteelle (sama logiikka kuin palstatuloksissa)
    if not buildings or not parcels:
        return {}
    index = mml.ParcelIndex(parcels)
    by_ref = {}
    for p in parcels:
        by_ref.setdefault(p["ref"], []).append(p)
    streams = [w for w in water_items if is_stream(w)]
    water_items = [w for w in water_items if w[1] != STREAM_COLLECTION]
    W = Water(water_items, Land(parcels)) if water_items else None
    S = Streams(streams) if streams and STREAMS_ENABLED else None
    cache, out = {}, {}
    none = {"luokka": "ei", "etaisyys": None, "rantaviiva": 0, "laji": "", "vesiala_ha": None}

    def cls(p):
        if p["id"] not in cache:
            cache[p["id"]] = W.classify(parcel_geom(p["polys"]), p["ref"]) if W else none
        return cache[p["id"]]
    for b in buildings:
        par = index.find(b["_x"], b["_y"], prefer_ref=b.get("property_identifier") or "")
        if not par:
            continue
        c = cls(par)
        ra, rl = CLASS_CODE[c["luokka"]], c["rantaviiva"]
        if ra < 2:  # kiinteistön toinen palsta rannassa (esim. tien toisella puolella)?
            others = [cls(q) for q in by_ref.get(par["ref"], []) if q["id"] != par["id"]]
            shore_others = [o for o in others if o["luokka"].startswith("ranta")]
            if shore_others:
                ra, rl = SEPARATE, max(o["rantaviiva"] for o in shore_others)
        if ra < 2 and S:
            ln = S.length(parcel_geom(par["polys"]))
            if ln >= MIN_STREAM_M:
                ra, rl = STREAM, round(ln)
        out[b["building_key"]] = [ra, rl, c["etaisyys"], WATER_CODE.get(c["laji"], ""), c["vesiala_ha"]]
    return out


class ShoreResults:
    """Rantatulokset kunnittain: {"munis": {kunta: {"date", "res": {building_key: [...]}}}}. Lasketaan aina, kun kunnan
    palstat ladataan (ParcelResults.on_parcels); uusi rakennus saa tuloksen kunnan seuraavassa palstahaussa."""

    def __init__(self, path, today=None, log=print):
        self.path, self.log = path, log
        self.today = today or dt.date.today()
        self.data = {"munis": {}}
        if os.path.exists(path):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                self.data = json.load(f)
            log(f"  rantatulokset tallessa: {len(self.data['munis'])} kuntaa")

    def has(self, m):
        return m in self.data["munis"]

    def version(self, m):
        return self.data["munis"].get(m, {}).get("v", 1)

    def date(self, m):
        return self.data["munis"].get(m, {}).get("date", "")

    def put(self, m, res):
        self.data["munis"][m] = {"date": self.today.isoformat(), "v": VERSION, "res": res}

    def collect(self, munis):
        out = {}
        for m in munis:
            out.update(self.data["munis"].get(m, {}).get("res", {}))
        return out

    def prune(self, munis):
        for m in set(self.data["munis"]) - set(munis):
            del self.data["munis"][m]

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(self.data, f, separators=(",", ":"))
        os.replace(tmp, self.path)
