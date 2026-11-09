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


# ---------- kaukonäkymän kuva (rasteritiilet) ----------
RENDER_VERSION = 1           # nosta, kun väritys tai laskenta muuttuu → kuva tehdään uudelleen seuraavassa ajossa
TILE = 256
ZMIN, ZMAX = 0, 9            # tilojen rajat näkyvät zoomista 10 (config.METSA_POLY_MINZOOM)
BOUNDS = (19.0, 59.4, 31.8, 70.2)   # lon/lat: Manner-Suomi ja Ahvenanmaa (tiilet vain tälle alueelle)
# Väriasteikko: puuta koko alaa kohden m³/ha → väri (liukuva). Alle FADE m³/ha häivytetään läpinäkyväksi
# (meri, järvet, pellot ja taajamat näkyvät taustakartan väreissä).
# Koeajo 9.11.2026 (256 m ruudut, joissa metsää): mediaani 73, 75 % 115, 95 % 179 m³/ha.
RAMP = [(0, "#f1eadb"), (25, "#d6e5b9"), (50, "#a8cf8e"), (75, "#6fae6b"), (100, "#3c8a4f"), (140, "#1d5e34")]
FADE = 8.0
OPACITY = 0.78
BLUR_PASSES = 3              # pehmennyskierrokset kullakin tasolla (3 × 1-2-1 ≈ 1,2 solun gaussinen)


def _rgb(hexcol):
    return [int(hexcol[i:i + 2], 16) for i in (1, 3, 5)]


