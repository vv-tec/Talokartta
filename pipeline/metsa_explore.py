"""Selvitysajo: metsätilat (tiekartan kohta 6, Tammela-koe). Ei vaikuta julkaistuun sivuun.

Vaihe "rakenne": tulostaa aineistojen rakenteen, jotta laskenta voidaan kirjoittaa oikeisiin sarakkeisiin:
  - Metsäkeskuksen metsävarakuviot (uusi tietomalli 1.9.2026 alkaen, https://avoin.metsakeskus.fi/aineistot/MV/Kunta/)
    ja tietomallin kuvaus (Excel)
  - Luken kantohinnat (Teollisuuspuun kauppa hinta-alueittain kuukausittain, 0100_teokau)
  - MML:n kiinteistörekisterikartan kaikki taulut ja tilakohtaiset alat (kiinteistö = sen kaikki palstat yhteensä)

Käyttö: MML_API_KEY=... python -m pipeline.metsa_explore 834 rakenne
"""
import collections
import io
import os
import re
import sqlite3
import sys
import time
import zipfile

from . import net
from .mml_files import MMLFiles, PARCEL_PROCESS, gpkg_polys

MV_BASE = "https://avoin.metsakeskus.fi/aineistot/MV/Kunta/"
MV_MODEL_XLSX = ("https://www.metsakeskus.fi/sites/default/files/document/"
                 "tiedosto-tietomallikaavio-mv_ey_2-1-3-metsakeskuksen-tietomallin-uudistus.xlsx")
LUKE_API = "https://statdb.luke.fi/PxWeb/api/v1/fi/LUKE"
LUKE_TABLE = "met/teokau/kk/0100_teokau.px"
MUNI_NAMES = {"834": "Tammela"}
OUT = "metsakoe"


def log(*a):
    print(*a, flush=True)


def shoelace(ring):
    s = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        s += x1 * y2 - x2 * y1
    return abs(s) / 2


def poly_area(polys):
    """polys = [[ulkokehä, reikä, ...], ...] → ala m²."""
    return sum(shoelace(p[0]) - sum(shoelace(h) for h in p[1:]) for p in polys)


def describe(path, sample=3, max_distinct=40):
    """Taulut, sarakkeet, rivimäärät, esimerkkirivit ja vähäarvoisten sarakkeiden jakaumat."""
    con = sqlite3.connect(path)
    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'gpkg_%' "
        "AND name NOT LIKE 'rtree_%' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for t in tables:
        cols = [(r[1], r[2]) for r in con.execute(f'PRAGMA table_info("{t}")')]
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        log(f"\n  TAULU {t}: {n} riviä")
        log(f"    sarakkeet: {cols}")
        for row in con.execute(f'SELECT * FROM "{t}" LIMIT {sample}'):
            shown = []
            for (name, _), v in zip(cols, row):
                if isinstance(v, bytes):
                    shown.append(f"{name}=<{len(v)} tavua>")
                else:
                    shown.append(f"{name}={v!r}")
            log("    esim: " + ", ".join(shown))
        if n == 0:
            continue
        for name, typ in cols:
            if "geom" in name.lower() or typ.upper() in ("BLOB", "GEOMETRY", "MULTIPOLYGON", "POLYGON"):
                continue
            k = con.execute(f'SELECT COUNT(DISTINCT "{name}") FROM "{t}"').fetchone()[0]
            nulls = con.execute(f'SELECT COUNT(*) FROM "{t}" WHERE "{name}" IS NULL').fetchone()[0]
            if k <= max_distinct:
                dist = con.execute(f'SELECT "{name}", COUNT(*) c FROM "{t}" GROUP BY 1 ORDER BY c DESC').fetchall()
                log(f"    {name}: {k} arvoa, tyhjiä {nulls}: {dist}")
            else:
                mm = con.execute(f'SELECT MIN("{name}"), MAX("{name}") FROM "{t}"').fetchone()
                log(f"    {name}: {k} eri arvoa, tyhjiä {nulls}, min {mm[0]!r} max {mm[1]!r}")
    con.close()


# ---------- Metsäkeskus ----------

