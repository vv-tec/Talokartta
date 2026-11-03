"""Kiinteistöpalstat Maanmittauslaitoksen INSPIRE-latauspalvelusta (WFS) sekä geometrialaskenta."""
import datetime as dt
import gzip
import json
import math
import os
import time
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
    """Palauttaa (osumien määrä (numberMatched, jos tiedossa), [ {id, ref, rings:[[(x,y)...], ...] (ensimmäinen ulkorengas)} ])."""
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
    matched = root.get("numberMatched", "")
    return (max(n, int(matched)) if matched.isdigit() else n), out


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


def tiles_for_bbox(x0, y0, x1, y1):
    """Hakuruudut (indeksit), jotka peittävät alueen."""
    t = PARCEL_TILE_M
    return {(i, j) for i in range(int(math.floor(x0 / t)), int(math.ceil(x1 / t)))
            for j in range(int(math.floor(y0 / t)), int(math.ceil(y1 / t)))}


def wfs_tile_fetch(key):
    """Välimuistin hakufunktio WFS:lle: avain 'i,j' = PARCEL_TILE_M-kokoinen ruutu."""
    i, j = (int(v) for v in key.split(","))
    t = PARCEL_TILE_M
    return _fetch_box(i * t, j * t, (i + 1) * t, (j + 1) * t)


class ParcelCache:
    """Palstat erinä (WFS-ruutu tai kunta) levylle tallennettuna, jotta niitä ei haeta joka yö uudelleen.

    Rakenne: {"stamp", "keys": {erä: [palsta-id, ...]}, "dates": {erä: "YYYY-MM-DD"}, "parcels": {id: {"ref", "polys"}}}
    fetch(erä) palauttaa listan palstoja {"id", "ref", "polys"}. Sama palsta voi tulla useasta erästä (kuntien
    rajoilla), id:n perusteella se tallennetaan kerran.

    Puuttuvat erät haetaan heti. Vanhentuneet (yli max_age_days) haetaan uudelleen vanhimmasta alkaen, mutta yhdellä
    ajolla enintään 1/max_age_days-osa eristä, jolloin uudelleenhaku jakautuu tasaisesti viikon öille.
    Haku keskeytetään hallitusti, kun deadline (time.time()-arvo) ylittyy; jo haetut erät säilyvät (save()).
    """

    def __init__(self, path, max_age_days, fetch, today=None, log=print, label="erä"):
        self.path, self.log, self.fetch, self.label = path, log, fetch, label
        self.max_age = max_age_days
        self.today = today or dt.date.today()
        self.data = {"stamp": "none", "keys": {}, "dates": {}, "parcels": {}}
        if os.path.exists(path):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                old = json.load(f)
            old.setdefault("keys", old.pop("tiles", {}))  # vanha muoto
            fetched = old.pop("fetched", self.today.isoformat())
            old.setdefault("dates", {k: fetched for k in old["keys"]})
            old.setdefault("stamp", f"{fetched}-{len(old['keys'])}")
            self.data = old
            dates = sorted(old["dates"].values()) or ["-"]
            log(f"  palstat välimuistista: {len(old['keys'])} {label}a, haettu {dates[0]} … {dates[-1]}")
        self.changed = False
        self.missing = []

    def age(self, k):
        return (self.today - dt.date.fromisoformat(self.data["dates"][k])).days

    def get(self, keys, deadline=None):
        keys = sorted({str(k) for k in keys})
        missing = [k for k in keys if k not in self.data["keys"]]
        stale = sorted((k for k in keys if k in self.data["keys"] and self.age(k) >= self.max_age),
                       key=lambda k: self.data["dates"][k])
        budget = math.ceil(len(keys) / self.max_age)
        todo = missing + stale[:budget]
        if todo:
            self.log(f"  haetaan {len(missing)} puuttuvaa ja {len(todo) - len(missing)} vanhentunutta {self.label}a "
                     f"(vanhentuneita yhteensä {len(stale)}, välimuistissa {len(keys) - len(missing)})")
        for n, k in enumerate(todo, 1):
            if deadline and time.time() > deadline:
                self.log(f"  aikaraja täynnä: {len(todo) - n + 1} {self.label}a jää seuraavaan ajoon")
                break
            try:
                fetched = list(self.fetch(k))
            except Exception as e:  # noqa: BLE001 – yksi epäonnistunut erä ei kaada koko ajoa
                self.log(f"  {self.label} {k}: haku epäonnistui: {e}")
                continue
            ids = []
            for p in fetched:
                polys = [[[(round(x, 2), round(y, 2)) for x, y in r] for r in rs] for rs in p["polys"]]
                self.data["parcels"][p["id"]] = {"ref": p["ref"], "polys": polys}
                ids.append(p["id"])
            self.data["keys"][k] = ids
            self.data["dates"][k] = self.today.isoformat()
            self.changed = True
            if n % 100 == 0 or n == len(todo) or self.label == "kunta":
                self.log(f"  {self.label} {n}/{len(todo)} ({k}): {len(ids)} palstaa, yhteensä {len(self.data['parcels'])}")
        self.missing = [k for k in keys if k not in self.data["keys"]]
        ids = {pid for k in keys if k in self.data["keys"] for pid in self.data["keys"][k]}
        return [{"id": pid, "ref": self.data["parcels"][pid]["ref"],
                 "polys": [[[tuple(c) for c in r] for r in rs] for rs in self.data["parcels"][pid]["polys"]]}
                for pid in ids]

    def stamp(self):
        """Tunniste välimuistin versiolle (muuttuu aina, kun palstoja haetaan)."""
        return self.data["stamp"]

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        if self.changed or not os.path.exists(self.path):
            # uudelleen haetun erän vanhat palstat, joihin mikään erä ei enää viittaa, poistetaan
            used = {pid for ids in self.data["keys"].values() for pid in ids}
            self.data["parcels"] = {pid: v for pid, v in self.data["parcels"].items() if pid in used}
            self.data["stamp"] = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S") + f"-{len(self.data['keys'])}"
            with gzip.open(self.path, "wt", encoding="utf-8") as f:
                json.dump(self.data, f, separators=(",", ":"))
        with open(os.path.join(os.path.dirname(self.path) or ".", "parcels.stamp"), "w") as f:
            f.write(self.stamp())


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