def total_per_ha(agg):
    """Puuta koko alaa kohden (m³/ha) ruuduittain; NaN, jos ruudussa ei ole yhtään laskettua pikseliä."""
    valid = agg["block"] ** 2 - agg["nocalc"].astype(np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(valid > 0, agg["vol"] / valid, np.nan)


def _blur(a, passes=None):
    """Pehmennys (binomi 1-2-1 molempiin suuntiin, BLUR_PASSES kertaa); NaN-kohdat eivät levitä virhettä."""
    w = np.where(np.isnan(a), 0.0, 1.0)
    v = np.nan_to_num(a)
    for _ in range(BLUR_PASSES if passes is None else passes):
        for axis in (0, 1):
            v = (np.roll(v, 1, axis) + 2 * v + np.roll(v, -1, axis)) / 4
            w = (np.roll(w, 1, axis) + 2 * w + np.roll(w, -1, axis)) / 4
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(w > 0.2, v / w, np.nan)


def pyramid(tot, levels=6):
    """Tasot 1×, 2×, 4× … solukoko (keskiarvo 2×2), kukin pehmennettynä."""
    out = [_blur(tot)]
    cur = tot
    for _ in range(levels - 1):
        h, w = cur.shape
        pad = np.full((h + h % 2, w + w % 2), np.nan)
        pad[:h, :w] = cur
        blocks = pad.reshape(pad.shape[0] // 2, 2, pad.shape[1] // 2, 2)
        with np.errstate(invalid="ignore"):
            cur = np.nanmean(blocks, axis=(1, 3)) if np.isfinite(blocks).any() else blocks[:, 0, :, 0]
        out.append(_blur(cur))
    return out


def _bilinear(a, fx, fy):
    h, w = a.shape
    x0 = np.clip(np.floor(fx).astype(int), 0, w - 1)
    y0 = np.clip(np.floor(fy).astype(int), 0, h - 1)
    x1, y1 = np.clip(x0 + 1, 0, w - 1), np.clip(y0 + 1, 0, h - 1)
    tx, ty = np.clip(fx - x0, 0, 1), np.clip(fy - y0, 0, 1)
    v = (a[y0, x0] * (1 - tx) * (1 - ty) + a[y0, x1] * tx * (1 - ty) + a[y1, x0] * (1 - tx) * ty + a[y1, x1] * tx * ty)
    outside = (fx < -0.5) | (fy < -0.5) | (fx > w - 0.5) | (fy > h - 0.5)
    return np.where(outside, np.nan, v)


def colorize(v):
    """m³/ha → RGBA (uint8). Liukuva väri RAMPin mukaan; pienet arvot ja NaN läpinäkyviä."""
    stops = np.array([s for s, _ in RAMP], dtype=float)
    cols = np.array([_rgb(c) for _, c in RAMP], dtype=float)
    vv = np.nan_to_num(v, nan=0.0)
    rgba = np.zeros(v.shape + (4,), dtype=np.uint8)
    for ch in range(3):
        rgba[..., ch] = np.interp(vv, stops, cols[:, ch]).round().astype(np.uint8)
    alpha = np.clip(vv / FADE, 0, 1) * OPACITY * 255
    rgba[..., 3] = np.where(np.isnan(v), 0, alpha).round().astype(np.uint8)
    return rgba


def _tile_range(z):
    import math
    n = 2 ** z
    def tx(lon):
        return int((lon + 180) / 360 * n)
    def ty(lat):
        r = math.radians(lat)
        return int((1 - math.log(math.tan(r) + 1 / math.cos(r)) / math.pi) / 2 * n)
    return range(tx(BOUNDS[0]), tx(BOUNDS[2]) + 1), range(ty(BOUNDS[3]), ty(BOUNDS[1]) + 1)


def render_tile(levels, x0, y0, cell, z, x, y):
    """Yksi 256×256 PNG-tiili (tai None, jos tyhjä)."""
    import io
    from PIL import Image
    from .tm35 import latlon_to_tm35_np
    n = 2 ** z
    px = (np.arange(TILE) + 0.5) / TILE
    lon = (x + px) / n * 360 - 180
    merc = np.pi * (1 - 2 * (y + px) / n)
    lat = np.degrees(np.arctan(np.sinh(merc)))
    LON, LAT = np.meshgrid(lon, lat)
    X, Y = latlon_to_tm35_np(LAT, LON)
    pix_m = 40075016.7 * np.cos(np.radians(lat.mean())) / (TILE * n)
    lvl = 0
    while lvl + 1 < len(levels) and cell * 2 ** (lvl + 1) <= pix_m:
        lvl += 1
    c = cell * 2 ** lvl
    v = _bilinear(levels[lvl], (X - x0) / c - 0.5, (y0 - Y) / c - 0.5)
    rgba = colorize(v)
    if not rgba[..., 3].any():
        return None
    img = Image.fromarray(rgba, "RGBA").quantize(colors=128, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def render_pmtiles(agg, out):
    """Koko Suomen kuva PMTiles-tiedostoksi (PNG-tiilet z ZMIN–ZMAX). Palauttaa tiilien määrän."""
    from pmtiles.tile import Compression, TileType, zxy_to_tileid
    from pmtiles.writer import Writer
    levels = pyramid(total_per_ha(agg))
    jobs = sorted((zxy_to_tileid(z, x, y), z, x, y) for z in range(ZMIN, ZMAX + 1)
                  for x in _tile_range(z)[0] for y in _tile_range(z)[1])
    count = 0
    with open(out, "wb") as f:
        w = Writer(f)
        for tid, z, x, y in jobs:
            data = render_tile(levels, agg["x0"], agg["y0"], agg["cell"], z, x, y)
            if data:
                w.write_tile(tid, data)
                count += 1
        e7 = lambda v: int(v * 1e7)  # noqa: E731
        w.finalize({"tile_type": TileType.PNG, "tile_compression": Compression.NONE, "min_zoom": ZMIN,
                    "max_zoom": ZMAX, "min_lon_e7": e7(BOUNDS[0]), "min_lat_e7": e7(BOUNDS[1]),
                    "max_lon_e7": e7(BOUNDS[2]), "max_lat_e7": e7(BOUNDS[3]), "center_zoom": 5,
                    "center_lon_e7": e7(25.5), "center_lat_e7": e7(64.5)},
                   {"attribution": f"© Luonnonvarakeskus, monilähteisen VMI:n kartta-aineisto {YEAR} (CC BY 4.0)"})
    return count
