/* Talokartta – METSÄTILAT-näkymä (tiekartan kohta 6, vaihe 2).
 * Piilossa, kunnes omistaja hyväksyy: moodivalinta näkyy vain osoitteella ?moodi=metsa (tai ?moodi=talot).
 * Data tulee Metsakartta-repositorion sivulta (METSA_BASE): meta.json, f-<maakunta>.pmtiles (taso "f", zoomista
 * meta.poly_minzoom alkaen), r.pmtiles (kaukonäkymän metsäkuva: PNG-tiilet Luken VMI:stä, puuta koko alaa kohden
 * m³/ha; meta.grid; ei tietoruutua, omistajan päätös 9.11.2026) ja kortit/<kunta>.json (tietokortin tiedot).
 * Värit (omistajan päätökset 9.11.2026): liukuvat; kaukaa puuta koko alaa kohden (meri ja järvet vaalentavat),
 * lähellä tilan puuston määrä m³/ha metsämaata.
 * Tiilen ominaisuudet: k tunnus, ka kokonaisala ha, e puuston arvo €, eh €/ha metsämaata, vh m³/ha metsämaata, tu turvemaata %,
 * kp yleisin kasvupaikka 1–8, da/dt/d2/d3/d4/d5 kehitysluokkien osuudet % metsämaasta.
 * Kortin kentät: ks. Talokartan pipeline/metsa.py (CARD_KEYS).
 * Käyttää app.js:n globaaleja: map, $, nf, esc, makeRange, setHouseLayers, applyFilters, closeCard, closePanel, toast.
 */
"use strict";

