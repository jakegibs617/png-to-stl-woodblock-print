from stencil_to_stl.app.web import _safe_stem


def test_safe_stem_preserves_readable_filename() -> None:
    assert _safe_stem("Father's Day card.png") == "Father-s-Day-card"


def test_safe_stem_falls_back_for_empty_name() -> None:
    assert _safe_stem("///.png") == "png"
