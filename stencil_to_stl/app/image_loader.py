from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load_png_rgba(path: Path) -> np.ndarray:
    """Load a PNG image as an RGBA numpy array."""
    if path.suffix.lower() != ".png":
        raise ValueError("Input file must be a PNG.")
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError("Input file must be a PNG.")
        rgba = image.convert("RGBA")
        return np.asarray(rgba, dtype=np.uint8)

