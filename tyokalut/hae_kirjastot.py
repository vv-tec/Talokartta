"""Sivun kirjastot ja fontit omalle sivulle (tietosuoja 10.11.2026).

Ennen sivu latasi MapLibren ja PMTilesin unpkg-palvelusta ja fontit Googlelta, jolloin jokaisen kävijän IP-osoite
välittyi niille. Nyt ne tarjoillaan omalta sivulta kansiosta web/vendor/, eikä kävijän selain ota yhteyttä Googleen
eikä unpkg:hen. Ainoa ulkopuolinen palvelu on taustakartta (OpenFreeMap).

Ajetaan GitHubissa työnkulussa "Päivitä sivun kirjastot" (kirjastot.yml), joka tallentaa tuloksen repositorioon
(Clauden kone ei tavoita npm:ää). Lähde: npm-rekisteri; jokainen paketti tarkistetaan rekisterin sha512-tiivisteellä.
- Kirjaston versio vaihdetaan muuttamalla LIBRARIES-listaa (kansion nimessä versio → selaimet hakevat uuden).
  Muuta samalla web/index.html:n polut; pikatesti valvoo, että sivun viittaamat tiedostot ovat olemassa.
- Fonttipaketit (Fontsource, samat fontit kuin Google Fontsissa, OFL-lisenssi) lukitaan ensimmäisen haun versioon
  (web/vendor/versiot.json). Uusin versio: käsiajo valinnalla "päivitä fontit" (PAIVITA=1).
Tulos on toistettava: samat versiot → samat tiedostot (ei aikaleimoja), joten uusinta-ajo ei tee turhaa muutosta.
Käyttö: python tyokalut/hae_kirjastot.py
"""
import base64
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "vendor")
REGISTRY = "https://registry.npmjs.org/"

# (paketti, versio, {tiedosto paketissa: nimi kansiossa vendor/<paketti>-<versio>/})
LIBRARIES = [
    ("maplibre-gl", "4.7.1", {"dist/maplibre-gl.js": "maplibre-gl.js", "dist/maplibre-gl.css": "maplibre-gl.css"}),
    ("pmtiles", "3.2.0", {"dist/pmtiles.js": "pmtiles.js"}),
]
# (paketti, fontin nimi kuten style.css:ssä, painot). Vain latin + latin-ext (suomi, ruotsi, saame ym.).
FONTS = [
    ("@fontsource/familjen-grotesk", "Familjen Grotesk", [500, 600, 700]),
    ("@fontsource/source-sans-3", "Source Sans 3", [400, 600]),
    ("@fontsource/jetbrains-mono", "JetBrains Mono", [400, 500]),
]


