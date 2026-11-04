"""Rantalaskenta (KOE): rajautuuko kiinteistön palsta vesialueeseen.

Vaatii Shapely-kirjaston (vain tämä moduuli; muu ajo ei tarvitse sitä). Vesialueet Maanmittauslaitoksen
maastotietokannasta (OGC API Features), palstat kiinteistörekisterikartasta (mml_files).

Luokitus palstalle (etäisyys lähimpään vesialueeseen):
  "ranta"             etäisyys <= TOL_SHORE m (rajat eri mittauksista, joten pieni sallittu väli)
  "ranta (vesijättö)" etäisyys <= TOL_GAP m ja palstan ja veden välissä ei ole toisen kiinteistön maa-aluetta
                      (väli on vesialuekiinteistöä tai rekisteröimätöntä = tyypillisesti vesijättöä)
  "ei (toinen kiinteistö välissä)"  etäisyys <= TOL_GAP m, mutta välissä on toisen kiinteistön maapalsta
                      (naapuri, yhteinen ranta-alue, tie)
  "ei"                muuten
"""
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
