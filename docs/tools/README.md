# Interactive 3D cell reference — prism pipeline

Sibling of the EGL spin-video pipeline. Instead of rasterizing each cell to an
MP4, it exports *geometry*: per-layer merged polygons extruded with the lyd25
z-stack, rendered client-side by a dependency-free canvas painter's-algorithm
viewer. ~100× smaller per cell than video, and interactive (orbit, zoom,
layer toggles, explode).

## Files

- `extract_prisms.py` — reads `docs/cells.json`, finds every cell in the
  gf180mcuD PDK GDS, writes `docs/prisms/<cell>.json` + `prisms/index.json`.
  Needs gdstk. Cells over 20000 merged prisms are LOD-capped (largest shapes kept;
  the viewer displays "LOD: N of M shapes"). All vias render as hexagon
  extrusions; every via is kept up to 1000 per layer, then 1:10, beyond which the
  memory-macro monsters stride down (viewer shows "vias sampled 1:N").
- `make_index3d.py` — regenerates `docs/index3d.html` from `docs/index.html`
  (reuses its design system, CELLS blob, filters, and modal info panel;
  swaps the video machinery for lazy prism viewers). Re-run after
  `index.html` changes.

## Behavior

Cards load geometry via IntersectionObserver only while near the viewport and
dispose it on scroll-out — same memory strategy as the video edition. Spin
respects `prefers-reduced-motion`. Prisms are served straight from Pages
(`docs/prisms/`, no CDN needed — they're small enough for the deploy limit
that forced videos onto jsDelivr).

## Publishing

Commit `docs/prisms/` + `docs/index3d.html` and push: GitHub Pages serves it.
To make 3D the default, swap the filenames (the video edition keeps working
from whichever name it holds).

## Regenerate everything

```bash
python3 docs/tools/extract_prisms.py
python3 docs/tools/make_index3d.py
```
