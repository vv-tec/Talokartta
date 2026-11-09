"""Metsätilakoe, vaihe "laske" (tiekartan kohta 6): tilakohtaiset luvut yhdelle kunnalle → Excel omistajalle.

Lähteet:
  - MML kiinteistörekisterikartta (palstat → kiinteistöt; kiinteistö = sen kaikki palstat kunnan tiedostossa)
  - Metsäkeskuksen metsävarakuviot, uusi tietomalli (MV/Kunta/MV_<kunta>.zip): kuvio (stand), kasvupaikka
    (growthplacedata), puustotieto (treestand: luokka 1 inventointi, 2 laskettu nykyhetkeen, 3 ennuste),
    puustoyhteenveto (treestandsummary, m³/ha) ja ositteet puulajeittain (treestratum, m³/ha)
  - Luken kantohinnat hinta-alueittain kuukausittain (0100_teokau)
  - Ryhti: kiinteistön rakennukset (ristiinlinkitystä varten)

Kuvio jaetaan kiinteistöille kuvion ja palstan leikkauksen alan mukaan (hehtaarikohtaiset luvut × leikkauksen ala).
Tuottaa metsakoe/metsatilat_<kunta>.xlsx (+ csv lokiin) ja arvion karttatiedostojen koosta (tippecanoe).
"""
import collections
import csv
import json
import os
import sqlite3
import subprocess
import time
import zipfile

import shapely
from shapely.geometry import MultiPolygon, Polygon, mapping
from shapely.strtree import STRtree

# Selvitys käyttää tuotannon metsälaskentaa (pipeline/metsa); tuotanto ei koskaan tuo selvityksistä.
from .. import config
from ..metsa.hinnat import ASSORT, PRICE_AREA, PRICE_AREA_MUNI, TRADES, luke_prices, price_group  # noqa: F401
from ..metsa.kuviot import codes, num, read_stands, species_group, to_shape  # noqa: F401
from ..yhteiset import net, ryhti
from ..yhteiset.julkaisu import fmt_kt
from ..yhteiset.mml_files import MMLFiles, PARCEL_PROCESS, gpkg_polys
from ..yhteiset.ryhti import keep
from ..yhteiset.tm35 import tm35_to_latlon
from .metsa_explore import MUNI_NAMES, MV_BASE, OUT, log

GROUP_NAME = {"manty": "mänty ja muut havupuut", "kuusi": "kuusi", "koivu": "koivu", "lehti": "muut lehtipuut"}
MIN_HA = 2.0  # metsätilan raja (omistajan päätös 6.11.2026)
DEV_GROUPS = [  # kehitysluokat sarakkeiksi
    ("Aukea/siemenpuu %", {"A0", "S0"}), ("Taimikko %", {"T1", "T2", "Y1"}), ("Nuori kasvatus (02) %", {"02"}),
    ("Varttunut kasvatus (03) %", {"03"}), ("Uudistuskypsä (04) %", {"04"}), ("Suojuspuu (05) %", {"05"}),
    ("Eri-ikäisrakenteinen %", {"ER"}),
]


# ---------- MML ----------

def mml_parcels(muni):
    m = MMLFiles()
    job = m.execute(PARCEL_PROCESS, {"municipalityInput": muni, "fileFormatInput": "GPKG", "crsOutputInput": "EPSG:3067"})
    m.wait(job)
    _, files = m.results(job)
    g = [f for f in files if str(f.get("path", "")).endswith(".gpkg") or str(f.get("format", "")).upper() == "GPKG"]
    path = os.path.join(OUT, f"krk_{muni}.gpkg")
    m.download(g[0]["path"], path)
    con = sqlite3.connect(path)
    parcels = []
    for blob, kt in con.execute('SELECT geom, kiinteistotunnus FROM "PalstanSijaintitiedot"'):
        if blob and kt and kt.startswith(muni.zfill(3)):
            geom = to_shape(gpkg_polys(blob))
            if geom is not None and not geom.is_empty:
                parcels.append((kt, geom))
    con.close()
    return parcels


# ---------- Metsäkeskus ----------

