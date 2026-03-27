from __future__ import annotations

import argparse
import ast
from pathlib import Path

from mermaiden import build_parser, cmd_diagram, cmd_discover, cmd_generate


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
