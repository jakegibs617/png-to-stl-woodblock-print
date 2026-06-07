import numpy as np

from stencil_to_stl.app.mask_processor import black_pixel_mask, fill_diagonal_contacts, horizontal_runs, mirror_mask_x


def test_black_pixel_mask_requires_alpha_and_black_threshold() -> None:
    rgba = np.array(
        [
            [[0, 0, 0, 255], [10, 10, 10, 0], [200, 0, 0, 255]],
            [[127, 127, 127, 255], [128, 128, 128, 255], [1, 1, 1, 255]],
        ],
        dtype=np.uint8,
    )

    mask = black_pixel_mask(rgba, threshold=128)

    assert mask.tolist() == [
        [True, False, False],
        [True, False, True],
    ]


def test_mirror_mask_x_flips_columns() -> None:
    mask = np.array([[True, False, False], [False, True, False]])

    mirrored = mirror_mask_x(mask)

    assert mirrored.tolist() == [[False, False, True], [False, True, False]]


def test_horizontal_runs_groups_contiguous_pixels_by_row() -> None:
    mask = np.array(
        [
            [False, True, True, False, True],
            [True, True, False, False, False],
        ]
    )

    runs = horizontal_runs(mask)

    assert [(run.row, run.start_x, run.end_x) for run in runs] == [
        (0, 1, 2),
        (0, 4, 4),
        (1, 0, 1),
    ]


def test_fill_diagonal_contacts_closes_checkerboard_pinches() -> None:
    mask = np.array(
        [
            [True, False],
            [False, True],
        ],
        dtype=bool,
    )

    assert fill_diagonal_contacts(mask).tolist() == [
        [True, True],
        [True, True],
    ]
