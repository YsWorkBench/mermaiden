from __future__ import annotations

import argparse
import ast
from pathlib import Path

import pytest

import mermaiden as mermaiden_module
from mermaiden import build_parser, cmd_diagram, cmd_discover, cmd_generate
from models import ClassInfo, RelationType


def test_mermaiden_module_is_parseable() -> None:
    source = Path("src/mermaiden.py").read_text(encoding="utf-8")
    ast.parse(source)


def test_build_parser_from_cli_namespace() -> None:
    parser = build_parser()
    args = parser.parse_args(["discover", "./src"])
    args_follow_init = parser.parse_args(["discover", "./src", "--follow", "init.py"])
    args_from_root = parser.parse_args(["discover", "./src", "--namespace-from-root"])
    diagram_aliases_default = parser.parse_args(["diagram", "classes.txt"])
    diagram_aliases_on = parser.parse_args(["diagram", "classes.txt", "--aliases"])
    diagram_title = parser.parse_args(["diagram", "classes.txt", "--title", "My UML"])
    diagram_output_alias = parser.parse_args(
        ["diagram", "classes.txt", "--ouput", "diagram.HTM"]
    )
    diagram_namespace_none = parser.parse_args(
        ["diagram", "classes.txt", "--namespace", "None"]
    )
    diagram_recursive_attributes = parser.parse_args(
        ["diagram", "classes.txt", "--recursive-attributes"]
    )
    diagram_skip_enums = parser.parse_args(["diagram", "classes.txt", "--skip-enums"])
    diagram_isolate_default = parser.parse_args(["diagram", "classes.txt"])
    diagram_isolate_args = parser.parse_args(
        [
            "diagram",
            "classes.txt",
            "--isolate-class",
            "pkg.chain.B",
            "--isolate-distance",
            "2",
        ]
    )
    diagram_filters_empty = parser.parse_args(["diagram", "classes.txt", "--filters"])
    diagram_filters_values = parser.parse_args(
        ["diagram", "classes.txt", "--filters", "A$", r"pkg\.mod"]
    )
    generate_args = parser.parse_args(["generate", "diagram.md"])
    generate_pydantic = parser.parse_args(["generate", "diagram.md", "--pydantic"])
    generate_custom_output = parser.parse_args(
        ["generate", "diagram.html", "--output", "generated_pkg"]
    )

    assert args.command == "discover"
    assert args.style in {"flat", "escaped"}
    assert args.follow in {"path", "init.py"}
    assert args.namespace_from_root is False
    assert args_follow_init.follow == "init.py"
    assert args_from_root.namespace_from_root is True
    assert diagram_aliases_default.aliases is False
    assert diagram_aliases_on.aliases is True
    assert diagram_aliases_default.title == "UML Class Diagram"
    assert diagram_title.title == "My UML"
    assert diagram_output_alias.output == "diagram.HTM"
    assert diagram_namespace_none.namespace == "none"
    assert diagram_aliases_default.recursive_attributes is False
    assert diagram_recursive_attributes.recursive_attributes is True
    assert diagram_aliases_default.skip_enums is False
    assert diagram_skip_enums.skip_enums is True
    assert diagram_isolate_default.isolate_class is None
    assert diagram_isolate_default.isolate_distance == 1
    assert diagram_isolate_args.isolate_class == "pkg.chain.B"
    assert diagram_isolate_args.isolate_distance == 2
    assert diagram_aliases_default.filters is None
    assert diagram_filters_empty.filters == []
    assert diagram_filters_values.filters == ["A$", r"pkg\.mod"]
    assert generate_args.command == "generate"
    assert generate_args.diagram == "diagram.md"
    assert generate_args.output == "generated_src"
    assert generate_args.pydantic is False
    assert generate_pydantic.pydantic is True
    assert generate_custom_output.output == "generated_pkg"


