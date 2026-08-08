const { chromium } = require('playwright');
const BASE = process.env.BASE || 'http://localhost:8011/';
(async () => {
  const browser = await chromium.launch();
  const errors = [];
  const page = await browser.newPage({ viewport: { width: 1180, height: 1050 }, deviceScaleFactor: 2 });
  page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('pageerror', e => errors.push('PAGEERROR ' + e.message));

  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForSelector('.tilemap', { timeout: 8000 });
  await page.screenshot({ path: 'tools/shot-gov.png' });

  await page.evaluate(() => document.getElementById('state-SP')?.scrollIntoView());
  await page.waitForTimeout(300);
  await page.screenshot({ path: 'tools/shot-card.png' });

  await page.click('button[data-tab="sen"]');
  await page.waitForSelector('.natrow', { timeout: 8000 });
  await page.screenshot({ path: 'tools/shot-sen.png' });

  await page.click('button[data-tab="pres"]');
  await page.waitForSelector('.pres-lean', { timeout: 8000 });
  await page.screenshot({ path: 'tools/shot-pres.png' });

  const m = await browser.newPage({ viewport: { width: 390, height: 844 }, deviceScaleFactor: 2 });
  await m.goto(BASE, { waitUntil: 'networkidle' });
  await m.waitForSelector('.tilemap', { timeout: 8000 });
  await m.screenshot({ path: 'tools/shot-mobile.png' });

  console.log('CONSOLE ERRORS:', errors.length ? '\n' + errors.join('\n') : 'none');
  await browser.close();
})().catch(e => { console.error(e); process.exit(1); });
