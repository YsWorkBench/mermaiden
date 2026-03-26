"""Class discovery and relationship reconstruction from Python source files."""

from __future__ import annotations

import ast
from pathlib import Path

from ast_logic import (
    annotation_to_str,
    expr_to_name,
    extract_class_level_attributes,
    extract_method_info,
    infer_type_from_value,
    looks_like_interface,
    should_include_method,
    should_skip_pydantic_internal_attribute,
    split_type_names,
)
from inventory import guess_root_from_inventory, read_inventory
from models import (
    AttributeInfo,
    ClassInfo,
    mermaid_id,
    Relation,
    RelationType,
    should_skip_path,
)
from paths import (
    compute_module_name,
    compute_module_name_from_packages,
    parse_python_file,
)


class RelationCollector:
    """Collect attributes and relations from a class AST node."""

    def __init__(
        self, class_node: ast.ClassDef, module_name: str, qualname: str
    ) -> None:
        """Store class context used during relation extraction."""
        self.class_node = class_node
        self.module_name = module_name
        self.qualname = qualname

    def collect(self, current_fqcn: str) -> tuple[list[AttributeInfo], list[Relation]]:
        """Collect initializer attributes and method-level relations."""
        attrs: dict[str, AttributeInfo] = {}
        relations: dict[tuple[str, str, RelationType], Relation] = {}

        for rel in self._collect_class_attribute_associations(current_fqcn):
            key = (rel.source_fqcn, rel.target_name, rel.relation_type)
            relations[key] = rel

        for item in self.class_node.body:
            if (
                isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                and item.name == "__init__"
            ):
                init_attrs, init_relations = self._collect_init_relations(
                    item, current_fqcn
                )
                for attr in init_attrs:
                    prev = attrs.get(attr.name)
                    if prev is None or (not prev.type_name and attr.type_name):
                        attrs[attr.name] = attr
                for rel in init_relations:
                    relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = (
                        rel
                    )

            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for rel in self._collect_method_associations(item, current_fqcn):
                    key = (rel.source_fqcn, rel.target_name, rel.relation_type)
                    relations[key] = rel

        return sorted(attrs.values(), key=lambda a: a.name), list(relations.values())

    @staticmethod
    def _constructor_targets_from_value(node: ast.AST | None) -> set[str]:
        """Extract constructor call targets from assignment values."""
        if node is None:
            return set()

        if isinstance(node, ast.Call):
            callee = expr_to_name(node.func)
            return {callee} if callee else set()

        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            targets: set[str] = set()
            for elt in node.elts:
                targets.update(RelationCollector._constructor_targets_from_value(elt))
            return targets

        if isinstance(node, ast.Dict):
            targets = set()
            for key in node.keys:
                if key is not None:
                    targets.update(
                        RelationCollector._constructor_targets_from_value(key)
                    )
            for value in node.values:
                targets.update(RelationCollector._constructor_targets_from_value(value))
            return targets

        if isinstance(node, ast.ListComp):
            return RelationCollector._constructor_targets_from_value(node.elt)

        if isinstance(node, ast.SetComp):
            return RelationCollector._constructor_targets_from_value(node.elt)

        if isinstance(node, ast.DictComp):
            return RelationCollector._constructor_targets_from_value(
                node.key
            ) | RelationCollector._constructor_targets_from_value(node.value)

        if isinstance(node, ast.GeneratorExp):
            return RelationCollector._constructor_targets_from_value(node.elt)

        return set()

    @staticmethod
    def _is_container_type(type_name: str) -> bool:
        """Return True when a type annotation denotes a collection/container."""
        lowered = type_name.lower().replace(" ", "")
        container_markers = (
            "list[",
            "tuple[",
            "set[",
            "dict[",
            "iterable[",
            "sequence[",
            "mapping[",
            "mutablemapping[",
        )
        return any(marker in lowered for marker in container_markers)

    def _collect_init_relations(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        current_fqcn: str,
    ) -> tuple[list[AttributeInfo], list[Relation]]:
        """Extract relations created inside ``__init__`` assignments."""
        attrs: dict[str, AttributeInfo] = {}
        relations: dict[tuple[str, str, RelationType], Relation] = {}
        param_types: dict[str, str] = {}

        all_args = list(node.args.posonlyargs) + list(node.args.args)
        for i, arg in enumerate(all_args):
            if i == 0 and arg.arg == "self":
                continue
            param_types[arg.arg] = annotation_to_str(arg.annotation)

        if node.args.vararg is not None:
            param_types[node.args.vararg.arg] = annotation_to_str(
                node.args.vararg.annotation
            )
        for arg in node.args.kwonlyargs:
            param_types[arg.arg] = annotation_to_str(arg.annotation)
        if node.args.kwarg is not None:
            param_types[node.args.kwarg.arg] = annotation_to_str(
                node.args.kwarg.annotation
            )

        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                rhs_name = sub.value.id if isinstance(sub.value, ast.Name) else None
                rhs_constructor_targets = self._constructor_targets_from_value(
                    sub.value
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

                        if rhs_constructor_targets:
                            for dep in rhs_constructor_targets:
                                rel = Relation(
                                    source_fqcn=current_fqcn,
                                    target_name=dep,
                                    relation_type=RelationType.COMPOSITION,
                                    reason="self attribute initialized from constructor call",
                                )
                                relations[
                                    (
                                        rel.source_fqcn,
                                        rel.target_name,
                                        rel.relation_type,
                                    )
                                ] = rel
                        elif rhs_name and propagated_type:
                            rel_type = (
                                RelationType.AGGREGATION
                                if self._is_container_type(propagated_type)
                                else RelationType.ASSOCIATION
                            )
                            reason = (
                                "self attribute assigned from injected container parameter"
                                if rel_type == RelationType.AGGREGATION
                                else "self attribute assigned from injected parameter"
                            )
                            for dep in split_type_names(propagated_type):
                                rel = Relation(
                                    source_fqcn=current_fqcn,
                                    target_name=dep,
                                    relation_type=rel_type,
                                    reason=reason,
                                )
                                relations[
                                    (
                                        rel.source_fqcn,
                                        rel.target_name,
                                        rel.relation_type,
                                    )
                                ] = rel
                        elif final_type:
                            for dep in split_type_names(final_type):
                                rel = Relation(
                                    source_fqcn=current_fqcn,
                                    target_name=dep,
                                    relation_type=RelationType.ASSOCIATION,
                                    reason="self attribute typed or inferred",
                                )
                                relations[
                                    (
                                        rel.source_fqcn,
                                        rel.target_name,
                                        rel.relation_type,
                                    )
                                ] = rel

            elif isinstance(sub, ast.AnnAssign):
                if (
                    isinstance(sub.target, ast.Attribute)
                    and isinstance(sub.target.value, ast.Name)
                    and sub.target.value.id == "self"
                ):
                    ann_type = annotation_to_str(sub.annotation)
                    rhs_constructor_targets = self._constructor_targets_from_value(
                        sub.value
                    )
                    rhs_param_name = (
                        sub.value.id if isinstance(sub.value, ast.Name) else None
                    )
                    propagated_type = (
                        param_types.get(rhs_param_name, "") if rhs_param_name else ""
                    )
                    final_type = (
                        ann_type or propagated_type or infer_type_from_value(sub.value)
                    )

                    attrs[sub.target.attr] = AttributeInfo(sub.target.attr, final_type)

                    if rhs_constructor_targets:
                        for dep in rhs_constructor_targets:
                            rel = Relation(
                                source_fqcn=current_fqcn,
                                target_name=dep,
                                relation_type=RelationType.COMPOSITION,
                                reason="annotated self attribute initialized from constructor call",
                            )
                            relations[
                                (rel.source_fqcn, rel.target_name, rel.relation_type)
                            ] = rel
                    elif rhs_param_name and propagated_type:
                        rel_type = (
                            RelationType.AGGREGATION
                            if self._is_container_type(propagated_type)
                            else RelationType.ASSOCIATION
                        )
                        reason = (
                            "annotated self attribute assigned from injected container parameter"
                            if rel_type == RelationType.AGGREGATION
                            else "annotated self attribute assigned from injected parameter"
                        )
                        for dep in split_type_names(propagated_type):
                            rel = Relation(
                                source_fqcn=current_fqcn,
                                target_name=dep,
                                relation_type=rel_type,
                                reason=reason,
                            )
                            relations[
                                (rel.source_fqcn, rel.target_name, rel.relation_type)
                            ] = rel
                    elif final_type:
                        for dep in split_type_names(final_type):
                            rel = Relation(
                                source_fqcn=current_fqcn,
                                target_name=dep,
                                relation_type=RelationType.ASSOCIATION,
                                reason="annotated self attribute typed or inferred",
                            )
                            relations[
                                (rel.source_fqcn, rel.target_name, rel.relation_type)
                            ] = rel

        return list(attrs.values()), list(relations.values())

    def _collect_method_associations(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        current_fqcn: str,
    ) -> list[Relation]:
        """Extract association relations from method signatures and bodies."""
        relations: dict[tuple[str, str, RelationType], Relation] = {}

        for _, t in extract_method_info(node).params:
            for dep in split_type_names(t):
                rel = Relation(
                    current_fqcn, dep, RelationType.ASSOCIATION, "method parameter type"
                )
                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        for dep in split_type_names(annotation_to_str(node.returns)):
            rel = Relation(
                current_fqcn, dep, RelationType.ASSOCIATION, "method return type"
            )
            relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        for sub in ast.walk(node):
            if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                for dep in split_type_names(annotation_to_str(sub.annotation)):
                    rel = Relation(
                        current_fqcn,
                        dep,
                        RelationType.ASSOCIATION,
                        "typed local variable",
                    )
                    relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = (
                        rel
                    )

            if isinstance(sub, ast.Call):
                callee = expr_to_name(sub.func)
                short = callee.split(".")[-1]
                if short and short[:1].isupper():
                    rel = Relation(
                        current_fqcn,
                        short,
                        RelationType.ASSOCIATION,
                        "uses class in method body",
                    )
                    relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = (
                        rel
                    )

        return list(relations.values())

    def _collect_class_attribute_associations(
        self, current_fqcn: str
    ) -> list[Relation]:
        """Extract association relations from class-level annotated attributes."""
        relations: dict[tuple[str, str, RelationType], Relation] = {}

        for item in self.class_node.body:
            if not (
                isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)
            ):
                continue

            type_name = annotation_to_str(item.annotation)
            if not type_name:
                type_name = infer_type_from_value(item.value)
            if should_skip_pydantic_internal_attribute(item.target.id, type_name):
                continue

            for dep in split_type_names(type_name):
                rel = Relation(
                    current_fqcn,
                    dep,
                    RelationType.ASSOCIATION,
                    "class attribute type annotation",
                )
                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

        return list(relations.values())


