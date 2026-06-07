from __future__ import annotations

import numpy as np
import trimesh


def build_relief_mesh(
    mask: np.ndarray,
    *,
    base_thickness_mm: float,
    relief_height_mm: float,
    pixel_to_mm_scale: float,
) -> trimesh.Trimesh:
    """Build a base plate plus raised run-length prisms from a binary mask."""
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

    def cell_bounds(row: int, col: int) -> tuple[float, float, float, float]:
        x0 = col * pixel_to_mm_scale
        x1 = x0 + pixel_to_mm_scale
        y0 = (height_px - row - 1) * pixel_to_mm_scale
        y1 = y0 + pixel_to_mm_scale
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
                quad((x0, y0, 0.0), (x0, y0, top_z), (x0, y1, top_z), (x0, y1, 0.0))
            if col == width_px - 1:
                quad((x1, y1, 0.0), (x1, y1, top_z), (x1, y0, top_z), (x1, y0, 0.0))
            if row == 0:
                quad((x0, y1, 0.0), (x0, y1, top_z), (x1, y1, top_z), (x1, y1, 0.0))
            if row == height_px - 1:
                quad((x1, y0, 0.0), (x1, y0, top_z), (x0, y0, top_z), (x0, y0, 0.0))

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
    return mesh


def physical_dimensions(mask: np.ndarray, pixel_to_mm_scale: float) -> tuple[float, float]:
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    height_px, width_px = mask.shape
    return width_px * pixel_to_mm_scale, height_px * pixel_to_mm_scale
