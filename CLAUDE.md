# Talokartta – ohjeet kehittäjälle (Claude)

Omistaja ei ole ohjelmoija: Claude kirjoittaa kaiken koodin. Selitä muutokset suomeksi selkokielellä, tee pieniä
kokonaisuuksia ja kerro aina, miten omistaja voi itse todeta lopputuloksen (mitä avata, mitä pitäisi näkyä).
Omistajan käyttöohje on `KAYTTOOHJE.md` (ilmoitukset, käsiajo, avaimet, maakuntien lisääminen, kulut). **Päivitä se aina,
kun toiminta, asetukset, ilmoitukset tai maakunnat muuttuvat** (myös "Päivitetty viimeksi" ja luvut).

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
    Kunnan tiedosto haetaan uudelleen `PARCEL_MAX_AGE_DAYS` (14) pv välein (1/14 kunnista per yö; rajat muuttuvat harvoin).
    Uusi rakennus (ei tulosta) saa palstatiedon heti samassa ajossa pienellä aluehaulla `ParcelResults.fill_new`
    (INSPIRE WFS `_fetch_box`, lähekkäiset rakennukset 500 m ruuduittain yhteen pyyntöön, enintään
    `NEW_BUILDINGS_MAX_PER_RUN` 500/ajo; jos palstaa ei löydy, uusi yritys 7 pv päästä, kirjanpito `tried`).
    Aluehaun kiinteistön ala voi jäädä vajaaksi, jos kiinteistön muut palstat ovat kaukana; tarkentuu täydessä haussa (≤ 14 pv). WFS-varatapa säilyttää
    edelleen rajat ruuduittain (`mml.ParcelCache`, `cache/parcels.json.gz`). Vanha rajavälimuisti `parcels-mml.json.gz`
    muunnetaan tuloksiksi kerran (`build.migrate_parcel_cache`). Jokaisella erällä oma hakupäivä. Puuttuvat erät haetaan heti; vanhentuneet uudelleen vanhimmasta alkaen
    (kuorma jakautuu tasaisesti öille; WFS-varatavalla edelleen 1/7 per ajo). Palstahaku lopetetaan hallitusti 150 min kohdalla
    (`PARCEL_TIME_BUDGET_MIN`) ja yksittäisen erän virhe ohitetaan; jos eriä puuttuu, haetut tallennetaan
    (välimuistin tallennus `if: always()`), ajo päättyy virheeseen eikä julkaise, ja seuraava ajo jatkaa.
  - **Rantatieto (irrotettava lisäosa)** – `pipeline/shore.py`, `pipeline/requirements-shore.txt` (Shapely ~=2.1),
    `config.SHORE_REGIONS` (maakunnat; **tyhjä lista = pois päältä**: build ei tuo shore-moduulia eikä Shapelya, tiiliin ei
    tule ra-kenttiä, `meta.shore_regions` on tyhjä ja sivu piilottaa Ranta-osiot). Kytkentä vain kahdessa kohdassa:
    `ParcelResults.on_parcels`-koukku (lasketaan aina, kun kunnan palstat ladataan, samoista palstoista) ja
    `make_records(..., shore_res)`. Tulokset `cache/shore-results.json.gz` (`shore.ShoreResults`, kunnittain
    {building_key: [ra, rl, rd, rw, rwa]}). Käyttöönotto/uusi maakunta: kunnat, joilta tulos puuttuu, haetaan heti
    (`ParcelResults.get(force=…)`); muuten päivittyy 14 pv palstakierroksessa. Vesialueet MTK:sta kunnan rakennusten
    bbox + 2 km (`municipality_water`). Uusi rakennus saa rantatiedon kunnan seuraavassa palstahaussa (≤ 14 pv; fill_new ei laske rantaa).
    Lisäosan virhe ei kaada palstatietoja (lokiin "lisälaskenta epäonnistui").
    **Puron varrella POIS KÄYTÖSTÄ 5.11.2026** (`shore.STREAMS_ENABLED = False`): omistajan pistokoe Tammelassa 18 kohdetta
    (6 × 36312, 6 × mutkainen 36311, 6 × suora 36311) → kaikki ojia, myös 2–5 m ("suuri oja" 5/6). MTK ei erota puroa ojasta.
    Pois päältä: uomia ei haeta, ei upgradea, `make_records` muuntaa vanhat ra 5 → 0 (rl pois; päivittyvät 14 pv kierroksessa),
    meta `streams` false → sivu piilottaa luokan. Palautus: True + VERSION 3. Alla alkuperäinen toteutus:
    Puron varrella (ra 5, 4.11.2026): MTK `virtavesikapea` (viivat) haetaan samassa vesialuehaussa; vain jos palsta ei ole
    rannassa eikä kiinteistöllä ole erillistä rantapalstaa; puroa ≥ `MIN_STREAM_M` 10 m palstalla tai ≤ `TOL_STREAM` 5 m
    rajasta. Oletuksena vain kohdeluokka 36312 (2–5 m); 36311 (alle 2 m) sisältää ojat → pois, ehdokkaana mutkaisuus
    ≥ 1,1 ja ≥ 100 m (`NARROW_MIN_SINUOSITY`, odottaa omistajan pistokoetta). Laskennan versio `shore.VERSION` (2)
    tallessa kunnittain; vanhemmat kunnat päivitetään `ParcelResults.get(upgrade=…)`: vain yön normaalin kiintiön
    (ceil(N/14)) vapaisiin paikkoihin puuttuvien ja vanhentuneiden jälkeen → ei lisäkuormaa. meta `stream_regions` =
    maakunnat, joissa kaikki kunnat ovat versiossa ≥ 2 (sivu kertoo keskeneräiset). Web: `app.js` RANTA-lohkot (SHORE_*,
    shoreCard, buildShore) ja `index.html` `#shoreSec`. Kokonaan poisto: nämä + `shore.py`, `requirements-shore.txt`,
    workflow-asennusrivi ja selftestin `shore_tests`. Koe-työnkulku "Selvitys – rantatesti" (`shore_explore.py`) erikseen.
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
  `ra` ranta (0 ei, 1 ei – toinen kiinteistö välissä, 2 ranta, 3 ranta (vesijättö), 4 erillinen rantapalsta,
  5 puron varrella – pois käytöstä 5.11.2026; puuttuu = ei laskettu), `rl` rantaviiva m (ra 5: puroa palstalla m), `rd` etäisyys vedestä m, `rw` vesilaji (j/m/v), `rwa` lähimmän vesialueen ala ha (vain SHORE_REGIONS),
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
2f. ✅ Satakunta (16 kuntaa) 3.11.2026: ensiajo 33 min (Ryhti 4 min, palstat 26 min), 96 626 rakennusta, tiilet 21 Mt.
    Yhteensä 876 404 rakennusta (112 kuntaa, 6 maakuntaa), palsta 876 397:lle; tiilet yhteensä ~190 Mt.
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
   - Mitoitusarvio 5.11.2026 (9 maakuntaa, 150 kuntaa, 1,12 milj. rak., ~70 % väestöstä): koko Suomi ~1,85–1,95 milj.
     (Tilastokeskus: kesämökkejä 495 145 v. 2024, eniten Kuopio ja Mikkeli). Tiilet ~240 t/rak → ~450–480 Mt / 1 Gt;
     suurin tiedosto Uusimaa 62,5 Mt (muut ≤ ~45 Mt). Yöajo nyt 11 kuntaa/yö ~36 min → koko maa ceil(308/14) = 22
     kuntaa/yö ~60–75 min (raja 150 min; tarvittaessa PARCEL_MAX_AGE_DAYS 21). Välimuisti 176 Mt → ~330 Mt / 10 Gt.
     Muisti mitattu 5.11.2026: 4,9 Gt / 1,21 milj. rak. → koko Suomi ~7,5–8 Gt (ajokone 16 Gt); build lokittaa "Muistin huippu". Todellinen raja on Pagesin kaistan
     pehmeä raja 100 Gt/kk (käyttäjämäärä) → R2, jos liikenne kasvaa. Ahvenanmaa ei ole Ryhtissä.
