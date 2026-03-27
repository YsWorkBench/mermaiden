"""Generate default Python code structure from Mermaid UML diagrams."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import unescape
from pathlib import Path
import re
from typing import Iterable

from ast_logic import split_type_names

_MARKDOWN_MERMAID_BLOCK_RE = re.compile(
    r"```mermaid\s*(?P<source>.*?)```",
    re.IGNORECASE | re.DOTALL,
)
_HTML_MERMAID_BLOCK_RE = re.compile(
    r"<pre[^>]*class=[\"'][^\"']*mermaid[^\"']*[\"'][^>]*>(?P<source>.*?)</pre>",
    re.IGNORECASE | re.DOTALL,
)
_NAMESPACE_START_RE = re.compile(r"^namespace\s+(.+?)\{$")
_CLASS_START_RE = re.compile(r"^class\s+(.+?)\{$")
_RELATION_RE = re.compile(
    r"^(?P<src>`(?:\\`|[^`])+`|\S+)\s+"
    r"(?P<arrow><\|--|\*--|o--|-->|\.\.\|>)\s+"
    r"(?P<tgt>`(?:\\`|[^`])+`|\S+)$"
)
_METHOD_SIGNATURE_RE = re.compile(
    r"^(?P<name>[A-Za-z_][A-Za-z0-9_]*)\((?P<params>.*)\)\s*(?P<ret>.*)$"
)


@dataclass
class ParsedUmlClass:
    """Class extracted from Mermaid source."""

    class_id: str
    fqcn: str
    module: str
    qualname: str
    name: str
    attributes: dict[str, str] = field(default_factory=dict)
    methods: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ParsedRelation:
    """Relation extracted from Mermaid source."""

    source_id: str
    arrow: str
    target_id: str


@dataclass
class GeneratedClass:
    """Intermediate class model used to emit Python source."""

    fqcn: str
    module: str
    name: str
    attributes: dict[str, str] = field(default_factory=dict)
    methods: list[str] = field(default_factory=list)
    bases: set[str] = field(default_factory=set)


def _decode_mermaid_id(identifier: str) -> str:
    """Decode a Mermaid identifier, removing backticks when present."""
    cleaned = identifier.strip()
    if cleaned.startswith("`") and cleaned.endswith("`") and len(cleaned) >= 2:
        return cleaned[1:-1].replace(r"\`", "`")
    return cleaned


def _parse_mermaid_ref(ref: str) -> tuple[str, str | None]:
    """Parse ``id["label"]`` Mermaid references."""
    text = ref.strip()
    label: str | None = None

    if text.endswith('"]'):
        marker = text.rfind('["')
        if marker != -1:
            label = text[marker + 2 : -2].replace(r"\"", '"')
            text = text[:marker].strip()

    return _decode_mermaid_id(text), label


def extract_mermaid_source(diagram_file: Path) -> str:
    """Extract Mermaid source from markdown or html diagram files."""
    text = diagram_file.read_text(encoding="utf-8")
    suffix = diagram_file.suffix.lower()

    if suffix == ".md":
        for match in _MARKDOWN_MERMAID_BLOCK_RE.finditer(text):
            source = match.group("source").strip()
            if "classDiagram" in source:
                return source
        raise ValueError("No Mermaid classDiagram block found in markdown file.")

    if suffix in {".html", ".htm"}:
        html_match = _HTML_MERMAID_BLOCK_RE.search(text)
        if not html_match:
            raise ValueError('No Mermaid <pre class="mermaid"> block found in html.')
        source = unescape(html_match.group("source")).strip()
        if "classDiagram" not in source:
            raise ValueError("No classDiagram found inside html Mermaid block.")
        return source

    raise ValueError("Unsupported diagram extension. Use .md, .html, or .htm")


def _build_fqcn(class_id: str, label: str | None, module: str) -> str:
    """Build a best-effort FQCN from class declaration fields."""
    if label:
        if module:
            return label if label.startswith(f"{module}.") else f"{module}.{label}"
        return label

    if "." in class_id:
        return class_id

    return f"{module}.{class_id}" if module else class_id


def _sanitize_identifier(name: str) -> str:
    """Return a Python-safe identifier from arbitrary text."""
    out = []
    for ch in name:
        if ch.isalnum() or ch == "_":
            out.append(ch)
        else:
            out.append("_")
    result = "".join(out).strip("_")
    if not result:
        result = "value"
    if result[0].isdigit():
        result = f"_{result}"
    return result


def parse_mermaid_class_diagram(
    mermaid_source: str,
) -> tuple[dict[str, ParsedUmlClass], list[ParsedRelation]]:
    """Parse Mermaid class diagram source into classes and relations."""
    classes: dict[str, ParsedUmlClass] = {}
    relations: list[ParsedRelation] = []
    namespace_stack: list[str] = []
    block_stack: list[str] = []
    current_class_id: str | None = None

    for raw_line in mermaid_source.splitlines():
        line = raw_line.strip()
        if not line or line == "classDiagram" or line.startswith("%%"):
            continue

        if line == "}":
            if not block_stack:
                continue
            closed = block_stack.pop()
            if closed == "namespace" and namespace_stack:
                namespace_stack.pop()
            if closed == "class":
                current_class_id = None
            continue

        if current_class_id is not None and block_stack and block_stack[-1] == "class":
            current = classes[current_class_id]
            if line.startswith(("+", "-")):
                member = line[1:].strip()
                if "(" in member and ")" in member:
                    current.methods.append(member)
                elif member:
                    if ":" in member:
                        raw_name, raw_type = member.split(":", 1)
                        attr_name = _sanitize_identifier(raw_name.strip())
                        attr_type = raw_type.strip()
                    else:
                        attr_name = _sanitize_identifier(member)
                        attr_type = "object"
                    current.attributes[attr_name] = attr_type
            continue

        ns_match = _NAMESPACE_START_RE.match(line)
        if ns_match:
            ns_id, ns_label = _parse_mermaid_ref(ns_match.group(1))
            namespace_stack.append(ns_label or ns_id)
            block_stack.append("namespace")
            continue

        class_match = _CLASS_START_RE.match(line)
        if class_match:
            class_id, class_label = _parse_mermaid_ref(class_match.group(1))
            module = namespace_stack[-1] if namespace_stack else ""
            fqcn = _build_fqcn(class_id, class_label, module)
            qualname = class_label or fqcn.split(".")[-1]
            parsed = ParsedUmlClass(
                class_id=class_id,
                fqcn=fqcn,
                module=module or ".".join(fqcn.split(".")[:-1]),
                qualname=qualname,
                name=qualname.split(".")[-1],
            )
            classes[class_id] = parsed
            current_class_id = class_id
            block_stack.append("class")
            continue

        rel_match = _RELATION_RE.match(line)
        if rel_match:
            relations.append(
                ParsedRelation(
                    source_id=_decode_mermaid_id(rel_match.group("src")),
                    arrow=rel_match.group("arrow"),
                    target_id=_decode_mermaid_id(rel_match.group("tgt")),
                )
            )

    if not classes:
        raise ValueError("No classes could be parsed from Mermaid classDiagram.")

    return classes, relations


def _add_relation_attribute(
    owner: GeneratedClass,
    target: GeneratedClass,
    relation_arrow: str,
) -> None:
    """Add best-effort typed attributes inferred from non-inheritance relations."""
    base_name = _sanitize_identifier(target.name)

    if relation_arrow == "o--":
        attr_name = f"{base_name}_items"
        type_name = f"list[{target.name}]"
    elif relation_arrow == "*--":
        attr_name = base_name
        type_name = target.name
    else:
        attr_name = base_name
        type_name = target.name

    if attr_name not in owner.attributes:
        owner.attributes[attr_name] = type_name


def _iter_package_dirs(module: str) -> Iterable[Path]:
    """Yield package directories for a dotted module path."""
    parts = module.split(".")
    if len(parts) <= 1:
        return []

    package_dirs: list[Path] = []
    current = Path(parts[0])
    package_dirs.append(current)
    for part in parts[1:-1]:
        current = current / part
        package_dirs.append(current)
    return package_dirs


def _collect_typing_imports(types: Iterable[str]) -> set[str]:
    """Collect required symbols from ``typing`` based on type strings."""
    needed: set[str] = set()
    typing_symbols = {
        "Optional",
        "List",
        "Dict",
        "Set",
        "Tuple",
        "Any",
        "Iterable",
        "Sequence",
        "Mapping",
        "MutableMapping",
        "Literal",
        "ClassVar",
        "Final",
        "Type",
        "Self",
    }
    for type_name in types:
        for symbol in typing_symbols:
            if re.search(rf"\b{re.escape(symbol)}\b", type_name):
                needed.add(symbol)
    return needed


def _pydantic_field_default(type_name: str) -> str:
    """Return a best-effort ``Field(...)`` default expression for a type."""
    normalized = type_name.replace(" ", "")

    if normalized.startswith(("Optional[", "None|")) or "|None" in normalized:
        return "Field(default=None)"
    if normalized.startswith(("list[", "List[")):
        return "Field(default_factory=list)"
    if normalized.startswith(("dict[", "Dict[")):
        return "Field(default_factory=dict)"
    if normalized.startswith(("set[", "Set[")):
        return "Field(default_factory=set)"
    if normalized.startswith(("tuple[", "Tuple[")):
        return "Field(default_factory=tuple)"

    return "Field(...)"


def _render_method_stub(signature: str) -> list[str]:
    """Render a best-effort Python method from Mermaid signature text."""
    match = _METHOD_SIGNATURE_RE.match(signature.strip())
    if not match:
        name = _sanitize_identifier(signature.split("(")[0].strip() or "method")
        return [
            f"    def {name}(self) -> None:",
            "        raise NotImplementedError",
        ]

    name = _sanitize_identifier(match.group("name"))
    params_text = match.group("params").strip()
    return_text = match.group("ret").strip()
    params_suffix = f", {params_text}" if params_text else ""
    return_suffix = f" -> {return_text}" if return_text else ""
    return [
        f"    def {name}(self{params_suffix}){return_suffix}:",
        "        raise NotImplementedError",
    ]


def _build_module_source(
    module: str,
    classes: list[GeneratedClass],
    all_classes: dict[str, GeneratedClass],
    pydantic_models: bool = False,
) -> str:
    """Build Python source for one module."""
    lines: list[str] = ["from __future__ import annotations", ""]

    name_index: dict[str, set[str]] = {}
    for fqcn, cls in all_classes.items():
        name_index.setdefault(cls.name, set()).add(fqcn)

    typing_types: list[str] = []
    for cls in classes:
        typing_types.extend(cls.attributes.values())
        for method in cls.methods:
            method_match = _METHOD_SIGNATURE_RE.match(method)
            if method_match:
                typing_types.extend(
                    p.strip() for p in method_match.group("params").split(",")
                )
                typing_types.append(method_match.group("ret").strip())
    typing_imports = _collect_typing_imports(typing_types)

    cross_imports: dict[str, set[str]] = {}
    for cls in classes:
        for base_fqcn in cls.bases:
            base_cls = all_classes.get(base_fqcn)
            if base_cls is None or base_cls.module == module:
                continue
            cross_imports.setdefault(base_cls.module, set()).add(base_cls.name)

        for attr_type in cls.attributes.values():
            for type_name in split_type_names(attr_type):
                matches = name_index.get(type_name, set())
                if len(matches) != 1:
                    continue
                target_fqcn = next(iter(matches))
                target_cls = all_classes[target_fqcn]
                if target_cls.module == module:
                    continue
                cross_imports.setdefault(target_cls.module, set()).add(target_cls.name)

    if typing_imports:
        lines.append(f"from typing import {', '.join(sorted(typing_imports))}")

    pydantic_imports: list[str] = []
    if pydantic_models and any(not cls.bases for cls in classes):
        pydantic_imports.append("BaseModel")
    if pydantic_models and any(cls.attributes for cls in classes):
        pydantic_imports.append("Field")
    if pydantic_imports:
        lines.append(f"from pydantic import {', '.join(pydantic_imports)}")

    for import_module in sorted(cross_imports):
        names = ", ".join(sorted(cross_imports[import_module]))
        lines.append(f"from {import_module} import {names}")

    if len(lines) > 2 or (len(lines) == 2 and lines[1]):
        lines.append("")

    for cls in sorted(classes, key=lambda c: c.name):
        if pydantic_models and not cls.bases:
            base_names = ["BaseModel"]
        else:
            base_names = []
            for base_fqcn in sorted(cls.bases):
                base_cls = all_classes.get(base_fqcn)
                base_names.append(
                    base_cls.name if base_cls else base_fqcn.split(".")[-1]
                )

        bases = f"({', '.join(base_names)})" if base_names else ""
        lines.append(f"class {cls.name}{bases}:")

        wrote_body = False
        for attr_name, attr_type in sorted(cls.attributes.items()):
            if pydantic_models:
                field_default = _pydantic_field_default(attr_type)
                lines.append(f"    {attr_name}: {attr_type} = {field_default}")
            else:
                lines.append(f"    {attr_name}: {attr_type}")
            wrote_body = True

        for method_sig in cls.methods:
            if wrote_body:
                lines.append("")
            lines.extend(_render_method_stub(method_sig))
            wrote_body = True

        if not wrote_body:
            lines.append("    pass")

        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def generate_codebase_from_diagram(
    diagram_file: Path,
    output_dir: Path,
    pydantic_models: bool = False,
) -> tuple[int, int]:
    """Generate a default Python codebase structure from a Mermaid diagram file."""
    mermaid_source = extract_mermaid_source(diagram_file)
    parsed_classes, parsed_relations = parse_mermaid_class_diagram(mermaid_source)

    generated: dict[str, GeneratedClass] = {}
    id_to_fqcn: dict[str, str] = {}

    for class_id, parsed in parsed_classes.items():
        fqcn = parsed.fqcn
        module = parsed.module or ".".join(fqcn.split(".")[:-1])
        if not module:
            module = "generated"
            fqcn = f"{module}.{parsed.name}"

        generated[fqcn] = GeneratedClass(
            fqcn=fqcn,
            module=module,
            name=parsed.name,
            attributes=dict(parsed.attributes),
            methods=list(parsed.methods),
        )
        id_to_fqcn[class_id] = fqcn

    for rel in parsed_relations:
        src_fqcn = id_to_fqcn.get(rel.source_id)
        tgt_fqcn = id_to_fqcn.get(rel.target_id)
        if src_fqcn is None or tgt_fqcn is None:
            continue

        src_cls = generated[src_fqcn]
        tgt_cls = generated[tgt_fqcn]

        if rel.arrow == "<|--":
            tgt_cls.bases.add(src_fqcn)
        elif rel.arrow == "..|>":
            src_cls.bases.add(tgt_fqcn)
        elif rel.arrow == "-->":
            _add_relation_attribute(tgt_cls, src_cls, rel.arrow)
        elif rel.arrow in {"o--", "*--"}:
            _add_relation_attribute(src_cls, tgt_cls, rel.arrow)

    modules: dict[str, list[GeneratedClass]] = {}
    for cls in generated.values():
        modules.setdefault(cls.module, []).append(cls)

    output_dir.mkdir(parents=True, exist_ok=True)
    for module in sorted(modules):
        module_parts = module.split(".")
        module_path = output_dir.joinpath(*module_parts[:-1], f"{module_parts[-1]}.py")
        module_path.parent.mkdir(parents=True, exist_ok=True)

        for package_rel in _iter_package_dirs(module):
            package_dir = output_dir / package_rel
            package_dir.mkdir(parents=True, exist_ok=True)
            init_file = package_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("", encoding="utf-8")

        module_source = _build_module_source(
            module,
            modules[module],
            generated,
            pydantic_models=pydantic_models,
        )
        module_path.write_text(module_source, encoding="utf-8")

    return len(generated), len(modules)
