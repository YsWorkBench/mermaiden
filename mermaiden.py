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
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------

# Configuration

# ---------------------------------------------------------------------------

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
    "__a! exit__",
    "__copy__",
    "__deepcopy__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__del__",
}

VISIBILITY_PRIVATE_PREFIX = "_"
# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

"""
from dataclasses import dataclass
from abc import ABCMeta
from typing import ClassVar

@dataclass
class Product(metaclass=ABCMeta):
    c_type: ClassVar[str]
    c_brand: ClassVar[str]
    name: str

The instance attributes are now defined at the place of the classattributes for better visibility.
There typing.ClassVar is the new way of defining class methods.
ChatGPT's only supports types for attributes from this @dataclass.
And it was struggling with the __init__. 
"""

@dataclass
class AttributeInfo:
    name: str
    type_name: str = ""
    def render(self) -> str:
        vis = "-" if self.name.startswith(VISIBILITY_PRIVATE_PREFIX) else "+"
        if self.type_name:
            return f"{vis}{self.name}: {self.type_name}"
        return f"{vis}{self.name}"

@dataclass
class MethodInfo:
    name: str
    params: list[tuple[str, str]] = field(default_factory=list)  # (name, type)
    return_type: str = ""
    def render(self) -> str:
        vis = "-" if self.name.startswith(VISIBILITY_PRIVATE_PREFIX) else "+"
        rendered_params = []
        for param_name, param_type in self.params:
            if param_type:
                rendered_params.append(f"{param_name}: {param_type}")
            else:
                rendered_params.append(param_name)
        sig = ", ".join(rendered_params)
        if self.return_type:
            return f"{vis}{self.name}({sig}) {self.return_type}"
        return f"{vis}{self.name}({sig})"

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

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def safe_mermaid_id(name: str) -> str:
    out = []
    for ch in name:
        if ch.isalnum():
            out.append(ch)
        else:
            out.append("_")
    value = "".join(out)
    if value and value[0].isdigit():
        value = f"_{value}"
    return value

def normalize_path(path_str: str | Path, base_dir: Path | None = None) -> Path:
    p = Path(path_str)
    if not p.is_absolute():
        if base_dir is not None:
            p = (base_dir / p).resolve()
        else:
            p = p.resolve()
    else:
        p = p.resolve()
    return p

def common_existing_parent(paths: list[Path]) -> Path | None:
    existing = [p for p in paths if p.exists()]
    if not existing:
        return None
    try:
        return Path(os.path.commonpath([str(p) for p in existing]))
    except ValueError:
        return None
    
def parse_python_file(filepath: Path) -> ast.AST | None:
    try:
        source = filepath.read_text(encoding="utf-8")
        return ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError, OSError) as exc:
        print(f"[WARN] Skipping {filepath}: {exc}")
        return None
    
