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
    split_type_names,
)
from inventory import guess_root_from_inventory, read_inventory
from models import AttributeInfo, ClassInfo, Relation, RelationType, mermaid_id, should_skip_path
from paths import compute_module_name, compute_module_name_from_packages, parse_python_file


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
                rhs_call_name = expr_to_name(sub.value.func) if isinstance(sub.value, ast.Call) else ""
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
                                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel
                        elif final_type:
                            for dep in split_type_names(final_type):
                                rel = Relation(
                                    source_fqcn=current_fqcn,
                                    target_name=dep,
                                    relation_type=RelationType.ASSOCIATION,
                                    reason="self attribute typed or inferred",
                                )
                                relations[(rel.source_fqcn, rel.target_name, rel.relation_type)] = rel

            elif isinstance(sub, ast.AnnAssign):
                if (
                    isinstance(sub.target, ast.Attribute)
                    and isinstance(sub.target.value, ast.Name)
                    and sub.target.value.id == "self"
                ):
                    ann_type = annotation_to_str(sub.annotation)
                    rhs_call_name = expr_to_name(sub.value.func) if isinstance(sub.value, ast.Call) else ""
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
                    rel = Relation(current_fqcn, dep, RelationType.ASSOCIATION, "typed local variable")
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
        module_name = compute_module_name(root_dir, filepath)
        collector = ClassCollector(module_name, filepath, style=style)
        collector.visit(tree)
        found.extend(collector.classes)
    return found


def rebuild_class_map_from_inventory(
    inventory_file: Path, style: str = "flat"
) -> dict[str, ClassInfo]:
    stored_root, requested = read_inventory(inventory_file)
    if not requested:
        return {}

    root_hint = guess_root_from_inventory(stored_root, requested)

    existing_files = sorted({filepath for _, filepath, *_ in requested if filepath.exists()})
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
        collector = ClassCollector(module_name=module_name, filepath=filepath, style=style)
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
            else:
                rebuilt_qualname = matched.qualname
                if "." in fqcn:
                    rebuilt_module = fqcn.rsplit(".", 1)[0]
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

        print(f"[WARN] Could not safely rebuild class from inventory entry: {fqcn} ({filepath})")

    return class_map


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
            rel_type = RelationType.REALIZATION if looks_like_interface(base) else RelationType.INHERITANCE
            key = (target, cls.fqcn)
            resolved[key] = merge_relation(resolved.get(key, rel_type), rel_type)

        for rel in cls.relations:
            target = resolve_target_name(rel.target_name, cls, classes)
            if not target or target == cls.fqcn:
                continue
            key = (cls.fqcn, target)
            resolved[key] = merge_relation(resolved.get(key, rel.relation_type), rel.relation_type)

    return [(src, rtype, tgt) for (src, tgt), rtype in sorted(resolved.items())]
