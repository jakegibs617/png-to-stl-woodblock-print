from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from stencil_to_stl.app.config import StencilConfig
from stencil_to_stl.app.image_loader import load_png_rgba
from stencil_to_stl.app.mask_processor import black_pixel_mask, fill_diagonal_contacts, horizontal_runs, mirror_mask_x
from stencil_to_stl.app.mesh_builder import (
    Rectangle,
    build_relief_mesh,
    estimate_mesh_faces,
    merged_run_rectangles,
    physical_dimensions,
)
from stencil_to_stl.app.stl_exporter import export_stl


@dataclass(frozen=True)
class ConversionMetadata:
    image_width_px: int
    image_height_px: int
    physical_width_mm: float
    physical_height_mm: float
    base_thickness_mm: float
    relief_height_mm: float
    total_height_mm: float
    raised_pixel_count: int
    raised_pixel_percent: float
    estimated_relief_rectangles: int
    estimated_mesh_faces: int
    mirrored: bool
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ConversionResult:
    metadata: ConversionMetadata
    mesh: trimesh.Trimesh | None = None


def _load_mask(config: StencilConfig) -> np.ndarray:
    rgba = load_png_rgba(config.input_file, max_pixel_count=config.max_pixel_count)
    mask = black_pixel_mask(rgba, config.threshold)
    if config.mirror_x:
        mask = mirror_mask_x(mask)
    mask = fill_diagonal_contacts(mask)
    if not mask.any():
        raise ValueError("No black print pixels were detected.")
    return mask


def _warnings_for_mask(mask: np.ndarray, config: StencilConfig) -> tuple[str, ...]:
    runs = horizontal_runs(mask)
    if not runs:
        return ()
    x_scale, _ = _pixel_scales_for_mask(mask, config)
    min_width_mm = min(run.width_px for run in runs) * x_scale
    if min_width_mm < 0.8:
        return ("Very thin raised lines may fail to print or break. Recommended minimum: 0.4-0.8 mm.",)
    return ()


def _pixel_scales_for_mask(mask: np.ndarray, config: StencilConfig) -> tuple[float, float]:
    height_px, width_px = mask.shape
    x_scale = config.target_width_mm / width_px if config.target_width_mm is not None else config.pixel_to_mm_scale
    y_scale = config.target_height_mm / height_px if config.target_height_mm is not None else config.pixel_to_mm_scale
    return x_scale, y_scale


def _metadata_for_mask(
    mask: np.ndarray,
    config: StencilConfig,
    relief_rectangles: list[Rectangle],
) -> ConversionMetadata:
    pixel_scales = _pixel_scales_for_mask(mask, config)
    width_mm, height_mm = physical_dimensions(mask, pixel_scales)
    raised_pixel_count = int(mask.sum())
    total_pixels = int(mask.size)
    relief_rectangle_count = len(relief_rectangles)
    estimated_faces = estimate_mesh_faces(mask)
    warnings = _warnings_for_mask(mask, config)

    return ConversionMetadata(
        image_width_px=int(mask.shape[1]),
        image_height_px=int(mask.shape[0]),
        physical_width_mm=width_mm,
        physical_height_mm=height_mm,
        base_thickness_mm=config.base_thickness_mm,
        relief_height_mm=config.relief_height_mm,
        total_height_mm=config.base_thickness_mm + config.relief_height_mm,
        raised_pixel_count=raised_pixel_count,
        raised_pixel_percent=(raised_pixel_count / total_pixels) * 100,
        estimated_relief_rectangles=relief_rectangle_count,
        estimated_mesh_faces=estimated_faces,
        mirrored=config.mirror_x,
        warnings=warnings,
    )


def preview_conversion(config: StencilConfig) -> ConversionMetadata:
    config.validate_input()
    mask = _load_mask(config)
    relief_rectangles = merged_run_rectangles(mask)
    return _metadata_for_mask(mask, config, relief_rectangles)


def convert_stencil(config: StencilConfig, *, export: bool = True) -> ConversionResult:
    config.validate()
    mask = _load_mask(config)
    relief_rectangles = merged_run_rectangles(mask)
    metadata = _metadata_for_mask(mask, config, relief_rectangles)
    mesh = build_relief_mesh(
        mask,
        base_thickness_mm=config.base_thickness_mm,
        relief_height_mm=config.relief_height_mm,
        pixel_to_mm_scale=_pixel_scales_for_mask(mask, config),
        relief_rectangles=relief_rectangles,
    )
    if export:
        export_stl(mesh, config.output_file)
    return ConversionResult(metadata=metadata, mesh=mesh)
