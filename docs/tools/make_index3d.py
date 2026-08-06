#!/usr/bin/env python3
"""Generate docs/index3d.html: the interactive-3D sibling of index.html.

Reuses index.html's design system, CELLS data blob, filters, and modal info
panel verbatim; swaps the video pipeline for lazy-loaded prism viewers.
"""
import json, re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[1]
src = (DOCS / "index.html").read_text()

# ---- split: everything up to <script>, then the CELLS line ----
head, script = src.split("<script>", 1)
cells_line = next(l for l in script.splitlines() if l.startswith("const CELLS"))

# ---- HTML/CSS adjustments ----
head = head.replace(
    "<title>gf180mcuD — cell reference</title>",
    "<title>gf180mcuD — cell reference · interactive 3D</title>")
head = re.sub(r"<header>.*?</header>\s*", "", head, flags=re.S)
head = re.sub(r'<p class="stack-lede">.*?</p>\s*', "", head, flags=re.S)
head = head.replace('<h2 id="cells">Cell browser</h2>', "")
head = head.replace(
    '<div class="viewer"><video id="mv" loop muted playsinline controls></video></div>',
    '<div class="viewer"><div class="v3bar">'
    '<span class="v3name" id="v3name"></span>'
    '<span class="v3grp">'
    '<button class="v3btn" id="v3spin" type="button">pause</button>'
    '<button class="v3btn" id="v3iso" type="button">iso</button>'
    '<button class="v3btn" id="v3top" type="button">top</button>'
    '<button class="v3btn" id="v3reset" type="button">reset</button></span>'
    '<label class="v3explode">explode'
    ' <input type="range" id="v3x" min="0" max="5" step="0.5" value="0">'
    '<span class="v3xv" id="v3xv">0.0 \u00b5m</span></label>'
    '<span class="v3lod" id="v3lod"></span></div>'
    '<div class="v3legend" id="v3legend"></div>'
    '<div class="cwrap" id="cwrap"><canvas id="mv" tabindex="0"></canvas></div></div>')
head = head.replace(
    """<h2 id="stack">Layer stack</h2>""",
    """<h2 id="stack" class="stack-head">Layer stack<span class="rbadge" id="rbadge" role="status"></span></h2>""")
head = head.replace(
    """<dialog id="dlg"><button class="x" id="x" aria-label="Close">×</button>""",
    """<dialog id="dlg">""")
head = head.replace(
    """<div class="info" id="info"></div>""",
    """<div class="info-col"><div class="info-bar"><span class="library" id="v3lib"></span>"""
    """<button class="x" id="x" aria-label="Close">×</button></div>"""
    """<div class="info" id="info"></div></div>""")
head = head.replace("</style>", """
.thumb{position:relative}
.thumb canvas{width:100%;height:100%;display:block;cursor:grab;position:relative;z-index:1;touch-action:none}
.thumb .pending{position:absolute;inset:0;pointer-events:none;z-index:0}
.thumb.loaded .pending{display:none}
.thumb canvas:active{cursor:grabbing}
.modal canvas{width:100%;background:transparent;border:1px solid var(--line2);
  border-radius:9px;display:block;cursor:grab;touch-action:none}
.modal canvas:focus-visible{outline:2px solid var(--accent)}
.modal{max-width:none;padding:16px 18px;grid-template-columns:minmax(0,1fr) minmax(320px,380px);gap:0 16px;align-items:stretch}
.info-col{display:flex;flex-direction:column;gap:8px;min-height:0}
.modal .viewer{display:grid;grid-template-columns:auto minmax(0,1fr);
  grid-template-rows:36px minmax(0,1fr);gap:8px;min-height:0}
.v3bar{grid-column:1/3}
.cwrap{grid-row:2;grid-column:2;position:relative;min-height:0}
.cwrap canvas{width:100%;height:100%;min-height:0}
.v3loading{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
  font-family:var(--mono);font-size:12px;color:var(--accent);pointer-events:none;
  text-shadow:0 0 8px rgba(255,180,0,.4)}
.v3bar,.info-bar{min-height:36px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.info-bar{justify-content:space-between;border:1px solid var(--line2);background:var(--panel);
  padding:0 4px 0 12px;gap:8px}
.info-bar .library{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;
  color:var(--dim);overflow-wrap:anywhere}
.info-col .x{position:static;width:28px;height:28px;font-size:15px;margin:3px;flex:none;
  display:inline-flex;align-items:center;justify-content:center;line-height:1}
.info{flex:1;min-height:0;overflow-y:auto;max-height:none}
.v3name{font-family:var(--mono);font-size:13px;color:var(--accent);font-weight:600;overflow-wrap:anywhere;
  height:28px;box-sizing:border-box;display:inline-flex;align-items:center}
.v3xv{font-family:var(--mono);font-size:10.5px;color:var(--fg);min-width:44px;display:inline-block}
.v3grp{display:inline-flex;gap:6px}
.v3btn{background:var(--panel);color:var(--fg);border:1px solid var(--line2);height:28px;
  box-sizing:border-box;display:inline-flex;align-items:center;
  padding:4px 10px;font-family:var(--mono);font-size:10.5px;cursor:pointer}
.v3btn:hover{color:var(--accent);border-color:var(--accent)}
.v3btn:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
.v3mini{padding:2px 8px;font-size:10px;opacity:.85}
.v3legend{grid-row:2;grid-column:1;display:flex;flex-direction:column;gap:5px;
  align-items:stretch;overflow-y:auto;min-width:100px;min-height:0}
.v3legend .v3lg{justify-content:flex-start;width:100%}
.v3legend .v3mini{width:100%;text-align:center}
.stack-head{display:flex;justify-content:space-between;align-items:center;gap:8px}
.rbadge{font-family:var(--mono);font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;
  padding:1px 7px;border:1px solid var(--line2);background:var(--bg);font-weight:500}
.rbadge.gl{color:var(--accent)}
.rbadge.cpu{color:var(--dim)}
.controls{margin:16px 0;min-height:36px;align-items:stretch}
.controls input[type=search],.controls select{padding-top:0;padding-bottom:0;height:36px}
.stack-sidebar{padding-top:16px}
.stack-head{min-height:36px;margin-top:0}
@media(max-width:820px){
  .modal .viewer{display:flex;flex-direction:column}
  .cwrap{flex:none;height:56vh}
  .v3legend{flex-direction:row;flex-wrap:wrap;min-width:0}
  .v3legend .v3lg,.v3legend .v3mini{width:auto}
  /* close button always reachable at the top on mobile */
  .info-col .x{position:fixed;top:12px;right:12px;z-index:6;width:28px;height:28px;font-size:14px;
    background:var(--panel);border:1px solid var(--line2);box-shadow:0 0 0 4px var(--bg)}
  .modal{padding:12px}
  .v3bar{padding-right:44px}          /* clear the fixed close button */
  .v3lod{margin-left:0;flex-basis:100%;order:9}
}
/* mobile grid: cell browser first, layer stack a compact legend below */
@media(max-width:850px){
  .layout{display:flex;flex-direction:column}
  .page{order:1}
  .stack-sidebar{order:2;max-height:none;padding:14px}
  .stack-head{cursor:pointer}
  .stack-head::after{content:"\\25be";margin-left:auto;color:var(--dim)}
  .stack-sidebar.collapsed .stack-list{display:none}
  .stack-sidebar.collapsed .stack-head::after{content:"\\25b8"}
  .stack-lede{display:none}
  .stack-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr))}
  .stack-dims,.stack-note{display:none}      /* compact: swatch + name + layer only */
  .stack-item{padding:6px 8px}
}
@media(max-width:560px){
  .grid,.stack-list{grid-template-columns:1fr}
  .v3name{max-width:9ch;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
}
.v3lg{display:inline-flex;align-items:center;gap:5px;background:var(--panel);border:1px solid var(--line);
  border-radius:99px;padding:2px 9px 2px 5px;font-family:var(--mono);font-size:10.5px;cursor:pointer;user-select:none;
  color:var(--fg)}
input[type=range]{-webkit-appearance:none;appearance:none;--p:0%;height:18px;min-width:170px;
  background:transparent;cursor:pointer}
input[type=range]::-webkit-slider-runnable-track{height:6px;border:1px solid var(--line2);
  background:linear-gradient(to right,var(--accent) var(--p),transparent var(--p)),
    repeating-linear-gradient(to right,transparent 0,transparent calc(10% - 1px),#4a3606 calc(10% - 1px),#4a3606 10%),
    #150f02}
input[type=range]::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;width:14px;height:14px;
  margin-top:-4px;background:var(--accent);border:1px solid #000;box-shadow:0 0 6px rgba(255,180,0,.5)}
input[type=range]::-moz-range-track{height:6px;border:1px solid var(--line2);
  background:repeating-linear-gradient(to right,transparent 0,transparent calc(10% - 1px),#4a3606 calc(10% - 1px),#4a3606 10%),#150f02}
input[type=range]::-moz-range-progress{height:6px;background:var(--accent)}
input[type=range]::-moz-range-thumb{width:14px;height:14px;background:var(--accent);border:1px solid #000;box-shadow:0 0 6px rgba(255,180,0,.5)}
input[type=range]:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.v3lg .sw2{width:10px;height:10px;border-radius:3px}
.v3lg.off{opacity:.35}
.v3explode{display:flex;align-items:center;gap:7px;font-family:var(--mono);font-size:10.5px;color:var(--dim)}
.v3lod{font-family:var(--mono);font-size:10px;color:var(--dim);margin-left:auto}

/* ---- amber EL display: committed dark theme, mono everywhere ---- */
:root, :root[data-theme="dark"], :root[data-theme="light"]{
  --bg:#000000; --panel:#050402; --panel2:#0b0803; --line:#4a3606; --line2:#7a5c08;
  --fg:#f2b21d; --dim:#9c7a14; --accent:#ffb400; --good:#46e04d;
  --mono:ui-monospace,"Cascadia Mono","SF Mono",Menlo,Consolas,"DejaVu Sans Mono",monospace;
  --sans:var(--mono);
}
*{border-radius:0!important}
body{font-family:var(--mono)}
.cname,.v3name,h2,.stack-top{text-shadow:0 0 7px rgba(255,180,0,.30)}
.rbadge.gl{text-shadow:0 0 7px rgba(255,180,0,.4)}
.card,.stack-list,.fact,.pin-group,.info,.lg,.v3lg,.rbadge,.v3reset,input[type=search],select{border-color:var(--line2)}
.card:hover,.card:focus-within{border-color:var(--accent);box-shadow:0 0 12px rgba(255,180,0,.12);transform:none}
input[type=search],select{background:#050402;color:var(--fg)}
.thumb{background:#000}
.stack-list{background:#050402;list-style:none}
.v3name{background:var(--accent);color:#000;padding:2px 8px;text-shadow:none;font-weight:600}
.pin-input{--pin:#46e04d}.pin-output{--pin:#ffb400}.pin-io{--pin:#4db8ff}.pin-supply{--pin:#ff7a45}
dialog::backdrop{background:rgba(0,0,0,.988)}
.v3reset:hover{color:var(--accent);border-color:var(--accent)}
.pins code.haspin{cursor:pointer}
.pins code.haspin:hover{border-color:var(--accent);color:var(--accent)}
a{color:var(--accent)}
::selection{background:var(--accent);color:#000}
</style>""")

