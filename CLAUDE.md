# Talokartta – ohjeet kehittäjälle (Claude)

Omistaja ei ole ohjelmoija: Claude kirjoittaa kaiken koodin. Selitä muutokset suomeksi selkokielellä, tee pieniä
kokonaisuuksia ja kerro aina, miten omistaja voi itse todeta lopputuloksen (mitä avata, mitä pitäisi näkyä).
Omistajan käyttöohje on `KAYTTOOHJE.md` (ilmoitukset, käsiajo, avaimet, maakuntien lisääminen, kulut). **Päivitä se aina,
kun toiminta, asetukset, ilmoitukset tai maakunnat muuttuvat** (myös "Päivitetty viimeksi" ja luvut).
Mittaukset, koeajot ja päätösten tausta: `HISTORIA.md` (arkisto; lisää sinne uudet mittaukset, pidä tämä tiedosto tiiviinä).

## Nykytila (6.11.2026)

- Koko Manner-Suomi: 18 maakuntaa, 292 kuntaa (`config.REGIONS`, tarkistettu Tilastokeskuksen luokitusta vasten),
  1 898 604 asuinrakennusta, palsta kaikille paitsi 9. Rantatieto kaikissa maakunnissa. Ahvenanmaa ei ole Ryhtissä.
- Sivu https://vv-tec.github.io/Talokartta/ (GitHub Pages). Tiilet ~486 Mt / 1 Gt, suurin tiedosto Uusimaa 62,5 Mt / 100 Mt.
- Yöajo (klo ~4–5) ~25–35 min: Ryhti-muutokset + ~22 kuntaa palstoja ja rantaa (1/14 kunnista). Muistin huippu
  7,6 Gt / 16 Gt (build lokittaa "Muistin huippu"), välimuisti ~314 Mt / 10 Gt, levyä vapaana ~90 Gt.

## Arkkitehtuuri

