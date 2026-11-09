/* Metsakartta – esikatselu. Lukee data/meta.json:n ja näyttää metsätilat zoomista 11 alkaen
 * (f-<maakunta>.pmtiles, taso "f"; kaukaa ei mitään, jotta taustakartta erottuu – omistajan toive 6.11.2026).
 * Suodattimet: kokonaisala, puuston arvo, metsäpohja (maapohja + yleisin kasvupaikka), ikäjakauma.
 * Ominaisuuksien lyhyet avaimet: ks. Talokartan pipeline/metsa.py, funktio props. */
const AREAS = { MPKH01: "Etelä-Suomi", MPKH02: "Keski-Suomi", MPKH03: "Savo-Karjala", MPKH04: "Kymi-Savo",
  MPKH05: "Etelä-Pohjanmaa", MPKH06: "Pohjois-Pohjanmaa", MPKH07: "Kainuu-Koillismaa", MPKH08: "Lappi" };
const SPECIES = { m: "mänty ja muut havupuut", k: "kuusi", b: "koivu", l: "muut lehtipuut" };
const SITES = { 1: "Lehto", 2: "Lehtomainen kangas", 3: "Tuore kangas", 4: "Kuivahko kangas", 5: "Kuiva kangas",
  6: "Karukkokangas", 7: "Kalliomaa ja hietikko", 8: "Lakimetsä ja tunturi" };
const DEV = [["da", "Aukea / siemenpuu", "#e9d8a6"], ["dt", "Taimikko", "#b5d99c"], ["d2", "Nuori kasvatus", "#7fbf7b"],
  ["d3", "Varttunut kasvatus", "#3f9a5a"], ["d4", "Uudistuskypsä", "#1b5e34"], ["d5", "Suojuspuu", "#8c6d46"],
  ["de", "Eri-ikäisrakenteinen", "#6a8caf"]];
const STEPS = [[0, "#f1eadb"], [3000, "#d6e5b9"], [6000, "#a8cf8e"], [9000, "#6fae6b"], [12000, "#3c8a4f"], [15000, "#1d5e34"]];
const color = ["step", ["get", "eh"], STEPS[0][1], ...STEPS.slice(1).flat()];

const fmt = (n, d = 0) => (n ?? 0).toLocaleString("fi-FI", { maximumFractionDigits: d, minimumFractionDigits: d });
const eur = (n) => fmt(Math.round((n ?? 0) / 100) * 100) + " €";

// WGS84 → ETRS-TM35FIN (Karttapaikka-linkkiä varten)
function tm35(lat, lon) {
  const a = 6378137, f = 1 / 298.257222101, k0 = 0.9996, lon0 = 27 * Math.PI / 180, n = f / (2 - f);
  const A = a / (1 + n) * (1 + n * n / 4 + n ** 4 / 64), e = Math.sqrt(f * (2 - f));
  const h = [n / 2 - 2 * n * n / 3 + 5 * n ** 3 / 16, 13 * n * n / 48 - 3 * n ** 3 / 5, 61 * n ** 3 / 240];
  const phi = lat * Math.PI / 180, lam = lon * Math.PI / 180 - lon0;
  const t = Math.sinh(Math.atanh(Math.sin(phi)) - e * Math.atanh(e * Math.sin(phi)));
  const xi = Math.atan2(t, Math.cos(lam)), eta = Math.atanh(Math.sin(lam) / Math.sqrt(1 + t * t));
  let x = eta, y = xi;
  for (let j = 1; j <= 3; j++) { x += h[j - 1] * Math.cos(2 * j * xi) * Math.sinh(2 * j * eta); y += h[j - 1] * Math.sin(2 * j * xi) * Math.cosh(2 * j * eta); }
  return { e: Math.round(500000 + k0 * A * x), n: Math.round(k0 * A * y) };
}

const protocol = new pmtiles.Protocol();
maplibregl.addProtocol("pmtiles", protocol.tile);
const dataUrl = (file) => "pmtiles://" + new URL("data/" + file, location.href).href;
const map = new maplibregl.Map({
  container: "map", style: "https://tiles.openfreemap.org/styles/positron", center: [23.85, 60.75], zoom: 11,
  hash: "kartta", attributionControl: false,
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution:
  'Metsävaratieto © Suomen metsäkeskus · Kiinteistöt © Maanmittauslaitos · Kantohinnat © Luonnonvarakeskus · Rakennukset © SYKE Ryhti · <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' }), "bottom-right");

