"""
Author: ChatGPT
Two-phase Python UML extractor.
Phase 1:
    Discover Python classes recursively in a folder and write them to an inventory file.
Phase 2:
    Read the inventory and generate a Mermaid UML class diagram markdown file.
Features:
    - Recursive scan of Python packages/modules
    - Nested classes
    - Namespace/module-aware Mermaid output
    - Inheritance edges
    - Class attributes
    - __init__ instance attributes (self.x = ...)
    - Type extraction for attributes and methods
    - Ignores most Python dunder/special methods in UML output
    - More robust path resolution between discover and diagram phases

Examples:
    python -m mermaiden.py discover ./src --output classes.txt
    python -m mermaiden.py diagram classes.txt --output UMLdiagram.md
"""

from __future__ import annotations

import argparse
import ast
import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable


# to override the other extract_init_instance_attributes ?
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
                        chosen_type = (
                            current.type_name if current and current.type_name else final_type
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


IGNORED_SPECIAL_METHODS = {
    "__repr__",
    "__str__",
    "__hash__",
    "__bytes__",
    "__format__",
    "__bool__",
    "__dir__",
    "__sizeof__",
    "__enter__",
    "__exit__",
    "__aenter__",
    "__aexit__",
    "__copy__",
    "__deepcopy__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__del__",
}

EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "build",
    "dist",
}


class MermaidIdStyle(str, Enum):
    FLAT = "flat"
    ESCAPED = "escaped"


class RelationType(str, Enum):
    INHERITANCE = "<|--"
    COMPOSITION = "*--"
    AGGREGATION = "o--"
    ASSOCIATION = "-->"
    REALIZATION = "..|>"


@dataclass(frozen=True)
class AttributeInfo:
    name: str
    type_name: str = ""

    def render(self) -> str:
        vis = "-" if self.name.startswith("_") else "+"
        return f"{vis}{self.name}: {self.type_name}" if self.type_name else f"{vis}{self.name}"


@dataclass(frozen=True)
class MethodInfo:
    name: str
    params: list[tuple[str, str]] = field(default_factory=list)
    return_type: str = ""

    def render(self) -> str:
        vis = "-" if self.name.startswith("_") else "+"
        sig = ", ".join(f"{n}: {t}" if t else n for n, t in self.params)
        return f"{vis}{self.name}({sig}) {self.return_type}".rstrip()


@dataclass(frozen=True)
class Relation:
    source_fqcn: str
    target_name: str
    relation_type: RelationType
    reason: str = ""


@dataclass
class ClassInfo:
    class_id: str
    fqcn: str
    module: str
    qualname: str
    name: str
    filepath: str
    lineno: int
    bases: list[str] = field(default_factory=list)
    methods: list[MethodInfo] = field(default_factory=list)
    attributes: list[AttributeInfo] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)


@dataclass
class NamespaceNode:
    name: str
    full_name: str
    children: dict[str, "NamespaceNode"] = field(default_factory=dict)
    classes: list[ClassInfo] = field(default_factory=list)


def build_namespace_tree(classes: dict[str, ClassInfo]) -> NamespaceNode:
    root = NamespaceNode(name="", full_name="")

    for cls in classes.values():
        parts = [p for p in cls.module.split(".") if p]
        current = root
        prefix: list[str] = []

        for part in parts:
            prefix.append(part)
            full_name = ".".join(prefix)

            if part not in current.children:
                current.children[part] = NamespaceNode(
                    name=part,
                    full_name=full_name,
                )
            current = current.children[part]

        current.classes.append(cls)

    return root


def should_skip_path(path: Path) -> bool:
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def safe_mermaid_id(name: str, style: MermaidIdStyle = MermaidIdStyle.FLAT) -> str:
    """
    Build a Mermaid-safe identifier.

    Styles:
      - flat:
            replace non-alnum chars with "_"
            example: presentation.auth.login -> presentation_auth_login

      - escaped:
            keep dots and wrap identifier in backticks
            example: presentation.auth.login -> `presentation.auth.login`

    Notes:
      - In escaped mode, backticks inside the name are escaped defensively.
      - In flat mode, identifiers are normalized to [A-Za-z0-9_].
    """
    if style == MermaidIdStyle.ESCAPED:
        escaped = name.replace("`", r"\`")
        return f"`{escaped}`"

    out = []
    for ch in name:
        out.append(ch if ch.isalnum() else "_")
    result = "".join(out)
    if result and result[0].isdigit():
        result = "_" + result
    return result


