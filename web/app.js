/* Talokartta – karttasovellus.
 * Data: data/talot.pmtiles (tasot "b" = rakennukset zoomista 12 alkaen, "g" = tiheysruudut) ja data/meta.json.
 * Rakennuksen ominaisuudet: id rakennustunnus, k kiinteistötunnus, a osoite, pc postinumero, po postitoimipaikka,
 * p tyyppi, s käytössäolo, d valmistumispäivä, y vuosi, g kerrosala, t kokonaisala, f kerroksia, n asuntoja,
 * c rakennuksia samalla kiinteistöllä, pa palstan ala, ka kiinteistön ala, pn palstoja, ex/ny ETRS-TM35FIN.
 */
"use strict";

const TYPES = { "05": "Pientalo", "06": "Kerrostalo", "01": "Vapaa-ajan asunto" };
const STATUS = {
  "01": "Vakinainen asuminen", "03": "Loma-asuminen", "05": "Tyhjillään", "04": "Muu tilapäinen asuminen",
  "02": "Toimitila- tai tuotantokäyttö", "10": "Käytöstä ei tietoa", "11": "Muu (sauna, liiteri yms.)",
  "09": "Hylätty (ränsistynyt)", "": "Ei tietoa",
};
const STATUS_COLOR = { "01": "--s-01", "03": "--s-03", "05": "--s-05", "11": "--s-11" };
const PLOT_STOPS = [0, 500, 1000, 1500, 2000, 3000, 5000, 10000, 20000, 50000, Infinity];
const GFA_STOPS = [0, 50, 80, 100, 120, 150, 200, 300, 500, 1000, Infinity];
const STYLES = { light: "https://tiles.openfreemap.org/styles/positron", dark: "https://tiles.openfreemap.org/styles/dark" };

const $ = (id) => document.getElementById(id);
const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const nf = new Intl.NumberFormat("fi-FI");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const darkMq = window.matchMedia("(prefers-color-scheme: dark)");
const fmtArea = (m2) => m2 == null ? "–" : m2 >= 10000 ? `${nf.format(Math.round(m2 / 100) / 100)} ha` : `${nf.format(m2)} m²`;
const fmtDate = (d) => { const [y, m, dd] = d.split("-"); return `${+dd}.${+m}.${y}`; };

const state = { types: new Set(Object.keys(TYPES)), status: new Set(Object.keys(STATUS)), colorMode: "type", selected: null };
let META = null;
let ranges = {};

function toast(msg) {
  const el = $("toast"); el.textContent = msg; el.hidden = false;
  clearTimeout(el._t); el._t = setTimeout(() => { el.hidden = true; }, 3500);
}

/* ---------- liukusäätimet ---------- */
function makeRange(el, stops, fmt, onChange) {
  const last = stops.length - 1;
  el.innerHTML = `<div class="vals"><span class="lo"></span><span class="hi"></span></div>
    <div class="track"><div class="fill"></div>
    <input type="range" min="0" max="${last}" step="1" value="0" aria-label="Alaraja">
    <input type="range" min="0" max="${last}" step="1" value="${last}" aria-label="Yläraja"></div>`;
  const [a, b] = el.querySelectorAll("input");
  const r = {
    get lo() { return Math.min(+a.value, +b.value); },
    get hi() { return Math.max(+a.value, +b.value); },
    get full() { return r.lo === 0 && r.hi === last; },
    reset() { a.value = 0; b.value = last; draw(); },
    expr(prop) {
      if (r.full) return null;
      const parts = [["has", prop]];
      if (r.lo > 0) parts.push([">=", ["get", prop], stops[r.lo]]);
      if (stops[r.hi] !== Infinity) parts.push(["<=", ["get", prop], stops[r.hi]]);
      return ["all", ...parts];
    },
  };
  function draw() {
    el.querySelector(".fill").style.cssText = `left:${(r.lo / last) * 100}%;right:${100 - (r.hi / last) * 100}%`;
    el.querySelector(".lo").innerHTML = r.full ? '<span class="all">kaikki, myös puuttuvat</span>' : fmt(stops[r.lo], "lo");
    el.querySelector(".hi").textContent = r.full ? "" : fmt(stops[r.hi], "hi");
  }
  [a, b].forEach((i) => i.addEventListener("input", () => { draw(); onChange(); }));
  draw();
  return r;
}