2x. ✅ Rantatieto – käytössä kaikissa 6 maakunnassa 4.11.2026 (`config.SHORE_REGIONS`), otettu käyttöön paketeittain
    omistajan pyynnöstä. Uusi maakunta: lisätään oletuksena myös SHORE_REGIONSiin samassa muutoksessa (palstat ladataan
    joka tapauksessa; KAYTTOOHJE kohta 6), ellei omistaja toisin pyydä. Alla mittaukset sekä koe- ja suunnitteluhistoria.
    Paketti 1 Pirkanmaa + Päijät-Häme (32 kuntaa): 77 min, raskain Tampere 58 s; ranta 49 526 / 168 991 ja
    22 412 / 76 110; tiilet 37 → 40,5 Mt ja 17 → 18,9 Mt.
    Paketti 2 Satakunta + Uusimaa (42 kuntaa): 1 h 58 min (lähellä 150 min palstarajaa → enintään ~40 kuntaa/ajo
    pakotettuna), raskaimmat Helsinki 132 s, Espoo 121 s, Pori 98 s; ranta 20 491 / 96 626 ja 38 476 / 288 487;
    tiilet 21,3 → 23,2 Mt ja 58,2 → 62,5 Mt.
    Paketti 3 Varsinais-Suomi (27 kuntaa): 1 h 34 min, Parainen 273 s, Turku 114 s; ranta 47 662 / 173 260; tiili 38,7 → 42,0 Mt.
    Yhteensä omalla rannalla (ra 2–3) 195 891 / 876 423 (22 %); tiilet ~206 Mt. Yhtään "lisälaskenta epäonnistui" ei tullut.
    Jatkuva kuorma: ~8 kuntaa/yö × ~30 s ≈ 4 min lisää yöajoon; vesialuehaut ~8 kuntaa/yö.
    Kanta-Häme 4.11.2026: käyttöönottoajo 31 min (palstojen uudelleenlataus 11 kuntaa ~25 min, rantalaskenta yht. ~5 min,
    Hämeenlinna 126 s); omalla rannalla (ra 2–3) 17 324 / 72 949 asuinrakennusta; tiili 16,1 → 17,5 Mt (+9 %).
    Selftestin rantatestit ajetaan CI:ssä (Shapely asennettu).
    Koe: `pipeline/shore.py` + `shore_explore.py` + työnkulku "Selvitys – rantatesti" (Shapely ~=2.1 asennetaan vain siinä).
    Vesialueet: MTK OGC API Features (`maastotiedot/features/v1`, kokoelmat `jarvi`, `meri`, `virtavesialue`; sama API-avain,
    Basic auth toimii; bbox-crs/crs EPSG:3067). Tammela: 6 335 asuinrakennusta → ranta 2 659, erillinen rantapalsta 121,
    todennäköisesti (3–15 m) 201, ei 3 354; vapaa-ajan asunnoista 64 % rannalla. Vesialueet 5 s, laskenta 18 s
    (3 ms/palsta), muisti 285 Mt. Tulos omistajalle Excelinä tarkistettavaksi (Karttapaikka-linkit).
    Omistajan tarkistus 4.11.2026 (6 kohdetta): 5 "kyllä" olivat 3–11 m päässä vedestä, väli vesijättöä → omistajan linjaus:
    **vesijättö lasketaan omaksi rannaksi** (käytettävissä ja yleensä lunastettavissa). Luokitus v2 (`shore.py`):
    ranta ≤ `TOL_SHORE` 3 m; "ranta (vesijättö)" ≤ `TOL_GAP` 20 m, jos välissä ei ole toisen kiinteistön maapalstaa
    (tarkistus viidestä kohdasta rantaa, enemmistö ratkaisee); muuten "ei (toinen kiinteistö välissä)"; yli 20 m "ei".
    Vesialuekiinteistö tunnistetaan kiinteistötunnuksen 3. osasta `0876` (yhteinen vesialue; diagnostiikka: palstoista,
    jotka ovat > 80 % vettä, 188 kpl 0876). Välissä esiintyy myös `0878` (28) – käsitellään toistaiseksi maana, selvitä tyyppi.
    v2 Tammela: ranta 2 659, ranta (vesijättö) 153, erillinen rantapalsta 120, ei (toinen kiinteistö välissä) 63, ei 3 340;
    kaikki 6 omistajan tarkistamaa osuivat oikein. Laskenta 24 s (4 ms/palsta, väliaineiston tarkistus mukana), muisti 312 Mt.
    Käyttöliittymässä "ranta" ja "ranta (vesijättö)" kuuluvat suodattimessa samaan "Oma ranta" -valintaan; kortissa maininta vesijätöstä.
    Ennen käyttöönottoa:
    a) ✅ omistajan tarkistus (v1) → vesijättölinjaus; v2:n uudet luokat omistajalle Excelinä mahdolliseen lisätarkistukseen;
    b) ✅ suorituskykytestit 4.11.2026 nykyisille maakunnille:
       Parainen 445 (saaristo, pahin): 16 237 rak., 16 226 palstaa, meri-vesialueiden haku 42 s, laskenta 267 s
       (16,5 ms/palsta, ~4× Tammela), muisti 2,1 Gt (valtava merikuvio). Tulos: ranta 9 458, vesijättö 463, erillinen 435,
       toinen kiinteistö välissä 192, ei 5 689 (vapaa-ajan asunnoista ~86 % rannalla).
       Espoo 049 (iso kaupunki): 39 626 rak., 24 648 palstaa, vesialueet 4 s, laskenta 119 s (4,8 ms/palsta), muisti 449 Mt.
       Tulos: ranta 1 518, vesijättö 48, erillinen 69, toinen kiinteistö välissä 262, ei 37 729. Kaupungeissa välissä usein
       `9903`/`9901` (kaavan yleiset alueet, esim. rantapuisto/katu) → "ei" on oikein.
       Arvio 112 kunnalle: ~750 000 palstaa × ~7 ms ≈ 1,5 h laskentaa per 14 pv kierros ≈ 6–7 min/yö; MML-vesialuehaut
       muutamia satoja/kierros. Optimointi tarvittaessa: merikuviot pilkotaan 1 km ruutuihin (muisti ja Parainen-tyyppiset
       kunnat nopeammiksi); koeajon "indeksit"-aika sisältää vain diagnostiikkaa (ei tuotantoon).
       Saimaa (Puumala 623) testataan, kun Etelä-Savo lisätään.
    Toteutusmalli (helposti kumottava):
    1. `config.SHORE_ENABLED = False` -kytkin + `SHORE_TOL_SHORE`, `SHORE_TOL_LIKELY`. Shapely tuodaan vain kytkimen ollessa
       päällä (laiska import), versio lukittuna requirements.txt:ssä.
    2. Vesialueet haetaan samassa viikoittaisessa kuntakohtaisessa palstahaussa (kunnan rakennusten bbox + 2 km); ei omaa välimuistia.
    3. Laskenta `ParcelResults.put`-vaiheessa: tulos laajenee [pa, ka, pn] → [pa, ka, pn, ranta-luokka, rantaviiva m,
       etäisyys vedestä m, vesilaji, vesialueen ala ha]; kiinteistötasolla "erillinen rantapalsta" (saman kiinteistön toinen palsta rannassa).
    4. Käyttöönotto leviää viikoittaisen uudelleenhaun mukana (1/7 kunnista per yö) → kaikki kunnat viikossa ilman erillistä
       raskasta ajoa; siihen asti "ei vielä laskettu". Lisäaika koko Suomessa arviolta ~10 min/yö.
    5. Tiiliin uudet avaimet: `ra` (0 ei, 1 ei – toinen kiinteistö välissä, 2 ranta, 3 ranta (vesijättö), 4 erillinen rantapalsta), `rl` rantaviiva m,
       `rd` etäisyys vedestä m, `rw` vesilaji (j järvi, m meri, v joki), `rwa` vesialueen ala ha. Arvio tiilikoon kasvusta ~3–5 %.
    6. Käyttöliittymä: suodatinryhmä "Ranta" (Oma ranta [sis. vesijättö] / Erillinen rantapalsta / Ei rantaa / Ei laskettu),
       mahdollisesti liukusäädin "etäisyys vedestä" ja "vesialueen koko" (lammet pois); kortissa osio "Ranta" + selite rajoituksista.
    7. Pikatestit yksinkertaisilla geometrioilla (ohitetaan, jos Shapely puuttuu).
    8. Kumoaminen: `SHORE_ENABLED = False` → build jättää rantakentät pois heti seuraavassa ajossa; riippuvuuden voi poistaa myöhemmin.
    Rajoitukset (kerrotaan käyttäjälle): yhteinen ranta-alue/venevalkama tontin ja veden välissä → "ei" (oikein, mutta voi yllättää);
    kiinteistörajojen epätarkkuus maaseudulla; maankohoamisrannikko (vesijättö); purot (viivoja, `virtavesikapea`) eivät mukana;
    tieto ei kerro vesialueen omistuksesta eikä rannan laadusta.
    Avoimet kysymykset: kiinteistötyyppi 0878. (Lammet ratkaistu 4.11.2026; puro hylätty pistokokeessa 5.11.2026, ks. 2g.)
