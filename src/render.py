"""Mermaid source and document rendering utilities."""

from __future__ import annotations

from html import escape
from pathlib import Path

from discovery import collect_all_relations, resolve_target_name
from models import (
    AttributeInfo,
    build_namespace_tree,
    ClassInfo,
    mermaid_id,
    MethodInfo,
    NamespaceNode,
)


def _format_mermaid_alias(identifier: str, label: str, aliases: bool) -> str:
    """Return Mermaid identifier with optional display label alias."""
    if not aliases:
        return identifier
    escaped_label = label.replace('"', r"\"")
    return f'{identifier}["{escaped_label}"]'


def mermaid_class_block(
    cls: ClassInfo,
    aliases: bool = True,
    class_identifier: str | None = None,
    class_label: str | None = None,
    attributes: list[AttributeInfo] | None = None,
    methods: list[MethodInfo] | None = None,
) -> list[str]:
    """Render one class block in Mermaid class diagram syntax."""
    identifier = class_identifier if class_identifier is not None else cls.class_id
    label = class_label if class_label is not None else cls.qualname
    class_ref = _format_mermaid_alias(identifier, label, aliases)
    attrs = attributes if attributes is not None else cls.attributes
    meths = methods if methods is not None else cls.methods
    lines = [f"class {class_ref}" + " {"]
    for attr in attrs:
        lines.append(f"  {attr.render()}")
    for method in meths:
        lines.append(f"  {method.render()}")
    lines.append("}")
    return lines


def render_nested_namespace_lines(
    node: NamespaceNode,
    indent: int = 0,
    style: str = "flat",
    aliases: bool = True,
    class_id_map: dict[str, str] | None = None,
    recursive_member_map: (
        dict[str, tuple[list[AttributeInfo], list[MethodInfo]]] | None
    ) = None,
) -> list[str]:
    """Render namespaces recursively using Mermaid nested namespace blocks."""
    lines: list[str] = []
    pad = "  " * indent

    for child_name in sorted(node.children):
        child = node.children[child_name]
        ns_id = mermaid_id(child.full_name, style=style)
        ns_ref = _format_mermaid_alias(ns_id, child.full_name, aliases)
        lines.append(f"{pad}namespace {ns_ref}" + "{")

        for cls in sorted(child.classes, key=lambda c: c.qualname):
            cls_identifier = (
                class_id_map.get(cls.fqcn, cls.class_id)
                if class_id_map is not None
                else cls.class_id
            )
            cls_attributes, cls_methods = (
                recursive_member_map.get(cls.fqcn, (None, None))
                if recursive_member_map is not None
                else (None, None)
            )
            for row in mermaid_class_block(
                cls,
                aliases=aliases,
                class_identifier=cls_identifier,
                attributes=cls_attributes,
                methods=cls_methods,
            ):
                lines.append(f"{pad}  {row}")

        lines.extend(
            render_nested_namespace_lines(
                child,
                indent + 1,
                style=style,
                aliases=aliases,
                class_id_map=class_id_map,
                recursive_member_map=recursive_member_map,
            )
        )
        lines.append(f"{pad}" + "}")

    return lines


def render_compat_namespace_lines(
    node: NamespaceNode,
    style: str = "flat",
    aliases: bool = True,
    class_id_map: dict[str, str] | None = None,
    recursive_member_map: (
        dict[str, tuple[list[AttributeInfo], list[MethodInfo]]] | None
    ) = None,
) -> list[str]:
    """Render namespaces in compatibility mode for Mermaid limitations."""
    lines: list[str] = []

    def visit(current: NamespaceNode) -> None:
        """Depth-first traversal used by compatibility namespace rendering."""
        if current.full_name:
            ns_id = mermaid_id(current.full_name, style=style)
            ns_ref = _format_mermaid_alias(ns_id, current.full_name, aliases)
            lines.append(f"namespace {ns_ref}" + "{")

            for child_name in sorted(current.children):
                child = current.children[child_name]
                child_ns_id = mermaid_id(child.full_name, style=style)
                child_ns_ref = _format_mermaid_alias(
                    child_ns_id, child.full_name, aliases
                )
                lines.append(f"  class {child_ns_ref}")

            for cls in sorted(current.classes, key=lambda c: c.qualname):
                cls_identifier = (
                    class_id_map.get(cls.fqcn, cls.class_id)
                    if class_id_map is not None
                    else cls.class_id
                )
                cls_attributes, cls_methods = (
                    recursive_member_map.get(cls.fqcn, (None, None))
                    if recursive_member_map is not None
                    else (None, None)
                )
                for row in mermaid_class_block(
                    cls,
                    aliases=aliases,
                    class_identifier=cls_identifier,
                    attributes=cls_attributes,
                    methods=cls_methods,
                ):
                    lines.append(f"  {row}")

            lines.append("}")

        for child_name in sorted(current.children):
            visit(current.children[child_name])

    visit(node)
    return lines


