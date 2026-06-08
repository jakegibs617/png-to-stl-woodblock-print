from __future__ import annotations

import json
import math
import re
import tempfile
import uuid
import warnings
from dataclasses import asdict
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

warnings.filterwarnings("ignore", category=DeprecationWarning, message="'cgi' is deprecated.*")

import cgi

from PIL import Image

from stencil_to_stl.app.config import MAX_PIXEL_COUNT_DEFAULT, MM_PER_INCH, StencilConfig
from stencil_to_stl.app.conversion import ConversionMetadata, convert_stencil


HOST = "127.0.0.1"
PORT = 8765
WEB_AUTO_PIXEL_LIMIT = 2_000_000
WEB_TARGET_MESH_PIXELS = 100_000
WORK_DIR = Path(tempfile.mkdtemp(prefix="stencil-to-stl-web-"))
UPLOAD_DIR = WORK_DIR / "uploads"
OUTPUT_DIR = WORK_DIR / "outputs"
DOWNLOADS: dict[str, Path] = {}

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Stencil to STL</title>
  <style>
    :root {
      color-scheme: light;
      --bg: #f7f7f4;
      --ink: #1f2423;
      --muted: #626b67;
      --line: #cfd7d1;
      --panel: #ffffff;
      --accent: #2f6f5e;
      --accent-strong: #214f43;
      --warn: #8a5a19;
      --danger: #a5382a;
      --shadow: 0 10px 30px rgba(31, 36, 35, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--ink);
    }

    main {
      width: min(1280px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0;
    }

    .app {
      display: grid;
      grid-template-columns: minmax(340px, 1.1fr) minmax(280px, 360px) minmax(320px, 0.9fr);
      gap: 16px;
      align-items: stretch;
    }

    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: var(--shadow);
      min-width: 0;
    }

    .panel header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 52px;
      padding: 14px 16px;
      border-bottom: 1px solid var(--line);
    }

    h1, h2 {
      margin: 0;
      font-size: 15px;
      line-height: 1.2;
      font-weight: 700;
      letter-spacing: 0;
    }

    .drop {
      display: grid;
      grid-template-rows: 1fr auto;
      min-height: calc(100vh - 48px);
    }

    .drop-zone {
      margin: 16px;
      min-height: 420px;
      border: 1px dashed #9fb0a8;
      border-radius: 8px;
      display: grid;
      place-items: center;
      overflow: hidden;
      background: #fbfbf9;
      position: relative;
    }

    .drop-zone.has-image {
      border-style: solid;
      background: #efefea;
    }

    .drop-zone input {
      position: absolute;
      inset: 0;
      opacity: 0;
      cursor: pointer;
    }

    .empty {
      display: grid;
      gap: 12px;
      justify-items: center;
      color: var(--muted);
      text-align: center;
      padding: 24px;
    }

    .empty svg {
      width: 42px;
      height: 42px;
      stroke: var(--accent);
      stroke-width: 1.8;
      fill: none;
    }

    #previewImage {
      display: none;
      max-width: 100%;
      max-height: calc(100vh - 160px);
      object-fit: contain;
      image-rendering: auto;
    }

    .file-meta {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 0 16px 16px;
      color: var(--muted);
      font-size: 13px;
      min-height: 34px;
    }

    form {
      padding: 16px;
      display: grid;
      gap: 16px;
    }

    fieldset {
      margin: 0;
      padding: 0;
      border: 0;
      display: grid;
      gap: 10px;
    }

    legend {
      margin: 0 0 2px;
      padding: 0;
      font-size: 12px;
      font-weight: 700;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }

    label {
      display: grid;
      gap: 6px;
      font-size: 13px;
      color: var(--muted);
    }

    input[type="number"] {
      width: 100%;
      height: 36px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
      font: inherit;
      color: var(--ink);
      background: #fff;
    }

    input[type="checkbox"] {
      width: 16px;
      height: 16px;
      accent-color: var(--accent);
    }

    .row {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
    }

    .check {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      min-height: 36px;
      color: var(--ink);
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 0 10px;
    }

    .actions {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    button, .download {
      height: 38px;
      border: 1px solid transparent;
      border-radius: 6px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 8px;
      padding: 0 12px;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      text-decoration: none;
      white-space: nowrap;
    }

    button[type="submit"], .download {
      color: #fff;
      background: var(--accent);
    }

    button[type="submit"]:hover, .download:hover { background: var(--accent-strong); }

    button.secondary {
      color: var(--ink);
      background: #fff;
      border-color: var(--line);
    }

    button:disabled {
      opacity: 0.55;
      cursor: wait;
    }

    .result-body {
      padding: 16px;
      display: grid;
      gap: 14px;
    }

    .status {
      min-height: 38px;
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 10px;
      font-size: 13px;
      color: var(--muted);
      background: #fbfbf9;
    }

    .status.error {
      color: var(--danger);
      border-color: #ddb5ae;
      background: #fff8f7;
    }

    .status.busy {
      color: var(--warn);
      border-color: #e4c890;
      background: #fffaf0;
    }

    dl {
      margin: 0;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px 12px;
      font-size: 13px;
    }

    dt { color: var(--muted); }
    dd { margin: 0; font-variant-numeric: tabular-nums; text-align: right; }

    .warnings {
      display: grid;
      gap: 8px;
      color: var(--warn);
      font-size: 13px;
    }

    .hidden { display: none; }

    @media (max-width: 980px) {
      main { width: min(720px, calc(100vw - 24px)); padding: 12px 0; }
      .app { grid-template-columns: 1fr; }
      .drop { min-height: auto; }
      .drop-zone { min-height: 300px; }
    }
  </style>
</head>
<body>
  <main>
    <div class="app">
      <section class="panel drop">
        <header>
          <h1>Stencil to STL</h1>
          <span id="imageBadge"></span>
        </header>
        <div id="dropZone" class="drop-zone">
          <input id="fileInput" name="image" type="file" accept="image/png">
          <div id="emptyState" class="empty">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M12 3v12"></path>
              <path d="m7 8 5-5 5 5"></path>
              <path d="M5 15v4h14v-4"></path>
            </svg>
            <strong>Choose a PNG stencil</strong>
          </div>
          <img id="previewImage" alt="">
        </div>
        <div class="file-meta">
          <span id="fileName">No file selected</span>
          <span id="fileSize"></span>
        </div>
      </section>

      <section class="panel">
        <header><h2>Settings</h2></header>
        <form id="convertForm">
          <fieldset>
            <legend>Geometry</legend>
            <div class="row">
              <label>Base mm
                <input name="base_thickness" type="number" min="0.1" step="0.1" value="2.0">
              </label>
              <label>Relief mm
                <input name="relief_height" type="number" min="0.1" step="0.1" value="1.5">
              </label>
            </div>
            <label>Fallback mm per pixel
              <input name="scale" type="number" min="0.001" step="0.001" value="0.1">
            </label>
            <div class="row">
              <label>Width in
                <input name="width_in" type="number" min="0.01" step="0.01" placeholder="PNG">
              </label>
              <label>Height in
                <input name="height_in" type="number" min="0.01" step="0.01" placeholder="PNG">
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>Mask</legend>
            <label>Threshold
              <input name="threshold" type="number" min="0" max="255" step="1" value="128">
            </label>
            <label>Safety cap pixels
              <input name="max_pixels" type="number" min="1" step="1" value="1000000">
            </label>
            <label class="check">
              Mirror horizontally
              <input name="mirror" type="checkbox" checked>
            </label>
          </fieldset>

          <div class="actions">
            <button id="generateButton" type="submit">Generate STL</button>
            <button class="secondary" type="button" id="resetButton">Reset</button>
          </div>
        </form>
      </section>

      <section class="panel">
        <header><h2>Output</h2></header>
        <div class="result-body">
          <div id="status" class="status">Ready</div>
          <a id="downloadLink" class="download hidden" href="#">Download STL</a>
          <dl id="metadata" class="hidden"></dl>
          <div id="warnings" class="warnings"></div>
        </div>
      </section>
    </div>
  </main>

  <script>
    const fileInput = document.getElementById('fileInput');
    const dropZone = document.getElementById('dropZone');
    const emptyState = document.getElementById('emptyState');
    const previewImage = document.getElementById('previewImage');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const form = document.getElementById('convertForm');
    const statusBox = document.getElementById('status');
    const metadata = document.getElementById('metadata');
    const warnings = document.getElementById('warnings');
    const downloadLink = document.getElementById('downloadLink');
    const generateButton = document.getElementById('generateButton');
    const resetButton = document.getElementById('resetButton');

    let selectedFile = null;

    function formatBytes(bytes) {
      if (!bytes) return '';
      const units = ['B', 'KB', 'MB', 'GB'];
      let value = bytes;
      let unit = 0;
      while (value >= 1024 && unit < units.length - 1) {
        value /= 1024;
        unit += 1;
      }
      return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`;
    }

    function setStatus(text, mode = '') {
      statusBox.textContent = text;
      statusBox.className = `status ${mode}`.trim();
    }

    function setFile(file) {
      selectedFile = file;
      downloadLink.classList.add('hidden');
      metadata.classList.add('hidden');
      metadata.innerHTML = '';
      warnings.innerHTML = '';
      if (!file) {
        fileName.textContent = 'No file selected';
        fileSize.textContent = '';
        emptyState.style.display = 'grid';
        previewImage.style.display = 'none';
        previewImage.removeAttribute('src');
        dropZone.classList.remove('has-image');
        setStatus('Ready');
        return;
      }
      fileName.textContent = file.name;
      fileSize.textContent = formatBytes(file.size);
      previewImage.src = URL.createObjectURL(file);
      previewImage.style.display = 'block';
      emptyState.style.display = 'none';
      dropZone.classList.add('has-image');
      setStatus('Ready');
    }

    function renderMetadata(data, processing) {
      const rows = [
        ['Image', `${data.image_width_px} x ${data.image_height_px} px`],
        ['Physical', `${data.physical_width_mm.toFixed(3)} x ${data.physical_height_mm.toFixed(3)} mm`],
        ['Height', `${data.total_height_mm.toFixed(3)} mm`],
        ['Raised pixels', `${data.raised_pixel_count} (${data.raised_pixel_percent.toFixed(1)}%)`],
        ['Rectangles', `${data.estimated_relief_rectangles}`],
        ['Faces', `${data.estimated_mesh_faces}`],
        ['Mirrored', data.mirrored ? 'yes' : 'no']
      ];
      if (processing && processing.optimized) {
        rows.splice(1, 0, ['Source pixels', `${processing.original_pixel_count}`]);
      }
      metadata.innerHTML = rows.map(([key, value]) => `<dt>${key}</dt><dd>${value}</dd>`).join('');
      metadata.classList.remove('hidden');
      warnings.innerHTML = (data.warnings || []).map(warning => `<div>${warning}</div>`).join('');
    }

    fileInput.addEventListener('change', () => setFile(fileInput.files[0] || null));
    resetButton.addEventListener('click', () => {
      form.reset();
      fileInput.value = '';
      setFile(null);
    });

    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!selectedFile) {
        setStatus('Choose a PNG first', 'error');
        return;
      }

      const body = new FormData(form);
      body.set('image', selectedFile);
      body.set('mirror', form.elements.mirror.checked ? 'true' : 'false');

      generateButton.disabled = true;
      downloadLink.classList.add('hidden');
      setStatus('Generating STL', 'busy');

      try {
        const response = await fetch('/api/convert', { method: 'POST', body });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Conversion failed');
        renderMetadata(data.metadata, data.processing);
        downloadLink.href = data.download_url;
        downloadLink.download = data.filename;
        downloadLink.classList.remove('hidden');
        setStatus('STL ready');
      } catch (error) {
        setStatus(error.message, 'error');
      } finally {
        generateButton.disabled = false;
      }
    });
  </script>
</body>
</html>
"""


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "stencil"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip(".-")
    return stem or "stencil"


@dataclass(frozen=True)
class WebImageInfo:
    width_px: int
    height_px: int
    dpi: tuple[float, float] | None

    @property
    def pixel_count(self) -> int:
        return self.width_px * self.height_px


@dataclass(frozen=True)
class MeshInput:
    path: Path
    target_width_mm: float | None
    target_height_mm: float | None
    original_pixel_count: int
    mesh_pixel_count: int


def _field_value(form: cgi.FieldStorage, name: str, default: str = "") -> str:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list):
        return default
    value = field.value
    return value if isinstance(value, str) else default


def _float_field(form: cgi.FieldStorage, name: str, default: float | None = None) -> float | None:
    value = _field_value(form, name).strip()
    if not value:
        return default
    return float(value)


def _int_field(form: cgi.FieldStorage, name: str, default: int) -> int:
    value = _field_value(form, name).strip()
    return int(value) if value else default


def _png_info(path: Path) -> WebImageInfo:
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError("Input file must be a PNG.")
        dpi = image.info.get("dpi")
        if dpi is not None and (dpi[0] <= 0 or dpi[1] <= 0):
            dpi = None
        return WebImageInfo(width_px=image.width, height_px=image.height, dpi=dpi)


def _physical_size_mm(info: WebImageInfo, fallback_scale_mm: float) -> tuple[float, float]:
    if info.dpi is not None:
        return (info.width_px / info.dpi[0]) * MM_PER_INCH, (info.height_px / info.dpi[1]) * MM_PER_INCH
    return info.width_px * fallback_scale_mm, info.height_px * fallback_scale_mm


def _effective_max_pixels(pixel_count: int, requested_max_pixels: int) -> int:
    if pixel_count <= requested_max_pixels:
        return requested_max_pixels
    if pixel_count <= WEB_AUTO_PIXEL_LIMIT:
        return pixel_count
    raise ValueError(
        f"Image has {pixel_count:,} pixels, which exceeds the automatic local limit of "
        f"{WEB_AUTO_PIXEL_LIMIT:,}. Enter a larger max-pixels value to generate it anyway."
    )


def _resized_dimensions(width_px: int, height_px: int, target_pixels: int) -> tuple[int, int]:
    if width_px * height_px <= target_pixels:
        return width_px, height_px
    scale = math.sqrt(target_pixels / (width_px * height_px))
    return max(1, round(width_px * scale)), max(1, round(height_px * scale))


def _prepare_mesh_input(
    input_file: Path,
    upload_id: str,
    stem: str,
    fallback_scale_mm: float,
    target_width_mm: float | None,
    target_height_mm: float | None,
) -> MeshInput:
    info = _png_info(input_file)
    original_width_mm, original_height_mm = _physical_size_mm(info, fallback_scale_mm)
    physical_width_mm = target_width_mm or original_width_mm
    physical_height_mm = target_height_mm or original_height_mm
    resized_width, resized_height = _resized_dimensions(info.width_px, info.height_px, WEB_TARGET_MESH_PIXELS)

    if (resized_width, resized_height) == (info.width_px, info.height_px):
        return MeshInput(
            path=input_file,
            target_width_mm=target_width_mm,
            target_height_mm=target_height_mm,
            original_pixel_count=info.pixel_count,
            mesh_pixel_count=info.pixel_count,
        )

    optimized_file = UPLOAD_DIR / f"{upload_id}-{stem}-mesh.png"
    with Image.open(input_file) as image:
        resized = image.convert("RGBA").resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        dpi = (
            resized_width / (physical_width_mm / MM_PER_INCH),
            resized_height / (physical_height_mm / MM_PER_INCH),
        )
        resized.save(optimized_file, format="PNG", dpi=dpi)

    return MeshInput(
        path=optimized_file,
        target_width_mm=physical_width_mm,
        target_height_mm=physical_height_mm,
        original_pixel_count=info.pixel_count,
        mesh_pixel_count=resized_width * resized_height,
    )


def _metadata_json(metadata: ConversionMetadata) -> dict[str, object]:
    return asdict(metadata)


class StencilWebHandler(BaseHTTPRequestHandler):
    server_version = "StencilToSTLWeb/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_html(HTML)
            return
        if parsed.path == "/download":
            self._send_download(parse_qs(parsed.query).get("id", [""])[0])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/convert":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            self._handle_convert()
        except Exception as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)

    def _handle_convert(self) -> None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            raise ValueError("Expected multipart form data.")

        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
                "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
            },
        )
        image_field = form["image"] if "image" in form else None
        if image_field is None or isinstance(image_field, list) or not image_field.filename:
            raise ValueError("PNG upload is required.")

        upload_id = uuid.uuid4().hex
        stem = _safe_stem(image_field.filename)
        input_file = UPLOAD_DIR / f"{upload_id}-{stem}.png"
        output_file = OUTPUT_DIR / f"{upload_id}-{stem}.stl"
        with input_file.open("wb") as handle:
            handle.write(image_field.file.read())

        requested_max_pixels = _int_field(form, "max_pixels", MAX_PIXEL_COUNT_DEFAULT)
        fallback_scale = _float_field(form, "scale", 0.1) or 0.1
        width_in = _float_field(form, "width_in")
        height_in = _float_field(form, "height_in")
        target_width_mm = width_in * MM_PER_INCH if width_in is not None else None
        target_height_mm = height_in * MM_PER_INCH if height_in is not None else None
        mesh_input = _prepare_mesh_input(
            input_file,
            upload_id,
            stem,
            fallback_scale,
            target_width_mm,
            target_height_mm,
        )
        max_pixel_count = _effective_max_pixels(mesh_input.mesh_pixel_count, requested_max_pixels)

        config = StencilConfig(
            input_file=mesh_input.path,
            output_file=output_file,
            base_thickness_mm=_float_field(form, "base_thickness", 2.0) or 2.0,
            relief_height_mm=_float_field(form, "relief_height", 1.5) or 1.5,
            pixel_to_mm_scale=fallback_scale,
            target_width_mm=mesh_input.target_width_mm,
            target_height_mm=mesh_input.target_height_mm,
            threshold=_int_field(form, "threshold", 128),
            mirror_x=_field_value(form, "mirror", "true") == "true",
            max_pixel_count=max_pixel_count,
        )

        result = convert_stencil(config)
        download_id = uuid.uuid4().hex
        DOWNLOADS[download_id] = output_file
        self._send_json(
            {
                "metadata": _metadata_json(result.metadata),
                "download_url": f"/download?id={download_id}",
                "filename": output_file.name.removeprefix(f"{upload_id}-"),
                "processing": {
                    "original_pixel_count": mesh_input.original_pixel_count,
                    "mesh_pixel_count": mesh_input.mesh_pixel_count,
                    "optimized": mesh_input.mesh_pixel_count < mesh_input.original_pixel_count,
                },
            }
        )

    def _send_download(self, download_id: str) -> None:
        path = DOWNLOADS.get(download_id)
        if path is None or not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "model/stl")
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'attachment; filename="{path.name.split("-", 1)[-1]}"')
        self.end_headers()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                self.wfile.write(chunk)

    def _send_html(self, html: str) -> None:
        payload = html.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data: dict[str, object], *, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def run(host: str = HOST, port: int = PORT) -> None:
    server = ThreadingHTTPServer((host, port), StencilWebHandler)
    print(f"Serving Stencil to STL at http://{host}:{port}")
    print(f"Temporary files: {WORK_DIR}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
    finally:
        server.server_close()


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
