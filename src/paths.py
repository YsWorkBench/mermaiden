"""Path and module-resolution utilities for package-aware source analysis."""

from __future__ import annotations

import ast
import os
from pathlib import Path


def normalize_path(path_str: str | Path, base_dir: Path | None = None) -> Path:
    """Resolve a path string against an optional base directory."""
    p = Path(path_str)
    if not p.is_absolute():
        p = (base_dir / p if base_dir else p).resolve()
    else:
        p = p.resolve()
    return p


def is_package_dir(path: Path) -> bool:
    """Return True when a directory is a Python package."""
    return path.is_dir() and (path / "__init__.py").exists()


def find_package_anchor(filepath: Path) -> Path:
    """Find the highest directory in the contiguous package chain."""
    current_dir = filepath.parent
    highest_package = None

    while is_package_dir(current_dir):
        highest_package = current_dir
        parent = current_dir.parent
        if parent == current_dir:
            break
        current_dir = parent

    return highest_package if highest_package is not None else filepath.parent


def find_import_root_for_file(filepath: Path) -> Path:
    """Return the filesystem directory that should act as import root."""
    package_anchor = find_package_anchor(filepath)
    if is_package_dir(package_anchor):
        return package_anchor.parent
    return filepath.parent


def compute_module_name_from_packages(
    filepath: Path, fallback_root: Path | None = None
) -> str:
    """Compute module name while respecting package boundaries."""
    import_root = find_import_root_for_file(filepath)

    if fallback_root is not None:
        try:
            filepath.relative_to(fallback_root)
            try:
                import_root.relative_to(fallback_root)
                chosen_root = fallback_root
            except ValueError:
                chosen_root = import_root
        except ValueError:
            chosen_root = import_root
    else:
        chosen_root = import_root

    rel = filepath.relative_to(chosen_root).with_suffix("")
    parts = list(rel.parts)

    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts) if parts else filepath.stem


def parse_python_file(filepath: Path) -> ast.AST | None:
    """Parse a Python file into an AST, returning None on parse errors."""
    try:
        return ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        print(f"[WARN] Skipping {filepath}: {exc}")
        return None


def compute_module_name(root_dir: Path, filepath: Path) -> str:
    """Compute module name using package-aware resolution."""
    return compute_module_name_from_packages(filepath, root_dir)


def common_existing_parent(paths: list[Path]) -> Path | None:
    """Return common parent for existing paths, if one can be determined."""
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    try:
        return Path(os.path.commonpath([str(p) for p in existing]))
    except ValueError:
        return None