def test_cmd_discover_and_cmd_diagram_work_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x.py").write_text("class A:\n    pass\n", encoding="utf-8")

    inv = tmp_path / "classes.txt"
    out = tmp_path / "diagram.HTM"

    discover_args = argparse.Namespace(
        root=str(root),
        output=str(inv),
        style="flat",
        follow="path",
        namespace_from_root=False,
    )
    diagram_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out),
        namespace="legacy",
        style="flat",
        aliases=True,
        recursive_attributes=False,
        skip_enums=False,
        title="Project UML",
    )

    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    assert cmd_diagram(diagram_args) == 0
    assert out.exists()


def test_cmd_diagram_filters_classname_and_module(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("class Keep:\n    pass\n", encoding="utf-8")
    (pkg / "b.py").write_text("class Drop:\n    pass\n", encoding="utf-8")

    inv = tmp_path / "classes.txt"
    out_by_name = tmp_path / "diagram_by_name.md"
    out_by_module = tmp_path / "diagram_by_module.md"

    discover_args = argparse.Namespace(
        root=str(root),
        output=str(inv),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    diagram_by_name_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out_by_name),
        namespace="nested",
        style="escaped",
        aliases=False,
        filters=[r"Keep$"],
        recursive_attributes=False,
        skip_enums=False,
        title="Project UML",
    )
    assert cmd_diagram(diagram_by_name_args) == 0
    text_by_name = out_by_name.read_text(encoding="utf-8")
    assert "class `pkg.a.Keep`" in text_by_name
    assert "class `pkg.b.Drop`" not in text_by_name

    diagram_by_module_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out_by_module),
        namespace="nested",
        style="escaped",
        aliases=False,
        filters=[r"pkg\.b"],
        recursive_attributes=False,
        skip_enums=False,
        title="Project UML",
    )
    assert cmd_diagram(diagram_by_module_args) == 0
    text_by_module = out_by_module.read_text(encoding="utf-8")
    assert "class `pkg.b.Drop`" in text_by_module
    assert "class `pkg.a.Keep`" not in text_by_module


def test_cmd_diagram_namespace_none_omits_namespaces_and_module_prefix(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "a.py").write_text("class Keep:\n    pass\n", encoding="utf-8")
    (pkg / "b.py").write_text("class Drop:\n    pass\n", encoding="utf-8")

    inv = tmp_path / "classes.txt"
    out = tmp_path / "diagram_none.md"

    discover_args = argparse.Namespace(
        root=str(root),
        output=str(inv),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    diagram_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out),
        namespace="none",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=False,
        title="Project UML",
    )
    assert cmd_diagram(diagram_args) == 0
    text = out.read_text(encoding="utf-8")
    assert "namespace " not in text
    assert "class `Keep` {" in text
    assert "class `Drop` {" in text
    assert "class `pkg.a.Keep` {" not in text
    assert "class `pkg.b.Drop` {" not in text


def test_cmd_diagram_recursive_attributes_child_overrides_parent(
    tmp_path: Path,
) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "base.py").write_text(
        "class Base:\n"
        "    item: int = 0\n"
        "    def run(self) -> int:\n"
        "        return 1\n"
        "    def keep(self) -> bool:\n"
        "        return True\n",
        encoding="utf-8",
    )
    (pkg / "child.py").write_text(
        "from pkg.base import Base\n"
        "class Child(Base):\n"
        '    item: str = "x"\n'
        "    def run(self) -> str:\n"
        '        return "ok"\n',
        encoding="utf-8",
    )

    inv = tmp_path / "classes.txt"
    out = tmp_path / "diagram_recursive.md"

    discover_args = argparse.Namespace(
        root=str(root),
        output=str(inv),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    diagram_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out),
        namespace="none",
        style="escaped",
        aliases=False,
        recursive_attributes=True,
        skip_enums=False,
        title="Project UML",
    )
    assert cmd_diagram(diagram_args) == 0

    text = out.read_text(encoding="utf-8")
    child_block = text.split("class `Child` {", 1)[1].split("}", 1)[0]
    assert "+item: str" in child_block
    assert "+item: int" not in child_block
    assert "+run() str" in child_block
    assert "+run() int" not in child_block
    assert "+keep() bool" in child_block