"""
def safe_mermaid_id_legacy(name: str) -> str:
    out = []
    for ch in name:
        out.append(ch if ch.isalnum() else "_")
    result = "".join(out)
    if result and result[0].isdigit():
        result = "_" + result
    return result
"""


def normalize_path(path_str: str | Path, base_dir: Path | None = None) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        p = (base_dir / p if base_dir else p).resolve()
    else:
        p = p.resolve()
    return p


def is_package_dir(path: Path) -> bool:
    return path.is_dir() and (path / "__init__.py").exists()


def find_package_anchor(filepath: Path) -> Path:
    """
    Return the highest directory in the contiguous package chain
    containing this file.

    Example:
        src/myapp/domain/models/user.py
    where:
        myapp/__init__.py exists
        domain/__init__.py exists
        models/__init__.py exists

    returns:
        src/myapp

    If the file is itself __init__.py, its parent package dir is used.
    """
    current_dir = filepath.parent
    highest_package = None

    while is_package_dir(current_dir):
        highest_package = current_dir
        parent = current_dir.parent
        if parent == current_dir:
            break
        current_dir = parent

    return highest_package if highest_package is not None else filepath.parent


def find_import_root_for_file(filepath: Path) -> Path:
    """
    Return the directory that should act as the import root for this file.

    If the file belongs to a package chain:
        import root = parent of the highest package dir

    Example:
        src/myapp/domain/models/user.py
        -> import root = src

    If no package chain exists:
        import root = file parent
    """
    package_anchor = find_package_anchor(filepath)
    if is_package_dir(package_anchor):
        return package_anchor.parent
    return filepath.parent


def compute_module_name_from_packages(filepath: Path, fallback_root: Path | None = None) -> str:
    """
    Compute a Python module name by respecting __init__.py package boundaries.

    Priority:
      1. Use the file's package-derived import root
      2. If fallback_root is provided and is more appropriate, use it only if
         the file is relative to it and it does not cut through package logic
    """
    import_root = find_import_root_for_file(filepath)

    if fallback_root is not None:
        try:
            # Only use fallback root if it is an ancestor and not deeper than import root
            filepath.relative_to(fallback_root)
            try:
                import_root.relative_to(fallback_root)
                chosen_root = fallback_root
            except ValueError:
                chosen_root = import_root
        except ValueError:
            chosen_root = import_root
    else:
        chosen_root = import_root

    rel = filepath.relative_to(chosen_root).with_suffix("")
    parts = list(rel.parts)

    if parts and parts[-1] == "__init__":
        parts = parts[:-1]

    return ".".join(parts) if parts else filepath.stem


def parse_python_file(filepath: Path) -> ast.AST | None:
    try:
        return ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        print(f"[WARN] Skipping {filepath}: {exc}")
        return None


def compute_module_name(root_dir: Path, filepath: Path) -> str:
    # To search the __init__.py instead.
    return compute_module_name_from_packages(filepath, root_dir)


def compute_module_name_legacy(root_dir: Path, filepath: Path) -> str:
    rel = filepath.relative_to(root_dir).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else root_dir.name


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