class ClassCollector(ast.NodeVisitor):
    """AST visitor that turns class definitions into ``ClassInfo`` objects."""

    def __init__(self, module_name: str, filepath: Path, style: str = "flat") -> None:
        """Initialize collection state for a parsed file."""
        self.module_name = module_name
        self.filepath = filepath
        self.classes: list[ClassInfo] = []
        self._class_stack: list[str] = []
        self.style = style

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class and collect UML-related metadata."""
        qualname = (
            ".".join([*self._class_stack, node.name])
            if self._class_stack
            else node.name
        )
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


def _normalize_namespace_token(token: str) -> str:
    """Normalize a namespace token for fuzzy matching."""
    return "".join(ch for ch in token.lower() if ch.isalnum())


def _compute_module_name_for_discovery(
    root_dir: Path, filepath: Path, namespace_from_root: bool
) -> str:
    """Compute module names for discovery according to namespace mode."""
    if namespace_from_root:
        return str(compute_module_name(root_dir, filepath))

    rel = filepath.relative_to(root_dir).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _split_namespace(module_name: str) -> list[str]:
    """Split dotted module path into namespace segments."""
    return [part for part in module_name.split(".") if part]


def _namespace_prefix_matches(module_name: str, prefix: str) -> bool:
    """Return True when module starts with prefix using normalized tokens."""
    module_parts = [
        _normalize_namespace_token(p) for p in _split_namespace(module_name)
    ]
    prefix_parts = [_normalize_namespace_token(p) for p in _split_namespace(prefix)]
    if not prefix_parts:
        return True
    if len(module_parts) < len(prefix_parts):
        return False
    return all(m == p for m, p in zip(module_parts, prefix_parts))


def _resolve_import_target(
    package_module: str, module: str | None, level: int
) -> str | None:
    """Resolve import-from target into a dotted module path."""
    if level < 0:
        return None

    package_parts = _split_namespace(package_module)

    if level > 0:
        base_len = len(package_parts) - (level - 1)
        if base_len < 0:
            return None
        base_parts = package_parts[:base_len]
        module_parts = _split_namespace(module or "")
        return (
            ".".join([*base_parts, *module_parts]) if base_parts or module_parts else ""
        )

    if module:
        return module
    return None


def _parse_init_exports(
    root_dir: Path, namespace_from_root: bool = False
) -> dict[str, dict[str, set[str]]]:
    """Parse package ``__init__.py`` files and collect exported names."""
    exports: dict[str, dict[str, set[str]]] = {}

    for init_file in sorted(root_dir.rglob("__init__.py")):
        if should_skip_path(init_file):
            continue
        tree = parse_python_file(init_file)
        if tree is None:
            continue

        package_module = _compute_module_name_for_discovery(
            root_dir, init_file, namespace_from_root=namespace_from_root
        )
        explicit: set[str] = set()
        star_targets: set[str] = set()

        module_node = tree if isinstance(tree, ast.Module) else None
        if module_node is None:
            continue

        for stmt in module_node.body:
            if not isinstance(stmt, ast.ImportFrom):
                continue

            target = _resolve_import_target(package_module, stmt.module, stmt.level)

            for alias in stmt.names:
                if alias.name == "*":
                    if target:
                        star_targets.add(target)
                    continue
                explicit.add(alias.asname or alias.name.split(".")[-1])

        exports[package_module] = {"explicit": explicit, "star": star_targets}

    return exports


def _remap_classes_follow_init(
    classes: list[ClassInfo],
    root_dir: Path,
    style: str,
    namespace_from_root: bool = False,
) -> list[ClassInfo]:
    """Remap class namespaces by following ``__init__.py`` exports."""
    init_exports = _parse_init_exports(
        root_dir, namespace_from_root=namespace_from_root
    )
    if not init_exports:
        return classes

    top_level = [cls for cls in classes if "." not in cls.qualname]
    exported_names: dict[str, set[str]] = {
        pkg: set(data["explicit"]) for pkg, data in init_exports.items()
    }

    # Propagate star-exported names across package boundaries until stable.
    changed = True
    while changed:
        changed = False
        for pkg, data in init_exports.items():
            names = exported_names.setdefault(pkg, set())
            before = len(names)

            for target in data["star"]:
                for cls in top_level:
                    if _namespace_prefix_matches(cls.module, target):
                        names.add(cls.name)

                for other_pkg, other_names in exported_names.items():
                    if _namespace_prefix_matches(other_pkg, target):
                        names.update(other_names)

            if len(names) != before:
                changed = True

    # Skip ambiguous remapping for packages exporting duplicate class names.
    ambiguous: set[tuple[str, str]] = set()
    for pkg, names in exported_names.items():
        for name in names:
            matching = [
                cls
                for cls in top_level
                if cls.name == name and _namespace_prefix_matches(cls.module, pkg)
            ]
            if len(matching) > 1:
                ambiguous.add((pkg, name))

    remapped: list[ClassInfo] = []
    for cls in classes:
        top_name = cls.qualname.split(".")[0]
        package_candidates = [
            pkg
            for pkg, names in exported_names.items()
            if top_name in names
            and (pkg, top_name) not in ambiguous
            and _namespace_prefix_matches(cls.module, pkg)
        ]

        if package_candidates:
            new_module = sorted(
                package_candidates, key=lambda p: (len(_split_namespace(p)), p)
            )[0]
        else:
            new_module = cls.module

        new_fqcn = f"{new_module}.{cls.qualname}" if new_module else cls.qualname
        new_relations = [
            Relation(
                source_fqcn=new_fqcn,
                target_name=rel.target_name,
                relation_type=rel.relation_type,
                reason=rel.reason,
            )
            for rel in cls.relations
        ]

        remapped.append(
            ClassInfo(
                class_id=mermaid_id(new_fqcn, style),
                fqcn=new_fqcn,
                module=new_module,
                qualname=cls.qualname,
                name=cls.name,
                filepath=cls.filepath,
                lineno=cls.lineno,
                bases=cls.bases,
                methods=cls.methods,
                attributes=cls.attributes,
                relations=new_relations,
            )
        )

    return remapped


def discover_classes(
    root_dir: Path,
    style: str = "flat",
    follow: str = "path",
    namespace_from_root: bool = False,
) -> list[ClassInfo]:
    """Recursively discover classes in Python files below ``root_dir``."""
    found: list[ClassInfo] = []
    for filepath in sorted(root_dir.rglob("*.py")):
        if should_skip_path(filepath):
            continue
        tree = parse_python_file(filepath)
        if tree is None:
            continue
        module_name = _compute_module_name_for_discovery(
            root_dir, filepath, namespace_from_root=namespace_from_root
        )
        collector = ClassCollector(module_name, filepath, style=style)
        collector.visit(tree)
        found.extend(collector.classes)

    if follow == "path":
        return found

    if follow == "init.py":
        return _remap_classes_follow_init(
            found,
            root_dir,
            style=style,
            namespace_from_root=namespace_from_root,
        )

    raise ValueError(f"Unsupported follow mode: {follow}")


def rebuild_class_map_from_inventory(
    inventory_file: Path, style: str = "flat"
) -> dict[str, ClassInfo]:
    """Rebuild class metadata from an inventory and current source files."""
    stored_root, requested = read_inventory(inventory_file)
    if not requested:
        return {}

    root_hint = guess_root_from_inventory(stored_root, requested)

    existing_files = sorted(
        {filepath for _, filepath, *_ in requested if filepath.exists()}
    )
    if not existing_files:
        print("[WARN] None of the inventory file paths currently exist.")
        return {}

    parsed_by_file: dict[Path, list[ClassInfo]] = {}
    fqcn_index: dict[str, ClassInfo] = {}

    for filepath in existing_files:
        tree = parse_python_file(filepath)
        if tree is None:
            continue

        module_name = compute_module_name_from_packages(filepath, root_hint)
        collector = ClassCollector(
            module_name=module_name, filepath=filepath, style=style
        )
        collector.visit(tree)

        parsed_by_file[filepath] = collector.classes
        for cls in collector.classes:
            fqcn_index[cls.fqcn] = cls

    class_map: dict[str, ClassInfo] = {}

    for entry in requested:
        fqcn = entry[0]
        filepath = entry[1]

        if fqcn in class_map or not filepath.exists():
            continue

        requested_parts = fqcn.split(".")
        requested_short_name = requested_parts[-1]

        candidates = parsed_by_file.get(filepath, [])
        if not candidates:
            continue

        direct = fqcn_index.get(fqcn)
        if direct is not None and Path(direct.filepath) == filepath:
            class_map[fqcn] = direct
            continue

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

        short_matches = [cls for cls in candidates if cls.name == requested_short_name]

        if len(short_matches) == 1:
            matched = short_matches[0]

            if fqcn.endswith("." + matched.qualname):
                rebuilt_module = fqcn[: -(len(matched.qualname) + 1)]
                rebuilt_qualname = matched.qualname
            elif fqcn == matched.qualname:
                rebuilt_module = ""
                rebuilt_qualname = matched.qualname
            else:
                rebuilt_qualname = matched.qualname
                if "." in fqcn:
                    rebuilt_module = fqcn.rsplit(".", 1)[0]
                else:
                    rebuilt_module = ""

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

        print(
            f"[WARN] Could not safely rebuild class from inventory entry: {fqcn} ({filepath})"
        )

    return class_map


def resolve_target_name(
    target_name: str, current_class: ClassInfo, known_classes: dict[str, ClassInfo]
) -> str | None:
    """Resolve a relation target to a known fully qualified class name."""
    if target_name in known_classes:
        return target_name

    same_module = (
        f"{current_class.module}.{target_name}" if current_class.module else target_name
    )
    if same_module in known_classes:
        return same_module

    suffix_matches = [
        fqcn
        for fqcn in known_classes
        if fqcn.endswith(f".{target_name}") or fqcn == target_name
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]

    return None


def merge_relation(existing: RelationType, new: RelationType) -> RelationType:
    """Keep the strongest relationship type based on priority."""
    priority = {
        RelationType.INHERITANCE: 5,
        RelationType.REALIZATION: 4,
        RelationType.COMPOSITION: 3,
        RelationType.AGGREGATION: 2,
        RelationType.ASSOCIATION: 1,
    }
    return existing if priority[existing] >= priority[new] else new


def should_treat_base_as_realization(
    base_name: str, target_fqcn: str, classes: dict[str, ClassInfo]
) -> bool:
    """Decide whether a base-edge should be modeled as realization."""
    if looks_like_interface(base_name):
        return True

    target_cls = classes.get(target_fqcn)
    if target_cls is None:
        return False

    # A base class inheriting from ABC/Protocol behaves like an interface contract.
    return any(looks_like_interface(parent) for parent in target_cls.bases)


def collect_all_relations(
    classes: dict[str, ClassInfo]
) -> list[tuple[str, RelationType, str]]:
    """Collect and normalize all inheritance and association relations."""
    resolved: dict[tuple[str, str], RelationType] = {}

    for cls in classes.values():
        for base in cls.bases:
            target = resolve_target_name(base, cls, classes)
            if not target:
                continue
            rel_type = (
                RelationType.REALIZATION
                if should_treat_base_as_realization(base, target, classes)
                else RelationType.INHERITANCE
            )
            key = (
                (cls.fqcn, target)
                if rel_type == RelationType.REALIZATION
                else (target, cls.fqcn)
            )
            resolved[key] = merge_relation(resolved.get(key, rel_type), rel_type)

        for rel in cls.relations:
            target = resolve_target_name(rel.target_name, cls, classes)
            if not target or target == cls.fqcn:
                continue
            key = (
                (target, cls.fqcn)
                if rel.relation_type == RelationType.ASSOCIATION
                else (cls.fqcn, target)
            )
            resolved[key] = merge_relation(
                resolved.get(key, rel.relation_type), rel.relation_type
            )

    return [(src, rtype, tgt) for (src, tgt), rtype in sorted(resolved.items())]
