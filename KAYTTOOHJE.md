# Talokartta – käyttöohje omistajalle

Tämä ohje on sinulle, palvelun omistajalle. Siinä kerrotaan, miten palvelu toimii, mitä sinun pitää (ja ei tarvitse)
tehdä, mitä ilmoitukset tarkoittavat ja missä tärkeät tunnukset ovat. Ohjelmointia ei tarvita.
Kehittäjän (Clauden) tekninen muistio on tiedostossa [CLAUDE.md](CLAUDE.md).

- **Sivu:** https://vv-tec.github.io/Talokartta/
- **Koodi ja asetukset:** https://github.com/vv-tec/Talokartta
- **Päivitetty viimeksi:** 4.11.2026 (Claude päivittää tämän ohjeen, kun toiminta muuttuu)

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
- Sivun suodatinpaneelin alareunassa näkyy, milloin tiedot on viimeksi päivitetty.

**Mukana nyt (4.11.2026):** Uusimaa, Varsinais-Suomi, Kanta-Häme, Pirkanmaa, Päijät-Häme, Satakunta, Keski-Suomi ja
Kymenlaakso – 141 kuntaa, 1 057 553 asuinrakennusta.

---

## 2. Mitä sinun tarvitsee tehdä

**Normaalisti ei mitään.** Palvelu päivittyy itsestään.

Kun saat sähköpostin otsikolla **"Talokartan päivitys epäonnistui"**, katso kohta 4.

Hyvä tapa: avaa sivu silloin tällöin ja katso, että päivitysaika on tuore (enintään vuorokauden vanha).

---

## 3. Mistä näet tilanteen GitHubissa

Avaa https://github.com/vv-tec/Talokartta (kirjaudu sisään).

| Välilehti | Mitä siellä on |
|---|---|
| **Actions** | Kaikki ajot. Vihreä ✓ = onnistui, punainen ✗ = epäonnistui, keltainen pyörivä = käynnissä. |
| **Issues** | Ilmoitukset epäonnistuneista ajoista. Avoin ilmoitus = viimeisin ajo epäonnistui. Ilmoitus sulkeutuu itsestään, kun seuraava ajo onnistuu. |
| **Code** | Koodi, tämä ohje ja kehittäjän muistio. |

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
| "Koe-epäonnistuminen" | Testiajo, joka pysäytettiin tarkoituksella. Ei toimenpiteitä. |

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

Muut ajot Actions-välilehdellä (**Selvitys – …**) ovat Clauden koeajoja. Ne eivät vaikuta sivuun.

---

## 6. Uuden maakunnan lisääminen

Pyydä Claudea, esimerkiksi: *"Lisää Etelä-Savo."*

- Claude lisää maakunnan kunnat asetuksiin, ja ensimmäinen ajo alkaa heti.
- Ensimmäinen ajo kestää noin 30–110 minuuttia (tontit ladataan Maanmittauslaitokselta kunta kerrallaan).
- Uusi maakunta tulee sivulle vasta, kun kaikki sen kuntien tiedot ovat valmiina. Jos ajo ei ehdi kerralla, se
  jatkuu seuraavana yönä. Muut maakunnat päivittyvät sillä välin normaalisti.
- Yhteen ajoon mahtuu noin 25–30 kuntaa (1–2 keskikokoista maakuntaa; Keski-Suomi + Kymenlaakso, 29 kuntaa, vei 1 h 45 min).
- **Rantatieto** lasketaan oletuksena samalla, koska se on käytössä kaikissa nykyisissä maakunnissa (lisää ensiajoon
  noin 10–20 %). Jos et halua sitä uudelle maakunnalle, mainitse pyynnössä: *"Lisää Etelä-Savo ilman rantatietoa."*

Puuttuvat maakunnat (4.11.2026): Etelä-Karjala, Etelä-Pohjanmaa, Etelä-Savo, Kainuu, Keski-Pohjanmaa,
Lappi, Pohjanmaa, Pohjois-Karjala, Pohjois-Pohjanmaa ja Pohjois-Savo. Ahvenanmaalla on oma
rakennusrekisterinsä, joten sen tiedot on selvitettävä erikseen.

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
- **Tallenna itsellesi tiedostot**, joita haluat säilyttää (esim. Claudelta saadut Excelit) – Clauden työkone on väliaikainen.
- Pyydä isoista muutoksista silloin tällöin **erillinen katselmointi** uudessa keskustelussa.
- Tarkista uudet ominaisuudet itse sivulta: Claude kertoo aina, mitä avata ja mitä pitäisi näkyä.

