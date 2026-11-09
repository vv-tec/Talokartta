# Talokartta

Kartta, jolla näkyvät asuinrakennukset ja niiden tiedot (valmistumisvuosi, pinta-alat, rakenteet, lämmitys, tontti,
kiinteistötunnus) suoraan avoimista rekistereistä. Tiedot päivittyvät automaattisesti joka yö.

- **Sivu:** https://vv-tec.github.io/Talokartta/
- **Käyttöohje omistajalle:** [KAYTTOOHJE.md](KAYTTOOHJE.md) – ilmoitukset, käsiajo, avaimet, maakuntien lisääminen
- **Kehittäjän muistio:** [CLAUDE.md](CLAUDE.md) – arkkitehtuuri, päätökset ja tiekartta

## Rakenne

```
Ryhti (SYKE) ───────┐                              ┌─> data/b-<maakunta>.pmtiles  (rakennukset)
                    ├─> pipeline/talot (Python) ───┼─> data/g.pmtiles             (tiheysruudut)
Maanmittauslaitos ──┘   joka yö GitHub Actionsissa └─> data/meta.json             (päivitysaika, määrät)
                                                              │
                                          web/ (sivu) ────────┴─> GitHub Pages

Metsäkeskus, MML, Luke ─> pipeline/metsa ─> vv-tec/Metsakartta (oma Pages) ─> web/metsa.js (metsätilanäkymä)
```

- `pipeline/talot/` hakee rakennukset ja osoitteet Ryhtistä (muutoshaulla) sekä kiinteistöpalstat Maanmittauslaitokselta,
  yhdistää ne ja tekee karttatiilet (`python -m pipeline.talot`).
- `pipeline/metsa/` laskee metsätilat; ajo ja julkaisu repositoriossa [vv-tec/Metsakartta](https://github.com/vv-tec/Metsakartta)
  (`python -m pipeline.metsa`). Talot ja metsätilat eivät riipu toisistaan; yhteiset osat ovat `pipeline/yhteiset/`:ssä
  ja asetukset `pipeline/config.py`:ssä. Kokeiluajot `pipeline/selvitykset/`.
- `web/` näyttää tiilet kartalla (MapLibre GL + PMTiles); metsätilanäkymä `web/metsa.js`.
- Testit: `python -m pipeline.selftest` (myös osien rajat) ja työnkulku **Testit** jokaisesta muutoksesta (myös sivu
  oikeassa selaimessa). `.github/workflows/build-deploy.yml` ajaa päivityksen joka yö, tarkistaa sivun ja julkaisee;
  epäonnistunut ajo ei julkaise ja avaa ilmoituksen.

## Lähteet ja lisenssit

- Rakennukset ja osoitteet: Suomen ympäristökeskus, Ryhti, CC BY 4.0
- Kiinteistöpalstat: Maanmittauslaitos, CC BY 4.0
- Metsätilat: Suomen metsäkeskus, Luonnonvarakeskus (CC BY 4.0)
- Taustakartta: OpenFreeMap, © OpenStreetMapin tekijät (ODbL)

Kartassa ei ole omistajatietoja.
