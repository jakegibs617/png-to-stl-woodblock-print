from __future__ import annotations

import argparse
from pathlib import Path

from stencil_to_stl.app.config import MAX_PIXEL_COUNT_DEFAULT, StencilConfig
from stencil_to_stl.app.image_loader import load_png_rgba
from stencil_to_stl.app.mask_processor import black_pixel_mask, mirror_mask_x
from stencil_to_stl.app.mesh_builder import build_relief_mesh, physical_dimensions
from stencil_to_stl.app.stl_exporter import export_stl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stencil-to-stl",
        description="Generate an STL relief block from a black-and-transparent PNG stencil.",
    )
    parser.add_argument("input_file", type=Path)
    parser.add_argument("output_file", type=Path)
    parser.add_argument("--base-thickness", type=float, default=2.0, help="Base thickness in millimeters.")
    parser.add_argument("--relief-height", type=float, default=1.5, help="Raised relief height above the base.")
    parser.add_argument("--scale", type=float, default=0.1, help="Millimeters per source pixel.")
    parser.add_argument("--threshold", type=int, default=128, help="Black pixel RGB threshold from 0 to 255.")

    mirror_group = parser.add_mutually_exclusive_group()
    mirror_group.add_argument("--mirror", dest="mirror_x", action="store_true", help="Mirror the stencil horizontally.")
    mirror_group.add_argument("--no-mirror", dest="mirror_x", action="store_false", help="Do not mirror the stencil.")
    parser.set_defaults(mirror_x=True)

    parser.add_argument("--preview", action="store_true", help="Print calculated dimensions before exporting.")
    parser.add_argument(
        "--max-pixels",
        type=int,
        default=MAX_PIXEL_COUNT_DEFAULT,
        metavar="N",
        help=f"Maximum total pixel count allowed (default: {MAX_PIXEL_COUNT_DEFAULT:,}).",
    )
    return parser


def generate(config: StencilConfig, *, preview: bool = False) -> None:
    config.validate()
    rgba = load_png_rgba(config.input_file, max_pixel_count=config.max_pixel_count)
    mask = black_pixel_mask(rgba, config.threshold)
    if config.mirror_x:
        mask = mirror_mask_x(mask)

    if not mask.any():
        raise ValueError("No black print pixels were detected.")

    width_mm, height_mm = physical_dimensions(mask, config.pixel_to_mm_scale)
    if preview:
        print(f"Image size: {mask.shape[1]} x {mask.shape[0]} px")
        print(f"Physical size: {width_mm:g} mm x {height_mm:g} mm")
        print(f"Base thickness: {config.base_thickness_mm:g} mm")
        print(f"Relief height: {config.relief_height_mm:g} mm")
        print(f"Total height: {config.base_thickness_mm + config.relief_height_mm:g} mm")
        print(f"Mirrored: {'yes' if config.mirror_x else 'no'}")
        print("Warning: very thin raised lines may fail to print or break. Recommended minimum: 0.4-0.8 mm.")

    mesh = build_relief_mesh(
        mask,
        base_thickness_mm=config.base_thickness_mm,
        relief_height_mm=config.relief_height_mm,
        pixel_to_mm_scale=config.pixel_to_mm_scale,
    )
    export_stl(mesh, config.output_file)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = StencilConfig(
        input_file=args.input_file,
        output_file=args.output_file,
        base_thickness_mm=args.base_thickness,
        relief_height_mm=args.relief_height,
        pixel_to_mm_scale=args.scale,
        threshold=args.threshold,
        mirror_x=args.mirror_x,
        max_pixel_count=args.max_pixels,
    )

    try:
        generate(config, preview=args.preview)
    except Exception as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