---

## 9. Kulut ja rajat

- **Kulut:** 0 €. GitHub Actions ja GitHub Pages ovat ilmaisia julkiselle repositoriolle; rekisterien avoin data on maksutonta.
- **GitHub Pagesin rajat:** koko sivusto enintään 1 Gt (nyt noin 253 Mt), yksittäinen tiedosto enintään 100 Mt
  (suurin, Uusimaa, noin 63 Mt). Koko Suomi mahtuu arviolta hyvin.
- **Ulkoiset palvelut, joista sivu riippuu:** OpenFreeMap (taustakartta) ja unpkg (karttakirjastot). Jos jompikumpi on
  katkolla, sivu ei toimi kunnes palvelu palaa.

---

## 10. Rantatieto ("oma ranta")

- Sivulla on suodatin **Ranta** (Oma ranta / Erillinen rantapalsta / Puron varrella / Ei rantaa eikä puroa / Ei laskettu)
  ja talon tietokortissa osio **Ranta**. Tieto lasketaan kiinteistörajoista ja Maanmittauslaitoksen vesialueista.
- **Oma ranta** = tontti ulottuu veteen, tai välissä on vain vesijättöä (ei toisen kiinteistön maata). **Erillinen
  rantapalsta** = kiinteistön toinen palsta on rannassa. **Ei omaa rantaa** = välissä on esim. naapuri, yhteinen ranta-alue,
  rantapuisto tai tie, tai vesi on kaukana.
- **Puron varrella** = tontti ei ole rannassa, mutta puro kulkee tontilla tai sen rajalla (vähintään 10 m matkalla).
  Mukana ovat maastotietokannan 2–5 m leveät virtavedet (puro tai pieni joki). Kapeammat (alle 2 m) ovat aineistossa
  samassa luokassa metsä- ja peltoojien kanssa (Tammelassa 6 400 km), joten ne eivät ole mukana. Kokeiltu rajaus
  "vain mutkittelevat kapeat" odottaa pistokoettasi. Purotieto päivittyy nykyisiin kuntiin vähitellen noin kahden viikon
  aikana (yöajon tavallisissa tonttihauissa, ei lisäkuormaa); sivu kertoo, missä maakunnissa se on vielä kesken.
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
  | **Yhteensä** | **256 715 / 1 057 553** | **24 %** |

  Puron varrella (uusissa kunnissa heti): Keski-Suomi 1 460, Kymenlaakso 1 701, Kuhmoinen 78.

- Rantatieto päivittyy kunnan tonttien kanssa kahden viikon välein; laskenta lisää yöajoon noin 4 minuuttia.
- Uudelle maakunnalle rantatieto lasketaan oletuksena samalla, kun maakunta lisätään (kohta 6).
- **Poistaminen käytöstä:** pyydä Claudea *"Poista rantatieto käytöstä"* – se on yksi asetus (`SHORE_REGIONS` tyhjäksi),
  ja tieto katoaa sivulta seuraavassa ajossa. Muu palvelu ei muutu.

## 11. Avoimet asiat ja suunnitelmat (4.11.2026)

- **Tietosuojaseloste** – tehtävä ennen kuin palvelusta kerrotaan laajemmin (osoitteet ja kiinteistötunnukset voidaan yhdistää ihmisiin).
- **Rantatieto:** otetaanko alle 2 m leveät mutkittelevat purot mukaan (odottaa pistokoettasi).
- **Automaattinen sivun tarkistus** yöajon lopuksi – suunniteltu.
- Muut maakunnat, osoitehaku, oma verkko-osoite.

## Lähteet ja lisenssit

- Rakennukset ja osoitteet: Suomen ympäristökeskus (SYKE), Ryhti, CC BY 4.0
- Kiinteistöpalstat ja vesialueet: Maanmittauslaitos, kiinteistörekisterikartta ja maastotietokanta, CC BY 4.0
- Taustakartta: OpenFreeMap, © OpenStreetMapin tekijät (ODbL)
- Kartassa ei ole omistajatietoja.
