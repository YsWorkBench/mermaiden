from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from models import ClassInfo
from paths import find_import_root_for_file, normalize_path


def write_inventory(classes: Iterable[ClassInfo], output_file: Path, root_dir: Path) -> None:
    with output_file.open("w", encoding="utf-8") as f:
        f.write(f"# ROOT\t{root_dir}\n")
        f.write("# FQCN\tFILEPATH\tLINENO\tIMPORT_ROOT\n")
        for cls in sorted(classes, key=lambda c: c.fqcn):
            import_root = find_import_root_for_file(Path(cls.filepath))
            f.write(f"{cls.fqcn}\t{cls.filepath}\t{cls.lineno}\t{import_root}\n")


def read_inventory(
    inventory_file: Path,
) -> tuple[Path | None, list[tuple[str, Path, int, Path | None]]]:
    inventory_dir = inventory_file.parent.resolve()
    stored_root: Path | None = None
    rows: list[tuple[str, Path, int, Path | None]] = []

    with inventory_file.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("# ROOT\t"):
                root_str = line.split("\t", 1)[1]
                stored_root = normalize_path(root_str, inventory_dir)
                continue

            if line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) not in {3, 4}:
                print(f"[WARN] Ignoring malformed line: {line}")
                continue

            fqcn, path_text, lineno_text = parts[:3]
            import_root = normalize_path(parts[3], inventory_dir) if len(parts) == 4 else None

            try:
                lineno = int(lineno_text)
            except ValueError:
                print(f"[WARN] Invalid line number in line: {line}")
                continue

            filepath = normalize_path(path_text, inventory_dir)
            rows.append((fqcn, filepath, lineno, import_root))

    return stored_root, rows


def guess_root_from_inventory(
    stored_root: Path | None, rows: list[tuple[str, Path, int, Path | None]]
) -> Path | None:
    if stored_root is not None and stored_root.exists():
        return stored_root

    filepaths = [p for _, p, _, _ in rows if p.exists()]
    if not filepaths:
        return None

    try:
        return Path(os.path.commonpath([str(p.parent) for p in filepaths]))
    except ValueError:
        return None
