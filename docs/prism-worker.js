"use strict";

// CPU-side geometry preparation lives here so parsing multi-megabyte cells and
// triangulating their polygons never blocks scrolling or pointer input.
const controllers = new Map();

self.onmessage = async event => {
  const msg = event.data;
  if (msg.type === "cancel") {
    const controller = controllers.get(msg.id);
    if (controller) controller.abort();
    return;
  }
  if (msg.type !== "load") return;

  const controller = new AbortController();
  controllers.set(msg.id, controller);
  try {
    const response = await fetch(msg.url, {signal: controller.signal});
    if (!response.ok) throw new Error(`geometry request failed: ${response.status}`);
    const raw = await response.json();
    const data = expand(raw, msg.skipLayers || []);
    if (!data || !data.prisms) throw new Error("geometry payload is empty");
    const prepared = await prepare(data, raw.pins || [], msg.order, msg.colors,
      msg.includePrisms, msg.completeEdges, controller.signal);
    self.postMessage({type: "result", id: msg.id, prepared},
      [prepared.tris.buffer, prepared.lines.buffer]);
  } catch (error) {
    self.postMessage({
      type: "error",
      id: msg.id,
      aborted: error && error.name === "AbortError",
      message: error && error.message ? error.message : String(error),
    });
  } finally {
    controllers.delete(msg.id);
  }
};

const HEXPTS = Array.from({length: 6}, (_, i) => {
  const angle = Math.PI / 180 * (60 * i + 30);
  return [Math.cos(angle), Math.sin(angle)];
});

function expand(data, skipLayers) {
  const skipped = new Set(skipLayers);
  if (!data || !data.layers) {
    if (data && skipped.size) data = {...data, prisms: data.prisms.filter(prism => !skipped.has(prism.l))};
    return data; // legacy v1 geometry
  }
  const prisms = [];
  for (const layer of data.layers) {
    if (skipped.has(layer.l)) continue;
    if (layer.ps) for (const flat of layer.ps) {
      const points = [];
      for (let i = 0; i < flat.length; i += 2) points.push([flat[i], flat[i + 1]]);
      prisms.push({l: layer.l, p: points, z0: layer.z0, z1: layer.z1});
    }
    if (layer.hx) {
      const radius = layer.hr || 0.15;
      for (let i = 0; i < layer.hx.length; i += 2) {
        const cx = layer.hx[i], cy = layer.hx[i + 1];
        prisms.push({
          l: layer.l,
          p: HEXPTS.map(point => [cx + radius * point[0], cy + radius * point[1]]),
          z0: layer.z0,
          z1: layer.z1,
        });
      }
    }
  }
  return {w: data.w, h: data.h, zmax: data.zmax, lod: data.lod, prisms};
}

