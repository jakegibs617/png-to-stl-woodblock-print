import re
from decimal import Decimal
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from stencil_to_stl.app.web import (
    ConversionJob,
    HTML,
    WEB_AUTO_PIXEL_LIMIT,
    WEB_TARGET_MESH_PIXELS,
    _checkbox_field,
    _effective_max_pixels,
    _prepare_mesh_input,
    _resized_dimensions,
    _safe_stem,
)


def test_safe_stem_preserves_readable_filename() -> None:
    assert _safe_stem("Father's Day card.png") == "Father-s-Day-card"


def test_web_ui_uses_inches_for_width_height_and_mm_for_thickness() -> None:
    assert "Width inches" in HTML
    assert "Height inches" in HTML
    assert "Base mm" in HTML
    assert "Relief mm" in HTML
    assert "Thickness" in HTML


def test_every_number_input_default_satisfies_its_own_min_and_step() -> None:
    """A default the browser rejects blocks the whole form, silently and invisibly.

    HTML5 only accepts values reachable as min + n * step, so a field carrying
    min="0.01" step="0.05" value="0.8" fails validation and stops submission with
    no error anywhere in the page or the server log.
    """
    offenders = []
    for tag in re.findall(r"<input[^>]*type=\"number\"[^>]*>", HTML):
        attrs = dict(re.findall(r'(\w[\w-]*)="([^"]*)"', tag))
        if "step" not in attrs or attrs["step"] == "any" or "value" not in attrs:
            continue
        minimum = Decimal(attrs.get("min", "0"))
        step = Decimal(attrs["step"])
        offset = Decimal(attrs["value"]) - minimum
        if step > 0 and offset % step != 0:
            offenders.append((attrs.get("name"), attrs.get("min"), attrs["step"], attrs["value"]))

    assert offenders == []


class _StubForm:
    def __init__(self, values: dict) -> None:
        self._values = {k: SimpleNamespace(value=v) for k, v in values.items()}

    def __contains__(self, name: str) -> bool:
        return name in self._values

    def __getitem__(self, name: str):
        return self._values[name]


def test_checkbox_reads_the_value_a_browser_actually_submits() -> None:
    # A ticked box submits "on", not "true".
    assert _checkbox_field(_StubForm({"widen": "on"}), "widen", default=False) is True
    assert _checkbox_field(_StubForm({"widen": "true"}), "widen", default=False) is True


def test_checkbox_honors_an_explicit_clear_rather_than_falling_back_to_the_default() -> None:
    assert _checkbox_field(_StubForm({"widen": "false"}), "widen", default=True) is False
    assert _checkbox_field(_StubForm({"widen": "off"}), "widen", default=True) is False


def test_checkbox_falls_back_only_when_the_field_is_absent() -> None:
    assert _checkbox_field(_StubForm({}), "widen", default=True) is True
    assert _checkbox_field(_StubForm({}), "widen", default=False) is False


def test_submit_handler_sends_both_checkbox_states_explicitly() -> None:
    # Absence is ambiguous over the wire, so the page must state each one.
    assert "body.set('mirror', form.elements.mirror.checked ? 'true' : 'false')" in HTML
    assert "body.set('widen', form.elements.widen.checked ? 'true' : 'false')" in HTML


def test_thin_line_support_controls_are_exposed_in_the_ui() -> None:
    assert "Thin line support" in HTML
    assert 'name="min_feature_width"' in HTML
    assert 'name="chamfer_height"' in HTML
    assert 'name="widen"' in HTML


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
        threshold=128,
    )

    assert prepared.path != source
    assert prepared.original_pixel_count == 1024 * 1536
    assert prepared.mesh_pixel_count < prepared.original_pixel_count
    assert prepared.target_width_mm == pytest.approx((1024 / 200) * 25.4, abs=0.01)
    assert prepared.target_height_mm == pytest.approx((1536 / 200) * 25.4, abs=0.01)


def _hairline_png(path, background) -> None:
    image = Image.new("RGBA", (1600, 1600), color=background)
    for x in range(40, 1560, 80):
        for y in range(1600):
            image.putpixel((x, y), (0, 0, 0, 255))  # 19 single-pixel vertical lines
    image.save(path, dpi=(300, 300))


def _downsampled_ink_columns(tmp_path, background) -> tuple[int, int]:
    source = tmp_path / "hairlines.png"
    _hairline_png(source, background)

    prepared = _prepare_mesh_input(
        source,
        "upload",
        "hairlines",
        fallback_scale_mm=0.1,
        target_width_mm=None,
        target_height_mm=None,
        threshold=128,
    )

    mask = np.array(Image.open(prepared.path).convert("RGBA"))[:, :, 3] > 0
    return int(mask.any(axis=0).sum()), prepared.mesh_pixel_count


def test_downsampling_keeps_hairlines_drawn_on_an_opaque_background(tmp_path) -> None:
    # Blurring first and thresholding after wipes these out entirely: interpolation
    # pulls each line toward the white behind it until nothing is under the threshold.
    columns, mesh_pixels = _downsampled_ink_columns(tmp_path, (255, 255, 255, 255))

    assert mesh_pixels < 1600 * 1600
    assert columns == 19


def test_downsampling_does_not_smear_hairlines_on_a_transparent_background(tmp_path) -> None:
    # Here blurring keeps the lines but rings them out across several pixels each,
    # thickening the artwork. Thresholding first reproduces them exactly.
    columns, _ = _downsampled_ink_columns(tmp_path, (255, 255, 255, 0))

    assert columns == 19


def test_downsampling_thresholds_before_it_shrinks(tmp_path) -> None:
    source = tmp_path / "grey.png"
    # Mid grey is above the threshold, so nothing here is ink at any resolution.
    Image.new("RGBA", (1024, 1536), color=(160, 160, 160, 255)).save(source, dpi=(200, 200))

    prepared = _prepare_mesh_input(
        source,
        "upload",
        "grey",
        fallback_scale_mm=0.1,
        target_width_mm=None,
        target_height_mm=None,
        threshold=128,
    )

    mask = np.array(Image.open(prepared.path).convert("RGBA"))[:, :, 3] > 0

    assert not mask.any()


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
