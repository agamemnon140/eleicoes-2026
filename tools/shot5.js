const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8017/';
(async () => {
  const b = await chromium.launch();
  const errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1150 }, deviceScaleFactor: 2 });
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');
  // aba presidente + abre a lista de pesquisas
  await p.click('button[data-tab="pres"]');
  await p.waitForSelector('.pres1t');
  await p.click('.usedd summary').catch(() => {});
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-pres2.png' });
  // detalhe de candidato com pesquisas na média
  await p.click('button[data-tab="sen"]');
  await p.waitForSelector('.tilemap');
  await p.click('.tile[data-uf="AC"]');
  await p.waitForTimeout(300);
  await p.click('.det-toggle');
  await p.waitForTimeout(300);
  await p.$eval('.cand.est .cand-detail', el => el.scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-detail3.png' });
  console.log('CONSOLE ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
