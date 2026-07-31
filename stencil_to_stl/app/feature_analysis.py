from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import ndimage

# Distances come back center-to-center, so a feature's boundary sits half a pixel
# short of the nearest background center. Subtracting one pixel pitch from the
# doubled distance corrects for that, and rounds even pixel widths down rather
# than up: under-reporting width keeps the thin check on the safe side.
_TOLERANCE_MM = 1e-9


@dataclass(frozen=True)
class FeatureReport:
    min_width_mm: float
    thin_pixel_count: int
    thin_area_fraction: float
    component_count: int


@dataclass(frozen=True)
class WidenReport:
    pixels_added: int
    component_count_before: int
    component_count_after: int

    @property
    def merged_features(self) -> int:
        return max(0, self.component_count_before - self.component_count_after)


def _distance_into_mm(mask: np.ndarray, x_scale_mm: float, y_scale_mm: float) -> np.ndarray:
    """Distance in millimeters from each raised pixel to the nearest background pixel.

    The block ends at the edge of the image, so everything past it counts as
    empty. Without that, a feature running off the edge is measured across to the
    far side of itself and comes back twice as wide as it really is, and artwork
    covering the whole image has no background to measure against at all.
    """
    padded = np.pad(mask, 1, constant_values=False)
    distance = ndimage.distance_transform_edt(padded, sampling=(y_scale_mm, x_scale_mm))
    return distance[1:-1, 1:-1]


def _validate(mask: np.ndarray, min_width_mm: float, x_scale_mm: float, y_scale_mm: float) -> None:
    if mask.ndim != 2:
        raise ValueError("Expected a 2D mask.")
    if min_width_mm <= 0:
        raise ValueError("Minimum feature width must be greater than 0.")
    if x_scale_mm <= 0 or y_scale_mm <= 0:
        raise ValueError("Scale must be greater than 0.")


def _erosion_radius_mm(min_width_mm: float, x_scale_mm: float, y_scale_mm: float) -> float:
    return (min_width_mm + min(x_scale_mm, y_scale_mm)) / 2


def _medial_ridge(mask: np.ndarray, distance_in: np.ndarray) -> np.ndarray:
    """Pixels no closer to an edge than any of their neighbors."""
    return mask & (distance_in >= ndimage.maximum_filter(distance_in, size=3) - _TOLERANCE_MM)


def _local_width_mm(distance_in: np.ndarray, x_scale_mm: float, y_scale_mm: float) -> np.ndarray:
    return 2 * distance_in - min(x_scale_mm, y_scale_mm)


def _spread(seeds: np.ndarray, radius_mm: float, x_scale_mm: float, y_scale_mm: float) -> np.ndarray:
    distance = ndimage.distance_transform_edt(~seeds, sampling=(y_scale_mm, x_scale_mm))
    return distance <= radius_mm + _TOLERANCE_MM


def thin_feature_mask(
    mask: np.ndarray,
    *,
    min_width_mm: float,
    x_scale_mm: float,
    y_scale_mm: float,
) -> np.ndarray:
    """Return the raised pixels belonging to features narrower than ``min_width_mm``.

    A feature is at least ``w`` wide exactly when it survives a morphological
    opening with a disk of radius ``w / 2``, so the material at risk is what the
    opening removes. Measuring by raw distance-to-edge instead would flag the
    outer rim of every thick shape, since those pixels are close to a boundary
    even though the feature they belong to is not narrow.

    Opening alone also shaves the sharp corners off perfectly healthy shapes,
    because no disk quite reaches into a right angle. Those pixels are not a
    printing problem and there is nothing to widen, so the result is narrowed to
    material that answers to a genuinely narrow spine — a point on the medial
    ridge whose own width falls short.
    """
    _validate(mask, min_width_mm, x_scale_mm, y_scale_mm)
    if not mask.any():
        return np.zeros_like(mask)

    radius_mm = _erosion_radius_mm(min_width_mm, x_scale_mm, y_scale_mm)
    distance_in = _distance_into_mm(mask, x_scale_mm, y_scale_mm)

    narrow_spine = _medial_ridge(mask, distance_in) & (
        _local_width_mm(distance_in, x_scale_mm, y_scale_mm) < min_width_mm - _TOLERANCE_MM
    )
    if not narrow_spine.any():
        return np.zeros_like(mask)

    core = distance_in >= radius_mm - _TOLERANCE_MM
    opened = core.any() and not core.all()
    at_risk = mask & ~_spread(core, radius_mm, x_scale_mm, y_scale_mm) if opened else mask & ~core
    return at_risk & _spread(narrow_spine, radius_mm, x_scale_mm, y_scale_mm)


