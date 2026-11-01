"""Kiinteistöpalstat Maanmittauslaitoksen INSPIRE-latauspalvelusta (WFS) sekä geometrialaskenta."""
import math
import xml.etree.ElementTree as ET

from .config import MML_CP_WFS, PARCEL_PAGE, PARCEL_TILE_M
from .net import get

NS = {
    "wfs": "http://www.opengis.net/wfs/2.0",
    "gml": "http://www.opengis.net/gml/3.2",
    "cp": "http://inspire.ec.europa.eu/schemas/cp/4.0",
    "base": "http://inspire.ec.europa.eu/schemas/base/3.3",
}
G = "{%s}" % NS["gml"]


def _ring(el):
    """Rengas: kaikki posList/pos-koordinaatit elementin sisältä (myös kaarirenkaista)."""
    pts = []
    for pl in el.iter():
        if pl.tag in (G + "posList", G + "pos") and pl.text:
            v = [float(t) for t in pl.text.split()]
            pts.extend(zip(v[0::2], v[1::2]))
    return pts


def parse_parcels(xml_text):
    """Palauttaa (featureCount, [ {id, ref, rings:[[(x,y)...], ...] (ensimmäinen ulkorengas)} ])."""
    root = ET.fromstring(xml_text)
    out = []
    for cpel in root.iter("{%s}CadastralParcel" % NS["cp"]):
        lid = cpel.findtext("cp:inspireId/base:Identifier/base:localId", namespaces=NS)
        ref = cpel.findtext("cp:nationalCadastralReference", namespaces=NS)
        geom = cpel.find("cp:geometry", NS)
        polys = []
        if geom is not None:
            for poly in [e for e in geom.iter() if e.tag in (G + "Polygon", G + "PolygonPatch")]:
                rings = []
                ext = poly.find("gml:exterior", NS)
                if ext is not None:
                    rings.append(_ring(ext))
                for inner in poly.findall("gml:interior", NS):
                    rings.append(_ring(inner))
                if rings and len(rings[0]) >= 3:
                    polys.append(rings)
        if lid and ref and polys:
            out.append({"id": lid, "ref": ref, "polys": polys})
    n = sum(1 for _ in root.iter("{%s}member" % NS["wfs"]))
    return n, out


def ring_area(r):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(r, r[1:] + r[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def parcel_area(p):
    return sum(ring_area(rs[0]) - sum(ring_area(h) for h in rs[1:]) for rs in p["polys"])


def _in_ring(x, y, r):
    inside = False
    j = len(r) - 1
    for i in range(len(r)):
        xi, yi = r[i]
        xj, yj = r[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def contains(p, x, y):
    for rs in p["polys"]:
        if _in_ring(x, y, rs[0]) and not any(_in_ring(x, y, h) for h in rs[1:]):
            return True
    return False


def bbox(p):
    xs = [x for rs in p["polys"] for x, _ in rs[0]]
    ys = [y for rs in p["polys"] for _, y in rs[0]]
    return min(xs), min(ys), max(xs), max(ys)


def _fetch_box(x0, y0, x1, y1, depth=0):
    q = {
        "service": "WFS", "version": "2.0.0", "request": "GetFeature",
        "typeNames": "cp:CadastralParcel", "count": str(PARCEL_PAGE),
        "bbox": f"{x0},{y0},{x1},{y1},urn:ogc:def:crs:EPSG::3067",
    }
    n, parcels = parse_parcels(get(MML_CP_WFS, q).text)
    if n >= PARCEL_PAGE and depth < 6:  # ruutu täynnä -> jaetaan neljään osaan
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        res = []
        for a, b, c, d in ((x0, y0, mx, my), (mx, y0, x1, my), (x0, my, mx, y1), (mx, my, x1, y1)):
            res.extend(_fetch_box(a, b, c, d, depth + 1))
        return res
    return parcels


def parcels_in_bbox(x0, y0, x1, y1, log=print):
    """Kaikki palstat, jotka leikkaavat aluetta. Haetaan ruuduittain ja poistetaan päällekkäiset."""
    t = PARCEL_TILE_M
    xs = range(int(math.floor(x0 / t)), int(math.ceil(x1 / t)))
    ys = range(int(math.floor(y0 / t)), int(math.ceil(y1 / t)))
    total = len(xs) * len(ys)
    seen = {}
    for k, (i, j) in enumerate((i, j) for i in xs for j in ys):
        for p in _fetch_box(i * t, j * t, (i + 1) * t, (j + 1) * t):
            seen[p["id"]] = p
        if (k + 1) % 50 == 0 or k + 1 == total:
            log(f"  palstaruudut {k + 1}/{total}, palstoja {len(seen)}")
    return list(seen.values())


class ParcelIndex:
    """Yksinkertainen ruutuindeksi: mikä palsta sisältää pisteen."""

    def __init__(self, parcels, cell=500):
        self.cell = cell
        self.grid = {}
        for p in parcels:
            p["area"] = parcel_area(p)
            bx0, by0, bx1, by1 = bbox(p)
            for i in range(int(bx0 // cell), int(bx1 // cell) + 1):
                for j in range(int(by0 // cell), int(by1 // cell) + 1):
                    self.grid.setdefault((i, j), []).append(p)

    def find(self, x, y, prefer_ref=None):
        cands = [p for p in self.grid.get((int(x // self.cell), int(y // self.cell)), []) if contains(p, x, y)]
        if not cands:
            return None
        if prefer_ref:
            for p in cands:
                if p["ref"] == prefer_ref:
                    return p
        return min(cands, key=lambda p: p["area"])