footer_old = "<p><strong>703 cells</strong> across 11 libraries; 703 rendered so far.\n  Videos appear as the background render completes — reload to pick up new ones.</p>"
head = head.replace(
    "Videos appear as the background render completes — reload to pick up new ones.",
    "Every card is live geometry — drag to orbit, open for layers and explode view.")
head = head.replace(
    "3D views are exploded by layer and spun 360°, rendered headless via an EGL backend for\n  GDS3D. Explode distance is scaled per library: the offset is absolute in microns, so the\n  value that suits a 350 µm I/O pad would throw a 3 µm standard cell off screen.",
    "Cells render as per-layer merged prisms extruded with the lyd25 z-stack — WebGL2 (shared context,\n  depth-buffered, blitted per card; painter's-algorithm canvas fallback), no libraries. Geometry loads only while a card is near the viewport and is\n  dropped when it scrolls away. Very large macros are level-of-detail capped (largest shapes kept)\n  and say so in their viewer. The spin-video edition remains at <a href=\"index.html\">index.html</a>.")

# ---- new script ----
js = r"""
__CELLS__
const SEQ = /^(dff|sdff|lat|icgt)/, PHYS = /^(fill|endcap|antenna|tie|hold|ant|decap|tap|diode|brk|cor)/;
function kindOf(r){
  if (r.l.slice(-3) === "_pr") return "prim";
  if (r.l.indexOf("_io") > -1) return "io";
  if (r.l.indexOf("sram") > -1 || r.l.indexOf("efuse") > -1) return "macro";
  if (SEQ.test(r.st)) return "seq";
  if (PHYS.test(r.st)) return "phys";
  return "comb";
}
CELLS.forEach(r => r.k = kindOf(r));

const COL=__COLMAP__;
const ZORDER=["COMP","Poly2","Contact","Metal1","Via1","Metal2","Via2","Metal3","Via3","Metal4","FuseTop","Via4","Metal5","Pad"];
const PBASE="prisms/";
const VIAL=["Contact","Via1","Via2","Via3","Via4"];
const REDUCED=matchMedia("(prefers-reduced-motion: reduce)").matches;

function shade(hex,f){const n=parseInt(hex.slice(1),16),r=(n>>16)&255,g=(n>>8)&255,b=n&255;
  return "rgb("+Math.min(255,r*f|0)+","+Math.min(255,g*f|0)+","+Math.min(255,b*f|0)+")";}

// ---------- shared WebGL2 renderer (one context, blitted into card canvases) ----------
const GLR=(function(){
  const cv=document.createElement("canvas");
  const gl=cv.getContext("webgl2",{antialias:true,alpha:true,premultipliedAlpha:true});
  if(!gl)return null;
  const vs=`#version 300 es
  layout(location=0) in vec3 aPos; layout(location=1) in vec3 aNrm; layout(location=2) in vec3 aCol;
  uniform mat4 uM; uniform vec2 uRot; uniform float uLine; uniform float uZoff; uniform float uBright;
  out vec3 vCol;
  void main(){
    vec4 clip=uM*vec4(aPos.x,aPos.y,aPos.z+uZoff,1.0);
    clip.z-=uLine;
    float shade;
    if(aNrm.z>0.5){ shade=1.12; }
    else{
      float wx=aNrm.x*uRot.x-aNrm.y*uRot.y, wy=aNrm.x*uRot.y+aNrm.y*uRot.x;
      shade=(0.55+0.45*max(0.0,wx*0.45-wy*0.55))*0.9;
    }
    vCol=aCol*shade*uBright;
    gl_Position=clip;
  }`;
  const fs=`#version 300 es
  precision mediump float; in vec3 vCol; out vec4 o;
  void main(){ o=vec4(vCol,1.0); }`;
  function sh(t,src){const x=gl.createShader(t);gl.shaderSource(x,src);gl.compileShader(x);
    if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(x);return x;}
  const R={cv,gl};
  R.reinit=function(){
    const prog=gl.createProgram();
    gl.attachShader(prog,sh(gl.VERTEX_SHADER,vs));gl.attachShader(prog,sh(gl.FRAGMENT_SHADER,fs));
    gl.linkProgram(prog);
    if(!gl.getProgramParameter(prog,gl.LINK_STATUS))throw gl.getProgramInfoLog(prog);
    R.prog=prog;
    R.uM=gl.getUniformLocation(prog,"uM");R.uRot=gl.getUniformLocation(prog,"uRot");
    R.uLine=gl.getUniformLocation(prog,"uLine");R.uZoff=gl.getUniformLocation(prog,"uZoff");
    R.uBright=gl.getUniformLocation(prog,"uBright");
    gl.enable(gl.DEPTH_TEST);gl.depthFunc(gl.LEQUAL);
  };
  R.reinit();
  return R;
})();

const ZZ={"COMP":[-0.3,0],"Poly2":[0,0.2],"Contact":[0,0.86],"Metal1":[0.86,1.41],
 "Via1":[1.41,2.01],"Metal2":[2.01,2.56],"Via2":[2.56,3.16],"Metal3":[3.16,3.71],
 "Via3":[3.71,4.31],"Metal4":[4.31,4.86],"FuseTop":[4.9,5.2],"Via4":[4.86,5.76],
 "Metal5":[5.76,6.95],"Pad":[6.95,7.25]};
function lerpBox(a,b,k){return {cx:a.cx+(b.cx-a.cx)*k,cy:a.cy+(b.cy-a.cy)*k,
  cz:a.cz+(b.cz-a.cz)*k,Rad:a.Rad+(b.Rad-a.Rad)*k,Zh:a.Zh+(b.Zh-a.Zh)*k};}
function pinBox(pin,off){
  let minx=1e9,maxx=-1e9,miny=1e9,maxy=-1e9,zb=1e9,zt=-1e9,li=0;
  for(const r of pin.s){
    const z=ZZ[r[0]];if(!z)continue;
    minx=Math.min(minx,r[1]);miny=Math.min(miny,r[2]);
    maxx=Math.max(maxx,r[3]);maxy=Math.max(maxy,r[4]);
    zb=Math.min(zb,z[0]);zt=Math.max(zt,z[1]);
    li=Math.max(li,ZORDER.indexOf(r[0]));
  }
  if(minx>maxx)return null;
  return {box:{cx:(minx+maxx)/2,cy:(miny+maxy)/2,cz:(zb+zt)/2+li*off,
    Rad:Math.max(1.2,Math.hypot(maxx-minx,maxy-miny)*1.6),Zh:Math.max(1.2,zt-zb)},li:li};
}
const HEXPTS=[];for(let i=0;i<6;i++){const a=Math.PI/180*(60*i+30);HEXPTS.push([Math.cos(a),Math.sin(a)]);}
function expand(d){
  if(!d||!d.layers)return d;   // v1 passthrough
  const prisms=[];
  for(const L of d.layers){
    if(L.ps)for(const flat of L.ps){
      const pts=[];
      for(let i=0;i<flat.length;i+=2)pts.push([flat[i],flat[i+1]]);
      prisms.push({l:L.l,p:pts,z0:L.z0,z1:L.z1});
    }
    if(L.hx){const r=L.hr||0.15;
      for(let i=0;i<L.hx.length;i+=2){
        const cx=L.hx[i],cy=L.hx[i+1];
        prisms.push({l:L.l,p:HEXPTS.map(h=>[cx+r*h[0],cy+r*h[1]]),z0:L.z0,z1:L.z1});
      }
    }
  }
  return {w:d.w,h:d.h,zmax:d.zmax,lod:d.lod,prisms:prisms};
}
function layerStats(d){
  const st={};
  for(const pr of d.prisms){
    let a=st[pr.l];
    if(!a)a=st[pr.l]={minx:1e9,maxx:-1e9,miny:1e9,maxy:-1e9,z0:1e9,z1:-1e9};
    for(const pt of pr.p){
      if(pt[0]<a.minx)a.minx=pt[0]; if(pt[0]>a.maxx)a.maxx=pt[0];
      if(pt[1]<a.miny)a.miny=pt[1]; if(pt[1]>a.maxy)a.maxy=pt[1];
    }
    if(pr.z0<a.z0)a.z0=pr.z0; if(pr.z1>a.z1)a.z1=pr.z1;
  }
  return st;
}
function fitBox(st,hidden,off){
  let minx=1e9,maxx=-1e9,miny=1e9,maxy=-1e9,zb=1e9,zt=-1e9,any=false;
  for(let li=0;li<ZORDER.length;li++){
    const L=ZORDER[li],a=st[L];
    if(!a||hidden.has(L))continue;
    any=true;
    if(a.minx<minx)minx=a.minx; if(a.maxx>maxx)maxx=a.maxx;
    if(a.miny<miny)miny=a.miny; if(a.maxy>maxy)maxy=a.maxy;
    const z0=a.z0+li*off,z1=a.z1+li*off;
    if(z0<zb)zb=z0; if(z1>zt)zt=z1;
  }
  if(!any){minx=0;maxx=1;miny=0;maxy=1;zb=0;zt=1;}
  return {cx:(minx+maxx)/2,cy:(miny+maxy)/2,cz:(zb+zt)/2,
    Rad:(Math.hypot(maxx-minx,maxy-miny)/2)||0.5,Zh:((zt-zb)/2)||0.5};
}
function hex2rgb(h){const n=parseInt(h.slice(1),16);return [((n>>16)&255)/255,((n>>8)&255)/255,(n&255)/255];}

// ear-clip triangulation for simple (possibly concave / keyholed) polygons
function earcut(pts){
  const n=pts.length, idx=[];
  if(n<3)return idx;
  let ring=[];
  for(let i=0;i<n;i++){
    const p=pts[i],q=pts[(i+1)%n];
    if(Math.abs(p[0]-q[0])>1e-9||Math.abs(p[1]-q[1])>1e-9)ring.push(i);
  }
  let area=0;
  for(let i=0;i<ring.length;i++){
    const p=pts[ring[i]],q=pts[ring[(i+1)%ring.length]];
    area+=p[0]*q[1]-q[0]*p[1];
  }
  if(area<0)ring.reverse();
  let guard=ring.length*ring.length+10;
  while(ring.length>3&&guard-->0){
    let clipped=false;
    for(let i=0;i<ring.length;i++){
      const a=pts[ring[(i+ring.length-1)%ring.length]],b=pts[ring[i]],c=pts[ring[(i+1)%ring.length]];
      const cross=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
      if(cross<=1e-12)continue;
      let ok=true;
      for(let j=0;j<ring.length&&ok;j++){
        const pi=ring[j];
        if(pi===ring[(i+ring.length-1)%ring.length]||pi===ring[i]||pi===ring[(i+1)%ring.length])continue;
        const p=pts[pi];
        const d1=(b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]);
        const d2=(c[0]-b[0])*(p[1]-b[1])-(c[1]-b[1])*(p[0]-b[0]);
        const d3=(a[0]-c[0])*(p[1]-c[1])-(a[1]-c[1])*(p[0]-c[0]);
        if(d1>=-1e-12&&d2>=-1e-12&&d3>=-1e-12)ok=false;
      }
      if(ok){
        idx.push(ring[(i+ring.length-1)%ring.length],ring[i],ring[(i+1)%ring.length]);
        ring.splice(i,1);clipped=true;break;
      }
    }
    if(!clipped)break; // degenerate: fan the rest
  }
  if(ring.length===3)idx.push(ring[0],ring[1],ring[2]);
  else for(let i=1;i<ring.length-1;i++)idx.push(ring[0],ring[i],ring[i+1]);
  return idx;
}

class GLView{
  constructor(cv,data,opts){
    this.cv=cv;this.d=data;this.o=opts||{};
    this.az=-0.6;this.el=1.0;this.zoom=1;this.off=0;this.panx=0;this.pany=0;this.hidden=new Set();this.panx=0;this.pany=0;
    if(this.o.novia)for(const L of VIAL)this.hidden.add(L);
    this.st=layerStats(data);
    this.spin=!!this.o.spin&&!REDUCED;
    const tris=[],lines=[];this.triRange={};this.lineRange={};
    for(const L of ZORDER){
      const start=tris.length/9, lstart=lines.length/9;
      for(const pr of data.prisms){
        if(pr.l!==L)continue;
        const col=hex2rgb(COL[L]||"#888888"),n=pr.p.length;
        for(let i=0;i<n;i++){
          const a=pr.p[i],b=pr.p[(i+1)%n];
          const ex_=b[0]-a[0],ey=b[1]-a[1],em=Math.hypot(ex_,ey)||1;
          const nx=ey/em,ny=-ex_/em;
          // two triangles for the side quad
          const v=[[a[0],a[1],pr.z0],[b[0],b[1],pr.z0],[b[0],b[1],pr.z1],
                   [a[0],a[1],pr.z0],[b[0],b[1],pr.z1],[a[0],a[1],pr.z1]];
          for(const q of v)tris.push(q[0],q[1],q[2],nx,ny,0,col[0],col[1],col[2]);
          lines.push(a[0],a[1],pr.z1,0,0,1,col[0]*0.3,col[1]*0.3,col[2]*0.3,
                     b[0],b[1],pr.z1,0,0,1,col[0]*0.3,col[1]*0.3,col[2]*0.3);
        }
        const ti=earcut(pr.p);
        for(const k of ti){
          const q=pr.p[k];
          tris.push(q[0],q[1],pr.z1,0,0,1,col[0],col[1],col[2]);
        }
      }
      this.triRange[L]=[start,tris.length/9-start];
      this.lineRange[L]=[lstart,lines.length/9-lstart];
    }
    const gl=GLR.gl;
    this.vboT=gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,this.vboT);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(tris),gl.STATIC_DRAW);
    this.vboL=gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,this.vboL);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(lines),gl.STATIC_DRAW);

    this.ptrs=new Map(); this.pinch=null; this._lastTap=0;
    this._down=e=>{
      cv.setPointerCapture(e.pointerId);
      this.ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
      this.spin=false; this.userHeld=true;
      if(this.ptrs.size===1){
        const now=performance.now();
        if(e.pointerType==="touch"&&now-this._lastTap<300){   // double-tap resets
          this.az=-0.6;this.el=1.0;this.zoom=1;this.panx=0;this.pany=0;
        }
        this._lastTap=now;
        this.drag=[e.clientX,e.clientY];
        this.panning=(e.shiftKey||e.button===1||e.button===2);
      } else if(this.ptrs.size===2){ this.drag=null; this.pinch=this._ptrState(); }
      this.request();
    };
    this._move=e=>{
      if(!this.ptrs.has(e.pointerId))return;
      this.ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(this.ptrs.size>=2){
        const p=this._ptrState();
        if(p&&this.pinch){
          const k=p.d/this.pinch.d;
          if(isFinite(k)&&k>0)this.zoom=Math.min(400,Math.max(0.35,this.zoom*k));
          this.panx+=p.cx-this.pinch.cx; this.pany+=p.cy-this.pinch.cy;
        }
        this.pinch=p; this.request(); return;
      }
      if(!this.drag)return;
      const dx=e.clientX-this.drag[0], dy=e.clientY-this.drag[1];
      if(this.panning){ this.panx+=dx; this.pany+=dy; }
      else{ this.az+=dx*0.008;
             this.el=Math.min(1.5,Math.max(0.1,this.el+dy*0.006)); }
      this.drag=[e.clientX,e.clientY]; this.request();
    };
    this._up=e=>{
      if(e&&e.pointerId!==undefined)this.ptrs.delete(e.pointerId);
      else this.ptrs.clear();
      this.pinch=null;
      if(this.ptrs.size===1){ const p=[...this.ptrs.values()][0]; this.drag=[p.x,p.y]; this.panning=false; }
      else if(this.ptrs.size===0){ this.drag=null; }
      if(this.o&&this.o.onNav)this.o.onNav();
    };
    
    
    
    cv.addEventListener("pointercancel",this._up);
    cv.addEventListener("contextmenu",e=>e.preventDefault());
    this._key=e=>{
      const k=e.key;let used=true;
      if(k==="ArrowLeft")this.az-=0.12;
      else if(k==="ArrowRight")this.az+=0.12;
      else if(k==="ArrowUp")this.el=Math.min(1.5,this.el+0.08);
      else if(k==="ArrowDown")this.el=Math.max(0.1,this.el-0.08);
      else if(k==="+"||k==="=")this.zoom=Math.min(400,this.zoom*1.15);
      else if(k==="-")this.zoom=Math.max(0.35,this.zoom/1.15);
      else used=false;
      if(used){e.preventDefault();this.spin=false;this.userHeld=true;this.request();}};
    cv.addEventListener("pointerdown",this._down);
    cv.addEventListener("pointermove",this._move);
    cv.addEventListener("pointerup",this._up);
    cv.addEventListener("contextmenu",e=>e.preventDefault());
    cv.addEventListener("keydown",this._key);
    if(this.o.wheel){this._wheel=e=>{e.preventDefault();
      this.zoom=Math.min(400,Math.max(0.35,this.zoom*(e.deltaY<0?1.15:1/1.15)));this.request();};
      cv.addEventListener("wheel",this._wheel,{passive:false});}
    if(this.spin)this.loop();else this.request();
  }
  _ptrState(){
    const a=[...this.ptrs.values()];
    if(a.length<2)return null;
    const dx=a[0].x-a[1].x, dy=a[0].y-a[1].y;
    return {d:Math.hypot(dx,dy),cx:(a[0].x+a[1].x)/2,cy:(a[0].y+a[1].y)/2};
  }
  loop(){this.raf=requestAnimationFrame(t=>{
    if(this.spin){this.az+=0.0045;this.draw();
      if(this.o.onNav&&t-(this._ht||0)>600){this._ht=t;this.o.onNav();}
      this.loop();}});}
  request(){if(this.raf2)return;this.raf2=requestAnimationFrame(()=>{this.raf2=0;this.draw();});}
  draw(){
    const d=this.d;if(!d)return;
    const _now=performance.now();
    if(this._lt!==undefined){const inst=1000/Math.max(1,_now-this._lt);
      this.fps=this.fps?this.fps*0.9+inst*0.1:inst;}
    this._lt=_now;
    const cv=this.cv,dpr=window.devicePixelRatio||1;
    const W=cv.clientWidth,H=cv.clientHeight;
    if(!W||!H)return;
    const PW=Math.round(W*dpr),PH=Math.round(H*dpr);
    if(cv.width!==PW){cv.width=PW;cv.height=PH;}
    const R=GLR,gl=R.gl;
    if(R.cv.width<PW||R.cv.height<PH){R.cv.width=Math.max(R.cv.width,PW);R.cv.height=Math.max(R.cv.height,PH);}
    gl.viewport(0,R.cv.height-PH,PW,PH);
    gl.enable(gl.SCISSOR_TEST);gl.scissor(0,R.cv.height-PH,PW,PH);
    gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT|gl.DEPTH_BUFFER_BIT);
    const ca=Math.cos(this.az),sa=Math.sin(this.az),ce=Math.cos(this.el),se=Math.sin(this.el);
    const off=this.off;
    const _tnow=performance.now();
    let fb=fitBox(this.st,this.hidden,off);
    if(this.anim){
      const k=Math.min(1,(_tnow-this.anim.t0)/this.anim.dur);
      const e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
      fb=lerpBox(this.anim.from,this.anim.to,e);
      this.az+=0.0022;
      if(k>=1){this.focus=this.anim.to;this.anim=null;}
    } else if(this.focus) fb=this.focus;
    this._fb=fb;
    const cx=fb.cx,cy=fb.cy,cz=fb.cz,Rad=fb.Rad,Zh=fb.Zh;
    const R3=Math.hypot(Rad,Zh);
    const s=Math.min(W,H)/(2*R3*1.05)*this.zoom;   // sphere fit: angle-independent, CAD-stable
    const sx=2*s/W, sy=2*s/H, span=2*(Rad+Zh)+1;
    // clip = M * (x,y,z,1); rx=(x-cx)ca-(y-cy)sa; ry=(x-cx)sa+(y-cy)ca; z'=z*ex-cz
    // X = rx*sx ; Y = -(ry*se - z'*ce)*sy ... GL y-up: screen-down formula negated
    // Z = (ry*ce + z'*se)/span
    const M=new Float32Array(16);
    M[0]=ca*sx;        M[4]=-sa*sx;        M[8]=0;            M[12]=(-cx*ca+cy*sa)*sx;
    M[1]=-sa*se*sy;    M[5]=-ca*se*sy;     M[9]=ce*sy;     M[13]=-(-cx*sa-cy*ca)*(-se*sy)+(-cz)*ce*sy;
    // GL: nearer = smaller clip z, but our painter depth is bigger = nearer -> negate
    M[2]=-sa*ce/span;  M[6]=-ca*ce/span;   M[10]=-se/span; M[14]=-(((-cx*sa-cy*ca)*ce-cz*se)/span);
    M[12]+=(this.panx||0)*2/W; M[13]-=(this.pany||0)*2/H;
    M[3]=0;M[7]=0;M[11]=0;M[15]=1;
    // fix M[13]: Y = -(ry*se - z'ce)*sy = -ry*se*sy + z'*ce*sy ; ry const part = (-cx*sa - cy*ca)
    M[13]=-((-cx*sa-cy*ca)*se)*sy+(-cz)*ce*sy;
    gl.useProgram(R.prog);
    gl.uniformMatrix4fv(R.uM,false,M);
    gl.uniform2f(R.uRot,ca,sa);
    gl.uniform1f(R.uBright,1);
    const bind=vbo=>{
      gl.bindBuffer(gl.ARRAY_BUFFER,vbo);
      gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,3,gl.FLOAT,false,36,0);
      gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,3,gl.FLOAT,false,36,12);
      gl.enableVertexAttribArray(2);gl.vertexAttribPointer(2,3,gl.FLOAT,false,36,24);
    };
    gl.uniform1f(R.uLine,0);
    bind(this.vboT);
    for(let li=0;li<ZORDER.length;li++){
      const L=ZORDER[li];
      if(this.hidden.has(L))continue;
      gl.uniform1f(R.uZoff,li*off);
      const r=this.triRange[L];if(r&&r[1])gl.drawArrays(gl.TRIANGLES,r[0],r[1]);
    }
    gl.uniform1f(R.uLine,0.0015);
    bind(this.vboL);
    for(let li=0;li<ZORDER.length;li++){
      const L=ZORDER[li];
      if(this.hidden.has(L))continue;
      gl.uniform1f(R.uZoff,li*off);
      const r=this.lineRange[L];if(r&&r[1])gl.drawArrays(gl.LINES,r[0],r[1]);
    }
    if(this.vboH&&(this.focus||this.anim||_tnow<(this.flashUntil||0))){
      const pulse=_tnow<(this.flashUntil||0)?1.05+0.55*Math.sin(_tnow/90):1.18;
      gl.uniform1f(R.uBright,pulse);
      bind(this.vboH);
      gl.uniform1f(R.uLine,0.001);
      gl.uniform1f(R.uZoff,(this.hlLi||0)*off);
      gl.drawArrays(gl.TRIANGLES,0,this.hlN);
      gl.uniform1f(R.uBright,1);
    }
    gl.disable(gl.SCISSOR_TEST);
    const ctx=cv.getContext("2d");
    ctx.setTransform(1,0,0,1,0,0);
    ctx.clearRect(0,0,PW,PH);
    ctx.drawImage(R.cv,0,0,PW,PH,0,0,PW,PH);
    if(this.fps){
      const t=Math.round(this.fps)+" fps";
      ctx.font=(9*dpr)+"px ui-monospace,Menlo,Consolas,monospace";
      ctx.fillStyle="rgba(0,0,0,.55)";ctx.fillText(t,4*dpr+1,PH-4*dpr+1);
      ctx.fillStyle="rgba(160,170,185,.9)";ctx.fillText(t,4*dpr,PH-4*dpr);
    }
  }
  flyToPin(pin){
    const pb=pinBox(pin,this.off);
    if(!pb)return;
    const tris=[];
    for(const r of pin.s){
      const z=ZZ[r[0]];if(!z)continue;
      const g=Math.max(0.05,Math.min(0.35,0.08*Math.min(r[3]-r[1],r[4]-r[2])));
      const x0=r[1]-g,y0=r[2]-g,x1=r[3]+g,y1=r[4]+g;
      const zl=z[0]-0.03,zh=z[1]+0.03,C=[1,0.78,0.12];
      const q=(p1,p2,p3,p4,nx,ny,nz)=>{for(const v of[p1,p2,p3,p1,p3,p4])tris.push(v[0],v[1],v[2],nx,ny,nz,C[0],C[1],C[2]);};
      q([x0,y0,zh],[x1,y0,zh],[x1,y1,zh],[x0,y1,zh],0,0,1);
      q([x0,y0,zl],[x1,y0,zl],[x1,y0,zh],[x0,y0,zh],0,-1,0);
      q([x1,y0,zl],[x1,y1,zl],[x1,y1,zh],[x1,y0,zh],1,0,0);
      q([x1,y1,zl],[x0,y1,zl],[x0,y1,zh],[x1,y1,zh],0,1,0);
      q([x0,y1,zl],[x0,y0,zl],[x0,y0,zh],[x0,y1,zh],-1,0,0);
    }
    const gl=GLR.gl;
    if(this.vboH)gl.deleteBuffer(this.vboH);
    this.vboH=gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER,this.vboH);
    gl.bufferData(gl.ARRAY_BUFFER,new Float32Array(tris),gl.STATIC_DRAW);
    this.hlN=tris.length/9;this.hlLi=pb.li;
    this.flashUntil=performance.now()+3200;   // flash in place — no camera motion
    this.animLoop();
  }
  animLoop(){
    if(this.rafA)return;
    const step=()=>{
      this.rafA=0;this.draw();
      if(this.anim||performance.now()<(this.flashUntil||0))this.rafA=requestAnimationFrame(step);
    };
    this.rafA=requestAnimationFrame(step);
  }
  clearFocus(){
    this.anim=null;this.focus=null;this.flashUntil=0;
    if(this.vboH){GLR.gl.deleteBuffer(this.vboH);this.vboH=null;}
    this.request();
  }
  dispose(){
    cancelAnimationFrame(this.raf);cancelAnimationFrame(this.raf2);cancelAnimationFrame(this.rafA);
    const gl=GLR.gl;
    gl.deleteBuffer(this.vboT);gl.deleteBuffer(this.vboL);
    if(this.vboH)gl.deleteBuffer(this.vboH);
    const cv=this.cv;
    cv.removeEventListener("pointerdown",this._down);
    cv.removeEventListener("pointermove",this._move);
    cv.removeEventListener("pointerup",this._up);
    if(this._wheel)cv.removeEventListener("wheel",this._wheel);
    const ctx=cv.getContext("2d");ctx&&ctx.clearRect(0,0,cv.width,cv.height);
    this.d=null;
  }
}

class PainterView{
  constructor(cv,data,opts){
    this.cv=cv;this.d=data;this.o=opts||{};
    this.az=-0.6;this.el=1.0;this.zoom=1;this.off=0;this.panx=0;this.pany=0;this.hidden=new Set();this.panx=0;this.pany=0;
    if(this.o.novia)for(const L of VIAL)this.hidden.add(L);
    this.st=layerStats(data);
    this.spin=!!this.o.spin&&!REDUCED;this.raf=0;this.last=0;
    this.ptrs=new Map(); this.pinch=null; this._lastTap=0;
    this._down=e=>{
      cv.setPointerCapture(e.pointerId);
      this.ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
      this.spin=false; this.userHeld=true;
      if(this.ptrs.size===1){
        const now=performance.now();
        if(e.pointerType==="touch"&&now-this._lastTap<300){
          this.az=-0.6;this.el=1.0;this.zoom=1;this.panx=0;this.pany=0;
        }
        this._lastTap=now;
        this.drag=[e.clientX,e.clientY];
        this.panning=(e.shiftKey||e.button===1||e.button===2);
      } else if(this.ptrs.size===2){ this.drag=null; this.pinch=this._ptrState(); }
      this.request();
    };
    this._move=e=>{
      if(!this.ptrs.has(e.pointerId))return;
      this.ptrs.set(e.pointerId,{x:e.clientX,y:e.clientY});
      if(this.ptrs.size>=2){
        const p=this._ptrState();
        if(p&&this.pinch){
          const k=p.d/this.pinch.d;
          if(isFinite(k)&&k>0)this.zoom=Math.min(400,Math.max(0.35,this.zoom*k));
          this.panx+=p.cx-this.pinch.cx; this.pany+=p.cy-this.pinch.cy;
        }
        this.pinch=p; this.request(); return;
      }
      if(!this.drag)return;
      const dx=e.clientX-this.drag[0], dy=e.clientY-this.drag[1];
      if(this.panning){ this.panx+=dx; this.pany+=dy; }
      else{ this.az+=dx*0.008;
            this.el=Math.min(1.5,Math.max(0.1,this.el+dy*0.006)); }
      this.drag=[e.clientX,e.clientY];this.request();};
    this._up=e=>{
      if(e&&e.pointerId!==undefined)this.ptrs.delete(e.pointerId); else this.ptrs.clear();
      this.pinch=null;
      if(this.ptrs.size===1){ const q=[...this.ptrs.values()][0]; this.drag=[q.x,q.y]; this.panning=false; }
      else if(this.ptrs.size===0){ this.drag=null; }
      if(this.o.onNav)this.o.onNav();};
    cv.addEventListener("pointerdown",this._down);
    cv.addEventListener("pointermove",this._move);
    cv.addEventListener("pointerup",this._up);
    cv.addEventListener("pointercancel",this._up);
    cv.addEventListener("contextmenu",e=>e.preventDefault());
    if(this.o.wheel){this._wheel=e=>{e.preventDefault();
      this.zoom=Math.min(400,Math.max(0.35,this.zoom*(e.deltaY<0?1.15:1/1.15)));this.request();};
      cv.addEventListener("wheel",this._wheel,{passive:false});}
    if(this.spin)this.loop();else this.request();
  }
  _ptrState(){
    const a=[...this.ptrs.values()];
    if(a.length<2)return null;
    const dx=a[0].x-a[1].x, dy=a[0].y-a[1].y;
    return {d:Math.hypot(dx,dy),cx:(a[0].x+a[1].x)/2,cy:(a[0].y+a[1].y)/2};
  }
  loop(){this.raf=requestAnimationFrame(t=>{
    if(this.spin){this.az+=0.0045;this.draw();
      if(this.o.onNav&&t-(this._ht||0)>600){this._ht=t;this.o.onNav();}
      this.loop();}});}
  request(){if(this.raf2)return;this.raf2=requestAnimationFrame(()=>{this.raf2=0;this.draw();});}
  draw(){
    const cv=this.cv,d=this.d,dpr=window.devicePixelRatio||1;
    if(!d)return;
    const _now=performance.now();
    if(this._lt!==undefined){const inst=1000/Math.max(1,_now-this._lt);
      this.fps=this.fps?this.fps*0.9+inst*0.1:inst;}
    this._lt=_now;
    const W=cv.clientWidth,H=cv.clientHeight;
    if(!W||!H)return;
    if(cv.width!==(W*dpr|0)){cv.width=W*dpr;cv.height=H*dpr;}
    const ctx=cv.getContext("2d");
    ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);
    const ca=Math.cos(this.az),sa=Math.sin(this.az),ce=Math.cos(this.el),se=Math.sin(this.el);
    const off=this.off;
    const _tnow=performance.now();
    let fb=fitBox(this.st,this.hidden,off);
    if(this.anim){
      const k=Math.min(1,(_tnow-this.anim.t0)/this.anim.dur);
      const e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;
      fb=lerpBox(this.anim.from,this.anim.to,e);
      this.az+=0.0022;
      if(k>=1){this.focus=this.anim.to;this.anim=null;}
    } else if(this.focus) fb=this.focus;
    this._fb=fb;
    const cx=fb.cx,cy=fb.cy,cz=fb.cz,Rad=fb.Rad,Zh=fb.Zh;
    const R3=Math.hypot(Rad,Zh);
    const s=Math.min(W,H)/(2*R3*1.05)*this.zoom;   // sphere fit: angle-independent, CAD-stable
    const faces=[];
    if(this.hl&&(this.focus||this.anim||_tnow<(this.flashUntil||0))){
      const a=_tnow<(this.flashUntil||0)?0.5+0.35*Math.sin(_tnow/90):0.65;
      for(const r of this.hl){
        const z=ZZ[r[0]];if(!z)continue;
        const li=ZORDER.indexOf(r[0]);
        faces.push({hl:!0,a:a,p:[[r[1],r[2]],[r[3],r[2]],[r[3],r[4]],[r[1],r[4]]],z:z[1]+li*off+0.04});
      }
    }
    for(const pr of d.prisms){
      if(this.hidden.has(pr.l))continue;
      const zo=ZORDER.indexOf(pr.l)*off;
      const z0=pr.z0+zo-cz,z1=pr.z1+zo-cz,n=pr.p.length,base=COL[pr.l]||"#888";
      const proj=[];
      for(let i=0;i<n;i++){
        const x=pr.p[i][0]-cx,y=pr.p[i][1]-cy;
        const rx=x*ca-y*sa,ry=x*sa+y*ca;
        proj.push([W/2+rx*s+(this.panx||0),H/2+ry*se*s+(this.pany||0),ry*ce]);
      }
      const bot=proj.map((p,i)=>[p[0],p[1]-z0*ce*s,p[2]+z0*se]);
      const top=proj.map((p,i)=>[p[0],p[1]-z1*ce*s,p[2]+z1*se]);
      for(let i=0;i<n;i++){
        const j=(i+1)%n;
        const ex_=pr.p[j][0]-pr.p[i][0],ey=pr.p[j][1]-pr.p[i][1],em=Math.hypot(ex_,ey)||1;
        const nx=ey/em,ny=-ex_/em,wx=nx*ca-ny*sa,wy=nx*sa+ny*ca;
        const lam=0.55+0.45*Math.max(0,wx*0.45-wy*0.55);
        const q=[bot[i],bot[j],top[j],top[i]];
        faces.push({q,d:(q[0][2]+q[1][2]+q[2][2]+q[3][2])/4,c:shade(base,lam*0.9)});
      }
      faces.push({q:top,d:top.reduce((a,v)=>a+v[2],0)/top.length+1e-4,c:shade(base,1.12)});
    }
    faces.sort((a,b)=>a.d-b.d);
    ctx.lineWidth=0.4;
    for(const f of faces){
      ctx.beginPath();ctx.moveTo(f.q[0][0],f.q[0][1]);
      for(let i=1;i<f.q.length;i++)ctx.lineTo(f.q[i][0],f.q[i][1]);
      ctx.closePath();ctx.fillStyle=f.c;ctx.fill();
      ctx.strokeStyle="rgba(0,0,0,.22)";ctx.stroke();
    }
    for(const f of faces){
      if(!f.hl)continue;
      ctx.beginPath();
      let first=!0;
      for(const pt of f.p){
        const x=pt[0]-cx,y=pt[1]-cy,rx=x*ca-y*sa,ry=x*sa+y*ca;
        const sx2=W/2+rx*s,sy2=H/2+(ry*se-(f.z-cz)*ce)*s;
        if(first){ctx.moveTo(sx2,sy2);first=!1;}else ctx.lineTo(sx2,sy2);
      }
      ctx.closePath();
      ctx.fillStyle="rgba(255,190,30,"+f.a+")";ctx.fill();
    }
    if(this.fps){
      const t=Math.round(this.fps)+" fps";
      ctx.font="9px ui-monospace,Menlo,Consolas,monospace";
      ctx.fillStyle="rgba(0,0,0,.55)";ctx.fillText(t,5,H-4);
      ctx.fillStyle="rgba(160,170,185,.9)";ctx.fillText(t,4,H-5);
    }
  }
  flyToPin(pin){
    const pb=pinBox(pin,this.off);
    if(!pb)return;
    this.hl=pin.s;this.hlLi=pb.li;
    this.flashUntil=performance.now()+3200;
    this.animLoop();
  }
  animLoop(){
    if(this.rafA)return;
    const step=()=>{
      this.rafA=0;this.draw();
      if(this.anim||performance.now()<(this.flashUntil||0))this.rafA=requestAnimationFrame(step);
    };
    this.rafA=requestAnimationFrame(step);
  }
  clearFocus(){this.anim=null;this.focus=null;this.flashUntil=0;this.hl=null;this.request();}
  dispose(){
    cancelAnimationFrame(this.raf);cancelAnimationFrame(this.raf2);
    const cv=this.cv;
    cv.removeEventListener("pointerdown",this._down);
    cv.removeEventListener("pointermove",this._move);
    cv.removeEventListener("pointerup",this._up);
    if(this._wheel)cv.removeEventListener("wheel",this._wheel);
    const ctx=cv.getContext("2d");ctx&&ctx.clearRect(0,0,cv.width,cv.height);
    this.d=null;
  }
}

const PrismView = GLR ? GLView : PainterView;


const grid=document.getElementById("grid"), q=document.getElementById("q"),
      lib=document.getElementById("lib"), kind=document.getElementById("kind"),
      count=document.getElementById("count");

// Load geometry only while a card is near the viewport; drop it when it
// scrolls away — same memory strategy as the video edition.
const ACTIVE=new Set();
function setBadge(){
  const b=document.getElementById("rbadge");
  if(!b)return;
  if(GLR){b.textContent="webgl2 on";b.className="rbadge gl";
    b.title="Hardware rendering: one shared depth-buffered WebGL2 context, blitted per card";}
  else{b.textContent="webgl2 off";b.className="rbadge cpu";
    b.title="WebGL2 unavailable \u2014 software painter's-algorithm renderer";}
}
setBadge();
if(GLR){
  GLR.cv.addEventListener("webglcontextlost",e=>{
    e.preventDefault();
    const b=document.getElementById("rbadge");
    if(b){b.textContent="webgl2 \u2026";b.className="rbadge cpu";}
    for(const v of [...ACTIVE]){v.dispose();ACTIVE.delete(v);}
    if(modalView){modalView.dispose();modalView=null;}
  });
  GLR.cv.addEventListener("webglcontextrestored",()=>{GLR.reinit();setBadge();render();});
}
const io = new IntersectionObserver(es=>{
  for(const e of es){ const cv=e.target;
    if(e.isIntersecting){
      if(cv._pv||cv._loading)continue;
      cv._loading=true;
      fetch(PBASE+cv.dataset.p).then(r=>r.ok?r.json():null).then(raw=>{
        const d=expand(raw);
        cv._loading=false;
        if(!d){cv.closest(".thumb").innerHTML='<div class="pending">no geometry</div>';return;}
        if(cv.isConnected){
          const v=new PrismView(cv,d,{spin:true,novia:true});
          cv._pv=v; ACTIVE.add(v);
          cv.closest(".thumb").classList.add("loaded");
          cv.addEventListener("pointerenter",()=>{v.spin=false;});
          cv.addEventListener("pointerleave",()=>{
            if(!REDUCED&&!v.userHeld&&!dlg.open&&v.d){v.spin=true;v.loop();}});
        }
      }).catch(()=>cv._loading=false);
    } else if(cv._pv){ ACTIVE.delete(cv._pv); cv._pv.dispose(); cv._pv=null;
      cv.closest(".thumb").classList.remove("loaded"); }
  }
},{rootMargin:"250px"});

function render(){
  const t=q.value.trim().toLowerCase(), L=lib.value, K=kind.value;
  const sel = CELLS.filter(r =>
    (!L || r.l===L) && (!K || r.k===K) &&
    (!t || r.s.toLowerCase().includes(t) || (r.fam||"").toLowerCase().includes(t) ||
     Object.values(r.fn||{}).join(" ").toLowerCase().includes(t)));
  count.textContent = sel.length + " of " + CELLS.length;
  grid.querySelectorAll("canvas[data-p]").forEach(cv=>{io.unobserve(cv);
    if(cv._pv){ACTIVE.delete(cv._pv);cv._pv.dispose();}});
  grid.innerHTML="";
  const frag=document.createDocumentFragment();
  for(const r of sel){
    const card=document.createElement("article"); card.className="card";
    const b=document.createElement("button"); b.className="card-open";
    b.setAttribute("aria-label","Open "+r.s+" details");
    b.innerHTML='<div class="thumb"><canvas data-p="'+r.n+'.json"></canvas>'+
      '<div class="pending">loading\u2026</div></div><div class="cbody">'+
      '<div class="cname">'+r.s+'</div><div class="cfam">'+(r.fam||"&nbsp;")+'</div>'+
      '<div class="cmeta">'+(r.w?r.w.toFixed(3)+" × "+r.h.toFixed(3)+" µm":"")+
      (r.area?" · "+r.area.toFixed(1)+" µm²":"")+'</div>'+
      '<div class="csource">GDS from gf180mcuD/<br><span>'+r.g+'</span></div></div>';
    b.addEventListener("click",e=>{ if(!e.target.closest("canvas")||!dragging) open_(r); });
    card.appendChild(b);
    const actions=document.createElement("div"); actions.className="card-actions";
    const dl=document.createElement("a"); dl.className="card-download";
    dl.href=PBASE+r.n+".json"; dl.download=r.s+".json";
    dl.textContent="↓ geometry JSON";
    actions.appendChild(dl); card.appendChild(actions);
    frag.appendChild(card);
  }
  grid.appendChild(frag);
  grid.querySelectorAll("canvas[data-p]").forEach(cv=>io.observe(cv));
}
let dragging=false;
addEventListener("pointerdown",()=>dragging=false);
addEventListener("pointermove",e=>{if(e.buttons)dragging=true;});

const dlg=document.getElementById("dlg"), mv=document.getElementById("mv"),
      info=document.getElementById("info"), v3legend=document.getElementById("v3legend"),
      v3x=document.getElementById("v3x"), v3lod=document.getElementById("v3lod"),
      v3name=document.getElementById("v3name"), v3xv=document.getElementById("v3xv"),
      v3reset=document.getElementById("v3reset"), v3lib=document.getElementById("v3lib");
let modalView=null;
function pinGroup(label,pins,klass){
  if(!pins || !pins.length) return "";
  return '<div class="pin-group '+klass+'"><div class="pin-title"><span>'+label+
    '</span><b>'+pins.length+'</b></div><div class="pins">'+
    pins.map(p=>'<code data-pin="'+p+'">'+p+'</code>').join("")+'</div></div>';
}
let curCell=null, hashT=0;
function queueHash(){clearTimeout(hashT);hashT=setTimeout(writeHash,120);writeHash();}
function writeHash(){
  if(!dlg.open||!modalView||!curCell)return;
  const sp=new URLSearchParams();
  sp.set("c",curCell);
  if(+v3x.value>0)sp.set("x",(+v3x.value).toFixed(1));
  const az=Math.atan2(Math.sin(modalView.az),Math.cos(modalView.az));
  sp.set("az",az.toFixed(3)); sp.set("el",modalView.el.toFixed(3));
  if(Math.abs(modalView.zoom-1)>0.01)sp.set("zm",modalView.zoom.toFixed(2));
  if(modalView.hidden.size)sp.set("h",[...modalView.hidden].join(","));
  if(!modalView.spin)sp.set("spin","0");
  if(curPin)sp.set("pin",curPin);
  try{history.replaceState(null,"","#"+sp.toString());}catch(_){location.hash=sp.toString();}
}
function open_(r,hp){
  if(modalView){modalView.dispose();modalView=null;}
  curCell=r.n;
  for(const v of ACTIVE){v._paused=v.spin;v.spin=false;}
  v3legend.innerHTML=""; v3lod.textContent="loading\u2026";
  const _px=(hp&&hp.get("x"))||new URLSearchParams(location.search).get("x");
  v3x.value=_px?Math.min(5,Math.max(0,+_px)):0;
  updSlider(); v3name.textContent=r.s; v3lib.textContent=r.l;
  const cwrap=document.getElementById("cwrap")||mv.parentElement;
  let loadEl=cwrap.querySelector(".v3loading");
  if(!loadEl){loadEl=document.createElement("div");loadEl.className="v3loading";cwrap.appendChild(loadEl);}
  loadEl.textContent="loading geometry\u2026";loadEl.style.display="";
  const clearLoading=()=>{if(loadEl)loadEl.style.display="none";};
  // defer the fetch+build so the modal chrome paints first and the UI stays live
  requestAnimationFrame(()=>{
  fetch(PBASE+r.n+".json").then(x=>x.ok?x.json():null).then(raw=>{
    if(!dlg.open)return;
    // yield once more so the browser can paint before the heavy expand/build
    requestAnimationFrame(()=>{
    if(!dlg.open)return;
    const d=expand(raw);
    if(!d)return;
    modalView=new PrismView(mv,d,{spin:true,wheel:true,onNav:queueHash});
    clearLoading();
    if(hp){
      if(hp.get("az"))modalView.az=+hp.get("az");
      if(hp.get("el"))modalView.el=Math.min(1.5,Math.max(0.1,+hp.get("el")));
      if(hp.get("zm"))modalView.zoom=Math.min(400,Math.max(0.35,+hp.get("zm")));
      if(hp.get("h"))for(const L of hp.get("h").split(",").filter(x=>COL[x]))modalView.hidden.add(L);
      if(hp.get("spin")==="0")modalView.spin=false;
    }
    modalView.off=+v3x.value;
    buildChips(d);
    updSpin();
    const oreq=modalView.request.bind(modalView);
    modalView.request=function(){oreq();queueHash();};
    const pmap={};
    for(const pp of (raw&&raw.pins)||[])pmap[pp.n]=pp;
    info.querySelectorAll("code[data-pin]").forEach(el=>{
      const pp=pmap[el.dataset.pin];
      if(!pp)return;
      el.classList.add("haspin");el.title="locate pin";
      el.addEventListener("click",()=>{
        if(!modalView)return;
        modalView.flyToPin(pp);curPin=pp.n;queueHash();});
    });
    if(hp&&hp.get("pin")&&pmap[hp.get("pin")]){
      modalView.flyToPin(pmap[hp.get("pin")]);curPin=hp.get("pin");
    }
    queueHash();
    let lodTxt = (d.lod && d.lod.shown<d.lod.total)
      ? "LOD: "+d.lod.shown+" of "+d.lod.total+" shapes (largest kept)" : "";
    if(d.lod && d.lod.vias) lodTxt += (lodTxt?" \u00b7 ":"")+"vias sampled "+d.lod.vias;
    v3lod.textContent = lodTxt;
    });
  });
  });
  let fn="";
  for(const [p,e] of Object.entries(r.fn||{})) fn+='<div><i>'+p+' =</i> '+e+'</div>';
  const src="libs.ref/"+r.l+"/";
  let facts="";
  if(r.w) facts+='<div class="fact"><span>Dimensions</span><strong>'+r.w.toFixed(3)+' × '+
    r.h.toFixed(3)+' µm</strong><small>'+Math.round(r.w*1000)+' × '+Math.round(r.h*1000)+' nm</small></div>';
  if(r.area) facts+='<div class="fact"><span>Area</span><strong>'+r.area.toFixed(3)+' µm²</strong></div>';
  if(r.site) facts+='<div class="fact"><span>Site</span><strong>'+r.site+'</strong></div>';
  const pins=pinGroup("Inputs",r.i,"pin-input")+pinGroup("Outputs",r.o,"pin-output")+
    pinGroup("Bidirectional",r.b||[],"pin-io")+pinGroup("Supplies",r.p,"pin-supply")+
    pinGroup("Unspecified in LEF",r.u||[],"pin-unknown");
  const sources=r.k==="prim"
    ? '<div><i>GDS</i> gf180mcuD/'+r.g+'</div><div><i>Metadata</i> layout only — no LEF or Liberty</div>'
    : '<div><i>GDS</i> gf180mcuD/'+r.g+'</div><div><i>LEF · dimensions, site, pins</i> gf180mcuD/'+
      src+'lef/</div><div><i>Liberty · area, logic</i> gf180mcuD/'+src+'lib/</div>';
  info.innerHTML='<div class="info-head"><h3>'+r.n+
    '</h3><div class="fam">'+(r.fam||"")+'</div></div>'+
    (facts?'<div class="facts">'+facts+'</div>':'')+
    '<section class="modal-section"><h4 class="section-title">Pins · LEF</h4><div class="pin-groups">'+
      (pins||'<div class="empty">No LEF pin metadata for this layout-only cell.</div>')+'</div></section>'+
    (fn?'<section class="modal-section"><h4 class="section-title">Logic · Liberty</h4><div class="logic">'+
      fn+'</div></section>':'')+
    '<section class="modal-section"><h4 class="section-title">PDK sources</h4><div class="source">'+sources+'</div></section>';
  history.replaceState(null,"","#c="+encodeURIComponent(r.n));
  dlg.showModal();
}
const v3spin=document.getElementById("v3spin"), v3iso=document.getElementById("v3iso"),
      v3top=document.getElementById("v3top");
function updSpin(){v3spin.textContent=(modalView&&modalView.spin)?"pause":"spin";}
function buildChips(d){
  v3legend.innerHTML="";
  const present=new Set(d.prisms.map(pr=>pr.l));
  const order=[...ZORDER].reverse().filter(l=>present.has(l)); // top of stack first
  const chips={};
  function sync(){
    for(const l of order)chips[l].classList.toggle("off",modalView.hidden.has(l));
    modalView.request();
  }
  for(const l of order){
    const b=document.createElement("button");
    b.type="button";b.className="v3lg";
    b.innerHTML='<span class="sw2" style="background:'+COL[l]+'"></span>'+l;
    b.title="click: toggle \u00b7 double-click: solo";
    b.addEventListener("click",()=>{
      if(modalView.hidden.has(l))modalView.hidden.delete(l);
      else modalView.hidden.add(l);
      sync();});
    b.addEventListener("dblclick",()=>{
      const others=order.filter(x=>x!==l);
      const soloed=!modalView.hidden.has(l)&&others.every(x=>modalView.hidden.has(x));
      modalView.hidden.clear();
      if(!soloed)for(const x of others)modalView.hidden.add(x);
      sync();});
    v3legend.appendChild(b);chips[l]=b;
  }
  const mk=(t,fn)=>{const b=document.createElement("button");b.type="button";
    b.className="v3btn v3mini";b.textContent=t;b.addEventListener("click",fn);
    v3legend.appendChild(b);};
  mk("all",()=>{modalView.hidden.clear();sync();});
  mk("none",()=>{for(const x of order)modalView.hidden.add(x);sync();});
  sync();
}
function updSlider(){
  const p=(+v3x.value-+v3x.min)/(+v3x.max-+v3x.min)*100;
  v3x.style.setProperty("--p",p+"%");
  v3xv.textContent=(+v3x.value).toFixed(1)+" \u00b5m";
}
v3x.addEventListener("input",()=>{
  updSlider();
  if(modalView){modalView.off=+v3x.value;modalView.request();}});
v3reset.addEventListener("click",()=>{
  v3x.value=0; updSlider(); curPin=null;
  if(modalView){modalView.clearFocus();modalView.az=-0.6;modalView.el=1.0;modalView.zoom=1;modalView.off=0;modalView.panx=0;modalView.pany=0;modalView.request();}});
v3spin.addEventListener("click",()=>{
  if(!modalView)return;
  if(modalView.spin){modalView.spin=false;}
  else{modalView.userHeld=false;modalView.spin=true;modalView.loop();}
  updSpin();queueHash();});
v3iso.addEventListener("click",()=>{if(modalView){modalView.az=-0.6;modalView.el=1.0;modalView.request();}});
v3top.addEventListener("click",()=>{if(modalView){modalView.az=0;modalView.el=1.5;modalView.request();}});
mv.addEventListener("pointerdown",()=>setTimeout(updSpin,0));
function close_(){ curPin=null; history.replaceState(null,"",location.pathname+location.search); dlg.close();
  if(modalView){modalView.dispose();modalView=null;}
  for(const v of ACTIVE){if(v._paused&&!REDUCED&&v.d){v.spin=true;v.loop();}v._paused=false;} }
document.getElementById("x").addEventListener("click",close_);
dlg.addEventListener("click",e=>{ if(e.target===dlg) close_(); });
dlg.addEventListener("cancel",e=>{ e.preventDefault(); close_(); });
[q,lib,kind].forEach(el=>el.addEventListener("input",render));
// URL params preset the filters: ?q=nand2&lib=gf180mcu_fd_sc_mcu7t5v0&kind=comb
{const sp=new URLSearchParams(location.search);
 if(sp.get("q"))q.value=sp.get("q");
 if(sp.get("lib"))lib.value=sp.get("lib");
 if(sp.get("kind"))kind.value=sp.get("kind");}
render();
function openByHash(){
  if(!location.hash||location.hash.length<2)return;
  const hp=new URLSearchParams(location.hash.slice(1));
  const n=hp.get("c");
  if(!n)return;
  const r=CELLS.find(x=>x.n===decodeURIComponent(n));
  if(r)open_(r,hp);
}
addEventListener("hashchange",openByHash);
openByHash();

// mobile: collapse the layer-stack legend by default; tap heading to toggle
(function(){
  const side=document.querySelector(".stack-sidebar"), head=document.getElementById("stack");
  if(!side||!head)return;
  const mq=matchMedia("(max-width:850px)");
  const apply=()=>{ if(mq.matches)side.classList.add("collapsed"); else side.classList.remove("collapsed"); };
  apply(); mq.addEventListener("change",apply);
  head.addEventListener("click",()=>{ if(mq.matches)side.classList.toggle("collapsed"); });
})();
"""
js = js.replace("__CELLS__", cells_line)

# layer palette parsed from the sidebar markup so 3D colors always match it
pairs = re.findall(r'--c:(#[0-9a-fA-F]{6})"></span>([A-Za-z0-9]+)</span>', src)
colmap = {name: hexv for hexv, name in pairs}
needed = ["COMP","Poly2","Contact","Metal1","Via1","Metal2","Via2","Metal3","Via3",
          "Metal4","FuseTop","Via4","Metal5","Pad"]
missing = [n for n in needed if n not in colmap]
assert not missing, f"sidebar palette missing {missing}"
js = js.replace("__COLMAP__", json.dumps({n: colmap[n] for n in needed}))

out = head + "<script>\n" + js + "\n</script></body></html>\n"
(DOCS / "index3d.html").write_text(out)
print("wrote docs/index3d.html:", len(out), "bytes")
