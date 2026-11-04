/* Talokartta – karttasovellus.
 * Data: data/meta.json kertoo tiedostot: data/g.pmtiles (taso "g" = tiheysruudut, kaikki alueet) ja
 * maakunnittain data/b-<maakunta>.pmtiles (taso "b" = rakennukset zoomista 12 alkaen).
 * Rakennuksen ominaisuudet: id rakennustunnus, k kiinteistötunnus, a osoite, pc postinumero, po postitoimipaikka,
 * p tyyppi, s käytössäolo, d valmistumispäivä, y vuosi, g kerrosala, t kokonaisala, f kerroksia, n asuntoja,
 * c rakennuksia samalla kiinteistöllä, pa palstan ala, ka kiinteistön ala, pn palstoja, ex/ny ETRS-TM35FIN,
 * m runkomateriaali, fa julkisivu, r rakentamistapa, h lämmitystapa, e lämmitysenergia (koodit, ks. CATS),
 * v tilavuus m³, ha huoneistoala m², sj suojeltu (1/0).
 */
"use strict";

const TYPES = { "05": "Pientalo", "06": "Kerrostalo", "01": "Vapaa-ajan asunto" };
const STATUS = {
  "01": "Vakinainen asuminen", "03": "Loma-asuminen", "05": "Tyhjillään", "04": "Muu tilapäinen asuminen",
  "02": "Toimitila- tai tuotantokäyttö", "10": "Käytöstä ei tietoa", "11": "Muu (sauna, liiteri yms.)",
  "09": "Hylätty (ränsistynyt)", "": "Ei tietoa",
};
// numeroavaimet ("10", "11") järjestyisivät muuten ensimmäisiksi
const ORDER = { types: ["05", "06", "01"], status: ["01", "03", "04", "05", "02", "09", "11", "10", ""] };
// Rakenne- ja lämmityssuodattimet: Ryhtin koodistot (koodistot.suomi.fi). "" = tieto puuttuu rekisteristä.
const CATS = [
  { key: "m", title: "Runkomateriaali", opts: [["04", "Puu"], ["02", "Tiili"], ["01", "Betoni"], ["03", "Teräs"], ["99", "Muu"]] },
  { key: "fa", title: "Julkisivu", opts: [["05", "Puu"], ["02", "Tiili"], ["01", "Betoni"], ["03", "Metallilevy"], ["04", "Kivi"], ["06", "Lasi"], ["99", "Muu"]] },
  { key: "h", title: "Lämmitystapa", opts: [["01", "Vesikeskuslämmitys"], ["03", "Sähkölämmitys"], ["02", "Ilmakeskuslämmitys"],
    ["04", "Uuni, takka tai kamiina"], ["06", "Ilmalämpöpumppu"], ["05", "Aurinkolämmitys"], ["07", "Ei kiinteää lämmityslaitetta"], ["99", "Muu"]] },
  { key: "e", title: "Lämmitysenergia", opts: [["01", "Kauko- tai aluelämpö"], ["04", "Sähkö"], ["02", "Kevyt polttoöljy"],
    ["03", "Raskas polttoöljy"], ["07", "Puu"], ["09", "Maalämpö tms."], ["1101", "Maalämpöpumppu"], ["1102", "Ilmalämpöpumppu"],
    ["1103", "Poistoilmalämpöpumppu"], ["1104", "Ilma-vesilämpöpumppu"], ["11", "Lämpöpumppu (tarkentamaton)"], ["05", "Kaasu"],
    ["06", "Kivihiili"], ["08", "Turve"], ["10", "Aurinkoenergia"], ["99", "Muu"]] },
  { key: "r", title: "Rakentamistapa", opts: [["02", "Paikalla tehty"], ["01", "Elementti"]] },
];
CATS.forEach((c) => {
  c.opts.push(["", "Ei tietoa"]);
  c.labels = Object.fromEntries(c.opts);
  c.order = c.opts.map(([k]) => k);  // Object.keys järjestäisi numeroavaimet (10, 11, 1101…) ensin
});
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

/* ---------- RANTA (irrotettava lisäosa: näkyy vain, kun meta.json:n shore_regions ei ole tyhjä) ----------
 * Tiilien ra: 0 ei, 1 ei – toinen kiinteistö välissä, 2 ranta, 3 ranta (vesijättö), 4 erillinen rantapalsta,
 * 5 puron varrella; rl rantaviiva m (ra 5: puroa palstalla m), rd etäisyys vedestä m, rw vesilaji (j/m/v),
 * rwa vesialueen ala ha (rd/rw/rwa kertovat aina lähimmän vesialueen, myös puron varrella). */
