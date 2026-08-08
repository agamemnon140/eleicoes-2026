// Rasteriza assets/icon.svg em PNGs para PWA/iOS usando o Chromium do Playwright.
const { chromium } = require('playwright');
const fs = require('fs');
const svg = fs.readFileSync('assets/icon.svg', 'utf8');
const sizes = { 'icon-192.png': 192, 'icon-512.png': 512, 'icon-512-maskable.png': 512, 'apple-touch-icon.png': 180 };
(async () => {
  fs.mkdirSync('web/icons', { recursive: true });
  const b = await chromium.launch();
  for (const [name, size] of Object.entries(sizes)) {
    const p = await b.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
    await p.setContent(`<style>html,body{margin:0}svg{width:${size}px;height:${size}px;display:block}</style>${svg}`,
      { waitUntil: 'networkidle' });
    await p.screenshot({ path: 'web/icons/' + name });
    await p.close();
  }
  fs.copyFileSync('assets/icon.svg', 'web/icons/icon.svg');
  await b.close();
  console.log('icons gerados em web/icons/:', Object.keys(sizes).join(', '), '+ icon.svg');
})().catch(e => { console.error(e); process.exit(1); });