2g. ✅ Keski-Suomi (22 kuntaa) ja Kymenlaakso (6) + puuttunut Kuhmoinen 291 Pirkanmaalle (siirtyi 2021) 4.11.2026,
    rantatieto ja purot mukana heti. Uusien maakuntien kuntalistat tarkistettava ajantasaisesta maakuntajaosta.
    Ensiajo 1 h 45 min (Ryhti 29 kuntaa ~5 min, palstat + ranta ~1 h 36 min; raskain Kouvola 286: 275 s rantaa,
    ~13 min yht.). 1 057 553 rakennusta (141 kuntaa, 8 maakuntaa), palsta kaikille. Keski-Suomi 110 542 (oma ranta
    41 199 = 37 %, puron varrella 1 460), Kymenlaakso 65 788 (16 204 = 25 %, puro 1 701), Kuhmoinen 4 800 (3 421, puro 78).
    Puroviivoja (virtavesikapea) haetaan kunnan bboxista 10 000–276 000 kpl (eniten Keuruu 249 ja Kouvola 286).
    Tiilet: Keski-Suomi 30,4 Mt, Kymenlaakso 15,4, Pirkanmaa 41,9; yhteensä ~253 Mt. Ei "lisälaskenta epäonnistui".
    Puroluokka poistettiin 5.11.2026 omistajan pistokokeen perusteella (kaikki 18 ojia) → STREAMS_ENABLED False.
    Lisäksi omistajan päätös 4.11.2026: alle 1 ha lammet mukana (olivat jo; MTK `jarvi` sisältää ne) ja "puron varrella" lisätään.
    Tammela: purot 36311 6 411 km / 36312 367 km; kaikki purot → 806 taloa (ojia), vain 2–5 m → 204,
    + kapeat mutkaisuus ≥ 1,1 & ≥ 100 m → 538. Laskenta-aika lähes ennallaan (+1–3 s/kunta), purojen haku ~16–20 s/kunta.
