"""Rakennukset ja osoitteet SYKE:n Ryhti-järjestelmän avoimesta OGC API Features -rajapinnasta."""
from ..config import EXCLUDED_STATUS, RESIDENTIAL, RYHTI_BASE
from .net import get
import time

CRS_3067 = "http://www.opengis.net/def/crs/EPSG/0/3067"


def _paged(collection, params, page=1000):
    url = f"{RYHTI_BASE}/{collection}/items"
    q = {"f": "application/json", "limit": str(page), "filter-lang": "cql-text", **params}
    while url:
        for attempt in range(3):  # katkennut vastaus (todettu 18.11.2026: "Unterminated string") → uusi yritys
            try:
                j = get(url, q).json()
                break
            except ValueError:
                if attempt == 2:
                    raise
                time.sleep(30)
        yield from j.get("features", [])
        nxt = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
        url, q = nxt, None  # next-linkissä on parametrit valmiina


def count(collection, flt):
    """Ehdon täyttävien kohteiden määrä (numberMatched) yhdellä kevyellä pyynnöllä; None, jos palvelu ei kerro."""
    j = get(f"{RYHTI_BASE}/{collection}/items", {"f": "application/json", "limit": "1", "filter-lang": "cql-text",
                                                  "filter": flt}).json()
    n = j.get("numberMatched")
    return n if isinstance(n, int) else None


def changed_filter(since, until=None):
    """Muutoshaun ehto: muutettu aikaleiman since jälkeen (ja enintään until)."""
    flt = f"modified_timestamp_utc > '{since}'"
    return flt + (f" AND modified_timestamp_utc <= '{until}'" if until else "")


def code(uri):
    """'http://uri.suomi.fi/.../code/05' -> '05'"""
    return uri.rsplit("/", 1)[-1] if uri else ""


def _buildings(flt):
    for f in _paged("open_building", {"filter": flt, "crs": CRS_3067}):
        g = f.get("geometry")
        if not g or g.get("type") != "Point":
            continue
        x, y = g["coordinates"][:2]
        if x > y:  # varmistus akselijärjestykselle: pohjoiskoordinaatti on aina suurempi
            x, y = y, x
        p = f["properties"]
        p["_x"], p["_y"] = x, y
        yield p


def buildings(municipality):
    """Kaikki kunnan rakennukset, sijainti ETRS-TM35FIN-koordinaatteina (x=itä, y=pohjoinen)."""
    return _buildings(f"municipality_number='{municipality}'")


def changed_buildings(since):
    """Koko maan rakennukset, joita on muutettu aikaleiman since (ISO, UTC) jälkeen."""
    return _buildings(f"modified_timestamp_utc > '{since}'")


ADDR_PROPS = "address_key,building_key,address_fin,postal_code,postal_office_fin,municipality_number,modified_timestamp_utc"


def addresses(municipality):
    for f in _paged("open_address", {"filter": f"municipality_number='{municipality}'", "properties": ADDR_PROPS}, page=2000):
        yield f["properties"]


def changed_addresses(since, until=None):
    for f in _paged("open_address", {"filter": changed_filter(since, until), "properties": ADDR_PROPS}, page=2000):
        yield f["properties"]


def deleted_addresses(since):
    for f in _paged("open_address_deleted", {"filter": f"modified_timestamp_utc > '{since}'"}, page=2000):
        yield f["properties"]


def addresses_for(building_keys):
    """Osoitteet tietyille rakennuksille (uudet rakennukset muutoshaussa), 50 kerrallaan."""
    keys = sorted(building_keys)
    for i in range(0, len(keys), 50):
        ids = ",".join(f"'{k}'" for k in keys[i:i + 50])
        for f in _paged("open_address", {"filter": f"building_key IN ({ids})", "properties": ADDR_PROPS}, page=2000):
            yield f["properties"]


def keep(p):
    """Asuinrakennus, joka näytetään: luokka 01/05/06, ei purettu tai tuhoutunut (config.RESIDENTIAL, EXCLUDED_STATUS).
    Käyttävät sekä talot (kartan rakennukset) että metsätilat (asuinrakennusten määrä tilalla)."""
    return (
        code(p.get("main_purpose")) in RESIDENTIAL
        and code(p.get("usage_status")) not in EXCLUDED_STATUS
        and not p.get("demolition_date")
    )