def mv_gpkg(muni):
    name = MUNI_NAMES.get(muni, muni)
    url = f"{MV_BASE}MV_{name}.zip"
    dest = os.path.join(OUT, f"MV_{name}.zip")
    with net.session().get(url, stream=True, timeout=600) as r:
        r.raise_for_status()
        modified = r.headers.get("Last-Modified")
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    with zipfile.ZipFile(dest) as z:
        z.extractall(OUT)
        gp = [os.path.join(OUT, n) for n in z.namelist() if n.lower().endswith(".gpkg")][0]
    return gp, modified


# ---------- Ryhti ----------

def ryhti_by_property(muni):
    allb, res = collections.Counter(), collections.Counter()
    for b in ryhti.buildings(muni):
        k = b.get("property_identifier")
        if not k:
            continue
        allb[k] += 1
        if keep(b):
            res[k] += 1
    return allb, res


# ---------- laskenta ----------

def run(muni):
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    region = next(r for r, ms in config.REGIONS.items() if muni in ms)
    area = PRICE_AREA_MUNI.get(muni, PRICE_AREA[region])
    latest, ptable, months = luke_prices(area)
    log(f"Kantohinnat ({region} → {area}): " + ", ".join(f"{k[0]}/{k[1]} {v[0]} ({v[1]})" for k, v in sorted(latest.items())))

    gp, modified = mv_gpkg(muni)
    log(f"Metsäkeskuksen aineisto {gp} (päivitetty {modified}), {time.time() - t0:.0f} s")
    stands, C = read_stands(gp)
    parcels = mml_parcels(muni)
    log(f"Palstoja (kunnan kiinteistöt) {len(parcels)}, {time.time() - t0:.0f} s")
    allb, resb = ryhti_by_property(muni)
    log(f"Ryhti: {sum(allb.values())} rakennusta, joista asuinrakennuksia {sum(resb.values())}, {time.time() - t0:.0f} s")

    tree = STRtree([g for _, g in parcels])
    props = collections.defaultdict(lambda: collections.defaultdict(float))
    meta = collections.defaultdict(lambda: {"inv": [], "calc": [], "palstat": []})
    for kt, g in parcels:
        P = props[kt]
        P["ala"] += g.area / 1e4
        meta[kt]["palstat"].append(g)
    matched = unmatched = 0.0
    for sid, s in stands.items():
        g = s["geom"]
        ga = g.area
        if ga <= 0:
            continue
        hits = tree.query(g, predicate="intersects")
        inside = 0.0
        for i in hits:
            kt, pg = parcels[i]
            a = g.intersection(pg).area
            if a < 1:
                continue
            inside += a
            ha = a / 1e4
            P = props[kt]
            mg = s.get("mg")
            if mg == "1":
                P["metsamaa"] += ha
            elif mg in ("2", "3"):
                P["kitujouto"] += ha
            else:
                P["muu_kuvio"] += ha
            if "vol" not in s:
                P["ei_puustoa_ha"] += ha
                continue
            P["puusto_ha"] += ha
            vol, saw, pulp = s["vol"] * ha, s["saw"] * ha, s["pulp"] * ha
            P["vol"] += vol
            P["saw"] += saw
            P["pulp"] += pulp
            if s.get("age") is not None:
                P["ika_x_ha"] += s["age"] * ha
                P["ika_ha"] += ha
            for gname, sh in s["share"]["vol"].items():
                P["vol_" + gname] += vol * sh
            value_p = value_h = 0.0
            dc = s.get("dc") or ""
            trade = "UUD" if dc in ("04", "05", "ER", "S0", "Y1") else "HAR" if dc == "03" else "ENS" if dc == "02" else "PKAUP"
            for kind, amount in (("tukki", saw), ("kuitu", pulp)):
                for gname, sh in s["share"]["saw" if kind == "tukki" else "pulp"].items():
                    ptl = ASSORT[(price_group(gname), kind)]
                    p = latest.get(("PKAUP", ptl), (0, None))[0]
                    ph = (latest.get((trade, ptl)) or latest.get(("HAR", ptl)) or latest.get(("PKAUP", ptl)) or (0, None))[0]
                    value_p += amount * sh * p
                    value_h += amount * sh * ph
                    P[f"{kind}_{price_group(gname)}"] += amount * sh
            P["arvo"] += value_p
            P["arvo_hakkuutapa"] += value_h
            if mg == "1":
                P[f"dc_{dc or '?'}"] += ha
                P[f"fc_{s.get('fc')}"] += ha
                if s.get("sg") in ("2", "3", "4", "5"):
                    P["turve_ha"] += ha
                if s.get("dr") in DRAINED:
                    P["ojitettu_ha"] += ha
                if s.get("restr"):
                    P["rajoitus_ha"] += ha
            if s.get("inv"):
                meta[kt]["inv"].append((s["inv"], ha))
            if s.get("calc"):
                meta[kt]["calc"].append((s["calc"], ha))
        matched += inside
        unmatched += max(0.0, ga - inside)
    log(f"Kuvioiden ala kunnan kiinteistöillä {matched / 1e4:.0f} ha, kiinteistöjen ulkopuolella {unmatched / 1e4:.0f} ha "
        f"({100 * unmatched / max(1, matched + unmatched):.1f} %), {time.time() - t0:.0f} s")

    fc_lab = C.get(("growthplacedata", "fertilityclass"), {})
    rows = []
    for kt, P in props.items():
        grp = kt[6:10]
        if grp == "0876" or grp.startswith("99"):  # yhteiset vesialueet, kaavan yleiset alueet
            continue
        if P["ala"] < MIN_HA:
            continue
        mm = P["metsamaa"]
        big = max(meta[kt]["palstat"], key=lambda g: g.area)
        pt = big.representative_point()
        lat, lon = tm35_to_latlon(pt.x, pt.y)
        fcs = {k[3:]: v for k, v in P.items() if k.startswith("fc_")}
        fc_main = max(fcs, key=fcs.get) if fcs else None
        vols = {g: P.get("vol_" + g, 0) for g in GROUP_NAME}
        main_sp = max(vols, key=vols.get) if P["vol"] > 0 else None
        inv = sorted(meta[kt]["inv"])
        r = {
            "Kiinteistötunnus": fmt_kt(kt),
            "Metsätila (metsämaata > 2 ha)": "kyllä" if mm > MIN_HA else "ei",
            "Kokonaisala ha": round(P["ala"], 2),
            "Palstoja": len(meta[kt]["palstat"]),
            "Metsämaa ha": round(mm, 2),
            "Kitu- ja joutomaa ha": round(P["kitujouto"], 2),
            "Muu ala ha": round(max(0.0, P["ala"] - mm - P["kitujouto"] - P["muu_kuvio"]), 2),
            "Metsätietoa % alasta": round(100 * (mm + P["kitujouto"] + P["muu_kuvio"]) / P["ala"]),
            "Puuston arvo €": round(P["arvo"]),
            "Puuston arvo €/ha (metsämaa)": round(P["arvo"] / mm) if mm > 0.1 else None,
            "Arvo hakkuutavan hinnoin €": round(P["arvo_hakkuutapa"]),
            "Puumäärä m³": round(P["vol"]),
            "Puumäärä m³/ha (metsämaa)": round(P["vol"] / mm) if mm > 0.1 else None,
            "Tukkipuu m³": round(P["saw"]),
            "Kuitupuu m³": round(P["pulp"]),
            "Mänty+havu m³": round(vols["manty"]),
            "Kuusi m³": round(vols["kuusi"]),
            "Koivu m³": round(vols["koivu"]),
            "Muu lehtipuu m³": round(vols["lehti"]),
            "Pääpuulaji": GROUP_NAME.get(main_sp, ""),
            "Keski-ikä v": round(P["ika_x_ha"] / P["ika_ha"]) if P["ika_ha"] > 0 else None,
        }
        for name, dcs in DEV_GROUPS:
            r[name] = round(100 * sum(P.get("dc_" + d, 0) for d in dcs) / mm) if mm > 0.1 else None
        r.update({
            "Kasvupaikka (yleisin)": fc_lab.get(fc_main, fc_main or ""),
            "Turvemaata %": round(100 * P["turve_ha"] / mm) if mm > 0.1 else None,
            "Ojitettu %": round(100 * P["ojitettu_ha"] / mm) if mm > 0.1 else None,
            "Hakkuurajoitus %": round(100 * P["rajoitus_ha"] / mm) if mm > 0.1 else None,
            "Inventointi vanhin": inv[0][0][:7] if inv else "",
            "Inventointi uusin": inv[-1][0][:7] if inv else "",
            "Rakennuksia (Ryhti)": allb.get(kt, 0),
            "Asuinrakennuksia (Ryhti)": resb.get(kt, 0),
            "Karttapaikka": (f"https://asiointi.maanmittauslaitos.fi/karttapaikka/?lang=fi&share=customMarker"
                             f"&n={round(pt.y)}&e={round(pt.x)}&title={fmt_kt(kt)}&desc=&zoom=9"),
            "Google Maps": f"https://www.google.com/maps/search/?api=1&query={lat:.6f},{lon:.6f}",
            "_kt": kt,
        })
        rows.append(r)
    rows.sort(key=lambda r: -r["Puuston arvo €"])
    log(f"Kiinteistöjä yli {MIN_HA} ha (ilman yhteisiä vesialueita ja kaava-alueita): {len(rows)}, joista metsämaata yli "
        f"{MIN_HA} ha: {sum(r['Metsätila (metsämaata > 2 ha)'] == 'kyllä' for r in rows)}, {time.time() - t0:.0f} s")

    summary = summarize(rows, latest, area, region, modified)
    for line in summary:
        log("  " + " | ".join(str(x) for x in line))
    sizes = tile_estimate(rows, meta, muni)
    write_outputs(muni, rows, summary, latest, ptable, months, area, C, sizes)
    log(f"Valmis {time.time() - t0:.0f} s")