def common_existing_parent(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    try:
        return Path(os.path.commonpath([str(p) for p in existing]))
    except ValueError:
        return None


def write_inventory(classes: Iterable[ClassInfo], output_file: Path, root_dir: Path) -> None:
    with output_file.open("w", encoding="utf-8") as f:
        f.write(f"# ROOT\t{root_dir}\n")
        f.write("# FQCN\tFILEPATH\tLINENO\tIMPORT_ROOT\n")
        for cls in sorted(classes, key=lambda c: c.fqcn):
            import_root = find_import_root_for_file(Path(cls.filepath))
            f.write(f"{cls.fqcn}\t{cls.filepath}\t{cls.lineno}\t{import_root}\n")


def write_inventory_legacy(classes: Iterable[ClassInfo], output_file: Path, root_dir: Path) -> None:
    with output_file.open("w", encoding="utf-8") as f:
        f.write(f"# ROOT\t{root_dir}\n")
        f.write("# FQCN\tFILEPATH\tLINENO\n")
        for cls in sorted(classes, key=lambda c: c.fqcn):
            f.write(f"{cls.fqcn}\t{cls.filepath}\t{cls.lineno}\n")


def read_inventory(
    inventory_file: Path,
) -> tuple[Path | None, list[tuple[str, Path, int, Path | None]]]:
    inventory_dir = inventory_file.parent.resolve()
    stored_root: Path | None = None
    rows: list[tuple[str, Path, int, Path | None]] = []

    with inventory_file.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            if line.startswith("# ROOT\t"):
                root_str = line.split("\t", 1)[1]
                stored_root = normalize_path(root_str, inventory_dir)
                continue

            if line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) not in {3, 4}:
                print(f"[WARN] Ignoring malformed line: {line}")
                continue

            fqcn, path_text, lineno_text = parts[:3]
            import_root = normalize_path(parts[3], inventory_dir) if len(parts) == 4 else None

            try:
                lineno = int(lineno_text)
            except ValueError:
                print(f"[WARN] Invalid line number in line: {line}")
                continue

            filepath = normalize_path(path_text, inventory_dir)
            rows.append((fqcn, filepath, lineno, import_root))

    return stored_root, rows


def read_inventory_legacy(inventory_file: Path) -> tuple[Path | None, list[tuple[str, Path, int]]]:
    inventory_dir = inventory_file.parent.resolve()
    stored_root: Path | None = None
    rows: list[tuple[str, Path, int]] = []

    with inventory_file.open("r", encoding="utf-8") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("# ROOT\t"):
                stored_root = normalize_path(line.split("\t", 1)[1], inventory_dir)
                continue
            if line.startswith("#"):
                continue

            parts = line.split("\t")
            if len(parts) != 3:
                print(f"[WARN] Ignoring malformed line: {line}")
                continue

            fqcn, path_text, lineno_text = parts
            try:
                lineno = int(lineno_text)
            except ValueError:
                print(f"[WARN] Invalid line number: {line}")
                continue

            rows.append((fqcn, normalize_path(path_text, inventory_dir), lineno))

    return stored_root, rows


def guess_root_from_inventory(
    stored_root: Path | None, rows: list[tuple[str, Path, int, Path | None]]
) -> Path | None:
    if stored_root is not None and stored_root.exists():
        return stored_root

    filepaths = [p for _, p, _, _ in rows if p.exists()]
    if not filepaths:
        return None

    # This is only a coarse hint. Final module names must still be
    # computed with package-aware logic.
    try:
        return Path(os.path.commonpath([str(p.parent) for p in filepaths]))
    except ValueError:
        return None


"""
def guess_root_from_inventory_legacy(
    stored_root: Path | None, rows: list[tuple[str, Path, int, Path | None]]
) -> Path | None:
    if stored_root and stored_root.exists():
        return stored_root
    return common_existing_parent([p for _, p, _, _ in rows])
"""


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


