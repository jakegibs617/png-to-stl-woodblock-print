from pathlib import Path

import numpy as np
from PIL import Image

from stencil_to_stl.app.image_loader import load_png_rgba, png_physical_size_mm


def test_load_png_rgba_converts_to_rgba(tmp_path: Path) -> None:
    path = tmp_path / "input.png"
    Image.new("LA", (2, 1), color=(0, 255)).save(path)

    rgba = load_png_rgba(path)

    assert rgba.shape == (1, 2, 4)
    assert rgba.dtype == np.uint8


def test_png_physical_size_mm_uses_dpi_metadata(tmp_path: Path) -> None:
    path = tmp_path / "input.png"
    Image.new("RGBA", (500, 700), color=(0, 0, 0, 255)).save(path, dpi=(100, 100))

    size_mm = png_physical_size_mm(path)

    assert size_mm is not None
    assert round(size_mm[0], 3) == 127.0
    assert round(size_mm[1], 3) == 177.8


def test_png_physical_size_mm_returns_none_without_dpi(tmp_path: Path) -> None:
    path = tmp_path / "input.png"
    Image.new("RGBA", (2, 1), color=(0, 0, 0, 255)).save(path)

    assert png_physical_size_mm(path) is None
