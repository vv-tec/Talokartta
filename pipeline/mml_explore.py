"""Selvitysajo: mitä Maanmittauslaitoksen tiedostopalvelu palauttaa kiinteistörekisterikartasta.

Käyttö: MML_API_KEY=... python -m pipeline.mml_explore 235
Tulostaa prosessien kuvaukset, työn tulokset ja ladattujen tiedostojen rakenteen. Ei muuta julkaistua sivua.
"""
import json
import os
import sys
import time
import zipfile

from .mml_files import MMLFiles, describe_gpkg

PROC = "kiinteistorekisterikartta_vektori_kunta"


def main():
    kunta = sys.argv[1] if len(sys.argv) > 1 else "235"
    fmt = sys.argv[2] if len(sys.argv) > 2 else "GPKG"
    m = MMLFiles()
    procs = m.get_json("/processes")
    ids = [p.get("id") for p in procs.get("processes", [])]
    print("Kiinteistöprosessit:", [i for i in ids if i and "kiinteisto" in i])
    desc = m.get_json(f"/processes/{PROC}")
    print("Prosessin kuvaus (inputs):")
    print(json.dumps(desc.get("inputs", desc), ensure_ascii=False, indent=1)[:4000])

    t0 = time.time()
    job = m.execute(PROC, {"municipalityInput": kunta, "fileFormatInput": fmt, "crsOutputInput": "EPSG:3067"})
    print("Työ:", job)
    m.wait(job)
    print(f"Valmis {time.time() - t0:.0f} s")
    res, files = m.results(job)
    print("Tulos:", json.dumps(res, ensure_ascii=False)[:3000])
    os.makedirs("mml_explore", exist_ok=True)
    for i, f in enumerate(files):
        url = f.get("path") or f.get("href")
        name = os.path.join("mml_explore", f"{i}_" + os.path.basename(url.split("?")[0]))
        m.download(url, name)
        print(f"Ladattu {name}: {os.path.getsize(name) / 1e6:.1f} Mt")
        paths = [name]
        if zipfile.is_zipfile(name):
            with zipfile.ZipFile(name) as z:
                z.extractall("mml_explore")
                paths = [os.path.join("mml_explore", n) for n in z.namelist()]
                print("  zip:", z.namelist())
        for p in paths:
            if p.lower().endswith(".gpkg"):
                print("GeoPackage", p)
                describe_gpkg(p)
            elif p.lower().endswith((".json", ".geojson")):
                with open(p, encoding="utf-8") as fh:
                    head = fh.read(3000)
                print("GeoJSON", p, head)


if __name__ == "__main__":
    main()
