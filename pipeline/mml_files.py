"""Maanmittauslaitoksen paikkatiedon tiedostopalvelu (OGC API Processes).

Palvelu vaatii ilmaisen API-avaimen (MML OmaTili). Avain luetaan ympäristömuuttujasta MML_API_KEY
(GitHubissa repositorion salaisuus) ja lähetetään Basic-tunnistautumisena, jolloin palvelun palauttamat
linkit toimivat sellaisenaan.

Kulku: POST /processes/{id}/execution -> työ (jobID) -> GET /jobs/{id} kunnes "successful"
-> GET /jobs/{id}/results/ -> ladataan tiedostot.
"""
import os
import sqlite3
import struct
import time

import requests

from .config import USER_AGENT

BASE = "https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1"


class MMLFiles:
    def __init__(self, api_key=None, log=print):
        key = api_key or os.environ.get("MML_API_KEY")
        if not key:
            raise RuntimeError("MML_API_KEY puuttuu (Maanmittauslaitoksen API-avain, GitHubissa repositorion salaisuus).")
        self.s = requests.Session()
        self.s.auth = (key, "")
        self.s.headers["User-Agent"] = USER_AGENT
        self.log = log

    def _req(self, method, url, tries=5, **kw):
        for attempt in range(tries):
            try:
                r = self.s.request(method, url, timeout=300, **kw)
                if r.status_code < 500 and r.status_code != 429:
                    r.raise_for_status()
                    return r
                err = f"HTTP {r.status_code}: {r.text[:300]}"
            except requests.RequestException as e:
                if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 500:
                    raise RuntimeError(f"{method} {url}: HTTP {e.response.status_code} {e.response.text[:500]}") from e
                err = str(e)
            time.sleep(min(60, 5 * 2 ** attempt))
        raise RuntimeError(f"{method} {url} epäonnistui: {err}")

    def get_json(self, path):
        return self._req("GET", path if path.startswith("http") else BASE + path).json()

    def execute(self, process_id, inputs):
        r = self._req("POST", f"{BASE}/processes/{process_id}/execution", json={"id": process_id, "inputs": inputs})
        job = r.json()
        return job.get("jobID") or job.get("jobId") or job.get("id")

    def wait(self, job_id, max_minutes=120):
        t0 = time.time()
        while True:
            st = self.get_json(f"/jobs/{job_id}")
            status = st.get("status")
            if status == "successful":
                return st
            if status in ("failed", "dismissed"):
                raise RuntimeError(f"MML-työ {job_id} päättyi tilaan {status}: {str(st)[:500]}")
            if time.time() - t0 > max_minutes * 60:
                raise RuntimeError(f"MML-työ {job_id} ei valmistunut {max_minutes} minuutissa")
            time.sleep(10)

    def results(self, job_id):
        """Palauttaa listan tiedostotietueita (sisältää ainakin 'path' eli latauslinkin)."""
        res = self.get_json(f"/jobs/{job_id}/results/")
        files = []

        def walk(x):
            if isinstance(x, dict):
                if any(k in x for k in ("path", "href")) and any(k in x for k in ("format", "mimeType", "length", "type")):
                    files.append(x)
                for v in x.values():
                    walk(v)
            elif isinstance(x, list):
                for v in x:
                    walk(v)
        walk(res)
        return res, files

    def download(self, url, dest):
        if not url.startswith("http"):
            url = "https://avoin-paikkatieto.maanmittauslaitos.fi" + url
        with self._req("GET", url, stream=True) as r, open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        return dest


# ---------- GeoPackage-geometriat (ilman lisäkirjastoja) ----------

def _wkb_polys(b, o=0):
    """Lukee WKB:stä (Multi)Polygonin. Palauttaa (polys, uusi_offset); polys = [[ulkorengas, reikä...], ...]."""
    endian = "<" if b[o] == 1 else ">"
    gtype = struct.unpack_from(endian + "I", b, o + 1)[0]
    o += 5
    has_z = has_m = False
    if gtype & 0x80000000:
        has_z = True
    if gtype & 0x40000000:
        has_m = True
    gtype &= 0x0FFFFFFF
    if gtype >= 3000:
        has_z = has_m = True; gtype -= 3000
    elif gtype >= 2000:
        has_m = True; gtype -= 2000
    elif gtype >= 1000:
        has_z = True; gtype -= 1000
    dims = 2 + has_z + has_m
    if gtype == 3:  # Polygon
        (nr,) = struct.unpack_from(endian + "I", b, o); o += 4
        rings = []
        for _ in range(nr):
            (n,) = struct.unpack_from(endian + "I", b, o); o += 4
            vals = struct.unpack_from(endian + "d" * (n * dims), b, o); o += 8 * n * dims
            rings.append([(vals[i], vals[i + 1]) for i in range(0, len(vals), dims)])
        return [rings], o
    if gtype == 6:  # MultiPolygon
        (n,) = struct.unpack_from(endian + "I", b, o); o += 4
        polys = []
        for _ in range(n):
            p, o = _wkb_polys(b, o)
            polys += p
        return polys, o
    raise ValueError(f"Tuntematon geometriatyyppi {gtype}")


def gpkg_polys(blob):
    """GeoPackage-geometria (GP-otsake + WKB) -> [[ulkorengas, reikä...], ...]."""
    if blob[:2] != b"GP":
        raise ValueError("Ei GeoPackage-geometria")
    flags = blob[3]
    env = (flags >> 1) & 0b111
    env_len = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[env]
    return _wkb_polys(blob, 8 + env_len)[0]


def describe_gpkg(path, log=print, sample=3):
    """Tulostaa GeoPackagen taulut, sarakkeet, rivimäärät ja esimerkkirivit (vianetsintään)."""
    con = sqlite3.connect(path)
    try:
        tables = [r[0] for r in con.execute("SELECT table_name FROM gpkg_contents")]
    except sqlite3.Error:
        tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
    for t in tables:
        cols = [(r[1], r[2]) for r in con.execute(f'PRAGMA table_info("{t}")')]
        n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        log(f"  taulu {t}: {n} riviä; sarakkeet {cols}")
        for row in con.execute(f'SELECT * FROM "{t}" LIMIT {sample}'):
            shown = []
            for (name, typ), v in zip(cols, row):
                if isinstance(v, bytes):
                    try:
                        polys = gpkg_polys(v)
                        shown.append(f"{name}=<{len(polys)} polygonia, {len(polys[0][0])} pistettä, eka {polys[0][0][0]}>")
                    except Exception as e:  # noqa: BLE001
                        shown.append(f"{name}=<{len(v)} tavua {v[:12].hex()} ({e})>")
                else:
                    shown.append(f"{name}={v!r}")
            log("    " + ", ".join(shown))
    con.close()