2h. ✅ Etelä-Karjala (9 kuntaa: 153, 405, 416, 441, 580, 689, 700, 739, 831) 5.11.2026 rantatiedon kanssa (ei puroja).
    Ensiajo 31 min (Ryhti ~2 min, palstat + ranta ~26 min; Lappeenranta 104 s rantaa, Saimaa ei ongelma).
    61 466 rakennusta, omalla rannalla 21 769 (35 %; Imatra vain 277 / 8 186). Yhteensä 1 119 029 rakennusta
    (150 kuntaa, 9 maakuntaa), palsta 1 119 028:lle. Tiili 15,3 Mt; tiilet yhteensä ~268 Mt.
2i. ✅ Etelä-Savo (11 kuntaa: 046, 097, 178, 213, 491, 507, 593, 623, 681, 740, 768) 5.11.2026 rantatiedon kanssa.
    **Pertunmaa 588 liitettiin Mäntyharjuun 507 1.1.2025**: Ryhti 0 rakennusta numerolla 588 (4 917 rakennuksen
    property_identifier alkaa yhä 588, municipality_number 507) ja MML-tiedostopalvelu hylkää 588 (HTTP 400
    municipalityInput). Tarkista kuntaliitokset ennen lisäystä! Selvitys: "Selvitys – Ryhti-kentät", kunta "puuttuu:NNN".
    Uusi sääntö `build.grown`: jos kunnan rakennusmäärä > 1,1 × palstojen hakuhetken määrä (`ParcelResults` tallentaa `n`;
    vanhoissa tallenteissa kattavuus < 90 %), kunta pakotetaan uudelleenhakuun heti (lokissa "tulokset kattavat alle 90 %").
    Ajot: ensiajo 55 min (Mikkeli 190 s rantaa, Savonlinna 111 s, Puumala 52 s – Saimaa ei ongelma) + Mäntyharjun
    uudelleenhaku 11 min. 95 723 rakennusta, omalla rannalla 53 808 (56 %; Puumala 84 %). Yhteensä 1 214 752 rakennusta
    (161 kuntaa, 10 maakuntaa), palsta 1 214 751:lle. Tiili 26,6 Mt; tiilet yhteensä ~295 Mt.
    Muistin huippu 4,9 Gt (1,21 milj. rak.) → koko Suomi ~7,5–8 Gt / 16 Gt; levyä vapaana 91 Gt.