let META = null;
document.getElementById("legend").innerHTML = STEPS.map(([v, c], i) =>
  `<i style="background:${c}"></i><span>${i < STEPS.length - 1 ? `${fmt(v)}–${fmt(STEPS[i + 1][0])}` : `yli ${fmt(v)}`} €/ha</span>`).join("");

const AGES = [["a", "Aukea ja taimikko", ["da", "dt"]], ["n", "Nuori kasvatusmetsä", ["d2"]],
  ["v", "Varttunut kasvatusmetsä", ["d3"]], ["u", "Uudistuskypsä", ["d4", "d5"]]];
const fillIds = () => META.regions.map((r) => r.file.replace(/\.pmtiles$/, "") + "-fill");
const num = (id) => { const v = document.getElementById(id).value; return v === "" ? null : Number(v); };
const sumOf = (keys) => ["+", 0, ...keys.map((k) => ["coalesce", ["get", k], 0])];

function filterExpr() {
  const f = ["all"];
  const range = (key, lo, hi) => {
    if (lo !== null) f.push([">=", ["get", key], lo]);
    if (hi !== null) f.push(["<=", ["get", key], hi]);
  };
  range("ka", num("kaMin"), num("kaMax"));
  range("e", num("eMin"), num("eMax"));
  const peat = document.getElementById("peat").value;
  if (peat === "min") f.push(["<", ["coalesce", ["get", "tu"], 0], 50]);
  if (peat === "peat") f.push([">=", ["coalesce", ["get", "tu"], 0], 50]);
  const boxes = [...document.querySelectorAll("#sites input")];
  const on = boxes.filter((b) => b.checked).map((b) => Number(b.value));
  if (on.length < boxes.length) f.push(["in", ["coalesce", ["get", "kp"], 0], ["literal", on]]);
  for (const [id, , keys] of AGES) {
    const v = Number(document.getElementById("age-" + id).value);
    if (v > 0) f.push([">=", sumOf(keys), v]);
  }
  return f;
}

function applyFilters() {
  if (!META) return;
  const f = filterExpr();
  for (const r of META.regions) {
    const id = r.file.replace(/\.pmtiles$/, "");
    map.setFilter(id + "-fill", f);
    map.setFilter(id + "-line", f);
  }
  updateCount();
}

function updateCount() {
  const el = document.getElementById("count");
  if (map.getZoom() < (META.poly_minzoom || 11)) { el.textContent = "Zoomaa lähemmäs nähdäksesi metsätilat."; return; }
  const seen = new Set(map.queryRenderedFeatures({ layers: fillIds() }).map((f) => f.properties.k));
  el.textContent = `Kartalla näkyvissä ${fmt(seen.size)} metsätilaa.`;
}

function buildFilters() {
  const kp = META.kp || {};
  document.getElementById("sites").innerHTML = Object.keys(kp).sort((a, b) => a - b).map((code) =>
    `<label class="chk"><input type="checkbox" value="${code}" checked> ${SITES[code] || "Ei tietoa"}<span class="n">${fmt(kp[code])}</span></label>`).join("");
  document.getElementById("ages").innerHTML = AGES.map(([id, lab]) => `<div class="slider">
    <label for="age-${id}"><span>${lab}</span><span id="age-${id}-v">0 %</span></label>
    <input type="range" id="age-${id}" min="0" max="100" step="10" value="0"></div>`).join("");
  document.getElementById("kaMax").placeholder = `enintään (${fmt(META.max?.ka)})`;
  document.getElementById("panel").addEventListener("input", (e) => {
    if (e.target.type === "range") document.getElementById(e.target.id + "-v").textContent = e.target.value + " %";
    applyFilters();
  });
  document.getElementById("reset").addEventListener("click", () => {
    for (const el of document.querySelectorAll("#panel input[type=number]")) el.value = "";
    for (const el of document.querySelectorAll("#sites input")) el.checked = true;
    for (const [id] of AGES) { document.getElementById("age-" + id).value = 0; document.getElementById("age-" + id + "-v").textContent = "0 %"; }
    document.getElementById("peat").value = "";
    applyFilters();
  });
}