- `pipeline/` – Python 3.12, riippuvuus `requests` (+ Shapely rantatiedolle). Ajo: `python -m pipeline.build --out dist`.
  Pikatestit ilman verkkoa: `python -m pipeline.selftest` (pidä ajan tasalla, kun logiikka muuttuu; rantatestit ohitetaan
  ilman Shapelya, CI:ssä ajetaan). Verkkopyynnöt `net.py`: peräkkäin, uudelleenyritys viiveellä, `USER_AGENT` tunnistaa projektin.
  - `ryhti.py` – SYKE Ryhti OGC API Features: `open_building` (crs EPSG:3067), `open_address`, `open_address_deleted`.
    Suodatus CQL `municipality_number='NNN'`; muutoshaku `modified_timestamp_utc > '…Z'` (koko maassa ~2 500–7 000
    muuttunutta rakennusta/vrk). `properties`-parametri toimii osoitteille, rakennuksille ohitetaan.
  - `ryhti_store.py` – tila `cache/ryhti.json.gz` (vain asuinrakennukset kevennettyinä). Kunta haetaan kokonaan, jos puuttuu
    tai yli `RYHTI_FULL_DAYS` (30) pv vanha; muuten koko maan muutokset edellisen tallessa olevan jälkeen (1 pv päällekkäisyys),
    uusille rakennuksille osoitteet erikseen. Poistetut siivoutuvat kunnan seuraavassa täydessä haussa, joka lokittaa erot
    ("erot tallessa olleeseen: …") muutoshaun luotettavuuden seurantaan. Täysiä hakuja enintään `RYHTI_TIME_BUDGET_MIN` (60) min.
  - `mml_files.py` – **palstalähde**: MML:n tiedostopalvelu (OGC API Processes,
    `https://avoin-paikkatieto.maanmittauslaitos.fi/tiedostopalvelu/ogcproc/v1`), prosessi
    `kiinteistorekisterikartta_vektori_kunta`, GPKG/EPSG:3067, yksi työ per kunta. Avain GitHub-salaisuutena `MML_API_KEY`
    (Basic auth, avain käyttäjänä; Claude ei näe avainta). Taulu `PalstanSijaintitiedot` (geom, kiinteistotunnus 14 num.);
    luetaan nyt vain nämä kaksi saraketta. Kuntatiedostossa myös naapurikuntien rajapalstoja. Palstalla ei ole pysyvää
    tunnistetta → id = kiinteistötunnus + ensimmäinen piste. Geometria luetaan ilman kirjastoja (`gpkg_polys`).
  - `mml.py` – INSPIRE WFS `cp:CadastralParcel` (bbox E,N + `urn:ogc:def:crs:EPSG::3067`): varatapa ilman avainta
    (`mml.ParcelCache`, rajat ruuduittain) sekä uusien rakennusten aluehaku `ParcelResults.fill_new` (500 m ruuduittain,
    enintään `NEW_BUILDINGS_MAX_PER_RUN` 500/ajo; ei löytynyt → uusi yritys 7 pv, kirjanpito `tried`; kiinteistön ala voi
    jäädä vajaaksi, tarkentuu täydessä haussa).
  - `mml.ParcelResults` (`cache/parcel-results.json.gz`, {kunta: {date, n, res: {building_key: [pa, ka, pn]}}}): vain
    tulokset, ei rajoja. Kunta haetaan uudelleen `PARCEL_MAX_AGE_DAYS` (14) pv välein vanhimmasta alkaen; puuttuvat heti;
    `build.grown` pakottaa uudelleenhaun, jos kunnan rakennusmäärä > 1,1 × hakuhetken `n` (esim. kuntaliitos).
    Palstahaku lopetetaan hallitusti `PARCEL_TIME_BUDGET_MIN` (150) min kohdalla; yksittäisen kunnan virhe ohitetaan; jos
    kuntia puuttuu, haetut tallennetaan (välimuisti `if: always()`), ajo päättyy virheeseen eikä julkaise, seuraava jatkaa.
    Kapasiteetti: pakotettuna ~30 kuntaa/ajo (rantatieto mukana).
  - **Rantatieto (irrotettava lisäosa)** – `shore.py`, `requirements-shore.txt` (Shapely ~=2.1), `config.SHORE_REGIONS`
    (**tyhjä lista = pois päältä**: shorea/Shapelya ei tuoda, ei ra-kenttiä, sivu piilottaa Ranta-osiot). Kytkentä vain
    `ParcelResults.on_parcels`-koukussa (lasketaan samoista palstoista aina, kun kunnan palstat ladataan) ja
    `make_records(..., shore_res)`. Tulokset `cache/shore-results.json.gz` ({building_key: [ra, rl, rd, rw, rwa]}).
    Vesialueet MTK OGC API Features (`maastotiedot/features/v1`: `jarvi` (myös alle 1 ha lammet), `meri`, `virtavesialue`;
    sama avain) kunnan rakennusten bbox + 2 km. Luokitus (v2): ranta ≤ `TOL_SHORE` 3 m; ranta (vesijättö) ≤ `TOL_GAP` 20 m,
    jos välissä ei toisen kiinteistön maapalstaa (5 kohtaa, enemmistö); muuten "toinen kiinteistö välissä"; yli 20 m "ei";
    erillinen rantapalsta = saman kiinteistön toinen palsta rannassa. Yhteinen vesialue tunnistetaan tunnuksen 3. osasta
    `0876`; `9901`/`9903` (kaavan yleiset alueet) ovat maata → "ei" oikein. Uusi maakunta / käyttöönotto: puuttuvat kunnat
    haetaan heti (`ParcelResults.get(force=…)`); uusi rakennus saa rannan kunnan seuraavassa palstahaussa (≤ 14 pv).
    Lisäosan virhe ei kaada palstoja (loki "lisälaskenta epäonnistui"). Laskennan versio `shore.VERSION` kunnittain;
    vanhat päivitetään `get(upgrade=…)` vain yön vapaaseen kiintiöön.
    **Puron varrella pois käytöstä 5.11.2026** (`shore.STREAMS_ENABLED = False`; omistajan pistokoe: kaikki 18 uomaa ojia,
    MTK ei erota puroa ojasta). `make_records` muuntaa vanhat ra 5 → 0; meta `streams` false. Palautus: True + VERSION 3
    (toteutuksen kuvaus HISTORIA.md). Web: `app.js` RANTA-lohkot (SHORE_*, shoreCard, buildShore), `index.html` `#shoreSec`.
    Kokonaan poisto: nämä + `shore.py`, `requirements-shore.txt`, workflow-asennusrivi, selftestin `shore_tests`.
  - Julkaisu maakunnittain: maakunta julkaistaan, kun sen kaikkien kuntien Ryhti- ja palstatulokset ovat valmiina;
    keskeneräinen odottaa, muut päivittyvät. Palstat haetaan vain Ryhti-valmiille kunnille.
  - Turvatarkistus `build.publish_problems` vertaa julkaistun sivun meta.jsoniin (`config.SITE_URL`): estää julkaisun, jos
    maakunta putoaisi pois tai kunnan rakennusmäärä putoaa yli `DROP_PCT` 5 % (ja yli `DROP_MIN` 20); meta `muni_counts`.
    Ohitus: käsiajo `ohita_tarkistukset` (env `SKIP_CHECKS`). `build.fail()` tulostaa `::error`-rivin → issueen "Syy".
  - `build.py` – yhdistää, kirjoittaa GeoJSONSeq:n, ajaa `tippecanoe` (taso kerrallaan) → `dist/data/b-<maakunta>.pmtiles`
    + `g.pmtiles` (tiheysruudut, tile-join) + `meta.json`, kopioi `web/` → `dist/`. Keskeytyy, jos tiedosto > 95 Mt.
  - Selvitysajot (eivät vaikuta sivuun): `ryhti_explore.py` ("Selvitys – Ryhti-kentät"; kunta `maakunnat` = kuntalistojen
    tarkistus Tilastokeskuksen luokitusta kunta_1_YYYY0101#maakunta_1_YYYY0101 vasten, `puuttuu:NNN` = kuntaliitosselvitys),
    `mml_explore.py` ("Selvitys – MML-tiedostolataus"), `shore_explore.py` ("Selvitys – rantatesti"), `codes_explore.py`,
    `metsa_explore.py` + `metsa_laske.py` ("Selvitys – metsätilat", vaihe `rakenne` / `laske` → Excel liitteenä + CSV lokiin).
- `web/` – staattinen sivu, ei build-vaihetta. Lukee `meta.json`:n `regions`-listan ja lisää jokaiselle maakunnalle lähteen
  ja tason (`B_LAYERS`); suodattimet ja värit koskevat kaikkia. MapLibre GL 4.7.1 + pmtiles 3.2.0 unpkg-CDN:stä,
  taustakartta OpenFreeMap (positron/dark).
- `.github/workflows/build-deploy.yml` – yöllinen ajo (cron 17 2 * * *) + push + käsin; julkaisu GitHub Pagesiin;
  epäonnistunut ajo ei julkaise. `[skip ci]` commit-viestissä ohittaa ajon (pelkät dokumenttimuutokset). Jobi `notify`:
  epäonnistunut ajo avaa issuen (label `ajo-epäonnistui`, mainitsee omistajan) tai kommentoi avointa; onnistunut sulkee.
  Käsiajon `koe_virhe` pysäyttää ajon tarkoituksella. Välimuistin avain `parcels-<aikaleima>` joka ajossa.
  Jobi `check` (deployn jälkeen) kutsuu `check-site.yml`:ää buildin `updated`/`count`-luvuilla; notify: jos deploy
  onnistui ja vain check epäonnistui, issuen otsikko "Talokartan sivun tarkistus löysi ongelman" (muuten "…päivitys epäonnistui").
- **Metsakartta** (metsätilat, tiekartan kohta 6; vaihe 1 tehty 6.11.2026): koodi täällä, ajo ja julkaisu repositoriossa
  **vv-tec/Metsakartta** (oma Pages 1 Gt: https://vv-tec.github.io/Metsakartta/, sama alkuperä kuin Talokartta → ei CORS-ongelmaa).
  Metsakartan työnkulku `metsa.yml` ("Päivitä metsätilat ja julkaise", cron 47 4 * * * eli Talokartan jälkeen + käsin,
  `ohita_tarkistukset`) hakee Talokartan koodin (`koodi/`), ajaa `python -m pipeline.metsa`, julkaisee ja ilmoittaa
  epäonnistumisesta Metsakartan issueihin (sama malli). Salaisuus `MML_API_KEY` erikseen Metsakartassa (omistajan valinta A:
  Metsakartta lataa palstat itse 30 pv välein, ~10 kuntaa/yö). Asetukset `config.METSA_*` (maakunnat `METSA_REGIONS`).
  - `metsa.py`: kunta vanhimmasta (puuttuvat ensin, `METSA_MAX_AGE_DAYS` 30, `METSA_TIME_BUDGET_MIN` 150, `VERSION`-muutos
    → uudelleenlaskenta): Metsäkeskuksen MV_<Kunta>.zip (nimi config.py:n kommenteista, `norm`), MML-palstat
    (`municipality_parcels`), Ryhti (rakennukset kiinteistöittäin) → kuviot × palstat (STRtree, leikkausala) → talteen vain
    metsätilat (metsämaata > `METSA_MIN_FOREST_HA`): määrät `am_<kauppatapa>|<puutavaralaji>` (m³), alat, luokkien ha:t,
    raja 1 m yleistettynä lon/lat. Välimuisti `cache/metsa/<kunta>.json.gz` + `state.json` (avain `metsa-<aikaleima>`).
    Arvo lasketaan julkaisussa joka ajo Luken uusimmilla hinnoilla (`props`). Kunnan virhe → muut jatkavat, ajo päättyy
    virheeseen eikä julkaise. Turvatarkistus: maakunta ei putoa, kunnan tilamäärä ei pudota yli 5 %.
  - Julkaisu: `data/f-<maakunta>.pmtiles` (taso "f", rajat z10–13 (`POLY_MAXZOOM`, ylizoomaus; minzoom 11 → 10 6.11.2026
    omistajan toiveesta), `--detect-shared-borders`, **vain `TILE_KEYS`**: k, ka, e (100 €), eh (10 €), tu, kp, da–d5),
    `data/kortit/<kunta>.json` ({c: `CARD_KEYS`, r: {tunnus: [arvot]}}; tietokortti lataa klikatessa, kunta =
    tunnuksen 1. osa 3 numeroksi), `data/meta.json`
    (regions, muni_counts, munis, prices {alue: {"KAUP|PTL": [hinta, kk]}}, `kp` kasvupaikkajakauma, `max` {ka, e}, `cards`),
    esikatselusivu `metsa_web/` (index.html + esikatselu.js; väri €/ha, tietokortti, **suodattimet**: kokonaisala,
    puuston arvo €, metsäpohja = maapohja (turve < / ≥ 50 %) + yleisin kasvupaikka, ikäjakauma (vähintään % aukea+taimikko,
    nuori, varttunut, uudistuskypsä d4+d5); näkyvien määrä). **Kaukaa ei näytetä mitään** (omistajan päätös 6.11.2026:
    pisteet peittivät taustakartan) → pistetaso fp poistettu; paneeli kehottaa zoomaamaan. Talokartan sivua ei vielä muutettu.
    Selaintarkistus `check/metsa_tarkistus.mjs` (Metsakartan jobi `check` julkaisun jälkeen; 10 kohtaa, mm. suodattimet ja
    kortti; epäonnistuminen → Metsakartan issue). Käyttää globaaleja `map`, `META` ja id:itä `#kaMin`, `#age-u`, `#reset`,
    `#count`, `#card` → päivitä tarkistus, jos nämä muuttuvat.
    **Koko (vaihe 2a, 6.11.2026): Kanta-Häme 16 728 tilaa, f 9,1 Mt + kortit 3,0 Mt (ennen 25,7 Mt) → koko Suomi
    pinta-alan mukaan ~0,5 + 0,17 Gt ≈ 0,7 Gt / 1 Gt.** Ensimmäinen haku ~2 min/kunta (Hämeenlinna 10 min, MML hallitsee).
    **Vaihe 3 (7.11.2026): + Uusimaa** 26 kuntaa 58 min, 27 326 tilaa, f-uusimaa 15,9 Mt; yhteensä 44 054 tilaa,
    kortit 7,9 Mt, muisti 710 Mt. Kaikki MV-tiedostot löytyivät nimellä (puuttuva → `::warning` + 0 tilaa).
    **+ Pirkanmaa (7.11.2026)** 23 kuntaa 50 min, 44 264 tilaa, f-pirkanmaa 24,6 Mt; yhteensä 88 318 tilaa, f 49,6 Mt +
    kortit 15,9 Mt ≈ 0,74 kt/tila → koko Suomi ~0,7–0,8 Gt (seuraa). `muni_names` jättää sulkulisätiedot pois (Kuhmoinen).
    **+ Päijät-Häme (7.11.2026)** 10 kuntaa 22 min, 16 276 tilaa, f-paijat-hame 10,0 Mt; yhteensä 104 594 tilaa,
    f 59,6 Mt + kortit 18,8 Mt = 78 Mt.
    **+ Varsinais-Suomi (7.11.2026)** 27 kuntaa 56 min, 35 248 tilaa, f 21,1 Mt; yhteensä 139 842 tilaa, f 80,7 Mt +
    kortit 25,1 Mt = 106 Mt, muisti 1,3 Gt. `mv_file`: MV-tiedosto myös nimen 1. sanalla (Koski Tl → löytyi).
    **+ Satakunta (7.11.2026)** 16 kuntaa, 24 797 tilaa, f 12,4 Mt; yhteensä 164 639 tilaa, f 93,1 Mt + kortit 29,6 Mt
    = 123 Mt. `mv_download` yrittää uudelleen 4× (Eurajoki: Connection reset kaatoi ensimmäisen ajon).
    **+ Kymenlaakso (8.11.2026)** 6 kuntaa 20 min (Kouvola 555 s), 17 796 tilaa, f 9,6 Mt, hinta-alue MPKH04;
    yhteensä 182 435 tilaa, f 102,7 Mt + kortit 32,7 Mt = 136 Mt. `metsa.js` addLayers odottaa `getStyle()`:a (idle).
    **+ Etelä-Karjala (8.11.2026)** 9 kuntaa 23 min, 22 265 tilaa, f 12,3 Mt; yhteensä 204 700 tilaa, f 115,0 Mt +
    kortit 36,7 Mt = 152 Mt.
    **+ Keski-Suomi (8.11.2026)** 22 kuntaa 51 min, 44 897 tilaa, f 26,7 Mt; yhteensä 249 597 tilaa (150/292 kuntaa),
    f 141,7 Mt + kortit 44,8 Mt = 187 Mt → koko Suomi ~0,5–0,7 Gt. MV-latauksen uusi yritys toimi (Laukaa).
    **+ Etelä-Savo (8.11.2026)** 11 kuntaa 55 min (1. ajo: MML palautti tyhjiä vastauksia kaikille → `_req_json`
    yrittää uudelleen ja kertoo tilan), 41 862 tilaa, f 28,9 Mt; yhteensä 291 459 tilaa, f 170,6 Mt + kortit 52,4 Mt.
    **Kuntaliitokset:** `config.MERGED_PROPERTY_PREFIXES` {"507": ["588"]} (Pertunmaan tunnukset yhä 588) → palstat
    mukaan (`own_prefixes`), kortit tallennetaan **tunnusalun** mukaan (`card_prefix`, 162 tiedostoa / 161 kuntaa);
    paljon vieraita tunnusalkuja kuntatiedostossa → `::warning` (uusi liitostapaus).
  - **Talokartan metsätilanäkymä** (vaihe 2b, 6.11.2026; piilotettu): `web/metsa.js` (IIFE, toimii vain jos osoitteessa
    `?moodi=…`; `window.Metsa` {enabled, active, meta, addLayers, updateCount, click, hover, clearSelection, has,
    houseLink}). Lukee `METSA_BASE` = https://vv-tec.github.io/Metsakartta/data/ (meta.json, f-*.pmtiles, kortit/).
    `index.html`: `#modeSwitch` (Talot | Metsätilat, hidden), `#fpanel` (metsäpaneeli, sisältö metsa.js:stä: `#fCount`,
    `#fKaMin/Max`, `#fEMin/Max`, `#fPeat`, `#fSites`, `#fAge-a/n/v/u`, `#fReset`). `app.js`-koukut: `setHouseLayers`,
    updateCount/click/mousemove ohjataan Metsalle, `curPanel()`, closeCard → clearSelection, talon kortissa `#forestLink`
    (näkyy, jos kiinteistö on metsätila), fitBounds/alaotsikko vain talonäkymässä. Tasot `metsa-f-<maakunta>-fill/-line/-sel`
    taustakartan nimien alla. Moodi osoitteessa (`?moodi=metsa|talot`, replaceState). `build.py` versioi metsa.js:n.
    Tarkistus: `check/metsa_tarkistus.mjs` `runTalo` (TALO_URL, oletus julkaistu Talokartta; ajetaan Metsakartan jobissa).
  - Pages-julkaisun jumi myös Metsakartassa (6.11.2026 kahdesti peräkkäin "deployment_queued" → "Timeout reached"):
    peruutetun version (`pages_build_version` = commit) uudelleenyritys jumittuu → tee Metsakarttaan uusi commit
    (esim. README) ja aja uudelleen; meni läpi heti. Lisäksi Pages näyttää uuden version joskus vasta 5–15 min
    "success"-julkaisun jälkeen, kyselyparametrista huolimatta → sivu hakee meta.jsonin `?v=<aika>`, tarkistus odottaa
    versiota 10 min ja vanha versio on vain varoitus (`::warning`), ei hälytys.
  - Ominaisuudet: `k` tunnus, `ka` kokonaisala, `mm` metsämaa, `kj` kitu+jouto, `mu` muu ala (ha), `mt` metsätietoa %,
    `pn` palstoja, `e` arvo €, `eh` €/ha metsämaata, `eu` arvo hakkuutavan hinnoin, `et`/`ek` tukki/kuitu €, `t`/`ku`
    tukki/kuitu m³, `v` m³, `vh` m³/ha, `sm`/`sk`/`sb`/`sl` puulajit m³ (havu, kuusi, koivu, muu lehti), `ps` pääpuulaji,
    `ik` keski-ikä, `da` aukea/siemenpuu, `dt` taimikko, `d2`–`d5`, `de` eri-ikäis (% metsämaasta), `kp` yleisin kasvupaikka
    1–8, `tu` turve %, `oj` ojitettu %, `hr` hakkuurajoitus %, `i0`/`i1` inventointi vvvv-kk, `rb`/`ab` rakennuksia/asuin-,
    `pa` Luken hinta-alue.
- `check/` – **sivun tarkistus** (`sivutarkistus.mjs`, Node + Playwright 1.63, `package.json`). Avaa julkaistun sivun
  Chromiumilla ja tarkistaa 17 kohtaa (meta-versio ja määrät, pmtiles 206, taustakartta, tunnetut paikat Tampere/Tammela/
  Kallio/Rovaniemi, tietokortti, puhelinkoko, JS-virheet, lataukset). Käyttää sivun globaaleja `map`, `META`, `B_LAYERS`,
  `state` (`app.js`) sekä id:itä `#card`, `#filtersBtn`, `#panel`, `#visCount`, `#updated` → **päivitä tarkistus, jos
  nämä muuttuvat** (myös moodien tullessa). Uusi yritys 60 s päästä ennen hälytystä. Käsiajo: työnkulku "Tarkista sivu"
  (`check-site.yml`, valinnainen `osoite`). Lokin ✓/✗-rivit; kuvakaappaukset liitteenä (Claude ei voi ladata niitä).

## Tiilien sisältö

- Taso `b` (zoom 12–14, ylizoomaus ylöspäin): yksi piste per asuinrakennus. Lyhyet avaimet säästävät tilaa:
  `id` rakennustunnus, `k` kiinteistötunnus (834-404-3-64), `a` osoite(et) " / ", `pc` postinro, `po` postitoimipaikka,
  `p` tyyppi (01 vapaa-ajan, 05 pientalo, 06 kerrostalo), `s` käytössäolo (Ryhti-koodi), `d` valmistumispäivä, `y` vuosi,
  `g` kerrosala, `t` kokonaisala, `f` kerroksia, `n` asuntoja, `c` asuinrakennuksia samalla kiinteistöllä,
  `pa` palstan ala m², `ka` kiinteistön ala m², `pn` palstoja, `ex`/`ny` ETRS-TM35FIN,
  `ra` ranta (0 ei, 1 ei – toinen kiinteistö välissä, 2 ranta, 3 ranta (vesijättö), 4 erillinen rantapalsta,
  5 puron varrella – pois käytöstä; puuttuu = ei laskettu), `rl` rantaviiva m, `rd` etäisyys vedestä m, `rw` vesilaji
  (j/m/v), `rwa` lähimmän vesialueen ala ha, `m` runkomateriaali, `fa` julkisivu, `r` rakentamistapa, `h` lämmitystapa,
  `e` lämmitysenergia (Ryhti-koodit, "00" pois; selitteet `web/app.js` CATS, koodistot.suomi.fi), `v` tilavuus,
  `ha` huoneistoala, `sj` suojeltu 1/0. Puuttuvat arvot jätetään pois (suodattimet käyttävät `has`).
  meta.json `by` = koodikenttien jakaumat (suodattimet näyttävät vain aineistossa esiintyvät arvot).
  Ryhtissä ei ole väriä eikä liittymätietoja. Lupatiedot: kokoelma `avoimet_lupa_rakennukset` (ei käytössä).
- Taso `g` (zoom 0–11): tiheysruudut 5 km (z0–9) ja 1 km (z10–11), ominaisuus `n` = rakennusten määrä.

## Päätökset

- Ei omaa palvelinta eikä tietokantaa: staattiset tiedostot → halpa, nopea, skaalautuu. Kulut 0 €.
- Tiedot päivitetään yöllä eräajona, ei reaaliajassa. Rekisterien kuormitus pidetään pienenä (omistajan toive):
  haut peräkkäin, harvoin muuttuva tieto kiertävästi (palstat 14 pv, Ryhti täysi 30 pv).
- Mukana vain asuinrakennukset (01, 05, 06); purettu/tuhoutunut (06, 07, 08) ja purkupäivälliset pois.
- Omistajatietoja ei käsitellä eikä näytetä.
- Lähdemaininnat (CC BY 4.0) ja päivitysaika näkyvät sivulla.
- Ranta: vesijättö lasketaan omaksi rannaksi; suodattimessa "Oma ranta" = ra 2–3. Lammet mukana. Puroluokka pois (5.11.2026).
- Uusi maakunta lisätään oletuksena rantatiedon kanssa (myös `SHORE_REGIONS`), ellei omistaja toisin pyydä.

## Käytännön ohjeet ja opitut asiat

- **Työympäristö:** Clauden kone ei tavoita rekisterirajapintoja (Ryhti, MML, stat.fi) suoraan → kokeet selvitysajoina
  GitHubissa. GitHubin GraphQL on estetty: käytä `gh api repos/vv-tec/Talokartta/...` (REST). Käsiajo:
  `gh api -X POST repos/vv-tec/Talokartta/actions/workflows/build-deploy.yml/dispatches -f ref=main`; selvitysajo esim.
  `.../explore-ryhti.yml/dispatches -f ref=main -f 'inputs[kunta]=maakunnat'`. Seuraa ajoa `gh run view <id> --log` ja
  poimi lokista rivit "Ryhti:", "Rakennuksia", "palstat", "ranta NNN", "Valmis", "Mt", "Muistin huippu", "##[error]".
  Sivun tarkistus: `.../check-site.yml/dispatches -f ref=main`; tulokset jobin lokista (`actions/jobs/<id>/logs`, rivit ✓/✗).
- **Kunnan tai maakunnan lisäys:** aja `maakunnat`-tarkistus ennen ja jälkeen; tarkista kuntaliitokset (esim. Pertunmaa
  588 → Mäntyharju 507 1.1.2025: Ryhtissä 0 rakennusta, MML hylkää numeron HTTP 400). Kunnan siirto maakunnasta toiseen ei
  vaadi uudelleenhakua. Päivitä KAYTTOOHJE (maakunnat, luvut, rantataulukko) ja HISTORIA (mittaukset).
- **Pages-julkaisun jumi** ("Timeout reached" deploy-vaiheessa, sattunut 5.11. ja 6.11.2026): `deploy-pages`-aikaraja on
  enintään 600000 ms (suurempi ohitetaan). Peruutetun julkaisun uudelleenajo ei toimi samalla versiolla → uusi käsiajo
  (välimuistilla ~7 min). Jos jumit yleistyvät: automaattinen uudelleenyritys.
- "Cache save failed" ajossa, jossa mitään ei haettu, on odotettu (sama avain on jo tallessa).
- **Rajat:** Pages 1 Gt sivusto, 100 Mt tiedosto, kaista ~100 Gt/kk (pehmeä) → tiilet Cloudflare R2:een, jos liikenne tai
  koko kasvaa. Ajokone 16 Gt muistia. Koko Suomen MML-GPKG (13,3 Gt, lataus ~2 h) on olemassa, mutta kunnittainen
  lataus on käytössä (ks. HISTORIA).
- Avoin kysymys: kiinteistötunnuksen ryhmä `0878` (rannan välissä, käsitellään maana) – selvitä tyyppi.

## Tiekartta

Valmiit: 1 Tammela, 2 koko Manner-Suomi (2a–2q maakunnittain), 2x rantatieto, 3 ilmoitus epäonnistuneesta ajosta
(issue + sähköposti), 3b automaattinen sivun tarkistus (6.11.2026). Yksityiskohdat HISTORIA.md.
Jatkossa mahdollinen: tarkistus ennen julkaisua paikallisesti tarjoillusta `dist/`:stä (estäisi rikkinäisen julkaisun).


4. Oma verkko-osoite.
5. Osoitehaku, mobiilihionta, tietosuojaseloste (ennen kuin palvelusta kerrotaan laajemmin; tärkeämpi metsätilojen myötä).
6. Toimintamoodit **Metsätilat** ja **Tontit** (suunniteltu 6.11.2026 omistajan kanssa, ei toteutettu; ei koodia ennen
   omistajan lupaa). Sama sivu, yläreunassa moodivalinta **Talot | Metsätilat | Tontit**. Yhteiset: taustakartta, kartan
   sijainti/zoom, myöhemmin osoitehaku. Moodikohtaiset: tasot, suodatinpaneeli, tietokortti. Moodi verkko-osoitteessa
   (jaettava linkki). Ristiinlinkitys: metsätilan kortista talonäkymään (jos tilalla asuinrakennus) ja päinvastoin.
   Keskeneräinen moodi piilossa (esim. `?moodi=metsa`), kunnes omistaja hyväksyy.
   Käyttäjät eivät näe myynnissä olevia kohteita (myynti-ilmoituksia ei ole avoimena datana) → tutkimiseen ja vertailuun.
   **Metsätilat** (toteutetaan ensin, data valmiimpaa):
   - Määritelmä (omistajan päätös 6.11.2026, vahvistettu Tammela-kokeen jälkeen): kiinteistö, jolla **metsämaata yli 2 ha**
     (Metsäkeskuksen pääryhmä metsämaa; muuten esim. hiekkakuopat näkyisivät metsinä). Tammelassa 1 689 tilaa.
     Yhteismetsät (esim. 834-874-1-0) ja suojelualueet (esim. kansallispuisto 834-891-1-3) **jäävät näkyviin**.
     Kiinteistön kaikki palstat yhteen; yhden palstan klikkaus korostaa koko tilan.
   - Lähteet: palstarajat nykyisestä MML-latauksesta (ei lisäkuormaa MML:lle; nyt rajat hylätään → talteen tilakohtaiset
     tulokset); Metsäkeskuksen avoin metsävaratieto (metsävarakuviot, CC BY 4.0, GPKG kunnittain, EPSG:3067, keskikoko
     1,4 ha, päivittyy 2×/vk; tarkkuus: kokonaistilavuus ±20 % ~8/10 kuviolla) – haetaan kunnittain esim. 30 pv välein;
     pellot/suot MTK:sta (sama avain kuin vesialueet); kantohinnat Luonnonvarakeskuksen tilastoista (PxWeb-rajapinta).
   - Suodattimet: kokonaisala ja metsämaan ala (ha), **puuston arvo** (€ ja €/ha; omistajan nimitys), puumäärä
     (m³, m³/ha), pääpuulaji, ikärakenne kehitysluokkina (esim. uudistuskypsää ≥ x %), metsäpohja (kasvupaikka,
     kivennäis-/turvemaa, ojitus). Väritys valittavissa: €/ha, kehitysluokka, kasvupaikka.
   - Tietokortti: alat (metsämaa, kitu-/joutomaa, **muu ala** = kokonaisala − metsäkuviot; omistajan päätös 6.11.2026),
     puusto puulajeittain, ikärakenne pylväinä, puuston arvo tukki/kuitu eriteltynä + käytetyt kantohinnat ja kuukausi,
     metsätiedon ajankohta. Maininta: laskennallinen arvo, ei kauppahinta.
     Omistajan päätökset 6.11.2026: arvion oheen myös **arvo hakkuutavan hinnoin** pienellä infotekstillä (uudistuskypsä
     uudistushakkuun, varttunut harvennushakkuun, nuori ensiharvennuksen hinnoin; Tammelassa ~9 % pystykaupan
     keskihintoja pienempi) sekä **hakkuurajoituksen osuus** metsämaasta (Metsäkeskuksen `restriction`-taulu, esim.
     kansallispuisto 100 %).
   - **Laajennusoptiot myöhemmin** (omistajan päätös 6.11.2026, ei ensimmäiseen versioon): metsätilan rantatieto
     (nykyinen rantalaskenta laajennettuna tiloille) sekä pellot ja suot erikseen MTK:sta (nyt "muu ala").
   - **Aineistot (selvitetty 6.11.2026, koeajo "Selvitys – metsätilat", `metsa_explore.py` / `metsa_laske.py`):**
     Metsäkeskuksen uusi tietomalli tuotannossa 1.9.2026 (vanha poistuu 6/2027): `https://avoin.metsakeskus.fi/aineistot/MV/Kunta/MV_<Kunta>.zip`
     (Tammela 53 Mt zip / 126 Mt GPKG, päivittyy viikoittain ke–to yönä). Taulut: `stand` (standid, geometry, area ha),
     `growthplacedata` (maingroup 1 metsämaa / 2 kitu / 3 jouto, subgroup, fertilityclass, soiltype, drainagestate),
     `treestand` (treestandclass 1 inventointi / 2 nykyhetki / 3 ennuste, developmentclass, maintreespecies, treedatadate),
     `treestandsummary` (m³/ha: volume, sawlogvolume, pulpwoodvolume, age), `treestratum` (puulajeittain, m³/ha),
     `codeschema_mapping` (koodien selitteet tiedostossa itsessään). Arvo −1 = puuttuu.
     MML:n kuntatiedostossa ei ole rekisteriyksikkölajia (vain tunnukset, palstat, rajat, rajamerkit).
     Luke: `https://statdb.luke.fi/PxWeb/api/v1/fi/LUKE/met/teokau/kk/0100_teokau.px` (INFO E_M3, MPKH01–08 hinta-alueet,
     KAUP PKAUP/UUD/HAR/ENS, PTL TUK_MA/KU/KO, KUI_MA/KU/KO; ENS-tukkihinta aina puuttuu). Hinta-alueet maakunnittain
     `metsa_laske.PRICE_AREA` (Kuusamo, Pudasjärvi, Taivalkoski → Kainuu-Koillismaa).
   - Puuston arvo = tukki- ja kuitupuun määrä × Luken kantohinnat hinta-alueittain. Omistajan päätös: **viimeisimmän
     kuukauden** hinnat, jos mahdollista (jos alueen kuukausihinta puuttuu, esim. vähäisen kaupan takia → edellinen
     julkaistu kuukausi; kerrotaan kortissa).
   - Varmistettava kokeessa: tarkka ikä vuosina vs. vain kehitysluokka, kasvupaikka-/maalaji-/ojituskentät, tukki/kuitu-
     jakauma, aineiston kattavuus (myös valtion maat?) ja ikä alueittain.
   - Vertailukohta: UPM-metsä "Selvitä metsäsi arvo" laskee arvon avoimesta datasta kiinteistötunnuksella (yksi kerrallaan);
     meillä kaikki selattavissa kerralla → mainitse tietosuojaselosteessa (kiinteistötunnus → omistaja selvitettävissä MML:stä).
   **Tontit** (rakentamattomat palstat; toinen vaihe):
   - Ala, rantatieto kaikille palstoille (nykyinen laskenta laajennettuna), rakentamaton = ei mitään Ryhti-rakennusta
     (myös saunat, varastot – nyt talteen vain asuinrakennukset; vanhoja pikkurakennuksia voi puuttua rekisteristä),
     asemakaava-alue vai haja-asutus (kaavojen ulkorajat, todennäköisesti avoimena – selvitä).
   - Rakennusoikeus: ei koko maasta. Ryhtiin konemuotoiset kaavat vapaaehtoisesti, pakollisiksi 1.1.2029 (5/2026 vasta
     27 kuntaa sai tallentaa). Siihen asti vain kuntien omat rajapinnat (iso työ/kunta) → aloitetaan ilman ja lisätään
     kunnittain saatavuuden mukaan. Sivulle selvä varoitus: rakentamaton (ranta)palsta ei usein ole rakennuspaikka
     (rantarakentaminen ratkaistaan kaavalla).
   **Toteutusmalli:** oma yöajo/jobi metsälaskennalle (muisti jo 7,6 Gt / 16 Gt), näytetään vain suodatetut kohteet
   (metsätilat > 2 ha, rakennuspaikan kokoiset rakentamattomat palstat), kaukaa pisteet/tiheysruudut ja lähellä rajat.
   Jos tiilet eivät mahdu sivun 1 Gt:hen (nyt ~486 Mt), ne tallennetaan erilliseen GitHub-repoon (oma 1 Gt; sama sivu
   lataa sieltä) tai R2:een.
   **Tammela-koe tehty 6.11.2026** (luvut HISTORIA.md): 1 689 metsätilaa (metsämaata > 2 ha; kokonaisala > 2 ha 2 355),
   puuston arvo mediaani 8 400 €/ha, ajo 2 min. Kokoarvio koko Suomelle ~0,4–0,75 Gt (rajat z10/12–14) → **ei mahdu**
   talojen kanssa sivun 1 Gt:hen → erillinen repo/R2. Omistajan päätökset kokeen jälkeen kirjattu yllä (määritelmä,
   erikoisyksiköt näkyviin, hakkuutavan hinnat + hakkuurajoitus korttiin). **Seuraavaksi:** tuotantoajon suunnitelma
   omistajan hyväksyttäväksi (tallennuspaikka, yöajo, tiilet, piilotettu moodi `?moodi=metsa`).
   **Hyväksytty suunnitelma (6.11.2026):** 1 ✅ yöajo + tiedostot Kanta-Hämeelle Metsakartassa (esikatselu); 2 ✅ tiedostojen
   karsinta + piilotettu moodi Talokartassa (`?moodi=metsa`); 3 laajennus maakunnittain; 4 julkistus omistajan
   hyväksynnällä (tietosuojaseloste ennen; moodivalinnan näyttäminen kaikille = metsa.js:n `params.has("moodi")`-ehto pois).
