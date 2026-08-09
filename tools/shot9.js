const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8017/';
(async () => {
  const b = await chromium.launch();
  const logs = [], errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1050 }, deviceScaleFactor: 2 });
  p.on('console', m => { const t=m.text(); if (m.type()==='error') errors.push(t); if (/self-check|mismatch/i.test(t)) logs.push(t); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');

  // banner no topo (aba Governadores)
  await p.waitForSelector('.upbanner');
  await p.screenshot({ path: 'tools/shot-banner.png', clip: { x:0, y:0, width:1180, height:340 } });

  // aba Pesquisas
  await p.click('button[data-tab="log"]');
  await p.waitForSelector('.logtbl');
  await p.screenshot({ path: 'tools/shot-log.png' });

  const nState = await p.$$eval('.logtbl tbody tr', rs => rs.length);
  const hasLinks = await p.$$eval('.logtbl a', as => as.length);
  console.log('LOG rows(1ª tabela+):', nState, '| links de fonte:', hasLinks);
  console.log('SELF-CHECK:', logs.join(' | ') || '(nenhum)');
  console.log('ERRORS:', errors.length ? '\n'+errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
