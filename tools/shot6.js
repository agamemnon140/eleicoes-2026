const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8017/';
(async () => {
  const b = await chromium.launch();
  const logs = [], errors = [];
  const p = await b.newPage({ viewport: { width: 1180, height: 1200 }, deviceScaleFactor: 2 });
  p.on('console', m => { const t = m.text(); if (m.type()==='error') errors.push(t); if (/self-check|mismatch/.test(t)) logs.push(`[${m.type()}] ${t}`); });
  p.on('pageerror', e => errors.push('PAGEERROR ' + e.message));
  await p.goto(BASE, { waitUntil: 'networkidle' });
  await p.waitForSelector('.tilemap');

  // aba Senado, sim=0 → mostra composição + painel do simulador
  await p.click('button[data-tab="sen"]');
  await p.waitForSelector('.compo');
  await p.screenshot({ path: 'tools/shot-sen-sim0.png' });

  // choque pró-Bolsonaro: presidente −6, senado −4
  const setSlider = async (id, val) => {
    await p.$eval(`#sim-${id}`, (el, v) => {
      el.value = String(v);
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }, val);
    await p.waitForTimeout(120);
  };
  await setSlider('pres', -6);
  await setSlider('sen', -4);
  await p.waitForTimeout(300);
  await p.screenshot({ path: 'tools/shot-sen-shock.png' });

  // aba Presidente sob o mesmo choque
  await p.click('button[data-tab="pres"]');
  await p.waitForSelector('.pres1t');
  await p.waitForTimeout(200);
  await p.screenshot({ path: 'tools/shot-pres-shock.png' });

  console.log('SELF-CHECK/LOGS:', logs.length ? '\n' + logs.join('\n') : '(nenhum)');
  console.log('CONSOLE ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await b.close();
})().catch(e => { console.error(e); process.exit(1); });
