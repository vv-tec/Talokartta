"""Ryhtin rakennukset ja osoitteet tallessa ajojen välillä, jotta rekisteriä ei tarvitse hakea joka yö kokonaan.

Jokainen kunta haetaan kokonaan, kun se puuttuu tai sen täysi haku on yli full_days vanha (vanhimmasta alkaen,
enintään 1/full_days kunnista per ajo, eli kuorma jakautuu kuukaudelle). Muuten haetaan vain muutokset:
koko maan rakennukset ja osoitteet, joiden modified_timestamp_utc on edellisen ajon jälkeen (päivän päällekkäisyydellä).
Täysi haku myös siivoaa rakennukset, jotka on poistettu rekisteristä kokonaan (niistä ei tule muutostietoa).

Tallessa vain asuinrakennukset (keep) ja niiden osoitteet, kevennettyinä: koodit ilman URI-alkuosaa.
"""
import datetime as dt
import gzip
import json
import math
import os
import time

from . import ryhti

FIELDS = ("building_key", "permanent_building_identifier", "property_identifier", "completion_date", "main_purpose",
          "usage_status", "gross_floor_area", "total_area", "number_of_storeys", "apartment_count",
          "material_of_load_bearing_structures", "facade_material", "construction_method", "heating_method",
          "heating_energy_source", "volume", "floor_area", "is_protected", "municipality_number")
URI_FIELDS = {"main_purpose", "usage_status", "material_of_load_bearing_structures", "facade_material",
              "construction_method", "heating_method", "heating_energy_source"}
OVERLAP = dt.timedelta(days=1)  # muutoshaku alkaa päivää ennen edellistä tallessa olevaa muutosta


def slim(p):
    out = {k: (ryhti.code(p[k]) if k in URI_FIELDS else p[k]) for k in FIELDS if p.get(k) is not None}
    out["_x"], out["_y"] = round(p["_x"], 2), round(p["_y"], 2)
    return out


def addr_row(a):
    return [a.get("building_key"), a.get("address_fin") or "", a.get("postal_code") or "",
            a.get("postal_office_fin") or "", a.get("municipality_number") or ""]


