from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from stencil_to_stl.app.cli import generate
from stencil_to_stl.app.config import MAX_PIXEL_COUNT_DEFAULT, StencilConfig
from stencil_to_stl.app.image_loader import load_png_rgba


def _make_png(tmp_path: Path, width: int, height: int) -> Path:
    path = tmp_path / "input.png"
    img = Image.new("RGBA", (width, height), color=(0, 0, 0, 255))
    img.save(path)
    return path


def test_config_rejects_zero_max_pixel_count(tmp_path: Path) -> None:
    config = StencilConfig(
        input_file=tmp_path / "in.png",
        output_file=tmp_path / "out.stl",
        max_pixel_count=0,
    )
    with pytest.raises(ValueError, match="max_pixel_count must be at least 1"):
        config.validate()


def test_config_rejects_negative_max_pixel_count(tmp_path: Path) -> None:
    config = StencilConfig(
        input_file=tmp_path / "in.png",
        output_file=tmp_path / "out.stl",
        max_pixel_count=-1,
    )
    with pytest.raises(ValueError, match="max_pixel_count must be at least 1"):
        config.validate()


def test_generate_rejects_image_above_pixel_limit(tmp_path: Path) -> None:
    png = _make_png(tmp_path, width=5, height=5)
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        max_pixel_count=24,
    )
    with pytest.raises(ValueError, match="exceeds the limit"):
        generate(config)


def test_generate_accepts_image_at_pixel_limit(tmp_path: Path) -> None:
    png = _make_png(tmp_path, width=5, height=5)
    config = StencilConfig(
        input_file=png,
        output_file=tmp_path / "out.stl",
        max_pixel_count=25,
    )
    generate(config)
    assert (tmp_path / "out.stl").exists()


def test_default_max_pixel_count_is_five_hundred_thousand() -> None:
    assert MAX_PIXEL_COUNT_DEFAULT == 500_000


def test_pixel_check_fires_before_rgba_conversion(tmp_path: Path) -> None:
    png = _make_png(tmp_path, width=5, height=5)
    with patch("stencil_to_stl.app.image_loader.Image") as mock_pil:
        mock_image = mock_pil.open.return_value.__enter__.return_value
        mock_image.format = "PNG"
        mock_image.width = 5
        mock_image.height = 5
        mock_image.convert.return_value = None

        with pytest.raises(ValueError, match="exceeds the limit"):
            load_png_rgba(png, max_pixel_count=24)

        mock_image.convert.assert_not_called()


def test_config_default_max_pixel_count() -> None:
    config = StencilConfig(
        input_file=Path("in.png"),
        output_file=Path("out.stl"),
    )
    assert config.max_pixel_count == MAX_PIXEL_COUNT_DEFAULT
