from __future__ import annotations

import argparse
from pathlib import Path

from stencil_to_stl.app.config import MAX_PIXEL_COUNT_DEFAULT, MM_PER_INCH, StencilConfig
from stencil_to_stl.app.conversion import ConversionMetadata, convert_stencil, preview_conversion


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
    parser.add_argument("--width-in", type=float, help="Target physical width in inches.")
    parser.add_argument("--height-in", type=float, help="Target physical height in inches.")
    parser.add_argument("--threshold", type=int, default=128, help="Black pixel RGB threshold from 0 to 255.")

    mirror_group = parser.add_mutually_exclusive_group()
    mirror_group.add_argument("--mirror", dest="mirror_x", action="store_true", help="Mirror the stencil horizontally.")
    mirror_group.add_argument("--no-mirror", dest="mirror_x", action="store_false", help="Do not mirror the stencil.")
    parser.set_defaults(mirror_x=True)

    parser.add_argument("--preview", action="store_true", help="Print calculated dimensions before exporting.")
    parser.add_argument(
        "--preview-only",
        action="store_true",
        help="Print calculated dimensions without generating an STL.",
    )
    parser.add_argument(
        "--max-pixels",
        type=int,
        default=MAX_PIXEL_COUNT_DEFAULT,
        metavar="N",
        help=f"Maximum total pixel count allowed (default: {MAX_PIXEL_COUNT_DEFAULT:,}).",
    )
    return parser


def print_preview(metadata: ConversionMetadata) -> None:
    print(f"Image size: {metadata.image_width_px} x {metadata.image_height_px} px")
    print(f"Physical size: {metadata.physical_width_mm:g} mm x {metadata.physical_height_mm:g} mm")
    print(f"Base thickness: {metadata.base_thickness_mm:g} mm")
    print(f"Relief height: {metadata.relief_height_mm:g} mm")
    print(f"Total height: {metadata.total_height_mm:g} mm")
    print(f"Raised pixels: {metadata.raised_pixel_count} ({metadata.raised_pixel_percent:.1f}%)")
    print(f"Estimated relief rectangles: {metadata.estimated_relief_rectangles}")
    print(f"Estimated mesh faces: {metadata.estimated_mesh_faces}")
    print(f"Mirrored: {'yes' if metadata.mirrored else 'no'}")
    for warning in metadata.warnings:
        print(f"Warning: {warning}")


def generate(config: StencilConfig, *, preview: bool = False) -> None:
    result = convert_stencil(config)
    if preview:
        print_preview(result.metadata)


def preview(config: StencilConfig) -> None:
    print_preview(preview_conversion(config))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config = StencilConfig(
        input_file=args.input_file,
        output_file=args.output_file,
        base_thickness_mm=args.base_thickness,
        relief_height_mm=args.relief_height,
        pixel_to_mm_scale=args.scale,
        target_width_mm=args.width_in * MM_PER_INCH if args.width_in is not None else None,
        target_height_mm=args.height_in * MM_PER_INCH if args.height_in is not None else None,
        threshold=args.threshold,
        mirror_x=args.mirror_x,
        max_pixel_count=args.max_pixels,
    )

    try:
        if args.preview_only:
            preview(config)
        else:
            generate(config, preview=args.preview)
    except Exception as exc:
        parser.exit(1, f"error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
