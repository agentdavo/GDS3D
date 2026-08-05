# docs — the published site

GitHub Pages serves this directory from `master`, at
<https://agentdavo.github.io/GDS3D/>.

```
docs/
  index.html          the gf180mcuD reference — all 692 cells
  cells.json          the same data, machine-readable
  videos/<lib>/*.mp4  702 spins, one per placeable cell
  .nojekyll           serve the tree literally, no Jekyll build
```

Nothing here is hand-edited. Both files are generated:

```
python3 tools/extract_cell_meta.py   # PDK  -> docs/cells.json
python3 tools/build_site.py          # + videos -> docs/index.html
```

## `cells.json`

692 records read straight out of the PDK — LEF for the footprint, placement
site and every pin's direction and use; Liberty (typical corner) for cell area
and the Boolean function of each output. Keyed by LEF macro name:

```json
"gf180mcu_ef_io__bi_t": {
  "lib": "gf180mcu_fd_io", "short": "bi_t",
  "size": [75.0, 350.0], "site": "GF_IO_Site", "area": null,
  "pins": [{"name": "A", "dir": "INPUT", "use": "SIGNAL"}, ...],
  "functions": {}
}
```

Note the key and `lib` can disagree: this library ships LEF whose macros are
named `gf180mcu_ef_io__*` while the directory is `gf180mcu_fd_io`. Do not filter
cells on the library prefix — `gf180mcu_re_efuse` names its macros with no
prefix at all, and filtering that way silently drops all seven of them.

It is published rather than kept private so the page's data can be used without
scraping the page.

The videos are **real files in this directory, not a symlink**. Pages publishes
the `docs/` tree as it stands and will not follow a link out of it, so the mp4s
have to live here. That is also why the render tool writes here directly.

## Why the videos look the way they do

Every cell is rendered with identical settings so that two cells can be compared
side by side:

    720 x 720, 2x supersampled, 180 frames (6 s @ 30 fps), full 360 deg spin
    h264 crf 26, preset veryslow
    LOD disabled — every layer drawn at every distance

Regenerate with `python3 tools/render_all_cells.py`. It is resumable: it skips
any cell whose video already exists, so deleting one file re-renders just that
cell. A full run is about six hours on llvmpipe.

Do not try to shrink these by transcoding. AV1 (libsvtav1) comes out **larger**
on this content — measured 105–183% of source — because the h264 is already at a
slow preset and hard-edged synthetic geometry gives AV1 nothing to recover.

## Weight

The tree is ~250 MB, inside the 1 GB Pages soft limit. The page loads no video
up front: an IntersectionObserver attaches a source only when a card scrolls
into view and pauses it when it leaves, so a visit costs a few megabytes rather
than the whole set.
