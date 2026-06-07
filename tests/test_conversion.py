from pathlib import Path
from unittest.mock import patch

from PIL import Image

from stencil_to_stl.app.config import StencilConfig
from stencil_to_stl.app.conversion import convert_stencil, preview_conversion


def _make_png(tmp_path: Path) -> Path:
    path = tmp_path / "input.png"
    image = Image.new("RGBA", (4, 3), color=(255, 255, 255, 0))
    image.putpixel((0, 0), (0, 0, 0, 255))
    image.putpixel((1, 0), (0, 0, 0, 255))
    image.putpixel((0, 1), (0, 0, 0, 255))
    image.putpixel((1, 1), (0, 0, 0, 255))
    image.save(path)
    return path


def test_preview_conversion_returns_structured_metadata_without_export(tmp_path: Path) -> None:
    png = _make_png(tmp_path)
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        pixel_to_mm_scale=0.5,
        mirror_x=False,
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
    assert metadata.estimated_mesh_faces == 24
    assert metadata.mirrored is False


def test_convert_stencil_can_return_mesh_without_exporting(tmp_path: Path) -> None:
    png = _make_png(tmp_path)
    config = StencilConfig(input_file=png, output_file=tmp_path / "out.stl")

    result = convert_stencil(config, export=False)

    assert result.mesh is not None
    assert result.mesh.is_watertight
    assert not config.output_file.exists()
