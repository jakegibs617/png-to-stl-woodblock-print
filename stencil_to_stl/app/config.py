from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MAX_PIXEL_COUNT_DEFAULT = 4_000_000  # 2000×2000 px


@dataclass(frozen=True)
class StencilConfig:
    input_file: Path
    output_file: Path
    base_thickness_mm: float = 2.0
    relief_height_mm: float = 1.5
    pixel_to_mm_scale: float = 0.1
    threshold: int = 128
    mirror_x: bool = True
    max_pixel_count: int = MAX_PIXEL_COUNT_DEFAULT

    def validate(self) -> None:
        if self.input_file.suffix.lower() != ".png":
            raise ValueError("Input file must be a PNG.")
        if self.output_file.suffix.lower() != ".stl":
            raise ValueError("Output file must use the .stl extension.")
        if self.base_thickness_mm <= 0:
            raise ValueError("Base thickness must be greater than 0.")
        if self.relief_height_mm <= 0:
            raise ValueError("Relief height must be greater than 0.")
        if self.pixel_to_mm_scale <= 0:
            raise ValueError("Scale must be greater than 0.")
        if not 0 <= self.threshold <= 255:
            raise ValueError("Threshold must be between 0 and 255.")
        if self.max_pixel_count < 1:
            raise ValueError("max_pixel_count must be at least 1.")

