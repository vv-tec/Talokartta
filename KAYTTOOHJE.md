# Talokartta – käyttöohje omistajalle

Tämä ohje on sinulle, palvelun omistajalle. Siinä kerrotaan, miten palvelu toimii, mitä sinun pitää (ja ei tarvitse)
tehdä, mitä ilmoitukset tarkoittavat ja missä tärkeät tunnukset ovat. Ohjelmointia ei tarvita.
Kehittäjän (Clauden) tekninen muistio on tiedostossa [CLAUDE.md](CLAUDE.md).

- **Sivu:** https://vv-tec.github.io/Talokartta/
- **Koodi ja asetukset:** https://github.com/vv-tec/Talokartta
- **Päivitetty viimeksi:** 6.11.2026 (Claude päivittää tämän ohjeen, kun toiminta muuttuu)

---

## 1. Miten palvelu toimii lyhyesti

```
Ryhti (SYKE): rakennukset, osoitteet ──┐
                                       ├─> yöajo GitHubissa ─> karttatiedostot ─> sivu (GitHub Pages)
Maanmittauslaitos: tontit ─────────────┘     noin klo 4–6
```

- **Joka yö** GitHub ajaa päivityksen automaattisesti. Tiedot haetaan eri rytmeissä:

  | Mitä | Mistä | Kuinka usein |
  |---|---|---|
  | Muuttuneet rakennukset ja osoitteet | Ryhti (SYKE) | joka yö, vain edellisen yön jälkeen muuttuneet |
  | Uusien rakennusten tonttitieto | Maanmittauslaitos | joka yö, pieni aluehaku vain uusien rakennusten kohdalta |
  | Kunnan kaikki rakennukset ja osoitteet (varmistus) | Ryhti | kerran kuukaudessa, muutama kunta joka yö |
  | Kunnan kaikkien tonttien rajat | Maanmittauslaitos | kerran kahdessa viikossa, noin 1/14 kunnista joka yö |

  Yöajo kestää noin 20–25 minuuttia, josta suurin osa on tonttien latausta (rantalaskenta samoista tonteista noin 4 min). Uuden rakennuksen kiinteistön kokonaisala
  voi tarkentua vasta kunnan seuraavassa täydessä tonttihaussa (enintään kahden viikon päästä).
- **Sivu** on pelkkiä tiedostoja, ei omaa palvelinta tai tietokantaa. Siksi palvelu on ilmainen ja kestää paljon käyttäjiä.
- **Jos yöajo epäonnistuu,** sivulle jää edellinen toimiva versio. Mitään ei mene rikki – tiedot vain eivät päivity sinä yönä.
- **Sivun tarkistus:** julkaisun jälkeen GitHub avaa sivun automaattisesti oikeassa selaimessa (työpöytä- ja puhelinkoossa)
  ja katsoo, että se toimii kuten sinulla: kartta ja taustakartta latautuvat, Tampereella, Tammelassa, Helsingin Kalliossa
  ja Rovaniemellä näkyy taloja, talon tietokortti aukeaa osoitteineen ja tontin aloineen, puhelimen Suodattimet-nappi
  toimii eikä sivulla ole virheitä. Jos jokin ei toimi, saat ilmoituksen (kohta 4). Tarkistus kestää noin 2 minuuttia.
- Sivun suodatinpaneelin alareunassa näkyy, milloin tiedot on viimeksi päivitetty.

**Mukana nyt (6.11.2026): koko Manner-Suomi** – kaikki 18 maakuntaa (Uusimaa, Varsinais-Suomi, Kanta-Häme, Pirkanmaa,
Päijät-Häme, Satakunta, Keski-Suomi, Kymenlaakso, Etelä-Karjala, Etelä-Savo, Pohjois-Karjala, Pohjois-Savo, Pohjanmaa,
Etelä-Pohjanmaa, Keski-Pohjanmaa, Pohjois-Pohjanmaa, Kainuu ja Lappi) – 292 kuntaa, 1 898 604 asuinrakennusta.
Ahvenanmaa puuttuu (ks. kohta 6).

---

## 2. Mitä sinun tarvitsee tehdä

**Normaalisti ei mitään.** Palvelu päivittyy itsestään.