const SHORE_OPTS = { own: "Oma ranta", sep: "Erillinen rantapalsta", stream: "Puron varrella", no: "Ei rantaa eikä puroa", na: "Ei laskettu" };
const SHORE_VALS = { own: [2, 3], sep: [4], stream: [5], no: [0, 1], na: [-1] };
const SHORE_ORDER = ["own", "sep", "stream", "no", "na"];
const SHORE_TEXT = { 2: "Oma ranta", 3: "Oma ranta – välissä vesijättöä", 4: "Erillinen rantapalsta (kiinteistön toinen palsta rannassa)",
  5: "Puron varrella (puro kulkee tontilla tai sen rajalla)",
  1: "Ei omaa rantaa – välissä toinen kiinteistö (esim. yhteinen ranta-alue, puisto tai tie)", 0: "Ei omaa rantaa" };
const WATER_NAME = { j: "järvi", m: "meri", v: "joki" };
const shoreOn = () => (META?.shore_regions?.length ?? 0) > 0;
const fmtHa = (v) => v >= 1000 ? `${nf.format(Math.round(v / 100))} km²` : v >= 10 ? `${nf.format(Math.round(v))} ha` : `${nf.format(v)} ha`;

const allCats = () => Object.fromEntries(CATS.map((c) => [c.key, new Set(c.order)]));
const state = { types: new Set(Object.keys(TYPES)), status: new Set(Object.keys(STATUS)), cats: allCats(), shore: new Set(SHORE_ORDER), colorMode: "type", selected: null };
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

function buildChecks(el, labels, set, colorVar, order) {
  el.innerHTML = "";
  (order || Object.keys(labels)).map((k) => [k, labels[k]]).forEach(([k, label]) => {
    const lab = document.createElement("label");
    lab.innerHTML = `<input type="checkbox"${set.has(k) ? " checked" : ""}>${colorVar ? '<span class="sw"></span>' : ""}<span>${esc(label)}</span><span class="n"></span>`;
    if (colorVar) lab.querySelector(".sw").style.background = `var(${colorVar(k)})`;
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
  for (const c of CATS) {
    const set = state.cats[c.key];
    if (set.size < c.order.length) parts.push(["in", ["coalesce", ["get", c.key], ""], ["literal", [...set]]]);
  }
  if (shoreOn() && state.shore.size < SHORE_ORDER.length)
    parts.push(["in", ["coalesce", ["get", "ra"], -1], ["literal", [...state.shore].flatMap((k) => SHORE_VALS[k])]]);
  return parts.length ? ["all", ...parts] : null;
}
function activeFilterCount() {
  return [ranges.year, ranges.plot, ranges.gfa].filter((r) => !r.full).length
    + (state.types.size < Object.keys(TYPES).length) + (state.status.size < Object.keys(STATUS).length)
    + CATS.filter((c) => state.cats[c.key].size < c.order.length).length
    + (shoreOn() && state.shore.size < SHORE_ORDER.length);
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
const HAD_VIEW = location.hash.includes("kartta=");  // jaettu linkki, jossa on valmis karttanäkymä
const dataUrl = (file) => "pmtiles://" + new URL("data/" + file, location.href).href;
let B_LAYERS = [], SEL_LAYERS = [];  // rakennustasot ja valintarenkaat, yksi kutakin maakuntaa kohden

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

let styleReady = false;
function addDataLayers() {
  if (!META?.regions || !styleReady || map.getSource("g")) return;  // odotetaan sekä taustakarttaa että meta.jsonia
  const halo = css("--halo");
  map.addSource("g", { type: "vector", url: dataUrl(META.grid) });
  map.addLayer({
    id: "g", type: "circle", source: "g", "source-layer": "g", maxzoom: minZoomB(),
    paint: {
      "circle-color": css("--grid"),
      "circle-opacity": 0.55,
      "circle-stroke-color": halo, "circle-stroke-width": 1, "circle-stroke-opacity": 0.8,
      // säde mitoitettu ruutujen väliin, jotta ympyrät eivät peitä toisiaan (5 km ruudut z≤9, 1 km z10–11)
      "circle-radius": ["interpolate", ["linear"], ["zoom"],
        5, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 0.8, 45, 2.5],
        8, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 1.8, 45, 8.5],
        9.99, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 3, 45, 16],
        10, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 1.5, 22, 3.4],
        11.99, ["interpolate", ["linear"], ["sqrt", ["get", "n"]], 1, 2.5, 22, 6.8]],
    },
  });
  map.addLayer({
    id: "g-n", type: "symbol", source: "g", "source-layer": "g", minzoom: 8.5, maxzoom: 10,
    filter: [">=", ["get", "n"], 10],
    layout: { "text-field": ["to-string", ["get", "n"]], "text-size": 11, "text-font": ["Noto Sans Regular"], "text-allow-overlap": false },
    paint: { "text-color": css("--ink"), "text-halo-color": halo, "text-halo-width": 1.2 },
  });
  B_LAYERS = []; SEL_LAYERS = [];
  // Jokainen maakunta on oma tiedostonsa; selain hakee vain niiden tiilet, jotka ovat näkyvissä.
  for (const r of META.regions) {
    const id = r.file.replace(/\.pmtiles$/, "");
    map.addSource(id, { type: "vector", url: dataUrl(r.file) });
    map.addLayer({
      id, type: "circle", source: id, "source-layer": "b", minzoom: minZoomB(),
      paint: {
        "circle-color": colorExpr(),
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 2.6, 14, 4.5, 16, 7, 18, 10],
        "circle-stroke-color": halo,
        "circle-stroke-width": ["interpolate", ["linear"], ["zoom"], 12, 0.6, 16, 1.5],
        "circle-opacity": 0.92,
      },
    });
    B_LAYERS.push(id);
  }
  for (const id of B_LAYERS) {
    map.addLayer({
      id: id + "-sel", type: "circle", source: id, "source-layer": "b", minzoom: minZoomB(),
      filter: ["==", ["get", "id"], state.selected ?? "__none__"],
      paint: {
        "circle-color": "rgba(0,0,0,0)",
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 12, 8, 16, 13, 18, 17],
        "circle-stroke-color": css("--ink"), "circle-stroke-width": 3,
      },
    });
    SEL_LAYERS.push(id + "-sel");
  }
  applyFilters();
}
map.on("style.load", () => { styleReady = true; addDataLayers(); });