DRAINED = {"3", "7", "8", "9"}  # Kuivatustilanne: ojitettu kangas, ojikko, muuttuma, turvekangas


def summarize(rows, latest, area, region, modified):
    def block(sel, title):
        n = len(sel)
        mm = sum(r["Metsämaa ha"] for r in sel)
        val = sum(r["Puuston arvo €"] for r in sel)
        vol = sum(r["Puumäärä m³"] for r in sel)
        perha = sorted(r["Puuston arvo €/ha (metsämaa)"] for r in sel if r["Puuston arvo €/ha (metsämaa)"] is not None)
        med = perha[len(perha) // 2] if perha else None
        cov = sorted(r["Metsätietoa % alasta"] for r in sel)
        low = sum(1 for c in cov if c < 50)
        return [
            (title, ""),
            ("Kiinteistöjä", n),
            ("Kokonaisala ha", round(sum(r["Kokonaisala ha"] for r in sel))),
            ("Metsämaa ha", round(mm)),
            ("Puumäärä m³", round(vol)),
            ("Puuston arvo € yhteensä", round(val)),
            ("Puuston arvo €/ha (metsämaa), mediaani", med),
            ("Metsätietoa alle 50 % alasta (kiinteistöjä)", low),
            ("Asuinrakennus tilalla (kiinteistöjä)", sum(1 for r in sel if r["Asuinrakennuksia (Ryhti)"] > 0)),
            ("", ""),
        ]
    forest = [r for r in rows if r["Metsätila (metsämaata > 2 ha)"] == "kyllä"]
    out = block(rows, "Määritelmä A: kokonaisala yli 2 ha") + block(forest, "Määritelmä B: metsämaata yli 2 ha")
    for lo, hi in ((2, 5), (5, 10), (10, 20), (20, 50), (50, 100), (100, 1e9)):
        n = sum(1 for r in forest if lo < r["Metsämaa ha"] <= hi)
        out.append((f"Metsätiloja, metsämaata {lo}–{hi if hi < 1e9 else ''} ha", n))
    out += [("", ""), ("Kantohintojen hinta-alue", f"{region} → Luken hinta-alue {area}"),
            ("Metsäkeskuksen aineisto päivitetty", modified)]
    return out


def tile_estimate(rows, meta, muni):
    """Tekee metsätiloista koekarttatiedostot (rajat lähellä, pisteet kaukaa) ja palauttaa koot."""
    forest = [r for r in rows if r["Metsätila (metsämaata > 2 ha)"] == "kyllä"]
    poly_path = os.path.join(OUT, "f.geojsonl")
    pt_path = os.path.join(OUT, "fp.geojsonl")
    nverts = 0
    with open(poly_path, "w") as fp, open(pt_path, "w") as fq:
        for r in forest:
            props = {"k": r["Kiinteistötunnus"], "ha": r["Metsämaa ha"], "e": r["Puuston arvo €"],
                     "eh": r["Puuston arvo €/ha (metsämaa)"], "v": r["Puumäärä m³"], "ps": r["Pääpuulaji"][:1],
                     "u": r["Uudistuskypsä (04) %"], "t": r["Taimikko %"], "kp": r["Kasvupaikka (yleisin)"][:12]}
            for g in meta[r["_kt"]]["palstat"]:
                g = g.simplify(1.0)
                polys = list(g.geoms) if hasattr(g, "geoms") else [g]
                coords = []
                for p in polys:
                    if p.geom_type != "Polygon":
                        continue
                    rings = [p.exterior, *p.interiors]
                    nverts += sum(len(x.coords) for x in rings)
                    coords.append([[list(reversed(tm35_to_latlon(x, y))) for x, y in ring.coords] for ring in rings])
                if coords:
                    fp.write(json.dumps({"type": "Feature", "properties": props,
                                         "geometry": {"type": "MultiPolygon", "coordinates": coords}}) + "\n")
            big = max(meta[r["_kt"]]["palstat"], key=lambda g: g.area).representative_point()
            lat, lon = tm35_to_latlon(big.x, big.y)
            fq.write(json.dumps({"type": "Feature", "properties": props,
                                 "geometry": {"type": "Point", "coordinates": [lon, lat]}}) + "\n")
    sizes = {"metsätiloja": len(forest), "kärkipisteitä (1 m yleistys)": nverts}
    for name, src, zmin, zmax in (("rajat z12–14", poly_path, 12, 14), ("rajat z10–14", poly_path, 10, 14),
                                  ("pisteet z6–11", pt_path, 6, 11)):
        out = os.path.join(OUT, f"koe_{zmin}_{zmax}_{os.path.basename(src)}.pmtiles")
        try:
            subprocess.run(["tippecanoe", "-o", out, "--force", "--quiet", f"-Z{zmin}", f"-z{zmax}", "-l", "f",
                            "--no-tile-size-limit", src], check=True)
            sizes[name + " Mt"] = round(os.path.getsize(out) / 1e6, 2)
        except Exception as e:  # noqa: BLE001
            sizes[name] = f"ei onnistunut: {e}"
    log(f"Karttatiedostokoe: {sizes}")
    return sizes


def write_outputs(muni, rows, summary, latest, ptable, months, area, C, sizes):
    import openpyxl
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    cols = [k for k in rows[0] if not k.startswith("_")] if rows else []
    csv_path = os.path.join(OUT, f"metsatilat_{muni}.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Metsätilat"
    ws.append(cols)
    for c in ws[1]:
        c.font = Font(bold=True)
    link_cols = {cols.index("Karttapaikka") + 1, cols.index("Google Maps") + 1}
    for r in rows:
        ws.append([r[c] for c in cols])
        for ci in link_cols:
            cell = ws.cell(row=ws.max_row, column=ci)
            cell.hyperlink = cell.value
            cell.value = "avaa"
            cell.font = Font(color="0563C1", underline="single")
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = ws.dimensions
    for i, c in enumerate(cols, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(9, min(22, len(c) + 2))

    s = wb.create_sheet("Yhteenveto")
    for line in summary:
        s.append(list(line))
    s.append([])
    s.append(["Karttatiedostokoe (vain metsätilat, tämä kunta)", ""])
    for k, v in sizes.items():
        s.append([k, v])
    s.column_dimensions["A"].width = 48
    s.column_dimensions["B"].width = 40

    p = wb.create_sheet("Kantohinnat")
    p.append(["Laskennassa käytetyt hinnat (viimeisin julkaistu kuukausi), €/m³, hinta-alue " + area])
    p.append(["Kauppatapa", "Puutavaralaji", "Hinta €/m³", "Kuukausi"])
    ptl_names = {v: f"{k[0].replace('manty', 'mänty')}{k[1]}" for k, v in ASSORT.items()}
    for (kaup, ptl), (price, m) in sorted(latest.items()):
        p.append([TRADES[kaup], ptl_names[ptl], price, m])
    p.append([])
    p.append(["Hinnat kuukausittain (tyhjä = ei julkaistu)"])
    p.append(["Kauppatapa", "Puutavaralaji", *months])
    for kaup in TRADES:
        for ptl in ASSORT.values():
            p.append([TRADES[kaup], ptl_names[ptl], *[ptable.get((kaup, ptl, m)) for m in months]])
    p.column_dimensions["A"].width = 28
    p.column_dimensions["B"].width = 16

    e = wb.create_sheet("Selitteet")
    for line in EXPLAIN:
        e.append([line])
    e.append([])
    for key, title in [(("growthplacedata", "fertilityclass"), "Kasvupaikka"),
                       (("treestand", "developmentclass"), "Kehitysluokka"),
                       (("growthplacedata", "drainagestate"), "Kuivatustilanne (ojitettu % = koodit " + ", ".join(sorted(DRAINED)) + ")"),
                       (("growthplacedata", "subgroup"), "Alaryhmä (turvemaa = korpi, räme, neva)"),
                       (("restriction", "cuttingrestriction"), "Hakkuun rajoitus")]:
        e.append([title + ":"])
        for code, lab in sorted(C.get(key, {}).items()):
            e.append([f"   {code} = {lab}"])
    e.column_dimensions["A"].width = 120
    xlsx = os.path.join(OUT, f"metsatilat_{muni}.xlsx")
    wb.save(xlsx)
    log(f"Kirjoitettu {xlsx} ja {csv_path}")


EXPLAIN = [
    "METSÄTILAKOE – laskennallinen, ei kauppahinta eikä arvio kiinteistön käyvästä arvosta.",
    "Rivit: kunnan kiinteistöt, joiden kokonaisala on yli 2 ha (yhteiset vesialueet 876 ja kaavan yleiset alueet 99xx pois).",
    "Sarake 'Metsätila' = metsämaata (Metsäkeskuksen kuvioiden pääryhmä metsämaa) yli 2 ha.",
    "Kokonaisala: kaikki kiinteistön palstat kunnan kiinteistörekisterikartassa (toisen kunnan puolella olevat palstat puuttuvat).",
    "Muu ala = kokonaisala − metsäkuvioiden ala (esim. pellot, pihat, tiet, vesi sekä alueet, joilta Metsäkeskuksella ei ole tietoa).",
    "Metsätietoa % alasta: pieni luku voi tarkoittaa peltoa, rakennettua aluetta tai aluetta, jota Metsäkeskuksen aineisto ei kata (esim. valtion maat).",
    "Puusto: Metsäkeskuksen laskema nykyhetken puusto (inventointi + kasvulaskenta), hehtaarikohtaiset luvut × kuvion ala kiinteistöllä.",
    "Puuston arvo € = tukkipuu × tukin kantohinta + kuitupuu × kuidun kantohinta puulajeittain (Luke, pystykauppa, viimeisin julkaistu kuukausi).",
    "Arvo hakkuutavan hinnoin: vertailu, jossa uudistuskypsät kuviot uudistushakkuun, varttuneet harvennushakkuun ja nuoret ensiharvennuksen hinnoin.",
    "Mänty ja muut havupuut männyn hinnoin, muut lehtipuut koivun hinnoin. Pikkutukki ja energiapuu eivät ole mukana.",
    "Kehitysluokat ja kasvupaikka: osuus metsämaan alasta. Keski-ikä: kuvioiden ikä painotettuna alalla.",
    "Inventointi vanhin/uusin: milloin kiinteistön kuvioiden puusto on inventoitu (vanha tieto on laskettu kasvumallilla nykyhetkeen).",
    "Tarkkuus (Metsäkeskus): kokonaistilavuus noin ±20 % noin 8/10 kuviolla; yksittäisen kuvion virhe voi olla suurempi.",
    "Hakkuurajoitus %: osuus metsämaasta, jolla Metsäkeskuksen aineistossa on hakkuun rajoitus (esim. suojelu); arvo on laskettu silti.",
    "Rakennuksia: Ryhtin kaikki rakennukset kiinteistöllä; asuinrakennukset samoin perustein kuin Talokartan talonäkymässä.",
    "Lähteet: Suomen metsäkeskus, metsävaratieto (CC BY 4.0); Maanmittauslaitos, kiinteistörekisterikartta (CC BY 4.0); "
    "Luonnonvarakeskus, teollisuuspuun kauppa (CC BY 4.0); SYKE Ryhti (CC BY 4.0).",
]
