import pw from '/home/djs/node_modules/playwright/index.js';

const {chromium} = pw;
const base = process.env.INDEX_URL || 'http://127.0.0.1:8199/index.html';
const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({viewport: {width: 1280, height: 720}});
const errors = [], workers = [];
page.on('console', message => {
  if (message.type() === 'error') errors.push(message.text());
});
page.on('pageerror', error => errors.push(`PAGEERROR ${error.message}`));
page.on('worker', worker => workers.push(worker.url()));
await page.addInitScript(() => {
  addEventListener('DOMContentLoaded', () => {
    window.__frameGaps = [];
    let previous = performance.now();
    const frame = now => {
      window.__frameGaps.push(now - previous);
      previous = now;
      requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
});

// The efuse library contains the largest prism payloads. Card workers should
// omit via geometry, cancel offscreen work, and reuse the prepared mesh on return.
const firstStarted = Date.now();
await page.goto(`${base}?lib=gf180mcu_re_efuse`, {waitUntil: 'domcontentloaded'});
await page.waitForFunction(() => ACTIVE.size > 0, null, {timeout: 30000});
const firstLoad = Date.now() - firstStarted;
const firstState = await page.evaluate(() => {
  const canvas = [...document.querySelectorAll('canvas[data-p]')].find(item => item._pv);
  return {
    name: canvas.dataset.p,
    badge: document.getElementById('rbadge').textContent,
    prepared: !!(canvas._pv.d.stats && canvas._pv.d.present && !canvas._pv.d.prisms),
    hasVia: canvas._pv.d.present.some(layer => /^Via|^Contact/.test(layer)),
    canvas: [canvas.width, canvas.height],
  };
});
const firstCard = firstState.name;

await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
await page.waitForFunction(name => {
  const canvas = [...document.querySelectorAll('canvas[data-p]')].find(item => item.dataset.p === name);
  return canvas && !canvas._pv && !canvas._loading;
}, firstCard, {timeout: 10000});
const reloadStarted = Date.now();
await page.evaluate(() => scrollTo(0, 0));
await page.waitForFunction(name => {
  const canvas = [...document.querySelectorAll('canvas[data-p]')].find(item => item.dataset.p === name);
  return !!(canvas && canvas._pv);
}, firstCard, {timeout: 10000});
const cachedReload = Date.now() - reloadStarted;

const scrollTiming = await page.evaluate(() => {
  const gaps = (window.__frameGaps || []).sort((a, b) => a - b);
  return {
    max: Math.max(0, ...gaps),
    p95: gaps[Math.floor(gaps.length * 0.95)] || 0,
  };
});

// Also cover the modal path with a representative standard cell.
await page.goto(`${base}?q=inv_1&lib=gf180mcu_fd_sc_mcu7t5v0`+
  '#c=gf180mcu_fd_sc_mcu7t5v0__inv_1&spin=0', {waitUntil: 'domcontentloaded'});
await page.waitForFunction(() => modalView && document.querySelector('.v3loading').style.display === 'none',
  null, {timeout: 15000});
const modal = await page.evaluate(() => ({
  canvas: [modalView.cv.width, modalView.cv.height],
  hasBuffers: !!(modalView.vboT && modalView.vboL),
  workerPrepared: !!(modalView.d.stats && modalView.d.present && !modalView.d.prisms),
}));

console.log('worker urls     :', workers);
console.log('renderer badge  :', firstState.badge);
console.log('largest cards   : first', `${firstLoad} ms`, '· cached return', `${cachedReload} ms`);
console.log('card mesh       :', firstState.canvas, firstState.prepared ? 'worker prepared' : 'NOT PREPARED',
  firstState.hasVia ? 'unexpected vias' : 'vias omitted');
console.log('frame gaps      : max', scrollTiming.max.toFixed(1), 'ms · p95',
  scrollTiming.p95.toFixed(1), 'ms');
console.log('modal mesh      :', modal.canvas, modal.workerPrepared && modal.hasBuffers ? 'PASS' : 'FAIL');
console.log('console errors  :', errors.length ? errors : 'none');

const failures = [];
if (!workers.some(worker => worker.endsWith('/prism-worker.js'))) failures.push('worker did not start');
if (!firstState.badge.includes('workers')) failures.push('worker renderer badge missing');
if (!firstState.prepared || firstState.hasVia) failures.push('card mesh was not worker-optimized');
if (!firstState.canvas[0] || !firstState.canvas[1]) failures.push('card canvas is empty');
if (cachedReload > 1000) failures.push(`cached reload took ${cachedReload} ms`);
if (!modal.workerPrepared || !modal.hasBuffers) failures.push('modal did not use transferred mesh buffers');
if (errors.length) failures.push('browser console errors');
await browser.close();
if (failures.length) {
  console.error('FAIL:', failures.join('; '));
  process.exit(1);
}
