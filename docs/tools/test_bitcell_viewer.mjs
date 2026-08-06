import pw from '/home/djs/node_modules/playwright/index.js';
const { chromium } = pw;

const OUT = '/tmp/claude-1000/-home-djs-chdl-ext-gf180mcu-project-template/de2bb2a9-8840-4967-8cee-4040a78e7793/scratchpad/shots';
const URL = 'file:///home/djs/chdl/ext/GDS3D/docs/bitcell_compare.html';

const browser = await chromium.launch({
  args: ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
});
const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
const errs = [];
page.on('console', m => { if (m.type() === 'error') errs.push(m.text()); });
page.on('pageerror', e => errs.push('PAGEERROR ' + e.message));
await page.goto(URL, { waitUntil: 'load' });
await page.waitForTimeout(500);

// does WebGL2 actually exist, and did every view get a context?
const ctx = await page.evaluate(() => ({
  gl: views.map(v => !!v.gl),
  ver: views[0].gl ? views[0].gl.getParameter(views[0].gl.VERSION) : null,
  renderer: views[0].gl ? views[0].gl.getParameter(views[0].gl.RENDERER) : null,
  scale: SCALE,
}));
console.log('WebGL2 per view :', ctx.gl, '\nversion         :', ctx.ver,
            '\nrenderer        :', ctx.renderer, '\nSCALE           :', ctx.scale.toFixed(2));

// read the real framebuffer: coverage bbox + which colour is topmost
const probe = await page.evaluate(() => {
  const out = [];
  for (const v of views) {
    v.draw();
    const gl = v.gl, w = v.cv.width, h = v.cv.height;
    const px = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    let x0 = 1e9, x1 = -1e9, y0 = 1e9, y1 = -1e9, n = 0, top = null;
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4;
      if (px[i + 3] < 8) continue;
      n++;
      if (x < x0) x0 = x; if (x > x1) x1 = x;
      if (y < y0) y0 = y; if (y > y1) y1 = y;
      // readPixels is bottom-up, so the largest y is the TOP of the image.
      // Skip the dark outline pixels -- we want the topmost FACE.
      const dark = px[i] < 110 && px[i + 1] < 115 && px[i + 2] < 120;
      if (!dark && (!top || y > top.y)) top = { y, r: px[i], g: px[i + 1], b: px[i + 2] };
    }
    out.push({ label: v.cell.label, w, h, n,
               cx: (x0 + x1) / 2 - w / 2, cy: (y0 + y1) / 2 - h / 2,
               fill: [(x1 - x0) / w, (y1 - y0) / h], top });
  }
  return out;
});
console.log('\ncanvas readback (0,0 offset = perfectly centred):');
for (const p of probe)
  console.log('  ', p.label.padEnd(21), p.w + 'x' + p.h,
    'painted', String(p.n).padStart(7),
    ' offset', p.cx.toFixed(1).padStart(6), p.cy.toFixed(1).padStart(6),
    ' fill', (p.fill[0] * 100).toFixed(0) + '% x ' + (p.fill[1] * 100).toFixed(0) + '%',
    ' topmost rgb(' + p.top.r + ',' + p.top.g + ',' + p.top.b + ')');

// Metal3 is #e08030 -> the highest layer, so it must own the topmost pixel of
// the fd cell at the default view. Metal2 (#9b59b6) sits below it.
const m3 = [224, 128, 48], t = probe[0].top;
const near = (a, b) => Math.abs(a.r - b[0]) < 60 && Math.abs(a.g - b[1]) < 60 && Math.abs(a.b - b[2]) < 60;
console.log('\nstack orientation:', near(t, m3)
  ? 'PASS - Metal3 (orange) is topmost on the fd cell'
  : 'CHECK - topmost is not Metal3-ish');

// zoom must survive layer toggles
const zoom = await page.evaluate(() => {
  const before = SCALE;
  document.querySelectorAll('.chip').forEach(c => { if (c.textContent.includes('Metal2')) c.click(); });
  const after = SCALE;
  document.querySelectorAll('.chip').forEach(c => { if (c.textContent.includes('Metal2')) c.click(); });
  return { before, after, restored: SCALE };
});
console.log('layer toggle    :', zoom.before.toFixed(3), '->', zoom.after.toFixed(3),
            zoom.before === zoom.after ? 'PASS (zoom held)' : 'FAIL (rescaled)');

const cvs = await page.$$('canvas');
for (let i = 0; i < cvs.length; i++) await cvs[i].screenshot({ path: `${OUT}/cell${i}.png` });
await page.screenshot({ path: `${OUT}/page.png`, fullPage: false });
await page.evaluate(() => { document.getElementById('ex').value = 18;
  document.getElementById('ex').oninput({ target: { value: 18 } }); });
await page.waitForTimeout(150);
await page.screenshot({ path: `${OUT}/exploded.png` });
console.log('\nconsole errors  :', errs.length ? errs : 'none');
await browser.close();
