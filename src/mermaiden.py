"""Compatibility facade for the refactored mermaiden modules."""

from __future__ import annotations
import argparse

from ast_logic import *  # noqa: F401,F403
from discovery import *  # noqa: F401,F403
from inventory import *  # noqa: F401,F403
from models import *  # noqa: F401,F403
from paths import *  # noqa: F401,F403
from render import *  # noqa: F401,F403

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

    write_mermaid_output(
        classes,
        output_file,
        namespace=args.namespace,
        style=args.style,
        html_title=args.html_title,
        markdown_title=args.markdown_title,
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
    p1.add_argument(
        "--style",
        choices=["flat", "escaped"],
        default="flat",
        help="How Mermaid identifiers are emitted",
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
        "--markdown-title",
        default="Mardown UML Class Diagram",
        help="Document title for markdown output",
    )

    p2.add_argument(
        "--html-title",
        default="HTML UML Class Diagram",
        help="Document title for HTML output",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
