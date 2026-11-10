// Talokartta – julkaistun sivun automaattinen tarkistus (tiekartan kohta 3b).
// Avaa sivun oikeassa selaimessa (Playwright + Chromium) ja tarkistaa, että se toimii kuten käyttäjällä:
// ei JS-virheitä, meta.json on juuri julkaistu versio, taustakartta ja kaikki karttatiedostot latautuvat,
// tunnetuissa paikoissa näkyy rakennuksia, tietokortti aukeaa ja puhelinkoossa suodatinpaneeli toimii.
// Ei kuormita rekistereitä (vain oma sivu ja OpenFreeMap). Valvoo myös, ettei sivu ota yhteyttä muihin palveluihin
// (tietosuoja 10.11.2026: kirjastot ja fontit omalta sivulta, ks. tyokalut/hae_kirjastot.py).
//
// Ympäristömuuttujat (kaikki valinnaisia):
//   SITE_URL         tarkistettava sivu (oletus https://vv-tec.github.io/Talokartta/)
//   EXPECT_UPDATED   buildin meta.json:n "updated" – sivulla pitää olla juuri tämä versio
//   EXPECT_COUNT     buildin rakennusmäärä
//   OUT_DIR          kuvakaappausten kansio (oletus sivutarkistus)
//   ATTEMPTS         yrityskerrat ennen hälytystä (oletus 2; tilapäinen verkkokatko ei hälytä)
// Lopputulos: GitHubin ::error-rivit (→ notify-issueen "Syy") ja yhteenveto ajon sivulle; virhe → exit 1.

import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const SITE = (process.env.SITE_URL || "https://vv-tec.github.io/Talokartta/").replace(/\/?$/, "/");
const EXPECT_UPDATED = process.env.EXPECT_UPDATED || "";
const EXPECT_COUNT = process.env.EXPECT_COUNT ? Number(process.env.EXPECT_COUNT) : null;
const OUT = process.env.OUT_DIR || "sivutarkistus";
const ATTEMPTS = Number(process.env.ATTEMPTS || 2);
const GH = !!process.env.GITHUB_ACTIONS;
const BUST = process.env.GITHUB_RUN_ID || String(Date.now());

// Tunnetut paikat: jokaisessa pitää näkyä asuinrakennuksia. Ensimmäisessä avataan tietokortti.
// Valittu eri maakunnista (myös suurin tiedosto Uusimaa ja pohjoisin Lappi).
const PLACES = [
  { name: "Tampereen keskusta", lat: 61.4978, lon: 23.761, z: 15, card: true },
  { name: "Tammelan keskusta", lat: 60.8095, lon: 23.763, z: 14 },
  { name: "Helsinki, Kallio", lat: 60.184, lon: 24.95, z: 15 },
  { name: "Rovaniemen keskusta", lat: 66.503, lon: 25.729, z: 14 },
];
const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };
const TIMEOUT = 60_000;
// Palvelut, joihin kävijän selain saa ottaa yhteyttä (tietosuojaseloste luettelee nämä): oma sivu, Metsakartan tiedostot
// ja taustakartta. Uusi palvelu (esim. kävijätilasto) → lisää tähän JA tietosuojaselosteeseen.
const ALLOWED_HOSTS = [new URL(SITE).host, "vv-tec.github.io", "tiles.openfreemap.org"];

fs.mkdirSync(OUT, { recursive: true });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const log = (s) => console.log(s);
const ghText = (s) => String(s).replace(/%/g, "%25").replace(/\r/g, "").replace(/\n/g, " ");

// Odottaa, että kartta on piirtänyt kaiken (MapLibre "idle"), enintään TIMEOUT.
async function idle(page) {
  await page.evaluate((ms) => new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("kartta ei valmistunut ajassa")), ms);
    map.once("idle", () => { clearTimeout(t); res(); });
    map.triggerRepaint();
  }), TIMEOUT);
}

