import numpy as np
import pytest

from stencil_to_stl.app.height_field import build_height_field, remove_saddle_pinches


def _field(mask: np.ndarray, chamfer_height_mm: float = 0.5) -> np.ndarray:
    return build_height_field(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        chamfer_height_mm=chamfer_height_mm,
        x_scale_mm=0.1,
        y_scale_mm=0.1,
    )


def test_raised_cells_keep_the_full_relief_height() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[5:10, 5:10] = True

    field = _field(mask)

    assert field[mask] == pytest.approx(3.5)


def test_chamfer_ramps_down_to_the_base_within_the_chamfer_width() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[:, 7] = True

    field = _field(mask)
    row = field[7]

    assert row[7] == pytest.approx(3.5)
    assert np.all(np.diff(row[7:]) <= 0)  # monotonically falling away from the line
    assert row[13] == pytest.approx(2.0)  # 0.6 mm out, past the 0.5 mm chamfer


def test_chamfer_never_eats_more_than_its_own_height_of_clearance() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[:, 5] = True
    mask[:, 7] = True  # a 0.1 mm valley, far narrower than the 1.0 mm of merging skirt

    field = _field(mask)
    valley = field[7, 6]

    assert valley <= 2.5 + 1e-9
    assert 3.5 - valley >= 1.0 - 1e-9  # relief minus chamfer height of ink clearance


def _saddle_corners(field: np.ndarray) -> int:
    upper_left, upper_right = field[:-1, :-1], field[:-1, 1:]
    lower_left, lower_right = field[1:, :-1], field[1:, 1:]
    main = np.minimum(upper_left, lower_right) > np.maximum(upper_right, lower_left)
    anti = np.minimum(upper_right, lower_left) > np.maximum(upper_left, lower_right)
    return int((main | anti).sum())


def test_removing_saddles_opens_the_pinch_by_adding_material() -> None:
    field = np.array(
        [
            [3.5, 2.0],
            [2.0, 3.5],
        ]
    )

    opened = remove_saddle_pinches(field)

    assert _saddle_corners(opened) == 0
    assert np.all(opened >= field)  # the pinch is relieved by filling, never by cutting


def test_removing_saddles_leaves_a_field_without_pinches_alone() -> None:
    field = np.array(
        [
            [3.5, 3.5, 2.0],
            [3.5, 2.0, 2.0],
            [2.0, 2.0, 2.0],
        ]
    )

    assert remove_saddle_pinches(field).tolist() == field.tolist()


def test_removing_saddles_clears_dense_speckle() -> None:
    rng = np.random.default_rng(0)
    mask = rng.random((30, 30)) < 0.35
    field = build_height_field(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        chamfer_height_mm=0.5,
        x_scale_mm=0.1,
        y_scale_mm=0.1,
    )

    assert _saddle_corners(field) > 0
    assert _saddle_corners(remove_saddle_pinches(field)) == 0


def test_zero_chamfer_height_reproduces_a_plain_two_level_block() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[5:10, 5:10] = True

    field = _field(mask, chamfer_height_mm=0.0)

    assert set(np.unique(field).tolist()) == {2.0, 3.5}
