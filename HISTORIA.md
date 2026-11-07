# Talokartta – kehityshistoria ja mittaukset

Siirretty CLAUDE.md:stä 6.11.2026 (tiivistys). Tämä on arkisto: mittaukset, koeajot ja päätösten tausta
maakuntien lisäyksistä ja rantatiedosta. Nykytila, rakenne ja avoimet suunnitelmat ovat CLAUDE.md:ssä.
Lue tämä, kun tarvitset vertailulukuja (ajoajat, muisti, tiilikoot) tai päätöksen perustelun.

## Rantatiedon alkuperäinen kuvaus (sis. puron varrella -luokan toteutuksen, pois käytöstä 5.11.2026)

Puron varrella (ra 5, 4.11.2026): MTK `virtavesikapea` (viivat) haetaan samassa vesialuehaussa; vain jos palsta ei ole
    rannassa eikä kiinteistöllä ole erillistä rantapalstaa; puroa ≥ `MIN_STREAM_M` 10 m palstalla tai ≤ `TOL_STREAM` 5 m
    rajasta. Oletuksena vain kohdeluokka 36312 (2–5 m); 36311 (alle 2 m) sisältää ojat → pois, ehdokkaana mutkaisuus
    ≥ 1,1 ja ≥ 100 m (`NARROW_MIN_SINUOSITY`, odottaa omistajan pistokoetta). Laskennan versio `shore.VERSION` (2)
    tallessa kunnittain; vanhemmat kunnat päivitetään `ParcelResults.get(upgrade=…)`: vain yön normaalin kiintiön
    (ceil(N/14)) vapaisiin paikkoihin puuttuvien ja vanhentuneiden jälkeen → ei lisäkuormaa. meta `stream_regions` =
    maakunnat, joissa kaikki kunnat ovat versiossa ≥ 2 (sivu kertoo keskeneräiset). Web: `app.js` RANTA-lohkot (SHORE_*,
    shoreCard, buildShore) ja `index.html` `#shoreSec`. Kokonaan poisto: nämä + `shore.py`, `requirements-shore.txt`,
    workflow-asennusrivi ja selftestin `shore_tests`. Koe-työnkulku "Selvitys – rantatesti" (`shore_explore.py`) erikseen.

## Tiekartta (valmiit vaiheet, alkuperäinen teksti)

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
2. ✅ Koko Suomi (Manner-Suomi 6.11.2026, ks. 2q; Ahvenanmaa ei ole Ryhtissä). Rekisterien kuormitus pidetään pienenä (omistajan toive):
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
2k. ✅ Pohjois-Savo (19 kuntaa: 140, 171, 204, 239, 263, 297, 402, 420, 595, 686, 687, 749, 762, 778, 844, 857, 915, 921, 925)
    5.11.2026 rantatiedon kanssa; ei kuntaliitoksia (Joroinen 171 siirtyi Etelä-Savosta 2021). Ensiajo 1 h 14 min (Ryhti ~5 min,
    palstat + ranta ~66 min; Kuopio 297: 279 s rantaa). 105 795 rakennusta, omalla rannalla 42 750 (40 %).
    Yhteensä 1 406 336 rakennusta (192 kuntaa, 12 maakuntaa), palsta 1 406 335:lle. Tiili 30,0 Mt; tiilet yhteensä ~350 Mt.
    Muistin huippu 5,7 Gt. Rautavaara 687 puuttui alun perin (lisätty 6.11.2026 ajossa 2o; 1 718 rak., ranta 621).