async function prepare(data, pins, order, colors, includePrisms, completeEdges, signal) {
  const stats = {}, grouped = new Map(order.map(layer => [layer, []]));
  for (const prism of data.prisms) {
    if (grouped.has(prism.l)) grouped.get(prism.l).push(prism);
    let bounds = stats[prism.l];
    if (!bounds) bounds = stats[prism.l] = {
      minx: Infinity, maxx: -Infinity, miny: Infinity, maxy: -Infinity,
      z0: Infinity, z1: -Infinity,
    };
    for (const point of prism.p) {
      if (point[0] < bounds.minx) bounds.minx = point[0];
      if (point[0] > bounds.maxx) bounds.maxx = point[0];
      if (point[1] < bounds.miny) bounds.miny = point[1];
      if (point[1] > bounds.maxy) bounds.maxy = point[1];
    }
    if (prism.z0 < bounds.z0) bounds.z0 = prism.z0;
    if (prism.z1 > bounds.z1) bounds.z1 = prism.z1;
  }

  const triangles = [], lines = [], triRange = {}, lineRange = {};
  let processed = 0;
  for (const layer of order) {
    const triStart = triangles.length / 9, lineStart = lines.length / 9;
    const color = hex2rgb(colors[layer] || "#888888");
    for (const prism of grouped.get(layer)) {
      if ((processed++ & 2047) === 0) {
        if (signal.aborted) throw new DOMException("geometry job cancelled", "AbortError");
        await new Promise(resolve => setTimeout(resolve, 0));
      }
      const n = prism.p.length;
      for (let i = 0; i < n; i++) {
        const a = prism.p[i], b = prism.p[(i + 1) % n];
        const ex = b[0] - a[0], ey = b[1] - a[1], length = Math.hypot(ex, ey) || 1;
        const nx = ey / length, ny = -ex / length;
        const side = [
          [a[0], a[1], prism.z0], [b[0], b[1], prism.z0], [b[0], b[1], prism.z1],
          [a[0], a[1], prism.z0], [b[0], b[1], prism.z1], [a[0], a[1], prism.z1],
        ];
        for (const vertex of side) triangles.push(
          vertex[0], vertex[1], vertex[2], nx, ny, 0, color[0], color[1], color[2]);
        const edgeColor = [0.16, 0.17, 0.19];
        const edge = (p, q) => lines.push(
          p[0], p[1], p[2], 0, 0, 1, edgeColor[0], edgeColor[1], edgeColor[2],
          q[0], q[1], q[2], 0, 0, 1, edgeColor[0], edgeColor[1], edgeColor[2]);
        edge([a[0], a[1], prism.z1], [b[0], b[1], prism.z1]);
        if (completeEdges) {
          edge([a[0], a[1], prism.z0], [b[0], b[1], prism.z0]);
          edge([a[0], a[1], prism.z0], [a[0], a[1], prism.z1]);
        }
      }
      for (const index of earcut(prism.p)) {
        const point = prism.p[index];
        triangles.push(point[0], point[1], prism.z1, 0, 0, 1,
          color[0], color[1], color[2]);
      }
    }
    triRange[layer] = [triStart, triangles.length / 9 - triStart];
    lineRange[layer] = [lineStart, lines.length / 9 - lineStart];
  }

  const result = {
    w: data.w,
    h: data.h,
    zmax: data.zmax,
    lod: data.lod,
    pins,
    stats,
    present: order.filter(layer => grouped.get(layer).length),
    triRange,
    lineRange,
    tris: new Float32Array(triangles),
    lines: new Float32Array(lines),
  };
  result.byteSize = result.tris.byteLength + result.lines.byteLength;
  if (includePrisms) result.prisms = data.prisms;
  return result;
}

function hex2rgb(hex) {
  const value = parseInt(hex.slice(1), 16);
  return [((value >> 16) & 255) / 255, ((value >> 8) & 255) / 255, (value & 255) / 255];
}

// Ear-clip triangulation for simple (possibly concave/keyholed) polygons.
function earcut(points) {
  const indices = [];
  if (points.length < 3) return indices;
  let ring = [];
  for (let i = 0; i < points.length; i++) {
    const point = points[i], next = points[(i + 1) % points.length];
    if (Math.abs(point[0] - next[0]) > 1e-9 || Math.abs(point[1] - next[1]) > 1e-9)
      ring.push(i);
  }
  let area = 0;
  for (let i = 0; i < ring.length; i++) {
    const point = points[ring[i]], next = points[ring[(i + 1) % ring.length]];
    area += point[0] * next[1] - next[0] * point[1];
  }
  if (area < 0) ring.reverse();
  let guard = ring.length * ring.length + 10;
  while (ring.length > 3 && guard-- > 0) {
    let clipped = false;
    for (let i = 0; i < ring.length; i++) {
      const ai = ring[(i + ring.length - 1) % ring.length], bi = ring[i],
            ci = ring[(i + 1) % ring.length];
      const a = points[ai], b = points[bi], c = points[ci];
      const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      if (cross <= 1e-12) continue;
      let clear = true;
      for (const pi of ring) {
        if (pi === ai || pi === bi || pi === ci) continue;
        const point = points[pi];
        const d1 = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0]);
        const d2 = (c[0] - b[0]) * (point[1] - b[1]) - (c[1] - b[1]) * (point[0] - b[0]);
        const d3 = (a[0] - c[0]) * (point[1] - c[1]) - (a[1] - c[1]) * (point[0] - c[0]);
        if (d1 >= -1e-12 && d2 >= -1e-12 && d3 >= -1e-12) {
          clear = false;
          break;
        }
      }
      if (clear) {
        indices.push(ai, bi, ci);
        ring.splice(i, 1);
        clipped = true;
        break;
      }
    }
    if (!clipped) break;
  }
  if (ring.length === 3) indices.push(ring[0], ring[1], ring[2]);
  else for (let i = 1; i < ring.length - 1; i++) indices.push(ring[0], ring[i], ring[i + 1]);
  return indices;
}