class RelationCollector:
    def __init__(self, class_node: ast.ClassDef, module_name: str, qualname: str) -> None:
        self.class_node = class_node
        self.module_name = module_name
        self.qualname = qualname

    def collect(self, current_fqcn: str) -> tuple[list[AttributeInfo], list[Relation]]:
        attrs: dict[str, AttributeInfo] = {}
        relations: dict[tuple[str, str, RelationType], Relation] = {}

        for item in self.class_node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
                init_attrs, init_relations = self._collect_init_relations(item, current_fqcn)
                for attr in init_attrs:
                    prev = attrs.get(attr.name)
                    if prev is None or (not prev.type_name and attr.type_name):
                        attrs[attr.name] = attr
                for rel in init_relations:
                    relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for rel in self._collect_method_associations(item, current_fqcn):
                    key = (rel.source_fqcn, rel.target_name, rel.relation_type)
                    relations[key] = rel

        return sorted(attrs.values(), key=lambda a: a.name), list(relations.values())

    def _collect_init_relations(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        current_fqcn: str,
    ) -> tuple[list[AttributeInfo], list[Relation]]:
        attrs: dict[str, AttributeInfo] = {}
        relations: dict[tuple[str, str, RelationType], Relation] = {}
        param_types: dict[str, str] = {}

        all_args = list(node.args.posonlyargs) + list(node.args.args)
        for i, arg in enumerate(all_args):
            if i == 0 and arg.arg == "self":
                continue
            param_types[arg.arg] = annotation_to_str(arg.annotation)

        if node.args.vararg is not None:
            param_types[node.args.vararg.arg] = annotation_to_str(node.args.vararg.annotation)
        for arg in node.args.kwonlyargs:
            param_types[arg.arg] = annotation_to_str(arg.annotation)
        if node.args.kwarg is not None:
            param_types[node.args.kwarg.arg] = annotation_to_str(node.args.kwarg.annotation)

        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                rhs_name = sub.value.id if isinstance(sub.value, ast.Name) else None
                rhs_call_name = (
                    expr_to_name(sub.value.func) if isinstance(sub.value, ast.Call) else ""
                )
                rhs_inferred_type = infer_type_from_value(sub.value)
                propagated_type = param_types.get(rhs_name, "") if rhs_name else ""
                final_type = propagated_type or rhs_inferred_type

                for target in sub.targets:
                    if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                    ):
                        attrs[target.attr] = AttributeInfo(target.attr, final_type)

                        if rhs_call_name:
                            rel = Relation(
                                source_fqcn=current_fqcn,
                                target_name=rhs_call_name,
                                relation_type=RelationType.COMPOSITION,
                                reason="self attribute initialized from constructor call",
                            )
                            relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel
                        elif rhs_name and propagated_type:
                            for dep in split_type_names(propagated_type):
                                rel = Relation(
                                    source_fqcn=current_fqcn,
                                    target_name=dep,
                                    relation_type=RelationType.AGGREGATION,
                                    reason="self attribute assigned from injected parameter",
                                )
                                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = (
                                    rel
                                )
                        elif final_type:
                            for dep in split_type_names(final_type):
                                rel = Relation(
                                    source_fqcn=current_fqcn,
                                    target_name=dep,
                                    relation_type=RelationType.ASSOCIATION,
                                    reason="self attribute typed or inferred",
                                )
                                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = (
                                    rel
                                )

            elif isinstance(sub, ast.AnnAssign):
                if (
                    isinstance(sub.target, ast.Attribute)
                    and isinstance(sub.target.value, ast.Name)
                    and sub.target.value.id == "self"
                ):
                    ann_type = annotation_to_str(sub.annotation)
                    rhs_call_name = (
                        expr_to_name(sub.value.func) if isinstance(sub.value, ast.Call) else ""
                    )
                    rhs_param_name = sub.value.id if isinstance(sub.value, ast.Name) else None
                    propagated_type = param_types.get(rhs_param_name, "") if rhs_param_name else ""
                    final_type = ann_type or propagated_type or infer_type_from_value(sub.value)

                    attrs[sub.target.attr] = AttributeInfo(sub.target.attr, final_type)

                    if rhs_call_name:
                        rel = Relation(
                            source_fqcn=current_fqcn,
                            target_name=rhs_call_name,
                            relation_type=RelationType.COMPOSITION,
                            reason="annotated self attribute initialized from constructor call",
                        )
                        relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel
                    elif rhs_param_name and propagated_type:
                        for dep in split_type_names(propagated_type):
                            rel = Relation(
                                source_fqcn=current_fqcn,
                                target_name=dep,
                                relation_type=RelationType.AGGREGATION,
                                reason="annotated self attribute assigned from injected parameter",
                            )
                            relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel
                    elif final_type:
                        for dep in split_type_names(final_type):
                            rel = Relation(
                                source_fqcn=current_fqcn,
                                target_name=dep,
                                relation_type=RelationType.ASSOCIATION,
                                reason="annotated self attribute typed or inferred",
                            )
                            relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        return list(attrs.values()), list(relations.values())

    def _collect_method_associations(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        current_fqcn: str,
    ) -> list[Relation]:
        relations: dict[tuple[str, str, RelationType], Relation] = {}

        for _, t in extract_method_info(node).params:
            for dep in split_type_names(t):
                rel = Relation(current_fqcn, dep, RelationType.ASSOCIATION, "method parameter type")
                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        for dep in split_type_names(annotation_to_str(node.returns)):
            rel = Relation(current_fqcn, dep, RelationType.ASSOCIATION, "method return type")
            relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        for sub in ast.walk(node):
            if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                for dep in split_type_names(annotation_to_str(sub.annotation)):
                    rel = Relation(
                        current_fqcn, dep, RelationType.ASSOCIATION, "typed local variable"
                    )
                    relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

            if isinstance(sub, ast.Call):
                callee = expr_to_name(sub.func)
                short = callee.split(".")[-1]
                if short and short[:1].isupper():
                    rel = Relation(
                        current_fqcn, short, RelationType.ASSOCIATION, "uses class in method body"
                    )
                    relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        return list(relations.values())