function buildChecks(el, labels, set, colorVar) {
  el.innerHTML = "";
  Object.entries(labels).forEach(([k, label]) => {
    const lab = document.createElement("label");
    lab.innerHTML = `<input type="checkbox" checked><span class="sw"></span><span>${esc(label)}</span><span class="n"></span>`;
    lab.querySelector(".sw").style.background = `var(${colorVar(k)})`;
    lab.dataset.k = k;
    lab.querySelector("input").addEventListener("change", (e) => { e.target.checked ? set.add(k) : set.delete(k); applyFilters(); });
    el.appendChild(lab);
  });
}

/* ---------- suodatin- ja värilausekkeet ---------- */
function filterExpr() {
  const parts = [];
  for (const [prop, r] of [["y", ranges.year], ["pa", ranges.plot], ["g", ranges.gfa]]) { const e = r.expr(prop); if (e) parts.push(e); }
  if (state.types.size < Object.keys(TYPES).length) parts.push(["in", ["get", "p"], ["literal", [...state.types]]]);
  if (state.status.size < Object.keys(STATUS).length) parts.push(["in", ["coalesce", ["get", "s"], ""], ["literal", [...state.status]]]);
  return parts.length ? ["all", ...parts] : null;
}
function activeFilterCount() {
  return [ranges.year, ranges.plot, ranges.gfa].filter((r) => !r.full).length
    + (state.types.size < Object.keys(TYPES).length) + (state.status.size < Object.keys(STATUS).length);
}
const typeColor = (k) => `--t-${k}`;
const statusColor = (k) => STATUS_COLOR[k] || "--s-other";
function colorExpr() {
  if (state.colorMode === "type") return ["match", ["get", "p"], "05", css("--t-05"), "06", css("--t-06"), "01", css("--t-01"), css("--s-other")];
  return ["match", ["coalesce", ["get", "s"], ""], "01", css("--s-01"), "03", css("--s-03"), "05", css("--s-05"), "11", css("--s-11"), css("--s-other")];
}

/* ---------- kartta ---------- */
const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);
const DATA_URL = "pmtiles://" + new URL("data/talot.pmtiles", location.href).href;

const map = new maplibregl.Map({
  container: "map",
  style: darkMq.matches ? STYLES.dark : STYLES.light,
  center: [25, 64.5], zoom: 4.5, minZoom: 3, maxZoom: 19,
  hash: "kartta", attributionControl: false, dragRotate: false, pitchWithRotate: false,
});
map.touchZoomRotate.disableRotation();
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
map.addControl(new maplibregl.GeolocateControl({ positionOptions: { enableHighAccuracy: true }, fitBoundsOptions: { maxZoom: 15 } }), "top-right");
map.addControl(new maplibregl.ScaleControl({ unit: "metric" }), "bottom-left");
map.addControl(new maplibregl.AttributionControl({ compact: true,
  customAttribution: 'Rakennukset © SYKE Ryhti · Kiinteistöt © Maanmittauslaitos · <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' }), "bottom-right");

function minZoomB() { return META?.building_minzoom ?? 12; }

function addDataLayers() {
  if (map.getSource("talot")) return;
  map.addSource("talot", { type: "vector", url: DATA_URL });
  const halo = css("--halo");
  map.addLayer({
    id: "g", type: "circle", source: "talot", "source-layer": "g", maxzoom: minZoomB(),
    paint: {
      "circle-color": css("--grid"),
      "circle-opacity": 0.55,
      "circle-stroke-color": halo, "circle-stroke-width": 1, "circle-stroke-opacity": 0.8,
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        4, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 2, 30, 9, 150, 22],
        8, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 4, 30, 16, 150, 34],
        9, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 3, 10, 9, 40, 20],
        11.9, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 6, 10, 20, 40, 40]],
    },
  });
  map.addLayer({
    id: "g-n", type: "symbol", source: "talot", "source-layer": "g", minzoom: 8, maxzoom: minZoomB(),
    filter: [">=", ["get", "n"], 10],
    layout: { "text-field": ["to-string", ["get", "n"]], "text-size": 11, "text-font": ["Noto Sans Regular"], "text-allow-overlap": false },
    paint: { "text-color": css("--ink"), "text-halo-color": halo, "text-halo-width": 1.2 },
  });
  map.addLayer({
    id: "b", type: "circle", source: "talot", "source-layer": "b", minzoom: minZoomB(),
    paint: {
      "circle-color": colorExpr(),
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 2.6, 14, 4.5, 16, 7, 18, 10],
      "circle-stroke-color": halo,
      "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 12, 0.6, 16, 1.5],
      "circle-opacity": 0.92,
    },
  });
  map.addLayer({
    id: "b-sel", type: "circle", source: "talot", "source-layer": "b", minzoom: minZoomB(),
    filter: ["==", ["get", "id"], state.selected ?? "__none__"],
    paint: {
      "circle-color": "rgba(0,0,0,0)",
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 8, 16, 13, 18, 17],
      "circle-stroke-color": css("--ink"), "circle-stroke-width": 3,
    },
  });
  applyFilters();
}
map.on("style.load", addDataLayers);

