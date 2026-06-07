from pathlib import Path

import numpy as np
from PIL import Image

from stencil_to_stl.app.image_loader import load_png_rgba


def test_load_png_rgba_converts_to_rgba(tmp_path: Path) -> None:
    path = tmp_path / "input.png"
    Image.new("LA", (2, 1), color=(0, 255)).save(path)

    rgba = load_png_rgba(path)

    assert rgba.shape == (1, 2, 4)
    assert rgba.dtype == np.uint8

