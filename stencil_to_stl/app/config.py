from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


MAX_PIXEL_COUNT_DEFAULT = 500_000  # ~707×707 px; limits mesh to ~2M triangles worst-case
MM_PER_INCH = 25.4

# Two extrusions of a 0.4 mm nozzle. One is the least an FDM printer can lay down
# at all; two is the least that holds together once the block is inked and pressed.
MIN_FEATURE_WIDTH_MM_DEFAULT = 0.8
CHAMFER_HEIGHT_MM_DEFAULT = 0.5


@dataclass(frozen=True)
class StencilConfig:
    input_file: Path
    output_file: Path
    base_thickness_mm: float = 2.0
    relief_height_mm: float = 1.5
    pixel_to_mm_scale: float = 0.1
    target_width_mm: float | None = None
    target_height_mm: float | None = None
    threshold: int = 128
    mirror_x: bool = True
    max_pixel_count: int = MAX_PIXEL_COUNT_DEFAULT
    min_feature_width_mm: float = MIN_FEATURE_WIDTH_MM_DEFAULT
    chamfer_height_mm: float = CHAMFER_HEIGHT_MM_DEFAULT
    widen_thin_features: bool = True

    @property
    def chamfer_enabled(self) -> bool:
        return self.chamfer_height_mm > 0

    def validate_input(self) -> None:
        if self.input_file.suffix.lower() != ".png":
            raise ValueError("Input file must be a PNG.")
        if self.base_thickness_mm <= 0:
            raise ValueError("Base thickness must be greater than 0.")
        if self.relief_height_mm <= 0:
            raise ValueError("Relief height must be greater than 0.")
        if self.pixel_to_mm_scale <= 0:
            raise ValueError("Scale must be greater than 0.")
        if self.target_width_mm is not None and self.target_width_mm <= 0:
            raise ValueError("Target width must be greater than 0.")
        if self.target_height_mm is not None and self.target_height_mm <= 0:
            raise ValueError("Target height must be greater than 0.")
        if not 0 <= self.threshold <= 255:
            raise ValueError("Threshold must be between 0 and 255.")
        if self.max_pixel_count < 1:
            raise ValueError("max_pixel_count must be at least 1.")
        if self.min_feature_width_mm <= 0:
            raise ValueError("Minimum feature width must be greater than 0.")
        if self.chamfer_height_mm < 0:
            raise ValueError("Chamfer height must not be negative.")
        if self.chamfer_height_mm >= self.relief_height_mm:
            # The chamfer eats its own height out of every valley. Letting it reach
            # the relief height would flood the low areas and leave nothing to ink.
            raise ValueError("Chamfer height must be less than the relief height.")

    def validate(self) -> None:
        self.validate_input()
        if self.output_file.suffix.lower() != ".stl":
            raise ValueError("Output file must use the .stl extension.")
