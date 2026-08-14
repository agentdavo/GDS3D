import pw from '/home/djs/node_modules/playwright/index.js';

const {chromium} = pw;
const base = process.env.INDEX_URL || 'http://127.0.0.1:8199/index.html';
const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({viewport: {width: 1100, height: 760}});
const errors = [];
page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
page.on('pageerror', error => errors.push(error.message));

await page.goto(`${base}?q=bi_t&lib=gf180mcu_fd_io`+
  '#c=gf180mcu_fd_io__bi_t&spin=0', {waitUntil: 'domcontentloaded'});
await page.waitForFunction(() => modalView && document.querySelector('.v3loading').style.display === 'none',
  null, {timeout: 30000});

const visibility = await page.evaluate(() => {
  const canvas = modalView.cv, context = canvas.getContext('2d');
  const pins = [...document.querySelectorAll('.pins code.haspin')];
  const invisible = [];
  for (const pin of pins) {
    modalView.clearFocus();
    modalView.draw();
    const before = context.getImageData(0, 0, canvas.width, canvas.height).data;
    pin.click();
    // Use the steady selected state so the assertion is independent of pulse phase.
    modalView.flashUntil = 0;
    modalView.focus = modalView._fb;
    modalView.draw();
    const after = context.getImageData(0, 0, canvas.width, canvas.height).data;
    let changedYellow = 0;
    for (let i = 0; i < after.length; i += 4) {
      const delta = Math.abs(after[i] - before[i]) + Math.abs(after[i + 1] - before[i + 1]) +
        Math.abs(after[i + 2] - before[i + 2]);
      if (delta > 60 && after[i] > 110 && after[i + 1] > 70 && after[i + 2] < 100)
        changedYellow++;
    }
    if (changedYellow < 4) invisible.push({pin: pin.dataset.pin, changedYellow});
  }
  modalView.clearFocus();
  return {total: pins.length, invisible};
});

console.log('IO pin visibility:', visibility.total, 'pins ·',
  visibility.invisible.length ? visibility.invisible : 'PASS');
console.log('console errors:', errors.length ? errors : 'none');
await browser.close();
if (!visibility.total || visibility.invisible.length || errors.length) process.exit(1);