class RyhtiStore:
    def __init__(self, path, full_days=30, keep=None, today=None, log=print):
        self.path, self.full_days, self.log = path, full_days, log
        self.keep = keep or (lambda p: True)
        self.today = today or dt.date.today()
        self.data = {"munis": {}, "b": {}, "a": {}, "mark": None}
        if os.path.exists(path):
            with gzip.open(path, "rt", encoding="utf-8") as f:
                self.data = json.load(f)
            log(f"  Ryhti tallessa: {len(self.data['b'])} rakennusta, {len(self.data['a'])} osoitetta, "
                f"viimeisin muutos {self.data['mark']}")
        self.stats = {"full": [], "drift": {}, "changed_b": 0, "changed_a": 0, "removed_b": 0, "removed_a": 0}
        self.missing = []

    def _mark(self, ts):
        if ts and (not self.data["mark"] or ts > self.data["mark"]):
            self.data["mark"] = ts

    def full(self, m):
        """Kunnan täysi haku: korvaa kunnan rakennukset ja osoitteet."""
        d = self.data
        before = {k: b for k, b in d["b"].items() if b.get("municipality_number") == m}
        d["b"] = {k: b for k, b in d["b"].items() if b.get("municipality_number") != m}
        d["a"] = {k: a for k, a in d["a"].items() if a[4] != m}
        n = 0
        for p in ryhti.buildings(m):
            self._mark(p.get("modified_timestamp_utc"))
            if self.keep(p):
                d["b"][p["building_key"]] = slim(p)
                n += 1
        na = 0
        for a in ryhti.addresses(m):
            self._mark(a.get("modified_timestamp_utc"))
            if a.get("building_key") in d["b"] and a.get("address_key"):
                d["a"][a["address_key"]] = addr_row(a)
                na += 1
        had = m in d["munis"]
        d["munis"][m] = self.today.isoformat()
        msg = f"  kunta {m}: täysi haku, {n} asuinrakennusta, {na} osoitetta"
        if had:
            # kuinka paljon tallessa ollut (muutoshaulla ylläpidetty) tieto poikkesi rekisteristä
            after = {k: b for k, b in d["b"].items() if b.get("municipality_number") == m}
            drift = {"uusia": len(after.keys() - before.keys()), "poistuneita": len(before.keys() - after.keys()),
                     "muuttuneita": sum(1 for k in after.keys() & before.keys() if after[k] != before[k])}
            self.stats["drift"][m] = drift
            msg += f"; erot tallessa olleeseen: {drift['uusia']} uutta, {drift['poistuneita']} poistunutta, {drift['muuttuneita']} muuttunutta"
        self.log(msg)
        return n

    def changes(self, since, munis):
        """Muutokset koko maasta aikaleiman since jälkeen; vain annettujen kuntien kohteet tallennetaan."""
        d, st = self.data, self.stats
        new = set()
        for p in ryhti.changed_buildings(since):
            self._mark(p.get("modified_timestamp_utc"))
            if p.get("municipality_number") not in munis:
                continue
            st["changed_b"] += 1
            k = p["building_key"]
            if self.keep(p):
                if k not in d["b"]:
                    new.add(k)
                d["b"][k] = slim(p)
            elif d["b"].pop(k, None) is not None:
                st["removed_b"] += 1
        for a in ryhti.changed_addresses(since):
            self._mark(a.get("modified_timestamp_utc"))
            if a.get("municipality_number") not in munis or not a.get("address_key"):
                continue
            st["changed_a"] += 1
            if a.get("building_key") in d["b"]:
                d["a"][a["address_key"]] = addr_row(a)
            else:
                d["a"].pop(a["address_key"], None)
        for a in ryhti.deleted_addresses(since):
            if d["a"].pop(a.get("address_key"), None) is not None:
                st["removed_a"] += 1
        if new:  # uusille asuinrakennuksille myös osoitteet, joita ei ole muutettu hiljattain
            for a in ryhti.addresses_for(new):
                if a.get("address_key") and a.get("building_key") in d["b"]:
                    d["a"][a["address_key"]] = addr_row(a)

    def update(self, munis, deadline=None):
        """Täydet haut (puuttuvat ensin) aikarajaan asti, sitten muutokset valmiille kunnille.
        Kunnat, joiden täysi haku ei ehtinyt, jäävät listaan self.missing ja haetaan seuraavalla ajolla."""
        munis = [str(m) for m in munis]
        d = self.data
        prev_mark = d["mark"]
        missing = [m for m in munis if m not in d["munis"]]
        stale = sorted((m for m in munis if m in d["munis"] and
                        (self.today - dt.date.fromisoformat(d["munis"][m])).days >= self.full_days),
                       key=lambda m: d["munis"][m])
        todo = missing + stale[:math.ceil(len(munis) / self.full_days)]
        if todo:
            self.log(f"  Ryhti: täysi haku {len(todo)} kunnalle ({len(missing)} uutta, {len(stale)} yli {self.full_days} pv vanhaa)")
        for n, m in enumerate(todo):
            if deadline and time.time() > deadline:
                self.log(f"  Ryhti: aikaraja täynnä, {len(todo) - n} kunnan täysi haku jää seuraavaan ajoon")
                break
            self.full(m)
            self.stats["full"].append(m)
        if prev_mark:
            since = (dt.datetime.fromisoformat(prev_mark.replace("Z", "+00:00")) - OVERLAP).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.changes(since, {m for m in munis if m in d["munis"]})
            s = self.stats
            self.log(f"  Ryhti: muutokset {since} jälkeen: {s['changed_b']} rakennusta ({s['removed_b']} poistui), "
                     f"{s['changed_a']} osoitetta ({s['removed_a']} poistettu)")
        # kunnat, jotka on poistettu asetuksista
        gone = set(d["munis"]) - set(munis)
        if gone:
            d["b"] = {k: b for k, b in d["b"].items() if b.get("municipality_number") not in gone}
            d["a"] = {k: a for k, a in d["a"].items() if a[4] not in gone}
            for m in gone:
                del d["munis"][m]
        self.missing = [m for m in munis if m not in d["munis"]]

    def ready(self, m):
        return m in self.data["munis"]

    def buildings(self, m=None):
        return [b for b in self.data["b"].values() if m is None or b.get("municipality_number") == m]

    def addresses(self):
        b = self.data["b"]
        rows = sorted((a for a in self.data["a"].values() if a[0] in b), key=lambda a: (a[0], a[1]))  # vakaa järjestys
        return [{"building_key": a[0], "address_fin": a[1], "postal_code": a[2], "postal_office_fin": a[3]} for a in rows]

    def save(self):
        b = self.data["b"]  # poistuneiden rakennusten osoitteet pois
        self.data["a"] = {k: a for k, a in self.data["a"].items() if a[0] in b}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with gzip.open(tmp, "wt", encoding="utf-8") as f:
            json.dump(self.data, f, separators=(",", ":"))
        os.replace(tmp, self.path)
