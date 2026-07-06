#!/usr/bin/env python3
"""Render an interactive 3D preview of base print files to bases_3d.html.

Same sampling as bases_preview.py (a few bases per texture variant plus
objectives), but each sample becomes an orbitable 3D plane: the
heightmap displaces the mesh at true physical scale (mm), the color
file is the texture. Sliders for relief exaggeration and light
elevation — judging 0.3–0.5 mm of relief needs raking light.

The HTML embeds the PNGs as base64 but loads three.js from jsDelivr,
so viewing needs network access once (browser caches it after).
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from collections import defaultdict
from io import BytesIO
from pathlib import Path

from PIL import Image

from generator import (
    add_common_args,
    build_sticker,
    get_icon_svg,
    load_flag,
    parse_bool,
    resolve_background,
)
from bases import (
    DEFAULT_TEXTURES,
    OBJECTIVE_BASE,
    OBJECTIVE_VARIANT,
    BLEED_MM,
    Textures,
    parse_base,
    render_base,
    row_rng,
    variant_for_platoon,
)

ROOT = Path(__file__).parent
DEFAULT_HTML = ROOT / "bases_3d.html"

PER_VARIANT = 2
RELIEF_MM = 0.8  # production Eufy Studio max-relief setting (PETG test, 2026-07)


def to_b64(img: Image.Image) -> str:
    buf = BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Render bases_3d.html.")
    add_common_args(p)
    p.add_argument("--textures", type=Path, default=DEFAULT_TEXTURES)
    p.add_argument("--seed", type=int, default=1979)
    p.add_argument("--html", type=Path, default=DEFAULT_HTML)
    args = p.parse_args(argv)

    if not args.csv.exists():
        print(f"Missing input: {args.csv}", file=sys.stderr)
        return 1

    bg = resolve_background(args)
    flag_inner, flag_vb = load_flag(args.country, args.flag)
    textures = Textures(args.textures)

    with args.csv.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    by_variant: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if not (row.get("base") or "").strip():
            continue
        v = variant_for_platoon(
            args.seed, row.get("formation") or "", row.get("group") or "")
        seen = {r["base"] for r in by_variant[v]}
        if len(by_variant[v]) < PER_VARIANT and row["base"] not in seen:
            by_variant[v].append(row)

    icon_cache: dict[tuple[str, bool], str] = {}
    samples: list[dict] = []

    def add_sample(label: str, sub: str, base_wd: str,
                   color: Image.Image, height: Image.Image) -> None:
        w, d = parse_base(base_wd)
        samples.append({
            "label": label, "sub": sub,
            "wMm": w + 2 * BLEED_MM, "dMm": d + 2 * BLEED_MM,
            "color": to_b64(color), "height": to_b64(height),
        })

    for variant in sorted(by_variant):
        for row in by_variant[variant]:
            base_w, base_d = parse_base(row["base"])
            symbol = (row.get("symbol") or "").strip()
            is_hq = parse_bool(row.get("hq"))
            key = (symbol, is_hq)
            if key not in icon_cache:
                icon_cache[key] = get_icon_svg(args.affiliation, symbol, is_hq)
            sticker_svg = build_sticker(
                row["designation"], row["name"], icon_cache[key], base_w,
                bg, flag_inner, flag_vb,
            )
            rng = row_rng(args.seed, row["designation"], row["name"])
            color, height = render_base(
                textures, variant, base_w, base_d, rng, sticker_svg,
                sticker_bg=bg)
            add_sample(f"{row['designation']} · {row['name']}",
                       f"{variant} · {row['base']} mm", row["base"], color, height)

    for i in (1, 2):
        rng = row_rng(args.seed, f"OBJ{i:02d}", "objective")
        ow, od = parse_base(OBJECTIVE_BASE)
        color, height = render_base(
            textures, OBJECTIVE_VARIANT, ow, od, rng, None, objective=True)
        add_sample(f"OBJ{i:02d}", f"{OBJECTIVE_VARIANT} · {OBJECTIVE_BASE} mm",
                   OBJECTIVE_BASE, color, height)

    data = json.dumps(samples)
    html = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Base 3D preview</title>
<style>
  body { margin:0; background:#222; color:#ddd; font-family:sans-serif;
         display:flex; flex-direction:column; height:100vh; }
  #bar { padding:10px 14px; display:flex; gap:18px; align-items:center;
         background:#2e2e2e; flex-wrap:wrap; }
  #bar label { font-size:13px; color:#aaa; }
  #view { flex:1; }
  select, input[type=range] { vertical-align:middle; }
  #sub { color:#888; font-size:12px; }
</style>
<script type="importmap">
{"imports":{"three":"https://cdn.jsdelivr.net/npm/three@0.165.0/build/three.module.js",
"three/addons/":"https://cdn.jsdelivr.net/npm/three@0.165.0/examples/jsm/"}}
</script>
</head><body>
<div id="bar">
  <label>Base <select id="sel"></select></label>
  <span id="sub"></span>
  <label>Relief ×<span id="exv">1</span>
    <input id="exag" type="range" min="1" max="10" step="0.5" value="1"></label>
  <label>Light elevation <span id="elv">20</span>°
    <input id="elev" type="range" min="5" max="80" step="1" value="20"></label>
  <span id="sub2" style="color:#666;font-size:12px">drag = orbit · wheel = zoom
    · relief at ×1 is the physical 0.8 mm</span>
</div>
<div id="view"></div>
<script type="module">
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

const SAMPLES = __DATA__;
const RELIEF_MM = __RELIEF__;

const view = document.getElementById('view');
const renderer = new THREE.WebGLRenderer({antialias:true});
view.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x222222);
const camera = new THREE.PerspectiveCamera(35, 1, 1, 2000);
camera.position.set(0, -55, 35);
const controls = new OrbitControls(camera, renderer.domElement);

const amb = new THREE.AmbientLight(0xffffff, 0.45);
scene.add(amb);
const sun = new THREE.DirectionalLight(0xfff4e0, 1.4);
scene.add(sun);

let mesh = null, cur = null;

function loadImage(src) {
  return new Promise(res => { const i = new Image(); i.onload = () => res(i); i.src = src; });
}

function pixels(img) {
  const c = document.createElement('canvas');
  c.width = img.width; c.height = img.height;
  const ctx = c.getContext('2d');
  ctx.drawImage(img, 0, 0);
  return ctx.getImageData(0, 0, img.width, img.height);
}

async function show(idx) {
  const s = SAMPLES[idx];
  document.getElementById('sub').textContent = s.sub;
  const [ci, hi] = await Promise.all([loadImage(s.color), loadImage(s.height)]);
  const hd = pixels(hi);
  const nx = hi.width, ny = hi.height;
  const geo = new THREE.PlaneGeometry(s.wMm, s.dMm, nx - 1, ny - 1);
  const base = new Float32Array(nx * ny);
  for (let y = 0; y < ny; y++)
    for (let x = 0; x < nx; x++)
      base[y * nx + x] = hd.data[(y * nx + x) * 4] / 255;
  const tex = new THREE.Texture(ci);
  tex.needsUpdate = true;
  tex.colorSpace = THREE.SRGBColorSpace;
  const mat = new THREE.MeshStandardMaterial({map: tex, roughness: 0.85, metalness: 0});
  if (mesh) { scene.remove(mesh); mesh.geometry.dispose(); mesh.material.map.dispose(); mesh.material.dispose(); }
  mesh = new THREE.Mesh(geo, mat);
  scene.add(mesh);
  cur = {geo, base, nx, ny};
  displace();
}

function displace() {
  if (!cur) return;
  const ex = parseFloat(document.getElementById('exag').value);
  document.getElementById('exv').textContent = ex;
  const pos = cur.geo.attributes.position;
  for (let i = 0; i < pos.count; i++)
    pos.setZ(i, cur.base[i] * RELIEF_MM * ex);
  pos.needsUpdate = true;
  cur.geo.computeVertexNormals();
}

function relight() {
  const el = parseFloat(document.getElementById('elev').value) * Math.PI / 180;
  document.getElementById('elv').textContent = document.getElementById('elev').value;
  sun.position.set(-Math.cos(el) * 60, -Math.cos(el) * 30, Math.sin(el) * 60);
}

function resize() {
  const w = view.clientWidth, h = view.clientHeight;
  renderer.setSize(w, h);
  renderer.setPixelRatio(window.devicePixelRatio);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}

const sel = document.getElementById('sel');
SAMPLES.forEach((s, i) => sel.add(new Option(s.label, i)));
sel.onchange = () => show(sel.value);
document.getElementById('exag').oninput = displace;
document.getElementById('elev').oninput = relight;
window.onresize = resize;

resize(); relight(); show(0);
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
</script>
</body></html>
"""
    html = html.replace("__DATA__", data).replace("__RELIEF__", str(RELIEF_MM))
    args.html.write_text(html, encoding="utf-8")
    print(f"Wrote {args.html} with {len(samples)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
