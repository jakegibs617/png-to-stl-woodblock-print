from __future__ import annotations

import numpy as np
from scipy import ndimage

CHAMFER_ANGLE_TANGENT = 1.0  # 45 degrees: the skirt reaches out as far as it is tall


def remove_saddle_pinches(height_field: np.ndarray) -> np.ndarray:
    """Fill height-field saddles so the block can close into a solid.

    Where two diagonally opposite cells both stand above the other two, the
    surface touches itself along the vertical line those four cells share. Four
    wall faces meet on that one edge instead of two, which is not a surface any
    slicer can resolve, and it is a knife-edge in the print besides.

    The pinch is relieved by lifting the lower pair rather than cutting the upper
    one down: adding material at a point where two features barely touch is the
    same instinct as chamfering a root, and it never removes artwork. Lifting can
    expose a new saddle nearby, so this repeats until none is left, which it
    always reaches because heights only ever rise and are bounded above.
    """
    if height_field.ndim != 2:
        raise ValueError("Expected a 2D height field.")
    field = height_field.astype(float, copy=True)
    if field.shape[0] < 2 or field.shape[1] < 2:
        return field

    while True:
        upper_left, upper_right = field[:-1, :-1], field[:-1, 1:]
        lower_left, lower_right = field[1:, :-1], field[1:, 1:]
        main_floor = np.minimum(upper_left, lower_right)
        anti_floor = np.minimum(upper_right, lower_left)
        pinched_anti = main_floor > np.maximum(upper_right, lower_left)
        pinched_main = anti_floor > np.maximum(upper_left, lower_right)
        if not pinched_anti.any() and not pinched_main.any():
            return field

        # Lift only the taller cell of the sunken pair: that alone is enough to
        # stop the two diagonals clearing each other, so the fill stays minimal.
        _lift_taller(field, pinched_anti, upper_right, lower_left, main_floor, (0, 1), (1, 0))
        _lift_taller(field, pinched_main, upper_left, lower_right, anti_floor, (0, 0), (1, 1))


def _lift_taller(
    field: np.ndarray,
    pinched: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    target: np.ndarray,
    first_offset: tuple[int, int],
    second_offset: tuple[int, int],
) -> None:
    if not pinched.any():
        return
    rows, cols = np.nonzero(pinched)
    heights = target[rows, cols]
    take_first = first[rows, cols] >= second[rows, cols]

    for selected, (row_offset, col_offset) in ((take_first, first_offset), (~take_first, second_offset)):
        if not selected.any():
            continue
        np.maximum.at(
            field,
            (rows[selected] + row_offset, cols[selected] + col_offset),
            heights[selected],
        )


def build_height_field(
    mask: np.ndarray,
    *,
    base_thickness_mm: float,
    relief_height_mm: float,
    chamfer_height_mm: float,
    x_scale_mm: float,
    y_scale_mm: float,
) -> np.ndarray:
    """Return the top height of every cell, in millimeters above the build plate.

    A raised feature is a cantilevered wall, and bending stress at its root grows
    with the square of its height-to-width ratio. Meeting the base plate at a
    square 90 degree corner puts that peak stress into a notch with no material
    behind it, which is where thin lines snap. Flaring the root outward adds
    section modulus exactly where the moment is largest.

    The flare is capped at ``chamfer_height_mm`` rather than running the full
    relief. That bound is what protects the print: where two features are close
    enough for their skirts to meet, the valley between them still keeps
    ``relief_height_mm - chamfer_height_mm`` of ink clearance, so the paper never
    touches the valley floor. A full-height draft angle would fill it in.

    The top surface is untouched — every raised cell keeps the full relief height
    and the exact footprint of the mask, so print fidelity is unchanged and all
    inked surfaces stay coplanar.
    """
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    if base_thickness_mm <= 0:
        raise ValueError("Base thickness must be greater than 0.")
    if relief_height_mm <= 0:
        raise ValueError("Relief height must be greater than 0.")
    if chamfer_height_mm < 0:
        raise ValueError("Chamfer height must not be negative.")
    if chamfer_height_mm >= relief_height_mm:
        raise ValueError("Chamfer height must be less than the relief height.")
    if x_scale_mm <= 0 or y_scale_mm <= 0:
        raise ValueError("Scale must be greater than 0.")

    field = np.full(mask.shape, base_thickness_mm, dtype=float)
    field[mask] = base_thickness_mm + relief_height_mm
    if chamfer_height_mm == 0 or not mask.any() or mask.all():
        return field

    chamfer_width_mm = chamfer_height_mm / CHAMFER_ANGLE_TANGENT
    distance_out_mm = ndimage.distance_transform_edt(~mask, sampling=(y_scale_mm, x_scale_mm))

    # Distances are center-to-center, but the wall face sits half a pixel outside
    # the last raised center, so back that half pixel out before ramping.
    half_pitch_mm = min(x_scale_mm, y_scale_mm) / 2
    distance_from_wall_mm = np.clip(distance_out_mm - half_pitch_mm, 0.0, None)

    ramp = np.clip(1.0 - distance_from_wall_mm / chamfer_width_mm, 0.0, 1.0)
    field[~mask] = base_thickness_mm + chamfer_height_mm * ramp[~mask]
    return field
