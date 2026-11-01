"""Data-ajon asetukset. Muuta tätä tiedostoa, kun kartan aluetta laajennetaan."""

# Alue ja kunnat, joiden rakennukset haetaan (kuntanumerot).
REGION_TITLE = "Kanta-Hämeen asuinrakennukset"
MUNICIPALITIES = [
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
]

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
PARCEL_MAX_AGE_DAYS = 7     # palstat haetaan uudelleen viikon välein; muuten käytetään välimuistia

# Karttatiilet: yksittäiset rakennukset näkyvät tästä zoomitasosta alkaen.
BUILDING_MINZOOM = 12
# Tiheysruudut (koko metreinä) ja zoomitasot, joilla kukin näkyy.
DENSITY_GRIDS = [
    {"size": 5000, "minzoom": 0, "maxzoom": 8},
    {"size": 1000, "minzoom": 9, "maxzoom": BUILDING_MINZOOM - 1},
]
