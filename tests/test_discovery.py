from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

import pytest

import discovery as discovery_module
from discovery import (
    _expand_target_candidates,
    _namespace_prefix_matches,
    _parse_import_aliases,
    _parse_init_exports,
    _remap_classes_follow_init,
    _resolve_import_target,
    collect_all_relations,
    discover_classes,
    merge_relation,
    rebuild_class_map_from_inventory,
    RelationCollector,
    resolve_target_name,
    should_treat_base_as_realization,
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


def test_constructor_targets_from_value_covers_composite_nodes() -> None:
    parse_expr = lambda expr: ast.parse(expr, mode="eval").body

    assert RelationCollector._constructor_targets_from_value(None) == set()
    assert RelationCollector._constructor_targets_from_value(
        parse_expr("{KeyCtor(): ValueCtor()}")
    ) == {"KeyCtor", "ValueCtor"}
    assert RelationCollector._constructor_targets_from_value(
        parse_expr("{SetItem() for _ in seq}")
    ) == {"SetItem"}
    assert RelationCollector._constructor_targets_from_value(
        parse_expr("{KeyItem(k): ValueItem(v) for k, v in seq}")
    ) == {"KeyItem", "ValueItem"}
    assert RelationCollector._constructor_targets_from_value(
        parse_expr("(GenItem() for _ in seq)")
    ) == {"GenItem"}
    assert RelationCollector._constructor_targets_from_value(
        parse_expr("WhenTrue() if cond else WhenFalse()")
    ) == {"WhenTrue", "WhenFalse"}


def test_discover_classes_covers_init_annassign_and_method_associations(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text(
        "class Dep:\n    pass\n"
        "class Other:\n    pass\n"
        "class Holder:\n"
        "    def __init__(self, *items: list[Dep], dep: list[Dep], **more: Dep):\n"
        "        self.count = 1\n"
        "        self.typed_count: int = 1\n"
        "        self.comp: Dep = Dep()\n"
        "        self.agg: list[Dep] = dep\n"
        "        self.extra: Dep = more\n"
        "    def run(self) -> None:\n"
        "        local: Dep = Dep()\n"
        "        Other()\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))
    holder_raw_relations = {
        (rel.target_name, rel.relation_type)
        for rel in classes["pkg.app.Holder"].relations
    }

    assert ("pkg.app.Holder", RelationType.COMPOSITION, "pkg.app.Dep") in rels
    assert ("Dep", RelationType.AGGREGATION) in holder_raw_relations
    assert ("pkg.app.Dep", RelationType.ASSOCIATION, "pkg.app.Holder") in rels
    assert ("pkg.app.Other", RelationType.ASSOCIATION, "pkg.app.Holder") in rels


def test_discover_classes_class_annassign_infers_type_and_skips_model_config(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "app.py").write_text(
        "class ConfigDict:\n    pass\n"
        "class Child:\n    pass\n"
        "class Model:\n"
        "    model_config: ConfigDict = ConfigDict()\n"
        "    inferred: (lambda v: v) = Child()\n",
        encoding="utf-8",
    )

    classes = {cls.fqcn: cls for cls in discover_classes(root)}
    rels = set(collect_all_relations(classes))
    model = classes["pkg.app.Model"]
    attrs = {(attr.name, attr.type_name) for attr in model.attributes}

    assert ("inferred", "Child") in attrs
    assert ("pkg.app.Model", RelationType.COMPOSITION, "pkg.app.Child") in rels
    assert (
        "pkg.app.ConfigDict",
        RelationType.ASSOCIATION,
        "pkg.app.Model",
    ) not in rels


def test_namespace_and_import_target_helpers_cover_edge_cases() -> None:
    assert _namespace_prefix_matches("pkg.module", "") is True
    assert _resolve_import_target("pkg.module", None, -1) is None
    assert _resolve_import_target("pkg", None, 3) is None
    assert _resolve_import_target("pkg.module", "target.mod", 0) == "target.mod"
    assert _resolve_import_target("pkg.module", None, 0) is None


def test_parse_import_aliases_and_expand_candidates_cover_alias_edge_cases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pkg_file = tmp_path / "pkg_file.py"
    pkg_file.write_text(
        "import pkg.mod as pm\n"
        "import plain.module\n"
        "from .sub import Thing as AliasThing\n"
        "from .star import *\n",
        encoding="utf-8",
    )

    aliases = _parse_import_aliases("pkg.pkg_file", pkg_file)
    assert aliases["pm"] == "pkg.mod"
    assert aliases["plain"] == "plain.module"
    assert aliases["AliasThing"] == "pkg.sub.Thing"
    assert "*" not in aliases

    top_file = tmp_path / "top.py"
    top_file.write_text("from . import Local\n", encoding="utf-8")
    top_aliases = _parse_import_aliases("", top_file)
    assert top_aliases["Local"] == "Local"

    top_cls = ClassInfo("Top", "Top", "", "Top", "Top", str(top_file), 1)
    assert _expand_target_candidates("  ", top_cls) == []
    assert _expand_target_candidates("Local", top_cls) == ["Local"]

    alias_file = tmp_path / "alias_file.py"
    alias_file.write_text(
        "from .types import DummyTypeEnum as DT\n",
        encoding="utf-8",
    )
    alias_cls = ClassInfo(
        "Alias",
        "pkg.alias_file.Alias",
        "pkg.alias_file",
        "Alias",
        "Alias",
        str(alias_file),
        1,
    )
    assert "pkg.types.DummyTypeEnum.Member" in _expand_target_candidates(
        "DT.Member", alias_cls
    )

    weird_file = tmp_path / "weird.py"
    weird_file.write_text("from pkg import AnyName\n", encoding="utf-8")
    real_parse: Callable[[Path], ast.AST | None] = discovery_module.parse_python_file

    def fake_parse(path: Path) -> ast.AST | None:
        if path == weird_file:
            return ast.Name(id="x")
        return real_parse(path)

    monkeypatch.setattr(discovery_module, "parse_python_file", fake_parse)
    assert _parse_import_aliases("pkg.weird", weird_file) == {}

    fake_cls = ClassInfo(
        "Fake",
        "pkg.Fake",
        "pkg",
        "Fake",
        "Fake",
        str(pkg_file),
        1,
    )

    monkeypatch.setattr(
        discovery_module,
        "_parse_import_aliases",
        lambda module_name, filepath: {"Q.Y": "Q.Y.Z"},
    )
    candidates = _expand_target_candidates("Q.Y", fake_cls)
    assert candidates == ["Q.Y", "Q", "Q.Y.Z"]


def test_parse_init_exports_and_remap_cover_skip_and_ambiguous_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        "VALUE = 1\n" "from .mod import Exported\n" "from .shared import *\n",
        encoding="utf-8",
    )
    (pkg / "mod.py").write_text("class Exported:\n    pass\n", encoding="utf-8")

    skipped = root / ".venv" / "fakepkg"
    skipped.mkdir(parents=True)
    (skipped / "__init__.py").write_text("from .mod import Hidden\n", encoding="utf-8")

    broken = root / "broken"
    broken.mkdir(parents=True)
    (broken / "__init__.py").write_text("from .mod import (\n", encoding="utf-8")

    exports = _parse_init_exports(root)
    assert exports["pkg"]["explicit"] == {"Exported"}
    assert exports["pkg"]["star"] == {"pkg.shared"}
    assert all(".venv" not in key for key in exports)

    special_root = tmp_path / "special"
    special_pkg = special_root / "spkg"
    special_pkg.mkdir(parents=True)
    init_file = special_pkg / "__init__.py"
    init_file.write_text("from .mod import A\n", encoding="utf-8")

    real_parse: Callable[[Path], ast.AST | None] = discovery_module.parse_python_file

    def fake_parse(path: Path) -> ast.AST | None:
        if path == init_file:
            return ast.Name(id="x")
        return real_parse(path)

    monkeypatch.setattr(discovery_module, "parse_python_file", fake_parse)
    assert _parse_init_exports(special_root) == {}

    plain_classes = [
        ClassInfo("C", "pkg.mod.C", "pkg.mod", "C", "C", str(pkg / "mod.py"), 1)
    ]
    no_init_root = tmp_path / "no_init"
    no_init_root.mkdir()
    assert (
        _remap_classes_follow_init(plain_classes, no_init_root, style="flat")
        is plain_classes
    )

    amb_root = tmp_path / "ambiguous"
    amb_pkg = amb_root / "pkg"
    amb_pkg.mkdir(parents=True)
    (amb_pkg / "__init__.py").write_text(
        "from .a import Duplicate\n" "from .b import Duplicate\n",
        encoding="utf-8",
    )
    (amb_pkg / "a.py").write_text("class Duplicate:\n    pass\n", encoding="utf-8")
    (amb_pkg / "b.py").write_text("class Duplicate:\n    pass\n", encoding="utf-8")

    remapped = {cls.fqcn for cls in discover_classes(amb_root, follow="init.py")}
    assert "pkg.a.Duplicate" in remapped
    assert "pkg.b.Duplicate" in remapped
    assert "pkg.Duplicate" not in remapped


def test_discover_classes_skips_excluded_paths_syntax_errors_and_bad_follow(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    root.mkdir(parents=True)
    (root / "ok.py").write_text("class Visible:\n    pass\n", encoding="utf-8")
    (root / "bad.py").write_text("class Broken(:\n    pass\n", encoding="utf-8")
    skipped = root / ".venv"
    skipped.mkdir()
    (skipped / "hidden.py").write_text("class Hidden:\n    pass\n", encoding="utf-8")

    classes = {cls.fqcn for cls in discover_classes(root)}
    assert "ok.Visible" in classes
    assert all("Hidden" not in fqcn for fqcn in classes)

    with pytest.raises(ValueError, match="Unsupported follow mode"):
        discover_classes(root, follow="invalid")


def test_should_treat_base_as_realization_and_self_relations() -> None:
    assert (
        should_treat_base_as_realization("SomeProtocol", "pkg.SomeProtocol", {}) is True
    )
    assert should_treat_base_as_realization("Concrete", "pkg.Concrete", {}) is False

    self_ref = ClassInfo(
        "pkg_A",
        "pkg.A",
        "pkg",
        "A",
        "A",
        "a.py",
        1,
        relations=[Relation("pkg.A", "A", RelationType.ASSOCIATION)],
    )
    assert collect_all_relations({"pkg.A": self_ref}) == []


def test_rebuild_class_map_handles_empty_and_missing_inventory_entries(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    empty_inventory = tmp_path / "empty.txt"
    empty_inventory.write_text("# ROOT\t.\n# FQCN\tFILEPATH\tLINENO\tIMPORT_ROOT\n")
    assert rebuild_class_map_from_inventory(empty_inventory) == {}

    missing_inventory = tmp_path / "missing.txt"
    missing_inventory.write_text(
        "# ROOT\t.\n"
        "# FQCN\tFILEPATH\tLINENO\tIMPORT_ROOT\n"
        "pkg.mod.Missing\t./does_not_exist.py\t1\t.\n",
        encoding="utf-8",
    )
    assert rebuild_class_map_from_inventory(missing_inventory) == {}
    assert "None of the inventory file paths currently exist" in capsys.readouterr().out


def test_rebuild_class_map_covers_fallback_matching_and_warnings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")

    mod = pkg / "mod.py"
    mod.write_text(
        "class Real:\n"
        "    pass\n"
        "class Outer:\n"
        "    class Inner:\n"
        "        pass\n",
        encoding="utf-8",
    )
    empty = pkg / "empty.py"
    empty.write_text("# no classes\n", encoding="utf-8")
    bad = pkg / "bad.py"
    bad.write_text("class Broken(:\n    pass\n", encoding="utf-8")

    inv = tmp_path / "complex_inventory.txt"
    inv.write_text(
        f"# ROOT\t{root}\n"
        "# FQCN\tFILEPATH\tLINENO\tIMPORT_ROOT\n"
        f"pkg.mod.Real\t{mod}\t1\t{root}\n"
        f"pkg.mod.Real\t{mod}\t1\t{root}\n"
        f"pkg.alias.Real\t{mod}\t1\t{root}\n"
        f"Real\t{mod}\t1\t{root}\n"
        f"pkg.alias.Inner\t{mod}\t1\t{root}\n"
        f"Inner\t{mod}\t1\t{root}\n"
        f"pkg.unknown.Missing\t{mod}\t1\t{root}\n"
        f"pkg.empty.Nothing\t{empty}\t1\t{root}\n"
        f"pkg.bad.Broken\t{bad}\t1\t{root}\n"
        f"pkg.missing.Miss\t{pkg / 'missing.py'}\t1\t{root}\n",
        encoding="utf-8",
    )

    rebuilt = rebuild_class_map_from_inventory(inv)
    logs = capsys.readouterr().out

    assert "pkg.mod.Real" in rebuilt
    assert "pkg.alias.Real" in rebuilt
    assert "Real" in rebuilt
    assert "pkg.alias.Inner" in rebuilt
    assert "Inner" in rebuilt
    assert rebuilt["Real"].module == ""
    assert rebuilt["pkg.alias.Inner"].module == "pkg.alias"
    assert rebuilt["Inner"].module == ""
    assert (
        "Could not safely rebuild class from inventory entry: pkg.unknown.Missing"
        in logs
    )