def compute_module_name(root_dir: Path, filepath: Path) -> str:
    rel = filepath.relative_to(root_dir)
    no_suffix = rel.with_suffix("")
    parts = list(no_suffix.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return root_dir.name
    return ".".join(parts)

def expr_to_name(node: ast.AST | None) -> str:
    if node is None:
        return None
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
        return ", ".join(expr_to_name(elt) for elt in node.elts)
    if isinstance(node, ast.List):
        return ", ".join(expr_to_name(elt) for elt in node.elts)
    if isinstance(node, ast.Constant):
        if node.value is Ellipsis:
            return "..."
        return repr(node.value)
    if isinstance(node, ast.Call):
        return expr_to_name(node.func)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = expr_to_name(node.left)
        right = expr_to_name(node.right)
        return f"{left} | {right}"
    return ""

def annotation_to_str(node: ast.AST | None) -> str:
    return expr_to_name(node)

def infer_type_from_value(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Constant):
        if node.value is None:
            return "None"
        return type(node.value).__name__
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

def visibility_prefix(name: str) -> str:
    return "-" if name.startswith(VISIBILITY_PRIVATE_PREFIX) else "+"

# ---------------------------------------------------------------------------
# AST extraction
# ---------------------------------------------------------------------------

def extract_method_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> MethodInfo:
    params: list[tuple[str, str]] = []
    # positional-only and normal args
    all_args = list(node.args.posonlyargs) + list(node.args.args)
    for i, arg in enumerate(all_args):
        # skip self/cls in methods
        if i == 0 and arg.arg in {"self", "cls"}:
            continue
        params.append((arg.arg, annotation_to_str(arg.annotation)))
    # *args
    if node.args.vararg is not None:
        params.append((f"*{node.args.vararg.arg}", annotation_to_str(node.args.vararg.annotation)))
    # keyword-only
    for arg in node.args.kwonlyargs:
        params.append((arg.arg, annotation_to_str(arg.annotation)))
    # **kwargs
    if node.args.kwarg is not None:
        params.append((f"**{node.args.kwarg.arg}", annotation_to_str(node.args.kwarg.annotation)))
    return_type = annotation_to_str(node.returns)
    return MethodInfo(
        name=node.name,
        params=params,
        return_type=return_type,
    )

def extract_class_level_attributes(node: ast.ClassDef) -> list[AttributeInfo]:
    attrs: dict[str, AttributeInfo] = {}
    for item in node.body:
        if isinstance(item, ast.Assign):
            inferred = infer_type_from_value(item.value)
            for target in item.targets:
                if isinstance(target, ast.Name):
                    attrs[target.id] = AttributeInfo(target.id, inferred)
        elif isinstance(item, ast.AnnAssign):
            if isinstance(item.target, ast.Name):
                type_name = annotation_to_str(item.annotation)
                if not type_name and item.value is not None:
                    type_name = infer_type_from_value(item.value)
                attrs[item.target.id] = AttributeInfo(item.target.id, type_name)
    return sorted(attrs.values(), key=lambda a: a.name)

def extract_init_instance_attributes(node: ast.ClassDef) -> list[AttributeInfo]:
    attrs: dict[str, AttributeInfo] = {}
    for item in node.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__":
            for sub in ast.walk(item):
                if isinstance(sub, ast.Assign):
                    value_type = infer_type_from_value(sub.value)
                    for target in sub.targets:
                        if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                        ):
                            current = attrs.get(target.attr)
                            chosen_type = current.type_name if current and current.type_name else value_type
                            attrs[target.attr] = AttributeInfo(target.attr, chosen_type)
                elif isinstance(sub, ast.AnnAssign):
                    if (
                        isinstance(sub.target, ast.Attribute)
                        and isinstance(sub.target.value, ast.Name)
                        and sub.target.value.id == "self"
                    ):
                        type_name = annotation_to_str(sub.annotation)
                        if not type_name and sub.value is not None:
                            type_name = infer_type_from_value(sub.value)
                        attrs[sub.target.attr] = AttributeInfo(sub.target.attr, type_name)
    return sorted(attrs.values(), key=lambda a: a.name)

class ClassCollector(ast.NodeVisitor):
    def __init__(self, module_name: str, filepath: Path) -> None:
        self.module_name = module_name
        self.filepath = filepath
        self.classes: list[ClassInfo] = []
        self._class_stack: list[str] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualname = ".".join([*self._class_stack, node.name]) if self._class_stack else node.name
        fqcn = f"{self.module_name}.{qualname}" if self.module_name else qualname
        class_id = safe_mermaid_id(fqcn)
        bases = [expr_to_name(base) for base in node.bases if expr_to_name(base)]
        class_attrs = extract_class_level_attributes(node)
        init_attrs = extract_init_instance_attributes(node)
        combined_attrs: dict[str, AttributeInfo] = {}
        for attr in class_attrs + init_attrs:
            existing = combined_attrs.get(attr.name)
            if existing is None or (not existing.type_name and attr.type_name):
                combined_attrs[attr.name] = attr
        methods: list[MethodInfo] = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if should_include_method(item.name):
                    methods.append(extract_method_info(item))
        info = ClassInfo(
            class_id=class_id,
            fqcn=fqcn,
            module=self.module_name,
            qualname=qualname,
            name=node.name,
            filepath=str(self.filepath),
            lineno=node.lineno,
            bases=bases,
            methods=sorted(methods, key=lambda m: m.name),
            attributes=sorted(combined_attrs.values(), key=lambda a: a.name),
        )
        self.classes.append(info)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