2l. ✅ Pohjanmaa (14 kuntaa: 231, 280, 287, 288, 399, 440, 475, 499, 545, 598, 599, 893, 905, 946) 5.11.2026 rantatiedon
    kanssa; Kruunupyy siirtyi Keski-Pohjanmaalta ja Isokyrö 152 Etelä-Pohjanmaalle 2021. Build 56 min (Ryhti ~4 min, palstat +
    ranta ~49 min; Mustasaari 106 s rantaa, saaristo ei ongelma). 78 685 rakennusta, omalla rannalla 21 526 (27 %).
    Yhteensä 1 485 021 rakennusta (206 kuntaa, 13 maakuntaa), palsta 1 485 020:lle. Tiili 19,6 Mt; tiilet yhteensä ~370 Mt.
    Muistin huippu 6,0 Gt. Ensimmäinen julkaisu jumittui GitHub Pagesissa (`updating_pages` > 10 min, deploy-pages
    aikaraja) → yritettiin 30 min, mutta deploy-pages sallii enintään 600000 ms (10 min) → arvo 600000; peruutetun julkaisun uudelleenajo ("Deployment cancelled") ei toimi samalla versiolla,
    vaan tarvitaan uusi ajo (uusi commit tai käsiajo).
2m. ✅ Etelä-Pohjanmaa (18 kuntaa: 005, 010, 052, 145, 151, 152, 218, 232, 233, 300, 301, 403, 408, 743, 759, 846, 934, 989)
    5.11.2026 rantatiedon kanssa; ei kuntaliitoksia. Build 55 min (Ryhti ~2,5 min, palstat + ranta ~46 min; Seinäjoki 83 s
    rantaa). 89 445 rakennusta, omalla rannalla 15 563 (17 %). Yhteensä 1 574 467 rakennusta (224 kuntaa, 14 maakuntaa),
    palsta 1 574 466:lle. Tiili 23,7 Mt; tiilet yhteensä ~395 Mt. Muistin huippu 6,4 Gt. Pages-julkaisu kesti 3,7 min
    (aiemmin ~20 s) → seuraa; deploy-pagesin aikaraja on enintään 10 min.
2n. ✅ Keski-Pohjanmaa (8 kuntaa: 074, 217, 236, 272, 421, 584, 849, 924) 5.11.2026 rantatiedon kanssa; Kruunupyy siirtyi
    Pohjanmaalle 2021. **Korjattu 6.11.2026:** listassa oli virheellisesti Haapajärvi 069 (kuuluu Pohjois-Pohjanmaahan)
    Kannuksen 217 sijaan; alla olevat luvut ovat ennen korjausta (korjattuna 27 586 rak., ranta 5 810). Build 21 min (Ryhti ~1 min, palstat + ranta ~17 min; Kokkola 56 s rantaa). 28 187 rakennusta, omalla
    rannalla 5 923 (21 %). Yhteensä 1 602 654 rakennusta (232 kuntaa, 15 maakuntaa), palsta 1 602 653:lle. Tiili 7,2 Mt;
    tiilet yhteensä ~400 Mt. Muistin huippu 6,5 Gt. Pages-julkaisu 48 s.
