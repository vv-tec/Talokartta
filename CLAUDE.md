# Talokartta – ohjeet kehittäjälle (Claude)

Omistaja ei ole ohjelmoija: Claude kirjoittaa kaiken koodin. Selitä muutokset suomeksi selkokielellä, tee pieniä
kokonaisuuksia ja kerro aina, miten omistaja voi itse todeta lopputuloksen (mitä avata, mitä pitäisi näkyä).

## Arkkitehtuuri

- `pipeline/` – Python 3.12, ainoa riippuvuus `requests`. Ajo: `python -m pipeline.build --out dist`.
  Pikatestit ilman verkkoa: `python -m pipeline.selftest` (pidä ajan tasalla, kun logiikka muuttuu).
  - `ryhti.py` – SYKE Ryhti OGC API Features: `open_building` (crs EPSG:3067), `open_address`, `open_address_deleted`.
    Suodatus CQL:llä `municipality_number='NNN'`; muutoshaku `modified_timestamp_utc > '…Z'` toimii (koko maassa ~7 000
    muuttunutta rakennusta/vrk). `properties`-parametri toimii osoitteille, rakennuksille se ohitetaan.
  - `ryhti_store.py` – rakennukset ja osoitteet tallessa (`cache/ryhti.json.gz`, vain asuinrakennukset kevennettyinä).
    Kunta haetaan kokonaan, jos puuttuu tai yli `RYHTI_FULL_DAYS` (30) pv vanha (1/30 kunnista per yö); muuten vain koko maan
    muutokset edellisen tallessa olevan muutoksen jälkeen (1 pv päällekkäisyys), ja uusille rakennuksille osoitteet erikseen.
    Rekisteristä kokonaan poistetut rakennukset siivoutuvat kunnan seuraavassa täydessä haussa. Täysi haku lokittaa erot
    tallessa olleeseen ("erot tallessa olleeseen: N uutta, N poistunutta, N muuttunutta") → muutoshaun luotettavuuden seuranta.
    Täysiä hakuja tehdään enintään `RYHTI_TIME_BUDGET_MIN` (60) min ajon alusta; loput seuraavalla ajolla (`store.missing`).
  - `mml.py` – MML INSPIRE WFS `cp:CadastralParcel`, bbox järjestyksessä E,N + `urn:ogc:def:crs:EPSG::3067`. Haku 2 km ruuduissa, täysi ruutu jaetaan neljään. Pinta-ala shoelace, piste-palsta ruutuindeksillä.
    WFS on nykyään vain varatapa (jos `MML_API_KEY` puuttuu).
  - `mml_files.py` – **ensisijainen palstalähde**: MML:n paikkatiedon tiedostopalvelu (OGC API Processes,
    `https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1`), prosessi `kiinteistorekisterikartta_vektori_kunta`,
    GPKG/EPSG:3067, yksi työ per kunta. API-avain GitHub-salaisuutena `MML_API_KEY` (Basic auth: avain käyttäjänä).
    GeoPackagessa taulu `PalstanSijaintitiedot` (geom, kiinteistotunnus 14 num.); kuntatiedostossa myös naapurikuntien rajapalstoja.
    Palstalla ei ole pysyvää tunnistetta → id = kiinteistötunnus + ensimmäinen piste. Geometria luetaan ilman kirjastoja (`gpkg_polys`).
    Kauniaisten tiedosto 3,9 Mt, työ ~40 s. Selvitysajo: työnkulku "Selvitys – MML-tiedostolataus" (`pipeline/mml_explore.py`).
  - Palstoista säilytetään vain rakennuskohtaiset tulokset kunnittain (`mml.ParcelResults`, `cache/parcel-results.json.gz`:
    {kunta: {date, res: {building_key: [pa, ka, pn]}}}), ei rajoja → muisti ja välimuisti pysyvät pieninä koko Suomellekin.
    Kunnan rekisteriin tullut uusi rakennus saa palstatiedot kunnan seuraavassa haussa (≤ 7 pv). WFS-varatapa säilyttää
    edelleen rajat ruuduittain (`mml.ParcelCache`, `cache/parcels.json.gz`). Vanha rajavälimuisti `parcels-mml.json.gz`
    muunnetaan tuloksiksi kerran (`build.migrate_parcel_cache`). Jokaisella erällä oma hakupäivä. Puuttuvat erät haetaan heti; yli 7 pv vanhat uudelleen vanhimmasta alkaen, enintään
    1/7 eristä per ajo (kuorma jakautuu viikon öille). Palstahaku lopetetaan hallitusti 150 min kohdalla
    (`PARCEL_TIME_BUDGET_MIN`) ja yksittäisen erän virhe ohitetaan; jos eriä puuttuu, haetut tallennetaan
    (välimuistin tallennus `if: always()`), ajo päättyy virheeseen eikä julkaise, ja seuraava ajo jatkaa.
  - Julkaisu maakunnittain: maakunta julkaistaan, kun sen kaikkien kuntien rakennukset (Ryhti) ja palstatulokset ovat valmiina;
    keskeneräinen (esim. uusi) maakunta odottaa, muut päivittyvät normaalisti. Palstat haetaan vain Ryhti-valmiille kunnille.
  - Turvatarkistus (`build.publish_problems`) vertaa julkaistun sivun meta.jsoniin (`config.SITE_URL`): julkaisu estetään,
    jos sivulla oleva maakunta putoaisi pois tai kunnan rakennusmäärä putoaa yli `DROP_PCT` 5 % (ja yli `DROP_MIN` 20).
    meta.json:ssa `muni_counts`. Ohitus: käsiajo valinnalla `ohita_tarkistukset` (env `SKIP_CHECKS`).
    `build.fail()` tulostaa `::error`-rivin, jonka `notify` poimii issueen kohtaan "Syy".
  - `build.py` – yhdistää, kirjoittaa GeoJSONSeq:n ja ajaa `tippecanoe` (taso kerrallaan, ilman ominaisuuskohtaisia zoomeja) → `dist/data/b-<maakunta>.pmtiles` (rakennukset, yksi tiedosto per `config.REGIONS`-alue) + `g.pmtiles` (tiheysruudut, tile-join) + `meta.json` (luettelo tiedostoista), kopioi `web/` → `dist/`. Ajo keskeytyy, jos jokin tiedosto > 95 Mt.