const toggle = document.getElementById("toggle");
toggle.addEventListener("click", () => {
  const open = document.getElementById("panel").classList.toggle("open");
  toggle.setAttribute("aria-expanded", open);
});

map.on("load", async () => {
  // GitHub Pagesin välimuisti pitää tiedostoja jopa 10 min → kyselyparametri hakee aina tuoreen (pieni tiedosto)
  META = await (await fetch("data/meta.json?v=" + Date.now(), { cache: "no-cache" })).json();
  const upd = new Date(META.updated).toLocaleString("fi-FI", { dateStyle: "short", timeStyle: "short" });
  document.getElementById("stats").textContent =
    `${fmt(META.count)} metsätilaa. Päivitetty ${upd}.`;
  const minz = META.poly_minzoom || 11;
  for (const r of META.regions) {
    const id = r.file.replace(/\.pmtiles$/, "");
    map.addSource(id, { type: "vector", url: dataUrl(r.file) });
    map.addLayer({ id: id + "-fill", type: "fill", source: id, "source-layer": "f", minzoom: minz,
      paint: { "fill-color": color, "fill-opacity": 0.55 } });
    map.addLayer({ id: id + "-line", type: "line", source: id, "source-layer": "f", minzoom: minz,
      paint: { "line-color": "#24382b", "line-width": ["interpolate", ["linear"], ["zoom"], 11, 0.3, 15, 1.2] } });
    map.addLayer({ id: id + "-sel", type: "line", source: id, "source-layer": "f", minzoom: minz,
      filter: ["==", ["get", "k"], ""], paint: { "line-color": "#d1495b", "line-width": 3 } });
    map.on("click", id + "-fill", (e) => select(e.features[0], e.lngLat));
    map.on("mouseenter", id + "-fill", () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", id + "-fill", () => (map.getCanvas().style.cursor = ""));
  }
  buildFilters();
  map.on("idle", updateCount);
  updateCount();
});

// Tietokortin tiedot ovat kuntakohtaisissa tiedostoissa data/kortit/<kunta>.json ({c: sarakkeet, r: {tunnus: [arvot]}}),
// jotta karttatiedostot pysyvät pieninä. Kunta = kiinteistötunnuksen ensimmäinen osa (3 numeroa).
const CARDS = {};
function cardData(k) {
  const muni = k.split("-")[0].padStart(3, "0");
  CARDS[muni] ??= fetch(`data/${META.cards || "kortit/"}${muni}.json?v=${encodeURIComponent(META.updated)}`)
    .then((r) => (r.ok ? r.json() : null)).catch(() => null);
  return CARDS[muni].then((d) => {
    const row = d?.r?.[k];
    return row ? Object.fromEntries(d.c.map((c, i) => [c, row[i]]).filter(([, v]) => v !== null)) : null;
  });
}

async function select(f, ll) {
  const k = f.properties.k;
  for (const r of META.regions) map.setFilter(r.file.replace(/\.pmtiles$/, "") + "-sel", ["==", ["get", "k"], k]);
  const card = document.getElementById("card");
  card.innerHTML = `<h2>${k}</h2><p>Ladataan tietoja…</p>`;
  card.style.display = "block";
  const extra = await cardData(k);
  if (document.querySelector("#card h2")?.textContent !== k) return;  // käyttäjä ehti klikata toista tilaa
  const p = { tu: 0, oj: 0, hr: 0, ...f.properties, ...(extra || {}), k };
  if (!extra) { card.innerHTML = `<h2>${k}</h2><p>Tilan tietoja ei saatu ladattua. Yritä hetken päästä uudelleen.</p>`; return; }
  const pr = META.prices?.[p.pa] || {};
  const month = Object.entries(pr).find(([k]) => k.startsWith("PKAUP|"))?.[1]?.[1] || "";
  const monthTxt = month ? `${parseInt(month.slice(5), 10)}/${month.slice(0, 4)}` : "";
  const xy = tm35(ll.lat, ll.lng);
  const kp = `https://asiointi.maanmittauslaitos.fi/karttapaikka/?lang=fi&share=customMarker&n=${xy.n}&e=${xy.e}&title=${encodeURIComponent(p.k)}&desc=&zoom=9`;
  const talo = `https://vv-tec.github.io/Talokartta/#kartta=14/${ll.lat.toFixed(5)}/${ll.lng.toFixed(5)}`;
  const species = Object.keys(SPECIES).filter((s) => p["s" + s]).map((s) =>
    `<tr><td>${SPECIES[s]}</td><td>${fmt(p["s" + s])} m³</td></tr>`).join("");
  const bars = DEV.filter(([k]) => p[k]).map(([k, , c]) => `<span style="width:${p[k]}%;background:${c}" title="${k}"></span>`).join("");
  const devRows = DEV.filter(([k]) => p[k]).map(([k, lab, c]) =>
    `<tr><td><i style="display:inline-block;width:10px;height:10px;background:${c};border-radius:2px"></i> ${lab}</td><td>${p[k]} %</td></tr>`).join("");
  document.getElementById("card").innerHTML = `
    <button class="x" aria-label="Sulje" onclick="document.getElementById('card').style.display='none'">×</button>
    <h2>${p.k}</h2>
    <div class="sec">Puuston arvo</div>
    <table>
      <tr><td><b>Puuston arvo</b></td><td><b>${eur(p.e)}</b></td></tr>
      <tr><td>per hehtaari metsämaata</td><td>${fmt(p.eh)} €/ha</td></tr>
      <tr><td>tukkipuu / kuitupuu</td><td>${eur(p.et)} / ${eur(p.ek)}</td></tr>
      <tr><td>Arvo hakkuutavan hinnoin</td><td>${eur(p.eu)}</td></tr>
    </table>
    <div class="note">Pystykaupan keskihinnat ${AREAS[p.pa] || ""} ${monthTxt} (Luke). Hakkuutavan hinnoin: uudistuskypsä
      metsä uudistushakkuun, varttunut harvennushakkuun ja nuori ensiharvennuksen kantohinnoin.
      Laskennallinen arvo, ei kauppahinta.</div>
    <div class="sec">Alat</div>
    <table>
      <tr><td>Kokonaisala (${p.pn} palstaa)</td><td>${fmt(p.ka, 1)} ha</td></tr>
      <tr><td>Metsämaa</td><td>${fmt(p.mm, 1)} ha</td></tr>
      <tr><td>Kitu- ja joutomaa</td><td>${fmt(p.kj, 1)} ha</td></tr>
      <tr><td>Muu ala (pelto, piha, vesi, tieto puuttuu)</td><td>${fmt(p.mu, 1)} ha</td></tr>
      <tr><td>Hakkuurajoitus (esim. suojelu)</td><td>${p.hr} % metsämaasta</td></tr>
    </table>
    <div class="sec">Puusto</div>
    <table>
      <tr><td>Puumäärä</td><td>${fmt(p.v)} m³ (${fmt(p.vh)} m³/ha)</td></tr>
      <tr><td>tukkipuu / kuitupuu</td><td>${fmt(p.t)} / ${fmt(p.ku)} m³</td></tr>
      ${species}
      ${p.ik ? `<tr><td>Keski-ikä</td><td>${p.ik} v</td></tr>` : ""}
    </table>
    <div class="sec">Ikärakenne (osuus metsämaasta)</div>
    <div class="bars">${bars}</div>
    <table>${devRows}</table>
    <div class="sec">Metsäpohja</div>
    <table>
      <tr><td>Yleisin kasvupaikka</td><td>${SITES[p.kp] || "–"}</td></tr>
      <tr><td>Turvemaata / ojitettu</td><td>${p.tu} % / ${p.oj} %</td></tr>
    </table>
    <div class="sec">Muuta</div>
    <table>
      <tr><td>Metsätieto inventoitu</td><td>${p.i0 ? (p.i0 === p.i1 ? p.i0 : `${p.i0} – ${p.i1}`) : "–"}</td></tr>
      <tr><td>Rakennuksia (joista asuin-)</td><td>${p.rb} (${p.ab})</td></tr>
    </table>
    <div class="note"><a href="${kp}" target="_blank" rel="noopener">Karttapaikka</a> ·
      <a href="${talo}" target="_blank" rel="noopener">Talokartta tästä kohdasta</a></div>`;
  document.getElementById("card").style.display = "block";
}
