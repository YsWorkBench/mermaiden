from __future__ import annotations

from pathlib import Path

from discovery import (
    collect_all_relations,
    discover_classes,
    merge_relation,
    rebuild_class_map_from_inventory,
    resolve_target_name,
)
from inventory import write_inventory
from models import ClassInfo, Relation, RelationType


def test_discover_classes_and_basic_shapes(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text(
        "class Base:\n    pass\n"
        "class Child(Base):\n"
        "    def run(self, x: int) -> str:\n"
        "        return str(x)\n",
        encoding="utf-8",
    )

    classes = discover_classes(root)
    fqcns = {c.fqcn for c in classes}
    assert "pkg.a.Base" in fqcns
    assert "pkg.a.Child" in fqcns


def test_resolve_target_name_and_merge_relation() -> None:
    cls_a = ClassInfo("A", "pkg.A", "pkg", "A", "A", "a.py", 1)
    cls_b = ClassInfo("B", "pkg.B", "pkg", "B", "B", "b.py", 1)
    known = {"pkg.A": cls_a, "pkg.B": cls_b}

    assert resolve_target_name("pkg.B", cls_a, known) == "pkg.B"
    assert resolve_target_name("B", cls_a, known) == "pkg.B"
    assert resolve_target_name("Missing", cls_a, known) is None

    assert merge_relation(RelationType.ASSOCIATION, RelationType.COMPOSITION) == RelationType.COMPOSITION
    assert merge_relation(RelationType.INHERITANCE, RelationType.ASSOCIATION) == RelationType.INHERITANCE


def test_collect_all_relations_resolves_inheritance_and_association() -> None:
    base = ClassInfo("pkg_Base", "pkg.Base", "pkg", "Base", "Base", "a.py", 1)
    child = ClassInfo(
        "pkg_Child",
        "pkg.Child",
        "pkg",
        "Child",
        "Child",
        "a.py",
        2,
        bases=["Base"],
        relations=[Relation("pkg.Child", "Base", RelationType.ASSOCIATION)],
    )

    rels = collect_all_relations({"pkg.Base": base, "pkg.Child": child})
    assert ("pkg.Base", RelationType.INHERITANCE, "pkg.Child") in rels


def test_rebuild_class_map_from_inventory(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    mod = pkg / "mod.py"
    mod.write_text("class A:\n    pass\n", encoding="utf-8")

    discovered = discover_classes(root)
    inv = tmp_path / "classes.txt"
    write_inventory(discovered, inv, root)

    rebuilt = rebuild_class_map_from_inventory(inv)
    assert "pkg.mod.A" in rebuilt
    assert rebuilt["pkg.mod.A"].name == "A"
