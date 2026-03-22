from __future__ import annotations

import ast

from models import AttributeInfo, IGNORED_SPECIAL_METHODS, MethodInfo


def expr_to_name(node: ast.AST | None) -> str:
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
    return expr_to_name(node)


def infer_type_from_value(node: ast.AST | None) -> str:
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
    if isinstance(node, ast.Call):
        return expr_to_name(node.func)
    return ""


def is_special_method(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def should_include_method(name: str) -> bool:
    if name == "__init__":
        return False
    if name in IGNORED_SPECIAL_METHODS:
        return False
    if is_special_method(name):
        return False
    return True


def split_type_names(type_name: str) -> set[str]:
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
    noise = {
        "list",
        "dict",
        "set",
        "tuple",
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
    }
    return {p.split(".")[-1] for p in parts if p not in noise}


def looks_like_interface(base_name: str) -> bool:
    short = base_name.split(".")[-1]
    return short in {"Protocol", "ABC"} or short.endswith("Protocol") or short.endswith("ABC")


def extract_method_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
    params: list[tuple[str, str]] = []

    all_args = list(node.args.posonlyargs) + list(node.args.args)
    for i, arg in enumerate(all_args):
        if i == 0 and arg.arg in {"self", "cls"}:
            continue
        params.append((arg.arg, annotation_to_str(arg.annotation)))

    if node.args.vararg is not None:
        params.append((f"*{node.args.vararg.arg}", annotation_to_str(node.args.vararg.annotation)))

    for arg in node.args.kwonlyargs:
        params.append((arg.arg, annotation_to_str(arg.annotation)))

    if node.args.kwarg is not None:
        params.append((f"**{node.args.kwarg.arg}", annotation_to_str(node.args.kwarg.annotation)))

    return MethodInfo(node.name, params, annotation_to_str(node.returns))


def extract_class_level_attributes(node: ast.ClassDef) -> list[AttributeInfo]:
    attrs: dict[str, AttributeInfo] = {}

    for item in node.body:
        if isinstance(item, ast.Assign):
            inferred = infer_type_from_value(item.value)
            for target in item.targets:
                if isinstance(target, ast.Name):
                    attrs[target.id] = AttributeInfo(target.id, inferred)
        elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
            attrs[item.target.id] = AttributeInfo(
                item.target.id,
                annotation_to_str(item.annotation) or infer_type_from_value(item.value),
            )

    return sorted(attrs.values(), key=lambda a: a.name)


def extract_init_instance_attributes_types_from_constructor(
    node: ast.ClassDef,
) -> list[AttributeInfo]:
    attrs: dict[str, AttributeInfo] = {}

    for item in node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) or item.name != "__init__":
            continue

        param_types: dict[str, str] = {}

        all_args = list(item.args.posonlyargs) + list(item.args.args)
        for i, arg in enumerate(all_args):
            if i == 0 and arg.arg == "self":
                continue
            param_types[arg.arg] = annotation_to_str(arg.annotation)

        if item.args.vararg is not None:
            param_types[item.args.vararg.arg] = annotation_to_str(item.args.vararg.annotation)

        for arg in item.args.kwonlyargs:
            param_types[arg.arg] = annotation_to_str(arg.annotation)

        if item.args.kwarg is not None:
            param_types[item.args.kwarg.arg] = annotation_to_str(item.args.kwarg.annotation)

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
                        chosen_type = current.type_name if current and current.type_name else final_type
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
