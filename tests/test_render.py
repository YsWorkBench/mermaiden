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


def test_generate_mermaid_source_skip_enums_hides_enum_values() -> None:
    ordered_enum = ClassInfo(
        class_id="pkg_OrderedEnum",
        fqcn="pkg.OrderedEnum",
        module="pkg",
        qualname="OrderedEnum",
        name="OrderedEnum",
        filepath="a.py",
        lineno=1,
        bases=["Enum"],
        attributes=[AttributeInfo("A", "int")],
    )
    dummy_type_enum = ClassInfo(
        class_id="pkg_DummyTypeEnum",
        fqcn="pkg.DummyTypeEnum",
        module="pkg",
        qualname="DummyTypeEnum",
        name="DummyTypeEnum",
        filepath="a.py",
        lineno=2,
        bases=["OrderedEnum"],
        attributes=[AttributeInfo("DummyPckg", "int"), AttributeInfo("Other", "int")],
    )
    regular = ClassInfo(
        class_id="pkg_Regular",
        fqcn="pkg.Regular",
        module="pkg",
        qualname="Regular",
        name="Regular",
        filepath="a.py",
        lineno=3,
        attributes=[AttributeInfo("value", "int")],
    )
    classes = {
        "pkg.OrderedEnum": ordered_enum,
        "pkg.DummyTypeEnum": dummy_type_enum,
        "pkg.Regular": regular,
    }

    without_skip = generate_mermaid_source(classes, namespace="none", aliases=False)
    with_skip = generate_mermaid_source(
        classes,
        namespace="none",
        aliases=False,
        skip_enums=True,
    )

    assert "+A: int" in without_skip
    assert "+DummyPckg: int" in without_skip
    assert "+value: int" in without_skip

    assert "+A: int" not in with_skip
    assert "+DummyPckg: int" not in with_skip
    assert "+Other: int" not in with_skip
    assert "class OrderedEnum {" in with_skip
    assert "class DummyTypeEnum {" in with_skip
    assert "+value: int" in with_skip


def test_generate_mermaid_source_skip_enums_detects_structural_enum_and_derivatives() -> (
    None
):
    descriptive_enum = ClassInfo(
        class_id="pkg_DescriptiveEnum",
        fqcn="pkg.DescriptiveEnum",
        module="pkg",
        qualname="DescriptiveEnum",
        name="DescriptiveEnum",
        filepath="a.py",
        lineno=1,
        attributes=[AttributeInfo("Foo", "str"), AttributeInfo("Bar", "str")],
    )
    derived_descriptive_enum = ClassInfo(
        class_id="pkg_DerivedDescriptiveEnum",
        fqcn="pkg.DerivedDescriptiveEnum",
        module="pkg",
        qualname="DerivedDescriptiveEnum",
        name="DerivedDescriptiveEnum",
        filepath="a.py",
        lineno=2,
        bases=["DescriptiveEnum"],
        attributes=[AttributeInfo("Baz", "str"), AttributeInfo("Qux", "str")],
    )
    descriptive_ordered_enum = ClassInfo(
        class_id="pkg_DescriptiveOrderedEnum",
        fqcn="pkg.DescriptiveOrderedEnum",
        module="pkg",
        qualname="DescriptiveOrderedEnum",
        name="DescriptiveOrderedEnum",
        filepath="a.py",
        lineno=3,
        attributes=[
            AttributeInfo("Alpha", "tuple"),
            AttributeInfo("Beta", "tuple"),
        ],
    )
    regular = ClassInfo(
        class_id="pkg_Regular",
        fqcn="pkg.Regular",
        module="pkg",
        qualname="Regular",
        name="Regular",
        filepath="a.py",
        lineno=4,
        attributes=[AttributeInfo("value", "str")],
    )
    classes = {
        "pkg.DescriptiveEnum": descriptive_enum,
        "pkg.DerivedDescriptiveEnum": derived_descriptive_enum,
        "pkg.DescriptiveOrderedEnum": descriptive_ordered_enum,
        "pkg.Regular": regular,
    }

    without_skip = generate_mermaid_source(classes, namespace="none", aliases=False)
    with_skip = generate_mermaid_source(
        classes,
        namespace="none",
        aliases=False,
        skip_enums=True,
    )

    assert "+Foo: str" in without_skip
    assert "+Baz: str" in without_skip
    assert "+Alpha: tuple" in without_skip

    assert "+Foo: str" not in with_skip
    assert "+Bar: str" not in with_skip
    assert "+Baz: str" not in with_skip
    assert "+Qux: str" not in with_skip
    assert "+Alpha: tuple" not in with_skip
    assert "+Beta: tuple" not in with_skip
    assert "class DescriptiveEnum {" in with_skip
    assert "class DerivedDescriptiveEnum {" in with_skip
    assert "class DescriptiveOrderedEnum {" in with_skip
    assert "+value: str" in with_skip


def test_generate_mermaid_source_strips_quotes_for_related_forward_refs_only() -> None:
    owner = ClassInfo(
        class_id="pkg_Owner",
        fqcn="pkg.Owner",
        module="pkg",
        qualname="Owner",
        name="Owner",
        filepath="a.py",
        lineno=1,
        attributes=[
            AttributeInfo("items", "list['Item']"),
            AttributeInfo("tag", "Literal['internal']"),
        ],
        relations=[Relation("pkg.Owner", "Item", RelationType.AGGREGATION)],
    )
    item = ClassInfo(
        class_id="pkg_Item",
        fqcn="pkg.Item",
        module="pkg",
        qualname="Item",
        name="Item",
        filepath="a.py",
        lineno=2,
    )
    classes = {"pkg.Owner": owner, "pkg.Item": item}

    diagram = generate_mermaid_source(classes, namespace="none", aliases=False)

    assert "+items: list[Item]" in diagram
    assert "+items: list['Item']" not in diagram
    assert "+tag: Literal['internal']" in diagram


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
