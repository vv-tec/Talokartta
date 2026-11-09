"""METSAKARTTA – metsäkuva kaukonäkymään Luken monilähde-VMI:n puuston tilavuudesta (omistajan päätös 9.11.2026).

Mittari: puuston määrä **koko alaa kohden** (m³/ha; meri, järvet, pellot ja taajamat lasketaan nollana → vaalentavat).
Lähde: Luonnonvarakeskus, monilähteisen VMI:n kartta-aineisto 2023 (CC BY 4.0), koko Suomi yhtenä GeoTIFFinä (16 m,
ETRS-TM35FIN, arvo m³/ha metsä-, kitu- ja joutomaalla; 32767 = muu maa, vesi tai Suomen ulkopuoli; 32766 = ei laskettu,
esim. pilvi). Tiedosto luetaan lohkoittain (koko maa olisi muistissa ~6 Gt) ja kootaan BLOCK×BLOCK-pikselin ruutuihin.
"""
import os
import time

import numpy as np
import requests

URL = "https://www.nic.funet.fi/index/geodata/luke/vmi/2023/tilavuus_vmi1x_1923.tif"
YEAR = 2023
NODATA = 32767     # muu kuin metsä-/kitu-/joutomaa (myös vesi) tai Suomen ulkopuoli
NOCALC = 32766     # ei laskettu (pilvi tms.)
UA = {"User-Agent": "Talokartta (github.com/vv-tec/Talokartta)"}


def download(dest, url=URL, tries=4):
    """Lataa tiedoston (jatkaa keskeytynyttä latausta, jos palvelin sallii)."""
    t0 = time.time()
    for attempt in range(1, tries + 1):
        have = os.path.getsize(dest) if os.path.exists(dest) else 0
        headers = dict(UA, **({"Range": f"bytes={have}-"} if have else {}))
        try:
            with requests.get(url, headers=headers, timeout=120, stream=True) as r:
                if r.status_code == 416:      # jo kokonaan ladattu
                    break
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with open(dest, mode) as f:
                    for chunk in r.iter_content(1 << 22):
                        f.write(chunk)
            break
        except requests.RequestException as e:
            print(f"  VMI-lataus katkesi ({e}); yritys {attempt}/{tries}", flush=True)
            if attempt == tries:
                raise
            time.sleep(20 * attempt)
    print(f"  VMI ladattu: {os.path.getsize(dest) / 1e6:.0f} Mt, {time.time() - t0:.0f} s", flush=True)
    return dest


def aggregate(path, block=16):
    """Kokoaa 16 m pikselit block×block-ruutuihin. Palauttaa dictin: vol (m³/ha-summa metsäpikseleistä, float64),
    forest (metsä-/kitu-/joutomaapikseleitä), nocalc (laskematta), x0, y0 (vasen yläkulma, m), cell (m), shape."""
    import tifffile
    with tifffile.TiffFile(path) as tif:
        page = tif.pages[0]
        h, w = page.shape[:2]
        scale = page.tags["ModelPixelScaleTag"].value
        tie = page.tags["ModelTiepointTag"].value   # (i, j, k, x, y, z)
        px = float(scale[0])
        x0 = float(tie[3]) - float(tie[0]) * px
        y0 = float(tie[4]) + float(tie[1]) * px
        ch, cw = -(-h // block), -(-w // block)
        vol = np.zeros((ch, cw), dtype=np.float64)
        forest = np.zeros((ch, cw), dtype=np.int32)
        nocalc = np.zeros((ch, cw), dtype=np.int32)
        for data, idx, shape in page.segments():
            if data is None:
                continue
            a = np.asarray(data).reshape(shape[-3], shape[-2])
            r0, c0 = idx[-3], idx[-2]
            a = a[: max(0, min(a.shape[0], h - r0)), : max(0, min(a.shape[1], w - c0))]
            if a.size == 0:
                continue
            rows = (np.arange(a.shape[0]) + r0) // block
            cols = (np.arange(a.shape[1]) + c0) // block
            nr, nc_ = rows[-1] - rows[0] + 1, cols[-1] - cols[0] + 1
            local = ((rows - rows[0])[:, None] * nc_ + (cols - cols[0])[None, :]).ravel()
            win = (slice(rows[0], rows[0] + nr), slice(cols[0], cols[0] + nc_))
            v = a.ravel()
            ok = v < NOCALC
            if ok.any():
                vol[win] += np.bincount(local[ok], weights=v[ok].astype(np.float64), minlength=nr * nc_).reshape(nr, nc_)
                forest[win] += np.bincount(local[ok], minlength=nr * nc_).reshape(nr, nc_).astype(np.int32)
            ncm = v == NOCALC
            if ncm.any():
                nocalc[win] += np.bincount(local[ncm], minlength=nr * nc_).reshape(nr, nc_).astype(np.int32)
    return {"vol": vol, "forest": forest, "nocalc": nocalc,
            "x0": x0, "y0": y0, "cell": px * block, "block": block, "shape": (h, w)}