function applyFilters() {
  if (!B_LAYERS.length || !ranges.year) return;
  const f = filterExpr();
  B_LAYERS.forEach((id) => map.getLayer(id) && map.setFilter(id, f));
  CATS.forEach((c) => { const m = $("cat-" + c.key)?.querySelector(".mark"); if (m) m.hidden = state.cats[c.key].size === c.order.length; });
  const n = activeFilterCount();
  $("fcount").hidden = !n; $("fcount").textContent = n;
  scheduleCount();
}
function applyColors() {
  const c = colorExpr();
  B_LAYERS.forEach((id) => map.getLayer(id) && map.setPaintProperty(id, "circle-color", c));
}
function markSelected(id) {
  SEL_LAYERS.forEach((l) => map.getLayer(l) && map.setFilter(l, ["==", ["get", "id"], id]));
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
  if (!B_LAYERS.length) return;
  const seen = new Set();
  map.queryRenderedFeatures({ layers: B_LAYERS }).forEach((f) => seen.add(f.properties.id));
  $("visCount").textContent = nf.format(seen.size);
  $("visLabel").textContent = activeFilterCount() ? "suodatettua rakennusta näkyvissä" : "rakennusta näkyvissä";
}
map.on("moveend", scheduleCount);
map.on("idle", scheduleCount);

/* ---------- valinta ja kohdekortti ---------- */
function pick(point) {
  const pad = window.matchMedia("(pointer: coarse)").matches ? 14 : 7;
  const fs = map.queryRenderedFeatures([[point.x - pad, point.y - pad], [point.x + pad, point.y + pad]], { layers: B_LAYERS });
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
    const g = map.getLayer("g") && map.queryRenderedFeatures(e.point, { layers: ["g"] })[0];
    if (g) map.flyTo({ center: g.geometry.coordinates, zoom: Math.max(minZoomB() + 0.6, map.getZoom() + 2) });
    return;
  }
  const f = pick(e.point);
  f ? select(f.properties, f.geometry.coordinates, f.source) : closeCard();
});
map.on("mousemove", (e) => {
  const layers = map.getZoom() < minZoomB() ? ["g"] : B_LAYERS;
  const hit = layers.length && map.getLayer(layers[0]) && map.queryRenderedFeatures([[e.point.x - 4, e.point.y - 4], [e.point.x + 4, e.point.y + 4]], { layers }).length;
  map.getCanvas().style.cursor = hit ? "pointer" : "";
});