2j. ✅ Pohjois-Karjala (13 kuntaa: 090, 146, 167, 176, 260, 276, 309, 422, 426, 541, 607, 707, 848) 5.11.2026 rantatiedon
    kanssa. Ensiajo 55 min (Ryhti ~3 min, palstat + ranta ~50 min; Lieksa 125 s, Joensuu 101 s rantaa). 85 789 rakennusta,
    omalla rannalla 30 700 (36 %). Yhteensä 1 300 541 rakennusta (174 kuntaa, 11 maakuntaa), palsta 1 300 540:lle.
    Tiili 24,5 Mt; tiilet yhteensä ~320 Mt. Muistin huippu 5,2 Gt.
2k. ✅ Pohjois-Savo (18 kuntaa: 140, 171, 204, 239, 263, 297, 402, 420, 595, 686, 749, 762, 778, 844, 857, 915, 921, 925)
    5.11.2026 rantatiedon kanssa; ei kuntaliitoksia (Joroinen 171 siirtyi Etelä-Savosta 2021). Ensiajo 1 h 14 min (Ryhti ~5 min,
    palstat + ranta ~66 min; Kuopio 297: 279 s rantaa). 105 795 rakennusta, omalla rannalla 42 750 (40 %).
    Yhteensä 1 406 336 rakennusta (192 kuntaa, 12 maakuntaa), palsta 1 406 335:lle. Tiili 30,0 Mt; tiilet yhteensä ~350 Mt.
    Muistin huippu 5,7 Gt.