Kun saat sähköpostin otsikolla **"Talokartan päivitys epäonnistui"** tai **"Talokartan sivun tarkistus löysi
ongelman"**, katso kohta 4.

Hyvä tapa: avaa sivu silloin tällöin ja katso, että päivitysaika on tuore (enintään vuorokauden vanha).

---

## 3. Mistä näet tilanteen GitHubissa

Avaa https://github.com/vv-tec/Talokartta (kirjaudu sisään).

| Välilehti | Mitä siellä on |
|---|---|
| **Actions** | Kaikki ajot. Vihreä ✓ = onnistui, punainen ✗ = epäonnistui, keltainen pyörivä = käynnissä. |
| **Issues** | Ilmoitukset epäonnistuneista ajoista. Avoin ilmoitus = viimeisin ajo epäonnistui. Ilmoitus sulkeutuu itsestään, kun seuraava ajo onnistuu. |
| **Code** | Koodi, tämä ohje, kehittäjän muistio (CLAUDE.md) ja kehityshistoria mittauksineen (HISTORIA.md). |

Ajon yksityiskohdat: Actions → klikkaa ajoa → klikkaa **build** → avautuu loki.
Lokin lopussa näkyy esimerkiksi rakennusten määrä ja karttatiedostojen koot.

---

## 4. Kun saat ilmoituksen epäonnistuneesta ajosta

Ilmoituksessa (GitHubin Issues ja sähköposti) lukee **Kohta** (mikä vaihe epäonnistui), usein myös **Syy**, ja linkki ajon lokiin.

| Syy tai tilanne | Mitä tehdä |
|---|---|
| Yksittäinen epäonnistuminen, syy esim. yhteysvirhe tai "HTTP 500/502/503" | Ei mitään. Rekisteri oli todennäköisesti hetken katkolla. Seuraava yöajo yrittää uudelleen. Jos haluat heti, käynnistä ajo käsin (kohta 5). |
| Sama ilmoitus useana yönä peräkkäin (ilmoitukseen tulee uusia kommentteja) | Pyydä Claudea selvittämään: kerro ilmoituksen numero tai liitä sen teksti. |
| **"Turvatarkistus esti julkaisun"** | Jonkin kunnan rakennusmäärä putosi yhdessä yössä yli 5 % tai maakunta olisi pudonnut sivulta. Yleensä kyse on rekisterin häiriöstä, joka korjaantuu itsestään. Jos sama toistuu, pyydä Claudea katsomaan. Ohita tarkistus (kohta 5) vain, jos tiedät pudotuksen olevan todellinen. |
| Syy mainitsee **401** tai **403** ja Maanmittauslaitoksen | API-avain ei kelpaa. Katso kohta 7, "Maanmittauslaitoksen API-avain". |
| "on X Mt, yli GitHub Pagesin rajan" | Jokin karttatiedosto kasvoi liian suureksi. Pyydä Claudea jakamaan alue pienempiin osiin. |
| Kohta on **deploy** (julkaisu), syy esim. "Timeout reached" | GitHub Pages jumittui sivua päivittäessään (sattunut 5.11. ja 6.11.2026). Ei mitään: seuraava yöajo julkaisee. Jos haluat heti, käynnistä ajo käsin (kohta 5). |
| "Koe-epäonnistuminen" | Testiajo, joka pysäytettiin tarkoituksella. Ei toimenpiteitä. |
| Otsikko **"Talokartan sivun tarkistus löysi ongelman"** (kohta **check / sivu**) | Tiedot päivittyivät, mutta automaattinen tarkistus huomasi, ettei kaikki sivulla toimi. Syy kertoo mikä, esim. "Taustakartta" (OpenFreeMap katkolla), "JavaScript-virheet" tai "Rovaniemen keskusta: ei yhtään rakennusta". Avaa sivu itse ja katso. Kuvakaappaukset: ajon sivun alareunassa **Artifacts → sivutarkistus** (zip). Tarkistus yrittää jo kahdesti, joten tilapäinen katko ei hälytä. Pyydä Claudea selvittämään ja liitä ilmoituksen teksti. |

---

## 5. Ajon käynnistäminen käsin

