# Talokartta – ohjeet kehittäjälle (Claude)

Omistaja ei ole ohjelmoija: Claude kirjoittaa kaiken koodin. Selitä muutokset suomeksi selkokielellä, tee pieniä
kokonaisuuksia ja kerro aina, miten omistaja voi itse todeta lopputuloksen (mitä avata, mitä pitäisi näkyä).

## Arkkitehtuuri

- `pipeline/` – Python 3.12, ainoa riippuvuus `requests`. Ajo: `python -m pipeline.build --out dist`.
  Pikatestit ilman verkkoa: `python -m pipeline.selftest` (pidä ajan tasalla, kun logiikka muuttuu).
  - `ryhti.py` – SYKE Ryhti OGC API Features: `open_building` (crs EPSG:3067), `open_address`. Suodatus CQL:llä `municipality_number='NNN'`.
  - `mml.py` – MML INSPIRE WFS `cp:CadastralParcel`, bbox järjestyksessä E,N + `urn:ogc:def:crs:EPSG::3067`. Haku 2 km ruuduissa, täysi ruutu jaetaan neljään. Pinta-ala shoelace, piste-palsta ruutuindeksillä.
    Palstat säilytetään ruuduittain välimuistissa (`cache/parcels.json.gz`, GitHub Actions cache) ja haetaan uudelleen 7 päivän välein; puuttuvat ruudut haetaan heti.
  - `build.py` – yhdistää, kirjoittaa GeoJSONSeq:n ja ajaa `tippecanoe` (taso kerrallaan, ilman ominaisuuskohtaisia zoomeja) + `tile-join` → `dist/data/talot.pmtiles` + `meta.json`, kopioi `web/` → `dist/`.
- `web/` – staattinen sivu, ei build-vaihetta. MapLibre GL 4.7.1 + pmtiles 3.2.0 unpkg-CDN:stä, taustakartta OpenFreeMap (positron/dark).
- `.github/workflows/build-deploy.yml` – yöllinen ajo + push + käsin; julkaisu GitHub Pagesiin. Epäonnistunut ajo ei julkaise.

## Tiilien sisältö

- Taso `b` (zoom 12–14, ylizoomaus ylöspäin): yksi piste per asuinrakennus. Lyhyet avaimet säästävät tilaa:
  `id` rakennustunnus, `k` kiinteistötunnus (834-404-3-64), `a` osoite(et) " / ", `pc` postinro, `po` postitoimipaikka,
  `p` tyyppi (01 vapaa-ajan, 05 pientalo, 06 kerrostalo), `s` käytössäolo (Ryhti-koodi), `d` valmistumispäivä, `y` vuosi,
  `g` kerrosala, `t` kokonaisala, `f` kerroksia, `n` asuntoja, `c` asuinrakennuksia samalla kiinteistöllä,
  `pa` palstan ala m², `ka` kiinteistön ala m², `pn` palstoja, `ex`/`ny` ETRS-TM35FIN.
  Puuttuvat arvot jätetään pois (suodattimet käyttävät `has`).
- Taso `g` (zoom 0–11): tiheysruudut 5 km (z0–8) ja 1 km (z9–11), ominaisuus `n` = rakennusten määrä.

## Päätökset

- Ei omaa palvelinta eikä tietokantaa: kaikki on staattisia tiedostoja → halpa, nopea, skaalautuu.
- Tiedot päivitetään yöllä eräajona, ei reaaliajassa käyttäjän pyynnöstä (rekisterirajapinnat ovat hitaita).
- Mukana vain asuinrakennukset (01, 05, 06); purettu/tuhoutunut (06, 07, 08) ja purkupäivälliset jätetään pois.
- Omistajatietoja ei käsitellä eikä näytetä.
- Lähdemaininnat (CC BY 4.0) ja päivitysaika näkyvät sivulla.

## Tiekartta

1. ✅ Tammela uudella rakenteella (karttatiilet, taustakartta, zoomausraja, yöllinen päivitys).
2a. (käynnissä) Kanta-Häme (11 kuntaa, `config.MUNICIPALITIES`) välivaiheena: palstojen viikkovälimuisti WFS:lle.
2. Koko Suomi. Rekisterien kuormitus pidetään pienenä (omistajan toive):
   - Ryhti: koko maa haetaan kerran, sen jälkeen öisin vain muuttuneet rakennukset ja osoitteet
     (`modified_timestamp_utc` > edellisen ajon aika). Edellinen tila tallennetaan ajojen välillä
     (esim. GitHub Releasen liitteenä tai Actions-välimuistissa). Täysi uudelleenhaku harvoin varmistukseksi, esim. kuukausittain.
   - MML: palstat koko maasta yhtenä tiedostolatauksena (kiinteistörekisterikartta, GeoPackage) WFS-ruutuhakujen sijaan,
     kerran viikossa riittää. Selvitä, vaatiiko tiedostopalvelu ilmaisen API-avaimen (→ GitHub Secret).
   - Haut peräkkäin, ei rinnakkain; uudelleenyritykset viiveellä; User-Agent tunnistaa projektin.
   - Varasuunnitelma, jos muutoshaku ei toimi luotettavasti: haetaan öisin vain osa kunnista kiertävästi.
   - GitHub Pagesin tiedostoraja 100 Mt → tiilet Cloudflare R2:een, jos kasvavat yli.
3. Ilmoitus omistajalle, jos yöajo epäonnistuu.
4. Oma verkko-osoite.
5. Osoitehaku, mobiilihionta, tietosuojaseloste.
