// Start: python -m http.server 8767 --directory docs
// Run: npm ci && node tools/check-research.cjs [site URL]
// CHROME_PATH can select a local Chrome; otherwise Playwright's Chromium is used.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const {existsSync} = require('node:fs');
const site = process.argv[2] || 'http://127.0.0.1:8767/';
const chrome = process.env.CHROME_PATH || ['C:/Program Files/Google/Chrome/Application/chrome.exe', '/usr/bin/google-chrome'].find(existsSync);

(async()=>{
  const browser = await chromium.launch({headless:true, ...(chrome?{executablePath:chrome}:{})});
  try{
    const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    page.on('console',m=>{if(m.type()==='error') errors.push(m.text());});
    await page.goto(site+'?aba=pres');
    await page.waitForSelector('.research-chart');
    for(const tab of ['gov','sen','pres','log','ma']){
      await page.evaluate(t=>selectTab(t),tab);
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=390),`${tab} exceeds mobile viewport`);
    }
    await page.goto(site+'?aba=gov&uf=SP&gov=3');
    await page.waitForSelector('.research-comparison');
    assert.equal(await page.evaluate(()=>filters.uf),'SP');
    assert.equal(await page.evaluate(()=>sim.gov),3);
    assert.equal(await page.locator('.state').count(),1);
    assert.match(await page.locator('.research-comparison').innerText(),/Cenário simulado/);
    await page.evaluate(()=>selectTab('log'));
    await page.selectOption('#research-status','excluded');
    assert.ok(await page.locator('.research-poll').count()>0);
    await page.reload();
    await page.waitForSelector('#research-status');
    assert.equal(await page.evaluate(()=>researchFilters.status),'excluded');
    await page.selectOption('#research-turn','2º turno');
    await page.reload();
    await page.waitForSelector('#research-turn');
    assert.equal(await page.locator('#research-turn').inputValue(),'2º turno');
    await page.goto(site+'?aba=ma&media_uf=AL&media_cargo=Senado');
    await page.waitForSelector('#ma-uf');
    assert.equal(await page.locator('#ma-uf').inputValue(),'AL');
    assert.equal(await page.locator('#ma-cargo').inputValue(),'Senado');
    await page.setViewportSize({width:1440,height:1000});
    await page.evaluate(()=>selectTab('pres'));
    const point=page.locator('.research-chart circle').first();
    await point.dispatchEvent('click');
    assert.notEqual(await page.locator('.chart-reading').innerText(),'Selecione um ponto para consultar a pesquisa.');
    assert.ok(await page.locator('.research-chart polygon').count()>0,'uncertainty bands missing');
    assert.deepEqual(errors,[]);
    console.log('PASS: five mobile tabs, charts/bands, poll details, exclusions, shared filters and simulated scenario; no JS errors.');
  }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
