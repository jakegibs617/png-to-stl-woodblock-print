import numpy as np

from stencil_to_stl.app.mask_processor import horizontal_runs
from stencil_to_stl.app.mesh_builder import build_relief_mesh, physical_dimensions


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
    assert mesh.bounds[0].tolist() == [0.0, 0.0, 0.0]
    assert mesh.bounds[1].tolist() == [1.0, 1.0, 3.5]
    assert len(horizontal_runs(mask)) == 2


def test_physical_dimensions_uses_width_then_height() -> None:
    mask = np.zeros((20, 10), dtype=bool)

    assert physical_dimensions(mask, 0.1) == (1.0, 2.0)


def test_large_solid_mask_uses_row_runs_not_pixel_cubes() -> None:
    mask = np.ones((1000, 1000), dtype=bool)

    assert len(horizontal_runs(mask)) == 1000

