import pytest
from PIL import Image

from stencil_to_stl.app.web import (
    ConversionJob,
    WEB_AUTO_PIXEL_LIMIT,
    WEB_TARGET_MESH_PIXELS,
    _effective_max_pixels,
    _prepare_mesh_input,
    _resized_dimensions,
    _safe_stem,
)


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


def test_resized_dimensions_keeps_aspect_under_target() -> None:
    width, height = _resized_dimensions(1024, 1536, WEB_TARGET_MESH_PIXELS)

    assert width * height <= WEB_TARGET_MESH_PIXELS + max(width, height)
    assert round(width / height, 2) == round(1024 / 1536, 2)


def test_prepare_mesh_input_downsamples_and_preserves_physical_size(tmp_path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (1024, 1536), color=(0, 0, 0, 255)).save(source, dpi=(200, 200))

    prepared = _prepare_mesh_input(
        source,
        "upload",
        "source",
        fallback_scale_mm=0.1,
        target_width_mm=None,
        target_height_mm=None,
    )

    assert prepared.path != source
    assert prepared.original_pixel_count == 1024 * 1536
    assert prepared.mesh_pixel_count < prepared.original_pixel_count
    assert prepared.target_width_mm == pytest.approx((1024 / 200) * 25.4, abs=0.01)
    assert prepared.target_height_mm == pytest.approx((1536 / 200) * 25.4, abs=0.01)


def test_conversion_job_json_includes_progress_and_elapsed() -> None:
    job = ConversionJob(
        id="job-1",
        status="running",
        stage="Building STL",
        progress=45,
        started_at=100.0,
    )
    job.finished_at = 112.25

    assert job.to_json() == {
        "job_id": "job-1",
        "status": "running",
        "stage": "Building STL",
        "progress": 45,
        "elapsed_seconds": 12.2,
    }
