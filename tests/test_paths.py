from __future__ import annotations

from pathlib import Path

from paths import (
    common_existing_parent,
    compute_module_name,
    compute_module_name_from_packages,
    find_import_root_for_file,
    find_package_anchor,
    is_package_dir,
    normalize_path,
    parse_python_file,
)


def test_normalize_path_relative_and_absolute(tmp_path: Path) -> None:
    rel = normalize_path("x/y.py", tmp_path)
    assert rel == (tmp_path / "x/y.py").resolve()

    abs_path = (tmp_path / "z.py").resolve()
    assert normalize_path(abs_path) == abs_path


def test_package_helpers_and_module_resolution(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    sub = pkg / "sub"
    sub.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (sub / "__init__.py").write_text("", encoding="utf-8")
    target = sub / "mod.py"
    target.write_text("class A:\n    pass\n", encoding="utf-8")

    assert is_package_dir(pkg)
    assert find_package_anchor(target) == pkg
    assert find_import_root_for_file(target) == root
    assert compute_module_name_from_packages(target) == "pkg.sub.mod"
    assert compute_module_name(root, target) == "pkg.sub.mod"


def test_compute_module_name_for_init_file(tmp_path: Path) -> None:
    root = tmp_path / "root"
    pkg = root / "myapp"
    pkg.mkdir(parents=True)
    init_file = pkg / "__init__.py"
    init_file.write_text("", encoding="utf-8")

    assert compute_module_name_from_packages(init_file) == "myapp"


def test_parse_python_file_success_and_failure(tmp_path: Path, capsys) -> None:
    good = tmp_path / "ok.py"
    bad = tmp_path / "bad.py"
    good.write_text("x = 1\n", encoding="utf-8")
    bad.write_text("def oops(:\n", encoding="utf-8")

    assert parse_python_file(good) is not None
    assert parse_python_file(bad) is None

    captured = capsys.readouterr()
    assert "[WARN] Skipping" in captured.out


def test_common_existing_parent(tmp_path: Path) -> None:
    p1 = tmp_path / "a" / "x.py"
    p2 = tmp_path / "a" / "b" / "y.py"
    p1.parent.mkdir(parents=True)
    p2.parent.mkdir(parents=True)
    p1.write_text("", encoding="utf-8")
    p2.write_text("", encoding="utf-8")

    parent = common_existing_parent([p1, p2, tmp_path / "missing.py"])
    assert parent == (tmp_path / "a")

    assert common_existing_parent([tmp_path / "none.py"]) is None
