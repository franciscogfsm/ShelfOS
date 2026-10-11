// Captures every real ShelfOS state used by the film, plus the on-screen position of each control.
import puppeteer from 'puppeteer-core';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
const BASE = process.env.SHELFOS_URL ?? 'http://localhost:3210';
const OUT = fileURLToPath(new URL(`./${process.env.SHOTS ?? 'shots'}/`, import.meta.url));
mkdirSync(OUT, { recursive: true });
const only = process.argv[2];
const chrome = process.env.CHROME ?? 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const browser = await puppeteer.launch({ executablePath: chrome, headless: 'new', args: ['--hide-scrollbars', '--force-color-profile=srgb'] });
const page = await browser.newPage();
const HIDE = 'nextjs-portal,[data-nextjs-toast]{display:none!important} *{caret-color:transparent!important}';
const sleep = (ms) => new Promise(r => setTimeout(r, ms));
const meta = {};
async function go(path, w = 1600, h = 900, dsf = 2.4) {
  await page.setViewport({ width: w, height: h, deviceScaleFactor: dsf });
  await page.goto(BASE + path, { waitUntil: 'networkidle2', timeout: 120000 });
  await page.addStyleTag({ content: HIDE });
  await sleep(3000);
}
async function shot(name) {
  await page.screenshot({ path: OUT + name + '.jpg', type: 'jpeg', quality: 93 });
  meta[name] = await page.evaluate(() => {
    const out = [];
    const seen = new Set();
    for (const e of document.querySelectorAll('button,a,section,nav,h1,h2,[class*=card],[class*=tile],[class*=row],[class*=chip],[class*=panel],[class*=popover],[class*=detail],[class*=palette],[class*=widget],[role=dialog],svg polygon,svg circle')) {
      if (seen.has(e)) continue; seen.add(e);
      const r = e.getBoundingClientRect();
      if (r.width < 6 || r.height < 6 || r.bottom < 0 || r.top > innerHeight || getComputedStyle(e).visibility === 'hidden' || getComputedStyle(e).opacity === '0') continue;
      out.push({ t: e.tagName.toLowerCase(), c: (e.className?.baseVal ?? e.className ?? '').toString().slice(0, 60), s: (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim().slice(0, 44), r: [r.x, r.y, r.width, r.height].map(v => Math.round(v * 10) / 10) });
    }
    return out;
  });
  console.log('shot', name);
}
const clickText = async (sel, text, nth = 0) => {
  const ok = await page.evaluate((sel, text, nth) => {
    const els = [...document.querySelectorAll(sel)].filter(e => (e.innerText || e.getAttribute('aria-label') || '').replace(/\s+/g, ' ').includes(text) && e.getBoundingClientRect().width > 0);
    if (!els[nth]) return false; els[nth].click(); return true;
  }, sel, text, nth);
  if (!ok) console.log('  !! not found', sel, text);
  return ok;
};
const want = (g) => !only || only === g;

if (want('wall')) {
  await go('/?view=wall'); await shot('wall');
  await page.addStyleTag({ content: '.metric-card,.camera-card{visibility:hidden!important}' });
  await sleep(200); await shot('wall_bare');
}
if (want('lapse')) {
  await go('/?view=wall');
  for (let i = 0; i < 16; i++) { await page.keyboard.press('ArrowLeft'); await sleep(120); }
  await sleep(1500);
  for (let i = 0; i <= 16; i++) { await sleep(1300); await shot('lapse' + String(i).padStart(2, '0')); await page.keyboard.press('ArrowRight'); }
}
if (want('camera')) {
  await go('/?view=camera&cam=6215'); await shot('camera');
  await clickText('.plan-row', 'slot 2'); await sleep(2500); await shot('area');
  if (await clickText('button', 'Show what ShelfOS sees')) { await sleep(2500); await shot('area_mask'); }
}
if (want('tasks')) {
  await go('/?view=tasks'); await shot('tasks');
  for (let i = 1; i <= 3; i++) {
    await page.evaluate(() => document.querySelector('.task-done:not([aria-pressed=true])')?.click());
    await sleep(1600); await shot('tasks_done' + i);
  }
}
if (want('analytics')) {
  await go('/?view=analytics'); await shot('analytics');
  for (const tab of ['Stock', 'Compliant', 'Covered']) { await clickText('.an-card button', tab); await sleep(1500); await shot('analytics_' + tab.toLowerCase()); }
}
if (want('run')) { await go('/?view=run'); await shot('run'); }
if (want('search')) {
  await go('/?view=wall');
  await clickText('button.search-trigger', 'Search'); await sleep(1200); await shot('search');
  await page.keyboard.type('banana', { delay: 60 }); await sleep(1500); await shot('search_typed');
}
if (want('ai')) {
  await go('/?view=wall');
  await clickText('button.ai-trigger', ''); await sleep(1800); await shot('ai');
}
if (want('light')) {
  await go('/?view=wall');
  await clickText('button.theme-switch', ''); await sleep(1800); await shot('wall_light');
}
if (want('staff')) {
  await go('/colaboradores', 430, 932, 3); await shot('m_route');
  await page.evaluate(() => window.scrollTo(0, 330)); await sleep(900); await shot('m_map');
  await page.evaluate(() => window.scrollTo(0, 0)); await sleep(500);
  await clickText('.staff-tabs button', 'Tarefas'); await sleep(1500); await shot('m_tasks');
  await clickText('.staff-tabs button', 'Percurso'); await sleep(1200);
  await clickText('.staff-bottom button', 'estou aqui'); await sleep(900); await shot('m_watch');
  await sleep(1700); await shot('m_analyze');
  await sleep(1800); await shot('m_confirmed');
  await sleep(2600); await shot('m_next');
}
if (want('type')) {
  await go('/?view=wall');
  await clickText('button.search-trigger', 'Search'); await sleep(1200);
  for (const [i, ch] of [...'banana'].entries()) { await page.keyboard.type(ch); await sleep(700); await shot('type' + (i + 1)); }
}
if (want('ai2')) {
  await go('/?view=wall');
  await clickText('button.ai-trigger', ''); await sleep(1800); await shot('ai_open');
  await clickText('.ai-widget button', 'What needs attention first'); 
  let last = '', still = 0;
  for (let i = 0; i < 120 && still < 5; i++) {
    await sleep(380); await shot('ai_' + String(i).padStart(2, '0'));
    const now = await page.evaluate(() => document.querySelector('.ai-widget')?.innerText ?? '');
    still = now === last && !now.includes('Thinking') ? still + 1 : 0; last = now;
  }
  await shot('ai_answer');
  if (await clickText('.ai-product-card', 'Banana')) { await sleep(2600); await shot('ai_jump'); }
  console.log('AI TEXT >>>', last.replace(/\n+/g, ' | ').slice(0, 2500));
}
if (want('stafflight')) {
  await go('/colaboradores', 430, 932, 3);
  await clickText('button.theme-switch', ''); await sleep(1500);
  await clickText('.staff-bottom button', 'estou aqui'); await sleep(7600); await shot('ml_next');
}
if (want('brand')) {
  const T = '*,*::before,*::after{background-color:transparent!important;background-image:none!important;backdrop-filter:none!important;box-shadow:none!important}';
  for (const theme of ['dark', 'light']) {
    await go('/?view=wall', 1600, 900, 8);
    if (theme === 'light') { await clickText('button.theme-switch', ''); await sleep(1500); }
    await page.addStyleTag({ content: T }); await sleep(400);
    for (const [name, sel] of [['wordmark', '.app-header .wordmark'], ['tagline', '.overview-heading h1']]) {
      const el = await page.$(sel);
      await el.screenshot({ path: OUT + `brand_${name}_${theme}.png`, omitBackground: true });
      console.log('brand', name, theme, JSON.stringify(await el.boundingBox()));
    }
  }
}
writeFileSync(OUT + (only ? `meta_${only}.json` : 'meta.json'), JSON.stringify(meta));
await browser.close();