def test_cmd_diagram_isolate_class_uses_graph_distance(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "chain.py").write_text(
        "class A:\n"
        "    pass\n"
        "class B(A):\n"
        "    pass\n"
        "class C(B):\n"
        "    pass\n"
        "class D(C):\n"
        "    pass\n",
        encoding="utf-8",
    )

    inv = tmp_path / "classes.txt"
    out_distance_1 = tmp_path / "diagram_isolate_d1.md"
    out_distance_2 = tmp_path / "diagram_isolate_d2.md"

    discover_args = argparse.Namespace(
        root=str(root),
        output=str(inv),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    isolate_d1_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out_distance_1),
        namespace="nested",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=False,
        isolate_class="pkg.chain.B",
        isolate_distance=1,
        title="Project UML",
    )
    assert cmd_diagram(isolate_d1_args) == 0
    text_d1 = out_distance_1.read_text(encoding="utf-8")
    assert "class `pkg.chain.A` {" in text_d1
    assert "class `pkg.chain.B` {" in text_d1
    assert "class `pkg.chain.C` {" in text_d1
    assert "class `pkg.chain.D` {" not in text_d1

    isolate_d2_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out_distance_2),
        namespace="nested",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=False,
        isolate_class="pkg.chain.B",
        isolate_distance=2,
        title="Project UML",
    )
    assert cmd_diagram(isolate_d2_args) == 0
    text_d2 = out_distance_2.read_text(encoding="utf-8")
    assert "class `pkg.chain.D` {" in text_d2


def test_cmd_diagram_skip_enums_hides_enum_members(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "types.py").write_text(
        "from enum import Enum\n"
        "class OrderedEnum(Enum):\n"
        "    A = 1\n"
        "class Kind(OrderedEnum):\n"
        "    Foo = 1\n"
        "    Bar = 2\n"
        "class DescriptiveEnum:\n"
        "    Basic = 'basic'\n"
        "    Advanced = 'advanced'\n"
        "class DerivedDescriptiveEnum(DescriptiveEnum):\n"
        "    Pro = 'pro'\n"
        "    Enterprise = 'enterprise'\n"
        "class Holder:\n"
        "    kind: Kind = Kind.Foo\n",
        encoding="utf-8",
    )

    inv = tmp_path / "classes.txt"
    out_default = tmp_path / "diagram_default.md"
    out_skip = tmp_path / "diagram_skip.md"

    discover_args = argparse.Namespace(
        root=str(root),
        output=str(inv),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    diagram_default_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out_default),
        namespace="nested",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=False,
        title="Project UML",
    )
    assert cmd_diagram(diagram_default_args) == 0
    default_text = out_default.read_text(encoding="utf-8")
    assert "+Foo: int" in default_text
    assert "+Bar: int" in default_text
    assert "+Basic: str" in default_text
    assert "+Advanced: str" in default_text
    assert "+Pro: str" in default_text
    assert "+Enterprise: str" in default_text
    assert "+kind: Kind" in default_text

    diagram_skip_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out_skip),
        namespace="nested",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=True,
        title="Project UML",
    )
    assert cmd_diagram(diagram_skip_args) == 0
    skip_text = out_skip.read_text(encoding="utf-8")
    assert "class `pkg.types.Kind` {" in skip_text
    assert "+Foo: int" not in skip_text
    assert "+Bar: int" not in skip_text
    assert "+A: int" not in skip_text
    assert "+Basic: str" not in skip_text
    assert "+Advanced: str" not in skip_text
    assert "+Pro: str" not in skip_text
    assert "+Enterprise: str" not in skip_text
    assert "+kind: Kind" in skip_text