function applyFilters() {
  if (!map.getLayer("b") || !ranges.year) return;
  map.setFilter("b", filterExpr());
  const n = activeFilterCount();
  $("fcount").hidden = !n; $("fcount").textContent = n;
  scheduleCount();
}
function applyColors() {
  if (!map.getLayer("b")) return;
  map.setPaintProperty("b", "circle-color", colorExpr());
}

/* ---------- laskuri ja vihje ---------- */
let countTimer = null;
function scheduleCount() { clearTimeout(countTimer); countTimer = setTimeout(updateCount, 120); }
function updateCount() {
  const z = map.getZoom(), close = z >= minZoomB();
  $("hint").hidden = close || !META;
  if (!close) {
    $("visCount").textContent = META ? nf.format(META.count) : "–";
    $("visLabel").textContent = "rakennusta kartalla. Lähennä nähdäksesi ne ja käyttääksesi suodattimia.";
    return;
  }
  if (!map.getLayer("b")) return;
  const seen = new Set();
  map.queryRenderedFeatures({ layers: ["b"] }).forEach((f) => seen.add(f.properties.id));
  $("visCount").textContent = nf.format(seen.size);
  $("visLabel").textContent = activeFilterCount() ? "suodatettua rakennusta näkyvissä" : "rakennusta näkyvissä";
}
map.on("moveend", scheduleCount);
map.on("idle", scheduleCount);

/* ---------- valinta ja kohdekortti ---------- */
function pick(point) {
  const pad = window.matchMedia("(pointer: coarse)").matches ? 14 : 7;
  const fs = map.queryRenderedFeatures([[point.x - pad, point.y - pad], [point.x + pad, point.y + pad]], { layers: ["b"] });
  if (!fs.length) return null;
  let best = fs[0], bd = Infinity;
  for (const f of fs) {
    const p = map.project(f.geometry.coordinates), d = (p.x - point.x) ** 2 + (p.y - point.y) ** 2;
    if (d < bd) { bd = d; best = f; }
  }
  return best;
}
map.on("click", (e) => {
  if (map.getZoom() < minZoomB()) {
    const g = map.queryRenderedFeatures(e.point, { layers: ["g"] })[0];
    if (g) map.flyTo({ center: g.geometry.coordinates, zoom: Math.max(minZoomB() + 0.6, map.getZoom() + 2) });
    return;
  }
  const f = pick(e.point);
  f ? select(f.properties, f.geometry.coordinates) : closeCard();
});
map.on("mousemove", (e) => {
  const layers = map.getZoom() < minZoomB() ? ["g"] : ["b"];
  const hit = map.getLayer(layers[0]) && map.queryRenderedFeatures([[e.point.x - 4, e.point.y - 4], [e.point.x + 4, e.point.y + 4]], { layers }).length;
  map.getCanvas().style.cursor = hit ? "pointer" : "";
});

