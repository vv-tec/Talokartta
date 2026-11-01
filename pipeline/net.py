"""Yhteinen HTTP-istunto uudelleenyrityksillä."""
import time

import requests

from .config import USER_AGENT

_session = None


def session():
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers["User-Agent"] = USER_AGENT
    return _session


def get(url, params=None, *, tries=5, timeout=120):
    """GET, joka yrittää uudelleen verkko- ja palvelinvirheissä (5xx, 429)."""
    last = None
    for attempt in range(tries):
        try:
            r = session().get(url, params=params, timeout=timeout)
            if r.status_code < 500 and r.status_code != 429:
                r.raise_for_status()
                return r
            last = RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
        except requests.RequestException as e:  # yhteysvirhe tai 4xx
            if isinstance(e, requests.HTTPError) and e.response is not None and e.response.status_code < 500:
                raise
            last = e
        time.sleep(min(60, 3 * 2 ** attempt))
    raise RuntimeError(f"Haku epäonnistui {tries} yrityksen jälkeen: {url} ({last})")