def test_cmd_generate_from_markdown_and_html(tmp_path: Path) -> None:
    mermaid_source = (
        "classDiagram\n"
        "class `pkg.base.Base` {\n"
        "  +identifier: int\n"
        "}\n"
        "class `pkg.app.Service` {\n"
        "  +dependency: Base\n"
        "  +run() None\n"
        "}\n"
        "`pkg.base.Base` <|-- `pkg.app.Service`\n"
    )

    md_diagram = tmp_path / "diagram.md"
    md_diagram.write_text(
        "# UML\n\n```mermaid\n" + mermaid_source + "```\n",
        encoding="utf-8",
    )
    md_output = tmp_path / "generated_from_md"
    generate_md_args = argparse.Namespace(
        diagram=str(md_diagram),
        output=str(md_output),
    )
    assert cmd_generate(generate_md_args) == 0

    base_py = md_output / "pkg" / "base.py"
    app_py = md_output / "pkg" / "app.py"
    assert (md_output / "pkg" / "__init__.py").exists()
    assert base_py.exists()
    assert app_py.exists()
    assert "class Base:" in base_py.read_text(encoding="utf-8")
    app_text = app_py.read_text(encoding="utf-8")
    assert "from pkg.base import Base" in app_text
    assert "class Service(Base):" in app_text
    assert "dependency: Base" in app_text
    assert "def run(self) -> None:" in app_text

    html_diagram = tmp_path / "diagram.HTM"
    html_diagram.write_text(
        '<!doctype html><html><body><pre class="mermaid">'
        + "classDiagram\nclass `pkg.alpha.Alpha` {\n}\n"
        + "</pre></body></html>",
        encoding="utf-8",
    )
    html_output = tmp_path / "generated_from_html"
    generate_html_args = argparse.Namespace(
        diagram=str(html_diagram),
        output=str(html_output),
    )
    assert cmd_generate(generate_html_args) == 0
    alpha_py = html_output / "pkg" / "alpha.py"
    assert alpha_py.exists()
    assert "class Alpha:" in alpha_py.read_text(encoding="utf-8")

    pydantic_output = tmp_path / "generated_from_md_pydantic"
    generate_pydantic_args = argparse.Namespace(
        diagram=str(md_diagram),
        output=str(pydantic_output),
        pydantic=True,
    )
    assert cmd_generate(generate_pydantic_args) == 0
    pydantic_base_py = pydantic_output / "pkg" / "base.py"
    pydantic_app_py = pydantic_output / "pkg" / "app.py"
    assert pydantic_base_py.exists()
    assert pydantic_app_py.exists()
    pydantic_base_text = pydantic_base_py.read_text(encoding="utf-8")
    pydantic_app_text = pydantic_app_py.read_text(encoding="utf-8")
    assert "from pydantic import BaseModel, Field" in pydantic_base_text
    assert "class Base(BaseModel):" in pydantic_base_text
    assert "identifier: int = Field(...)" in pydantic_base_text
    assert "class Service(Base):" in pydantic_app_text
    assert "dependency: Base = Field(...)" in pydantic_app_text


