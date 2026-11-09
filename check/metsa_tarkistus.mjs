// Metsätilojen tarkistus: Metsakartan julkaisemat tiedostot ja Talokartan metsätilanäkymä (?moodi=metsa) oikeassa
// selaimessa (Chromium). Ajetaan Metsakartan työnkulussa julkaisun jälkeen ja Talokartan Testit-työnkulussa ennen
// julkaisua (TALO_URL = paikallinen sivu). Tarkistaa: meta.json, julkaistu versio, etusivun ohjaus, moodivalinta,
// tilat Tammelassa, suodattimet ja liukusäätimet, värin valinta, tietokortti, metsäkuva kaukaa, paluu taloihin.
// Ympäristömuuttujat: SITE_URL (Metsakartta, oletus https://vv-tec.github.io/Metsakartta/), TALO_URL (oletus
// julkaistu Talokartta), EXPECT_UPDATED, ATTEMPTS (oletus 2).
import { chromium } from "playwright";

const SITE = (process.env.SITE_URL || "https://vv-tec.github.io/Metsakartta/").replace(/\/?$/, "/");
// Talokartan piilotettu metsätilanäkymä (?moodi=metsa), joka lukee tiedot Metsakartasta. Tyhjä = ei tarkisteta.
const TALO = process.env.TALO_URL ?? "https://vv-tec.github.io/Talokartta/";
const EXPECT_UPDATED = process.env.EXPECT_UPDATED || "";
const ATTEMPTS = Number(process.env.ATTEMPTS || 2);
const GH = !!process.env.GITHUB_ACTIONS;
const TIMEOUT = 60_000;  // versio-odotus enintään 10 min + kaksi yritystä → jobin aikaraja 25 min
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function idle(page) {
  await page.evaluate((ms) => new Promise((res, rej) => {
    const t = setTimeout(() => rej(new Error("kartta ei valmistunut ajassa")), ms);
    map.once("idle", () => { clearTimeout(t); res(); });
    map.triggerRepaint();
  }), TIMEOUT);
}

// Pages-välimuisti: uusi versio voi näkyä vasta 5–15 min julkaisun jälkeen (6.11.2026 havaittu yli 13 min).
// Odotetaan enintään 10 min; jos vanha versio näkyy yhä, se on vain varoitus (sivu toimii, päivittyy pian).
async function waitForVersion() {
  if (!EXPECT_UPDATED) return true;
  for (let i = 1; i <= 21; i++) {
    const m = await fetch(`${SITE}data/meta.json?v=${Date.now()}`).then((r) => r.json()).catch(() => null);
    if (m?.updated === EXPECT_UPDATED) return true;
    console.log(`  meta.json: ${m ? "vielä versio " + m.updated : "ei saatu"}, odotetaan 30 s`);
    if (i < 21) await sleep(30_000);
  }
  return false;
}

async function run() {
  const results = [];
  const ok = (name, pass, info = "") => { results.push({ name, pass, info }); console.log(`${pass ? "✓" : "✗"} ${name}${info ? " – " + info : ""}`); };
  const browser = await chromium.launch();
  // Metsakartan julkaisemat tiedostot (Talokartan metsätilanäkymä lukee ne)
  try {
    const m = await fetch(`${SITE}data/meta.json?v=${Date.now()}`).then((r) => r.json());
    ok("meta.json latautui", m.count > 0, `${m.count} metsätilaa, ${m.regions.length} maakuntaa, muoto ${m.schema ?? 1}, päivitetty ${m.updated}`);
    if (EXPECT_UPDATED && m.updated !== EXPECT_UPDATED) {
      console.log(`! julkaistu versio ei vielä näy (sivulla ${m.updated}, odotettu ${EXPECT_UPDATED}) – GitHubin välimuisti, ei virhe`);
      if (GH) console.log(`::warning::Metsakartta: uusi versio ${EXPECT_UPDATED} ei vielä näkynyt 10 min kuluessa (GitHubin välimuisti)`);
    } else if (EXPECT_UPDATED) {
      ok("julkaistu versio näkyy", true, EXPECT_UPDATED);
      const idx = await fetch(`${SITE}?v=${Date.now()}`).then((r) => r.text());
      ok("etusivu ohjaa Talokartan metsätilanäkymään", /moodi=metsa/.test(idx));
    }
  } catch (e) {
    ok("Metsakartan tiedostot saatavilla", false, String(e.message || e).slice(0, 200));
  }
  if (TALO) await runTalo(browser, ok);
  await browser.close();
  return results;
}

