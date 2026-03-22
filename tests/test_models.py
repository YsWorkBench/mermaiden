from __future__ import annotations

from pathlib import Path

from models import (
    AttributeInfo,
    ClassInfo,
    MermaidIdStyle,
    MethodInfo,
    build_namespace_tree,
    mermaid_id,
    safe_mermaid_id,
    should_skip_path,
)


def test_attribute_and_method_render_visibility() -> None:
    public_attr = AttributeInfo("name", "str")
    private_attr = AttributeInfo("_token")
    method = MethodInfo("do_work", [("x", "int"), ("y", "")], "bool")
    private_method = MethodInfo("_helper", [], "")

    assert public_attr.render() == "+name: str"
    assert private_attr.render() == "-_token"
    assert method.render() == "+do_work(x: int, y) bool"
    assert private_method.render() == "-_helper()"


def test_safe_mermaid_id_flat_and_escaped() -> None:
    assert safe_mermaid_id("a.b-c") == "a_b_c"
    assert safe_mermaid_id("1Class") == "_1Class"
    assert safe_mermaid_id("a`b", MermaidIdStyle.ESCAPED) == "`a\\`b`"


def test_mermaid_id_invalid_style_raises() -> None:
    try:
        mermaid_id("x", style="bad")
    except ValueError:
        pass
    else:
        raise AssertionError("Expected ValueError for invalid style")


def test_build_namespace_tree_places_classes_in_nodes() -> None:
    classes = {
        "pkg.mod.A": ClassInfo("pkg_mod_A", "pkg.mod.A", "pkg.mod", "A", "A", "/tmp/a.py", 1),
        "Top": ClassInfo("Top", "Top", "", "Top", "Top", "/tmp/t.py", 1),
    }

    tree = build_namespace_tree(classes)

    assert [c.fqcn for c in tree.classes] == ["Top"]
    assert "pkg" in tree.children
    assert "mod" in tree.children["pkg"].children
    mod_node = tree.children["pkg"].children["mod"]
    assert [c.fqcn for c in mod_node.classes] == ["pkg.mod.A"]


def test_should_skip_path_detects_excluded_parts() -> None:
    assert should_skip_path(Path("project/.git/config"))
    assert should_skip_path(Path("project/__pycache__/a.pyc"))
    assert not should_skip_path(Path("project/src/main.py"))
