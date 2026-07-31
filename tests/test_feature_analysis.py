import numpy as np
import pytest

from stencil_to_stl.app.feature_analysis import (
    measure_features,
    narrowest_feature_mm,
    thin_feature_mask,
    widen_thin_features,
)


def test_single_pixel_line_is_thinner_than_the_minimum() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[:, 4] = True

    thin = thin_feature_mask(mask, min_width_mm=0.8, x_scale_mm=0.1, y_scale_mm=0.1)

    assert thin.tolist() == mask.tolist()


def test_bar_wider_than_the_minimum_is_not_thin() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[:, 2:7] = True

    thin = thin_feature_mask(mask, min_width_mm=0.8, x_scale_mm=0.2, y_scale_mm=0.2)

    assert not thin.any()


def test_thick_blob_rim_is_not_reported_thin() -> None:
    mask = np.zeros((24, 24), dtype=bool)
    mask[2:22, 2:22] = True

    thin = thin_feature_mask(mask, min_width_mm=0.5, x_scale_mm=0.1, y_scale_mm=0.1)

    assert not thin.any()


def test_sharp_corners_of_a_wide_shape_are_not_reported_thin() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[:, 2:7] = True  # 1.0 mm wide, running off both ends of the block

    thin = thin_feature_mask(mask, min_width_mm=0.8, x_scale_mm=0.2, y_scale_mm=0.2)

    assert not thin.any()


def test_a_feature_running_off_the_block_edge_is_measured_at_its_true_width() -> None:
    mask = np.zeros((40, 40), dtype=bool)
    mask[:, 0:4] = True  # a 0.4 mm band hugging the left edge

    report = measure_features(mask, min_width_mm=0.8, x_scale_mm=0.1, y_scale_mm=0.1)

    assert report.min_width_mm == pytest.approx(0.3)
    assert report.thin_area_fraction == 1.0


def test_measure_reports_the_width_of_the_narrowest_line() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[:, 2:7] = True

    report = measure_features(mask, min_width_mm=0.8, x_scale_mm=0.1, y_scale_mm=0.1)

    assert report.min_width_mm == pytest.approx(0.5)


def test_measure_ignores_tapering_tips_when_reporting_width() -> None:
    mask = np.zeros((9, 9), dtype=bool)
    mask[:, 2:7] = True
    mask[0, 2:7] = False
    mask[0, 4] = True  # a one-pixel tip tapering off the end of a 5-pixel bar

    report = measure_features(mask, min_width_mm=0.8, x_scale_mm=0.1, y_scale_mm=0.1)

    assert report.min_width_mm == pytest.approx(0.5)


def test_measure_reports_thin_area_and_component_count() -> None:
    mask = np.zeros((9, 20), dtype=bool)
    mask[:, 2:7] = True  # 0.5 mm bar, below the minimum
    mask[:, 12:19] = True  # 0.7 mm bar, at the minimum

    report = measure_features(mask, min_width_mm=0.7, x_scale_mm=0.1, y_scale_mm=0.1)

    assert report.component_count == 2
    assert report.thin_pixel_count == 45
    assert report.thin_area_fraction == 45 / 108


def test_widening_grows_a_hairline_up_to_the_minimum_width() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[:, 7] = True  # 0.1 mm hairline

    widened, report = widen_thin_features(mask, min_width_mm=0.5, x_scale_mm=0.1, y_scale_mm=0.1)

    assert narrowest_feature_mm(widened, x_scale_mm=0.1, y_scale_mm=0.1) >= 0.5
    assert report.pixels_added > 0


def test_widening_leaves_shapes_already_wide_enough_untouched() -> None:
    mask = np.zeros((24, 24), dtype=bool)
    mask[2:22, 2:22] = True

    widened, report = widen_thin_features(mask, min_width_mm=0.5, x_scale_mm=0.1, y_scale_mm=0.1)

    assert widened.tolist() == mask.tolist()
    assert report.pixels_added == 0


def test_widening_reports_when_it_merges_neighbouring_features() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[:, 5] = True
    mask[:, 8] = True  # two hairlines separated by a 0.2 mm gap

    _, report = widen_thin_features(mask, min_width_mm=0.5, x_scale_mm=0.1, y_scale_mm=0.1)

    assert report.component_count_before == 2
    assert report.component_count_after == 1
