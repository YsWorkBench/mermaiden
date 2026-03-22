"""Shared enums and dataclasses used across discovery and rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

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
    """Supported Mermaid identifier rendering styles."""

    FLAT = "flat"
    ESCAPED = "escaped"


class RelationType(str, Enum):
    """Relationship arrows used in Mermaid class diagrams."""

    INHERITANCE = "<|--"
    COMPOSITION = "*--"
    AGGREGATION = "o--"
    ASSOCIATION = "-->"
    REALIZATION = "..|>"


@dataclass(frozen=True)
class AttributeInfo:
    """Represents a class or instance attribute for UML rendering."""

    name: str
    type_name: str = ""

    def render(self) -> str:
        """Render the attribute as a Mermaid class member line."""
        vis = "-" if self.name.startswith("_") else "+"
        return (
            f"{vis}{self.name}: {self.type_name}"
            if self.type_name
            else f"{vis}{self.name}"
        )


@dataclass(frozen=True)
class MethodInfo:
    """Represents a method signature for UML rendering."""

    name: str
    params: list[tuple[str, str]] = field(default_factory=list)
    return_type: str = ""

    def render(self) -> str:
        """Render the method as a Mermaid class member line."""
        vis = "-" if self.name.startswith("_") else "+"
        sig = ", ".join(f"{n}: {t}" if t else n for n, t in self.params)
        return f"{vis}{self.name}({sig}) {self.return_type}".rstrip()


@dataclass(frozen=True)
class Relation:
    """Represents a semantic relationship between two classes."""

    source_fqcn: str
    target_name: str
    relation_type: RelationType
    reason: str = ""


@dataclass
class ClassInfo:
    """Aggregates parsed class metadata used to build diagrams."""

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
    """Tree node used to organize classes by module namespace."""

    name: str
    full_name: str
    children: dict[str, NamespaceNode] = field(default_factory=dict)
    classes: list[ClassInfo] = field(default_factory=list)


def build_namespace_tree(classes: dict[str, ClassInfo]) -> NamespaceNode:
    """Build a namespace tree from a mapping of fully qualified class names."""
    root = NamespaceNode(name="", full_name="")

    for cls in classes.values():
        parts = [p for p in cls.module.split(".") if p]
        current = root
        prefix: list[str] = []

        for part in parts:
            prefix.append(part)
            full_name = ".".join(prefix)

            if part not in current.children:
                current.children[part] = NamespaceNode(name=part, full_name=full_name)
            current = current.children[part]

        current.classes.append(cls)

    return root


def should_skip_path(path: Path) -> bool:
    """Return True when a path contains an excluded directory name."""
    return any(part in EXCLUDED_DIR_NAMES for part in path.parts)


def safe_mermaid_id(name: str, style: MermaidIdStyle = MermaidIdStyle.FLAT) -> str:
    """Convert a class or namespace name into a Mermaid-safe identifier."""
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


def mermaid_id(name: str, style: str = "flat") -> str:
    """Map a style string to ``MermaidIdStyle`` and build a safe identifier."""
    return safe_mermaid_id(name, MermaidIdStyle(style))