function select(p, coords) {
  state.selected = p.id;
  if (map.getLayer("b-sel")) map.setFilter("b-sel", ["==", ["get", "id"], p.id]);
  const [lon, lat] = coords;
  const addr = p.a || "Ei katuosoitetta";
  const place = [p.pc, p.po].filter(Boolean).join(" ");
  const notes = [];
  if (p.ka > 100000) notes.push(`Kiinteistö on suuri (${fmtArea(p.ka)}), joten rakennus voi olla vuokratontilla tai osa tilaa. Silloin kiinteistön ala ei kerro tontin kokoa.`);
  else if (p.pn > 1) notes.push(`Kiinteistössä on ${p.pn} palstaa. Rakennuksen palstan ala vastaa lähinnä tonttia.`);
  if (p.c > 1) notes.push(`Samalla kiinteistöllä on ${p.c} asuinrakennusta.`);
  if (!p.d) notes.push("Valmistumispäivä puuttuu rekisteristä.");
  else if (p.d.endsWith("-01-01")) notes.push("Päiväksi on merkitty 1.1., joten tiedossa on todennäköisesti vain vuosi.");
  if (p.s === "09") notes.push("Rakennus on merkitty ränsistymisen vuoksi hylätyksi.");
  const sv = `https://www.google.com/maps/@?api=1&map_action=pano&viewpoint=${lat.toFixed(6)},${lon.toFixed(6)}`;
  const gm = `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lon.toFixed(6)}`;
  const kp = p.ex ? `https://asiointi.maanmittauslaitos.fi/karttapaikka/?lang=fi&share=customMarker&n=${p.ny}&e=${p.ex}&title=${encodeURIComponent(addr)}&desc=&zoom=11` : null;
  const card = $("card");
  card.innerHTML = `
    <div class="card-h">
      <h2>${esc(addr)}</h2>
      ${place ? `<div class="place">${esc(place)}</div>` : ""}
      <button type="button" class="x" id="closeCard" aria-label="Sulje tiedot">×</button>
      <div class="pills">
        <span class="pill"><span class="sw" style="background:var(${typeColor(p.p)})"></span>${esc(TYPES[p.p] ?? p.p)}</span>
        <span class="pill"><span class="sw" style="background:var(${statusColor(p.s ?? "")})"></span>${esc(STATUS[p.s ?? ""] ?? p.s)}</span>
      </div>
    </div>
    <div class="card-b">
      <div class="year"><span class="big">${p.y ?? "–"}</span><span class="sub">${p.d ? "valmistunut " + fmtDate(p.d) : "valmistumisvuosi puuttuu"}</span></div>
      <div class="sect"><h4>Rakennus</h4><dl class="kv">
        <dt>Kerrosala</dt><dd>${p.g ? nf.format(p.g) + " m²" : "–"}</dd>
        <dt>Kokonaisala</dt><dd>${p.t ? nf.format(p.t) + " m²" : "–"}</dd>
        <dt>Kerroksia</dt><dd>${p.f ?? "–"}</dd>
        <dt>Asuntoja</dt><dd>${p.n ?? "–"}</dd>
        <dt>Rakennustunnus</dt><dd>${esc(p.id)}</dd>
      </dl></div>
      <div class="sect"><h4>Tontti</h4><dl class="kv">
        <dt>Palstan ala</dt><dd>${fmtArea(p.pa)}</dd>
        <dt>Koko kiinteistö</dt><dd>${fmtArea(p.ka)}${p.pn > 1 ? ` · ${p.pn} palstaa` : ""}</dd>
        <dt>Kiinteistötunnus</dt><dd>${p.k ? `${esc(p.k)}<button type="button" class="copy" id="copyKt">Kopioi</button>` : "–"}</dd>
      </dl></div>
      ${notes.length ? `<div class="sect"><h4>Huomioita</h4><ul class="notes">${notes.map((n) => `<li>${n}</li>`).join("")}</ul></div>` : ""}
      <div class="sect"><h4>Avaa muualla</h4><div class="links">
        <a href="${sv}" target="_blank" rel="noopener">Google Street View <small>katunäkymä lähimmästä kuvauspisteestä ↗</small></a>
        <a href="${gm}" target="_blank" rel="noopener">Google Maps <small>kartta ja ilmakuva ↗</small></a>
        ${kp ? `<a href="${kp}" target="_blank" rel="noopener">Maanmittauslaitoksen Karttapaikka <small>maastokartta ja kiinteistörajat ↗</small></a>` : ""}
      </div></div>
      ${p.ex ? `<p class="coord">ETRS-TM35FIN N ${p.ny}, E ${p.ex} · WGS84 ${lat.toFixed(5)}, ${lon.toFixed(5)}</p>` : ""}
    </div>`;
  card.hidden = false;
  card.scrollTop = 0;
  $("closeCard").addEventListener("click", closeCard);
  $("copyKt")?.addEventListener("click", (e) => {
    navigator.clipboard?.writeText(p.k).then(() => { e.target.textContent = "Kopioitu"; setTimeout(() => { e.target.textContent = "Kopioi"; }, 1500); },
      () => toast("Kopiointi ei onnistunut"));
  });
  closePanel();
}
function closeCard() {
  state.selected = null;
  $("card").hidden = true;
  if (map.getLayer("b-sel")) map.setFilter("b-sel", ["==", ["get", "id"], "__none__"]);
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeCard(); closePanel(); } });

