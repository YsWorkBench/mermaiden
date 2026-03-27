"""Compatibility facade for the refactored mermaiden modules."""

from __future__ import annotations

import argparse
import heapq
import re
from typing import Callable, cast

from discovery import (
    collect_all_relations,
    discover_classes,
    rebuild_class_map_from_inventory,
)
from generate import generate_codebase_from_diagram
from inventory import write_inventory
from models import ClassInfo
from paths import normalize_path
from render import write_mermaid_output


def _resolve_isolate_target(
    classes: dict[str, ClassInfo], query: str
) -> tuple[str | None, str | None]:
    """Resolve ``--isolate-class`` query to a single class FQCN."""
    if not query:
        return None, "Empty --isolate-class value is not allowed"

    ranked_matches: list[tuple[int, str]] = []
    for fqcn, cls in classes.items():
        if fqcn == query:
            ranked_matches.append((0, fqcn))
        elif cls.qualname == query:
            ranked_matches.append((1, fqcn))
        elif cls.name == query:
            ranked_matches.append((2, fqcn))
        elif fqcn.endswith(f".{query}"):
            ranked_matches.append((3, fqcn))
        elif cls.class_id == query:
            ranked_matches.append((4, fqcn))

    if not ranked_matches:
        return None, f"--isolate-class did not match any class: {query!r}"

    best_rank = min(rank for rank, _ in ranked_matches)
    candidates = sorted({fqcn for rank, fqcn in ranked_matches if rank == best_rank})
    if len(candidates) > 1:
        preview = ", ".join(candidates[:5])
        suffix = "..." if len(candidates) > 5 else ""
        return (
            None,
            f"--isolate-class is ambiguous for {query!r}: {preview}{suffix}",
        )

    return candidates[0], None


def _build_relation_graph(classes: dict[str, ClassInfo]) -> dict[str, dict[str, int]]:
    """Build an undirected weighted graph from class relations."""
    graph: dict[str, dict[str, int]] = {fqcn: {} for fqcn in classes}
    for source_fqcn, _, target_fqcn in collect_all_relations(classes):
        if source_fqcn not in classes or target_fqcn not in classes:
            continue
        graph[source_fqcn][target_fqcn] = 1
        graph[target_fqcn][source_fqcn] = 1
    return graph


def _dijkstra_shortest_paths(
    graph: dict[str, dict[str, int]], start: str
) -> dict[str, float]:
    """Compute shortest-path distances using Dijkstra's algorithm."""
    distances: dict[str, float] = {node: float("inf") for node in graph}
    distances[start] = 0

    queue: list[tuple[int, str]] = [(0, start)]
    while queue:
        current_distance, current = heapq.heappop(queue)
        if current_distance > distances[current]:
            continue

        for neighbor, weight in graph[current].items():
            candidate = current_distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                heapq.heappush(queue, (candidate, neighbor))

    return distances


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
    title = getattr(args, "title", "UML Class Diagram")
    recursive_attributes = getattr(args, "recursive_attributes", False)
    skip_enums = getattr(args, "skip_enums", False)
    isolate_class = getattr(args, "isolate_class", None)
    isolate_distance = getattr(args, "isolate_distance", 1)

    if not inventory_file.exists():
        print(f"[ERROR] Inventory file not found: {inventory_file}")
        return 1

    classes = rebuild_class_map_from_inventory(inventory_file, style=args.style)
    if not classes:
        print("[ERROR] No classes could be rebuilt from inventory")
        return 1

    if isolate_class is None and isolate_distance != 1:
        print("[ERROR] --isolate-distance requires --isolate-class")
        return 1
    if isolate_distance < 0:
        print("[ERROR] --isolate-distance must be >= 0")
        return 1

    if isolate_class:
        target_fqcn, isolate_error = _resolve_isolate_target(classes, isolate_class)
        if isolate_error is not None or target_fqcn is None:
            print(f"[ERROR] {isolate_error}")
            return 1

        graph = _build_relation_graph(classes)
        shortest_paths = _dijkstra_shortest_paths(graph, target_fqcn)
        kept = {
            fqcn
            for fqcn, distance in shortest_paths.items()
            if distance <= isolate_distance
        }
        kept.add(target_fqcn)
        classes = {fqcn: cls for fqcn, cls in classes.items() if fqcn in kept}
        print(f"[OK] Isolated {target_fqcn} with graph distance <= {isolate_distance}")

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
        recursive_attributes=recursive_attributes,
        skip_enums=skip_enums,
        html_title=title,
        markdown_title=title,
    )
    print(f"[OK] Mermaid diagram written to: {output_file}")
    print(f"[OK] Included {len(classes)} classes")
    return 0


def cmd_generate(args: argparse.Namespace) -> int:
    """Run the ``generate`` CLI command."""
    diagram_file = normalize_path(args.diagram)
    output_dir = normalize_path(args.output)
    pydantic_models = getattr(args, "pydantic", False)

    if not diagram_file.exists() or not diagram_file.is_file():
        print(f"[ERROR] Diagram file not found: {diagram_file}")
        return 1

    try:
        class_count, module_count = generate_codebase_from_diagram(
            diagram_file=diagram_file,
            output_dir=output_dir,
            pydantic_models=pydantic_models,
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
    p2.add_argument(
        "--output",
        "--ouput",
        dest="output",
        default="UMLdiagram.md",
        help="Diagram output file (.md, .html, or .htm)",
    )
    p2.set_defaults(func=cmd_diagram)
    p2.add_argument(
        "--namespace",
        type=str.lower,
        choices=["nested", "legacy", "none"],
        default="legacy",
        help=(
            "Namespace rendering mode: nested namespaces, "
            "legacy compatibility fallback, or none (no namespace blocks)"
        ),
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
        "--recursive-attributes",
        action="store_true",
        help=(
            "Render inherited attributes/methods on each class using "
            "depth-first post-order traversal so child overrides are kept"
        ),
    )
    p2.add_argument(
        "--skip-enums",
        action="store_true",
        help="Hide enum value members while still rendering enum classes",
    )
    p2.add_argument(
        "--isolate-class",
        default=None,
        metavar="CLASS",
        help=(
            "Keep only one matched class and its graph neighbors "
            "(by shortest-path distance)"
        ),
    )
    p2.add_argument(
        "--isolate-distance",
        type=int,
        default=1,
        metavar="N",
        help="Graph distance used with --isolate-class (default: 1)",
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
        "--title",
        default="UML Class Diagram",
        help="Document title for markdown and HTML outputs",
    )

    p3 = subparsers.add_parser(
        "generate",
        help="Generate default Python codebase from Mermaid UML markdown/html",
    )
    p3.add_argument("diagram", help="Input diagram file (.md, .html, or .htm)")
    p3.add_argument(
        "--output",
        default="generated_src",
        help="Output directory for generated Python scaffold",
    )
    p3.add_argument(
        "--pydantic",
        action="store_true",
        help="Generate pydantic BaseModel classes instead of plain classes",
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
