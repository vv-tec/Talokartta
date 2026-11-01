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


def buildings(municipality):
    """Kaikki kunnan rakennukset, sijainti ETRS-TM35FIN-koordinaatteina (x=itä, y=pohjoinen)."""
    for f in _paged("open_building", {"filter": f"municipality_number='{municipality}'", "crs": CRS_3067}):
        g = f.get("geometry")
        if not g or g.get("type") != "Point":
            continue
        x, y = g["coordinates"][:2]
        if x > y:  # varmistus akselijärjestykselle: pohjoiskoordinaatti on aina suurempi
            x, y = y, x
        p = f["properties"]
        p["_x"], p["_y"] = x, y
        yield p


def addresses(municipality):
    props = "building_key,address_fin,postal_code,postal_office_fin"
    for f in _paged("open_address", {"filter": f"municipality_number='{municipality}'", "properties": props}, page=2000):
        yield f["properties"]
