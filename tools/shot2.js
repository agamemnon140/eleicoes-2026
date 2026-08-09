const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8013/';
(async () => {
  const b = await chromium.launch();
  const errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1250 }, deviceScaleFactor: 2 });
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));

  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');

  // 1) clicar SP -> filtra só SP; expandir "como foi calculado"
  await p.click('.tile[data-uf="SP"]');
  await p.waitForTimeout(300);
  await p.click('.det-toggle');
  await p.waitForTimeout(250);
  await p.screenshot({ path: 'tools/shot-detail.png' });

  // 2) modo por partido (recarrega p/ ver o mapa cheio)
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');
  await p.click('#colorToggle button[data-m="partido"]');
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-party.png' });

  // 3) hover mostra percentuais
  await p.hover('.tile[data-uf="RS"]');
  await p.waitForTimeout(250);
  await p.screenshot({ path: 'tools/shot-hover.png' });

  console.log('CONSOLE ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
