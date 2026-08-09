const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8013/';
(async () => {
  const b = await chromium.launch();
  const p = await b.newPage({ viewport: { width: 1180, height: 820 }, deviceScaleFactor: 2 });
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');
  await p.click('.tile[data-uf="SP"]');
  await p.waitForTimeout(300);
  await p.click('.det-toggle');            // expande o 1º candidato (Tarcísio)
  await p.waitForTimeout(300);
  await p.$eval('.cand.est .cand-detail', el => el.scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-detail2.png' });
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
