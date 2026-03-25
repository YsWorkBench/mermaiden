"""Compatibility facade for the refactored mermaiden modules."""

from __future__ import annotations

import argparse
import re
from typing import Callable, cast

from discovery import discover_classes, rebuild_class_map_from_inventory
from generate import generate_codebase_from_diagram
from inventory import write_inventory
from models import ClassInfo
from paths import normalize_path
from render import write_mermaid_output


def cmd_discover(args: argparse.Namespace) -> int:
    """Run the ``discover`` CLI command."""
    root_dir = normalize_path(args.root)
    output_file = normalize_path(args.output)
    follow_mode = getattr(args, "follow", "path")
    namespace_from_root = getattr(args, "namespace_from_root", False)

    if not root_dir.exists() or not root_dir.is_dir():
        print(f"[ERROR] Not a valid directory: {root_dir}")
        return 1

    classes = discover_classes(
        root_dir,
        style=args.style,
        follow=follow_mode,
        namespace_from_root=namespace_from_root,
    )
    write_inventory(classes, output_file, root_dir)

    print(f"[OK] Discovered {len(classes)} classes")
    print(f"[OK] Inventory written to: {output_file}")
    return 0


def cmd_diagram(args: argparse.Namespace) -> int:
    """Run the ``diagram`` CLI command."""
    inventory_file = normalize_path(args.inventory)
    output_file = normalize_path(args.output)
    aliases = getattr(args, "aliases", False)
    filters = getattr(args, "filters", None)

    if not inventory_file.exists():
        print(f"[ERROR] Inventory file not found: {inventory_file}")
        return 1

    classes = rebuild_class_map_from_inventory(inventory_file, style=args.style)
    if not classes:
        print("[ERROR] No classes could be rebuilt from inventory")
        return 1

    if filters:
        compiled_filters: list[re.Pattern[str]] = []
        for pattern in filters:
            try:
                compiled_filters.append(re.compile(pattern))
            except re.error as exc:
                print(f"[ERROR] Invalid regex in --filters: {pattern!r} ({exc})")
                return 1

        def _matches_filters(cls: ClassInfo) -> bool:
            searchable = (cls.name, cls.qualname, cls.module, cls.fqcn)
            return any(
                compiled.search(candidate)
                for compiled in compiled_filters
                for candidate in searchable
            )

        classes = {fqcn: cls for fqcn, cls in classes.items() if _matches_filters(cls)}
        if not classes:
            print("[WARN] No classes matched --filters; writing empty diagram.")

    write_mermaid_output(
        classes,
        output_file,
        namespace=args.namespace,
        style=args.style,
        aliases=aliases,
        html_title=args.html_title,
        markdown_title=args.markdown_title,
    )
    print(f"[OK] Mermaid diagram written to: {output_file}")
    print(f"[OK] Included {len(classes)} classes")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Run the ``generate`` CLI command."""
    diagram_file = normalize_path(args.diagram)
    output_dir = normalize_path(args.output)

    if not diagram_file.exists() or not diagram_file.is_file():
        print(f"[ERROR] Diagram file not found: {diagram_file}")
        return 1

    try:
        class_count, module_count = generate_codebase_from_diagram(
            diagram_file=diagram_file,
            output_dir=output_dir,
        )
    except ValueError as exc:
        print(f"[ERROR] {exc}")
        return 1

    print(f"[OK] Generated {class_count} classes across {module_count} modules")
    print(f"[OK] Codebase scaffold written to: {output_dir}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Discover Python classes and generate Mermaid UML diagrams"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    p1 = subparsers.add_parser(
        "discover", help="Scan a root folder and write class inventory"
    )
    p1.add_argument("root", help="Root folder to scan")
    p1.add_argument("--output", default="classes.txt", help="Inventory output file")
    p1.add_argument(
        "--style",
        choices=["flat", "escaped"],
        default="flat",
        help="How Mermaid identifiers are emitted",
    )
    p1.add_argument(
        "--follow",
        choices=["path", "init.py"],
        default="path",
        help="How module namespaces are resolved: filesystem paths or __init__.py exports",
    )
    p1.add_argument(
        "--namespace-from-root",
        action="store_true",
        help="Build class namespaces relative to the discovery root directory",
    )
    p1.set_defaults(func=cmd_discover)

    p2 = subparsers.add_parser("diagram", help="Generate Mermaid UML from inventory")
    p2.add_argument("inventory", help="Inventory file")
    p2.add_argument("--output", default="UMLdiagram.md", help="Markdown output file")
    p2.set_defaults(func=cmd_diagram)
    p2.add_argument(
        "--namespace",
        choices=["nested", "legacy"],
        default="legacy",
        help="Namespace rendering mode: nested namespaces or legacy for compatibility fallback",
    )
    p2.add_argument(
        "--style",
        choices=["flat", "escaped"],
        default="flat",
        help="How Mermaid identifiers are emitted",
    )
    p2.add_argument(
        "--aliases",
        action="store_true",
        help="Whether Mermaid aliases are emitted for classes and namespaces",
    )
    p2.add_argument(
        "--filters",
        nargs="*",
        default=None,
        metavar="REGEX",
        help=(
            "Optional regex list to include classes/modules in diagram. "
            "A class is kept when any regex matches its class name, qualname, module, or FQCN."
        ),
    )
    p2.add_argument(
        "--markdown-title",
        default="Mardown UML Class Diagram",
        help="Document title for markdown output",
    )

    p2.add_argument(
        "--html-title",
        default="HTML UML Class Diagram",
        help="Document title for HTML output",
    )

    p3 = subparsers.add_parser(
        "generate",
        help="Generate default Python codebase from Mermaid UML markdown/html",
    )
    p3.add_argument("diagram", help="Input diagram file (.md or .html)")
    p3.add_argument(
        "--output",
        default="generated_src",
        help="Output directory for generated Python scaffold",
    )
    p3.set_defaults(func=cmd_generate)
    return parser


def main() -> int:
    """Entry point for the ``mermaiden`` CLI."""
    parser = build_parser()
    args = parser.parse_args()
    func = cast(Callable[[argparse.Namespace], int], args.func)
    return func(args)


if __name__ == "__main__":
    raise SystemExit(main())
