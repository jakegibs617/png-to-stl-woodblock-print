import numpy as np

from stencil_to_stl.app.mask_processor import horizontal_runs
from stencil_to_stl.app.mesh_builder import build_relief_mesh, estimate_mesh_faces, merged_run_rectangles, physical_dimensions


def test_build_relief_mesh_has_base_and_consistent_total_height() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[4:6, 4:6] = True

    mesh = build_relief_mesh(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        pixel_to_mm_scale=0.1,
    )

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

    mesh = build_relief_mesh(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        pixel_to_mm_scale=(63.5, 88.9),
    )

    assert mesh.bounds[1].tolist() == [127.0, 177.8, 3.5]


def test_large_solid_mask_uses_row_runs_not_pixel_cubes() -> None:
    mask = np.ones((1000, 1000), dtype=bool)
    mesh = build_relief_mesh(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        pixel_to_mm_scale=0.1,
    )

    assert len(horizontal_runs(mask)) == 1000
    assert len(merged_run_rectangles(mask)) == 1
    assert mesh.is_watertight


def test_relief_touching_plate_boundary_is_watertight() -> None:
    mask = np.zeros((4, 4), dtype=bool)
    mask[0, :] = True

    mesh = build_relief_mesh(
        mask,
        base_thickness_mm=2.0,
        relief_height_mm=1.5,
        pixel_to_mm_scale=0.1,
    )

    assert mesh.is_watertight


def test_estimate_mesh_faces_matches_height_field_builder() -> None:
    mask = np.array(
        [
            [True, False],
            [False, False],
        ],
        dtype=bool,
    )

    assert estimate_mesh_faces(mask) == 40


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