class ClassCollector(ast.NodeVisitor):
    def __init__(self, module_name: str, filepath: Path, style: str = "flat") -> None:
        self.module_name = module_name
        self.filepath = filepath
        self.classes: list[ClassInfo] = []
        self._class_stack: list[str] = []
        self.style = style

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = ".".join([*self._class_stack, node.name]) if self._class_stack else node.name
        fqcn = f"{self.module_name}.{qualname}" if self.module_name else qualname
        class_id = mermaid_id(fqcn, self.style)

        bases = [expr_to_name(base) for base in node.bases if expr_to_name(base)]
        class_attrs = extract_class_level_attributes(node)

        relation_collector = RelationCollector(node, self.module_name, qualname)
        init_attrs, relations = relation_collector.collect(fqcn)

        attrs_map: dict[str, AttributeInfo] = {}
        for attr in class_attrs + init_attrs:
            prev = attrs_map.get(attr.name)
            if prev is None or (not prev.type_name and attr.type_name):
                attrs_map[attr.name] = attr

        methods = [
            extract_method_info(item)
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            and should_include_method(item.name)
        ]

        self.classes.append(
            ClassInfo(
                class_id=class_id,
                fqcn=fqcn,
                module=self.module_name,
                qualname=qualname,
                name=node.name,
                filepath=str(self.filepath),
                lineno=node.lineno,
                bases=bases,
                methods=sorted(methods, key=lambda m: m.name),
                attributes=sorted(attrs_map.values(), key=lambda a: a.name),
                relations=relations,
            )
        )

        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()


def discover_classes(root_dir: Path, style: str = "flat") -> list[ClassInfo]:
    found: list[ClassInfo] = []
    for filepath in sorted(root_dir.rglob("*.py")):
        if should_skip_path(filepath) and not filepath.is_file():
            continue
        tree = parse_python_file(filepath)
        if tree is None:
            continue
        # now use the __init__.py package navigation and namespace
        module_name = compute_module_name(root_dir, filepath)
        collector = ClassCollector(module_name, filepath, style=style)
        collector.visit(tree)
        found.extend(collector.classes)
    return found


