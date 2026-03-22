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

    assert args.command == "discover"
    assert args.style in {"flat", "escaped"}


def test_cmd_discover_and_cmd_diagram_work_end_to_end(tmp_path: Path) -> None:
    root = tmp_path / "src"
    pkg = root / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "x.py").write_text("class A:\n    pass\n", encoding="utf-8")

    inv = tmp_path / "classes.txt"
    out = tmp_path / "diagram.md"

    discover_args = argparse.Namespace(root=str(root), output=str(inv), style="flat")
    diagram_args = argparse.Namespace(
        inventory=str(inv),
        output=str(out),
        namespace="legacy",
        style="flat",
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
    )

    assert cmd_discover(discover_args) == 0
    assert inv.exists()

    assert cmd_diagram(diagram_args) == 0
    assert out.exists()
