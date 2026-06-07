# Stencil-to-STL Woodcut Generator

Generate a 3D-printable STL relief block from a black-and-transparent PNG stencil.

Transparent pixels become a rectangular base plate. Black or near-black pixels become raised print areas with a flat, consistent height. The image is mirrored horizontally by default because relief blocks print reversed onto paper.

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
  --scale 0.1 \
  --threshold 128 \
  --mirror
```

Disable mirroring:

```bash
stencil-to-stl input.png output.stl --no-mirror
```

Generate at a specific physical size, such as a 5 x 7 inch block:

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

## Defaults

```yaml
base_thickness_mm: 2.0
relief_height_mm: 1.5
pixel_to_mm_scale: 0.1
threshold: 128
mirror_x: true
output_units: millimeters
```

## Notes For Printmaking

Very thin raised lines may fail to print or break. A practical minimum raised feature width is usually 0.4-0.8 mm, depending on printer, resin/filament, paper, ink, and press pressure.

## Development

Run tests:

```bash
pytest
```

## Architecture Review

Current architecture:

- `stencil_to_stl/app/cli.py` owns argument parsing and CLI preview display.
- `stencil_to_stl/app/conversion.py` owns reusable conversion orchestration and structured metadata.
- `stencil_to_stl/app/image_loader.py` loads PNG files into RGBA arrays.
- `stencil_to_stl/app/mask_processor.py` converts RGBA pixels into a binary print mask and supports horizontal mirroring.
- `stencil_to_stl/app/mesh_builder.py` turns the mask into a `trimesh.Trimesh` relief block using merged run rectangles.
- `stencil_to_stl/app/stl_exporter.py` writes the mesh to an STL file.
- Tests cover image loading, masking, mirroring, basic dimensions, and watertight mesh output.

Observed gaps:

- There is no UI for loading a PNG. The project is currently CLI-only.
- Preview output is still text-only in the CLI, though structured metadata is available from the conversion service.
- Complex artwork can still produce non-watertight meshes in downstream mesh analysis and needs a dedicated manifold-surface pass.
- The local `.venv` may become invalid when the project folder moves because script shebangs can point to an old path.

Recommended architecture direction:

- Keep the CLI as a thin wrapper around the shared conversion service.
- Build the UI as another wrapper around the same service.
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
- Minimum feature width analysis for printmaking reliability.
- Optional cleanup tools such as despeckle, threshold preview, dilation, erosion, and smoothing.
- Export metadata alongside STL, such as settings and source image dimensions.
- Batch conversion for multiple PNG files.
- Cross-platform packaging as a small desktop app.

## Multi-Session Task List

A recommended machine-readable task list lives in `recommended_task_list.json`. It is designed to survive multiple work sessions with stable task IDs, priorities, dependencies, and completion fields.