// Seuraa sivun virheitä ja epäonnistuneita latauksia.
function watch(page, bag) {
  page.on("request", (r) => {
    const u = new URL(r.url());
    if (u.protocol === "http:" || u.protocol === "https:") bag.hosts.add(u.host);
  });
  page.on("pageerror", (e) => bag.pageErrors.push(String(e.message || e).slice(0, 300)));
  page.on("console", (m) => { if (m.type() === "error") bag.consoleErrors.push(m.text().slice(0, 300)); });
  page.on("requestfailed", (r) => {
    const f = r.failure()?.errorText || "";
    if (/ERR_ABORTED|NS_BINDING_ABORTED/.test(f)) return;  // kartan liikuttelu peruu tiilipyyntöjä: normaalia
    bag.failed.push(`${r.url().slice(0, 140)} (${f})`);
  });
  page.on("response", (r) => {
    const u = r.url(), host = new URL(u).host;
    if (host === "tiles.openfreemap.org" && !u.includes("/styles/") && r.status() < 400) bag.baseTiles++;
    if (r.status() >= 400) bag.failed.push(`${u.slice(0, 140)} (HTTP ${r.status()})`);
  });
}

async function attempt(n) {
  const checks = [];  // { name, ok, info }
  const ok = (name, info = "") => checks.push({ name, ok: true, info });
  const bad = (name, info) => checks.push({ name, ok: false, info });
  const shots = [];
  const bag = { pageErrors: [], consoleErrors: [], failed: [], baseTiles: 0, hosts: new Set() };
  const browser = await chromium.launch();
  try {
    // ---------- 1. meta.json: onko sivulla juuri julkaistu versio ----------
    const api = await (await browser.newContext()).request;
    let meta = null;
    for (let i = 0; i < 6; i++) {  // Pagesin välimuisti voi näyttää vanhaa hetken julkaisun jälkeen
      const r = await api.get(`${SITE}data/meta.json?v=${BUST}-${Date.now()}`, { timeout: 30_000 }).catch((e) => ({ ok: () => false, status: () => String(e.message).slice(0, 80) }));
      if (r.ok()) meta = await r.json().catch(() => null);
      if (meta && (!EXPECT_UPDATED || meta.updated === EXPECT_UPDATED)) break;
      if (i < 5) { log(`  meta.json: ${meta ? `vielä versio ${meta.updated}` : `ei saatu (${r.status()})`}, odotetaan 30 s`); await sleep(30_000); }
    }
    if (!meta) { bad("meta.json", "meta.json ei latautunut"); return { checks, shots }; }
    if (EXPECT_UPDATED && meta.updated !== EXPECT_UPDATED) bad("Julkaistu versio", `sivulla on versio ${meta.updated}, juuri tehty on ${EXPECT_UPDATED} (julkaisu ei näy)`);
    else ok("Julkaistu versio", `päivitetty ${meta.updated}`);
    const regions = meta.regions || [];
    const sum = regions.reduce((a, r) => a + (r.count || 0), 0);
    if (EXPECT_COUNT != null && meta.count !== EXPECT_COUNT) bad("Rakennusmäärä", `sivulla ${meta.count}, buildissa ${EXPECT_COUNT}`);
    else if (!regions.length || sum !== meta.count) bad("Rakennusmäärä", `maakuntia ${regions.length}, maakuntien summa ${sum} ≠ ${meta.count}`);
    else ok("Rakennusmäärä", `${meta.count} rakennusta, ${regions.length} maakuntaa`);

    // ---------- 2. karttatiedostot: jokainen vastaa osapyyntöön (HTTP 206, PMTiles v3 -otsake) ----------
    const files = [meta.grid || "g.pmtiles", ...regions.map((r) => r.file)];
    const broken = [];
    for (const f of files) {
      const r = await api.get(`${SITE}data/${f}`, { headers: { Range: "bytes=0-126" }, timeout: 30_000 }).catch(() => null);
      const b = r ? await r.body().catch(() => Buffer.alloc(0)) : Buffer.alloc(0);
      if (!r || r.status() !== 206 || b.subarray(0, 7).toString("latin1") !== "PMTiles" || b[7] !== 3)
        broken.push(`${f} (${r ? `HTTP ${r.status()}` : "ei vastausta"})`);
    }
    broken.length ? bad("Karttatiedostot", `rikki: ${broken.join(", ")}`) : ok("Karttatiedostot", `${files.length} tiedostoa vastaa`);

    // ---------- 3. työpöytä: sivu, taustakartta, tiheysruudut ----------
    const desk = await browser.newContext({ viewport: DESKTOP, locale: "fi-FI", timezoneId: "Europe/Helsinki" });
    const page = await desk.newPage();
    watch(page, bag);
    await page.goto(`${SITE}?v=${BUST}`, { waitUntil: "load", timeout: TIMEOUT });
    try {
      await page.waitForFunction(() => typeof META !== "undefined" && META && B_LAYERS.length > 0 && map.isStyleLoaded(), null, { timeout: TIMEOUT });
      await idle(page);
      ok("Sivu latautui");
    } catch (e) {
      bad("Sivu latautui", `kartta tai tiedot eivät latautuneet: ${e.message.split("\n")[0]}`);
      await page.screenshot({ path: path.join(OUT, "tyopoyta-virhe.png") }); shots.push("tyopoyta-virhe.png");
      return { checks, shots, bag };
    }
    const s = await page.evaluate(() => ({
      layers: map.getStyle().layers.length, ours: 2 + 2 * B_LAYERS.length, regions: B_LAYERS.length,
      grid: map.queryRenderedFeatures({ layers: ["g"] }).length,
      vis: document.getElementById("visCount").textContent, upd: document.getElementById("updated").textContent,
    }));
    if (s.layers - s.ours < 20 || bag.baseTiles === 0) bad("Taustakartta", `taustakartan tasoja ${s.layers - s.ours}, ladattuja tiiliä ${bag.baseTiles}`);
    else ok("Taustakartta", `${bag.baseTiles} tiiltä ladattu`);
    if (s.regions !== regions.length) bad("Maakuntatasot", `kartalla ${s.regions}, meta.jsonissa ${regions.length}`);
    else ok("Maakuntatasot", `${s.regions}`);
    if (!s.grid) bad("Tiheysruudut", "koko Suomen näkymässä ei näy ruutuja");
    else ok("Tiheysruudut", `${s.grid} ruutua näkyvissä`);
    if (s.vis.replace(/\D/g, "") !== String(meta.count) || !/päivitetty/.test(s.upd)) bad("Paneelin luvut", `laskuri "${s.vis}", päivitysaika "${s.upd}"`);
    else ok("Paneelin luvut", `${s.vis} · ${s.upd}`);
    await page.screenshot({ path: path.join(OUT, "1-tyopoyta-suomi.png") }); shots.push("1-tyopoyta-suomi.png");

    // ---------- 4. tunnetut paikat: rakennuksia näkyy; tietokortti ----------
    for (const p of PLACES) {
      await page.evaluate(({ lat, lon, z }) => map.jumpTo({ center: [lon, lat], zoom: z }), p);
      try { await idle(page); } catch (e) { bad(p.name, e.message); continue; }
      const n = await page.evaluate(() => new Set(map.queryRenderedFeatures({ layers: B_LAYERS }).map((f) => f.properties.id)).size);
      n > 0 ? ok(p.name, `${n} rakennusta näkyvissä`) : bad(p.name, "ei yhtään rakennusta näkyvissä");
      if (!p.card || !n) continue;
      // klikataan rakennusta, jolla on osoite ja palstan ala ja jonka lähellä ei ole muita (osuu varmasti oikeaan)
      const t = await page.evaluate(() => {
        const c = map.getCanvas().getBoundingClientRect();
        const fs = map.queryRenderedFeatures({ layers: B_LAYERS }).map((f) => ({ p: f.properties, pt: map.project(f.geometry.coordinates) }));
        let best = null, bd = -1;
        for (const f of fs) {
          if (!f.p.a || !f.p.pa || f.pt.x < c.width * 0.15 || f.pt.x > c.width * 0.55 || f.pt.y < c.height * 0.2 || f.pt.y > c.height * 0.8) continue;
          const d = Math.min(...fs.filter((o) => o.p.id !== f.p.id).map((o) => Math.hypot(o.pt.x - f.pt.x, o.pt.y - f.pt.y)));
          if (d > bd) { bd = d; best = f; }
        }
        return best && { id: best.p.id, a: best.p.a, x: c.left + best.pt.x, y: c.top + best.pt.y };
      });
      if (!t) { bad("Tietokortti", "sopivaa rakennusta (osoite ja palstan ala) ei löytynyt klikattavaksi"); continue; }
      await page.mouse.click(t.x, t.y);
      try {
        await page.waitForSelector("#card:not([hidden]) h2", { timeout: 10_000 });
        const c = await page.evaluate(() => {
          const dd = [...document.querySelectorAll("#card dt")].find((d) => d.textContent === "Palstan ala")?.nextElementSibling?.textContent;
          return { sel: state.selected, h2: document.querySelector("#card h2").textContent, pa: dd || "" };
        });
        if (c.sel !== t.id) bad("Tietokortti", `klikattiin ${t.id}, valittiin ${c.sel}`);
        else if (c.h2 !== t.a) bad("Tietokortti", `osoite "${c.h2}", odotettiin "${t.a}"`);
        else if (!/(m²|ha)$/.test(c.pa)) bad("Tietokortti", `palstan ala puuttuu ("${c.pa}")`);
        else ok("Tietokortti", `${c.h2}, palstan ala ${c.pa}`);
      } catch {
        bad("Tietokortti", "kortti ei auennut klikkauksesta");
      }
      await page.screenshot({ path: path.join(OUT, "2-tyopoyta-kortti.png") }); shots.push("2-tyopoyta-kortti.png");
    }
    await desk.close();

    // ---------- 5. puhelin: jaettu linkki, Suodattimet-nappi avaa paneelin ----------
    const phone = await browser.newContext({ viewport: PHONE, isMobile: true, hasTouch: true, deviceScaleFactor: 2, locale: "fi-FI" });
    const mp = await phone.newPage();
    watch(mp, bag);
    const pl = PLACES[0];
    await mp.goto(`${SITE}?v=${BUST}#kartta=${pl.z}/${pl.lat}/${pl.lon}`, { waitUntil: "load", timeout: TIMEOUT });
    try {
      await mp.waitForFunction(() => typeof META !== "undefined" && META && B_LAYERS.length > 0 && map.isStyleLoaded(), null, { timeout: TIMEOUT });
      await idle(mp);
      const n = await mp.evaluate(() => map.queryRenderedFeatures({ layers: B_LAYERS }).length);
      n > 0 ? ok("Puhelin: kartta", `${n} rakennusta (jaettu linkki ${pl.name})`) : bad("Puhelin: kartta", "jaetun linkin näkymässä ei rakennuksia");
      await mp.screenshot({ path: path.join(OUT, "3-puhelin-kartta.png") }); shots.push("3-puhelin-kartta.png");
      const btn = mp.locator("#filtersBtn");
      if (!(await btn.isVisible())) bad("Puhelin: suodattimet", "Suodattimet-nappi ei näy");
      else {
        await btn.tap();
        await sleep(700);  // paneelin liukuanimaatio
        const st = await mp.evaluate(() => {
          const el = document.getElementById("panel"), r = el.getBoundingClientRect();
          return { open: el.classList.contains("open"), exp: document.getElementById("filtersBtn").getAttribute("aria-expanded"), top: r.top, h: innerHeight };
        });
        st.open && st.exp === "true" && st.top < st.h * 0.5
          ? ok("Puhelin: suodattimet", "nappi avaa paneelin")
          : bad("Puhelin: suodattimet", `paneeli ei avautunut (open ${st.open}, yläreuna ${Math.round(st.top)} / ${st.h} px)`);
        await mp.screenshot({ path: path.join(OUT, "4-puhelin-suodattimet.png") }); shots.push("4-puhelin-suodattimet.png");
      }
    } catch (e) {
      bad("Puhelin: kartta", `ei latautunut: ${e.message.split("\n")[0]}`);
    }
    await phone.close();

    // ---------- 6. virheet koko käynnin ajalta ----------
    bag.pageErrors.length ? bad("JavaScript-virheet", [...new Set(bag.pageErrors)].slice(0, 3).join(" | ")) : ok("JavaScript-virheet", "ei virheitä");
    const ess = [...new Set(bag.failed)];
    ess.length ? bad("Lataukset", `epäonnistui ${ess.length}: ${ess.slice(0, 3).join(" | ")}`) : ok("Lataukset", "kaikki onnistuivat");
    const other = [...bag.hosts].filter((h) => !ALLOWED_HOSTS.includes(h));
    other.length ? bad("Ulkopuoliset palvelut", `sivu otti yhteyttä: ${other.join(", ")} (päivitä ALLOWED_HOSTS ja tietosuojaseloste)`)
      : ok("Ulkopuoliset palvelut", `vain ${[...bag.hosts].sort().join(", ")}`);
    return { checks, shots, bag };
  } catch (e) {
    bad("Tarkistus", `keskeytyi: ${String(e.message || e).split("\n")[0]}`);
    return { checks, shots, bag };
  } finally {
    await browser.close();
  }
}

