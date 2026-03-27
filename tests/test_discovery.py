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


def test_discover_classes_namespace_from_root_includes_root_prefix(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / "mod.py").write_text("class A:\n    pass\n", encoding="utf-8")

    default_classes = {cls.fqcn for cls in discover_classes(root)}
    from_root_classes = {
        cls.fqcn for cls in discover_classes(root, namespace_from_root=True)
    }

    assert "mod.A" in default_classes
    assert "src.mod.A" in from_root_classes
    assert "mod.A" not in from_root_classes


def test_discover_classes_collects_non_inheritance_relations(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "deps.py").write_text(
        "class Service:\n    pass\n"
        "class Repo:\n    pass\n"
        "class Entity:\n    pass\n"
        "class Base:\n    pass\n",
        encoding="utf-8",
    )
    (pkg / "app.py").write_text(
        "from .deps import Base, Entity, Repo, Service\n"
        "class Child(Base):\n"
        "    class Internal:\n"
        "        pass\n"
        "    def __init__(self, repo: tuple(None, Repo), services: tuple(None, list[Service]) = None):\n"
        "        self.repo = repo\n"
        "        self.services = services\n"
        "        self.internal = [Internal() for _ in range(3)]\n"
        "    def run(self, entity: Entity) -> None:\n"
        "        return None\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    assert ("pkg.deps.Base", RelationType.INHERITANCE, "pkg.app.Child") in rels
    assert ("pkg.app.Child", RelationType.AGGREGATION, "pkg.deps.Repo") in rels
    assert ("pkg.app.Child", RelationType.AGGREGATION, "pkg.deps.Service") in rels
    assert ("pkg.deps.Entity", RelationType.ASSOCIATION, "pkg.app.Child") in rels
    assert ("pkg.app.Child", RelationType.COMPOSITION, "pkg.app.Child.Internal") in rels


def test_discover_classes_collects_class_level_associations(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "deps.py").write_text("class Service:\n    pass\n", encoding="utf-8")
    (pkg / "app.py").write_text(
        "from .deps import Service\n"
        "class Child:\n"
        "    service: Service = Service\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    assert ("pkg.deps.Service", RelationType.ASSOCIATION, "pkg.app.Child") in rels


def test_discover_classes_handles_pydantic_configdict_and_annotated_metadata(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text(
        "class ConfigDict:\n    pass\n"
        "class Field:\n    pass\n"
        "class Service:\n    pass\n"
        "class MyModel:\n"
        "    model_config = ConfigDict(from_attributes=True)\n"
        "    dep: Annotated[Service, Field] = Service\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    model = classes["pkg.app.MyModel"]
    model_attrs = {(attr.name, attr.type_name) for attr in model.attributes}
    assert ("model_config", "ConfigDict") not in model_attrs
    assert ("dep", "Service") in model_attrs
    assert ("pkg.app.Service", RelationType.ASSOCIATION, "pkg.app.MyModel") in rels
    assert (
        "pkg.app.ConfigDict",
        RelationType.ASSOCIATION,
        "pkg.app.MyModel",
    ) not in rels
    assert ("pkg.app.Field", RelationType.ASSOCIATION, "pkg.app.MyModel") not in rels


def test_discover_classes_parses_quoted_forward_ref_attribute_types(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text(
        "class Field:\n    pass\n"
        "class dummy_composition:\n    pass\n"
        "class dummy:\n"
        "    composition: Optional[List['dummy.dummy_composition']] = Field(...)\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    dummy_cls = classes["pkg.app.dummy"]
    attr_pairs = {(attr.name, attr.type_name) for attr in dummy_cls.attributes}
    assert (
        "pkg.app.dummy",
        RelationType.AGGREGATION,
        "pkg.app.dummy_composition",
    ) in rels
    assert ("pkg.app.Field", RelationType.ASSOCIATION, "pkg.app.dummy") not in rels
    assert any(name == "composition" for name, _ in attr_pairs)


def test_discover_classes_class_attribute_default_factory_implies_composition(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text(
        "class Field:\n    pass\n"
        "class Item:\n    pass\n"
        "class Holder:\n"
        "    items: list[Item] = Field(default_factory=lambda: [Item()])\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    assert ("pkg.app.Holder", RelationType.COMPOSITION, "pkg.app.Item") in rels


def test_discover_classes_resolves_literal_enum_member_via_import_alias(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "types.py").write_text(
        "class OrderedEnum:\n    pass\n"
        "class DummyTypeEnum(OrderedEnum):\n"
        "    DummyComposition = 1\n",
        encoding="utf-8",
    )
    (pkg / "app.py").write_text(
        "from .types import DummyTypeEnum as DT\n"
        "class Holder:\n"
        "    kind: Literal[DT.DummyComposition] = DT.DummyComposition\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    assert (
        "pkg.types.DummyTypeEnum",
        RelationType.ASSOCIATION,
        "pkg.app.Holder",
    ) in rels


def test_discover_classes_resolves_quoted_alias_reference_to_imported_class(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "types.py").write_text(
        "class OrderedEnum:\n    pass\n"
        "class DummyTypeEnum(OrderedEnum):\n"
        "    DummyComposition = 1\n",
        encoding="utf-8",
    )
    (pkg / "app.py").write_text(
        "from .types import DummyTypeEnum as DT\n"
        "class Holder:\n"
        "    kind: 'DT.DummyComposition' = DT.DummyComposition\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))

    assert (
        "pkg.types.DummyTypeEnum",
        RelationType.ASSOCIATION,
        "pkg.app.Holder",
    ) in rels


def test_discover_classes_follow_init_py_flattens_namespaces(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    subpkg = pkg / "subpkg"
    subpkg.mkdir(parents=True)

    (pkg / "__init__.py").write_text("from .subpkg import *\n", encoding="utf-8")
    (subpkg / "__init__.py").write_text(
        "from .defs import Exported\n", encoding="utf-8"
    )
    (subpkg / "defs.py").write_text("class Exported:\n    pass\n", encoding="utf-8")
    (pkg / "consumer.py").write_text(
        "class Consumer:\n"
        "    def __init__(self, dep: Exported):\n"
        "        self.dep = dep\n",
        encoding="utf-8",
    )

    path_classes = {cls.fqcn: cls for cls in discover_classes(root, follow="path")}
    assert "pkg.subpkg.defs.Exported" in path_classes

    init_classes = {cls.fqcn: cls for cls in discover_classes(root, follow="init.py")}
    assert "pkg.Exported" in init_classes
    assert "pkg.subpkg.defs.Exported" not in init_classes

    rels = set(collect_all_relations(init_classes))
    assert ("pkg.Exported", RelationType.ASSOCIATION, "pkg.consumer.Consumer") in rels


def test_resolve_target_name_and_merge_relation() -> None:
    cls_a = ClassInfo("A", "pkg.A", "pkg", "A", "A", "a.py", 1)
    cls_b = ClassInfo("B", "pkg.B", "pkg", "B", "B", "b.py", 1)
    known = {"pkg.A": cls_a, "pkg.B": cls_b}

    assert resolve_target_name("pkg.B", cls_a, known) == "pkg.B"
    assert resolve_target_name("B", cls_a, known) == "pkg.B"
    assert resolve_target_name("Missing", cls_a, known) is None

    assert (
        merge_relation(RelationType.ASSOCIATION, RelationType.COMPOSITION)
        == RelationType.COMPOSITION
    )
    assert (
        merge_relation(RelationType.INHERITANCE, RelationType.ASSOCIATION)
        == RelationType.INHERITANCE
    )


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


def test_collect_all_relations_uses_realization_for_abstract_bases() -> None:
    contract = ClassInfo(
        "pkg_Contract",
        "pkg.Contract",
        "pkg",
        "Contract",
        "Contract",
        "a.py",
        1,
        bases=["ABC"],
    )
    impl = ClassInfo(
        "pkg_Impl",
        "pkg.Impl",
        "pkg",
        "Impl",
        "Impl",
        "a.py",
        2,
        bases=["Contract"],
    )

    rels = collect_all_relations({"pkg.Contract": contract, "pkg.Impl": impl})
    assert ("pkg.Impl", RelationType.REALIZATION, "pkg.Contract") in rels


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
