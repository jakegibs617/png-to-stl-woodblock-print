from __future__ import annotations

import numpy as np
import trimesh

from stencil_to_stl.app.mask_processor import Run, horizontal_runs


def merged_run_rectangles(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    """Merge identical horizontal runs across adjacent rows.

    Returns rectangles as (start_row, end_row, start_x, end_x), inclusive.
    """
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")

    rectangles: list[tuple[int, int, int, int]] = []
    active: dict[tuple[int, int], Run] = {}

    for row in range(mask.shape[0]):
        row_runs = [run for run in horizontal_runs(mask[row : row + 1]) if run.width_px > 0]
        current_keys: set[tuple[int, int]] = set()
        next_active: dict[tuple[int, int], Run] = {}

        for run in row_runs:
            key = (run.start_x, run.end_x)
            current_keys.add(key)
            if key in active:
                previous = active[key]
                next_active[key] = Run(row=previous.row, start_x=previous.start_x, end_x=previous.end_x)
            else:
                next_active[key] = Run(row=row, start_x=run.start_x, end_x=run.end_x)

        for key, run in active.items():
            if key not in current_keys:
                rectangles.append((run.row, row - 1, run.start_x, run.end_x))
        active = next_active

    for run in active.values():
        rectangles.append((run.row, mask.shape[0] - 1, run.start_x, run.end_x))

    return sorted(rectangles, key=lambda rectangle: (rectangle[0], rectangle[2], rectangle[1], rectangle[3]))


def estimate_mesh_faces(mask: np.ndarray) -> int:
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")

    return 12 + (len(merged_run_rectangles(mask)) * 12)


def build_relief_mesh(
    mask: np.ndarray,
    *,
    base_thickness_mm: float,
    relief_height_mm: float,
    pixel_to_mm_scale: float,
) -> trimesh.Trimesh:
    """Build a base plate plus raised rectangle prisms from a binary mask."""
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    if base_thickness_mm <= 0:
        raise ValueError("Base thickness must be greater than 0.")
    if relief_height_mm <= 0:
        raise ValueError("Relief height must be greater than 0.")
    if pixel_to_mm_scale <= 0:
        raise ValueError("Scale must be greater than 0.")

    height_px, width_px = mask.shape
    width_mm = width_px * pixel_to_mm_scale
    height_mm = height_px * pixel_to_mm_scale
    raised_z = base_thickness_mm + relief_height_mm

    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int]] = []
    vertex_index: dict[tuple[float, float, float], int] = {}

    def vertex(point: tuple[float, float, float]) -> int:
        if point not in vertex_index:
            vertex_index[point] = len(vertices)
            vertices.append(point)
        return vertex_index[point]

    def quad(
        a: tuple[float, float, float],
        b: tuple[float, float, float],
        c: tuple[float, float, float],
        d: tuple[float, float, float],
    ) -> None:
        faces.append((vertex(a), vertex(b), vertex(c)))
        faces.append((vertex(a), vertex(c), vertex(d)))

    def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> None:
        quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))
        quad((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0))
        quad((x0, y0, z0), (x0, y0, z1), (x0, y1, z1), (x0, y1, z0))
        quad((x1, y1, z0), (x1, y1, z1), (x1, y0, z1), (x1, y0, z0))
        quad((x0, y1, z0), (x0, y1, z1), (x1, y1, z1), (x1, y1, z0))
        quad((x1, y0, z0), (x1, y0, z1), (x0, y0, z1), (x0, y0, z0))

    box(0.0, width_mm, 0.0, height_mm, 0.0, base_thickness_mm)

    for start_row, end_row, start_x, end_x in merged_run_rectangles(mask):
        x0 = start_x * pixel_to_mm_scale
        x1 = (end_x + 1) * pixel_to_mm_scale
        y0 = (height_px - end_row - 1) * pixel_to_mm_scale
        y1 = (height_px - start_row) * pixel_to_mm_scale
        box(x0, x1, y0, y1, base_thickness_mm, raised_z)

    mesh = trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces), process=True)
    return mesh


def physical_dimensions(mask: np.ndarray, pixel_to_mm_scale: float) -> tuple[float, float]:
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    height_px, width_px = mask.shape
    return width_px * pixel_to_mm_scale, height_px * pixel_to_mm_scale
