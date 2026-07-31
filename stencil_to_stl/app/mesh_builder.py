from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import trimesh

from stencil_to_stl.app.height_field import remove_saddle_pinches
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


@dataclass(frozen=True)
class _Walls:
    """Vertical wall strips, each spanning its own height range at either end.

    A wall between two cells rarely gets to be a plain rectangle. Where it meets
    a grid corner, up to four cells of differing height meet on that one vertical
    line, and every wall arriving there has to carry a vertex at each of those
    heights or the surface will not close. Letting the two ends span different
    height ranges makes each strip a trapezoid, which is what lets neighbouring
    walls agree on where their shared edge is divided.
    """

    corner_a: np.ndarray  # (N, 2) xy of one end
    corner_b: np.ndarray  # (N, 2) xy of the other end
    a_low: np.ndarray
    a_high: np.ndarray
    b_low: np.ndarray
    b_high: np.ndarray
    outward: np.ndarray  # (N,) True where the corner order already faces outward

    def face_count(self) -> int:
        """Triangles that survive once collapsed ends are discarded."""
        a_flat = self.a_low == self.a_high
        b_flat = self.b_low == self.b_high
        return int(np.clip(2 - a_flat.astype(int) - b_flat.astype(int), 0, None).sum())

    def quads(self) -> np.ndarray:
        corners = np.stack(
            [
                np.column_stack([self.corner_a, self.a_low]),
                np.column_stack([self.corner_b, self.b_low]),
                np.column_stack([self.corner_b, self.b_high]),
                np.column_stack([self.corner_a, self.a_high]),
            ],
            axis=1,
        )
        flipped = corners[:, ::-1]
        return np.where(self.outward[:, None, None], corners, flipped)


def _stack_bands(
    corner_a: np.ndarray,
    corner_b: np.ndarray,
    a_levels: list[np.ndarray],
    b_levels: list[np.ndarray],
    outward: np.ndarray,
) -> _Walls:
    """Stack one wall into consecutive bands between the given split levels."""
    repeats = len(a_levels) - 1
    return _Walls(
        corner_a=np.tile(corner_a, (repeats, 1)),
        corner_b=np.tile(corner_b, (repeats, 1)),
        a_low=np.concatenate(a_levels[:-1]),
        a_high=np.concatenate(a_levels[1:]),
        b_low=np.concatenate(b_levels[:-1]),
        b_high=np.concatenate(b_levels[1:]),
        outward=np.tile(outward, repeats),
    )


def _concat_walls(walls: list[_Walls]) -> _Walls:
    return _Walls(
        corner_a=np.concatenate([w.corner_a for w in walls]),
        corner_b=np.concatenate([w.corner_b for w in walls]),
        a_low=np.concatenate([w.a_low for w in walls]),
        a_high=np.concatenate([w.a_high for w in walls]),
        b_low=np.concatenate([w.b_low for w in walls]),
        b_high=np.concatenate([w.b_high for w in walls]),
        outward=np.concatenate([w.outward for w in walls]),
    )


def _shift(values: np.ndarray, axis: int, offset: int, fallback: np.ndarray) -> np.ndarray:
    """Neighboring values one step along an axis, falling back at the edge."""
    shifted = fallback.copy()
    front = (slice(None),) * axis + (slice(None, -1),)
    back = (slice(None),) * axis + (slice(1, None),)
    if offset > 0:
        shifted[front] = values[back]
    else:
        shifted[back] = values[front]
    return shifted