def parcel_results(buildings, parcels):
    """Rakennuksille palstan ala (pa), kiinteistön ala (ka) ja palstojen määrä (pn): {building_key: [pa, ka, pn]}.

    Palsta on se, jonka sisällä rakennuksen piste on (saman kiinteistön palstaa suositaan). Kiinteistön ala on
    rakennuksen kiinteistötunnuksen kaikkien palstojen summa; jos tunnusta ei löydy, käytetään osuman palstan kiinteistöä.
    """
    ref_area, ref_n = {}, {}
    for p in parcels:
        p.setdefault("area", parcel_area(p))
        ref_area[p["ref"]] = ref_area.get(p["ref"], 0.0) + p["area"]
        ref_n[p["ref"]] = ref_n.get(p["ref"], 0) + 1
    index = ParcelIndex(parcels) if parcels else None
    out = {}
    for b in buildings:
        kt = b.get("property_identifier") or ""
        par = index.find(b["_x"], b["_y"], prefer_ref=kt) if index else None
        ref = kt if kt in ref_area else (par["ref"] if par else None)
        if par or ref:
            out[b["building_key"]] = [round(par["area"]) if par else None,
                                      round(ref_area[ref]) if ref else None, ref_n[ref] if ref else None]
    return out


class ParcelResults:
    """Palstoista tallessa vain rakennuskohtaiset tulokset kunnittain, ei rajoja: {kunta: {"date", "res": {building_key: [pa, ka, pn]}}}.

    Kunnan tiedosto haetaan, kun kunta puuttuu tai sen tulokset ovat yli max_age_days vanhoja (vanhimmasta alkaen,
    enintään 1/max_age_days kunnista per ajo). Rakennus, joka on tullut rekisteriin kunnan edellisen haun jälkeen,
    saa palstatietonsa kunnan seuraavassa haussa (viimeistään viikon päästä).
    """

    def __init__(self, path, max_age_days, fetch, today=None, log=print):
        self.path, self.max_age, self.fetch, self.log = path, max_age_days, fetch, log
        self.today = today or dt.date.today()
        self.data = {"munis": {}}
        if os.path.exists(path):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                self.data = json.load(f)
            dates = sorted(v["date"] for v in self.data["munis"].values()) or ["-"]
            log(f"  palstatulokset tallessa: {len(self.data['munis'])} kuntaa, haettu {dates[0]} … {dates[-1]}")
        self.missing = []

    def put(self, m, buildings, parcels, date=None):
        self.data["munis"][m] = {"date": date or self.today.isoformat(), "res": parcel_results(buildings, parcels)}

    def get(self, munis, buildings_by_muni, deadline=None):
        munis = sorted({str(m) for m in munis})
        d = self.data["munis"]
        missing = [m for m in munis if m not in d]
        stale = sorted((m for m in munis if m in d and
                        (self.today - dt.date.fromisoformat(d[m]["date"])).days >= self.max_age), key=lambda m: d[m]["date"])
        todo = missing + stale[:math.ceil(len(munis) / self.max_age)]
        if todo:
            self.log(f"  palstat: haetaan {len(missing)} puuttuvaa ja {len(todo) - len(missing)} vanhentunutta kuntaa "
                     f"(vanhentuneita yhteensä {len(stale)})")
        for n, m in enumerate(todo, 1):
            if deadline and time.time() > deadline:
                self.log(f"  aikaraja täynnä: {len(todo) - n + 1} kuntaa jää seuraavaan ajoon")
                break
            try:
                parcels = list(self.fetch(m))
            except Exception as e:  # noqa: BLE001 – yksi epäonnistunut kunta ei kaada koko ajoa
                self.log(f"  kunta {m}: palstojen haku epäonnistui: {e}")
                continue
            self.put(m, buildings_by_muni.get(m, []), parcels)
            self.log(f"  kunta {n}/{len(todo)} ({m}): {len(parcels)} palstaa, tulos {len(d[m]['res'])} rakennukselle")
        self.missing = [m for m in munis if m not in d]
        out = {}
        for m in munis:
            if m in d:
                out.update(d[m]["res"])
        return out

    def ready(self, m):
        return m in self.data["munis"]

    def prune(self, munis):
        """Poistaa asetuksista poistettujen kuntien tulokset."""
        for m in set(self.data["munis"]) - {str(x) for x in munis}:
            del self.data["munis"][m]

    def save(self):
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(self.data, f, separators=(",", ":"))
        os.replace(tmp, self.path)
