from __future__ import annotations

from pathlib import Path

from inventory import guess_root_from_inventory, read_inventory, write_inventory
from models import ClassInfo


def test_write_and_read_inventory_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    py_file = pkg / "a.py"
    py_file.write_text("class A:\n    pass\n", encoding="utf-8")

    classes = [
        ClassInfo(
            class_id="pkg_a_A",
            fqcn="pkg.a.A",
            module="pkg.a",
            qualname="A",
            name="A",
            filepath=str(py_file),
            lineno=1,
        )
    ]

    inv = tmp_path / "classes.txt"
    write_inventory(classes, inv, root)

    stored_root, rows = read_inventory(inv)
    assert stored_root == root
    assert len(rows) == 1
    fqcn, filepath, lineno, import_root = rows[0]
    assert fqcn == "pkg.a.A"
    assert filepath == py_file
    assert lineno == 1
    assert import_root == root


def test_read_inventory_skips_bad_lines(tmp_path: Path, capsys) -> None:
    inv = tmp_path / "bad.txt"
    inv.write_text(
        "# ROOT\t/root\n"
        "# HEADER\n"
        "bad\tline\n"
        "x.y.Z\t/tmp/z.py\tnotint\n"
        "x.y.Z\t/tmp/z.py\t10\n",
        encoding="utf-8",
    )

    _, rows = read_inventory(inv)
    assert len(rows) == 1
    assert rows[0][0] == "x.y.Z"

    out = capsys.readouterr().out
    assert "Ignoring malformed line" in out
    assert "Invalid line number" in out


def test_guess_root_from_inventory(tmp_path: Path) -> None:
    existing_root = tmp_path / "existing"
    existing_root.mkdir()

    file_a = tmp_path / "pkg" / "a.py"
    file_b = tmp_path / "pkg" / "sub" / "b.py"
    file_a.parent.mkdir(parents=True)
    file_b.parent.mkdir(parents=True)
    file_a.write_text("", encoding="utf-8")
    file_b.write_text("", encoding="utf-8")

    rows = [
        ("pkg.a.A", file_a, 1, None),
        ("pkg.sub.B", file_b, 1, None),
    ]

    assert guess_root_from_inventory(existing_root, rows) == existing_root
    guessed = guess_root_from_inventory(None, rows)
    assert guessed == (tmp_path / "pkg")
