from pathlib import Path
from unittest.mock import patch

from PIL import Image

from stencil_to_stl.app.config import StencilConfig
from stencil_to_stl.app.conversion import convert_stencil, preview_conversion


def _make_png(tmp_path: Path, *, dpi: tuple[int, int] | None = None) -> Path:
    path = tmp_path / "input.png"
    image = Image.new("RGBA", (4, 3), color=(255, 255, 255, 0))
    image.putpixel((0, 0), (0, 0, 0, 255))
    image.putpixel((1, 0), (0, 0, 0, 255))
    image.putpixel((0, 1), (0, 0, 0, 255))
    image.putpixel((1, 1), (0, 0, 0, 255))
    if dpi is None:
        image.save(path)
    else:
        image.save(path, dpi=dpi)
    return path


def test_preview_conversion_returns_structured_metadata_without_export(tmp_path: Path) -> None:
    png = _make_png(tmp_path)
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        pixel_to_mm_scale=0.5,
        mirror_x=False,
        min_feature_width_mm=0.1,  # this fixture is about geometry, not printability
    )

    with patch("stencil_to_stl.app.conversion.export_stl") as export_stl:
        metadata = preview_conversion(config)

    export_stl.assert_not_called()
    assert metadata.image_width_px == 4
    assert metadata.image_height_px == 3
    assert metadata.physical_width_mm == 2.0
    assert metadata.physical_height_mm == 1.5
    assert metadata.raised_pixel_count == 4
    assert metadata.raised_pixel_percent == 100 * (4 / 12)
    assert metadata.estimated_relief_rectangles == 1
    assert metadata.mirrored is False
    assert metadata.warnings == ()


def test_preview_conversion_does_not_require_stl_output_path(tmp_path: Path) -> None:
    png = _make_png(tmp_path)
    config = StencilConfig(input_file=png, output_file=tmp_path / "preview.txt")

    metadata = preview_conversion(config)

    assert metadata.image_width_px == 4


def _make_bar_png(tmp_path: Path, name: str, width_px: int, height_px: int, bar_width_px: int) -> Path:
    path = tmp_path / name
    image = Image.new("RGBA", (width_px, height_px), color=(255, 255, 255, 0))
    left = (width_px - bar_width_px) // 2
    for x in range(left, left + bar_width_px):
        for y in range(2, height_px - 2):
            image.putpixel((x, y), (0, 0, 0, 255))
    image.save(path)
    return path


def test_preview_conversion_omits_thin_line_warning_for_comfortably_wide_art(tmp_path: Path) -> None:
    png = _make_bar_png(tmp_path, "wide.png", 30, 30, 12)  # 1.2 mm bar
    config = StencilConfig(input_file=png, output_file=tmp_path / "out.stl", pixel_to_mm_scale=0.1)

    metadata = preview_conversion(config)

    assert metadata.warnings == ()
    assert metadata.thin_area_percent == 0
    assert metadata.widened_pixel_count == 0
    assert metadata.min_feature_width_mm >= 0.8


def test_preview_conversion_reports_and_widens_a_hairline(tmp_path: Path) -> None:
    png = _make_bar_png(tmp_path, "hairline.png", 30, 30, 2)  # 0.2 mm bar
    config = StencilConfig(input_file=png, output_file=tmp_path / "out.stl", pixel_to_mm_scale=0.1)

    metadata = preview_conversion(config)

    assert metadata.min_feature_width_mm < 0.8
    assert metadata.widened_pixel_count > 0
    assert any("Grew features" in warning for warning in metadata.warnings)


def test_disabling_widening_reports_the_hairline_without_changing_it(tmp_path: Path) -> None:
    png = _make_bar_png(tmp_path, "hairline.png", 30, 30, 2)
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        pixel_to_mm_scale=0.1,
        widen_thin_features=False,
    )

    metadata = preview_conversion(config)

    assert metadata.widened_pixel_count == 0
    assert metadata.raised_pixel_count == 2 * 26
    assert any("may not print" in warning for warning in metadata.warnings)


def test_preview_conversion_uses_target_physical_size(tmp_path: Path) -> None:
    png = _make_png(tmp_path)
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        target_width_mm=127.0,
        target_height_mm=177.8,
        mirror_x=False,
    )

    metadata = preview_conversion(config)

    assert metadata.physical_width_mm == 127.0
    assert metadata.physical_height_mm == 177.8
    assert metadata.warnings == ()


def test_preview_conversion_uses_png_physical_size_when_present(tmp_path: Path) -> None:
    png = _make_png(tmp_path, dpi=(100, 100))
    config = StencilConfig(input_file=png, output_file=tmp_path / "out.stl", mirror_x=False)

    metadata = preview_conversion(config)

    assert round(metadata.physical_width_mm, 3) == 1.016
    assert round(metadata.physical_height_mm, 3) == 0.762


def test_target_size_overrides_png_physical_size(tmp_path: Path) -> None:
    png = _make_png(tmp_path, dpi=(100, 100))
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        target_width_mm=127.0,
        target_height_mm=177.8,
        mirror_x=False,
    )

    metadata = preview_conversion(config)

    assert metadata.physical_width_mm == 127.0
    assert metadata.physical_height_mm == 177.8


def test_convert_stencil_can_return_mesh_without_exporting(tmp_path: Path) -> None:
    png = _make_png(tmp_path)
    config = StencilConfig(input_file=png, output_file=tmp_path / "out.stl")

    result = convert_stencil(config, export=False)

    assert result.mesh is not None
    assert result.mesh.is_watertight
    assert not config.output_file.exists()