def get(url, tries=4):
    for n in range(1, tries + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Talokartta-kirjastot (github.com/vv-tec/Talokartta)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001 – uusi yritys mistä tahansa verkkovirheestä
            if n == tries:
                raise SystemExit(f"::error title=Kirjastot::Lataus epäonnistui: {url} ({e})")
            time.sleep(5 * n)


def package(name, version):
    """npm-paketin tiedostot {polku: sisältö} (ilman package/-alkua), versio ja tiiviste. Tiiviste tarkistetaan."""
    info = json.loads(get(REGISTRY + urllib.parse.quote(name, safe="@") + "/" + version))
    integrity = info["dist"]["integrity"]
    algo, want = integrity.split("-", 1)
    if algo != "sha512":
        raise SystemExit(f"::error title=Kirjastot::{name}: odottamaton tiivistelaji {algo}")
    blob = get(info["dist"]["tarball"])
    if base64.b64encode(hashlib.sha512(blob).digest()).decode() != want:
        raise SystemExit(f"::error title=Kirjastot::{name}@{info['version']}: tiiviste ei täsmää rekisteriin")
    files = {}
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if m.isfile():
                files[m.name.split("/", 1)[1]] = tf.extractfile(m).read()
    return files, info["version"], integrity


def license_text(files):
    for p in sorted(files):
        if "/" not in p and re.match(r"(?i)licen[cs]e", p):
            return files[p]
    return None


def font_css(files, pkg, family, weight):
    """Fontsourcen <paino>.css → vain latin/latin-ext-osat, polut fontit/-kansioon, vain woff2. Palauttaa (css, tiedostot)."""
    css = files.get(f"{weight}.css")
    if css is None:
        raise SystemExit(f"::error title=Kirjastot::{pkg}: painoa {weight} ei löydy")
    out, used = [], []
    for block in re.findall(r"@font-face\s*\{[^}]*\}", css.decode("utf-8")):
        m = re.search(r"url\(\./files/([^)]+?-(latin|latin-ext)-\d+-normal\.woff2)\)", block)
        if not m:
            continue
        if f"'{family}'" not in block and f'"{family}"' not in block:
            raise SystemExit(f"::error title=Kirjastot::{pkg}: fontin nimi ei ole {family}")
        fn = m.group(1)
        if "files/" + fn not in files:
            raise SystemExit(f"::error title=Kirjastot::{pkg}: tiedosto {fn} puuttuu paketista")
        block = re.sub(r"src:[^;]*;", f"src: url(fontit/{fn}) format('woff2');", block)
        out.append(f"/* {fn[:-6]} */\n{block}")
        used.append(fn)
    if not any(re.search(r"-latin-\d+-normal\.woff2$", f) for f in used):
        raise SystemExit(f"::error title=Kirjastot::{pkg} {weight}: latin-merkistö puuttuu")
    return out, used


def main():
    prev = {}
    try:
        prev = json.load(open(os.path.join(OUT, "versiot.json"), encoding="utf-8")).get("fontit", {})
    except FileNotFoundError:
        pass
    update = os.environ.get("PAIVITA") == "1"
    tmp = OUT + ".uusi"
    shutil.rmtree(tmp, ignore_errors=True)
    os.makedirs(os.path.join(tmp, "fontit"))
    os.makedirs(os.path.join(tmp, "lisenssit"))
    manifest = {"kirjastot": {}, "fontit": {}}

    for name, version, wanted in LIBRARIES:
        files, ver, integ = package(name, version)
        d = os.path.join(tmp, f"{name}-{ver}")
        os.makedirs(d)
        for src, dst in wanted.items():
            if src not in files:
                raise SystemExit(f"::error title=Kirjastot::{name}@{ver}: {src} puuttuu paketista")
            open(os.path.join(d, dst), "wb").write(files[src])
        lic = license_text(files)
        if lic:
            open(os.path.join(tmp, "lisenssit", f"{name}.txt"), "wb").write(lic)
        manifest["kirjastot"][name] = {"versio": ver, "integrity": integ, "kansio": f"vendor/{name}-{ver}/"}
        print(f"{name} {ver}: {', '.join(wanted.values())}")

    css = ["/* Fontit omalta sivulta (Fontsource, SIL Open Font License; lisenssit/). Tehty: tyokalut/hae_kirjastot.py */"]
    for pkg, family, weights in FONTS:
        version = "latest" if update or pkg not in prev else prev[pkg]["versio"]
        files, ver, integ = package(pkg, version)
        n = 0
        for w in weights:
            blocks, used = font_css(files, pkg, family, w)
            css += blocks
            for fn in used:
                open(os.path.join(tmp, "fontit", fn), "wb").write(files["files/" + fn])
            n += len(used)
        lic = license_text(files)
        if lic:
            open(os.path.join(tmp, "lisenssit", pkg.split("/")[-1] + ".txt"), "wb").write(lic)
        manifest["fontit"][pkg] = {"versio": ver, "integrity": integ, "fontti": family, "painot": weights}
        print(f"{pkg} {ver}: {n} tiedostoa ({family} {weights})")
    open(os.path.join(tmp, "fontit.css"), "w", encoding="utf-8").write("\n\n".join(css) + "\n")
    json.dump(manifest, open(os.path.join(tmp, "versiot.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    shutil.rmtree(OUT, ignore_errors=True)
    os.rename(tmp, OUT)
    size = sum(os.path.getsize(os.path.join(p, f)) for p, _, fs in os.walk(OUT) for f in fs)
    print(f"Valmis: {OUT} ({size / 1e6:.1f} Mt)")


if __name__ == "__main__":
    sys.exit(main())