2o. ✅ Pohjois-Pohjanmaa (30 kuntaa: 009, 069, 071, 072, 139, 208, 244, 305, 317, 425, 436, 483, 494, 535, 563, 564, 615,
    625, 626, 630, 678, 691, 746, 748, 785, 791, 832, 859, 889, 977) 5.–6.11.2026 rantatiedon kanssa, samalla korjaukset
    Rautavaara 687 (Pohjois-Savo) ja Kannus 217 (Keski-Pohjanmaa). **Kuntalistat tarkistetaan nyt aina**
    Tilastokeskuksen luokitusta vasten: työnkulku "Selvitys – Ryhti-kentät", kunta `maakunnat`
    (`ryhti_explore.regions_check`, luokitus kunta_1_YYYY0101#maakunta_1_YYYY0101). Aja ennen ja jälkeen maakunnan
    lisäyksen; kaikki 16 lisättyä vastaavat luokitusta (308 kuntaa, 19 maakuntaa v. 2026).
    Build 1 h 29 min (Ryhti 31 kuntaa ~6 min, palstat + ranta 31 kuntaa ~79 min; Oulu 564: 168 s rantaa, Kuusamo 305: 138 s,
    Pudasjärvi 615: 55 s). Haapajärvi siirtyi välimuistista toiseen maakuntaan ilman uudelleenhakua.
    153 223 rakennusta, omalla rannalla 36 759 (24 %; Kuusamo 58 %). Yhteensä 1 756 994 rakennusta (263 kuntaa,
    16 maakuntaa), palsta 1 756 993:lle. Tiili 40,5 Mt; tiilet yhteensä ~440 Mt. **Muistin huippu 7,1 Gt** (1,76 milj. rak.)
    → Kainuu + Lappi arviolta ~7,7 Gt / 16 Gt. Pages-julkaisu 30 s. Jäljellä Kainuu (8 kuntaa) ja Lappi (21).
2p. ✅ Kainuu (8 kuntaa: 105, 205, 290, 578, 620, 697, 765, 777) 6.11.2026 rantatiedon kanssa; ei kuntaliitoksia,
    `maakunnat`-tarkistus OK ennen ajoa (17/17 maakuntaa). Build 31 min (Ryhti ~1,5 min, palstat + ranta ~27 min; Kajaani
    56 s, Kuhmo 54 s rantaa). 39 316 rakennusta, omalla rannalla 16 516 (42 %). Yhteensä 1 796 315 rakennusta (271 kuntaa,
    17 maakuntaa), palsta 1 796 311:lle (4 puuttuu). Tiili 12,4 Mt; tiilet yhteensä ~455 Mt. Muistin huippu 7,3 Gt.
    Jäljellä Lappi (21 kuntaa; arviolta ~110 000 rak.).
2q. ✅ Lappi (21 kuntaa: 047, 148, 240, 241, 261, 273, 320, 498, 583, 614, 683, 698, 732, 742, 751, 758, 845, 851, 854,
    890, 976) 6.11.2026 rantatiedon kanssa; ei kuntaliitoksia, `maakunnat`-tarkistus OK (18/18). Build 1 h 15 min (Ryhti
    ~4 min, palstat + ranta ~66 min; Inari 148: 180 s rantaa / 37 351 vesialuetta, Rovaniemi 97 s, Utsjoki 15 096
    vesialuetta 48 s). 102 279 rakennusta, omalla rannalla 36 612 (36 %). **Koko Manner-Suomi valmis:** 1 898 604
    rakennusta (292 kuntaa, 18 maakuntaa), palsta 1 898 595:lle (9 puuttuu). Tiili 30,3 Mt; tiilet yhteensä ~486 Mt / 1 Gt.
    Muistin huippu 7,6 Gt / 16 Gt. Ensimmäinen deploy jumittui taas (Timeout 10 min) → käsiajo (välimuistilla build 7 min,
    deploy 30 s) julkaisi. Jos Pages-jumit yleistyvät: harkitse deployn automaattista uudelleenyritystä (uusi ajo).
3. ✅ Ilmoitus omistajalle, jos yöajo epäonnistuu (3.11.2026, GitHub-issue + sähköposti).
3b. ✅ Automaattinen sivun tarkistus julkaisun jälkeen (6.11.2026). `check/sivutarkistus.mjs` (Node 22 + Playwright 1.63
    + Chromium), työnkulku `check-site.yml` ("Tarkista sivu": käsin + `workflow_call`), yöajossa jobi `check`
    (`needs: [build, deploy]`, saa buildin meta.json:n `updated` ja `count`). Tarkistaa 17 kohtaa: meta.json-versio
    (odottaa Pages-välimuistia enintään 6 × 30 s), määrä = maakuntien summa, 19 pmtiles-tiedostoa (Range → 206 +
    "PMTiles" v3 -otsake), sivun lataus, taustakartta (tasoja > 20, OpenFreeMap-tiiliä > 0), maakuntatasot, tiheysruudut,
    paneelin laskuri ja päivitysaika, rakennuksia Tampereella z15 / Tammelassa z14 / Kalliossa z15 / Rovaniemellä z14,
    tietokortti (eristetyin rakennus, jolla osoite ja palstan ala; osoite ja ala kortissa), puhelin 390 × 844: jaettu
    linkki `#kartta=` ja Suodattimet-nappi avaa paneelin, JS-virheet (`pageerror`), epäonnistuneet lataukset (fontit
    ja ERR_ABORTED ohitetaan). Epäonnistuessa uusi yritys 60 s päästä; vasta toinen virhe hälyttää (`::error`, max 8).
    Kuvakaappaukset (työpöytä Suomi + kortti, puhelin kartta + suodattimet) ajon liitteenä `sivutarkistus` 14 pv.
    Koeajot 6.11.: erillinen ajo 17/17 OK (tarkistus 43 s, jobi ~2 min asennuksineen), tahallinen virhe
    (`osoite` = olematon polku) → annotaatio "meta.json: meta.json ei latautunut", exit 1; push-ajo build 9 min →
    deploy 50 s → check 2 min 8 s (näki uuden version heti) → notify OK. Clauden kone ei voi ladata ajon liitteitä
    (blob-tallennus estetty proxyssa) → kuvat katsoo omistaja; lokin ✓/✗-rivit riittävät Claudelle.
6. Metsätilat – Tammela-koe 6.11.2026 (koeajo "Selvitys – metsätilat": `metsa_explore.py` vaihe `rakenne`, `metsa_laske.py`
    vaihe `laske`; ajot 42219899316, 42221250166). Metsäkeskuksen uusi tietomalli (1.9.2026): MV_Tammela.zip 53 Mt
    (GPKG 126 Mt, lataus 3 s), 32 180 kuviota, 100 487 puustotietoa, 185 518 ositetta; puulajijako ositteista 31 962
    kuviolla, pääpuulajista 214, ilman puustoa 4. MML-kuntatiedosto 37,9 Mt: 10 831 palstaa / 8 687 kiinteistöä
    (+ naapurikuntien rajapalstat); ei rekisteriyksikkölajia. Kuvioala kunnan kiinteistöillä 45 063 ha (kiinteistöjen
    ulkopuolella ~0 %). Luke 0100_teokau toimii (PxWeb v1, json-stat2), viimeisin kuukausi 2026M09; Etelä-Suomen
    pystykauppa €/m³: mäntytukki 78,12, kuusitukki 84,11, koivutukki 61,86, kuitu 22,39 / 24,51 / 22,33.
    Tulokset: kokonaisala > 2 ha 2 355 kiinteistöä (62 291 ha); metsämaata > 2 ha 1 689 (metsämaa 43 255 ha, puuta
    7,91 milj. m³ ≈ 183 m³/ha, arvo 424 M€, mediaani 8 401 €/ha, 10 %/90 % 2 771 / 17 305 €/ha); kokoluokat 2–5 ha 491,
    5–10 ha 417, 10–20 ha 366, 20–50 ha 302, 50–100 ha 67, yli 100 ha 44. Asuinrakennus tilalla 646. Metsätietoa alle 50 %
    alasta 204 tilalla. Hakkuurajoitus (restriction) keskim. 1,5 %, yli 50 % 15 tilalla (esim. 834-891-1-3 100 %).
    Suurimmat ovat erikoisyksiköitä (834-874-1-0 5 150 ha, 63 palstaa, 141 asuinrakennusta; 834-891/893) → selvitettävä.
    Karttatiedostokoe (tippecanoe, 1 m yleistys, 70 379 kärkipistettä): rajat z12–14 1,30 Mt, z10–14 1,72 Mt, pisteet
    z6–11 0,13 Mt. Pinta-alan mukaan koko Suomi (~430 × Tammela) ~0,56 / 0,74 Gt + pisteet ~0,06 Gt (yläarvio; pohjoisessa
    tilat isompia) → ei mahdu talojen kanssa 1 Gt:n sivuun. Koko ajo 126 s, muisti pieni.
    Huom: ajon liitteitä (Excel) Claude ei voi ladata; Claude kokosi saman Excelin lokiin pakatusta CSV:stä.
6a. ✅ Metsakartta vaihe 1 (6.11.2026): repositorio vv-tec/Metsakartta (omistaja loi, valinta A: oma MML-avain ja
    palstalataukset), `pipeline/metsa.py`, `metsa_web/`. Ensimmäinen ajo kaatui (KeyError 'ia': nollat jätetään
    välimuistista pois → `rec.get`), välimuisti tallessa → toinen ajo 10 s + julkaisu 5,5 min yhteensä.
    Kanta-Häme 11 kuntaa haku 23 min: Hämeenlinna 103 551 kuviota / 42 716 palstaa / 5 953 tilaa 576 s (MML 491 s),
    muut 51–133 s; Metsäkeskus 2–19 s/kunta. 16 728 metsätilaa. f-kanta-hame.pmtiles 23,0 Mt (z11–14, ~35 ominaisuutta),
    fp.pmtiles 7,4 Mt (z6–10, -r1). Muisti 127 Mt + tippecanoe 135 Mt. Pinta-alan mukaan koko Suomi (~58 × Kanta-Häme)
    ~1,3 Gt + 0,4 Gt → ennen laajennusta karsittava: tietokortin tiedot erilliseen kuntakohtaiseen JSONiin (tiileen vain
    värityksen ja suodattimien kentät), pisteille harvemmat zoomit / tiheysruudut.
6b. Metsakartta 6.11.2026 ilta: omistajan palautteesta pistetaso pois (taustakartta ei erottunut) ja esikatseluun
    suodattimet (kokonaisala, puuston arvo, metsäpohja, ikäjakauma). Selaintarkistus Metsakartan jobiksi: Tammela z12
    293 tilaa, kokonaisala ≥ 50 ha → 33, + uudistuskypsää ≥ 50 % → 1, tyhjennys → 293; kortti ja ei JS-virheitä.
    Julkaisu jumittui kahdesti (deployment_queued, sama commit-versio peruutuksen jälkeen) → uusi commit → onnistui.
    Tiedostot: f-kanta-hame.pmtiles 23,0 Mt (fp 7,4 Mt poistui).
6c. Metsakartta vaihe 2 (6.11.2026): (a) tiileen vain suodatin-/värikentät + kortit kuntakohtaisiin JSONeihin + rajat
    z13 asti: f-kanta-hame 25,7 → 9,1 Mt, kortit 3,0 Mt (11 kuntaa), julkaisu 4 s. Koko Suomi arvio ~0,7 Gt.
    (b) Talokartan piilotettu metsätilanäkymä `?moodi=metsa` (web/metsa.js), tarkistus laajennettu Talokarttaan.
6d. Metsakartta vaihe 3 alkaa (7.11.2026): Uusimaa lisätty. 26 kuntaa yhdessä ajossa 3 487 s (58 min, budjetti 150 min):
    Lohja 444 3 398 tilaa 433 s (MML 382 s), Espoo 049 594 tilaa, Helsinki 091 103 tilaa 200 s, Kauniainen 235 2 tilaa, Raasepori 710
    70 476 kuviota / 2 997 tilaa 229 s; Metsäkeskus 1–15 s/kunta, MML 33–382 s. Uusimaa 27 326 tilaa,
    f-uusimaa.pmtiles 15,9 Mt; kortit 37 kuntaa 7,9 Mt; muistin huippu 710 Mt. Kaikki MV_<Kunta>.zip löytyivät
    (lisätty varatapa: puuttuva tiedosto → varoitus, kunta 0 tilaa). Selaintarkistukset kaikki ✓.
    Pirkanmaa 7.11.2026: 23 kuntaa 3 011 s (50 min). Sastamala 790 86 323 kuviota / 6 139 tilaa 380 s (MML 326 s),
    Tampere 837 1 589 tilaa 226 s, Virrat 936 3 232, Ylöjärvi 980 2 957; muut 54–207 s. Kuhmoisen nimen kommentin
    sulkulisätieto olisi estänyt MV-tiedoston löytymisen → korjattu ennen ajoa (1 874 tilaa). Pirkanmaa 44 264 tilaa,
    f-pirkanmaa 24,6 Mt; kaikki yhteensä 88 318 tilaa, f 49,6 Mt + kortit 15,9 Mt; muisti 692 Mt. Tarkistukset ✓.
