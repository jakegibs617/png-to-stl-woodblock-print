from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def _validate_png(image: Image.Image, path: Path, max_pixel_count: int | None) -> None:
    if path.suffix.lower() != ".png":
        raise ValueError("Input file must be a PNG.")
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


def load_png_rgba(path: Path, *, max_pixel_count: int | None = None) -> np.ndarray:
    """Load a PNG image as an RGBA numpy array."""
    with Image.open(path) as image:
        _validate_png(image, path, max_pixel_count)
        rgba = image.convert("RGBA")
        return np.asarray(rgba, dtype=np.uint8)


def png_physical_size_mm(path: Path, *, max_pixel_count: int | None = None) -> tuple[float, float] | None:
    """Return the PNG physical size in millimeters when DPI metadata is present."""
    with Image.open(path) as image:
        _validate_png(image, path, max_pixel_count)
        dpi = image.info.get("dpi")
        if dpi is None:
            return None
        dpi_x, dpi_y = dpi
        if dpi_x <= 0 or dpi_y <= 0:
            return None
        return (image.width / dpi_x) * 25.4, (image.height / dpi_y) * 25.4