function shoreCard(p, source) {
  const region = META?.regions?.find((r) => r.file.replace(/\.pmtiles$/, "") === source)?.name;
  if (!shoreOn() || !META.shore_regions.includes(region)) return "";
  const own = p.ra >= 2 && p.ra <= 4;
  const streamDone = (META.stream_regions || []).includes(region);
  return `<div class="sect"><h4>Ranta</h4><dl class="kv txt">
      <dt>Tulos</dt><dd>${p.ra != null ? SHORE_TEXT[p.ra] : "Ei vielä laskettu (uusi rakennus, lasketaan kahden viikon sisällä)"}</dd>
      ${own && p.rl ? `<dt>Rantaviivaa</dt><dd>noin ${nf.format(p.rl)} m</dd>` : ""}
      ${p.ra === 5 && p.rl ? `<dt>Puroa tontilla</dt><dd>noin ${nf.format(p.rl)} m</dd>` : ""}
      ${p.ra != null && !own && p.rd != null ? `<dt>Etäisyys vedestä</dt><dd>${nf.format(Math.round(p.rd))} m</dd>` : ""}
      ${p.rw ? `<dt>${own ? "Vesi" : "Lähin vesi"}</dt><dd>${WATER_NAME[p.rw] ?? esc(p.rw)}${p.rwa != null && p.rw !== "m" ? `, ${fmtHa(p.rwa)}` : ""}</dd>` : ""}
    </dl><p class="fine">Laskettu kiinteistörajoista ja Maanmittauslaitoksen maastotietokannan vesialueista. Vesijättö
    (tontin ja veden välinen kaista, joka ei ole toisen kiinteistön maata) lasketaan omaksi rannaksi. Tieto ei kerro
    vesialueen omistuksesta eikä rannan laadusta. Purot ovat maastotietokannan kapeita virtavesiä (alle 5 m leveitä);
    puro lasketaan vain, jos tontti ei ole rannassa.${streamDone ? "" : " Puroja ei ole vielä laskettu kaikille tämän maakunnan kunnille (päivittyy kahden viikon sisällä)."}</p></div>`;
}

function select(p, coords, source) {
  state.selected = p.id;
  markSelected(p.id);
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
        ${p.ha ? `<dt>Huoneistoala</dt><dd>${nf.format(p.ha)} m²</dd>` : ""}
        ${p.v ? `<dt>Tilavuus</dt><dd>${nf.format(p.v)} m³</dd>` : ""}
        <dt>Rakennustunnus</dt><dd>${esc(p.id)}</dd>
      </dl></div>
      <div class="sect"><h4>Rakenteet ja lämmitys</h4><dl class="kv txt">
        ${CATS.map((c) => `<dt>${c.title}</dt><dd>${esc(c.labels[p[c.key] ?? ""] ?? p[c.key])}</dd>`).join("")}
        ${p.sj != null ? `<dt>Suojeltu</dt><dd>${p.sj ? "Kyllä" : "Ei"}</dd>` : ""}
      </dl></div>
      <div class="sect"><h4>Tontti</h4><dl class="kv">
        <dt>Palstan ala</dt><dd>${fmtArea(p.pa)}</dd>
        <dt>Koko kiinteistö</dt><dd>${fmtArea(p.ka)}${p.pn > 1 ? ` · ${p.pn} palstaa` : ""}</dd>
        <dt>Kiinteistötunnus</dt><dd>${p.k ? `${esc(p.k)}<button type="button" class="copy" id="copyKt">Kopioi</button>` : "–"}</dd>
      </dl></div>
      ${shoreCard(p, source)}
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
  markSelected("__none__");
}
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeCard(); closePanel(); } });

/* ---------- paneeli (puhelimessa alhaalta nouseva) ---------- */
function openPanel() { $("panel").classList.add("open"); $("filtersBtn").setAttribute("aria-expanded", "true"); }
function closePanel() { $("panel").classList.remove("open"); $("filtersBtn").setAttribute("aria-expanded", "false"); }
$("filtersBtn").addEventListener("click", () => ($("panel").classList.contains("open") ? closePanel() : openPanel()));
$("panelClose").addEventListener("click", closePanel);

