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

Print the calculated dimensions before export:

```bash
stencil-to-stl input.png output.stl --preview
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

# png-to-stl-woodblock-print