def _corner_splits(
    first: np.ndarray,
    second: np.ndarray,
    low: np.ndarray,
    high: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """The two other cell heights at a corner, clamped into the wall's own span."""
    lower = np.clip(np.minimum(first, second), low, high)
    upper = np.clip(np.maximum(first, second), low, high)
    return lower, upper


def _step_walls(height_field: np.ndarray, grid: dict[str, np.ndarray]) -> list[_Walls]:
    """Walls wherever two neighboring cells sit at different heights."""
    walls: list[_Walls] = []
    height_px, width_px = height_field.shape

    if width_px > 1:
        left, right = height_field[:, :-1], height_field[:, 1:]
        low, high = np.minimum(left, right), np.maximum(left, right)
        step = left != right
        if step.any():
            # The low-y end of a row abuts the next row down; the high-y end the previous one.
            below = _corner_splits(
                _shift(left, 0, 1, low), _shift(right, 0, 1, low), low, high
            )
            above = _corner_splits(
                _shift(left, 0, -1, low), _shift(right, 0, -1, low), low, high
            )
            x = grid["x1"][:, :-1][step]
            walls.append(
                _stack_bands(
                    np.column_stack([x, grid["y0"][:, :-1][step]]),
                    np.column_stack([x, grid["y1"][:, :-1][step]]),
                    [low[step], below[0][step], below[1][step], high[step]],
                    [low[step], above[0][step], above[1][step], high[step]],
                    # Corner order faces +x, outward while the left cell is taller.
                    left[step] > right[step],
                )
            )

    if height_px > 1:
        upper, lower = height_field[:-1, :], height_field[1:, :]
        low, high = np.minimum(upper, lower), np.maximum(upper, lower)
        step = upper != lower
        if step.any():
            before = _corner_splits(
                _shift(upper, 1, -1, low), _shift(lower, 1, -1, low), low, high
            )
            after = _corner_splits(
                _shift(upper, 1, 1, low), _shift(lower, 1, 1, low), low, high
            )
            y = grid["y0"][:-1, :][step]
            walls.append(
                _stack_bands(
                    np.column_stack([grid["x0"][:-1, :][step], y]),
                    np.column_stack([grid["x1"][:-1, :][step], y]),
                    [low[step], before[0][step], before[1][step], high[step]],
                    [low[step], after[0][step], after[1][step], high[step]],
                    # Corner order faces -y, outward while the upper cell is taller.
                    upper[step] > lower[step],
                )
            )

    return walls


def _neighbor_floor(heights: np.ndarray, offset: int) -> np.ndarray:
    """Lower of each height and its neighbor one step away, or itself at the ends."""
    floors = heights.copy()
    if offset > 0:
        floors[:-1] = np.minimum(heights[:-1], heights[1:])
    else:
        floors[1:] = np.minimum(heights[1:], heights[:-1])
    return floors


# Which neighbor sits at each end of a border wall, and whether the corner order
# already points away from the block. Rows run top-down while y runs bottom-up,
# so a row's low-y end abuts the next row; columns simply run with x.
_PERIMETER_SIDES = ("left", "right", "bottom", "top")
_PERIMETER_OFFSETS = {"left": (1, -1), "right": (1, -1), "bottom": (-1, 1), "top": (-1, 1)}
_PERIMETER_OUTWARD = {"left": False, "right": True, "bottom": True, "top": False}


def _side_heights(height_field: np.ndarray, side: str) -> np.ndarray:
    return {
        "left": height_field[:, 0],
        "right": height_field[:, -1],
        "bottom": height_field[-1, :],
        "top": height_field[0, :],
    }[side]


def _side_corners(grid: dict[str, np.ndarray], side: str) -> tuple[np.ndarray, np.ndarray]:
    return {
        "left": (
            np.column_stack([grid["x0"][:, 0], grid["y0"][:, 0]]),
            np.column_stack([grid["x0"][:, 0], grid["y1"][:, 0]]),
        ),
        "right": (
            np.column_stack([grid["x1"][:, -1], grid["y0"][:, -1]]),
            np.column_stack([grid["x1"][:, -1], grid["y1"][:, -1]]),
        ),
        "bottom": (
            np.column_stack([grid["x0"][-1, :], grid["y0"][-1, :]]),
            np.column_stack([grid["x1"][-1, :], grid["y0"][-1, :]]),
        ),
        "top": (
            np.column_stack([grid["x0"][0, :], grid["y1"][0, :]]),
            np.column_stack([grid["x1"][0, :], grid["y1"][0, :]]),
        ),
    }[side]


def _perimeter_walls(height_field: np.ndarray, grid: dict[str, np.ndarray] | None) -> list[_Walls]:
    """Outer walls, running from the build plate up to each border cell's height.

    Split at each neighbor's height for the same reason interior walls are: a
    border cell beside a shorter one shares a vertical line with both that
    neighbor's wall and the step between them, and both meet it partway up.
    """
    walls: list[_Walls] = []
    for side in _PERIMETER_SIDES:
        heights = _side_heights(height_field, side)
        offset_a, offset_b = _PERIMETER_OFFSETS[side]
        floor = np.zeros_like(heights)
        if grid is None:
            corner_a = corner_b = np.zeros((len(heights), 2))
        else:
            corner_a, corner_b = _side_corners(grid, side)
        walls.append(
            _stack_bands(
                corner_a,
                corner_b,
                [floor, _neighbor_floor(heights, offset_a), heights],
                [floor, _neighbor_floor(heights, offset_b), heights],
                np.full(len(heights), _PERIMETER_OUTWARD[side]),
            )
        )
    return walls


def _cell_grid(height_px: int, width_px: int, x_scale: float, y_scale: float) -> dict[str, np.ndarray]:
    columns = np.arange(width_px)
    rows = np.arange(height_px)
    return {
        "x0": np.broadcast_to(columns * x_scale, (height_px, width_px)),
        "x1": np.broadcast_to((columns + 1) * x_scale, (height_px, width_px)),
        "y0": np.broadcast_to(((height_px - rows - 1) * y_scale)[:, None], (height_px, width_px)),
        "y1": np.broadcast_to(((height_px - rows) * y_scale)[:, None], (height_px, width_px)),
    }


def _top_quads(height_field: np.ndarray, grid: dict[str, np.ndarray]) -> np.ndarray:
    z = height_field
    return np.stack(
        [
            np.stack([grid["x0"], grid["y0"], z], axis=-1).reshape(-1, 3),
            np.stack([grid["x1"], grid["y0"], z], axis=-1).reshape(-1, 3),
            np.stack([grid["x1"], grid["y1"], z], axis=-1).reshape(-1, 3),
            np.stack([grid["x0"], grid["y1"], z], axis=-1).reshape(-1, 3),
        ],
        axis=1,
    )


def _bottom_fan(height_px: int, width_px: int, x_scale: float, y_scale: float) -> tuple[np.ndarray, np.ndarray]:
    """Triangulate the flat underside as a fan from its center.

    The perimeter walls are built per cell, so the base plate has to carry a
    vertex at every cell corner along its edge or those edges leave T-junctions
    and the mesh stops being watertight. Fanning from the center meets that at
    2*(H+W) triangles instead of the 2 per cell a full grid would cost, and no
    boundary edge is collinear with the center so none of them is degenerate.
    """
    width_mm, height_mm = width_px * x_scale, height_px * y_scale
    columns = np.arange(width_px + 1) * x_scale
    rows = np.arange(height_px + 1) * y_scale

    ring = np.concatenate(
        [
            np.stack([columns[:-1], np.zeros(width_px)], axis=1),
            np.stack([np.full(height_px, width_mm), rows[:-1]], axis=1),
            np.stack([columns[::-1][:-1], np.full(width_px, height_mm)], axis=1),
            np.stack([np.zeros(height_px), rows[::-1][:-1]], axis=1),
        ]
    )
    center = np.array([[width_mm / 2, height_mm / 2]])
    points = np.concatenate([center, ring])
    vertices = np.column_stack([points, np.zeros(len(points))])

    count = len(ring)
    current = 1 + np.arange(count)
    following = 1 + (np.arange(count) + 1) % count
    # Reversed against the counter-clockwise ring so the underside faces -z.
    triangles = np.stack([np.zeros(count, dtype=np.int64), following, current], axis=1)
    return vertices, triangles


def _quads_to_triangles(quads: np.ndarray, first_vertex: int) -> np.ndarray:
    """Split (N, 4, 3) quads into (2N, 3) triangle indices over their own vertices."""
    count = len(quads)
    indices = first_vertex + np.arange(count * 4, dtype=np.int64).reshape(count, 4)
    triangles = np.empty((count * 2, 3), dtype=np.int64)
    triangles[0::2] = indices[:, [0, 1, 2]]
    triangles[1::2] = indices[:, [0, 2, 3]]
    return triangles


def _drop_degenerate_faces(vertices: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """Discard faces with a repeated corner.

    A wall band whose ends collapse is a triangle, or nothing at all, so one or
    both of the triangles the quad splitter emits for it has zero area. Such a
    face covers no surface, but its repeated edge is counted twice when checking
    that every edge borders exactly two faces, which would report a perfectly
    closed mesh as leaking.
    """
    corners = vertices[faces]
    repeated = (
        np.all(corners[:, 0] == corners[:, 1], axis=1)
        | np.all(corners[:, 1] == corners[:, 2], axis=1)
        | np.all(corners[:, 2] == corners[:, 0], axis=1)
    )
    return faces[~repeated]


def estimate_mesh_faces(height_field: np.ndarray) -> int:
    """Triangle count ``build_relief_mesh`` will produce for this height field."""
    _validate_height_field(height_field)
    height_field = remove_saddle_pinches(height_field)
    height_px, width_px = height_field.shape
    walls = _step_walls(height_field, _cell_grid(height_px, width_px, 1.0, 1.0))
    walls += _perimeter_walls(height_field, grid=None)

    tops = 2 * height_px * width_px
    bottom = 2 * (height_px + width_px)
    return tops + bottom + sum(wall.face_count() for wall in walls)


def _validate_height_field(height_field: np.ndarray) -> None:
    if height_field.ndim != 2:
        raise ValueError("Expected a 2D height field.")
    if height_field.size == 0:
        raise ValueError("Height field must not be empty.")
    if np.any(height_field <= 0):
        raise ValueError("Every height must be greater than 0.")


def build_relief_mesh(height_field: np.ndarray, *, pixel_to_mm_scale: PixelScale) -> trimesh.Trimesh:
    """Build a watertight block whose top follows the given per-cell height field.

    Heights are arbitrary rather than the two levels a plain mask would give, so
    a chamfered root reaches the mesh as a run of short steps instead of being
    flattened back into a square wall.
    """
    _validate_height_field(height_field)
    x_scale, y_scale = _normalize_pixel_scale(pixel_to_mm_scale)
    if x_scale <= 0 or y_scale <= 0:
        raise ValueError("Scale must be greater than 0.")

    height_field = remove_saddle_pinches(height_field)
    height_px, width_px = height_field.shape
    grid = _cell_grid(height_px, width_px, x_scale, y_scale)

    walls = _concat_walls(_step_walls(height_field, grid) + _perimeter_walls(height_field, grid))
    quads = np.concatenate([_top_quads(height_field, grid), walls.quads()])
    quad_vertices = quads.reshape(-1, 3)
    quad_faces = _quads_to_triangles(quads, first_vertex=0)

    bottom_vertices, bottom_faces = _bottom_fan(height_px, width_px, x_scale, y_scale)
    vertices = np.concatenate([quad_vertices, bottom_vertices])
    faces = np.concatenate([quad_faces, bottom_faces + len(quad_vertices)])

    return trimesh.Trimesh(vertices=vertices, faces=_drop_degenerate_faces(vertices, faces), process=True)


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
