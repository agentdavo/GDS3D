import fs from 'node:fs';
import path from 'node:path';

const docs = path.resolve(import.meta.dirname, '..');
const cells = JSON.parse(fs.readFileSync(path.join(docs, 'cells.json')));
const supportedLayers = new Set([
  'Nwell', 'Pwell', 'COMP', 'Poly2', 'Metal1', 'Metal2', 'Metal3', 'Metal4', 'Metal5',
]);
const missing = [], unsupported = [];
let checked = 0;

for (const [cellName, metadata] of Object.entries(cells)) {
  const prismPath = path.join(docs, 'prisms', `${cellName}.json`);
  if (!fs.existsSync(prismPath)) continue;
  const geometry = JSON.parse(fs.readFileSync(prismPath));
  const pins = new Map((geometry.pins || []).map(pin => [pin.n, pin]));
  for (const pin of metadata.pins || []) {
    checked++;
    const geometryPin = pins.get(pin.name);
    if (!geometryPin || !geometryPin.s?.length) {
      missing.push(`${cellName}:${pin.name}`);
      continue;
    }
    for (const shape of geometryPin.s) {
      if (!supportedLayers.has(shape[0])) unsupported.push(`${cellName}:${pin.name}:${shape[0]}`);
    }
  }
}

console.log(`LEF pin geometry: ${checked - missing.length} of ${checked}`);
if (missing.length || unsupported.length) {
  if (missing.length) console.error('Missing:', missing.slice(0, 20));
  if (unsupported.length) console.error('Unsupported layers:', unsupported.slice(0, 20));
  process.exit(1);
}