/* ---------- paneeli (puhelimessa alhaalta nouseva) ---------- */
function openPanel() { $("panel").classList.add("open"); $("filtersBtn").setAttribute("aria-expanded", "true"); }
function closePanel() { $("panel").classList.remove("open"); $("filtersBtn").setAttribute("aria-expanded", "false"); }
$("filtersBtn").addEventListener("click", () => ($("panel").classList.contains("open") ? closePanel() : openPanel()));
$("panelClose").addEventListener("click", closePanel);

/* ---------- käynnistys ---------- */
function initControls() {
  const y0 = META?.years?.[0] ?? 1800, y1 = META?.years?.[1] ?? new Date().getFullYear();
  const yStart = Math.max(y0, 1800);
  const years = Array.from({ length: y1 - yStart + 1 }, (_, i) => yStart + i);
  ranges.year = makeRange($("yearR"), years, (v) => String(v), applyFilters);
  ranges.plot = makeRange($("plotR"), PLOT_STOPS, (v, side) => v === Infinity ? "ei ylärajaa" : fmtArea(v), applyFilters);
  ranges.gfa = makeRange($("gfaR"), GFA_STOPS, (v) => v === Infinity ? "ei ylärajaa" : `${nf.format(v)} m²`, applyFilters);
  buildChecks($("typeChecks"), TYPES, state.types, typeColor);
  buildChecks($("statusChecks"), STATUS, state.status, statusColor);
  const counts = (box, by) => box.querySelectorAll("label").forEach((l) => { l.querySelector(".n").textContent = by?.[l.dataset.k] ? nf.format(by[l.dataset.k]) : ""; });
  counts($("typeChecks"), META?.by_type); counts($("statusChecks"), META?.by_status);
  // piilota käytössäolotilat, joita aineistossa ei ole
  if (META?.by_status) $("statusChecks").querySelectorAll("label").forEach((l) => { if (!META.by_status[l.dataset.k]) l.hidden = true; });

  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    state.colorMode = b.dataset.mode;
    document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    applyColors();
  }));
  $("reset").addEventListener("click", () => {
    Object.values(ranges).forEach((r) => r.reset());
    state.types = new Set(Object.keys(TYPES)); state.status = new Set(Object.keys(STATUS));
    document.querySelectorAll(".checks input").forEach((i) => { i.checked = true; });
    buildChecks($("typeChecks"), TYPES, state.types, typeColor);
    buildChecks($("statusChecks"), STATUS, state.status, statusColor);
    counts($("typeChecks"), META?.by_type); counts($("statusChecks"), META?.by_status);
    if (META?.by_status) $("statusChecks").querySelectorAll("label").forEach((l) => { if (!META.by_status[l.dataset.k]) l.hidden = true; });
    applyFilters();
  });
}

fetch("data/meta.json", { cache: "no-cache" })
  .then((r) => (r.ok ? r.json() : null))
  .catch(() => null)
  .then((m) => {
    META = m;
    initControls();
    if (m) {
      const d = new Date(m.updated);
      $("updated").textContent = `Tiedot päivitetty ${d.toLocaleDateString("fi-FI")} klo ${d.toLocaleTimeString("fi-FI", { hour: "2-digit", minute: "2-digit" })}.`;
      if (!location.hash.includes("kartta=")) map.fitBounds([[m.bounds[0], m.bounds[1]], [m.bounds[2], m.bounds[3]]], { padding: 40, duration: 0 });
    } else {
      toast("Aineiston tietoja ei saatu ladattua.");
    }
    applyFilters();
    scheduleCount();
  });

/* teeman vaihto: vaihdetaan taustakartta ja luetaan värit uudelleen */
darkMq.addEventListener("change", () => { map.setStyle(darkMq.matches ? STYLES.dark : STYLES.light); });
map.on("error", (e) => {
  const msg = String(e?.error?.message || "");
  if (/styles\/dark/.test(msg) || (e?.error?.url || "").includes("styles/dark")) { map.setStyle(STYLES.light); return; }  // varalla vaalea tausta
  if (/pmtiles|talot/i.test(msg)) toast("Karttatietojen lataus epäonnistui.");
});
