"""Puuston arvon hinnat: Luonnonvarakeskuksen kantohinnat hinta-alueittain ja kuukausittain (PxWeb-rajapinta).
Hinta-alueet maakunnittain (PRICE_AREA) ja kuntakohtaiset poikkeukset (PRICE_AREA_MUNI)."""
from ..yhteiset import net

LUKE_API = "https://statdb.luke.fi/PxWeb/api/v1/fi/LUKE"
LUKE_TABLE = "met/teokau/kk/0100_teokau.px"

# Luken puukaupan hinta-alueet 2023– (Luke: puukaupan alueluokitukset). Kuusamo, Pudasjärvi ja Taivalkoski → Kainuu-Koillismaa.
PRICE_AREA = {
    "Uusimaa": "MPKH01", "Varsinais-Suomi": "MPKH01", "Satakunta": "MPKH01", "Kanta-Häme": "MPKH01", "Päijät-Häme": "MPKH01",
    "Pirkanmaa": "MPKH02", "Keski-Suomi": "MPKH02",
    "Pohjois-Savo": "MPKH03", "Pohjois-Karjala": "MPKH03",
    "Kymenlaakso": "MPKH04", "Etelä-Karjala": "MPKH04", "Etelä-Savo": "MPKH04",
    "Etelä-Pohjanmaa": "MPKH05", "Pohjanmaa": "MPKH05", "Keski-Pohjanmaa": "MPKH05",
    "Pohjois-Pohjanmaa": "MPKH06", "Kainuu": "MPKH07", "Lappi": "MPKH08",
}
PRICE_AREA_MUNI = {"305": "MPKH07", "615": "MPKH07", "832": "MPKH07"}
TRADES = {"PKAUP": "Pystykauppa (kaikki hakkuut)", "UUD": "Uudistushakkuu", "HAR": "Harvennushakkuu", "ENS": "Ensiharvennus"}
ASSORT = {("manty", "tukki"): "TUK_MA", ("kuusi", "tukki"): "TUK_KU", ("koivu", "tukki"): "TUK_KO",
          ("manty", "kuitu"): "KUI_MA", ("kuusi", "kuitu"): "KUI_KU", ("koivu", "kuitu"): "KUI_KO"}


def price_group(g):
    return "koivu" if g == "lehti" else g  # muut lehtipuut koivun hinnoin (vähäinen määrä)


def luke_prices(area):
    """{(kauppatapa, puutavaralaji): (hinta €/m³, kuukausi)} viimeisimmästä kuukaudesta, jolla hinta on julkaistu."""
    meta = net.get(f"{LUKE_API}/{LUKE_TABLE}").json()
    months = next(v for v in meta["variables"] if v["code"] == "M")["values"][-12:]
    q = [{"code": "M", "selection": {"filter": "item", "values": months}},
         {"code": "INFO", "selection": {"filter": "item", "values": ["E_M3"]}},
         {"code": "MPKH", "selection": {"filter": "item", "values": [area]}},
         {"code": "KAUP", "selection": {"filter": "item", "values": list(TRADES)}},
         {"code": "PTL", "selection": {"filter": "item", "values": list(ASSORT.values())}}]
    r = net.session().post(f"{LUKE_API}/{LUKE_TABLE}", json={"query": q, "response": {"format": "json-stat2"}}, timeout=120)
    r.raise_for_status()
    js = r.json()
    dims = js["id"]
    sizes = js["size"]
    idx = {d: list(js["dimension"][d]["category"]["index"]) for d in dims}
    # json-stat2: index voi olla sanakirja {koodi: järjestys}
    for d in dims:
        ci = js["dimension"][d]["category"]["index"]
        if isinstance(ci, dict):
            idx[d] = sorted(ci, key=ci.get)
    values = js["value"]
    table = {}  # (kaup, ptl, kk) -> hinta
    strides = [1] * len(dims)
    for i in range(len(dims) - 2, -1, -1):
        strides[i] = strides[i + 1] * sizes[i + 1]
    for flat, v in (values.items() if isinstance(values, dict) else enumerate(values)):
        flat = int(flat)
        pos = {d: idx[d][(flat // strides[i]) % sizes[i]] for i, d in enumerate(dims)}
        if v is not None:
            table[(pos["KAUP"], pos["PTL"], pos["M"])] = float(v)
    latest = {}
    for kaup in TRADES:
        for ptl in ASSORT.values():
            got = [(m, table[(kaup, ptl, m)]) for m in months if (kaup, ptl, m) in table]
            if got:
                m, p = got[-1]
                latest[(kaup, ptl)] = (p, m)
    return latest, table, months