def narrowest_feature_mm(mask: np.ndarray, *, x_scale_mm: float, y_scale_mm: float) -> float:
    """Width of the narrowest sustained feature, in millimeters.

    Only medial-ridge pixels count — those whose distance-to-edge is at least as
    large as every neighbor's. A tapering tip or the outer rim of a thick shape
    sits close to a boundary but is always adjacent to a deeper pixel, so it is
    excluded and does not drag the reported width down to one pixel.
    """
    if not mask.any():
        return 0.0

    distance_in = _distance_into_mm(mask, x_scale_mm, y_scale_mm)
    ridge = mask & (distance_in >= ndimage.maximum_filter(distance_in, size=3) - _TOLERANCE_MM)
    return float(2 * distance_in[ridge].min() - min(x_scale_mm, y_scale_mm))


def measure_features(
    mask: np.ndarray,
    *,
    min_width_mm: float,
    x_scale_mm: float,
    y_scale_mm: float,
) -> FeatureReport:
    """Describe how much of the artwork falls below the minimum printable width."""
    _validate(mask, min_width_mm, x_scale_mm, y_scale_mm)
    raised_count = int(mask.sum())
    if raised_count == 0:
        return FeatureReport(min_width_mm=0.0, thin_pixel_count=0, thin_area_fraction=0.0, component_count=0)

    thin = thin_feature_mask(
        mask,
        min_width_mm=min_width_mm,
        x_scale_mm=x_scale_mm,
        y_scale_mm=y_scale_mm,
    )
    thin_count = int(thin.sum())
    return FeatureReport(
        min_width_mm=narrowest_feature_mm(mask, x_scale_mm=x_scale_mm, y_scale_mm=y_scale_mm),
        thin_pixel_count=thin_count,
        thin_area_fraction=thin_count / raised_count,
        component_count=component_count(mask),
    )


def widen_thin_features(
    mask: np.ndarray,
    *,
    min_width_mm: float,
    x_scale_mm: float,
    y_scale_mm: float,
) -> tuple[np.ndarray, WidenReport]:
    """Grow features narrower than ``min_width_mm`` until they are printable.

    Below one extrusion width a line does not survive slicing at all, and no
    amount of support geometry recovers it, so the only fix is more material.
    Growth is applied one pixel at a time to the thin set alone, which leaves
    artwork that is already wide enough completely untouched.

    Widening can close a narrow gap and fuse two features into one. That is the
    single way this step can quietly change the artwork, so the returned report
    carries the connected-component count on both sides for callers to surface.
    """
    _validate(mask, min_width_mm, x_scale_mm, y_scale_mm)
    count_before = component_count(mask)
    widened = mask.copy()

    finest_pitch_mm = min(x_scale_mm, y_scale_mm)
    max_passes = int(np.ceil(min_width_mm / (2 * finest_pitch_mm))) + 1
    for _ in range(max_passes):
        thin = thin_feature_mask(
            widened,
            min_width_mm=min_width_mm,
            x_scale_mm=x_scale_mm,
            y_scale_mm=y_scale_mm,
        )
        if not thin.any():
            break
        widened |= ndimage.binary_dilation(thin, structure=np.ones((3, 3), dtype=bool))

    return widened, WidenReport(
        pixels_added=int(widened.sum() - mask.sum()),
        component_count_before=count_before,
        component_count_after=component_count(widened),
    )


def component_count(mask: np.ndarray) -> int:
    """Number of connected raised regions, counting diagonal contact as connected."""
    if not mask.any():
        return 0
    _, count = ndimage.label(mask, structure=np.ones((3, 3), dtype=int))
    return int(count)
