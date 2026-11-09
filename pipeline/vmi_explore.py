"""SELVITYS (9.11.2026): Luken monilähde-VMI 2023 -kartta-aineisto (puuston tilavuus) kaukonäkymän metsäkuvaa varten.
Vaihe "linkit": tulostaa Luken tiedostopalvelun sivun linkit (tiedostonimien muoto). Vaihe "lataa:<url>": lataa yhden
tiedoston ja tulostaa koon, keston ja arvojakauman. Ei vaikuta sivuun. Kumoaminen: poista tämä ja explore-vmi.yml.
"""
import re
import sys
import time
import urllib.parse

import requests

UA = {"User-Agent": "Talokartta-selvitys (github.com/vv-tec/Talokartta)"}


def links(url):
    r = requests.get(url, headers=UA, timeout=60)
    print(f"{url}: HTTP {r.status_code}, {len(r.content)} tavua, {r.headers.get('content-type')}")
    found = sorted(set(re.findall(r'''(?:href|src)\s*=\s*["']([^"']+)["']''', r.text, re.I)))
    for h in found[:400]:
        print("  linkki:", urllib.parse.urljoin(url, h))
    js = re.findall(r'["\']([^"\']*(?:tilavuus|vmi|\.tif|\.zip)[^"\']*)["\']', r.text, re.I)
    for s in sorted(set(js))[:200]:
        print("  merkkijono:", s)
    if len(found) < 5:
        print(r.text[:4000])
    return r.text


def download(url):
    t0 = time.time()
    with requests.get(url, headers=UA, timeout=300, stream=True) as r:
        print(f"{url}: HTTP {r.status_code}, {r.headers.get('content-type')}, koko {r.headers.get('content-length')}")
        r.raise_for_status()
        with open("vmi.bin", "wb") as f:
            n = 0
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
                n += len(chunk)
    print(f"ladattu {n / 1e6:.1f} Mt {time.time() - t0:.0f} s")
    try:
        import numpy as np
        import tifffile
        a = tifffile.imread("vmi.bin")
        print("muoto", a.shape, a.dtype)
        with tifffile.TiffFile("vmi.bin") as t:
            for tag in t.pages[0].tags.values():
                if tag.name in ("ModelPixelScaleTag", "ModelTiepointTag", "GeoKeyDirectoryTag", "Compression", "GDAL_NODATA"):
                    print("  ", tag.name, str(tag.value)[:200])
        v = a[(a < 32766)]
        print(f"kelvollisia {v.size} / {a.size} ({100 * v.size / a.size:.1f} %), 32766: {(a == 32766).sum()}, 32767: {(a == 32767).sum()}")
        if v.size:
            print("tilavuus m³/ha: keskiarvo %.1f, persentiilit 10/50/90/99: %s" % (v.mean(), np.percentile(v, [10, 50, 90, 99])))
    except Exception as e:  # noqa: BLE001
        print("lukuvirhe:", e)


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "linkit"
    if arg == "linkit":
        for u in ["https://kartta.luke.fi/opendata/valinta.html", "https://kartta.luke.fi/opendata/"]:
            try:
                links(u)
            except Exception as e:  # noqa: BLE001
                print(u, "virhe:", e)
    elif arg.startswith("sivu:"):
        links(arg[5:])
    elif arg.startswith("lataa:"):
        download(arg[6:])