1. GitHub → **Actions** → vasemmalta **Päivitä tiedot ja julkaise**.
2. Oikealta **Run workflow** → avautuu valikko.
3. Jätä valinnat tyhjiksi ja paina vihreää **Run workflow** -nappia.
4. Ajo ilmestyy listaan muutamassa sekunnissa. Ajo kestää 3–20 minuuttia sen mukaan, montako kunnan tontteja on vuorossa.

Valikon valinnat (jätä normaalisti tyhjiksi):

- **koe_virhe** – pysäyttää ajon tarkoituksella. Vain ilmoituksen testaamiseen; saat testisähköpostin.
- **ohita_tarkistukset** – julkaisee, vaikka turvatarkistus huomauttaisi. Käytä vain, kun tiedät rakennusmäärän
  pudotuksen olevan todellinen (esim. kunta on poistettu asetuksista tarkoituksella).

**Sivun tarkistus käsin** (esim. jos sivu tuntuu oudolta): Actions → vasemmalta **Tarkista sivu** → **Run workflow** →
jätä osoite tyhjäksi → **Run workflow**. Noin 2 minuutissa vihreä ✓ = sivu toimii. Tulokset näet klikkaamalla ajoa:
taulukko ✅/❌ ja alareunassa kuvakaappaukset (**sivutarkistus**). Tämä ei päivitä tietoja eikä kuormita rekistereitä.

Muut ajot Actions-välilehdellä (**Selvitys – …**) ovat Clauden koeajoja. Ne eivät vaikuta sivuun.

---

## 6. Uuden maakunnan lisääminen

Kaikki Manner-Suomen maakunnat ovat mukana (6.11.2026), joten tätä tarvitaan vain, jos maakuntajako muuttuu tai
maakunta on poistettu ja halutaan takaisin. Pyydä Claudea, esimerkiksi: *"Lisää Lappi."*

- Claude lisää maakunnan kunnat asetuksiin, ja ensimmäinen ajo alkaa heti.
- Ensimmäinen ajo kestää noin 30–110 minuuttia (tontit ladataan Maanmittauslaitokselta kunta kerrallaan).
- Uusi maakunta tulee sivulle vasta, kun kaikki sen kuntien tiedot ovat valmiina. Jos ajo ei ehdi kerralla, se
  jatkuu seuraavana yönä. Muut maakunnat päivittyvät sillä välin normaalisti.
- Kuntalista: Claude tarkistaa sen automaattisesti Tilastokeskuksen virallisesta kunta–maakuntaluokituksesta
  (selvitysajo "Selvitys – Ryhti-kentät", kunta `maakunnat`). Tarkistus löysi 5.11.2026 kaksi Clauden virhettä
  (Rautavaara puuttui Pohjois-Savosta, Keski-Pohjanmaalla oli Haapajärvi Kannuksen tilalla); korjattu 6.11.2026.
- Kuntaliitokset: Claude tarkistaa kuntalistan ajantasaisesta maakuntajaosta. Esimerkiksi Pertunmaa liitettiin
  Mäntyharjuun 1.1.2025, joten sen talot ovat Mäntyharjun mukana. Jos kunnan talomäärä kasvaa liitoksen takia, tontit
  haetaan sille automaattisesti uudelleen.
- Yhteen ajoon mahtuu noin 30 kuntaa (1–2 keskikokoista maakuntaa; Pohjois-Pohjanmaa, 31 kuntaa Oulu mukaan lukien, vei 1 h 29 min;
  Lappi, 21 kuntaa, 1 h 15 min).
- **Rantatieto** lasketaan oletuksena samalla, koska se on käytössä kaikissa nykyisissä maakunnissa (lisää ensiajoon
  noin 10–20 %). Jos et halua sitä uudelle maakunnalle, mainitse pyynnössä: *"Lisää Lappi ilman rantatietoa."*

Puuttuu vain Ahvenanmaa: sillä on oma rakennusrekisterinsä (se ei ole Ryhtissä), joten sen tiedot on selvitettävä erikseen.

---

## 7. Tunnukset, avaimet ja asetukset

Nämä ovat palvelun "avaimet". **Älä koskaan liitä avaimia tai salasanoja keskusteluun Clauden kanssa.**