2l. ✅ Pohjanmaa (14 kuntaa: 231, 280, 287, 288, 399, 440, 475, 499, 545, 598, 599, 893, 905, 946) 5.11.2026 rantatiedon
    kanssa; Kruunupyy siirtyi Keski-Pohjanmaalta ja Isokyrö 152 Etelä-Pohjanmaalle 2021. Build 56 min (Ryhti ~4 min, palstat +
    ranta ~49 min; Mustasaari 106 s rantaa, saaristo ei ongelma). 78 685 rakennusta, omalla rannalla 21 526 (27 %).
    Yhteensä 1 485 021 rakennusta (206 kuntaa, 13 maakuntaa), palsta 1 485 020:lle. Tiili 19,6 Mt; tiilet yhteensä ~370 Mt.
    Muistin huippu 6,0 Gt. Ensimmäinen julkaisu jumittui GitHub Pagesissa (`updating_pages` > 10 min, deploy-pages
    aikaraja) → aikaraja 30 min; peruutetun julkaisun uudelleenajo ("Deployment cancelled") ei toimi samalla versiolla,
    vaan tarvitaan uusi ajo (uusi commit tai käsiajo).
2m. ✅ Etelä-Pohjanmaa (18 kuntaa: 005, 010, 052, 145, 151, 152, 218, 232, 233, 300, 301, 403, 408, 743, 759, 846, 934, 989)
    5.11.2026 rantatiedon kanssa; ei kuntaliitoksia. Build 55 min (Ryhti ~2,5 min, palstat + ranta ~46 min; Seinäjoki 83 s
    rantaa). 89 445 rakennusta, omalla rannalla 15 563 (17 %). Yhteensä 1 574 467 rakennusta (224 kuntaa, 14 maakuntaa),
    palsta 1 574 466:lle. Tiili 23,7 Mt; tiilet yhteensä ~395 Mt. Muistin huippu 6,4 Gt. Pages-julkaisu kesti 3,7 min
    (aiemmin ~20 s) → seuraa; aikaraja nyt 30 min.
