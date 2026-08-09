const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8017/';
(async () => {
  const b = await chromium.launch();
  const logs = [], errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 950 }, deviceScaleFactor: 2 });
  p.on('console', m => { const t = m.text(); if (m.type()==='error') errors.push(t); if (/self-check|mismatch/i.test(t)) logs.push(`[${m.type()}] ${t}`); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');
  await p.click('button[data-tab="sen"]');
  await p.waitForSelector('.compo');

  // atalho correlacionado pró-Bolsonaro +5
  await p.click('.chipbtn[data-preset="-5"]');
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-corr.png' });

  // ler valores dos 3 sliders + master
  const vals = await p.$$eval('#sim input[type=range]', els => els.map(e => ({id:e.id, v:e.value})));
  const master = await p.$eval('#v-all', el => el.textContent);
  console.log('SLIDERS:', JSON.stringify(vals), '| master:', master);
  console.log('SELF-CHECK/LOGS:', logs.length ? logs.join(' | ') : '(nenhum)');
  console.log('CONSOLE ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