### GitHub-tili (vv-tec)
- Koko palvelu on tämän tilin alla. Varmista, että tilillä on **kaksivaiheinen tunnistautuminen**:
  GitHub → oikean yläkulman kuva → **Settings → Password and authentication → Two-factor authentication**.
- Tallenna GitHubin varakoodit (recovery codes) turvalliseen paikkaan.

### Maanmittauslaitoksen API-avain
- Tarvitaan tonttien ja vesialueiden hakuun. Avain on GitHubissa salaisuutena nimellä **MML_API_KEY**:
  repositorio → **Settings → Secrets and variables → Actions**. Arvoa ei näe enää tallennuksen jälkeen (näin pitääkin olla).
- Jos avain lakkaa toimimaan tai haluat vaihtaa sen:
  1. Kirjaudu Maanmittauslaitoksen **OmaTiliin** ja luo uusi API-avain avoimille rajapinnoille.
  2. GitHub → repositorio → **Settings → Secrets and variables → Actions** → **MML_API_KEY** → kynäkuvake → liitä uusi avain → **Update secret**.
     **Tee sama myös Metsakartta-repositoriossa** (https://github.com/vv-tec/Metsakartta), jossa on oma kopio avaimesta.
  3. Käynnistä ajo käsin (kohta 5) ja katso, että se onnistuu.
- Jos avain puuttuu, palvelu käyttää hitaampaa varatapaa tonteille.

### Clauden oikeus repositorioon
- Claude tekee muutokset GitHub-sovelluksen kautta. Oikeudet näet: GitHub → **Settings → Applications → Installed GitHub Apps**.
  Suositus: oikeus vain tähän repositorioon (*Only select repositories*).

### GitHub Pages
- Julkaisuasetus: repositorio → **Settings → Pages → Source: GitHub Actions**. Tätä ei tarvitse muuttaa.

---

## 8. Kun jatkat kehitystä Clauden kanssa

- **Aloita uusi keskustelu** isommille uusille asioille. Kirjoita alkuun esimerkiksi:
  *"Jatketaan Talokartta-projektia (GitHub vv-tec/Talokartta). Lue ensin CLAUDE.md ja KAYTTOOHJE.md."*
- **Pyydä kirjaamaan päätökset** suunnitelmaan (CLAUDE.md). Keskusteluun jääneet päätökset unohtuvat.
  Suunnitelma pidetään tiiviinä; vanhat mittaukset ja taustat siirretään HISTORIA.md:hen (tiivistetty 6.11.2026).
- **Tallenna itsellesi tiedostot**, joita haluat säilyttää (esim. Claudelta saadut Excelit) – Clauden työkone on väliaikainen.
- Pyydä isoista muutoksista silloin tällöin **erillinen katselmointi** uudessa keskustelussa.
- Tarkista uudet ominaisuudet itse sivulta: Claude kertoo aina, mitä avata ja mitä pitäisi näkyä.

---

## 9. Kulut ja rajat

- **Kulut:** 0 €. GitHub Actions ja GitHub Pages ovat ilmaisia julkiselle repositoriolle; rekisterien avoin data on maksutonta.
- **GitHub Pagesin rajat:** koko sivusto enintään 1 Gt (nyt noin 485 Mt), yksittäinen tiedosto enintään 100 Mt
  (suurin, Uusimaa, noin 63 Mt). Koko Manner-Suomi (1,9 miljoonaa rakennusta) mahtuu siis hyvin.
- **Kävijämäärä:** GitHub Pagesin siirtomäärän suositusraja on 100 Gt kuukaudessa (arviolta 10 000–50 000 käyntiä).
  Jos sivun käyttö kasvaa tätä suuremmaksi, karttatiedostot siirretään Cloudflare R2 -palveluun (ilmainen siirto).
- **Ulkoiset palvelut, joista sivu riippuu:** OpenFreeMap (taustakartta) ja unpkg (karttakirjastot). Jos jompikumpi on
  katkolla, sivu ei toimi kunnes palvelu palaa. Yöllinen sivun tarkistus huomaa tällaisen katkon ja ilmoittaa siitä.

---

## 10. Rantatieto ("oma ranta")

- Sivulla on suodatin **Ranta** (Oma ranta / Erillinen rantapalsta / Ei rantaa / Ei laskettu)
  ja talon tietokortissa osio **Ranta**. Tieto lasketaan kiinteistörajoista ja Maanmittauslaitoksen vesialueista.
- **Oma ranta** = tontti ulottuu veteen, tai välissä on vain vesijättöä (ei toisen kiinteistön maata). **Erillinen
  rantapalsta** = kiinteistön toinen palsta on rannassa. **Ei omaa rantaa** = välissä on esim. naapuri, yhteinen ranta-alue,
  rantapuisto tai tie, tai vesi on kaukana.
- **Puron varrella -luokka poistettiin 5.11.2026.** Pistokokeessasi (Tammela, 18 kohdetta) yksikään uoma ei ollut puro:
  myös 2–5 m leveät olivat "suuria ojia". Maanmittauslaitoksen aineisto ei erota puroa ojasta, joten luokkaa ei näytetä
  eikä uomia enää haeta. Toiminto on vain kytketty pois (asetus `STREAMS_ENABLED`), joten sen voi palauttaa, jos
  löytyy aineisto, joka erottaa oikeat purot.
- Lammet: myös alle hehtaarin lammet ovat mukana (Tammelassa noin 200 rantataloa).
- Rajoitukset: tieto ei kerro vesialueen omistuksesta eikä rannan laadusta; uusi rakennus saa
  rantatiedon kahden viikon sisällä.
- **Käytössä kaikissa nykyisissä maakunnissa** (4.11.2026). Omalla rannalla (oma ranta tai vesijättö):

  | Maakunta | Omalla rannalla | Osuus |
  |---|---|---|
  | Kanta-Häme | 17 324 / 72 949 | 24 % |
  | Pirkanmaa | 52 947 / 173 791 | 30 % |
  | Päijät-Häme | 22 412 / 76 110 | 29 % |
  | Satakunta | 20 491 / 96 626 | 21 % |
  | Uusimaa | 38 476 / 288 487 | 13 % |
  | Varsinais-Suomi | 47 662 / 173 260 | 28 % |
  | Keski-Suomi | 41 199 / 110 542 | 37 % |
  | Kymenlaakso | 16 204 / 65 788 | 25 % |
  | Etelä-Karjala | 21 769 / 61 466 | 35 % |
  | Etelä-Savo | 53 808 / 95 723 | 56 % |
  | Pohjois-Karjala | 30 700 / 85 789 | 36 % |
  | Pohjois-Savo | 43 371 / 107 513 | 40 % |
  | Pohjanmaa | 21 526 / 78 685 | 27 % |
  | Etelä-Pohjanmaa | 15 563 / 89 445 | 17 % |
  | Keski-Pohjanmaa | 5 810 / 27 586 | 21 % |
  | Pohjois-Pohjanmaa | 36 759 / 153 223 | 24 % |
  | Kainuu | 16 516 / 39 316 | 42 % |
  | Lappi | 36 612 / 102 279 | 36 % |
  | **Yhteensä** | **noin 538 900 / 1 898 604** | **28 %** |

- Rantatieto päivittyy kunnan tonttien kanssa kahden viikon välein; laskenta lisää yöajoon noin 4 minuuttia.
- Uudelle maakunnalle rantatieto lasketaan oletuksena samalla, kun maakunta lisätään (kohta 6).
- **Poistaminen käytöstä:** pyydä Claudea *"Poista rantatieto käytöstä"* – se on yksi asetus (`SHORE_REGIONS` tyhjäksi),
  ja tieto katoaa sivulta seuraavassa ajossa. Muu palvelu ei muutu.

## 11. Avoimet asiat ja suunnitelmat (6.11.2026)

- **Tietosuojaseloste** – tehtävä ennen kuin palvelusta kerrotaan laajemmin (osoitteet ja kiinteistötunnukset voidaan yhdistää ihmisiin).
- Osoitehaku, oma verkko-osoite. (Kaikki Manner-Suomen maakunnat lisätty 6.11.2026.)
- **Metsätilat ja tontit** (metsätilojen vaihe 1 tehty 6.11.2026, ks. kohta 12): sivulle uudet toimintamoodit Talot | Metsätilat | Tontit.
  Metsätila = kiinteistö, jolla yli 2 ha metsämaata; haku mm. alan, **puuston arvon** (viimeisimmän kuukauden kantohinnoilla),
  ikärakenteen ja metsäpohjan mukaan. Tontit-moodissa rakentamattomat palstat alan ja rantatiedon mukaan; rakennusoikeus
  vasta, kun kunnat vievät kaavat Ryhtiin (pakollista 2029). Tarkempi suunnitelma: CLAUDE.md, tiekartan kohta 6.
  - **Tammela-koe tehty 6.11.2026** (koeajo Actions → **Selvitys – metsätilat**, ei vaikuta sivuun). Tulos on Excel
    `metsatilat_834.xlsx`: ajon sivun alareunassa **Artifacts → metsatilat-834** (zip). Tammelassa 1 689 metsätilaa
    (metsämaata yli 2 ha), puuston arvon mediaani noin 8 400 €/ha. Päätöksesi 6.11.2026: rajaus "metsämaata yli 2 ha";
    yhteismetsät ja suojelualueet jäävät näkyviin; tietokorttiin hakkuurajoituksen osuus ja arvo hakkuutavan hinnoin
    pienellä selitteellä.
  - Myöhemmin (ei ensimmäiseen versioon): metsätilojen rantatieto sekä pellot ja suot erikseen (nyt ne ovat "muuta alaa").

## 12. Metsakartta (metsätilat)

Metsätilat (kiinteistöt, joilla metsämaata yli 2 ha) lasketaan ja julkaistaan omassa repositoriossa **Metsakartta**,
koska niiden karttatiedostot eivät mahdu Talokartan sivun 1 Gt:n rajaan. Ohjelmakoodi on silti Talokartassa.

- **Esikatselu:** https://vv-tec.github.io/Metsakartta/ – kartta, jossa metsätilat on väritetty puuston arvon (€/ha) mukaan.
  Kauempaa pisteet, lähempää (zoom 11+) tilan rajat. Klikkaa tilaa: tietokortti (puuston arvo ja arvo hakkuutavan
  hinnoin, alat, hakkuurajoitus, puusto puulajeittain, ikärakenne, metsäpohja, linkit Karttapaikkaan ja Talokarttaan).
  Sivu on vain tarkistusta varten; metsätilat tulevat Talokarttaan omaksi näkymäkseen myöhemmin.
- **Mukana nyt (6.11.2026):** Kanta-Häme, 11 kuntaa, 16 728 metsätilaa.
- **Päivitys:** joka aamu noin klo 6.47 (Talokartan yöajon jälkeen). Kunnan metsätiedot ja tontit haetaan uudelleen
  kuukauden välein, muutama kunta kerrallaan; kantohinnat (Luke) joka ajossa uusimmasta julkaistusta kuukaudesta.
  Ajo kestää yleensä muutaman minuutin.
- **Ilmoitukset:** epäonnistunut ajo avaa Metsakartan **Issues**-välilehdelle ilmoituksen "Metsakartan päivitys
  epäonnistui" (sähköposti). Toimi kuten kohdassa 4. Julkaistuna pysyy edellinen toimiva versio.
- **Käsiajo:** https://github.com/vv-tec/Metsakartta → **Actions** → **Päivitä metsätilat ja julkaise** → **Run workflow**.
- **Avain:** Metsakartassa on oma `MML_API_KEY`-salaisuus. Jos vaihdat avaimen, päivitä se molempiin (kohta 7).
- **Uusi maakunta:** pyydä Claudea (*"Lisää metsätiloihin Pirkanmaa"*). Ennen koko Suomea karttatiedostoja on
  pienennettävä: Kanta-Häme vie jo noin 30 Mt, koko Suomi veisi nykyisellään yli 1 Gt.

## Lähteet ja lisenssit

- Rakennukset ja osoitteet: Suomen ympäristökeskus (SYKE), Ryhti, CC BY 4.0
- Kiinteistöpalstat ja vesialueet: Maanmittauslaitos, kiinteistörekisterikartta ja maastotietokanta, CC BY 4.0
- Taustakartta: OpenFreeMap, © OpenStreetMapin tekijät (ODbL)
- Kartassa ei ole omistajatietoja.
