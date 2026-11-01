# Talokartta

Kartta, jolla näkyvät asuinrakennukset ja niiden tiedot (valmistumisvuosi, pinta-alat, tontti, kiinteistötunnus) suoraan avoimista rekistereistä. Tiedot päivittyvät automaattisesti joka yö.

**Nykyinen vaihe:** Tammelan kunta (vaihe 1). Koko Suomi tulee vaiheessa 2.

## Miten tämä toimii

```
Ryhti (SYKE) ──┐                         ┌─> data/talot.pmtiles  (karttatiilet)
               ├─> pipeline/ (Python) ───┤
MML palstat ───┘    joka yö GitHubissa   └─> data/meta.json      (päivitysaika, määrät)
                                                    │
                                    web/ (sivu) ────┴─> GitHub Pages -julkaisu
```

1. **Data-ajo** (`pipeline/`) hakee rakennukset ja osoitteet Ryhdistä sekä kiinteistöpalstat Maanmittauslaitokselta, laskee palstojen pinta-alat ja tekee niistä karttatiilet.
2. **Verkkosivu** (`web/`) näyttää tiilet kartalla. Kaukaa katsottuna näkyy rakennusten tiheys, lähempää (zoom 12+) yksittäiset rakennukset, joita voi suodattaa.
3. **GitHub Actions** (`.github/workflows/build-deploy.yml`) ajaa data-ajon joka yö ja aina kun koodi muuttuu, ja julkaisee sivun GitHub Pagesiin. Jos ajo epäonnistuu, edellinen versio jää näkyviin.

## Käyttöönotto (tehdään kerran)

1. GitHubissa: repositorion **Settings → Pages → Build and deployment → Source: GitHub Actions**.
2. **Actions**-välilehti → *Päivitä tiedot ja julkaise* → **Run workflow**.
3. Kun ajo on vihreä, sivu löytyy osoitteesta `https://<käyttäjätunnus>.github.io/<repositorio>/`.

## Tietojen päivitys käsin

Actions → *Päivitä tiedot ja julkaise* → Run workflow.

## Lähteet ja lisenssit

- Rakennukset ja osoitteet: Suomen ympäristökeskus, Ryhti – rakennetun ympäristön tietojärjestelmä, CC BY 4.0
- Kiinteistöpalstat: Maanmittauslaitos, INSPIRE-kiinteistöpalstat, CC BY 4.0
- Taustakartta: OpenFreeMap, © OpenStreetMapin tekijät (ODbL)

Kartassa ei ole omistajatietoja.
