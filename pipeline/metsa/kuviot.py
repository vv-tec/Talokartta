"""Metsäkeskuksen metsävarakuviot (uusi tietomalli 1.9.2026, GPKG kunnittain): kuviot, kasvupaikka, puusto ja
puulajiosuudet kuviokohtaisesti. Lisäksi palstojen ja kuvioiden geometriat Shapely-muotoon (to_shape)."""
import collections
import sqlite3

import shapely
from shapely.geometry import MultiPolygon, Polygon

from ..yhteiset.julkaisu import log
from ..yhteiset.mml_files import gpkg_polys


def species_group(code, label):
    lab = (label or "").lower()
    if "lehtikuusi" in lab:
        return "manty"
    if "kuusi" in lab or code == "2":
        return "kuusi"
    if "koivu" in lab or code in ("3", "4"):
        return "koivu"
    if any(w in lab for w in ("mänty", "havu", "kataja", "pihta", "douglas", "marjakuusi")) or code in ("1", "8", "30"):
        return "manty"
    return "lehti"


def to_shape(polys):
    ps = []
    for p in polys:
        if len(p[0]) >= 3:
            ps.append(Polygon(p[0], [h for h in p[1:] if len(h) >= 3]))
    if not ps:
        return None
    g = ps[0] if len(ps) == 1 else MultiPolygon(ps)
    return g if g.is_valid else shapely.make_valid(g)


def codes(con):
    out = collections.defaultdict(dict)
    for t, f, v, lab in con.execute("SELECT table_name, field_name, codevalue, codelabel_fin FROM codeschema_mapping"):
        out[(t, f)][v] = lab
    return out


def num(v):
    return None if v is None or v < 0 else v


def read_stands(gp, verbose=True):
    """Kuviot: {standid: dict(geom, ha, kasvupaikka..., luvut m³/ha, puulajiosuudet)}; koodien selitteet."""
    con = sqlite3.connect(gp)
    C = codes(con)
    for key in [] if not verbose else [("treestand", "treestandclass"), ("growthplacedata", "maingroup"), ("growthplacedata", "subgroup"),
                ("growthplacedata", "fertilityclass"), ("growthplacedata", "drainagestate"), ("growthplacedata", "soiltype"),
                ("treestand", "developmentclass"), ("treestratum", "treespecies"), ("treestratum", "storey"),
                ("treestand", "treestanddatasource"), ("restriction", "cuttingrestriction")]:
        log(f"  koodisto {key}: {C.get(key)}")
    cls = C.get(("treestand", "treestandclass"), {})
    cur = next((c for c, l in cls.items() if "nykyhet" in l.lower() or "ajantas" in l.lower()), "2")
    inv = next((c for c, l in cls.items() if "inventoi" in l.lower()), "1")
    if verbose:
        log(f"  puustotiedon luokka: nykyhetki = {cur} ({cls.get(cur)}), inventointi = {inv} ({cls.get(inv)})")
    sp_lab = C.get(("treestratum", "treespecies"), {}) or C.get(("treestand", "maintreespecies"), {})

    stands = {}
    for sid, blob, area in con.execute("SELECT standid, geometry, area FROM stand"):
        g = to_shape(gpkg_polys(blob)) if blob else None
        if g is not None and not g.is_empty:
            stands[sid] = {"geom": g, "ha": area}
    for sid, mg, sg, fc, st, dr, gd in con.execute(
            "SELECT standid, maingroup, subgroup, fertilityclass, soiltype, drainagestate, growthplacedate FROM growthplacedata"):
        if sid in stands:
            stands[sid].update(mg=mg, sg=sg, fc=fc, st=st, dr=dr, gd=gd)
    ts_cur = {}
    for tsid, sid, dc, ms, dd in con.execute(
            "SELECT treestandid, standid, developmentclass, maintreespecies, treedatadate FROM treestand WHERE treestandclass=?",
            (cur,)):
        if sid in stands:
            ts_cur[tsid] = sid
            stands[sid].update(dc=dc, ms=ms, calc=dd)
    for sid, dd in con.execute("SELECT standid, MAX(treedatadate) FROM treestand WHERE treestandclass=? GROUP BY standid", (inv,)):
        if sid in stands:
            stands[sid]["inv"] = dd
    for tsid, age, vol, saw, pulp in con.execute(
            "SELECT treestandid, age, volume, sawlogvolume, pulpwoodvolume FROM treestandsummary"):
        sid = ts_cur.get(tsid)
        if sid is not None:
            stands[sid].update(age=num(age), vol=num(vol) or 0, saw=num(saw) or 0, pulp=num(pulp) or 0)
    for sid, cr in con.execute("SELECT standid, cuttingrestriction FROM restriction WHERE cuttingrestriction IS NOT NULL"):
        if sid in stands:
            stands[sid]["restr"] = cr
    strata = collections.defaultdict(list)
    for tsid, sp, vol, saw, pulp in con.execute(
            "SELECT treestandid, treespecies, volume, sawlogvolume, pulpwoodvolume FROM treestratum"):
        sid = ts_cur.get(tsid)
        if sid is not None:
            strata[sid].append((species_group(sp, sp_lab.get(sp)), num(vol) or 0, num(saw), num(pulp)))
    con.close()

    # puulajiryhmittäiset osuudet: tukki ja kuitu ositteista, skaalattuna yhteenvedon kokonaismääriin
    paths = collections.Counter()
    for sid, s in stands.items():
        if "vol" not in s:
            paths["ei puustotietoa"] += 1
            continue
        rows = strata.get(sid, [])
        share = {}
        for kind, col in (("vol", 1), ("saw", 2), ("pulp", 3)):
            tot = collections.Counter()
            for r in rows:
                v = r[col] if r[col] is not None else 0
                tot[r[0]] += v
            if sum(tot.values()) <= 0 and rows:  # ositteilla ei tukki/kuitu-jakoa → tilavuuden mukaan
                for r in rows:
                    tot[r[0]] += r[1]
            if sum(tot.values()) <= 0:
                tot = collections.Counter({species_group(s.get("ms"), sp_lab.get(s.get("ms"))) if s.get("ms") else "manty": 1})
            share[kind] = {g: v / sum(tot.values()) for g, v in tot.items()}
        s["share"] = share
        paths["ositteista" if rows and any(r[2] is not None for r in rows) else ("ositteiden tilavuudesta" if rows else "pääpuulajista")] += 1
    if verbose:
        log(f"  kuvioita {len(stands)}; puulajijako: {dict(paths)}")
    return stands, C
