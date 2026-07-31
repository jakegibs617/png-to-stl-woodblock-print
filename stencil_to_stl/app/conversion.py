from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from stencil_to_stl.app.config import StencilConfig
from stencil_to_stl.app.feature_analysis import measure_features, widen_thin_features
from stencil_to_stl.app.height_field import build_height_field
from stencil_to_stl.app.image_loader import load_png_rgba, png_physical_size_mm
from stencil_to_stl.app.mask_processor import black_pixel_mask, fill_diagonal_contacts, mirror_mask_x
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
    min_feature_width_mm: float
    thin_area_percent: float
    widened_pixel_count: int
    merged_feature_count: int
    chamfer_height_mm: float
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class LoadedMask:
    mask: np.ndarray
    png_physical_size_mm: tuple[float, float] | None


@dataclass(frozen=True)
class ConversionResult:
    metadata: ConversionMetadata
    mesh: trimesh.Trimesh | None = None


def _load_mask(config: StencilConfig) -> LoadedMask:
    rgba = load_png_rgba(config.input_file, max_pixel_count=config.max_pixel_count)
    physical_size_mm = png_physical_size_mm(config.input_file, max_pixel_count=config.max_pixel_count)
    mask = black_pixel_mask(rgba, config.threshold)
    if config.mirror_x:
        mask = mirror_mask_x(mask)
    mask = fill_diagonal_contacts(mask)
    if not mask.any():
        raise ValueError("No black print pixels were detected.")
    return LoadedMask(mask=mask, png_physical_size_mm=physical_size_mm)


@dataclass(frozen=True)
class SupportedMask:
    """A mask made printable, plus what had to change to get it there."""

    mask: np.ndarray
    min_feature_width_mm: float
    thin_area_fraction: float
    widened_pixel_count: int
    merged_feature_count: int
    warnings: tuple[str, ...]


def _apply_thin_line_support(
    mask: np.ndarray,
    config: StencilConfig,
    png_physical_size_mm: tuple[float, float] | None,
) -> SupportedMask:
    """Measure thin features and grow the ones too narrow to print.

    Measured before any widening, so the reported width describes the artwork as
    supplied rather than the version this step produced.
    """
    x_scale, y_scale = _pixel_scales_for_mask(mask, config, png_physical_size_mm)
    scales = {"x_scale_mm": x_scale, "y_scale_mm": y_scale}
    report = measure_features(mask, min_width_mm=config.min_feature_width_mm, **scales)

    warnings: list[str] = []
    widened_pixels = 0
    merged = 0

    if report.thin_pixel_count and config.widen_thin_features:
        mask, widening = widen_thin_features(mask, min_width_mm=config.min_feature_width_mm, **scales)
        widened_pixels = widening.pixels_added
        merged = widening.merged_features

    if widened_pixels:
        warnings.append(
            f"Grew features narrower than {config.min_feature_width_mm:g} mm so they can print "
            f"({widened_pixels:,} pixels added). Narrowest feature was {report.min_width_mm:.2f} mm."
        )
        if merged:
            warnings.append(
                f"Widening closed narrow gaps and merged {merged} separate feature(s). "
                "Check fine detail, or rerun with --no-widen to keep them apart."
            )
    elif report.thin_pixel_count:
        # Either widening is switched off, or it had no room to grow into.
        warnings.append(
            f"{report.thin_area_fraction * 100:.1f}% of the raised area is narrower than "
            f"{config.min_feature_width_mm:g} mm and may not print. Narrowest feature is "
            f"{report.min_width_mm:.2f} mm."
        )

    if not config.chamfer_enabled:
        warnings.append("Chamfer disabled: raised features meet the base plate at a square corner.")

    return SupportedMask(
        mask=mask,
        min_feature_width_mm=report.min_width_mm,
        thin_area_fraction=report.thin_area_fraction,
        widened_pixel_count=widened_pixels,
        merged_feature_count=merged,
        warnings=tuple(warnings),
    )


def _height_field_for(
    mask: np.ndarray,
    config: StencilConfig,
    png_physical_size_mm: tuple[float, float] | None,
) -> np.ndarray:
    x_scale, y_scale = _pixel_scales_for_mask(mask, config, png_physical_size_mm)
    return build_height_field(
        mask,
        base_thickness_mm=config.base_thickness_mm,
        relief_height_mm=config.relief_height_mm,
        chamfer_height_mm=config.chamfer_height_mm,
        x_scale_mm=x_scale,
        y_scale_mm=y_scale,
    )


def _pixel_scales_for_mask(
    mask: np.ndarray,
    config: StencilConfig,
    png_physical_size_mm: tuple[float, float] | None,
) -> tuple[float, float]:
    height_px, width_px = mask.shape
    fallback_width_mm = png_physical_size_mm[0] if png_physical_size_mm is not None else None
    fallback_height_mm = png_physical_size_mm[1] if png_physical_size_mm is not None else None
    x_scale = (
        config.target_width_mm or fallback_width_mm
    ) / width_px if config.target_width_mm is not None or fallback_width_mm is not None else config.pixel_to_mm_scale
    y_scale = (
        config.target_height_mm or fallback_height_mm
    ) / height_px if config.target_height_mm is not None or fallback_height_mm is not None else config.pixel_to_mm_scale
    return x_scale, y_scale


def _metadata_for_mask(
    mask: np.ndarray,
    config: StencilConfig,
    supported: SupportedMask,
    height_field: np.ndarray,
    relief_rectangles: list[Rectangle],
    png_physical_size_mm: tuple[float, float] | None,
) -> ConversionMetadata:
    pixel_scales = _pixel_scales_for_mask(mask, config, png_physical_size_mm)
    width_mm, height_mm = physical_dimensions(mask, pixel_scales)
    raised_pixel_count = int(mask.sum())
    total_pixels = int(mask.size)

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
        estimated_relief_rectangles=len(relief_rectangles),
        estimated_mesh_faces=estimate_mesh_faces(height_field),
        mirrored=config.mirror_x,
        min_feature_width_mm=supported.min_feature_width_mm,
        thin_area_percent=supported.thin_area_fraction * 100,
        widened_pixel_count=supported.widened_pixel_count,
        merged_feature_count=supported.merged_feature_count,
        chamfer_height_mm=config.chamfer_height_mm,
        warnings=supported.warnings,
    )


def _prepare(config: StencilConfig) -> tuple[np.ndarray, np.ndarray, ConversionMetadata]:
    """Load the artwork, make it printable, and build the block's height field."""
    loaded = _load_mask(config)
    supported = _apply_thin_line_support(loaded.mask, config, loaded.png_physical_size_mm)
    mask = supported.mask
    height_field = _height_field_for(mask, config, loaded.png_physical_size_mm)
    metadata = _metadata_for_mask(
        mask,
        config,
        supported,
        height_field,
        merged_run_rectangles(mask),
        loaded.png_physical_size_mm,
    )
    scales = _pixel_scales_for_mask(mask, config, loaded.png_physical_size_mm)
    return height_field, np.array(scales), metadata


def preview_conversion(config: StencilConfig) -> ConversionMetadata:
    config.validate_input()
    _, _, metadata = _prepare(config)
    return metadata


def convert_stencil(config: StencilConfig, *, export: bool = True) -> ConversionResult:
    config.validate()
    height_field, scales, metadata = _prepare(config)
    mesh = build_relief_mesh(height_field, pixel_to_mm_scale=(float(scales[0]), float(scales[1])))
    if export:
        export_stl(mesh, config.output_file)
    return ConversionResult(metadata=metadata, mesh=mesh)
