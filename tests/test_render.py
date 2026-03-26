from __future__ import annotations

from pathlib import Path

import pytest

from models import AttributeInfo, ClassInfo, MethodInfo, Relation, RelationType
from render import (
    generate_mermaid_source,
    render_html_document,
    render_markdown_document,
    write_diagram_output,
)


def _sample_classes() -> dict[str, ClassInfo]:
    base = ClassInfo(
        class_id="pkg_Base",
        fqcn="pkg.Base",
        module="pkg",
        qualname="Base",
        name="Base",
        filepath="a.py",
        lineno=1,
        attributes=[AttributeInfo("x", "int")],
        methods=[MethodInfo("run", [("v", "str")], "None")],
    )
    child = ClassInfo(
        class_id="pkg_Child",
        fqcn="pkg.Child",
        module="pkg",
        qualname="Child",
        name="Child",
        filepath="a.py",
        lineno=2,
        bases=["Base"],
        relations=[Relation("pkg.Child", "Base", RelationType.ASSOCIATION)],
    )
    return {"pkg.Base": base, "pkg.Child": child}


def test_generate_mermaid_source_nested_and_legacy() -> None:
    classes = _sample_classes()

    nested = generate_mermaid_source(classes, namespace="nested")
    legacy = generate_mermaid_source(classes, namespace="legacy")

    assert nested.startswith("classDiagram")
    assert 'namespace pkg["pkg"]{' in nested
    assert 'class pkg_Base["Base"] {' in nested
    assert "pkg_Base <|-- pkg_Child" in nested
    assert legacy.startswith("classDiagram")


def test_generate_mermaid_source_namespace_none_uses_module_free_identifiers() -> None:
    classes = _sample_classes()
    none_mode = generate_mermaid_source(classes, namespace="none", aliases=False)

    assert none_mode.startswith("classDiagram")
    assert "namespace " not in none_mode
    assert "class Base {" in none_mode
    assert "class Child {" in none_mode
    assert "class pkg_Base {" not in none_mode
    assert "class pkg_Child {" not in none_mode
    assert "Base <|-- Child" in none_mode


def test_generate_mermaid_source_recursive_attributes_postfix_override() -> None:
    base = ClassInfo(
        class_id="pkg_Base",
        fqcn="pkg.Base",
        module="pkg",
        qualname="Base",
        name="Base",
        filepath="a.py",
        lineno=1,
        attributes=[AttributeInfo("value", "int")],
        methods=[MethodInfo("run", [], "int"), MethodInfo("keep", [], "None")],
    )
    child = ClassInfo(
        class_id="pkg_Child",
        fqcn="pkg.Child",
        module="pkg",
        qualname="Child",
        name="Child",
        filepath="a.py",
        lineno=2,
        bases=["Base"],
        attributes=[AttributeInfo("value", "str")],
        methods=[MethodInfo("run", [], "str")],
    )
    classes = {"pkg.Base": base, "pkg.Child": child}

    recursive_text = generate_mermaid_source(
        classes,
        namespace="none",
        aliases=False,
        recursive_attributes=True,
    )
    child_block = recursive_text.split("class Child {", 1)[1].split("}", 1)[0]

    assert "+value: str" in child_block
    assert "+value: int" not in child_block
    assert "+run() str" in child_block
    assert "+run() int" not in child_block
    assert "+keep() None" in child_block


def test_generate_mermaid_source_without_aliases() -> None:
    classes = _sample_classes()
    nested = generate_mermaid_source(classes, namespace="nested", aliases=False)

    assert "namespace pkg{" in nested
    assert 'namespace pkg["pkg"]{' not in nested
    assert "class pkg_Base {" in nested
    assert 'class pkg_Base["Base"] {' not in nested


def test_generate_mermaid_source_bad_namespace_raises() -> None:
    with pytest.raises(ValueError):
        generate_mermaid_source(_sample_classes(), namespace="bad")


def test_render_markdown_and_html_document() -> None:
    md = render_markdown_document("classDiagram\n", title="My Diagram")
    assert md.startswith("# My Diagram")
    assert "```mermaid" in md

    html = render_html_document("classDiagram\nA --> B\n", title="<Title>")
    assert "<!DOCTYPE html>" in html
    assert "&lt;Title&gt;" in html


def test_write_diagram_output_md_and_html(tmp_path: Path) -> None:
    classes = _sample_classes()

    md_out = tmp_path / "diagram.md"
    html_out = tmp_path / "diagram.HTM"

    write_diagram_output(classes, md_out)
    write_diagram_output(classes, html_out)

    assert md_out.read_text(encoding="utf-8").startswith("# UML Class Diagram")
    assert "<html" in html_out.read_text(encoding="utf-8")


def test_write_diagram_output_unsupported_extension(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        write_diagram_output(_sample_classes(), tmp_path / "diagram.txt")
