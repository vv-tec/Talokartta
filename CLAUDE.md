# Talokartta – ohjeet kehittäjälle (Claude)

Omistaja ei ole ohjelmoija: Claude kirjoittaa kaiken koodin. Selitä muutokset suomeksi selkokielellä, tee pieniä
kokonaisuuksia ja kerro aina, miten omistaja voi itse todeta lopputuloksen (mitä avata, mitä pitäisi näkyä).

## Arkkitehtuuri

- `pipeline/` – Python 3.12, ainoa riippuvuus `requests`. Ajo: `python -m pipeline.build --out dist`.
  Pikatestit ilman verkkoa: `python -m pipeline.selftest` (pidä ajan tasalla, kun logiikka muuttuu).
  - `ryhti.py` – SYKE Ryhti OGC API Features: `open_building` (crs EPSG:3067), `open_address`. Suodatus CQL:llä `municipality_number='NNN'`.
  - `mml.py` – MML INSPIRE WFS `cp:CadastralParcel`, bbox järjestyksessä E,N + `urn:ogc:def:crs:EPSG::3067`. Haku 2 km ruuduissa, täysi ruutu jaetaan neljään. Pinta-ala shoelace, piste-palsta ruutuindeksillä.
    WFS on nykyään vain varatapa (jos `MML_API_KEY` puuttuu).
  - `mml_files.py` – **ensisijainen palstalähde**: MML:n paikkatiedon tiedostopalvelu (OGC API Processes,
    `https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1`), prosessi `kiinteistorekisterikartta_vektori_kunta`,
    GPKG/EPSG:3067, yksi työ per kunta. API-avain GitHub-salaisuutena `MML_API_KEY` (Basic auth: avain käyttäjänä).
    GeoPackagessa taulu `PalstanSijaintitiedot` (geom, kiinteistotunnus 14 num.); kuntatiedostossa myös naapurikuntien rajapalstoja.
    Palstalla ei ole pysyvää tunnistetta → id = kiinteistötunnus + ensimmäinen piste. Geometria luetaan ilman kirjastoja (`gpkg_polys`).
    Kauniaisten tiedosto 3,9 Mt, työ ~40 s. Selvitysajo: työnkulku "Selvitys – MML-tiedostolataus" (`pipeline/mml_explore.py`).
  - Palstat säilytetään erittäin (kunta tai WFS-ruutu) välimuistissa (`cache/parcels-mml.json.gz`, GitHub Actions cache),
    jokaisella erällä oma hakupäivä. Puuttuvat erät haetaan heti; yli 7 pv vanhat uudelleen vanhimmasta alkaen, enintään
    1/7 eristä per ajo (kuorma jakautuu viikon öille). Palstahaku lopetetaan hallitusti 150 min kohdalla
    (`PARCEL_TIME_BUDGET_MIN`) ja yksittäisen erän virhe ohitetaan; jos eriä puuttuu, haetut tallennetaan
    (välimuistin tallennus `if: always()`), ajo päättyy virheeseen eikä julkaise, ja seuraava ajo jatkaa.
  - `build.py` – yhdistää, kirjoittaa GeoJSONSeq:n ja ajaa `tippecanoe` (taso kerrallaan, ilman ominaisuuskohtaisia zoomeja) → `dist/data/b-<maakunta>.pmtiles` (rakennukset, yksi tiedosto per `config.REGIONS`-alue) + `g.pmtiles` (tiheysruudut, tile-join) + `meta.json` (luettelo tiedostoista), kopioi `web/` → `dist/`. Ajo keskeytyy, jos jokin tiedosto > 95 Mt.
- `web/` – staattinen sivu, ei build-vaihetta. Lukee `meta.json`:n `regions`-listan ja lisää jokaiselle maakunnalle oman lähteen ja tason (`B_LAYERS`); suodattimet ja värit koskevat kaikkia. MapLibre GL 4.7.1 + pmtiles 3.2.0 unpkg-CDN:stä, taustakartta OpenFreeMap (positron/dark).
- `.github/workflows/build-deploy.yml` – yöllinen ajo + push + käsin; julkaisu GitHub Pagesiin. Epäonnistunut ajo ei julkaise.

## Tiilien sisältö

- Taso `b` (zoom 12–14, ylizoomaus ylöspäin): yksi piste per asuinrakennus. Lyhyet avaimet säästävät tilaa:
  `id` rakennustunnus, `k` kiinteistötunnus (834-404-3-64), `a` osoite(et) " / ", `pc` postinro, `po` postitoimipaikka,
  `p` tyyppi (01 vapaa-ajan, 05 pientalo, 06 kerrostalo), `s` käytössäolo (Ryhti-koodi), `d` valmistumispäivä, `y` vuosi,
  `g` kerrosala, `t` kokonaisala, `f` kerroksia, `n` asuntoja, `c` asuinrakennuksia samalla kiinteistöllä,
  `pa` palstan ala m², `ka` kiinteistön ala m², `pn` palstoja, `ex`/`ny` ETRS-TM35FIN.
  Puuttuvat arvot jätetään pois (suodattimet käyttävät `has`).