(() => {
  const params = new URLSearchParams(location.search);
  if (!params.has("moodi")) return;  // piilotettu näkymä: ilman parametria sivu toimii kuten ennenkin

  const METSA_BASE = "https://vv-tec.github.io/Metsakartta/data/";
  const AREAS = { MPKH01: "Etelä-Suomi", MPKH02: "Keski-Suomi", MPKH03: "Savo-Karjala", MPKH04: "Kymi-Savo",
    MPKH05: "Etelä-Pohjanmaa", MPKH06: "Pohjois-Pohjanmaa", MPKH07: "Kainuu-Koillismaa", MPKH08: "Lappi" };
  const SPECIES = { sm: "Mänty ja muut havupuut", sk: "Kuusi", sb: "Koivu", sl: "Muut lehtipuut" };
  const SITES = { 1: "Lehto", 2: "Lehtomainen kangas", 3: "Tuore kangas", 4: "Kuivahko kangas", 5: "Kuiva kangas",
    6: "Karukkokangas", 7: "Kalliomaa ja hietikko", 8: "Lakimetsä ja tunturi", 0: "Ei tietoa" };
  const DEV = [["da", "Aukea / siemenpuusto", "#e9d8a6"], ["dt", "Taimikko", "#b5d99c"], ["d2", "Nuori kasvatusmetsä", "#7fbf7b"],
    ["d3", "Varttunut kasvatusmetsä", "#3f9a5a"], ["d4", "Uudistuskypsä", "#1b5e34"], ["d5", "Suojuspuusto", "#8c6d46"],
    ["de", "Eri-ikäisrakenteinen", "#6a8caf"]];
  const AGES = [["a", "Aukea ja taimikko", ["da", "dt"]], ["n", "Nuori kasvatusmetsä", ["d2"]],
    ["v", "Varttunut kasvatusmetsä", ["d3"]], ["u", "Uudistuskypsä", ["d4", "d5"]]];
  // Tilojen väri (omistajan päätös 9.11.2026): oletuksena puuta koko alaa kohden (vk, m³/ha) samalla asteikolla kuin
  // kaukonäkymän metsäkuva, jotta värit pysyvät synkronissa; vaihtoehtona puuston arvo yhteensä (e, €).
  const GREENS = ["#f1eadb", "#d6e5b9", "#a8cf8e", "#6fae6b", "#3c8a4f", "#1d5e34"];
  const RAMP_DEFAULT = [[0, GREENS[0]], [25, GREENS[1]], [50, GREENS[2]], [75, GREENS[3]], [100, GREENS[4]], [140, GREENS[5]]];
  const TILE_OPACITY = 0.55;
  let colorBy = "m3";
  try { if (localStorage.getItem("metsaVari") === "eur") colorBy = "eur"; } catch (e) { /* ei selaimen muistia */ }
  const m3Stops = () => FM?.grid?.ramp || RAMP_DEFAULT;
  const eurStops = () => {
    const st = FM?.e_stops?.length > 1 ? FM.e_stops : [0, 25000, 50000, 100000, 200000, 500000];
    return st.map((v, i) => [v, GREENS[Math.round(i * (GREENS.length - 1) / (st.length - 1))]]);
  };
  const colorExpr = () => colorBy === "eur"
    ? ["interpolate", ["linear"], ["coalesce", ["get", "e"], 0], ...eurStops().flat()]
    : ["interpolate", ["linear"], ["coalesce", ["get", "vk"], 0], ...m3Stops().flat()];
  const GRID = "metsa-r";     // kaukonäkymän metsäkuva (rasteri)
  const RASTER_OPACITY = 0.6; // metsäkuvan läpinäkyvyys (omistajan toive 9.11.2026: läpinäkyvämpi; kuvan oma peitto 0,78 → yht. ~0,47)
  // Ristihäivytys kaukonäkymästä tiloihin (omistajan valinta 9.11.2026): tilojen zoomista (poly_minzoom) alkaen metsäkuva
  // haalistuu XFADE zoomausaskeleen aikana ja tilat vahvistuvat FADE_IN askeleen aikana.
  const XFADE = 0.7, FADE_IN = 0.6;
  const fade = (z0, from, to, len) => ["interpolate", ["linear"], ["zoom"], z0, from, z0 + len, to];
  // even = portaat tasavälein (€-asteikko on epälineaarinen; väri muuttuu portaiden välillä lineaarisesti)
  const pos = (stops, i, even) => (even ? 100 * i / (stops.length - 1) : 100 * stops[i][0] / stops[stops.length - 1][0]);
  const gradient = (stops, even) => `linear-gradient(to right, ${stops.map(([, c], i) => `${c} ${pos(stops, i, even).toFixed(1)}%`).join(", ")})`;
  const legend = (stops, unit, op = 1, even = false, fmt = (v) => nf.format(v)) => `<div class="fgrad" style="background:${gradient(stops, even)};opacity:${op}"></div>
    <div class="fgrad-l">${stops.map(([v], i) => `<span style="left:${pos(stops, i, even).toFixed(1)}%">${fmt(v)}${i === stops.length - 1 ? "+" : ""}</span>`).join("")}</div>
    <div class="muted" style="font-size:12px;text-align:right">${unit}</div>`;
  const keur = (v) => (v >= 1000 ? `${nf.format(v / 1000)} t` : nf.format(v));
  function legendHtml() {
    const far = FM?.grid ? (FM.grid.opacity || 1) * RASTER_OPACITY : 0;
    const m3 = `<div class="muted" style="font-size:13px">${colorBy === "m3" ? "Puuta koko alaa kohden – sama asteikko kaukaa ja tiloissa" : "Kaukaa: puuta koko alaa kohden"}
        (meri, järvet ja pellot vaalentavat)</div>${legend(m3Stops(), "m³/ha", far || TILE_OPACITY)}`;
    const eu = colorBy === "eur" ? `<div class="muted" style="font-size:13px;margin-top:8px">Tilat: puuston arvo yhteensä</div>
        ${legend(eurStops(), "€ (t = tuhatta)", TILE_OPACITY, true, keur)}` : "";
    return m3 + eu;
  }
  function setColors() {
    for (const id of ids) if (map.getLayer(id + "-fill")) map.setPaintProperty(id + "-fill", "fill-color", colorExpr());
    if ($("fLegend")) $("fLegend").innerHTML = legendHtml();
  }
  const eur = (n) => nf.format(Math.round((n ?? 0) / 100) * 100) + " €";
  const ha = (n) => nf.format(Math.round((n ?? 0) * 10) / 10) + " ha";
  // Liukusäätimien portaat (viimeinen = ei ylärajaa)
  const EH_STOPS = [...Array.from({ length: 21 }, (_, i) => i * 1000), 25000, 30000, Infinity];
  const VH_STOPS = [...Array.from({ length: 16 }, (_, i) => i * 20), 350, 400, Infinity];
  const SL = {};              // liukusäätimet (makeRange, app.js)

  let FM = null;              // Metsakartan meta.json
  const HOUSE_HINT = $("hint").textContent;
  let ids = [];               // tasojen tunnisteet maakunnittain
  let selected = null;
  const CARDS = {};

  const M = {
    enabled: true,
    active: params.get("moodi") === "metsa",
  };
  window.Metsa = M;

  /* ---------- moodivalinta ---------- */
  const sw = $("modeSwitch");
  sw.hidden = false;
  sw.querySelectorAll("button").forEach((b) => b.addEventListener("click", () => setMode(b.dataset.m)));

  function setMode(m, fly) {
    M.active = m === "metsa";
    sw.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === m)));
    const u = new URL(location.href);
    u.searchParams.set("moodi", m);
    history.replaceState(null, "", u);
    closeCard();
    closePanel();
    $("panel").hidden = M.active;
    $("fpanel").hidden = !M.active;
    $("sub").textContent = M.active ? "Metsätilat avoimista aineistoista (esikatselu)" : (META?.title || "Asuinrakennukset avoimista rekistereistä");
    setHouseLayers(!M.active);
    $("hint").textContent = M.active ? "Lähennä nähdäksesi yksittäiset metsätilat" : HOUSE_HINT;
    for (const l of allLayers()) if (map.getLayer(l)) map.setLayoutProperty(l, "visibility", M.active ? "visible" : "none");
    if (fly) map.flyTo(fly);
    if (M.active) apply(); else applyFilters();
    updateCountSoon();
  }

  /* ---------- paneeli ---------- */
  function buildPanel() {
    const kp = FM?.kp || {};
    $("fpanel").innerHTML = `
      <div class="panel-h only-mobile"><h2>Metsätilat</h2>
        <button type="button" class="x" id="fpanelClose" aria-label="Sulje suodattimet">×</button></div>
      <section class="sum" aria-live="polite"><div class="big" id="fCount">–</div><div id="fLabel" class="muted">ladataan…</div></section>
      <section><h3>Kokonaisala (ha)</h3>
        <div class="fnum"><input type="number" id="fKaMin" min="0" step="1" inputmode="decimal" placeholder="vähintään" aria-label="Kokonaisala vähintään">–
          <input type="number" id="fKaMax" min="0" step="1" inputmode="decimal" placeholder="enintään" aria-label="Kokonaisala enintään"></div></section>
      <section><h3>Puuston arvo yhteensä (€)</h3>
        <div class="fnum"><input type="number" id="fEMin" min="0" step="10000" inputmode="numeric" placeholder="vähintään" aria-label="Puuston arvo vähintään">–
          <input type="number" id="fEMax" min="0" step="10000" inputmode="numeric" placeholder="enintään" aria-label="Puuston arvo enintään"></div></section>
      <section><h3>Puuston arvo (€/ha metsämaata)</h3><div class="range" id="fEhR"></div></section>
      <section><h3>Puuston määrä (m³/ha metsämaata)</h3><div class="range" id="fVhR"></div></section>
      <section><h3>Metsäpohja</h3>
        <select id="fPeat" class="fsel" aria-label="Maapohja">
          <option value="">Kivennäis- ja turvemaat</option>
          <option value="min">Pääosin kivennäismaata (turvetta alle 50 %)</option>
          <option value="peat">Pääosin turvemaata (vähintään 50 %)</option></select>
        <div class="muted" style="font-size:13px;margin-bottom:4px">Yleisin kasvupaikka</div>
        <div id="fSites" class="checks">${Object.keys(kp).sort((a, b) => a - b).map((c) =>
          `<label data-k="${c}"><input type="checkbox" value="${c}" checked><span>${esc(SITES[c] || c)}</span><span class="n">${nf.format(kp[c])}</span></label>`).join("")}</div></section>
      <section><h3>Ikäjakauma</h3><div class="muted" style="font-size:13px">Osuus metsämaasta vähintään</div>
        ${AGES.map(([id, lab]) => `<div class="fage"><label for="fAge-${id}"><span>${lab}</span><span id="fAge-${id}-v">0 %</span></label>
          <input type="range" id="fAge-${id}" min="0" max="100" step="10" value="0"></div>`).join("")}</section>
      <section><h3>Värit</h3>
        <div class="muted" style="font-size:13px;margin-bottom:2px">Tilojen väri</div>
        <div class="checks fcolor">
          <label><input type="radio" name="fColor" value="m3"${colorBy === "m3" ? " checked" : ""}><span>Puuston määrä (m³/ha)</span></label>
          <label><input type="radio" name="fColor" value="eur"${colorBy === "eur" ? " checked" : ""}><span>Puuston arvo yhteensä (€)</span></label></div>
        <div id="fLegend" style="margin-top:6px">${legendHtml()}</div>
        ${FM?.grid ? `<p class="muted" style="font-size:12px;margin:6px 0 0">Kaukonäkymä: Luonnonvarakeskus, monilähteisen VMI:n
          kartta-aineisto ${FM.grid.year} (kaikki metsät, myös valtion).</p>` : ""}</section>
      <button type="button" id="fReset" class="btn wide">Tyhjennä suodattimet</button>
      <p class="src">Metsätila = kiinteistö, jolla metsämaata yli 2 ha. Puuston arvo on laskennallinen (tukki- ja kuitupuu ×
        Luken kantohinnat), ei kauppahinta. Metsävaratieto: <a href="https://www.metsakeskus.fi/fi/avoin-metsa-ja-luontotieto" target="_blank" rel="noopener">Suomen metsäkeskus</a>,
        kiinteistöt: Maanmittauslaitos, kantohinnat: <a href="https://www.luke.fi/" target="_blank" rel="noopener">Luonnonvarakeskus</a>,
        rakennukset: SYKE Ryhti (kaikki CC BY 4.0). <span id="fUpdated"></span></p>`;
    $("fpanel").addEventListener("input", (e) => {
      if (e.target.name === "fColor") {
        colorBy = e.target.value;
        try { localStorage.setItem("metsaVari", colorBy); } catch (err) { /* ei selaimen muistia */ }
        setColors();
        return;
      }
      if (e.target.id.startsWith("fAge-")) $(e.target.id + "-v").textContent = e.target.value + " %";
      apply();
    });
    const noop = () => {};  // paneelin input-kuuntelija hoitaa suodatuksen
    SL.eh = makeRange($("fEhR"), EH_STOPS, (v) => (v === Infinity ? "ei ylärajaa" : `${nf.format(v)} €/ha`), noop);
    SL.vh = makeRange($("fVhR"), VH_STOPS, (v) => (v === Infinity ? "ei ylärajaa" : `${nf.format(v)} m³/ha`), noop);
    $("fpanelClose").addEventListener("click", closePanel);
    $("fReset").addEventListener("click", () => {
      $("fpanel").querySelectorAll("input[type=number]").forEach((i) => { i.value = ""; });
      $("fpanel").querySelectorAll("#fSites input").forEach((i) => { i.checked = true; });
      AGES.forEach(([id]) => { $("fAge-" + id).value = 0; $("fAge-" + id + "-v").textContent = "0 %"; });
      $("fPeat").value = "";
      SL.eh.reset(); SL.vh.reset();
      apply();
    });
    if (FM) {
      const d = new Date(FM.updated);
      $("fUpdated").textContent = `Päivitetty ${d.toLocaleDateString("fi-FI")}.`;
    }
  }

  const num = (id) => { const v = $(id)?.value; return v ? Number(v) : null; };
  function filterExpr() {
    const f = ["all"];
    const range = (key, lo, hi) => { if (lo !== null) f.push([">=", ["get", key], lo]); if (hi !== null) f.push(["<=", ["get", key], hi]); };
    range("ka", num("fKaMin"), num("fKaMax"));
    range("e", num("fEMin"), num("fEMax"));
    for (const key of ["eh", "vh"]) { const x = SL[key]?.expr(key); if (x) f.push(x); }
    const peat = $("fPeat")?.value;
    if (peat === "min") f.push(["<", ["coalesce", ["get", "tu"], 0], 50]);
    if (peat === "peat") f.push([">=", ["coalesce", ["get", "tu"], 0], 50]);
    const boxes = [...document.querySelectorAll("#fSites input")];
    const on = boxes.filter((b) => b.checked).map((b) => Number(b.value));
    if (on.length < boxes.length) f.push(["in", ["coalesce", ["get", "kp"], 0], ["literal", on]]);
    for (const [id, , keys] of AGES) {
      const v = Number($("fAge-" + id)?.value || 0);
      if (v > 0) f.push([">=", ["+", 0, ...keys.map((k) => ["coalesce", ["get", k], 0])], v]);
    }
    return f;
  }
  function activeCount() { return filterExpr().length - 1; }

  function apply() {
    if (!M.active) return;
    const f = filterExpr();
    for (const id of ids) for (const l of [id + "-fill", id + "-line"]) if (map.getLayer(l)) map.setFilter(l, f);
    const n = activeCount();
    $("fcount").hidden = !n; $("fcount").textContent = n;
    updateCountSoon();
  }

  /* ---------- tasot ---------- */
  const allLayers = () => [...ids.flatMap((id) => [id + "-fill", id + "-line", id + "-sel"]), GRID];
  const fillLayers = () => ids.map((i) => i + "-fill").filter((l) => map.getLayer(l));
  const gridOn = () => map.getLayer(GRID) && map.getZoom() < (FM.poly_minzoom || 10);
  M.addLayers = () => {
    if (!FM || !styleReady || (ids.length && map.getLayer(ids[0] + "-fill"))) return;  // styleReady: app.js
    // tilat taustakartan nimien alle, jotta paikannimet erottuvat
    // Taustakartta voi olla hetken kesken (esim. teeman vaihto) → getStyle() on tyhjä; yritetään uudelleen, kun kartta on valmis.
    const style = map.getStyle();
    if (!style?.layers) { map.once("idle", M.addLayers); return; }
    const before = style.layers.find((l) => l.type === "symbol")?.id;
    const minz = FM.poly_minzoom || 10;
    const vis = M.active ? "visible" : "none";
    ids = [];
    if (FM.grid?.type === "raster" && !map.getLayer(GRID)) {
      if (!map.getSource(GRID)) map.addSource(GRID, { type: "raster", url: "pmtiles://" + METSA_BASE + FM.grid.file, tileSize: 256 });
      map.addLayer({ id: GRID, type: "raster", source: GRID, maxzoom: minz + 1, layout: { visibility: vis },
        paint: { "raster-resampling": "linear", "raster-fade-duration": 0,
          "raster-opacity": fade(minz, RASTER_OPACITY, 0, XFADE) } }, before);
    }
    for (const r of FM.regions) {
      const id = "metsa-" + r.file.replace(/\.pmtiles$/, "");
      if (!map.getSource(id)) map.addSource(id, { type: "vector", url: "pmtiles://" + METSA_BASE + r.file });
      map.addLayer({ id: id + "-fill", type: "fill", source: id, "source-layer": "f", minzoom: minz, layout: { visibility: vis },
        paint: { "fill-color": colorExpr(), "fill-opacity": fade(minz, 0, TILE_OPACITY, FADE_IN) } }, before);
      map.addLayer({ id: id + "-line", type: "line", source: id, "source-layer": "f", minzoom: minz, layout: { visibility: vis },
        paint: { "line-color": "#24382b", "line-opacity": fade(minz, 0, 0.7, FADE_IN), "line-width": ["interpolate", ["linear"], ["zoom"], 10, 0.2, 15, 1.2] } }, before);
      map.addLayer({ id: id + "-sel", type: "line", source: id, "source-layer": "f", minzoom: minz, layout: { visibility: vis },
        filter: ["==", ["get", "k"], selected ?? "__none__"], paint: { "line-color": "#d1495b", "line-width": 3 } });
      ids.push(id);
    }
    apply();
  };

  /* ---------- laskuri ja vihje ---------- */
  let timer = null;
  function updateCountSoon() { clearTimeout(timer); timer = setTimeout(() => (M.active ? M.updateCount() : updateCount()), 120); }
  M.updateCount = () => {
    if (!FM) return;
    const close = map.getZoom() >= (FM.poly_minzoom || 10);
    $("hint").hidden = close;
    if (!close) {
      $("fCount").textContent = nf.format(FM.count);
      $("fLabel").textContent = FM.grid ? "metsätilaa. Kartan värit näyttävät, missä on paljon puuta; lähennä nähdäksesi yksittäiset tilat."
        : "metsätilaa. Lähennä nähdäksesi ne kartalla.";
      return;
    }
    const seen = new Set(map.queryRenderedFeatures({ layers: ids.map((i) => i + "-fill").filter((l) => map.getLayer(l)) }).map((f) => f.properties.k));
    $("fCount").textContent = nf.format(seen.size);
    $("fLabel").textContent = activeCount() ? "suodatettua metsätilaa näkyvissä" : "metsätilaa näkyvissä";
  };

  /* ---------- valinta ja kortti ---------- */
  M.hover = (e) => {
    if (gridOn()) { map.getCanvas().style.cursor = ""; return; }
    const layers = fillLayers();
    map.getCanvas().style.cursor = layers.length && map.queryRenderedFeatures(e.point, { layers }).length ? "pointer" : "";
  };
  M.click = (e) => {
    if (gridOn()) { closeCard(); return; }   // kaukonäkymässä ei tietoruutua
    const layers = fillLayers();
    const f = layers.length && map.queryRenderedFeatures(e.point, { layers })[0];
    if (f) select(f, e.lngLat); else closeCard();
  };
  M.clearSelection = () => {
    selected = null;
    for (const id of ids) if (map.getLayer(id + "-sel")) map.setFilter(id + "-sel", ["==", ["get", "k"], "__none__"]);
  };

  function cardData(k) {
    const muni = k.split("-")[0].padStart(3, "0");
    CARDS[muni] ??= fetch(`${METSA_BASE}${FM.cards || "kortit/"}${muni}.json?v=${encodeURIComponent(FM.updated)}`)
      .then((r) => (r.ok ? r.json() : null)).catch(() => null);
    return CARDS[muni].then((d) => {
      const row = d?.r?.[k];
      return row ? Object.fromEntries(d.c.map((c, i) => [c, row[i]]).filter(([, v]) => v !== null)) : null;
    });
  }
  M.has = (k) => (FM && k ? cardData(k).then(Boolean) : Promise.resolve(false));

  async function select(f, ll) {
    const k = f.properties.k;
    selected = k;
    for (const id of ids) if (map.getLayer(id + "-sel")) map.setFilter(id + "-sel", ["==", ["get", "k"], k]);
    const card = $("card");
    card.innerHTML = `<div class="card-h"><h2>${esc(k)}</h2><div class="place">Metsätila</div>
      <button type="button" class="x" id="closeCard" aria-label="Sulje tiedot">×</button></div>
      <div class="card-b"><p class="muted">Ladataan tietoja…</p></div>`;
    card.hidden = false;
    $("closeCard").addEventListener("click", closeCard);
    closePanel();
    const x = await cardData(k);
    if (selected !== k) return;  // ehdittiin valita toinen tila
    if (!x) { card.querySelector(".card-b").innerHTML = '<p class="muted">Tilan tietoja ei saatu ladattua. Yritä hetken päästä uudelleen.</p>'; return; }
    const p = { tu: 0, oj: 0, hr: 0, ...x };
    const pr = FM.prices?.[p.pa] || {};
    const month = Object.entries(pr).find(([key]) => key.startsWith("PKAUP|"))?.[1]?.[1] || "";
    const monthTxt = month ? `${parseInt(month.slice(5), 10)}/${month.slice(0, 4)}` : "";
    const lat = ll.lat, lon = ll.lng;
    const gm = `https://www.google.com/maps/search/?api=1&query=${lat.toFixed(6)},${lon.toFixed(6)}`;
    const xy = tm35(lat, lon);
    const kp = `https://asiointi.maanmittauslaitos.fi/karttapaikka/?lang=fi&share=customMarker&n=${xy.n}&e=${xy.e}&title=${encodeURIComponent(k)}&desc=&zoom=9`;
    const dev = DEV.filter(([key]) => p[key]);
    card.innerHTML = `
      <div class="card-h">
        <h2>${esc(k)}</h2><div class="place">Metsätila · ${ha(p.ka)}${p.pn > 1 ? ` · ${p.pn} palstaa` : ""}</div>
        <button type="button" class="x" id="closeCard" aria-label="Sulje tiedot">×</button>
      </div>
      <div class="card-b">
        <div class="year"><span class="big">${eur(p.e)}</span><span class="sub">puuston arvo<br>${nf.format(p.eh ?? 0)} €/ha metsämaata</span></div>
        <div class="sect"><h4>Puuston arvo</h4><dl class="kv">
          <dt>Tukkipuu</dt><dd>${eur(p.et)}</dd>
          <dt>Kuitupuu</dt><dd>${eur(p.ek)}</dd>
          <dt>Hakkuutavan hinnoin</dt><dd>${eur(p.eu)}</dd>
        </dl><p class="fine">Pystykaupan keskihinnat ${AREAS[p.pa] || ""} ${monthTxt} (Luke). Hakkuutavan hinnoin: uudistuskypsä
          metsä uudistushakkuun, varttunut harvennushakkuun ja nuori ensiharvennuksen kantohinnoin. Laskennallinen arvo, ei kauppahinta.</p></div>
        <div class="sect"><h4>Alat</h4><dl class="kv">
          <dt>Kokonaisala</dt><dd>${ha(p.ka)}</dd>
          <dt>Metsämaa</dt><dd>${ha(p.mm)}</dd>
          <dt>Kitu- ja joutomaa</dt><dd>${ha(p.kj)}</dd>
          <dt>Muu ala</dt><dd>${ha(p.mu)}</dd>
          <dt>Hakkuurajoitus</dt><dd>${p.hr} % metsämaasta</dd>
        </dl><p class="fine">Muu ala: pellot, pihat, tiet, vedet ja alueet, joilta metsätieto puuttuu. Hakkuurajoitus: esim. suojelualue.</p></div>
        <div class="sect"><h4>Puusto</h4><dl class="kv">
          <dt>Puumäärä</dt><dd>${nf.format(p.v ?? 0)} m³ · ${nf.format(p.vh ?? 0)} m³/ha metsämaata</dd>
          ${p.vk != null ? `<dt>Koko alaa kohden</dt><dd>${nf.format(p.vk)} m³/ha</dd>` : ""}
          <dt>Tukki / kuitu</dt><dd>${nf.format(p.t ?? 0)} / ${nf.format(p.ku ?? 0)} m³</dd>
          ${Object.entries(SPECIES).filter(([key]) => p[key]).map(([key, lab]) => `<dt>${lab}</dt><dd>${nf.format(p[key])} m³</dd>`).join("")}
          ${p.ik != null ? `<dt>Keski-ikä</dt><dd>${p.ik} v</dd>` : ""}
        </dl></div>
        <div class="sect"><h4>Ikärakenne (osuus metsämaasta)</h4>
          <div class="bars">${dev.map(([key, , c]) => `<span style="width:${p[key]}%;background:${c}"></span>`).join("")}</div>
          <dl class="kv txt">${dev.map(([key, lab, c]) => `<dt><span class="sw" style="background:${c}"></span>${lab}</dt><dd>${p[key]} %</dd>`).join("")}</dl></div>
        <div class="sect"><h4>Metsäpohja</h4><dl class="kv txt">
          <dt>Yleisin kasvupaikka</dt><dd>${SITES[p.kp] || "–"}</dd>
          <dt>Turvemaata</dt><dd>${p.tu} %</dd>
          <dt>Ojitettu</dt><dd>${p.oj} %</dd>
          <dt>Metsätieto inventoitu</dt><dd>${p.i0 ? (p.i0 === p.i1 ? p.i0 : `${p.i0} – ${p.i1}`) : "–"}</dd>
        </dl></div>
        <div class="sect"><h4>Avaa muualla</h4><div class="links">
          ${p.ab ? `<a href="#" id="toHouses">Talonäkymä <small>tilalla ${p.ab} asuinrakennus${p.ab > 1 ? "ta" : ""} – näytä talokartalla</small></a>` : ""}
          <a href="${kp}" target="_blank" rel="noopener">Maanmittauslaitoksen Karttapaikka <small>kiinteistörajat ja maastokartta ↗</small></a>
          <a href="${gm}" target="_blank" rel="noopener">Google Maps <small>kartta ja ilmakuva ↗</small></a>
        </div></div>
        <p class="fine">Rakennuksia tilalla ${p.rb ?? 0}, joista asuinrakennuksia ${p.ab ?? 0} (Ryhti). Metsävaratieto: Suomen metsäkeskus;
          tarkkuus noin ±20 % puuston kokonaismäärästä useimmilla kuvioilla.</p>
      </div>`;
    card.scrollTop = 0;
    $("closeCard").addEventListener("click", closeCard);
    $("toHouses")?.addEventListener("click", (ev) => {
      ev.preventDefault();
      setMode("talot", { center: [lon, lat], zoom: Math.max(map.getZoom(), 14.5) });
    });
  }

  // Talon kortista linkki metsätilaan, jos kiinteistö on metsätila
  M.houseLink = (k, el) => {
    if (!el || !k) return;
    M.has(k).then((yes) => {
      if (!yes || !el.isConnected) return;
      el.innerHTML = `<div class="sect"><h4>Metsätila</h4><div class="links"><a href="#" id="toForest">Metsätilanäkymä
        <small>kiinteistöllä metsämaata yli 2 ha – näytä puuston arvo ja metsätiedot</small></a></div></div>`;
      $("toForest").addEventListener("click", (ev) => { ev.preventDefault(); setMode("metsa", { zoom: Math.min(map.getZoom(), 13.5) }); });
    });
  };

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

  /* ---------- käynnistys ---------- */
  buildPanel();
  setMode(M.active ? "metsa" : "talot");
  fetch(METSA_BASE + "meta.json?v=" + Date.now())
    .then((r) => (r.ok ? r.json() : null)).catch(() => null)
    .then((m) => {
      if (!m) { toast("Metsätilojen tietoja ei saatu ladattua."); return; }
      FM = m;
      M.meta = m;
      buildPanel();
      M.addLayers();
      if (M.active && !location.hash.includes("kartta=") && m.regions[0]?.bounds) {
        const b = m.regions.reduce((acc, r) => r.bounds ? [Math.min(acc[0], r.bounds[0]), Math.min(acc[1], r.bounds[1]),
          Math.max(acc[2], r.bounds[2]), Math.max(acc[3], r.bounds[3])] : acc, [180, 90, -180, -90]);
        map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, duration: 0 });
      }
      setMode(M.active ? "metsa" : "talot");
    });
})();
