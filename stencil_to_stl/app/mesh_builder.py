from __future__ import annotations

import numpy as np
import trimesh

from stencil_to_stl.app.mask_processor import Run, horizontal_runs

Rectangle = tuple[int, int, int, int]
PixelScale = float | tuple[float, float]


def merged_run_rectangles(mask: np.ndarray) -> list[Rectangle]:
    """Merge identical horizontal runs across adjacent rows.

    Returns rectangles as (start_row, end_row, start_x, end_x), inclusive.
    """
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")

    rectangles: list[Rectangle] = []
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

    return sorted(rectangles, key=lambda r: (r[0], r[2], r[1], r[3]))


def estimate_mesh_faces(mask: np.ndarray) -> int:
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    height_px, width_px = mask.shape
    perimeter_edges = (height_px * 2) + (width_px * 2)
    raised_perimeter_edges = (
        int(mask[:, 0].sum())
        + int(mask[:, width_px - 1].sum())
        + int(mask[0, :].sum())
        + int(mask[height_px - 1, :].sum())
    )
    horizontal_transitions = int((mask[:, :-1] != mask[:, 1:]).sum()) if width_px > 1 else 0
    vertical_transitions = int((mask[:-1, :] != mask[1:, :]).sum()) if height_px > 1 else 0
    return (mask.size * 4) + (perimeter_edges * 2) + (raised_perimeter_edges * 2) + (
        (horizontal_transitions + vertical_transitions) * 2
    )


def build_relief_mesh(
    mask: np.ndarray,
    *,
    base_thickness_mm: float,
    relief_height_mm: float,
    pixel_to_mm_scale: PixelScale,
    relief_rectangles: list[Rectangle] | None = None,
) -> trimesh.Trimesh:
    """Build a base plate plus raised relief from a binary mask."""
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    if base_thickness_mm <= 0:
        raise ValueError("Base thickness must be greater than 0.")
    if relief_height_mm <= 0:
        raise ValueError("Relief height must be greater than 0.")
    x_scale, y_scale = _normalize_pixel_scale(pixel_to_mm_scale)
    if x_scale <= 0 or y_scale <= 0:
        raise ValueError("Scale must be greater than 0.")

    height_px, width_px = mask.shape
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

    def perimeter_quad(
        lower_a: tuple[float, float, float],
        upper_a: tuple[float, float, float],
        upper_b: tuple[float, float, float],
        lower_b: tuple[float, float, float],
        top_z: float,
    ) -> None:
        if top_z == base_thickness_mm:
            quad(lower_a, upper_a, upper_b, lower_b)
            return
        base_a = (upper_a[0], upper_a[1], base_thickness_mm)
        base_b = (upper_b[0], upper_b[1], base_thickness_mm)
        quad(lower_a, base_a, base_b, lower_b)
        quad(base_a, upper_a, upper_b, base_b)

    def cell_bounds(row: int, col: int) -> tuple[float, float, float, float]:
        x0 = col * x_scale
        x1 = x0 + x_scale
        y0 = (height_px - row - 1) * y_scale
        y1 = y0 + y_scale
        return x0, x1, y0, y1

    def cell_top(row: int, col: int) -> float:
        return raised_z if mask[row, col] else base_thickness_mm

    for row in range(height_px):
        for col in range(width_px):
            x0, x1, y0, y1 = cell_bounds(row, col)
            top_z = cell_top(row, col)

            quad((x0, y0, top_z), (x1, y0, top_z), (x1, y1, top_z), (x0, y1, top_z))
            quad((x0, y1, 0.0), (x1, y1, 0.0), (x1, y0, 0.0), (x0, y0, 0.0))

            if col == 0:
                perimeter_quad((x0, y0, 0.0), (x0, y0, top_z), (x0, y1, top_z), (x0, y1, 0.0), top_z)
            if col == width_px - 1:
                perimeter_quad((x1, y1, 0.0), (x1, y1, top_z), (x1, y0, top_z), (x1, y0, 0.0), top_z)
            if row == 0:
                perimeter_quad((x0, y1, 0.0), (x0, y1, top_z), (x1, y1, top_z), (x1, y1, 0.0), top_z)
            if row == height_px - 1:
                perimeter_quad((x1, y0, 0.0), (x1, y0, top_z), (x0, y0, top_z), (x0, y0, 0.0), top_z)

            if col < width_px - 1:
                neighbor_z = cell_top(row, col + 1)
                if top_z != neighbor_z:
                    low_z, high_z = sorted((top_z, neighbor_z))
                    quad((x1, y0, low_z), (x1, y0, high_z), (x1, y1, high_z), (x1, y1, low_z))
            if row < height_px - 1:
                neighbor_z = cell_top(row + 1, col)
                if top_z != neighbor_z:
                    low_z, high_z = sorted((top_z, neighbor_z))
                    quad((x1, y0, low_z), (x1, y0, high_z), (x0, y0, high_z), (x0, y0, low_z))

    mesh = trimesh.Trimesh(vertices=np.array(vertices), faces=np.array(faces), process=True)
    trimesh.repair.fix_normals(mesh)
    return mesh


def _normalize_pixel_scale(pixel_to_mm_scale: PixelScale) -> tuple[float, float]:
    if isinstance(pixel_to_mm_scale, tuple):
        return pixel_to_mm_scale
    return pixel_to_mm_scale, pixel_to_mm_scale


def physical_dimensions(mask: np.ndarray, pixel_to_mm_scale: PixelScale) -> tuple[float, float]:
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    height_px, width_px = mask.shape
    x_scale, y_scale = _normalize_pixel_scale(pixel_to_mm_scale)
    if x_scale <= 0 or y_scale <= 0:
        raise ValueError("Scale must be greater than 0.")
    return width_px * x_scale, height_px * y_scale
