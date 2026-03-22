from __future__ import annotations

import ast

from ast_logic import (
    annotation_to_str,
    expr_to_name,
    extract_class_level_attributes,
    extract_attributes_from_ctor,
    extract_method_info,
    infer_type_from_value,
    looks_like_interface,
    should_include_method,
    split_type_names,
)


def _parse_expr(source: str) -> ast.AST:
    return ast.parse(source, mode="eval").body


def _parse_class(source: str) -> ast.ClassDef:
    mod = ast.parse(source)
    for node in mod.body:
        if isinstance(node, ast.ClassDef):
            return node
    raise AssertionError("ClassDef not found")


def _parse_function(source: str) -> ast.FunctionDef:
    mod = ast.parse(source)
    for node in mod.body:
        if isinstance(node, ast.FunctionDef):
            return node
    raise AssertionError("FunctionDef not found")


def test_expr_and_annotation_stringification() -> None:
    assert expr_to_name(_parse_expr("pkg.Type")) == "pkg.Type"
    assert expr_to_name(_parse_expr("list[str]")) == "list[str]"
    assert expr_to_name(_parse_expr("A | B")) == "A | B"
    assert annotation_to_str(_parse_expr("dict[str, int]")) == "dict[str, int]"
    assert annotation_to_str(_parse_expr("tuple(None, Service)")) == "tuple[None, Service]"


def test_infer_type_from_value() -> None:
    assert infer_type_from_value(_parse_expr("1")) == "int"
    assert infer_type_from_value(_parse_expr("None")) == "None"
    assert infer_type_from_value(_parse_expr("[]")) == "list"
    assert infer_type_from_value(_parse_expr("MyType()")) == "MyType"
    assert (
        infer_type_from_value(_parse_expr("[Service() for _ in range(3)]"))
        == "list[Service]"
    )


def test_method_filters_and_type_split() -> None:
    assert not should_include_method("__init__")
    assert not should_include_method("__repr__")
    assert not should_include_method("__len__")
    assert should_include_method("run")

    deps = split_type_names("list[foo.Bar] | Optional[Baz]")
    assert deps == {"Bar", "Baz"}
    assert looks_like_interface("abc.ABC")
    assert looks_like_interface("UserProtocol")
    assert not looks_like_interface("BaseClass")


def test_extract_method_info() -> None:
    fn = _parse_function(
        "def f(self, x: int, *args: str, y: bool, **kwargs: float) -> Result: pass"
    )
    info = extract_method_info(fn)

    assert info.name == "f"
    assert info.params == [
        ("x", "int"),
        ("*args", "str"),
        ("y", "bool"),
        ("**kwargs", "float"),
    ]
    assert info.return_type == "Result"


def test_extract_class_attributes_and_init_instance_attributes() -> None:
    cls = _parse_class(
        "class A:\n"
        "    x = 1\n"
        "    y: str = 'a'\n"
        "    def __init__(self, dep: Service, n: int):\n"
        "        self.dep = dep\n"
        "        self.count = n\n"
        "        self.inline: Repo = Repo()\n"
    )

    class_attrs = extract_class_level_attributes(cls)
    assert [(a.name, a.type_name) for a in class_attrs] == [("x", "int"), ("y", "str")]

    init_attrs = extract_attributes_from_ctor(cls)
    pairs = [(a.name, a.type_name) for a in init_attrs]
    assert ("count", "int") in pairs
    assert ("dep", "Service") in pairs
    assert ("inline", "Repo") in pairs
