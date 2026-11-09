// Paikallinen sivupalvelin tarkistuksia varten: tarjoilee kansion (web/ tai valmis dist/) osoitteessa
// http://localhost:<portti>/ Range-pyyntöjä tukien (PMTiles tarvitsee). Jos tiedostoa ei ole ja on annettu
// varalähde, data/-pyynnöt haetaan julkaistulta sivulta (esim. web/-kansion testaus ilman omia karttatiedostoja).
// Käyttö: node check/paikallinen.mjs <kansio> [portti=8080] [varalähde, esim. https://vv-tec.github.io/Talokartta/]
import fs from "node:fs";
import http from "node:http";
import path from "node:path";

const ROOT = path.resolve(process.argv[2] || "dist");
const PORT = Number(process.argv[3] || 8080);
const UPSTREAM = process.argv[4] ? process.argv[4].replace(/\/?$/, "/") : "";
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css",
  ".json": "application/json", ".webmanifest": "application/manifest+json", ".png": "image/png", ".svg": "image/svg+xml",
  ".pmtiles": "application/octet-stream" };

async function proxy(req, res, rel) {
  const headers = req.headers.range ? { range: req.headers.range } : {};
  const r = await fetch(UPSTREAM + rel, { headers });
  // fetch purkaa pakkauksen (gzip) → pituus lasketaan puretusta sisällöstä, ei välitetä alkuperäistä
  const body = Buffer.from(await r.arrayBuffer());
  const out = { "content-length": body.length };
  for (const h of ["content-type", "content-range", "accept-ranges"]) if (r.headers.get(h)) out[h] = r.headers.get(h);
  res.writeHead(r.status, out);
  res.end(body);
}

http.createServer(async (req, res) => {
  try {
    const rel = decodeURIComponent(new URL(req.url, "http://x").pathname).replace(/^\/+/, "");
    let file = path.join(ROOT, rel);
    if (!file.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) {
      if (UPSTREAM && rel.startsWith("data/")) return await proxy(req, res, rel);
      res.writeHead(404); return res.end("ei löydy");
    }
    const size = fs.statSync(file).size;
    const type = TYPES[path.extname(file)] || "application/octet-stream";
    const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
    if (m) {
      const start = m[1] === "" ? Math.max(0, size - Number(m[2])) : Number(m[1]);
      const end = m[1] !== "" && m[2] !== "" ? Math.min(Number(m[2]), size - 1) : size - 1;
      res.writeHead(206, { "content-type": type, "content-length": end - start + 1, "accept-ranges": "bytes",
        "content-range": `bytes ${start}-${end}/${size}` });
      return fs.createReadStream(file, { start, end }).pipe(res);
    }
    res.writeHead(200, { "content-type": type, "content-length": size, "accept-ranges": "bytes" });
    fs.createReadStream(file).pipe(res);
  } catch (e) {
    res.writeHead(502); res.end(String(e.message || e));
  }
}).listen(PORT, () => console.log(`Paikallinen sivu: http://localhost:${PORT}/ (${ROOT}${UPSTREAM ? ", data varalla " + UPSTREAM : ""})`));
