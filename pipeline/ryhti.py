"""Rakennukset ja osoitteet SYKE:n Ryhti-järjestelmän avoimesta OGC API Features -rajapinnasta."""
from .config import RYHTI_BASE
from .net import get

CRS_3067 = "http://www.opengis.net/def/crs/EPSG/0/3067"


def _paged(collection, params, page=1000):
    url = f"{RYHTI_BASE}/{collection}/items"
    q = {"f": "application/json", "limit": str(page), "filter-lang": "cql-text", **params}
    while url:
        j = get(url, q).json()
        yield from j.get("features", [])
        nxt = next((l["href"] for l in j.get("links", []) if l.get("rel") == "next"), None)
        url, q = nxt, None  # next-linkissä on parametrit valmiina


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


def changed_addresses(since):
    for f in _paged("open_address", {"filter": f"modified_timestamp_utc > '{since}'", "properties": ADDR_PROPS}, page=2000):
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
