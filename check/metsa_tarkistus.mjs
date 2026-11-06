// Metsakartta – julkaistun esikatselusivun automaattinen tarkistus (ajetaan Metsakartan työnkulussa julkaisun jälkeen).
// Avaa sivun Chromiumilla ja tarkistaa: ei JS-virheitä, meta.json on juuri julkaistu versio, kaukaa ei näy mitään,
// Tammelassa näkyy metsätiloja, suodatin vähentää ja tyhjennys palauttaa ne, tietokortti aukeaa.
// Ympäristömuuttujat: SITE_URL (oletus https://vv-tec.github.io/Metsakartta/), EXPECT_UPDATED, ATTEMPTS (oletus 2).
import { chromium } from "playwright";

const SITE = (process.env.SITE_URL || "https://vv-tec.github.io/Metsakartta/").replace(/\/?$/, "/");
const EXPECT_UPDATED = process.env.EXPECT_UPDATED || "";
const ATTEMPTS = Number(process.env.ATTEMPTS || 2);
const GH = !!process.env.GITHUB_ACTIONS;
const TIMEOUT = 60_000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function idle(page) {
  await page.evaluate((ms) => new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("kartta ei valmistunut ajassa")), ms);
    map.once("idle", () => { clearTimeout(t); res(); });
    map.triggerRepaint();
  }), TIMEOUT);
}

const visible = (page) => page.evaluate(() =>
  new Set(map.queryRenderedFeatures({ layers: META.regions.map((r) => r.file.replace(/\.pmtiles$/, "") + "-fill") })
    .map((f) => f.properties.k)).size);

// Pages-välimuisti: odotetaan, kunnes juuri julkaistu meta.json näkyy (enintään 5 × 30 s), ennen sivun testausta.
async function waitForVersion() {
  if (!EXPECT_UPDATED) return;
  for (let i = 1; i <= 6; i++) {
    const m = await fetch(`${SITE}data/meta.json?v=${Date.now()}`).then((r) => r.json()).catch(() => null);
    if (m?.updated === EXPECT_UPDATED) return;
    console.log(`  meta.json: ${m ? "vielä versio " + m.updated : "ei saatu"}, odotetaan 30 s`);
    if (i < 6) await sleep(30_000);
  }
}

async function run() {
  const results = [];
  const ok = (name, pass, info = "") => { results.push({ name, pass, info }); console.log(`${pass ? "✓" : "✗"} ${name}${info ? " – " + info : ""}`); };
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message || e).slice(0, 300)));
  try {
    await page.goto(SITE + "?t=" + Date.now() + "#kartta=9/60.75/23.85", { waitUntil: "load", timeout: TIMEOUT });
    await page.waitForFunction(() => typeof META !== "undefined" && META && map.getLayer && map.isStyleLoaded(), null, { timeout: TIMEOUT });
    await idle(page);
    const meta = await page.evaluate(() => ({ updated: META.updated, count: META.count, regions: META.regions.map((r) => r.name) }));
    ok("meta.json latautui", meta.count > 0, `${meta.count} metsätilaa, ${meta.regions.join(", ")}, päivitetty ${meta.updated}`);
    if (EXPECT_UPDATED) ok("julkaistu versio näkyy sivulla", meta.updated === EXPECT_UPDATED, `odotettu ${EXPECT_UPDATED}`);
    ok("kaukaa (zoom 9) ei näy tiloja", (await visible(page)) === 0);

    await page.evaluate(() => map.jumpTo({ center: [23.85, 60.75], zoom: 12 }));
    await idle(page);
    const n0 = await visible(page);
    ok("Tammelassa näkyy metsätiloja (zoom 12)", n0 > 20, `${n0} tilaa`);
    const countText = await page.textContent("#count");
    ok("näkyvien määrä paneelissa", /näkyvissä/.test(countText), countText.trim());

    await page.fill("#kaMin", "50");
    await page.dispatchEvent("#kaMin", "input");
    await idle(page);
    const n1 = await visible(page);
    ok("suodatin (kokonaisala ≥ 50 ha) vähentää tiloja", n1 < n0 && n1 > 0, `${n0} → ${n1}`);
    await page.$eval("#age-u", (el) => { el.value = "50"; el.dispatchEvent(new Event("input", { bubbles: true })); });
    await idle(page);
    const n2 = await visible(page);
    ok("ikäjakauma-suodatin (uudistuskypsää ≥ 50 %) vähentää lisää", n2 <= n1, `${n1} → ${n2}`);
    await page.click("#reset");
    await idle(page);
    const n3 = await visible(page);
    ok("tyhjennys palauttaa tilat", n3 === n0, `${n3}`);

    const pt = await page.evaluate(() => {
      const f = map.queryRenderedFeatures({ layers: META.regions.map((r) => r.file.replace(/\.pmtiles$/, "") + "-fill") })[0];
      const c = f.geometry.type === "MultiPolygon" ? f.geometry.coordinates[0][0][0] : f.geometry.coordinates[0][0];
      return map.project(c);
    });
    // klikataan hieman polygonin sisäpuolelle reunapisteestä: etsitään piste, jossa on tila
    const hit = await page.evaluate(({ x, y }) => {
      for (let d = 2; d < 40; d += 2) for (const [dx, dy] of [[d, 0], [0, d], [-d, 0], [0, -d], [d, d], [-d, -d], [d, -d], [-d, d]]) {
        const q = map.queryRenderedFeatures([x + dx, y + dy], { layers: META.regions.map((r) => r.file.replace(/\.pmtiles$/, "") + "-fill") });
        if (q.length) return { x: x + dx, y: y + dy };
      }
      return null;
    }, pt);
    if (hit) {
      await page.mouse.click(hit.x, hit.y);
      await page.waitForSelector("#card", { state: "visible", timeout: 10_000 }).catch(() => {});
      const card = (await page.textContent("#card")) || "";
      ok("tietokortti aukeaa", /Puuston arvo/.test(card) && /Hakkuurajoitus/.test(card) && /hakkuutavan hinnoin/.test(card),
        card.replace(/\s+/g, " ").slice(0, 120));
    } else ok("tietokortti aukeaa", false, "klikattavaa tilaa ei löytynyt");
  } catch (e) {
    ok("sivu toimii", false, String(e.message || e).slice(0, 200));
  }
  ok("ei JavaScript-virheitä", errors.length === 0, errors.slice(0, 3).join(" | "));
  await browser.close();
  return results;
}

await waitForVersion();
let results = [];
for (let i = 1; i <= ATTEMPTS; i++) {
  console.log(`Yritys ${i}/${ATTEMPTS}: ${SITE}`);
  results = await run();
  if (results.every((r) => r.pass)) break;
  if (i < ATTEMPTS) await sleep(60_000);
}
const bad = results.filter((r) => !r.pass);
if (bad.length) {
  for (const r of bad) if (GH) console.log(`::error::Metsakartan tarkistus: ${r.name}${r.info ? " – " + r.info : ""}`.replace(/\n/g, " "));
  process.exit(1);
}
console.log("Kaikki tarkistukset kunnossa.");