/* ---------- käynnistys ---------- */
// lukumäärät valintojen viereen; hideEmpty piilottaa vaihtoehdot, joita aineistossa ei ole
function counts(box, by, hideEmpty) {
  box.querySelectorAll("label").forEach((l) => {
    const n = by?.[l.dataset.k];
    l.querySelector(".n").textContent = n ? nf.format(n) : "";
    if (hideEmpty && by) l.hidden = !n;
  });
}
function buildShore() {
  $("shoreSec").hidden = !shoreOn();
  if (!shoreOn()) return;
  const box = $("shoreChecks");
  buildChecks(box, SHORE_OPTS, state.shore, null, SHORE_ORDER);
  const by = META?.by?.ra || {};
  const n = (ks) => ks.reduce((a, k) => a + (by[k] || 0), 0);
  counts(box, { own: n(["2", "3"]), sep: n(["4"]), stream: n(["5"]), no: n(["0", "1"]), na: n([""]) });
  const sr = META.stream_regions || [], todo = META.shore_regions.filter((r) => !sr.includes(r));
  $("shoreNote").textContent = `Laskettu: ${META.shore_regions.join(", ")}. Muualla rakennukset ovat "Ei laskettu" -ryhmässä, joten rajaus piilottaa ne.`
    + (todo.length ? ` Puron varrella -tieto päivittyy vielä kunta kerrallaan (kesken: ${todo.join(", ")}).` : "");
}
function buildCats() {
  const root = $("catFilters");
  const open = new Set([...root.querySelectorAll("details[open]")].map((d) => d.id));
  root.innerHTML = "";
  for (const c of CATS) {
    const d = document.createElement("details");
    d.className = "cat"; d.id = "cat-" + c.key; d.open = open.has(d.id);
    d.innerHTML = `<summary><span>${esc(c.title)}</span><span class="mark" hidden>rajattu</span></summary>
      <div class="tools"><button type="button" data-all="1">Valitse kaikki</button><button type="button" data-all="0">Poista valinnat</button></div>
      <div class="checks"></div>`;
    const box = d.querySelector(".checks");
    buildChecks(box, c.labels, state.cats[c.key], null, c.order);
    counts(box, META?.by?.[c.key], true);
    d.querySelectorAll(".tools button").forEach((b) => b.addEventListener("click", () => {
      state.cats[c.key] = b.dataset.all === "1" ? new Set(c.order) : new Set();
      buildCats(); applyFilters();
    }));
    root.appendChild(d);
  }
}

function initControls() {
  const y0 = META?.years?.[0] ?? 1800, y1 = META?.years?.[1] ?? new Date().getFullYear();
  const yStart = Math.max(y0, 1800);
  const years = Array.from({ length: y1 - yStart + 1 }, (_, i) => yStart + i);
  ranges.year = makeRange($("yearR"), years, (v) => String(v), applyFilters);
  ranges.plot = makeRange($("plotR"), PLOT_STOPS, (v, side) => v === Infinity ? "ei ylärajaa" : fmtArea(v), applyFilters);
  ranges.gfa = makeRange($("gfaR"), GFA_STOPS, (v) => v === Infinity ? "ei ylärajaa" : `${nf.format(v)} m²`, applyFilters);
  buildChecks($("typeChecks"), TYPES, state.types, typeColor, ORDER.types);
  buildChecks($("statusChecks"), STATUS, state.status, statusColor, ORDER.status);
  counts($("typeChecks"), META?.by_type); counts($("statusChecks"), META?.by_status, true);
  buildCats();
  buildShore();

  document.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => {
    state.colorMode = b.dataset.mode;
    document.querySelectorAll(".seg button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
    applyColors();
  }));
  $("reset").addEventListener("click", () => {
    Object.values(ranges).forEach((r) => r.reset());
    state.types = new Set(Object.keys(TYPES)); state.status = new Set(Object.keys(STATUS)); state.cats = allCats(); state.shore = new Set(SHORE_ORDER);
    buildChecks($("typeChecks"), TYPES, state.types, typeColor, ORDER.types);
    buildChecks($("statusChecks"), STATUS, state.status, statusColor, ORDER.status);
    counts($("typeChecks"), META?.by_type); counts($("statusChecks"), META?.by_status, true);
    buildCats();
    buildShore();
    applyFilters();
  });
}

fetch("data/meta.json", { cache: "no-cache" })
  .then((r) => (r.ok ? r.json() : null))
  .catch(() => null)
  .then((m) => {
    META = m;
    initControls();
    addDataLayers();  // jos taustakartta ehti latautua ensin
    if (m) {
      if (m.title) $("sub").textContent = m.title;
      const d = new Date(m.updated);
      $("updated").textContent = `Tiedot päivitetty ${d.toLocaleDateString("fi-FI")} klo ${d.toLocaleTimeString("fi-FI", { hour: "2-digit", minute: "2-digit" })}.`;
      if (!HAD_VIEW) map.fitBounds([[m.bounds[0], m.bounds[1]], [m.bounds[2], m.bounds[3]]], { padding: 40, duration: 0 });
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
