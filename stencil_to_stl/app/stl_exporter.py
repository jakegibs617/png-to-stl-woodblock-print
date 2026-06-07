from __future__ import annotations

from pathlib import Path

import trimesh


def export_stl(mesh: trimesh.Trimesh, output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(output_file, file_type="stl")

