"""Data-ajon asetukset. Muuta tätä tiedostoa, kun kartan aluetta laajennetaan."""

# Alueet ja niiden kunnat (kuntanumerot). Uusi maakunta lisätään tähän.
REGIONS = {
    "Kanta-Häme": [
        "061",  # Forssa
        "082",  # Hattula
        "086",  # Hausjärvi
        "103",  # Humppila
        "109",  # Hämeenlinna
        "165",  # Janakkala
        "169",  # Jokioinen
        "433",  # Loppi
        "694",  # Riihimäki
        "834",  # Tammela
        "981",  # Ypäjä
    ],
    "Uusimaa": [
        "018",  # Askola
        "049",  # Espoo
        "078",  # Hanko
        "091",  # Helsinki
        "092",  # Vantaa
        "106",  # Hyvinkää
        "149",  # Inkoo
        "186",  # Järvenpää
        "224",  # Karkkila
        "235",  # Kauniainen
        "245",  # Kerava
        "257",  # Kirkkonummi
        "407",  # Lapinjärvi
        "434",  # Loviisa
        "444",  # Lohja
        "504",  # Myrskylä
        "505",  # Mäntsälä
        "543",  # Nurmijärvi
        "611",  # Pornainen
        "616",  # Pukkila
        "638",  # Porvoo
        "710",  # Raasepori
        "753",  # Sipoo
        "755",  # Siuntio
        "858",  # Tuusula
        "927",  # Vihti
    ],
    "Varsinais-Suomi": [
        "019",  # Aura
        "202",  # Kaarina
        "284",  # Koski Tl
        "304",  # Kustavi
        "322",  # Kemiönsaari
        "400",  # Laitila
        "423",  # Lieto
        "430",  # Loimaa
        "445",  # Parainen
        "480",  # Marttila
        "481",  # Masku
        "503",  # Mynämäki
        "529",  # Naantali
        "538",  # Nousiainen
        "561",  # Oripää
        "577",  # Paimio
        "631",  # Pyhäranta
        "636",  # Pöytyä
        "680",  # Raisio
        "704",  # Rusko
        "734",  # Salo
        "738",  # Sauvo
        "761",  # Somero
        "833",  # Taivassalo
        "853",  # Turku
        "895",  # Uusikaupunki
        "918",  # Vehmaa
    ],
}
REGION_TITLE = "Asuinrakennukset: " + ", ".join(REGIONS)
MUNICIPALITIES = [m for codes in REGIONS.values() for m in codes]

# Ryhdin avoin rakennusluokitus (main_purpose), joka otetaan mukaan:
# 01 = vapaa-ajan asuinrakennus, 05 = pientalo, 06 = kerrostalo
RESIDENTIAL = {"01", "05", "06"}

# Käytössäolotilanteet, joita ei näytetä: purettu (06, 07) ja tuhoutunut (08)
EXCLUDED_STATUS = {"06", "07", "08"}

RYHTI_BASE = "https://paikkatiedot.ymparisto.fi/geoserver/ryhti_building/ogc/features/v1/collections"
MML_CP_WFS = "https://inspire-wfs.maanmittauslaitos.fi/inspire-wfs/cp/ows"

USER_AGENT = "talokartta-data/1.0 (+https://github.com/vv-tec/talokartta)"

# Kiinteistöpalstojen haku tehdään ruuduittain (metreinä, ETRS-TM35FIN).
PARCEL_TILE_M = 2000
PARCEL_PAGE = 1000          # kuinka monta palstaa yhdellä pyynnöllä enintään (palvelun tuettu koko)
PARCEL_BBOX_PAD_M = 3000    # haetaan palstoja myös rakennusten alueen ympäriltä
PARCEL_MAX_AGE_DAYS = 7     # palstat haetaan uudelleen viikon välein (1/7 eristä joka yö); muuten käytetään välimuistia
RYHTI_FULL_DAYS = 30        # kunta haetaan Ryhtistä kokonaan kuukauden välein (1/30 kunnista per yö); muuten vain muutokset
PARCEL_TIME_BUDGET_MIN = 150  # palstojen haku lopetetaan hallitusti, kun ajo on kestänyt näin kauan; loput seuraavalla ajolla

# Karttatiilet: yksittäiset rakennukset näkyvät tästä zoomitasosta alkaen.
BUILDING_MINZOOM = 12
# Tiheysruudut (koko metreinä) ja zoomitasot, joilla kukin näkyy.
DENSITY_GRIDS = [
    {"size": 5000, "minzoom": 0, "maxzoom": 9},
    {"size": 1000, "minzoom": 10, "maxzoom": BUILDING_MINZOOM - 1},
]
