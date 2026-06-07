from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Run:
    row: int
    start_x: int
    end_x: int

    @property
    def width_px(self) -> int:
        return self.end_x - self.start_x + 1


def black_pixel_mask(rgba: np.ndarray, threshold: int) -> np.ndarray:
    """Return a binary mask where opaque near-black pixels are print areas."""
    if rgba.ndim != 3 or rgba.shape[2] != 4:
        raise ValueError("Expected an RGBA image array.")
    if not 0 <= threshold <= 255:
        raise ValueError("Threshold must be between 0 and 255.")

    rgb = rgba[:, :, :3]
    alpha = rgba[:, :, 3]
    return (alpha > 0) & np.all(rgb < threshold, axis=2)


def mirror_mask_x(mask: np.ndarray) -> np.ndarray:
    return np.fliplr(mask)


def fill_diagonal_contacts(mask: np.ndarray) -> np.ndarray:
    """Fill 2x2 diagonal-only contacts so raised regions mesh as a manifold surface."""
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    if mask.shape[0] < 2 or mask.shape[1] < 2:
        return mask.copy()

    regularized = mask.copy()
    while True:
        top_left = regularized[:-1, :-1]
        top_right = regularized[:-1, 1:]
        bottom_left = regularized[1:, :-1]
        bottom_right = regularized[1:, 1:]
        saddle = (top_left & bottom_right & ~top_right & ~bottom_left) | (
            top_right & bottom_left & ~top_left & ~bottom_right
        )
        rows, cols = np.nonzero(saddle)
        if len(rows) == 0:
            return regularized
        regularized[rows, cols] = True
        regularized[rows, cols + 1] = True
        regularized[rows + 1, cols] = True
        regularized[rows + 1, cols + 1] = True


def horizontal_runs(mask: np.ndarray) -> list[Run]:
    """Group continuous black pixels in each row into run rectangles."""
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")

    runs: list[Run] = []
    for row_index, row in enumerate(mask):
        start_x: int | None = None
        for x, value in enumerate(row):
            if value and start_x is None:
                start_x = x
            elif not value and start_x is not None:
                runs.append(Run(row=row_index, start_x=start_x, end_x=x - 1))
                start_x = None
        if start_x is not None:
            runs.append(Run(row=row_index, start_x=start_x, end_x=len(row) - 1))
    return runs