def _build_namespace_none_class_id_map(
    classes: dict[str, ClassInfo],
    style: str,
) -> dict[str, str]:
    """Build unique, module-free class identifiers for ``namespace=none``."""
    id_map: dict[str, str] = {}
    used_ids: set[str] = set()
    next_suffix_by_base: dict[str, int] = {}

    for cls in sorted(classes.values(), key=lambda c: (c.qualname, c.fqcn)):
        base_name = cls.qualname or cls.name or cls.fqcn.split(".")[-1]
        candidate_name = base_name
        candidate_id = mermaid_id(candidate_name, style=style)

        while candidate_id in used_ids:
            next_suffix = next_suffix_by_base.get(base_name, 2)
            candidate_name = f"{base_name}_{next_suffix}"
            candidate_id = mermaid_id(candidate_name, style=style)
            next_suffix_by_base[base_name] = next_suffix + 1

        used_ids.add(candidate_id)
        id_map[cls.fqcn] = candidate_id

    return id_map


def _build_recursive_member_map(
    classes: dict[str, ClassInfo],
) -> dict[str, tuple[list[AttributeInfo], list[MethodInfo]]]:
    """Build inherited members per class using depth-first post-order traversal."""
    memo: dict[str, tuple[list[AttributeInfo], list[MethodInfo]]] = {}
    visiting: set[str] = set()

    def collect_for_class(fqcn: str) -> tuple[list[AttributeInfo], list[MethodInfo]]:
        if fqcn in memo:
            return memo[fqcn]
        if fqcn in visiting:
            return [], []

        visiting.add(fqcn)
        cls = classes[fqcn]
        attr_map: dict[str, AttributeInfo] = {}
        method_map: dict[str, MethodInfo] = {}

        # Depth-first post-order: parent trees first, then current class members.
        # This guarantees child overrides replace inherited members.
        for base in cls.bases:
            target_fqcn = resolve_target_name(base, cls, classes)
            if not target_fqcn or target_fqcn not in classes:
                continue
            base_attrs, base_methods = collect_for_class(target_fqcn)
            for attr in base_attrs:
                attr_map[attr.name] = attr
            for method in base_methods:
                method_map[method.name] = method

        for attr in cls.attributes:
            attr_map[attr.name] = attr
        for method in cls.methods:
            method_map[method.name] = method

        visiting.remove(fqcn)
        merged = list(attr_map.values()), list(method_map.values())
        memo[fqcn] = merged
        return merged

    for fqcn in sorted(classes):
        collect_for_class(fqcn)

    return memo


