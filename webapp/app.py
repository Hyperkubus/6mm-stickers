"""Tiny Flask wrapper around the generator/sheets/preview CLIs.

Each request runs the pipeline in an isolated tempdir and streams the
result back as a download (zip / pdf / html). The repo's `lists/` and
`flags/` directories are read-only inputs.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file, abort

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from generator import COMMON_SYMBOLS, get_icon_svg

ROOT = Path(__file__).resolve().parent.parent
LISTS_DIR = ROOT / "lists"
FLAGS_DIR = ROOT / "flags"
AFFILIATIONS = ("friend", "hostile", "neutral", "unknown")
MAX_UPLOAD = 2 * 1024 * 1024  # 2 MB — CSVs are tiny

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD


def _available_csvs() -> list[str]:
    return sorted(p.name for p in LISTS_DIR.glob("*.csv"))


def _available_flags() -> list[str]:
    return sorted(p.stem.upper() for p in FLAGS_DIR.glob("*.svg"))


def _resolve_csv(tmp: Path) -> Path:
    """Take the CSV from the upload, falling back to a bundled one."""
    upload = request.files.get("csv_file")
    if upload and upload.filename:
        dest = tmp / "input.csv"
        upload.save(dest)
        return dest

    name = request.form.get("csv_name", "").strip()
    if not name:
        abort(400, "Pick a bundled CSV or upload one.")
    src = LISTS_DIR / name
    if not src.is_file() or src.resolve().parent != LISTS_DIR.resolve():
        abort(400, "Unknown bundled CSV.")
    return src


def _common_args() -> list[str]:
    affiliation = request.form.get("affiliation", "unknown")
    if affiliation not in AFFILIATIONS:
        abort(400, "Unknown affiliation.")
    args = ["--affiliation", affiliation]

    bg = request.form.get("background", "").strip()
    if bg:
        if not (bg.startswith("#") and len(bg) in (4, 7)):
            abort(400, "Background must be a hex like #002F5F.")
        args += ["--background", bg]

    country = request.form.get("country", "").strip()
    if country:
        if country not in _available_flags():
            abort(400, "Unknown country flag.")
        args += ["--country", country]

    return args


def _zip_dir(directory: Path, patterns: tuple[str, ...]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for pat in patterns:
            for p in sorted(directory.glob(pat)):
                zf.write(p, p.name)
    buf.seek(0)
    return buf


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        abort(500, f"Pipeline failed:\n{proc.stderr or proc.stdout}")


@app.get("/")
def index():
    return render_template(
        "index.html",
        csvs=_available_csvs(),
        flags=_available_flags(),
        affiliations=AFFILIATIONS,
        symbols=COMMON_SYMBOLS,
    )


@app.get("/api/symbols")
def api_symbols():
    """Return SVG icons for all common symbols at the requested affiliation."""
    affiliation = request.args.get("affiliation", "unknown")
    if affiliation not in AFFILIATIONS:
        abort(400, "Unknown affiliation.")
    result = []
    for phrase, desc in COMMON_SYMBOLS:
        svg = get_icon_svg(affiliation, phrase, False)
        result.append({"phrase": phrase, "desc": desc, "svg": svg})
    return jsonify(result)


@app.post("/generate")
def generate():
    action = request.form.get("action", "stickers")
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        csv_path = _resolve_csv(tmp)
        common = _common_args() + ["--csv", str(csv_path)]

        if action == "stickers":
            out_dir = tmp / "out"
            _run(["python", "generator.py", *common, "--out", str(out_dir)], cwd=ROOT)
            data = _zip_dir(out_dir, ("*.svg",))
            return send_file(data, mimetype="application/zip",
                             as_attachment=True, download_name="stickers.zip")

        if action == "sheets":
            out_dir = tmp / "sheets"
            _run(["python", "sheets.py", *common, "--out", str(out_dir)], cwd=ROOT)
            data = _zip_dir(out_dir, ("*.pdf",))
            return send_file(data, mimetype="application/zip",
                             as_attachment=True, download_name="sheets.zip")

        if action == "preview":
            out_dir = tmp / "out"
            preview_path = tmp / "preview.html"
            _run(["python", "generator.py", *common, "--out", str(out_dir)], cwd=ROOT)
            _run(
                ["python", "preview.py", *common,
                 "--out-stickers", str(out_dir), "--out", str(preview_path)],
                cwd=ROOT,
            )
            # Read into memory so the tempdir can be torn down.
            data = io.BytesIO(preview_path.read_bytes())
            return send_file(data, mimetype="text/html",
                             as_attachment=False, download_name="preview.html")

        abort(400, "Unknown action.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