def mv_files(muni):
    """Lataa kunnan metsävarakuviot uudesta tietomallista; palauttaa GeoPackage-polut."""
    r = net.get(MV_BASE)
    hrefs = sorted(set(re.findall(r'href="([^"?]+)"', r.text)))
    log(f"Hakemistossa {MV_BASE}: {len(hrefs)} linkkiä, esim. {hrefs[:12]}")
    name = MUNI_NAMES.get(muni, muni).lower()
    hits = [h for h in hrefs if name in h.lower() or re.search(rf"(^|[^0-9]){muni}([^0-9]|$)", h.rsplit('/', 1)[-1])]
    log("Osumat:", hits)
    if not hits:
        raise RuntimeError(f"Kunnan {muni} tiedostoa ei löytynyt hakemistosta {MV_BASE}")
    os.makedirs(OUT, exist_ok=True)
    paths = []
    for h in hits:
        url = h if h.startswith("http") else (("https://avoin.metsakeskus.fi" + h) if h.startswith("/") else MV_BASE + h)
        dest = os.path.join(OUT, os.path.basename(h))
        t0 = time.time()
        with net.session().get(url, stream=True, timeout=600) as resp:
            resp.raise_for_status()
            log(f"Ladataan {url} (Last-Modified {resp.headers.get('Last-Modified')})")
            with open(dest, "wb") as f:
                for chunk in resp.iter_content(1 << 20):
                    f.write(chunk)
        log(f"  {dest}: {os.path.getsize(dest) / 1e6:.1f} Mt, {time.time() - t0:.0f} s")
        if zipfile.is_zipfile(dest):
            with zipfile.ZipFile(dest) as z:
                log("  zip:", [(i.filename, i.file_size) for i in z.infolist()])
                z.extractall(OUT)
                paths += [os.path.join(OUT, n) for n in z.namelist() if n.lower().endswith(".gpkg")]
        elif dest.lower().endswith(".gpkg"):
            paths.append(dest)
    return paths


def mv_model():
    """Tulostaa Metsäkeskuksen tietomallin kuvauksen (Excel) – sarakkeiden merkitykset ja koodistot."""
    import openpyxl
    r = net.get(MV_MODEL_XLSX)
    wb = openpyxl.load_workbook(io.BytesIO(r.content), read_only=True, data_only=True)
    for ws in wb.worksheets:
        log(f"\n=== TIETOMALLI, välilehti {ws.title} ===")
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            cells = [str(c).replace("\n", " ")[:80] for c in row if c not in (None, "")]
            if cells:
                log("  " + " | ".join(cells))
            if i > 600:
                log("  ... (katkaistu)")
                break


# ---------- Luke ----------

def luke_prices():
    meta = None
    try:
        meta = net.get(f"{LUKE_API}/{LUKE_TABLE}").json()
    except Exception as e:  # noqa: BLE001
        log("Luken taulua ei löytynyt oletuspolusta:", e)
        for path in ["", "met", "met/teokau", "met/teokau/kk"]:
            try:
                log(f"  {LUKE_API}/{path}:", net.get(f"{LUKE_API}/{path}").text[:2000])
            except Exception as e2:  # noqa: BLE001
                log(f"  {path}: {e2}")
        return
    log("\nLuke, muuttujat:")
    for v in meta["variables"]:
        pairs = list(zip(v["values"], v["valueTexts"]))
        log(f"  {v['code']} ({v['text']}): {len(pairs)} arvoa, {pairs[:15]}{' …' if len(pairs) > 15 else ''}"
            f"{' viimeiset ' + str(pairs[-3:]) if len(pairs) > 15 else ''}")
    var = {v["code"]: v for v in meta["variables"]}

    def pick(code_hint, texts):
        v = next(v for c, v in var.items() if code_hint.lower() in (c + v["text"]).lower())
        out = [val for val, txt in zip(v["values"], v["valueTexts"]) if any(t.lower() in txt.lower() for t in texts)]
        return v["code"], out

    month_code = next(c for c, v in var.items() if "kuukau" in (c + v["text"]).lower())
    months = var[month_code]["values"][-6:]
    q = [{"code": month_code, "selection": {"filter": "item", "values": months}}]
    for hint, texts in [("tieto", ["hinta"]), ("alue", ["etelä-suomi"]),
                        ("kauppatapa", ["pystykauppa", "uudistushakkuu", "harvennushakkuu", "ensiharvennus"]),
                        ("puutavara", ["mäntytukki", "kuusitukki", "koivutukki", "mäntykuitu", "kuusikuitu", "koivukuitu"])]:
        code, vals = pick(hint, texts)
        q.append({"code": code, "selection": {"filter": "item", "values": vals}})
    log("Luke-kysely:", q)
    r = net.session().post(f"{LUKE_API}/{LUKE_TABLE}", json={"query": q, "response": {"format": "csv"}}, timeout=120)
    log(f"Luke vastaus HTTP {r.status_code}:\n{r.content.decode('utf-8-sig', 'replace')[:6000]}")


