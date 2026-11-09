"""Talojen ja metsätilojen yhteiset julkaisuapuvälineet: loki, ajon hallittu lopetus, tiedostonimet, tippecanoe,
julkaistun sivun meta.json ja koodiversio sivun tiedostonimiin."""
import datetime as dt
import os
import subprocess
import sys
import time

from . import net

MAX_FILE_MB = 95  # GitHub Pagesin raja on 100 Mt tiedostoa kohden


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def fail(msg):
    """Lopettaa ajon ilman julkaisua. GitHub Actionsissa viesti näkyy virheenä, ja ilmoitus (issue) poimii sen."""
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::error title=Julkaisua ei tehty::{msg}", flush=True)
    sys.exit(msg)


def fmt_kt(k):
    """'83440400030064' -> '834-404-3-64'"""
    if not k or len(k) != 14 or not k.isdigit():
        return k or ""
    return f"{int(k[0:3])}-{int(k[3:6])}-{int(k[6:10])}-{int(k[10:14])}"


def slug(name):
    """'Kanta-Häme' -> 'kanta-hame' (tiedostonimiin)."""
    t = name.lower().translate(str.maketrans({"ä": "a", "ö": "o", "å": "a"}))
    return "".join(c if c.isalnum() else "-" for c in t).strip("-")


def tippecanoe(src, out, layer, zmin, zmax, extra=()):
    """Karttatiilet GeoJSONSeq-tiedostosta PMTiles-tiedostoksi. Keskeyttää ajon, jos tulos on liian suuri Pagesille."""
    cmd = ["tippecanoe", "-o", out, "--force", "--quiet", f"-Z{zmin}", f"-z{zmax}", "-l", layer,
           "--no-tile-size-limit", "--no-feature-limit", *extra, src]
    log(" ".join(cmd))
    subprocess.run(cmd, check=True)
    size = os.path.getsize(out) / 1e6
    if size > MAX_FILE_MB:
        fail(f"{os.path.basename(out)} on {size:.1f} Mt, yli GitHub Pagesin rajan")
    return size


def previous_meta(site_url):
    """Julkaistun sivun meta.json vertailua varten (None, jos ei saatavilla, esim. ensimmäinen julkaisu)."""
    try:
        return net.get(site_url + "data/meta.json", {"t": str(int(time.time()))}, tries=3, timeout=30).json()
    except Exception as e:  # noqa: BLE001
        log(f"  julkaistua meta.jsonia ei saatu ({e}); turvatarkistus ohitetaan")
        return None


def stamp_assets(html_path, names):
    """Lisää sivun script/link-viittauksiin ?v=<aika>, jotta selain hakee uuden version julkaisun jälkeen."""
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M")
    html = open(html_path, encoding="utf-8").read()
    for n in names:
        attr = "href" if n.endswith(".css") else "src"
        html = html.replace(f'{attr}="{n}"', f'{attr}="{n}?v={stamp}"')
    open(html_path, "w", encoding="utf-8").write(html)


def peak_memory():
    """Muistin huippukäyttö (Linux) lokiin – koko Suomen mitoituksen seurantaan."""
    import resource
    return (f"Muistin huippu: ohjelma {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024:.0f} Mt, "
            f"aliprosessit {resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss / 1024:.0f} Mt")
