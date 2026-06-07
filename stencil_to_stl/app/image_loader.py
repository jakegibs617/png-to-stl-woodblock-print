from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def load_png_rgba(path: Path, *, max_pixel_count: int | None = None) -> np.ndarray:
    """Load a PNG image as an RGBA numpy array."""
    if path.suffix.lower() != ".png":
        raise ValueError("Input file must be a PNG.")
    with Image.open(path) as image:
        if image.format != "PNG":
            raise ValueError("Input file must be a PNG.")
        if max_pixel_count is not None:
            pixel_count = image.width * image.height
            if pixel_count > max_pixel_count:
                raise ValueError(
                    f"Image has {pixel_count:,} pixels ({image.width}×{image.height}), "
                    f"which exceeds the limit of {max_pixel_count:,}. "
                    f"Use --max-pixels to raise the limit or reduce the image dimensions."
                )
        rgba = image.convert("RGBA")
        return np.asarray(rgba, dtype=np.uint8)

