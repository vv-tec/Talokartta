/* Metsakartta – esikatselu. Lukee data/meta.json:n ja näyttää metsätilat:
 * zoom 6–10 pisteet (fp.pmtiles, taso "fp"), zoomista 11 rajat (f-<maakunta>.pmtiles, taso "f").
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
  container: "map", style: "https://tiles.openfreemap.org/styles/positron", center: [24.2, 60.85], zoom: 8.5,
  hash: "kartta", attributionControl: false,
});
map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
map.addControl(new maplibregl.AttributionControl({ compact: true, customAttribution:
  'Metsävaratieto © Suomen metsäkeskus · Kiinteistöt © Maanmittauslaitos · Kantohinnat © Luonnonvarakeskus · Rakennukset © SYKE Ryhti · <a href="https://openfreemap.org" target="_blank" rel="noopener">OpenFreeMap</a> © <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>' }), "bottom-right");

let META = null;
document.getElementById("legend").innerHTML = STEPS.map(([v, c], i) =>
  `<i style="background:${c}"></i><span>${i < STEPS.length - 1 ? `${fmt(v)}–${fmt(STEPS[i + 1][0])}` : `yli ${fmt(v)}`} €/ha</span>`).join("");

map.on("load", async () => {
  META = await (await fetch("data/meta.json", { cache: "no-cache" })).json();
  const upd = new Date(META.updated).toLocaleString("fi-FI", { dateStyle: "short", timeStyle: "short" });
  document.getElementById("stats").textContent =
    `${fmt(META.count)} metsätilaa: ${META.regions.map((r) => r.name).join(", ")}. Päivitetty ${upd}.`;
  const minz = META.poly_minzoom || 11;
  map.addSource("fp", { type: "vector", url: dataUrl("fp.pmtiles") });
  map.addLayer({ id: "fp", type: "circle", source: "fp", "source-layer": "fp", maxzoom: minz,
    paint: { "circle-color": color, "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 1.5, 10, 4],
      "circle-stroke-color": "#24382b", "circle-stroke-width": 0.4 } });
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
  }
  map.on("click", "fp", (e) => select(e.features[0], e.lngLat));
  for (const l of ["fp", ...META.regions.map((r) => r.file.replace(/\.pmtiles$/, "") + "-fill")]) {
    map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
  }
});

function select(f, ll) {
  const p = f.properties;
  for (const r of META.regions) map.setFilter(r.file.replace(/\.pmtiles$/, "") + "-sel", ["==", ["get", "k"], p.k]);
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
