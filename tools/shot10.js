// Aba "Médias" (por disputa) + coluna Votos na aba Pesquisas — confere render e erros de JS.
const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8017/';
(async () => {
  const b = await chromium.launch();
  const errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1100 }, deviceScaleFactor: 2 });
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');

  // aba Médias: SP governador (default), depois SP Senado
  await p.click('button[data-tab="ma"]');
  await p.waitForSelector('#ma-uf');
  await p.screenshot({ path: 'tools/shot-medias-gov.png', fullPage: true });
  await p.selectOption('#ma-cargo', 'Senado');
  await p.waitForSelector('.matbl');
  await p.screenshot({ path: 'tools/shot-medias-sen.png', fullPage: true });
  const votosTags = await p.$$eval('.matbl .basetag.v2', xs => xs.length);
  const soma100 = await p.$$eval('.matbl .basetag.t', xs => xs.length);
  console.log('MEDIAS SP/Senado: tags "2 por pessoa":', votosTags, '| "soma 100%"/totais:', soma100);

  // aba Pesquisas: coluna Votos presente
  await p.click('button[data-tab="log"]');
  await p.waitForSelector('.logtbl');
  const hdr = await p.$$eval('.logtbl thead th', ths => ths.map(t => t.textContent));
  console.log('LOG cabeçalho:', hdr.join(' | '));
  await p.screenshot({ path: 'tools/shot-log-votos.png', clip: { x: 0, y: 0, width: 1180, height: 900 } });
  console.log('ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