def rebuild_class_map_from_inventory(
    inventory_file: Path, style: str = "flat"
) -> dict[str, ClassInfo]:
    """
    Rebuild ClassInfo objects from the inventory, preserving correct module names.

    Matching strategy per requested FQCN, in order:
      1. Exact FQCN match from package-aware parsing
      2. Exact qualname match within the same file
      3. Exact terminal class name match within the same file, only if unique

    This avoids the old fallback that could attach the wrong module to a class
    just because the short class name happened to match.
    """
    stored_root, requested = read_inventory(inventory_file)
    if not requested:
        return {}

    # requested_fqcns = {fqcn for fqcn, _, *_ in requested}
    root_hint = guess_root_from_inventory(stored_root, requested)

    existing_files = sorted({filepath for _, filepath, *_ in requested if filepath.exists()})
    if not existing_files:
        print("[WARN] None of the inventory file paths currently exist.")
        return {}

    # Parse each file once, using package-aware module reconstruction.
    parsed_by_file: dict[Path, list[ClassInfo]] = {}
    fqcn_index: dict[str, ClassInfo] = {}

    for filepath in existing_files:
        tree = parse_python_file(filepath)
        if tree is None:
            continue

        module_name = compute_module_name_from_packages(filepath, root_hint)
        collector = ClassCollector(module_name=module_name, filepath=filepath, style=style)
        collector.visit(tree)

        parsed_by_file[filepath] = collector.classes
        for cls in collector.classes:
            fqcn_index[cls.fqcn] = cls

    class_map: dict[str, ClassInfo] = {}

    for entry in requested:
        # Support both 3-column and future 4-column inventory rows
        fqcn = entry[0]
        filepath = entry[1]

        if fqcn in class_map or not filepath.exists():
            continue

        requested_parts = fqcn.split(".")
        requested_short_name = requested_parts[-1]

        candidates = parsed_by_file.get(filepath, [])
        if not candidates:
            continue

        # ------------------------------------------------------------------
        # 1. Exact parsed FQCN match
        # ------------------------------------------------------------------
        direct = fqcn_index.get(fqcn)
        if direct is not None and Path(direct.filepath) == filepath:
            class_map[fqcn] = direct
            continue

        # ------------------------------------------------------------------
        # 2. Exact qualname match inferred from requested FQCN tail
        #    Example:
        #      fqcn = pkg.mod.Outer.Inner
        #      qualname candidate = Outer.Inner
        # ------------------------------------------------------------------
        qualname_matches: list[ClassInfo] = []
        for cls in candidates:
            if fqcn.endswith("." + cls.qualname):
                qualname_matches.append(cls)

        if len(qualname_matches) == 1:
            matched = qualname_matches[0]
            rebuilt = ClassInfo(
                class_id=mermaid_id(fqcn, style=style),
                fqcn=fqcn,
                module=fqcn[: -(len(matched.qualname) + 1)],
                qualname=matched.qualname,
                name=matched.name,
                filepath=matched.filepath,
                lineno=matched.lineno,
                bases=matched.bases,
                methods=matched.methods,
                attributes=matched.attributes,
                relations=matched.relations,
            )
            class_map[fqcn] = rebuilt
            continue

        # ------------------------------------------------------------------
        # 3. Unique terminal class-name match inside the same file
        #    Only accept if unique, to avoid collisions like:
        #      Outer.User and Another.User in the same file
        # ------------------------------------------------------------------
        short_matches = [cls for cls in candidates if cls.name == requested_short_name]

        if len(short_matches) == 1:
            matched = short_matches[0]

            # Rebuild module from requested fqcn + parsed qualname when possible.
            if fqcn.endswith("." + matched.qualname):
                rebuilt_module = fqcn[: -(len(matched.qualname) + 1)]
                rebuilt_qualname = matched.qualname
            else:
                # Conservative fallback:
                # keep parsed qualname, infer module from remaining prefix
                rebuilt_qualname = matched.qualname
                if "." in fqcn:
                    prefix = fqcn.rsplit(".", 1)[0]
                    # Only trust the requested prefix as module if the terminal name
                    # matches but qualname does not give us anything better.
                    rebuilt_module = prefix
                else:
                    rebuilt_module = matched.module

            rebuilt = ClassInfo(
                class_id=mermaid_id(fqcn, style=style),
                fqcn=fqcn,
                module=rebuilt_module,
                qualname=rebuilt_qualname,
                name=matched.name,
                filepath=matched.filepath,
                lineno=matched.lineno,
                bases=matched.bases,
                methods=matched.methods,
                attributes=matched.attributes,
                relations=matched.relations,
            )
            class_map[fqcn] = rebuilt
            continue

        # ------------------------------------------------------------------
        # 4. No safe match
        # ------------------------------------------------------------------
        print(f"[WARN] Could not safely rebuild class from inventory entry: {fqcn} ({filepath})")

    return class_map


"""
def rebuild_class_map_from_inventory_legacy(inventory_file: Path) -> dict[str, ClassInfo]:
    stored_root, requested = read_inventory(inventory_file)
    requested_fqcns = {fqcn for fqcn, _, _ in requested}
    if not requested:
        return {}

    root_dir = guess_root_from_inventory(stored_root, requested)
    filepaths = sorted({p for _, p, _ in requested if p.exists()})
    if not filepaths:
        return {}

    class_map: dict[str, ClassInfo] = {}

    if root_dir is not None:
        for filepath in filepaths:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            try:
                module_name = (
                    compute_module_name_from_packages(filepath, stored_root)
                    if stored_root is not None
                    else compute_module_name_from_packages(filepath, root_dir)
                )
            except Exception:
                module_name = filepath.with_suffix("").name
            collector = ClassCollector(module_name, filepath)
            collector.visit(tree)
            for cls in collector.classes:
                if cls.fqcn in requested_fqcns:
                    class_map[cls.fqcn] = cls

    missing = requested_fqcns - set(class_map)
    if missing:
        by_file: dict[Path, list[ClassInfo]] = {}
        for filepath in filepaths:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            collector = ClassCollector(filepath.with_suffix("").name, filepath)
            collector.visit(tree)
            by_file[filepath] = collector.classes

        for fqcn, filepath, _ in requested:
            if fqcn in class_map or not filepath.exists():
                continue
            short_name = fqcn.split(".")[-1]
            for cls in by_file.get(filepath, []):
                if cls.name == short_name or fqcn.endswith("." + cls.qualname):
                    cls.fqcn = fqcn
                    cls.class_id = safe_mermaid_id(fqcn)
                    if fqcn.endswith("." + cls.qualname):
                        cls.module = fqcn[: -(len(cls.qualname) + 1)]
                    class_map[fqcn] = cls
                    break

    return class_map
"""


