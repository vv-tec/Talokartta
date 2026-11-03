"""Rantalaskenta (KOE): rajautuuko kiinteistön palsta vesialueeseen.

Vaatii Shapely-kirjaston (vain tämä moduuli; muu ajo ei tarvitse sitä). Vesialueet Maanmittauslaitoksen
maastotietokannasta (OGC API Features), palstat kiinteistörekisterikartasta (mml_files).

Luokitus palstalle (etäisyys lähimpään vesialueeseen):
  "ranta"            etäisyys <= TOL_SHORE m  (rajat eri mittauksista, joten pieni sallittu väli)
  "todennäköisesti"  etäisyys <= TOL_LIKELY m
  "ei"               muuten
"""
import time

from shapely import make_valid
from shapely.geometry import MultiPolygon, Polygon, box, shape
from shapely.strtree import STRtree

TOL_SHORE = 3.0
TOL_LIKELY = 15.0
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


class Water:
    def __init__(self, items):
        self.items = items
        self.tree = STRtree([g for g, *_ in items])

    def classify(self, geom):
        """Palauttaa dict: luokka, etäisyys (m), rantaviivaa (m, palstan rajaa enintään TOL_SHORE m päässä vedestä),
        lähimmän vesialueen laji ja ala."""
        idx = self.tree.query(geom, predicate="dwithin", distance=TOL_LIKELY)
        if len(idx) == 0:
            near = self.tree.query_nearest(geom, max_distance=5000, return_distance=True)
            if len(near[0]) == 0:
                return {"luokka": "ei", "etaisyys": None, "rantaviiva": 0, "laji": "", "vesiala_ha": None}
            i, d = int(near[0][0]), float(near[1][0])
            return {"luokka": "ei", "etaisyys": round(d), "rantaviiva": 0, "laji": self.items[i][1],
                    "vesiala_ha": round(self.items[i][2] / 1e4, 1)}
        best, bd, shore = None, None, 0.0
        boundary = geom.boundary
        area_box = box(*geom.buffer(TOL_SHORE + 1).bounds)
        for i in idx:
            w = self.items[int(i)][0]
            d = geom.distance(w)
            if bd is None or d < bd:
                best, bd = int(i), d
            if d <= TOL_SHORE:
                local = w.intersection(area_box)  # iso järvi: vain palstan kohdalta, muuten puskurointi on raskasta
                if not local.is_empty:
                    shore += boundary.intersection(local.buffer(TOL_SHORE)).length
        luokka = "ranta" if bd <= TOL_SHORE else "todennäköisesti"
        return {"luokka": luokka, "etaisyys": round(bd, 1), "rantaviiva": round(shore), "laji": self.items[best][1],
                "vesiala_ha": round(self.items[best][2] / 1e4, 1)}
