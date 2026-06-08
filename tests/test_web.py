import pytest

from stencil_to_stl.app.web import WEB_AUTO_PIXEL_LIMIT, _effective_max_pixels, _safe_stem


def test_safe_stem_preserves_readable_filename() -> None:
    assert _safe_stem("Father's Day card.png") == "Father-s-Day-card"


def test_safe_stem_falls_back_for_empty_name() -> None:
    assert _safe_stem("///.png") == "png"


def test_effective_max_pixels_auto_raises_for_reasonable_upload() -> None:
    assert _effective_max_pixels(1_572_864, 1_000_000) == 1_572_864


def test_effective_max_pixels_honors_larger_explicit_cap() -> None:
    assert _effective_max_pixels(WEB_AUTO_PIXEL_LIMIT + 1, WEB_AUTO_PIXEL_LIMIT + 1) == WEB_AUTO_PIXEL_LIMIT + 1


def test_effective_max_pixels_blocks_large_upload_without_explicit_cap() -> None:
    with pytest.raises(ValueError, match="automatic local limit"):
        _effective_max_pixels(WEB_AUTO_PIXEL_LIMIT + 1, 1_000_000)