- Taso `g` (zoom 0–11): tiheysruudut 5 km (z0–9) ja 1 km (z10–11), ominaisuus `n` = rakennusten määrä.

## Päätökset

- Ei omaa palvelinta eikä tietokantaa: kaikki on staattisia tiedostoja → halpa, nopea, skaalautuu.
- Tiedot päivitetään yöllä eräajona, ei reaaliajassa käyttäjän pyynnöstä (rekisterirajapinnat ovat hitaita).
- Mukana vain asuinrakennukset (01, 05, 06); purettu/tuhoutunut (06, 07, 08) ja purkupäivälliset jätetään pois.
- Omistajatietoja ei käsitellä eikä näytetä.
- Lähdemaininnat (CC BY 4.0) ja päivitysaika näkyvät sivulla.

## Tiekartta

1. ✅ Tammela uudella rakenteella (karttatiilet, taustakartta, zoomausraja, yöllinen päivitys).
2a. ✅ Kanta-Häme (11 kuntaa, `config.MUNICIPALITIES`) välivaiheena: palstojen viikkovälimuisti WFS:lle. 72 948 rakennusta, ensiajo ~15 min, välimuistilla ~4 min, tiilet 14 Mt.
2b. ✅ Uusimaa (26 kuntaa) lisätty `config.REGIONS`-rakenteeseen samalla WFS-välimuistimallilla. Yhteensä 361 423 rakennusta,
    ~593 000 palstaa, ensiajo ~34 min, tiilet 65 Mt. Tiilet jaettu maakunnittain (✅ 2.11.2026), joten uusi maakunta mahtuu.
    GitHub Pagesin koko sivuston raja on 1 Gt: koko Suomi (~300–400 Mt) mahtuu, mutta seuraa kokoa.
2c. ✅ Varsinais-Suomi (27 kuntaa). Yhteensä 534 667 rakennusta, ~906 000 palstaa, 10 398 palstaruutua; ensiajo ~36 min.
    Tiilet: Kanta-Häme 14 Mt, Uusimaa 51 Mt, Varsinais-Suomi 34 Mt. Palstojen viikoittainen täysi uudelleenhaku on nyt
    ~10 000 WFS-pyyntöä (~1 h) → korvattu MML-tiedostolatauksella (✅ 2.11.2026): 64 kuntaa, 817 019 palstaa,
    palsta löytyi 534 660 / 534 667 rakennukselle. Ensilataus ~1 h 55 min (isot kunnat 4–8 min), koko ajo ~2 h 30 min;
    välimuistilla ajo ~24 min (Ryhti ~15 min, yhdistäminen ~7 min). Välimuisti ~262 Mt.
    "Cache save failed" ajossa, jossa mitään ei haettu, on odotettu (sama avain on jo tallessa).
2. Koko Suomi. Rekisterien kuormitus pidetään pienenä (omistajan toive):
   - Ryhti: koko maa haetaan kerran, sen jälkeen öisin vain muuttuneet rakennukset ja osoitteet
     (`modified_timestamp_utc` > edellisen ajon aika). Edellinen tila tallennetaan ajojen välillä
     (esim. GitHub Releasen liitteenä tai Actions-välimuistissa). Täysi uudelleenhaku harvoin varmistukseksi, esim. kuukausittain.
   - MML: ✅ tiedostopalvelu käytössä kunnittain (API-avain on GitHub-salaisuutena). Koeajo 2.11.2026
     `kiinteistorekisterikartta_vektori_koko_suomi` (GPKG): työ valmis 10 s:ssa (valmiiksi koottu tiedosto), mutta tiedosto
     13,3 Gt ja lataus ~2 h (~1,9 Mt/s). Sisältö: PalstanSijaintitiedot 3 766 278 palstaa, KiinteistotunnuksenSijaintitiedot
     3 766 278, KiinteistorajanSijaintitiedot 20,6 milj. rajaviivaa. Ajokoneen levyllä tilaa ~74 Gt → mahtuu.
     Koko maalle: palstoja ei voi pitää kaikkia Pythonin muistissa/JSON-välimuistissa → hae rakennuspisteittäin
     GPKG:n R-puuindeksistä (sqlite rtree) tai suodata vain rakennuksia sisältävät palstat. Tuloksessa on myös `zipPath`
     (selvitä, onko pakattu lataus pienempi/nopeampi). Kunnittainen lataus on todennäköisesti yhtä hidas per megatavu.
   - Haut peräkkäin, ei rinnakkain; uudelleenyritykset viiveellä; User-Agent tunnistaa projektin.
   - Varasuunnitelma, jos muutoshaku ei toimi luotettavasti: haetaan öisin vain osa kunnista kiertävästi.
   - GitHub Pagesin tiedostoraja 100 Mt → tiilet Cloudflare R2:een, jos kasvavat yli.
3. Ilmoitus omistajalle, jos yöajo epäonnistuu.
4. Oma verkko-osoite.
5. Osoitehaku, mobiilihionta, tietosuojaseloste.