def generate_mermaid_source(
    classes: dict[str, ClassInfo],
    namespace: str = "nested",
    style: str = "flat",
    aliases: bool = True,
    recursive_attributes: bool = False,
) -> str:
    """Generate Mermaid source text from discovered class metadata."""
    lines: list[str] = ["classDiagram"]
    class_id_map = (
        _build_namespace_none_class_id_map(classes, style=style)
        if namespace == "none"
        else {fqcn: cls.class_id for fqcn, cls in classes.items()}
    )
    recursive_member_map = (
        _build_recursive_member_map(classes) if recursive_attributes else {}
    )

    tree = build_namespace_tree(classes)

    if namespace != "none":
        for cls in sorted(tree.classes, key=lambda c: c.qualname):
            cls_identifier = class_id_map.get(cls.fqcn, cls.class_id)
            cls_attributes, cls_methods = recursive_member_map.get(
                cls.fqcn, (None, None)
            )
            for row in mermaid_class_block(
                cls,
                aliases=aliases,
                class_identifier=cls_identifier,
                attributes=cls_attributes,
                methods=cls_methods,
            ):
                lines.append(row)

    if namespace == "nested":
        lines.extend(
            render_nested_namespace_lines(
                tree,
                style=style,
                aliases=aliases,
                class_id_map=class_id_map,
                recursive_member_map=recursive_member_map,
            )
        )
    elif namespace == "legacy":
        lines.extend(
            render_compat_namespace_lines(
                tree,
                style=style,
                aliases=aliases,
                class_id_map=class_id_map,
                recursive_member_map=recursive_member_map,
            )
        )
    elif namespace == "none":
        for cls in sorted(classes.values(), key=lambda c: (c.qualname, c.fqcn)):
            cls_identifier = class_id_map[cls.fqcn]
            cls_attributes, cls_methods = recursive_member_map.get(
                cls.fqcn, (None, None)
            )
            for row in mermaid_class_block(
                cls,
                aliases=aliases,
                class_identifier=cls_identifier,
                attributes=cls_attributes,
                methods=cls_methods,
            ):
                lines.append(row)
    else:
        raise ValueError(f"Unsupported namespace: {namespace}")

    lines.append("")

    for src_fqcn, rel_type, tgt_fqcn in collect_all_relations(classes):
        src_id = class_id_map.get(src_fqcn, classes[src_fqcn].class_id)
        tgt_id = class_id_map.get(tgt_fqcn, classes[tgt_fqcn].class_id)
        lines.append(f"{src_id} {rel_type.value} {tgt_id}")

    return "\n".join(lines).strip() + "\n"


def render_markdown_document(
    mermaid_source: str, title: str = "UML Class Diagram"
) -> str:
    """Wrap Mermaid source in a Markdown document."""
    return f"# {title}\n\n" "```mermaid\n" f"{mermaid_source}" "```\n"


def render_html_document(
    mermaid_source: str,
    title: str = "Process Flow Diagram",
) -> str:
    """Wrap Mermaid source in a minimal standalone HTML document."""
    escaped_mermaid = escape(mermaid_source)
    return f"""<!DOCTYPE html>
<html lang=\"en\">
<head>
<meta charset=\"utf-8\" />
<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
<title>{escape(title)}</title>
</head>
<body>
<script type=\"module\" src=\"https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs\"></script>
<h1>{escape(title)}</h1>
<pre class=\"mermaid\">
{escaped_mermaid}</pre>
</body>
</html>
"""


def write_diagram_output(
    classes: dict[str, ClassInfo],
    output_file: Path,
    namespace: str = "nested",
    style: str = "flat",
    aliases: bool = True,
    recursive_attributes: bool = False,
    html_title: str = "Process Flow Diagram",
    markdown_title: str = "UML Class Diagram",
) -> None:
    """Write diagram output as Markdown or HTML based on extension."""
    suffix = output_file.suffix.lower()

    mermaid_source = generate_mermaid_source(
        classes,
        namespace=namespace,
        style=style,
        aliases=aliases,
        recursive_attributes=recursive_attributes,
    )

    if suffix == ".md":
        content = render_markdown_document(
            mermaid_source,
            title=markdown_title,
        )
    elif suffix in {".html", ".htm"}:
        content = render_html_document(
            mermaid_source,
            title=html_title,
        )
    else:
        raise ValueError(
            f"Unsupported output extension '{output_file.suffix}'. "
            "Supported extensions are .md, .html, and .htm"
        )

    output_file.write_text(content, encoding="utf-8")


def write_mermaid_output(
    classes: dict[str, ClassInfo],
    output_file: Path,
    namespace: str = "nested",
    style: str = "flat",
    aliases: bool = True,
    recursive_attributes: bool = False,
    html_title: str = "Process Flow Diagram",
    markdown_title: str = "UML Class Diagram",
) -> None:
    """Backward-compatible wrapper for ``write_diagram_output``."""
    write_diagram_output(
        classes=classes,
        output_file=output_file,
        namespace=namespace,
        style=style,
        aliases=aliases,
        recursive_attributes=recursive_attributes,
        html_title=html_title,
        markdown_title=markdown_title,
    )