// ---------- ajo: uusi yritys ennen hälytystä ----------
let res, first = null;
for (let n = 1; n <= ATTEMPTS; n++) {
  log(`Tarkistetaan ${SITE} (yritys ${n}/${ATTEMPTS})`);
  res = await attempt(n);
  for (const c of res.checks) log(`  ${c.ok ? "✓" : "✗"} ${c.name}${c.info ? ": " + c.info : ""}`);
  if (res.bag?.consoleErrors?.length) log(`  (konsolin virheilmoituksia ${res.bag.consoleErrors.length}, esim. ${res.bag.consoleErrors[0]})`);
  if (res.checks.every((c) => c.ok)) break;
  first ??= res;
  if (n < ATTEMPTS) { log("  → yritetään uudelleen 60 s päästä (tilapäinen katko ei hälytä)"); await sleep(60_000); }
}
const failed = res.checks.filter((c) => !c.ok);
if (GH) {
  if (failed.length) for (const c of failed.slice(0, 8)) console.log(`::error title=Sivun tarkistus::${ghText(`${c.name}: ${c.info}`)}`);
  else if (first) console.log(`::warning title=Sivun tarkistus::${ghText("Ensimmäinen yritys epäonnistui, uusinta onnistui: " + first.checks.filter((c) => !c.ok).map((c) => `${c.name}: ${c.info}`).join("; "))}`);
}
if (process.env.GITHUB_STEP_SUMMARY) {
  const rows = res.checks.map((c) => `| ${c.ok ? "✅" : "❌"} | ${c.name} | ${String(c.info).replace(/\|/g, "/")} |`).join("\n");
  fs.appendFileSync(process.env.GITHUB_STEP_SUMMARY,
    `## Sivun tarkistus ${failed.length ? "– ongelmia löytyi" : "– kaikki kunnossa"}\n\n${SITE}\n\n| | Kohta | Tulos |\n|---|---|---|\n${rows}\n\n`
    + `Kuvakaappaukset: ajon liitteenä **sivutarkistus** (${res.shots.join(", ") || "ei kuvia"}).\n`);
}
log(failed.length ? `Ongelmia: ${failed.length}` : "Sivu toimii.");
process.exit(failed.length ? 1 : 0);
