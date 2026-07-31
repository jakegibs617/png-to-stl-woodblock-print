# Stencil-to-STL Woodcut Generator

Generate a 3D-printable STL relief block from a black-and-transparent PNG stencil.

Transparent pixels become a rectangular base plate. Black or near-black pixels become raised print areas with a flat, consistent height. The image is mirrored horizontally by default because relief blocks print reversed onto paper.

Raised features are measured for printability, grown when they are too narrow to survive, and given a chamfered root so they do not snap off the plate. See [Thin Line Support](#thin-line-support).

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[test]"
```

## Usage

```bash
stencil-to-stl input.png output.stl \
  --base-thickness 2.0 \
  --relief-height 1.5 \
  --threshold 128 \
  --mirror
```

When the PNG includes DPI metadata, the STL uses the PNG's physical dimensions. If
the PNG has no physical size metadata, `--scale` controls millimeters per source
pixel.

Disable mirroring:

```bash
stencil-to-stl input.png output.stl --no-mirror
```

Override the PNG physical size, such as forcing a 5 x 7 inch block:

```bash
stencil-to-stl input.png output.stl --width-in 5 --height-in 7
```

Print the calculated dimensions before export:

```bash
stencil-to-stl input.png output.stl --preview
```

Preview conversion metadata without exporting an STL:

```bash
stencil-to-stl input.png output.stl --preview-only
```

Start the local browser UI:

```bash
stencil-to-stl-web
```

Then open `http://127.0.0.1:8765`.

## Defaults

```yaml
base_thickness_mm: 2.0
relief_height_mm: 1.5
pixel_to_mm_scale: 0.1
threshold: 128
mirror_x: true
min_feature_width_mm: 0.8
chamfer_height_mm: 0.5
widen_thin_features: true
output_units: millimeters
```

## Thin Line Support

A raised line is a cantilevered wall. Bending stress at its root grows with the
square of its height-to-width ratio, which is why fine detail snaps off a relief
block while thick areas survive. Two different failures come out of that, and
they need different answers.

**Too narrow to exist.** Below roughly one extrusion width the printer cannot lay
the line down at all, and no amount of geometry recovers it. Features narrower
than `--min-feature-width` are therefore grown until they are printable. Only the
narrow material grows; artwork already wide enough is left untouched. Widening can
close a narrow gap and fuse two features into one, so the run reports how many
features merged. Use `--no-widen` to measure and report without changing artwork.

**Wide enough to print, weak enough to break.** Every raised feature gets a 45
degree chamfer at its root, adding material exactly where the bending moment
peaks and removing the square notch the wall would otherwise meet the plate with.
The chamfer is capped at `--chamfer-height` rather than running the full relief,
so where two features are close enough for their skirts to meet, the valley
between them still keeps `relief_height - chamfer_height` of ink clearance. The
top surface is untouched: every raised face keeps the exact footprint of the
artwork and all inked surfaces stay coplanar. Use `--no-chamfer` to opt out.

```bash
stencil-to-stl input.png output.stl --min-feature-width 0.8 --chamfer-height 0.5
stencil-to-stl input.png output.stl --no-widen --no-chamfer
```

`--preview` reports the narrowest feature found, how much of the raised area falls
below the minimum, how many pixels widening added, and how many features merged.

## Notes For Printmaking

The 0.8 mm default is two passes of a 0.4 mm nozzle. One pass is the least an FDM
printer can lay down at all; two is the least that holds together once the block
is inked and pressed. A practical minimum runs 0.4-0.8 mm depending on printer,
resin/filament, paper, ink, and press pressure.

Feature width is measured in every direction, not just horizontally, using a
morphological opening. Width is reported along the medial ridge of each feature,
so a tapering tip or the sharp corner of an otherwise healthy shape is not
mistaken for a thin line. Anything past the edge of the image counts as empty, so
a feature running off the block edge is measured at its true width.

## Development

Run tests:

```bash
pytest
```

## Architecture Review

Current architecture:

- `stencil_to_stl/app/cli.py` owns argument parsing and CLI preview display.
- `stencil_to_stl/app/conversion.py` owns reusable conversion orchestration and structured metadata.
- `stencil_to_stl/app/web.py` serves the local browser UI and download endpoint.
- `stencil_to_stl/app/image_loader.py` loads PNG files into RGBA arrays.
- `stencil_to_stl/app/mask_processor.py` converts RGBA pixels into a binary print mask and supports horizontal mirroring.
- `stencil_to_stl/app/feature_analysis.py` measures feature width and grows anything too narrow to print.
- `stencil_to_stl/app/height_field.py` turns the mask into per-cell heights, adding the chamfered root.
- `stencil_to_stl/app/mesh_builder.py` turns a height field into a watertight `trimesh.Trimesh` block.
- `stencil_to_stl/app/stl_exporter.py` writes the mesh to an STL file.
- Tests cover image loading, masking, mirroring, feature measurement, widening, chamfer geometry, resampling fidelity, dimensions, and watertight mesh output.

Observed gaps:

- The local browser UI is intentionally simple and still lacks a 3D mesh preview.
- Preview output is still text-only in the CLI, though the browser UI displays structured metadata after generation.
- Coplanar cells are not merged into larger rectangles, so meshes stay heavier than they need to be. Doing so introduces T-junctions against the per-cell wall tops and needs its own manifold-safe pass.
- The local `.venv` may become invalid when the project folder moves because script shebangs can point to an old path.

Recommended architecture direction:

- Keep the CLI as a thin wrapper around the shared conversion service.
- Keep the UI as another wrapper around the same service.
- Continue optimizing mesh generation and watertightness before relying on the UI for large images.
- Keep automated tests around the shared conversion service so CLI and UI behavior stay aligned.

## Security Considerations

Primary risks:

- User-provided PNG files can be malformed, extremely large, or intentionally expensive to process.
- Very large masks can produce excessive mesh geometry and exhaust memory or CPU.
- Output paths from CLI arguments should remain explicit and should not silently overwrite unrelated files without user intent.
- A future web UI must avoid exposing arbitrary filesystem reads or writes.
- If the app becomes hosted, uploaded images and generated STL files should be treated as sensitive user data.

Recommended mitigations:

- Enforce maximum image dimensions or maximum pixel count before mesh generation.
- Add clear validation for file type, image mode, alpha channel behavior, and empty masks.
- Add geometry complexity estimates before export.
- Use temporary files for uploaded UI inputs and generated downloads.
- Keep UI output scoped to generated STL downloads rather than arbitrary server paths.
- Avoid shelling out with user-provided paths or arguments.
- Add dependency scanning once the project is prepared for release.

## High Priority Next Steps

1. Recreate the Python virtual environment and verify `pip install -e ".[test]"`.
2. Run the full test suite and fix any environment-independent failures.
3. Extract shared conversion logic from `cli.py` into a service module.
4. Add structured conversion metadata: image size, physical size, raised pixel count, estimated mesh size, total height, and warnings.
5. Add input limits for image dimensions and pixel count.
6. Optimize mesh generation using row runs or rectangle merging.
7. Add a basic UI for PNG upload, parameter controls, preview metadata, and STL download.
8. Add integration tests for CLI and conversion service behavior.

## Nice To Have Features

- Mask preview before export.
- Side-by-side original and processed preview.
- 3D mesh preview in the UI.
- Presets for common print sizes such as 4x6, 5x7, and postcard dimensions.
- Automatic scale calculation from desired physical width or height.
- Optional cleanup tools such as despeckle, threshold preview, and smoothing.
- Export metadata alongside STL, such as settings and source image dimensions.
- Batch conversion for multiple PNG files.
- Cross-platform packaging as a small desktop app.

## Multi-Session Task List

A recommended machine-readable task list lives in `recommended_task_list.json`. It is designed to survive multiple work sessions with stable task IDs, priorities, dependencies, and completion fields.