def test_resolve_isolate_target_covers_ranking_and_errors() -> None:
    nested = ClassInfo(
        class_id="pkg_mod_Outer_Inner",
        fqcn="pkg.mod.Outer.Inner",
        module="pkg.mod",
        qualname="Outer.Inner",
        name="Inner",
        filepath="a.py",
        lineno=1,
    )
    other = ClassInfo(
        class_id="pkg_other_Thing",
        fqcn="pkg.other.Thing",
        module="pkg.other",
        qualname="Thing",
        name="Thing",
        filepath="b.py",
        lineno=1,
    )
    classes = {nested.fqcn: nested, other.fqcn: other}

    target, err = mermaiden_module._resolve_isolate_target(classes, "")
    assert target is None
    assert "Empty --isolate-class value" in (err or "")

    target, err = mermaiden_module._resolve_isolate_target(
        classes, "pkg.mod.Outer.Inner"
    )
    assert target == "pkg.mod.Outer.Inner"
    assert err is None

    target, err = mermaiden_module._resolve_isolate_target(classes, "Outer.Inner")
    assert target == "pkg.mod.Outer.Inner"
    assert err is None

    target, err = mermaiden_module._resolve_isolate_target(classes, "Inner")
    assert target == "pkg.mod.Outer.Inner"
    assert err is None

    target, err = mermaiden_module._resolve_isolate_target(classes, "mod.Outer.Inner")
    assert target == "pkg.mod.Outer.Inner"
    assert err is None

    target, err = mermaiden_module._resolve_isolate_target(
        classes, "pkg_mod_Outer_Inner"
    )
    assert target == "pkg.mod.Outer.Inner"
    assert err is None

    a = ClassInfo("id1", "pkg.a.Same", "pkg.a", "Same", "Same", "a.py", 1)
    b = ClassInfo("id2", "pkg.b.Same", "pkg.b", "Same", "Same", "b.py", 1)
    ambiguous_target, ambiguous_err = mermaiden_module._resolve_isolate_target(
        {a.fqcn: a, b.fqcn: b}, "Same"
    )
    assert ambiguous_target is None
    assert "ambiguous" in (ambiguous_err or "")

    missing_target, missing_err = mermaiden_module._resolve_isolate_target(
        classes, "DoesNotExist"
    )
    assert missing_target is None
    assert "did not match any class" in (missing_err or "")


def test_build_relation_graph_skips_unknown_relations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a = ClassInfo("a", "pkg.A", "pkg", "A", "A", "a.py", 1)
    b = ClassInfo("b", "pkg.B", "pkg", "B", "B", "b.py", 1)
    classes = {a.fqcn: a, b.fqcn: b}

    monkeypatch.setattr(
        mermaiden_module,
        "collect_all_relations",
        lambda _: [
            ("pkg.A", RelationType.ASSOCIATION, "pkg.B"),
            ("pkg.A", RelationType.ASSOCIATION, "pkg.Missing"),
        ],
    )

    graph = mermaiden_module._build_relation_graph(classes)
    assert graph["pkg.A"] == {"pkg.B": 1}
    assert graph["pkg.B"] == {"pkg.A": 1}


def test_dijkstra_shortest_paths_handles_stale_queue_entries() -> None:
    graph = {
        "A": {"B": 10, "C": 1},
        "B": {},
        "C": {"B": 1},
    }
    distances = mermaiden_module._dijkstra_shortest_paths(graph, "A")
    assert distances["A"] == 0
    assert distances["C"] == 1
    assert distances["B"] == 2


def test_cmd_discover_invalid_directory_returns_error(tmp_path: Path) -> None:
    args = argparse.Namespace(
        root=str(tmp_path / "missing"),
        output=str(tmp_path / "classes.txt"),
        style="flat",
        follow="path",
        namespace_from_root=False,
    )
    assert cmd_discover(args) == 1


