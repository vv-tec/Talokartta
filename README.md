# Talokartta

Kartta, jolla näkyvät asuinrakennukset ja niiden tiedot (valmistumisvuosi, pinta-alat, rakenteet, lämmitys, tontti,
kiinteistötunnus) suoraan avoimista rekistereistä. Tiedot päivittyvät automaattisesti joka yö.

- **Sivu:** https://vv-tec.github.io/Talokartta/
- **Käyttöohje omistajalle:** [KAYTTOOHJE.md](KAYTTOOHJE.md) – ilmoitukset, käsiajo, avaimet, maakuntien lisääminen
- **Kehittäjän muistio:** [CLAUDE.md](CLAUDE.md) – arkkitehtuuri, päätökset ja tiekartta

## Rakenne

```
Ryhti (SYKE) ───────┐                              ┌─> data/b-<maakunta>.pmtiles  (rakennukset)
                    ├─> pipeline/ (Python) ────────┼─> data/g.pmtiles             (tiheysruudut)
Maanmittauslaitos ──┘   joka yö GitHub Actionsissa └─> data/meta.json             (päivitysaika, määrät)
                                                              │
                                          web/ (sivu) ────────┴─> GitHub Pages
```

- `pipeline/` hakee rakennukset ja osoitteet Ryhtistä (muutoshaulla) sekä kiinteistöpalstat Maanmittauslaitokselta,
  yhdistää ne ja tekee karttatiilet. Pikatestit: `python -m pipeline.selftest`.
- `web/` näyttää tiilet kartalla (MapLibre GL + PMTiles).
- `.github/workflows/build-deploy.yml` ajaa päivityksen joka yö ja julkaisee sivun; epäonnistunut ajo ei julkaise ja avaa ilmoituksen.

## Lähteet ja lisenssit

- Rakennukset ja osoitteet: Suomen ympäristökeskus, Ryhti, CC BY 4.0
- Kiinteistöpalstat: Maanmittauslaitos, CC BY 4.0
- Taustakartta: OpenFreeMap, © OpenStreetMapin tekijät (ODbL)

Kartassa ei ole omistajatietoja.
