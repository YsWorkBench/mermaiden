"""Mermaid source and document rendering utilities."""

from __future__ import annotations

from html import escape
from pathlib import Path

from discovery import collect_all_relations
from models import ClassInfo, NamespaceNode, build_namespace_tree, mermaid_id


def _format_mermaid_alias(identifier: str, label: str, aliases: bool) -> str:
    """Return Mermaid identifier with optional display label alias."""
    if not aliases:
        return identifier
    escaped_label = label.replace('"', r"\"")
    return f'{identifier}["{escaped_label}"]'


def mermaid_class_block(cls: ClassInfo, aliases: bool = True) -> list[str]:
    """Render one class block in Mermaid class diagram syntax."""
    class_ref = _format_mermaid_alias(cls.class_id, cls.qualname, aliases)
    lines = [f"class {class_ref}" + " {"]
    for attr in cls.attributes:
        lines.append(f"  {attr.render()}")
    for method in cls.methods:
        lines.append(f"  {method.render()}")
    lines.append("}")
    return lines


def render_nested_namespace_lines(
    node: NamespaceNode,
    indent: int = 0,
    style: str = "flat",
    aliases: bool = True,
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
            for row in mermaid_class_block(cls, aliases=aliases):
                lines.append(f"{pad}  {row}")

        lines.extend(
            render_nested_namespace_lines(
                child,
                indent + 1,
                style=style,
                aliases=aliases,
            )
        )
        lines.append(f"{pad}" + "}")

    return lines


def render_compat_namespace_lines(
    node: NamespaceNode, style: str = "flat", aliases: bool = True
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
                for row in mermaid_class_block(cls, aliases=aliases):
                    lines.append(f"  {row}")

            lines.append("}")

        for child_name in sorted(current.children):
            visit(current.children[child_name])

    visit(node)
    return lines


def generate_mermaid_source(
    classes: dict[str, ClassInfo],
    namespace: str = "nested",
    style: str = "flat",
    aliases: bool = True,
) -> str:
    """Generate Mermaid source text from discovered class metadata."""
    lines: list[str] = ["classDiagram"]

    tree = build_namespace_tree(classes)

    for cls in sorted(tree.classes, key=lambda c: c.qualname):
        for row in mermaid_class_block(cls, aliases=aliases):
            lines.append(row)

    if namespace == "nested":
        lines.extend(render_nested_namespace_lines(tree, style=style, aliases=aliases))
    elif namespace == "legacy":
        lines.extend(render_compat_namespace_lines(tree, style=style, aliases=aliases))
    else:
        raise ValueError(f"Unsupported namespace: {namespace}")

    lines.append("")

    for src_fqcn, rel_type, tgt_fqcn in collect_all_relations(classes):
        src_id = classes[src_fqcn].class_id
        tgt_id = classes[tgt_fqcn].class_id
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
    )

    if suffix == ".md":
        content = render_markdown_document(
            mermaid_source,
            title=markdown_title,
        )
    elif suffix == ".html":
        content = render_html_document(
            mermaid_source,
            title=html_title,
        )
    else:
        raise ValueError(
            f"Unsupported output extension '{output_file.suffix}'. "
            "Supported extensions are .md and .html"
        )

    output_file.write_text(content, encoding="utf-8")


def write_mermaid_output(
    classes: dict[str, ClassInfo],
    output_file: Path,
    namespace: str = "nested",
    style: str = "flat",
    aliases: bool = True,
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
        html_title=html_title,
        markdown_title=markdown_title,
    )
