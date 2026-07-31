import numpy as np
import pytest

from stencil_to_stl.app.height_field import build_height_field
from stencil_to_stl.app.mask_processor import horizontal_runs
from stencil_to_stl.app.mesh_builder import (
    build_relief_mesh,
    estimate_mesh_faces,
    merged_run_rectangles,
    physical_dimensions,
)


def _two_level_field(mask: np.ndarray, base: float = 2.0, relief: float = 1.5) -> np.ndarray:
    field = np.full(mask.shape, base, dtype=float)
    field[mask] = base + relief
    return field


def test_build_relief_mesh_has_base_and_consistent_total_height() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[4:6, 4:6] = True

    mesh = build_relief_mesh(_two_level_field(mask), pixel_to_mm_scale=0.1)

    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.bounds[0].tolist() == [0.0, 0.0, 0.0]
    assert mesh.bounds[1].tolist() == [1.0, 1.0, 3.5]
    assert len(horizontal_runs(mask)) == 2


def test_physical_dimensions_uses_width_then_height() -> None:
    mask = np.zeros((20, 10), dtype=bool)

    assert physical_dimensions(mask, 0.1) == (1.0, 2.0)


def test_physical_dimensions_accepts_separate_x_y_scales() -> None:
    mask = np.zeros((20, 10), dtype=bool)

    assert physical_dimensions(mask, (12.7, 8.89)) == (127.0, 177.8)


def test_build_relief_mesh_accepts_separate_x_y_scales() -> None:
    mask = np.ones((2, 2), dtype=bool)

    mesh = build_relief_mesh(_two_level_field(mask), pixel_to_mm_scale=(63.5, 88.9))

    assert mesh.bounds[1].tolist() == [127.0, 177.8, 3.5]


def test_large_solid_mask_stays_watertight() -> None:
    mask = np.ones((1000, 1000), dtype=bool)

    mesh = build_relief_mesh(_two_level_field(mask), pixel_to_mm_scale=0.1)

    assert len(horizontal_runs(mask)) == 1000
    assert len(merged_run_rectangles(mask)) == 1
    assert mesh.is_watertight


def test_relief_touching_plate_boundary_is_watertight() -> None:
    mask = np.zeros((4, 4), dtype=bool)
    mask[0, :] = True

    mesh = build_relief_mesh(_two_level_field(mask), pixel_to_mm_scale=0.1)

    assert mesh.is_watertight


def test_chamfered_field_is_watertight_and_keeps_the_relief_height() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[:, 7] = True
    field = build_height_field(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        chamfer_height_mm=0.5,
        x_scale_mm=0.1,
        y_scale_mm=0.1,
    )

    mesh = build_relief_mesh(field, pixel_to_mm_scale=0.1)

    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.bounds[1][2] == 3.5


def test_chamfer_adds_material_at_the_root_of_a_thin_line() -> None:
    mask = np.zeros((15, 15), dtype=bool)
    mask[:, 7] = True
    kwargs = dict(base_thickness_mm=2.0, relief_height_mm=1.5, x_scale_mm=0.1, y_scale_mm=0.1)

    square = build_relief_mesh(build_height_field(mask, chamfer_height_mm=0.0, **kwargs), pixel_to_mm_scale=0.1)
    chamfered = build_relief_mesh(build_height_field(mask, chamfer_height_mm=0.5, **kwargs), pixel_to_mm_scale=0.1)

    assert chamfered.volume > square.volume


def test_crossing_features_close_where_four_heights_meet() -> None:
    mask = np.zeros((60, 60), dtype=bool)
    mask[:, 30] = True
    mask[10:20, 10:50] = True
    field = build_height_field(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        chamfer_height_mm=0.5,
        x_scale_mm=0.1,
        y_scale_mm=0.1,
    )

    mesh = build_relief_mesh(field, pixel_to_mm_scale=0.1)

    assert mesh.is_watertight
    assert mesh.is_volume
    assert mesh.volume == pytest.approx(float(field.sum()) * 0.01)


def test_speckled_artwork_full_of_diagonal_pinches_still_closes() -> None:
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

    mesh = build_relief_mesh(field, pixel_to_mm_scale=0.1)

    assert mesh.is_watertight
    assert mesh.is_volume


def test_single_row_and_single_cell_fields_still_close() -> None:
    for shape in ((1, 1), (1, 8), (8, 1)):
        mesh = build_relief_mesh(np.full(shape, 2.0), pixel_to_mm_scale=0.1)

        assert mesh.is_watertight, shape
        assert mesh.volume == pytest.approx(shape[0] * shape[1] * 2.0 * 0.01)


def test_estimate_mesh_faces_matches_the_builder() -> None:
    mask = np.array([[True, False], [False, False]], dtype=bool)
    field = _two_level_field(mask)

    mesh = build_relief_mesh(field, pixel_to_mm_scale=0.1)

    assert estimate_mesh_faces(field) == len(mesh.faces)


def test_builder_emits_far_fewer_faces_than_four_per_cell() -> None:
    mask = np.ones((40, 40), dtype=bool)

    mesh = build_relief_mesh(_two_level_field(mask), pixel_to_mm_scale=0.1)

    assert len(mesh.faces) < 4 * mask.size / 2 + 8 * (40 + 40)


def test_sparse_mask_merges_only_matching_adjacent_runs() -> None:
    mask = np.array(
        [
            [True, True, False, True],
            [True, True, False, False],
            [False, True, True, False],
        ],
        dtype=bool,
    )

    assert merged_run_rectangles(mask) == [
        (0, 1, 0, 1),
        (0, 0, 3, 3),
        (2, 2, 1, 2),
    ]