def resolve_target_name(
    target_name: str, current_class: ClassInfo, known_classes: dict[str, ClassInfo]
) -> str | None:
    if target_name in known_classes:
        return target_name

    same_module = f"{current_class.module}.{target_name}" if current_class.module else target_name
    if same_module in known_classes:
        return same_module

    suffix_matches = [
        fqcn for fqcn in known_classes if fqcn.endswith(f".{target_name}") or fqcn == target_name
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


def merge_relation(existing: RelationType, new: RelationType) -> RelationType:
    priority = {
        RelationType.INHERITANCE: 5,
        RelationType.REALIZATION: 4,
        RelationType.COMPOSITION: 3,
        RelationType.AGGREGATION: 2,
        RelationType.ASSOCIATION: 1,
    }
    return existing if priority[existing] >= priority[new] else new


def collect_all_relations(classes: dict[str, ClassInfo]) -> list[tuple[str, RelationType, str]]:
    resolved: dict[tuple[str, str], RelationType] = {}

    for cls in classes.values():
        for base in cls.bases:
            target = resolve_target_name(base, cls, classes)
            if not target:
                continue
            rel_type = (
                RelationType.REALIZATION if looks_like_interface(base) else RelationType.INHERITANCE
            )
            key = (target, cls.fqcn)
            resolved[key] = merge_relation(resolved.get(key, rel_type), rel_type)

        for rel in cls.relations:
            target = resolve_target_name(rel.target_name, cls, classes)
            if not target or target == cls.fqcn:
                continue
            key = (cls.fqcn, target)
            resolved[key] = merge_relation(resolved.get(key, rel.relation_type), rel.relation_type)

    return [(src, rtype, tgt) for (src, tgt), rtype in sorted(resolved.items())]


def mermaid_class_block(cls: ClassInfo) -> list[str]:
    lines = [f'class {cls.class_id}["{cls.qualname}"]' + " {"]
    for attr in cls.attributes:
        lines.append(f"  {attr.render()}")
    for method in cls.methods:
        lines.append(f"  {method.render()}")
    lines.append("}")
    return lines


def render_nested_namespace_lines(
    node: NamespaceNode, indent: int = 0, style: str = "flat"
) -> list[str]:
    lines: list[str] = []
    pad = "  " * indent

    for child_name in sorted(node.children):
        child = node.children[child_name]
        ns_id = mermaid_id(child.full_name, style=style)
        # lines.append(f'{pad}namespace {ns_id}["{child.name}"]' + '{')
        lines.append(f"{pad}namespace {ns_id}" + "{")  # not supported renaming namespaces

        # child classes
        for cls in sorted(child.classes, key=lambda c: c.qualname):
            for row in mermaid_class_block(cls):
                lines.append(f"{pad}  {row}")

        # grandchildren
        lines.extend(render_nested_namespace_lines(child, indent + 1, style=style))
        lines.append(f"{pad}" + "}")

    return lines


def render_compat_namespace_lines(node: NamespaceNode, style: str = "flat") -> list[str]:
    """
    Compatibility mode for Mermaid namespace rendering bugs.

    Example:
        namespace presentation {
            class presentation_auth
            class presentation_main
        }
        namespace presentation_auth {
            class AuthScreen
        }
        namespace presentation_main {
            class MainScreen
        }
    """
    lines: list[str] = []

    def visit(current: NamespaceNode) -> None:
        # Skip synthetic root node
        if current.full_name:
            ns_id = mermaid_id(current.full_name, style=style)
            # lines.append(f'{pad}namespace {ns_id}["{current.name}"]' + '{')
            lines.append(f"namespace {ns_id}" + "{")  # not supported renaming namespaces

            # Represent child namespaces as synthetic classes
            for child_name in sorted(current.children):
                child = current.children[child_name]
                child_ns_id = mermaid_id(child.full_name, style=style)
                lines.append(f"  class {child_ns_id}")

            # Emit classes that belong directly to this namespace
            for cls in sorted(current.classes, key=lambda c: c.qualname):
                for row in mermaid_class_block(cls):
                    lines.append(f"  {row}")

            lines.append("}")

        # Recurse into every child namespace
        for child_name in sorted(current.children):
            visit(current.children[child_name])

    visit(node)
    return lines


def mermaid_id(name: str, style: str = "flat") -> str:
    return safe_mermaid_id(name, MermaidIdStyle(style))


def generate_mermaid(
    classes: dict[str, ClassInfo],
    namespace: str = "nested",
    style: str = "flat",
) -> str:
    lines: list[str] = [
        "# UML Class Diagram",
        "",
        "```mermaid",
        "classDiagram",
    ]

    tree = build_namespace_tree(classes)

    # Classes without a module
    for cls in sorted(tree.classes, key=lambda c: c.qualname):
        for row in mermaid_class_block(cls):
            lines.append(row)

    if namespace == "nested":
        lines.extend(render_nested_namespace_lines(tree, style=style))
    elif namespace == "legacy":
        lines.extend(render_compat_namespace_lines(tree, style=style))
    else:
        raise ValueError(f"Unsupported namespace: {namespace}")

    lines.append("")

    for src_fqcn, rel_type, tgt_fqcn in collect_all_relations(classes):
        src_id = classes[src_fqcn].class_id
        tgt_id = classes[tgt_fqcn].class_id
        lines.append(f"{src_id} {rel_type.value} {tgt_id}")

    lines.extend(["```", ""])
    return "\n".join(lines)


def write_mermaid_markdown(
    classes: dict[str, ClassInfo],
    output_file: Path,
    namespace: str = "nested",
    style: str = "flat",
) -> None:
    output_file.write_text(
        generate_mermaid(
            classes,
            namespace=namespace,
            style=style,
        ),
        encoding="utf-8",
    )


def cmd_discover(args: argparse.Namespace) -> int:
    root_dir = normalize_path(args.root)
    output_file = normalize_path(args.output)

    if not root_dir.exists() or not root_dir.is_dir():
        print(f"[ERROR] Not a valid directory: {root_dir}")
        return 1

    classes = discover_classes(root_dir, style=args.style)
    write_inventory(classes, output_file, root_dir)

    print(f"[OK] Discovered {len(classes)} classes")
    print(f"[OK] Inventory written to: {output_file}")
    return 0


def cmd_diagram(args: argparse.Namespace) -> int:
    inventory_file = normalize_path(args.inventory)
    output_file = normalize_path(args.output)

    if not inventory_file.exists():
        print(f"[ERROR] Inventory file not found: {inventory_file}")
        return 1

    classes = rebuild_class_map_from_inventory(inventory_file, style=args.style)
    if not classes:
        print("[ERROR] No classes could be rebuilt from inventory")
        return 1

    write_mermaid_markdown(
        classes,
        output_file,
        namespace=args.namespace,
        style=args.style,
    )
    print(f"[OK] Mermaid diagram written to: {output_file}")
    print(f"[OK] Included {len(classes)} classes")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Discover Python classes and generate Mermaid UML diagrams"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p1 = subparsers.add_parser("discover", help="Scan a root folder and write class inventory")
    p1.add_argument("root", help="Root folder to scan")
    p1.add_argument("--output", default="classes.txt", help="Inventory output file")
    p1.set_defaults(func=cmd_discover)

    p2 = subparsers.add_parser("diagram", help="Generate Mermaid UML from inventory")
    p2.add_argument("inventory", help="Inventory file")
    p2.add_argument("--output", default="UMLdiagram.md", help="Markdown output file")
    p2.set_defaults(func=cmd_diagram)
    p2.add_argument(
        "--namespace",
        choices=["nested", "legacy"],
        default="nested",
        help="Namespace rendering mode: nested namespaces or legacy for compatibility fallback",
    )
    p2.add_argument(
        "--style",
        choices=["flat", "escaped"],
        default="flat",
        help="How Mermaid identifiers are emitted",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())


