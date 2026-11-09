"""SELVITYS (9.11.2026): Luken monilähde-VMI 2023 -kartta-aineisto (puuston tilavuus) kaukonäkymän metsäkuvaa varten.
Vaihe "linkit": tulostaa Luken tiedostopalvelun sivun linkit (tiedostonimien muoto). Vaihe "lataa:<url>": lataa yhden
tiedoston ja tulostaa koon, keston ja arvojakauman. Ei vaikuta sivuun. Kumoaminen: poista tämä ja explore-vmi.yml.
"""
import os
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


def full():
    """Koko Suomen tilavuustiedosto: lataus, kokoaminen 256 m ruutuihin, arvojakauma ja pistokokeet."""
    import resource
    import numpy as np
    import tifffile
    from ..metsa import vmi
    from ..yhteiset.tm35 import latlon_to_tm35_np
    t0 = time.time()
    vmi.download("vmi.tif")
    with tifffile.TiffFile("vmi.tif") as t:
        pg = t.pages[0]
        print("muoto", pg.shape, pg.dtype, "pakkaus", pg.compression, "tiili", pg.tilewidth, pg.tilelength,
              "rivit/lohko", pg.rowsperstrip)
        for tag in pg.tags.values():
            if tag.name in ("ModelPixelScaleTag", "ModelTiepointTag", "GDAL_NODATA"):
                print("  ", tag.name, str(tag.value)[:200])
    t1 = time.time()
    r = vmi.aggregate("vmi.tif", block=16)
    print(f"kokoaminen {time.time() - t1:.0f} s, muistin huippu {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1e6:.2f} Gt")
    vol, forest, nocalc = r["vol"], r["forest"], r["nocalc"]
    full_px = r["block"] ** 2
    valid = full_px - nocalc
    tot = np.where(valid > 0, vol / np.maximum(valid, 1), 0)      # m³/ha koko alasta
    fh = np.where(forest > 0, vol / np.maximum(forest, 1), 0)     # m³/ha metsämaasta
    print("ruudukko", tot.shape, "x0", r["x0"], "y0", r["y0"], "solu", r["cell"], "m")
    print(f"laskematta (32766) yhteensä {nocalc.sum()} pikseliä; metsäpikseleitä {forest.sum()}")
    sel = forest > 0
    print("koko alaa kohden m³/ha (ruudut, joissa metsää) persentiilit 5/25/50/75/95/99:",
          np.round(np.percentile(tot[sel], [5, 25, 50, 75, 95, 99]), 1))
    print("metsämaata kohden m³/ha persentiilit 5/25/50/75/95/99:", np.round(np.percentile(fh[sel], [5, 25, 50, 75, 95, 99]), 1))
    places = {"Nauvo (saaristo)": (60.19, 21.91), "Korppoo (saaristo)": (60.16, 21.56), "Tammela": (60.81, 23.76),
              "Helsinki": (60.17, 24.94), "Kuhmo": (64.13, 29.52), "Suomussalmi": (64.89, 28.90),
              "Rovaniemi": (66.50, 25.73), "Pallas (valtio)": (68.05, 24.06), "Seinäjoki (peltoa)": (62.79, 22.84),
              "Puumala (järviä)": (61.52, 28.18), "Inari": (68.90, 27.03)}
    for name, (la, lo) in places.items():
        x, y = latlon_to_tm35_np(np.array([la]), np.array([lo]))
        c = int((x[0] - r["x0"]) // r["cell"]); rr = int((r["y0"] - y[0]) // r["cell"])
        for k, lab in ((2, "1 km"), (10, "5 km")):
            w = (slice(max(0, rr - k), rr + k), slice(max(0, c - k), c + k))
            vt = vol[w].sum() / max(1, valid[w].sum()); vf = vol[w].sum() / max(1, forest[w].sum())
            print(f"  {name} {lab}: koko alasta {vt:.0f} m³/ha, metsämaasta {vf:.0f} m³/ha, metsää {100 * forest[w].sum() / max(1, valid[w].sum()):.0f} %")
    np.savez_compressed("vmi256.npz", vol=vol.astype(np.float32), forest=forest.astype(np.uint16),
                        nocalc=nocalc.astype(np.uint16), meta=np.array([r["x0"], r["y0"], r["cell"]]))
    print(f"vmi256.npz {os.path.getsize('vmi256.npz') / 1e6:.1f} Mt; yhteensä {time.time() - t0:.0f} s")


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
    elif arg == "koko":
        full()
    elif arg.startswith("lataa:"):
        download(arg[6:])