- `web/` – staattinen sivu, ei build-vaihetta. Lukee `meta.json`:n `regions`-listan ja lisää jokaiselle maakunnalle oman lähteen ja tason (`B_LAYERS`); suodattimet ja värit koskevat kaikkia. MapLibre GL 4.7.1 + pmtiles 3.2.0 unpkg-CDN:stä, taustakartta OpenFreeMap (positron/dark).
- `.github/workflows/build-deploy.yml` – yöllinen ajo + push + käsin; julkaisu GitHub Pagesiin. Epäonnistunut ajo ei julkaise.
  Jobi `notify`: epäonnistunut ajo avaa issuen (label `ajo-epäonnistui`, mainitsee omistajan) tai kommentoi avointa;
  onnistunut ajo sulkee sen. Käsiajon valinta `koe_virhe` pysäyttää ajon tarkoituksella ilmoituksen testaamiseksi.
  Välimuistin avain `parcels-<aikaleima>` tallennetaan joka ajossa (Ryhti-tila muuttuu joka yö).

## Tiilien sisältö

- Taso `b` (zoom 12–14, ylizoomaus ylöspäin): yksi piste per asuinrakennus. Lyhyet avaimet säästävät tilaa:
  `id` rakennustunnus, `k` kiinteistötunnus (834-404-3-64), `a` osoite(et) " / ", `pc` postinro, `po` postitoimipaikka,
  `p` tyyppi (01 vapaa-ajan, 05 pientalo, 06 kerrostalo), `s` käytössäolo (Ryhti-koodi), `d` valmistumispäivä, `y` vuosi,
  `g` kerrosala, `t` kokonaisala, `f` kerroksia, `n` asuntoja, `c` asuinrakennuksia samalla kiinteistöllä,
  `pa` palstan ala m², `ka` kiinteistön ala m², `pn` palstoja, `ex`/`ny` ETRS-TM35FIN,
  `m` runkomateriaali, `fa` julkisivu, `r` rakentamistapa, `h` lämmitystapa, `e` lämmitysenergia (Ryhti-koodit, "00" pois;
  selitteet `web/app.js` CATS, koodistot.suomi.fi), `v` tilavuus, `ha` huoneistoala, `sj` suojeltu 1/0.
  meta.json `by` = koodikenttien jakaumat (suodattimet näyttävät vain aineistossa esiintyvät arvot).
  Ryhtissä ei ole väriä eikä sähkö-/vesi-/viemäriliittymiä. Lupatiedot: kokoelma `avoimet_lupa_rakennukset`
  (suomenkieliset kentät, esim. `kuntanumero`, `toimenpiteen_laji`), ei vielä käytössä. Selvitysajo: "Selvitys – Ryhti-kentät".
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
2d. ✅ Pirkanmaa (22 kuntaa) 3.11.2026 ensimmäisenä maakuntana uudella pohjalla. Ensiajo 55 min: Ryhti täysi haku 22 kunnalle
    ~4 min, palstat ~48 min (Tampere 3,5 min, Sastamala 7 min). Yhteensä 703 668 rakennusta (Pirkanmaa 168 993), palsta
    703 661:lle. Tiilet: Pirkanmaa 37 Mt, Uusimaa 58, Varsinais-Suomi 39, Kanta-Häme 16, g 0,8 Mt.
    Arvio: noin 20–25 kuntaa (tai 1–2 keskikokoista maakuntaa) mahtuu yhteen ajoon palstojen 150 min aikarajaan.
2e. ✅ Päijät-Häme (10 kuntaa, Iitti mukana) 3.11.2026: ensiajo 27 min (Ryhti 3 min, palstat 21 min), 76 110 rakennusta,
    tiilet 17 Mt. Yhteensä 779 778 rakennusta (96 kuntaa), palsta 779 771:lle.
2f. Satakunta (16 kuntaa) lisätty 3.11.2026.
2. Koko Suomi. Rekisterien kuormitus pidetään pienenä (omistajan toive):
   - Ryhti: ✅ muutoshaku ja tallennettu tila (`ryhti_store.py`, 3.11.2026). Koko maan ensimmäinen haku voi kestää
     tunteja → lisää maakunnat erissä tai lisää Ryhti-haulle aikaraja kuten palstoille.
   - Palstat: ✅ talteen vain tulokset (3.11.2026).
     Mitattu 3.11.2026 (64 kuntaa): ensimmäinen ajo (Ryhti kokonaan + rajojen muunnos) ~24 min; muutoshaulla koko build
     ~2,5 min (Ryhti-muutokset ~15 s, yhdistäminen ~45 s, tiilet ~45 s). 534 675 rakennusta, palsta 534 668:lle (sama 7 puuttuu).
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
3. ✅ Ilmoitus omistajalle, jos yöajo epäonnistuu (3.11.2026, GitHub-issue + sähköposti).
4. Oma verkko-osoite.
5. Osoitehaku, mobiilihionta, tietosuojaseloste.