def discover_classes(root_dir: Path) -> list[ClassInfo]:
    discovered: list[ClassInfo] = []
    for filepath in sorted(root_dir.rglob("*.py")):
        if not filepath.is_file():
            continue
        tree = parse_python_file(filepath)
        if tree is None:
            continue
        module_name = compute_module_name(root_dir, filepath)
        collector = ClassCollector(module_name=module_name, filepath=filepath)
        collector.visit(tree)
        discovered.extend(collector.classes)
    return discovered

# ---------------------------------------------------------------------------
# Inventory format
# ---------------------------------------------------------------------------

def write_inventory(classes: Iterable[ClassInfo], output_file: Path, root_dir: Path) -> None:
    with output_file.open("w", encoding="utf-8") as f:
        f.write(f"# ROOT\t{root_dir}\n")
        f.write("# FQCN\tFILEPATH\tLINENO\n")
        for cls in sorted(classes, key=lambda c: c.fqcn):
            f.write(f"{cls.fqcn}\t{cls.filepath}\t{cls.lineno}\n")

def read_inventory(inventory_file: Path) -> tuple[Path | None, list[tuple[str, Path, int]]]:
    inventory_dir = inventory_file.parent.resolve()
    stored_root: Path | None = None
    rows: list[tuple[str, Path, int]] = []
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
            if len(parts) != 3:
                print(f"[WARN] Ignoring malformed line: {line}")
                continue
            fqcn, path_text, lineno_text = parts
            try:
                lineno = int(lineno_text)
            except ValueError:
                print(f"[WARN] Invalid line number in line: {line}")
                continue
            filepath = normalize_path(path_text, inventory_dir)
            rows.append((fqcn, filepath, lineno))
    return stored_root, rows

# ---------------------------------------------------------------------------
# Rebuild class map from inventory
# ---------------------------------------------------------------------------

def resolve_existing_path(candidate: Path) -> Path | None:
    return candidate if candidate.exists() else None

def guess_root_from_inventory(
    stored_root: Path | None,
    rows: list[tuple[str, Path, int]],
) -> Path | None:
    if stored_root is not None and stored_root.exists():
        return stored_root
    filepaths = [p for _, p, _ in rows]
    common = common_existing_parent(filepaths)
    return common

def rebuild_class_map_from_inventory(inventory_file: Path) -> dict[str, ClassInfo]:
    stored_root, requested = read_inventory(inventory_file)
    requested_fqcns = {fqcn for fqcn, _, _ in requested}
    if not requested:
        return {}
    root_dir = guess_root_from_inventory(stored_root, requested)
    filepaths = sorted({filepath for _, filepath, _ in requested if filepath.exists()})
    if not filepaths:
        print("[WARN] None of the inventory file paths currently exist.")
        return {}
    class_map: dict[str, ClassInfo] = {}
    # Pass 1: use inferred/stored root for correct module namespace reconstruction
    if root_dir is not None:
        for filepath in filepaths:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            try:
                module_name = compute_module_name(root_dir, filepath)
            except Exception:
                module_name = filepath.with_suffix("").name
            collector = ClassCollector(module_name=module_name, filepath=filepath)
            collector.visit(tree)
            for cls in collector.classes:
                if cls.fqcn in requested_fqcns:
                    class_map[cls.fqcn] = cls
    # Pass 2: robust fallback matching by file + qualname/name
    missing = requested_fqcns - set(class_map)
    if missing:
        by_file: dict[Path, list[ClassInfo]] = {}
        for filepath in filepaths:
            tree = parse_python_file(filepath)
            if tree is None:
                continue
            module_name = filepath.with_suffix("").name
            collector = ClassCollector(module_name=module_name, filepath=filepath)
            collector.visit(tree)
            by_file[filepath] = collector.classes
        for fqcn, filepath, _ in requested:
            if fqcn in class_map or not filepath.exists():
                continue
            wanted_tail = fqcn.split(".")
            candidates = by_file.get(filepath, [])
            # 1) exact qualname match
            exact_qualname = ".".join(wanted_tail[1:]) if len(wanted_tail) > 1 else wanted_tail[0]
            for cls in candidates:
                if cls.qualname == exact_qualname:
                    cls.fqcn = fqcn
                    cls.class_id = safe_mermaid_id(fqcn)
                    requested_module = fqcn[: -(len(cls.qualname) + 1)] if fqcn.endswith("." + cls.qualname) else cls.module
                    cls.module = requested_module
                    class_map[fqcn] = cls
                    break
            if fqcn in class_map:
                continue
            # 2) fallback by terminal class name
            short_name = wanted_tail[-1]
            for cls in candidates:
                if cls.name == short_name:
                    cls.fqcn = fqcn
                    cls.class_id = safe_mermaid_id(fqcn)
                    requested_module = fqcn[:-(len(cls.qualname) + 1)] if fqcn.endswith("." + cls.qualname) else cls.module
                    cls.module = requested_module
                    class_map[fqcn] = cls
                    break
    return class_map