def test_cmd_diagram_error_paths_and_filter_warning(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_args = argparse.Namespace(
        inventory=str(tmp_path / "missing.txt"),
        output=str(tmp_path / "out.md"),
        namespace="nested",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=False,
        isolate_class=None,
        isolate_distance=1,
        filters=None,
        title="UML",
    )
    assert cmd_diagram(missing_args) == 1

    inventory = tmp_path / "classes.txt"
    inventory.write_text("# ROOT\t/tmp\n", encoding="utf-8")

    base_args = argparse.Namespace(
        inventory=str(inventory),
        output=str(tmp_path / "out.md"),
        namespace="nested",
        style="escaped",
        aliases=False,
        recursive_attributes=False,
        skip_enums=False,
        isolate_class=None,
        isolate_distance=1,
        filters=None,
        title="UML",
    )

    monkeypatch.setattr(
        mermaiden_module, "rebuild_class_map_from_inventory", lambda *_, **__: {}
    )
    assert cmd_diagram(base_args) == 1

    classes = {
        "pkg.A": ClassInfo("a", "pkg.A", "pkg", "A", "A", "a.py", 1),
    }
    monkeypatch.setattr(
        mermaiden_module,
        "rebuild_class_map_from_inventory",
        lambda *_, **__: classes,
    )
    monkeypatch.setattr(mermaiden_module, "write_mermaid_output", lambda *_, **__: None)

    args_distance_without_isolate = argparse.Namespace(**vars(base_args))
    args_distance_without_isolate.isolate_distance = 2
    assert cmd_diagram(args_distance_without_isolate) == 1

    args_negative_distance = argparse.Namespace(**vars(base_args))
    args_negative_distance.isolate_class = "pkg.A"
    args_negative_distance.isolate_distance = -1
    assert cmd_diagram(args_negative_distance) == 1

    args_bad_isolate = argparse.Namespace(**vars(base_args))
    args_bad_isolate.isolate_class = "Missing"
    args_bad_isolate.isolate_distance = 1
    assert cmd_diagram(args_bad_isolate) == 1

    args_bad_regex = argparse.Namespace(**vars(base_args))
    args_bad_regex.filters = ["["]
    assert cmd_diagram(args_bad_regex) == 1

    args_no_match_filters = argparse.Namespace(**vars(base_args))
    args_no_match_filters.filters = [r"^DoesNotMatch$"]
    assert cmd_diagram(args_no_match_filters) == 0


def test_cmd_generate_error_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing_args = argparse.Namespace(
        diagram=str(tmp_path / "missing.md"),
        output=str(tmp_path / "generated"),
        pydantic=False,
    )
    assert cmd_generate(missing_args) == 1

    diagram_file = tmp_path / "diagram.md"
    diagram_file.write_text("# empty", encoding="utf-8")

    monkeypatch.setattr(
        mermaiden_module,
        "generate_codebase_from_diagram",
        lambda **_: (_ for _ in ()).throw(ValueError("boom")),
    )
    failing_args = argparse.Namespace(
        diagram=str(diagram_file),
        output=str(tmp_path / "generated"),
        pydantic=False,
    )
    assert cmd_generate(failing_args) == 1


def test_main_uses_parser_func(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeParser:
        def parse_args(self) -> argparse.Namespace:
            return argparse.Namespace(func=lambda _: 7)

    monkeypatch.setattr(mermaiden_module, "build_parser", lambda: _FakeParser())
    assert mermaiden_module.main() == 7


def test_cmd_generate_pydantic_uses_field_for_relation_inferred_attributes(
    tmp_path: Path,
) -> None:
    mermaid_source = (
        "classDiagram\n"
        "class `pkg.src.Source` {\n"
        "}\n"
        "class `pkg.dst.Target` {\n"
        "}\n"
        "`pkg.src.Source` --> `pkg.dst.Target`\n"
    )
    md_diagram = tmp_path / "diagram_rel.md"
    md_diagram.write_text(
        "# UML\n\n```mermaid\n" + mermaid_source + "```\n",
        encoding="utf-8",
    )

    pydantic_output = tmp_path / "generated_from_rel_pydantic"
    generate_args = argparse.Namespace(
        diagram=str(md_diagram),
        output=str(pydantic_output),
        pydantic=True,
    )
    assert cmd_generate(generate_args) == 0

    target_py = pydantic_output / "pkg" / "dst.py"
    assert target_py.exists()
    target_text = target_py.read_text(encoding="utf-8")
    assert "from pydantic import BaseModel, Field" in target_text
    assert "class Target(BaseModel):" in target_text
    assert "Source: Source = Field(...)" in target_text
