"""AST helpers for extracting class, method, and type metadata."""

from __future__ import annotations

import ast
import re

from models import AttributeInfo, IGNORED_SPECIAL_METHODS, MethodInfo


def _is_annotated_expression(node: ast.AST | None) -> bool:
    """Return True when the node is ``typing.Annotated[...]``."""
    if not isinstance(node, ast.Subscript):
        return False
    base = expr_to_name(node.value)
    return base == "Annotated" or base.endswith(".Annotated")


def _iter_subscript_args(node: ast.Subscript) -> list[ast.AST]:
    """Return subscript arguments as a normalized list."""
    if isinstance(node.slice, ast.Tuple):
        return list(node.slice.elts)
    return [node.slice]


def _type_name_tokens(type_name: str) -> set[str]:
    """Split a type expression into normalized short-name tokens."""
    raw = (
        type_name.replace("[", " ")
        .replace("]", " ")
        .replace(",", " ")
        .replace("|", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    return {part.split(".")[-1] for part in raw.split() if part}


def should_skip_pydantic_internal_attribute(name: str, type_name: str) -> bool:
    """Return True for known pydantic internal class attributes."""
    if name != "model_config":
        return False
    return "ConfigDict" in _type_name_tokens(type_name)


def expr_to_name(node: ast.AST | None) -> str:
    """Convert an AST expression node to a readable type/name string."""
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = expr_to_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Subscript):
        value = expr_to_name(node.value)
        slc = expr_to_name(node.slice)
        return f"{value}[{slc}]" if slc else value
    if isinstance(node, ast.Tuple):
        return ", ".join(expr_to_name(e) for e in node.elts)
    if isinstance(node, ast.List):
        return ", ".join(expr_to_name(e) for e in node.elts)
    if isinstance(node, ast.Constant):
        return "None" if node.value is None else repr(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return f"{expr_to_name(node.left)} | {expr_to_name(node.right)}"
    if isinstance(node, ast.Call):
        return expr_to_name(node.func)
    return ""


def annotation_to_str(node: ast.AST | None) -> str:
    """Render a type annotation node as text."""
    if _is_annotated_expression(node):
        annotated_node = node
        assert isinstance(annotated_node, ast.Subscript)
        args = _iter_subscript_args(annotated_node)
        if args:
            return annotation_to_str(args[0])
        return ""

    if isinstance(node, ast.Call):
        base = expr_to_name(node.func)
        arg_parts = [annotation_to_str(arg) for arg in node.args]
        kw_parts = []
        for kw in node.keywords:
            value = annotation_to_str(kw.value)
            if not value:
                continue
            if kw.arg is None:
                kw_parts.append(value)
            else:
                kw_parts.append(f"{kw.arg}={value}")

        parts = [part for part in [*arg_parts, *kw_parts] if part]
        if parts and base:
            return f"{base}[{', '.join(parts)}]"
        return base

    return expr_to_name(node)


def infer_type_from_value(node: ast.AST | None) -> str:
    """Best-effort type inference from a literal or call expression."""
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        return "None" if node.value is None else type(node.value).__name__
    if isinstance(node, ast.List):
        return "list"
    if isinstance(node, ast.Tuple):
        return "tuple"
    if isinstance(node, ast.Dict):
        return "dict"
    if isinstance(node, ast.Set):
        return "set"
    if isinstance(node, ast.ListComp):
        elem_type = infer_type_from_value(node.elt)
        return f"list[{elem_type}]" if elem_type else "list"
    if isinstance(node, ast.SetComp):
        elem_type = infer_type_from_value(node.elt)
        return f"set[{elem_type}]" if elem_type else "set"
    if isinstance(node, ast.DictComp):
        key_type = infer_type_from_value(node.key)
        value_type = infer_type_from_value(node.value)
        if key_type and value_type:
            return f"dict[{key_type}, {value_type}]"
        return "dict"
    if isinstance(node, ast.GeneratorExp):
        elem_type = infer_type_from_value(node.elt)
        return f"Iterable[{elem_type}]" if elem_type else "Iterable"
    if isinstance(node, ast.Call):
        return expr_to_name(node.func)
    return ""


def is_special_method(name: str) -> bool:
    """Return True when a method name is a Python dunder method."""
    return name.startswith("__") and name.endswith("__")


def should_include_method(name: str) -> bool:
    """Decide whether a method should be shown in UML output."""
    if name == "__init__":
        return False
    if name in IGNORED_SPECIAL_METHODS:
        return False
    if is_special_method(name):
        return False
    return True


def split_type_names(type_name: str) -> set[str]:
    """Extract potential class names from a composite type string."""
    if not type_name:
        return set()

    raw = (
        type_name.replace("[", " ")
        .replace("]", " ")
        .replace(",", " ")
        .replace("|", " ")
        .replace("(", " ")
        .replace(")", " ")
    )
    parts = {p.strip() for p in raw.split() if p.strip()}

    normalized_parts: set[str] = set()
    for part in parts:
        cleaned = part.strip().strip("'").strip('"')
        if not cleaned or "=" in cleaned:
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_\.]*", cleaned):
            continue
        normalized_parts.add(cleaned)

    noise = {
        "list",
        "List",
        "dict",
        "Dict",
        "set",
        "Set",
        "tuple",
        "Tuple",
        "Optional",
        "Union",
        "Iterable",
        "Sequence",
        "Mapping",
        "MutableMapping",
        "Any",
        "None",
        "Literal",
        "ClassVar",
        "Final",
        "Self",
        "Type",
        "Protocol",
        "Annotated",
        "ConfigDict",
    }
    return {
        part.split(".")[-1]
        for part in normalized_parts
        if part.split(".")[-1] not in noise
    }


def looks_like_interface(base_name: str) -> bool:
    """Heuristically detect interface-like base types."""
    short = base_name.split(".")[-1]
    return (
        short in {"Protocol", "ABC"}
        or short.endswith("Protocol")
        or short.endswith("ABC")
    )


def extract_method_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
    """Extract method signature information from a function node."""
    params: list[tuple[str, str]] = []

    all_args = list(node.args.posonlyargs) + list(node.args.args)
    for i, arg in enumerate(all_args):
        if i == 0 and arg.arg in {"self", "cls"}:
            continue
        params.append((arg.arg, annotation_to_str(arg.annotation)))

    if node.args.vararg is not None:
        params.append(
            (f"*{node.args.vararg.arg}", annotation_to_str(node.args.vararg.annotation))
        )

    for arg in node.args.kwonlyargs:
        params.append((arg.arg, annotation_to_str(arg.annotation)))

    if node.args.kwarg is not None:
        params.append(
            (f"**{node.args.kwarg.arg}", annotation_to_str(node.args.kwarg.annotation))
        )

    return MethodInfo(node.name, params, annotation_to_str(node.returns))


def extract_class_level_attributes(node: ast.ClassDef) -> list[AttributeInfo]:
    """Extract class-level assignments and annotations as attributes."""
    attrs: dict[str, AttributeInfo] = {}

    for item in node.body:
        if isinstance(item, ast.Assign):
            inferred = infer_type_from_value(item.value)
            for target in item.targets:
                if isinstance(target, ast.Name):
                    if should_skip_pydantic_internal_attribute(target.id, inferred):
                        continue
                    attrs[target.id] = AttributeInfo(target.id, inferred)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            type_name = annotation_to_str(item.annotation) or infer_type_from_value(
                item.value
            )
            if should_skip_pydantic_internal_attribute(item.target.id, type_name):
                continue
            attrs[item.target.id] = AttributeInfo(
                item.target.id,
                type_name,
            )

    return sorted(attrs.values(), key=lambda a: a.name)


# Not used anymore ?
def extract_attributes_from_ctor(
    node: ast.ClassDef,
) -> list[AttributeInfo]:
    """Extract ``self`` attributes and inferred types from ``__init__``."""
    attrs: dict[str, AttributeInfo] = {}

    for item in node.body:
        if (
            not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            or item.name != "__init__"
        ):
            continue

        param_types: dict[str, str] = {}

        all_args = list(item.args.posonlyargs) + list(item.args.args)
        for i, arg in enumerate(all_args):
            if i == 0 and arg.arg == "self":
                continue
            param_types[arg.arg] = annotation_to_str(arg.annotation)

        if item.args.vararg is not None:
            param_types[item.args.vararg.arg] = annotation_to_str(
                item.args.vararg.annotation
            )

        for arg in item.args.kwonlyargs:
            param_types[arg.arg] = annotation_to_str(arg.annotation)

        if item.args.kwarg is not None:
            param_types[item.args.kwarg.arg] = annotation_to_str(
                item.args.kwarg.annotation
            )

        for sub in ast.walk(item):
            if isinstance(sub, ast.Assign):
                inferred_value_type = infer_type_from_value(sub.value)

                rhs_name = sub.value.id if isinstance(sub.value, ast.Name) else None
                propagated_type = param_types.get(rhs_name, "") if rhs_name else ""

                final_type = propagated_type or inferred_value_type

                for target in sub.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        current = attrs.get(target.attr)
                        chosen_type = (
                            current.type_name
                            if current and current.type_name
                            else final_type
                        )
                        attrs[target.attr] = AttributeInfo(target.attr, chosen_type)

            elif isinstance(sub, ast.AnnAssign):
                if (
                    isinstance(sub.target, ast.Attribute)
                    and isinstance(sub.target.value, ast.Name)
                    and sub.target.value.id == "self"
                ):
                    type_name = annotation_to_str(sub.annotation)
                    if not type_name and sub.value is not None:
                        if isinstance(sub.value, ast.Name):
                            type_name = param_types.get(sub.value.id, "")
                        if not type_name:
                            type_name = infer_type_from_value(sub.value)
                    attrs[sub.target.attr] = AttributeInfo(sub.target.attr, type_name)

    return sorted(attrs.values(), key=lambda a: a.name)