# ---------------------------------------------------------------------------
# Mermaid generation
# ---------------------------------------------------------------------------
def resolve_base_reference(
    base_name: str,
    current_class: ClassInfo,
    known_classes: dict[str, ClassInfo],
) -> str | None:
    if base_name in known_classes:
        return base_name
    same_module = f"{current_class.module}.{base_name}" if current_class.module else base_name
    if same_module in known_classes:
        return same_module
    # nested class aware suffix matching
    suffix_matches = [
        fqcn for fqcn in known_classes
        if fqcn.endswith(f".{base_name}") or fqcn == base_name
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    return None

def mermaid_class_block(cls: ClassInfo) -> list[str]:
    display_name = cls.qualname
    lines = [f'class {cls.class_id} {display_name}' + ' {']
    for attr in cls.attributes:
        lines.append(f"  {attr.render()}")
    for method in cls.methods:
        lines.append(f"  {method.render()}")
    lines.append("}")
    return lines

def generate_mermaid(classes: dict[str, ClassInfo]) -> str:
    lines: list[str] = []
    lines.append("# UML Class Diagram")
    lines.append("")
    lines.append("```mermaid")
    lines.append("classDiagram")
    by_module: dict[str, list[ClassInfo]] = {}
    for cls in classes.values():
        by_module.setdefault(cls.module or "root", []).append(cls)
    for module in sorted(by_module):
        module_classes = sorted(by_module[module], key=lambda c: c.qualname)
        ns_id = safe_mermaid_id(module)
        lines.append(f'namespace {ns_id} {module}' + ' {')
        for cls in module_classes:
            for row in mermaid_class_block(cls):
                lines.append(f"  {row}")
        lines.append("}")
    lines.append("")
    # inheritance
    for cls in sorted(classes.values(), key=lambda c: c.fqcn):
        for base in cls.bases:
            resolved = resolve_base_reference(base, cls, classes)
            if resolved:
                lines.append(f"{classes[resolved].class_id} <|-- {cls.class_id}")
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
def write_mermaid_markdown(classes: dict[str, ClassInfo], output_file: Path) -> None:
    output_file.write_text(generate_mermaid(classes), encoding="utf-8")

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_discover(args: argparse.Namespace) -> int:
    root_dir = normalize_path(args.root)
    output_file = normalize_path(args.output)
    if not root_dir.exists() or not root_dir.is_dir():
        print(f"[ERROR] Not a valid directory: {root_dir}")
        return 1
    classes = discover_classes(root_dir)
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
    classes = rebuild_class_map_from_inventory(inventory_file)
    if not classes:
        print("[ERROR] No classes could be rebuilt from the inventory")
        return 1
    write_mermaid_markdown(classes, output_file)
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
    return parser

def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)

if __name__ == "__main__":
    raise SystemExit(main())

