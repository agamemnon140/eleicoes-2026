const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8016/';
(async () => {
  const b = await chromium.launch();
  const errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1150 }, deviceScaleFactor: 2 });
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');
  await p.click('button[data-tab="sen"]');
  await p.waitForTimeout(200);
  await p.click('#colorToggle button[data-m="partido"]');
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-sen-party.png' });
  // drill-down: clica no PL na legenda
  await p.click('.legend [data-party="PL"]');
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-focus.png' });
  console.log('CONSOLE ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