3. ✅ Ilmoitus omistajalle, jos yöajo epäonnistuu (3.11.2026, GitHub-issue + sähköposti).
3b. Automaattinen sivun tarkistus yöajon lopuksi (suunniteltu 3.11.2026, ei vielä toteutettu). Tarkoitus: huomata ilman
    omistajaa, jos julkaistu sivu ei toimi (esim. JS-virhe, CDN- tai taustakarttakatko, rikkinäinen tiili), koska Claude ei
    näe sivua suoraan. Malli: uusi jobi `check` deployn jälkeen (`needs: deploy`), ennen `notify`a:
    - Playwright + Chromium GitHubin ajokoneella (`npx playwright install --with-deps chromium` tai pip-versio);
    - avaa `SITE_URL` (välimuistin ohitus `?v=<ajon id>`), odottaa `meta.json`:n ja kartan latautumisen;
    - tarkistaa: ei sivun JS-virheitä (`pageerror`), `meta.json`:n määrä ja maakunnat vastaavat buildin lukuja,
      taustakartta latautui, jokaisen maakunnan pmtiles vastaa (HTTP 206 Range-pyyntöön);
    - siirtyy tunnettuihin kohteisiin (esim. Tampereen keskusta z15, Tammela z14) ja tarkistaa `map.queryRenderedFeatures`
      → rakennuspisteitä > 0; avaa yhden kohteen tietokortin ja tarkistaa, että siinä on osoite ja tontin ala;
    - testaa myös puhelinkoon (390 px): Suodattimet-nappi näkyy ja avaa paneelin;
    - ottaa kuvakaappaukset (työpöytä + puhelin) ajon liitteiksi; epäonnistuessa `notify` avaa ilmoituksen syineen
      (`::error`-rivit kuten buildissa) ja liittää kuvakaappauksen linkin.
    Huom: tarkistus ei voi estää jo tehtyä julkaisua (Pages-julkaisu on tehty); se hälyttää. Vaihtoehto myöhemmin:
    tarkistus ennen julkaisua paikallisesti tarjoillusta dist/-kansiosta (estää rikkinäisen julkaisun) + kevyt tarkistus julkaisun jälkeen.
    Kesto arviolta 1–2 min/ajo, ei kuormita rekistereitä.
4. Oma verkko-osoite.
5. Osoitehaku, mobiilihionta, tietosuojaseloste.
