"""Tiny Flask wrapper around the generator/sheets/preview CLIs.

Each request runs the pipeline in an isolated tempdir and streams the
result back as a download (zip / pdf / html). The repo's `lists/` and
`flags/` directories are read-only inputs.
"""

from __future__ import annotations

import csv
import io
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
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

REQUIRED_COLS = ("designation", "name", "symbol", "width")
OPTIONAL_COLS = ("hq", "formation", "group")
STAGING_DIR = Path(tempfile.gettempdir()) / "6mm-stickers-staging"
STAGING_TTL = 30 * 60  # seconds — uploads expire after half an hour

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD


def _available_csvs() -> list[str]:
    return sorted(p.name for p in LISTS_DIR.glob("*.csv"))


def _available_flags() -> list[str]:
    return sorted(p.stem.upper() for p in FLAGS_DIR.glob("*.svg"))


def _gc_staging() -> None:
    """Best-effort cleanup of staged uploads older than STAGING_TTL."""
    if not STAGING_DIR.is_dir():
        return
    cutoff = time.time() - STAGING_TTL
    for p in STAGING_DIR.glob("*.csv"):
        try:
            if p.stat().st_mtime < cutoff:
                p.unlink()
        except OSError:
            pass


def _stash_upload(upload) -> str:
    STAGING_DIR.mkdir(exist_ok=True)
    _gc_staging()
    token = secrets.token_urlsafe(16)
    (STAGING_DIR / f"{token}.csv").write_bytes(upload.read())
    return token


def _staged_path(token: str) -> Path | None:
    # Guard against path traversal — tokens are urlsafe base64.
    if not token or not token.replace("-", "").replace("_", "").isalnum():
        return None
    p = STAGING_DIR / f"{token}.csv"
    return p if p.is_file() else None


def _resolve_csv() -> tuple[Path, str | None, str | None]:
    """Return (csv path, staged token, display name).

    Resolution order: existing staged token, fresh upload, bundled name.
    The staged token is non-None only when the CSV is in STAGING_DIR
    (i.e. survives across requests for the confirmation flow).
    """
    token = request.form.get("csv_token", "").strip()
    if token:
        p = _staged_path(token)
        if p is None:
            abort(400, "Uploaded CSV expired or not found — please re-upload.")
        return p, token, request.form.get("csv_display") or "upload.csv"

    upload = request.files.get("csv_file")
    if upload and upload.filename:
        token = _stash_upload(upload)
        return STAGING_DIR / f"{token}.csv", token, upload.filename

    name = request.form.get("csv_name", "").strip()
    if not name:
        abort(400, "Pick a bundled CSV or upload one.")
    src = LISTS_DIR / name
    if not src.is_file() or src.resolve().parent != LISTS_DIR.resolve():
        abort(400, "Unknown bundled CSV.")
    return src, None, name


def _validate_csv(path: Path) -> tuple[list[str], list[str], list[dict]]:
    """Return (header_errors, header_warnings, row_issues).

    header_errors: fatal — missing required columns / unreadable file.
    header_warnings: e.g. unrecognized extra columns (informational).
    row_issues: list of {line, designation, problem} dicts for rows the
                generator would silently skip.
    """
    try:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            if not fieldnames:
                return (["CSV is empty or has no header row."], [], [])
            missing = [c for c in REQUIRED_COLS if c not in fieldnames]
            if missing:
                return (
                    [f"CSV is missing required column(s): {', '.join(missing)}. "
                     f"Required columns are: {', '.join(REQUIRED_COLS)}."],
                    [], [],
                )
            known = set(REQUIRED_COLS) | set(OPTIONAL_COLS)
            extras = [c for c in fieldnames if c not in known]
            warnings = (
                [f"Ignored unrecognized column(s): {', '.join(extras)}."]
                if extras else []
            )

            issues: list[dict] = []
            for i, row in enumerate(reader, start=2):  # line 1 = header
                problems = []
                for col in ("designation", "name", "symbol"):
                    if not (row.get(col) or "").strip():
                        problems.append(f"{col} is blank")
                w = (row.get("width") or "").strip()
                if not w:
                    problems.append("width is blank")
                else:
                    try:
                        int(w)
                    except ValueError:
                        problems.append(f"width {w!r} is not an integer")
                if problems:
                    issues.append({
                        "line": i,
                        "designation": (row.get("designation") or "").strip() or "—",
                        "problem": "; ".join(problems),
                    })
            return ([], warnings, issues)
    except UnicodeDecodeError:
        return (["CSV is not valid UTF-8."], [], [])
    except csv.Error as e:
        return ([f"CSV parse error: {e}."], [], [])


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
    if action not in ("stickers", "sheets", "preview"):
        abort(400, "Unknown action.")
    confirm_skip = request.form.get("confirm_skip") == "1"

    csv_path, csv_token, csv_display = _resolve_csv()
    common_extra = _common_args()  # validate affiliation / background / country early

    header_errors, header_warnings, row_issues = _validate_csv(csv_path)
    if header_errors:
        if csv_token:
            (STAGING_DIR / f"{csv_token}.csv").unlink(missing_ok=True)
        abort(400, "\n".join(header_errors))

    if row_issues and not confirm_skip:
        # Make sure the CSV survives until the user confirms. Bundled CSVs
        # already live on disk; uploads have already been staged.
        return render_template(
            "confirm.html",
            issues=row_issues,
            warnings=header_warnings,
            csv_display=csv_display,
            csv_token=csv_token,
            csv_name="" if csv_token else csv_display,
            affiliation=request.form.get("affiliation", "unknown"),
            country=request.form.get("country", ""),
            background=request.form.get("background", ""),
            action=action,
        )

    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = Path(td)
            common = common_extra + ["--csv", str(csv_path)]

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

            # action == "preview"
            out_dir = tmp / "out"
            preview_path = tmp / "preview.html"
            _run(["python", "generator.py", *common, "--out", str(out_dir)], cwd=ROOT)
            _run(
                ["python", "preview.py", *common,
                 "--out-stickers", str(out_dir), "--out", str(preview_path)],
                cwd=ROOT,
            )
            data = io.BytesIO(preview_path.read_bytes())
            return send_file(data, mimetype="text/html",
                             as_attachment=False, download_name="preview.html")
    finally:
        if csv_token:
            (STAGING_DIR / f"{csv_token}.csv").unlink(missing_ok=True)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