# ---------- MML ----------

def mml_structure(muni):
    m = MMLFiles()
    job = m.execute(PARCEL_PROCESS, {"municipalityInput": muni, "fileFormatInput": "GPKG", "crsOutputInput": "EPSG:3067"})
    m.wait(job)
    _, files = m.results(job)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"krk_{muni}.gpkg")
    g = [f for f in files if str(f.get("path", "")).endswith(".gpkg") or str(f.get("format", "")).upper() == "GPKG"]
    m.download(g[0]["path"], path)
    log(f"MML-kiinteistörekisterikartta {muni}: {os.path.getsize(path) / 1e6:.1f} Mt")
    describe(path, max_distinct=25)
    # tilakohtaiset alat: kaikki palstat yhteen (myös naapurikuntien rajapalstat mukana tiedostossa)
    con = sqlite3.connect(path)
    area = collections.Counter()
    npal = collections.Counter()
    for blob, kt in con.execute('SELECT geom, kiinteistotunnus FROM "PalstanSijaintitiedot"'):
        if blob and kt:
            area[kt] += poly_area(gpkg_polys(blob))
            npal[kt] += 1
    con.close()
    own = {k: a for k, a in area.items() if k.startswith(muni.zfill(3))}
    groups = collections.Counter(k[6:10] for k in own)
    log(f"\nKiinteistöjä kunnan tunnuksella {len(own)} (tiedostossa kaikkiaan {len(area)}); ryhmät (3. osa): "
        f"{groups.most_common(30)}")
    for lim in (0.5, 1, 2, 5, 10, 20, 50, 100):
        sel = [a for a in own.values() if a > lim * 1e4]
        log(f"  yli {lim} ha: {len(sel)} kiinteistöä, yhteensä {sum(sel) / 1e4:.0f} ha")
    big = {k: a for k, a in own.items() if a > 2e4}
    gb = collections.Counter(k[6:10] for k in big)
    log(f"  yli 2 ha ryhmittäin: {gb.most_common(30)}")
    log(f"  palstoja per yli 2 ha kiinteistö: {collections.Counter(min(npal[k], 6) for k in big).most_common()}")
    log(f"  suurimmat: {sorted(((round(a / 1e4), k) for k, a in own.items()), reverse=True)[:15]}")


def main():
    muni = sys.argv[1] if len(sys.argv) > 1 else "834"
    phase = sys.argv[2] if len(sys.argv) > 2 else "rakenne"
    if phase == "laske":
        from .metsa_laske import run
        return run(muni)
    if phase != "rakenne":
        raise SystemExit(f"Tuntematon vaihe {phase}")
    for title, fn in [("METSÄKESKUS: tietomalli", mv_model),
                      ("LUKE: kantohinnat", luke_prices),
                      ("METSÄKESKUS: kunnan metsävarakuviot", lambda: [describe(p) for p in mv_files(muni)]),
                      ("MML: kiinteistörekisterikartta ja tilat", lambda: mml_structure(muni))]:
        log(f"\n##### {title} #####")
        t0 = time.time()
        try:
            fn()
        except Exception as e:  # noqa: BLE001 – yksi lähde ei kaada muita
            log(f"VIRHE ({title}): {type(e).__name__}: {e}")
        log(f"##### {title}: {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
