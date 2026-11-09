"""Inverse transverse Mercator for ETRS-TM35FIN (EPSG:3067) -> ETRS89 lat/lon (≈WGS84)."""
import math

A = 6378137.0
F = 1 / 298.257222101  # GRS80
K0 = 0.9996
LON0 = math.radians(27.0)
FE = 500000.0


def tm35_to_latlon(x, y):
    e2 = F * (2 - F)
    n = F / (2 - F)
    a_hat = A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    xi = y / (K0 * a_hat)
    eta = (x - FE) / (K0 * a_hat)
    d1 = n / 2 - 2 * n**2 / 3 + 37 * n**3 / 96
    d2 = n**2 / 48 + n**3 / 15
    d3 = 17 * n**3 / 480
    xi_p = xi - d1 * math.sin(2 * xi) * math.cosh(2 * eta) - d2 * math.sin(4 * xi) * math.cosh(4 * eta) - d3 * math.sin(6 * xi) * math.cosh(6 * eta)
    eta_p = eta - d1 * math.cos(2 * xi) * math.sinh(2 * eta) - d2 * math.cos(4 * xi) * math.sinh(4 * eta) - d3 * math.cos(6 * xi) * math.sinh(6 * eta)
    chi = math.asin(math.sin(xi_p) / math.cosh(eta_p))
    lat = chi
    for _ in range(10):
        lat = math.asin(math.tanh(math.atanh(math.sin(chi)) + math.sqrt(e2) * math.atanh(math.sqrt(e2) * math.sin(lat))))
    lon = LON0 + math.atan2(math.sinh(eta_p), math.cos(xi_p))
    return math.degrees(lat), math.degrees(lon)


def latlon_to_tm35_np(lat, lon):
    """ETRS89 lat/lon (asteina, numpy-taulukot) -> ETRS-TM35FIN x (itä), y (pohjoinen). Krügerin sarja (mm-tarkkuus)."""
    import numpy as np
    n = F / (2 - F)
    e = math.sqrt(F * (2 - F))
    a_hat = A / (1 + n) * (1 + n**2 / 4 + n**4 / 64)
    h = (n / 2 - 2 * n**2 / 3 + 5 * n**3 / 16, 13 * n**2 / 48 - 3 * n**3 / 5, 61 * n**3 / 240)
    phi = np.radians(lat)
    lam = np.radians(lon) - LON0
    t = np.sinh(np.arctanh(np.sin(phi)) - e * np.arctanh(e * np.sin(phi)))
    xi = np.arctan2(t, np.cos(lam))
    eta = np.arctanh(np.sin(lam) / np.sqrt(1 + t * t))
    x, y = eta.copy(), xi.copy()
    for j, hj in enumerate(h, start=1):
        x = x + hj * np.cos(2 * j * xi) * np.sinh(2 * j * eta)
        y = y + hj * np.sin(2 * j * xi) * np.cosh(2 * j * eta)
    return FE + K0 * a_hat * x, K0 * a_hat * y



if __name__ == "__main__":
    print(tm35_to_latlon(332010, 6748150), "expected ~ (60.83305349, 23.90942712)")
