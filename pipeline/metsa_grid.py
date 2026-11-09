"""METSAKARTTA – metsäruudut: kaukaa näytettävä yleiskuva puuston määrästä (m³ metsämaan hehtaaria kohden).

Omistajan päätös 9.11.2026: zoomeilla, joilla yksittäiset tilat eivät vielä näy, kartalla on ruudut (5 km ja 1 km),
väri = puuston määrä m³/ha metsämaata. Lasketaan metsätilojen tuloksista julkaisun yhteydessä (ei uusia hakuja):
tilan puusto (m³) ja metsämaa (ha) jaetaan ruuduille sen mukaan, kuinka suuri osa tilan pinta-alasta on kussakin
ruudussa (tila oletetaan tasaisen puustoiseksi). Ruutu näytetään vain, jos metsätilojen metsämaata on vähintään
MIN_SHARE ruudun alasta (muuten tieto olisi harhaanjohtava, esim. valtion maat puuttuvat Metsäkeskuksen aineistosta).
Ei Shapelya: palstat leikataan ruutuihin itse (Sutherland–Hodgman), jotta laskenta on nopea ja testattavissa.
"""
import collections

import numpy as np

from .tm35 import latlon_to_tm35_np, tm35_to_latlon

MIN_SHARE = 0.05


def ring_area(xs, ys):
    """Monikulmion ala (m²), kenkänauhakaava."""
    n = len(xs)
    if n < 3:
        return 0.0
    s = 0.0
    for k in range(n):
        s += xs[k - 1] * ys[k] - xs[k] * ys[k - 1]
    return abs(s) / 2


def clip_box(pts, x0, y0, x1, y1):
    """Rengas (lista (x, y)) leikattuna suorakulmioon (Sutherland–Hodgman; ala säilyy oikein)."""
    def cut(points, inside, cross):
        out = []
        if not points:
            return out
        prev = points[-1]
        for cur in points:
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
            prev = cur
        return out

    def at_x(x):
        return lambda p, q: (x, p[1] + (q[1] - p[1]) * (x - p[0]) / (q[0] - p[0]))

    def at_y(y):
        return lambda p, q: (p[0] + (q[0] - p[0]) * (y - p[1]) / (q[1] - p[1]), y)

    pts = cut(pts, lambda p: p[0] >= x0, at_x(x0))
    pts = cut(pts, lambda p: p[0] <= x1, at_x(x1))
    pts = cut(pts, lambda p: p[1] >= y0, at_y(y0))
    pts = cut(pts, lambda p: p[1] <= y1, at_y(y1))
    return pts


class ForestGrid:
    """Kerää tilat ruutuihin. sizes: ruutukoot metreinä, pienin ensin (suuremmat ovat sen monikertoja)."""

    def __init__(self, sizes=(1000, 5000), min_share=MIN_SHARE):
        self.sizes = tuple(sizes)
        self.min_share = min_share
        self.v = collections.defaultdict(float)    # (koko, i, j) -> m³
        self.mm = collections.defaultdict(float)   # (koko, i, j) -> metsämaata ha
        self.n = collections.Counter()             # (koko, i, j) -> tiloja (kokonaan tai osittain ruudussa)

    def pieces(self, g):
        """Tilan ala ruuduittain (pienin ruutukoko): {(i, j): m²}. g = GeoJSON MultiPolygon -koordinaatit (lon, lat)."""
        size = self.sizes[0]
        out = collections.defaultdict(float)
        for poly in g:
            rings = []
            for ring in poly:
                a = np.asarray(ring, dtype=float)
                if len(a) < 3:
                    continue
                x, y = latlon_to_tm35_np(a[:, 1], a[:, 0])
                rings.append((x, y))
            if not rings:
                continue
            ex = rings[0]
            i0, i1 = int(ex[0].min() // size), int(ex[0].max() // size)
            j0, j1 = int(ex[1].min() // size), int(ex[1].max() // size)
            if i0 == i1 and j0 == j1:   # palsta kokonaan yhdessä ruudussa (tavallisin)
                out[(i0, j0)] += max(0.0, ring_area(*rings[0]) - sum(ring_area(*r) for r in rings[1:]))
                continue
            lists = [list(zip(x.tolist(), y.tolist())) for x, y in rings]
            for i in range(i0, i1 + 1):
                for j in range(j0, j1 + 1):
                    box = (i * size, j * size, (i + 1) * size, (j + 1) * size)
                    areas = []
                    for pts in lists:
                        c = clip_box(pts, *box)
                        areas.append(ring_area([p[0] for p in c], [p[1] for p in c]) if len(c) >= 3 else 0.0)
                    a = areas[0] - sum(areas[1:])
                    if a > 0:
                        out[(i, j)] += a
        return {c: a for c, a in out.items() if a >= 1.0}   # alle 1 m²:n reunasirut (pyöristys) pois

    def add(self, g, v, mm):
        """Lisää tila: g raja (lon, lat), v puuston määrä m³, mm metsämaata ha."""
        if not g or not mm or mm <= 0:
            return
        parts = self.pieces(g)
        total = sum(parts.values())
        if total <= 0:
            return
        base = self.sizes[0]
        for size in self.sizes:
            k = size // base
            cells = collections.defaultdict(float)
            for (i, j), a in parts.items():
                cells[(i // k, j // k)] += a / total
            for (i, j), w in cells.items():
                key = (size, i, j)
                self.v[key] += (v or 0) * w
                self.mm[key] += mm * w
                self.n[key] += 1

    def features(self, size):
        """GeoJSON-ruudut (lon, lat) yhdelle ruutukoolle: vh m³/ha metsämaata, mm ha, n tiloja, s km, c tunniste."""
        need = self.min_share * size * size / 1e4
        for (s, i, j), mm in sorted(self.mm.items()):
            if s != size or mm < need:
                continue
            corners = [(i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1), (i, j)]
            ring = []
            for ci, cj in corners:
                lat, lon = tm35_to_latlon(ci * size, cj * size)
                ring.append([round(lon, 5), round(lat, 5)])
            yield {"type": "Feature",
                   "properties": {"vh": round(self.v[(s, i, j)] / mm), "mm": round(mm), "n": self.n[(s, i, j)],
                                  "s": size // 1000, "c": i * 10000 + j},
                   "geometry": {"type": "Polygon", "coordinates": [ring]}}