await waitForVersion();
// Talokartta ?moodi=metsa: moodivalinta näkyy, talot piilossa, metsätilat näkyvät, suodatin toimii, kortti aukeaa.
async function runTalo(browser, ok) {
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e.message || e).slice(0, 300)));
  const fills = () => page.evaluate(() => (map.getStyle()?.layers || []).filter((l) => /^metsa-.*-fill$/.test(l.id)).map((l) => l.id));
  const vis = () => page.evaluate(() => {
    const layers = (map.getStyle()?.layers || []).filter((l) => /^metsa-.*-fill$/.test(l.id)).map((l) => l.id);
    return new Set(map.queryRenderedFeatures({ layers }).map((f) => f.properties.k)).size;
  });
  try {
    await page.goto(TALO + "?moodi=metsa&t=" + Date.now() + "#kartta=12/60.75/23.85", { waitUntil: "load", timeout: TIMEOUT });
    await page.waitForFunction(() => window.Metsa?.meta && (map.getStyle()?.layers || []).some((l) => /^metsa-.*-fill$/.test(l.id)), null, { timeout: TIMEOUT });
    await idle(page);
    ok("Talokartta: moodivalinta näkyy", await page.isVisible("#modeSwitch"));
    ok("Talokartta: metsätilatasot ladattu", (await fills()).length > 0);
    const n0 = await vis();
    ok("Talokartta: Tammelassa näkyy metsätiloja", n0 > 20, `${n0} tilaa`);
    const houses = await page.evaluate(() => B_LAYERS.filter((l) => map.getLayoutProperty(l, "visibility") !== "none").length);
    ok("Talokartta: talot piilossa metsätilanäkymässä", houses === 0);
    await page.fill("#fKaMin", "50");
    await idle(page);
    const n1 = await vis();
    ok("Talokartta: suodatin vähentää metsätiloja", n1 < n0 && n1 > 0, `${n0} → ${n1}`);
    await page.click("#fReset");
    // Liukusäätimet €/ha ja m³/ha: alarajan nosto vähentää tiloja, tyhjennys palauttaa
    const slide = (sel, v) => page.evaluate(([s, val]) => {
      const i = document.querySelector(s + " input");
      i.value = val;
      i.dispatchEvent(new Event("input", { bubbles: true }));
    }, [sel, v]);
    for (const [sel, v, lab] of [["#fEhR", 10, "€/ha"], ["#fVhR", 8, "m³/ha"]]) {
      await idle(page);
      const a = await vis();
      await slide(sel, v);
      await idle(page);
      const b = await vis();
      ok(`Talokartta: liukusäädin ${lab} vähentää metsätiloja`, b < a && b > 0, `${a} → ${b}`);
      await page.click("#fReset");
    }
    // Tilojen värin valinta: € ↔ m³/ha vaihtaa täyttövärin lausekkeen
    {
      const colorKey = () => page.evaluate(() => {
        const l = (map.getStyle()?.layers || []).find((x) => /^metsa-.*-fill$/.test(x.id));
        return JSON.stringify(map.getPaintProperty(l.id, "fill-color")).includes('["get","e"]') ? "eur" : "m3";
      });
      await page.check('input[name=fColor][value=eur]');
      const k1 = await colorKey();
      await page.check('input[name=fColor][value=m3]');
      const k2 = await colorKey();
      ok("Talokartta: tilojen värin valinta (€ / m³/ha) toimii", k1 === "eur" && k2 === "m3", `${k1} → ${k2}`);
    }
    await idle(page);
    const pt = await page.evaluate(() => {
      const layers = (map.getStyle()?.layers || []).filter((l) => /^metsa-.*-fill$/.test(l.id)).map((l) => l.id);
      const { width, height } = map.getCanvas().getBoundingClientRect();
      for (let y = 40; y < height; y += 25) for (let x = 40; x < width; x += 25) {
        if (map.queryRenderedFeatures([x, y], { layers }).length) return { x, y };
      }
      return null;
    });
    if (pt) {
      const box = await page.locator("#map").boundingBox();
      await page.mouse.click(box.x + pt.x, box.y + pt.y);
      await page.waitForFunction(() => /Puuston arvo/.test(document.querySelector("#card")?.textContent || ""), null, { timeout: 15_000 }).catch(() => {});
      const card = (await page.textContent("#card")) || "";
      ok("Talokartta: metsätilan kortti aukeaa", /Puuston arvo/.test(card) && /Hakkuutavan hinnoin/.test(card), card.replace(/\s+/g, " ").slice(0, 100));
    } else ok("Talokartta: metsätilan kortti aukeaa", false, "klikattavaa tilaa ei löytynyt");
    // Kaukaa VMI-metsäkuva (rasteri)
    await page.evaluate(() => { closeCard(); map.jumpTo({ center: [23.85, 60.75], zoom: 8.5 }); });
    await idle(page);
    const tiles = await page.evaluate(() => {
      if (!map.getLayer("metsa-r")) return -1;
      const sc = map.style?.sourceCaches?.["metsa-r"];
      return sc ? Object.values(sc._tiles || {}).filter((t) => t.state === "loaded").length : 0;
    });
    ok("Talokartta: kaukaa näkyy metsäkuva", tiles > 0, tiles < 0 ? "metsäkuvataso puuttuu" : `${tiles} kuvatiiltä`);
    await page.click('#modeSwitch button[data-m="talot"]');
    await page.evaluate(() => map.jumpTo({ center: [23.763, 60.8095], zoom: 14 }));
    await idle(page);
    const back = await page.evaluate(() => new Set(map.queryRenderedFeatures({ layers: B_LAYERS }).map((f) => f.properties.id)).size);
    ok("Talokartta: takaisin taloihin – rakennukset näkyvät", back > 0, `${back} rakennusta`);
    const lines = await page.evaluate(() => (map.getStyle()?.layers || []).filter((l) => /^metsa-.*-line$/.test(l.id))
      .filter((l) => map.getLayoutProperty(l.id, "visibility") !== "none").length);
    ok("Talokartta: tilojen rajat näkyvät myös talonäkymässä", lines > 0, `${lines} rajatasoa`);
  } catch (e) {
    ok("Talokartta: metsätilanäkymä toimii", false, String(e.message || e).slice(0, 200));
  }
  ok("Talokartta: ei JavaScript-virheitä", errors.length === 0, errors.slice(0, 3).join(" | "));
  await page.close();
}

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
