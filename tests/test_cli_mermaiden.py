from __future__ import annotations

import argparse
import ast
from pathlib import Path

from mermaiden import build_parser, cmd_diagram, cmd_discover


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
    diagram_filters_empty = parser.parse_args(["diagram", "classes.txt", "--filters"])
    diagram_filters_values = parser.parse_args(
        ["diagram", "classes.txt", "--filters", "A$", r"pkg\.mod"]
    )

    assert args.command == "discover"
    assert args.style in {"flat", "escaped"}
    assert args.follow in {"path", "init.py"}
    assert args.namespace_from_root is False
    assert args_follow_init.follow == "init.py"
    assert args_from_root.namespace_from_root is True
    assert diagram_aliases_default.aliases is False
    assert diagram_aliases_on.aliases is True
    assert diagram_aliases_default.filters is None
    assert diagram_filters_empty.filters == []
    assert diagram_filters_values.filters == ["A$", r"pkg\.mod"]


def test_cmd_discover_and_cmd_diagram_work_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x.py").write_text("class A:\n    pass\n", encoding="utf-8")

    inv = tmp_path / "classes.txt"
    out = tmp_path / "diagram.md"

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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
    )
    assert cmd_diagram(diagram_by_module_args) == 0
    text_by_module = out_by_module.read_text(encoding="utf-8")
    assert "class `pkg.b.Drop`" in text_by_module
    assert "class `pkg.a.Keep`" not in text_by_module
