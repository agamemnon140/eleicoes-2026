const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8017/';
(async () => {
  const b = await chromium.launch();
  const logs = [], errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1000 }, deviceScaleFactor: 2 });
  p.on('console', m => { const t = m.text(); if (m.type()==='error') errors.push(t); if (/self-check|mismatch/i.test(t)) logs.push(t); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');

  // Senado: painel "Senadores eleitos por partido"
  await p.click('button[data-tab="sen"]');
  await p.waitForSelector('.compo');
  await p.$eval('.ppbar', el => el.scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(250);
  await p.screenshot({ path: 'tools/shot-senparty.png' });

  // detalhe de candidato com peso por recência
  await p.click('.tile[data-uf="AC"]');
  await p.waitForTimeout(250);
  await p.click('.det-toggle');
  await p.waitForTimeout(250);
  await p.$eval('.cand.est .usedpolls', el => el.scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(200);
  await p.screenshot({ path: 'tools/shot-peso-detail.png' });

  // Presidente: tabela do agregado com coluna Peso
  await p.click('button[data-tab="pres"]');
  await p.waitForSelector('.pres1t');
  await p.click('.usedd summary').catch(()=>{});
  await p.waitForTimeout(250);
  await p.$eval('.usedtbl', el => el.scrollIntoView({ block: 'center' }));
  await p.waitForTimeout(200);
  await p.screenshot({ path: 'tools/shot-pres-peso.png' });

  console.log('SELF-CHECK:', logs.join(' | ') || '(nenhum)');
  console.log('ERRORS:', errors.length ? '\n'+errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
