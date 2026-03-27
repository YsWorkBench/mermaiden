from __future__ import annotations

import argparse
import ast
from pathlib import Path
import shutil
import subprocess
import sys

from discovery import collect_all_relations, rebuild_class_map_from_inventory
from inventory import read_inventory
from mermaiden import cmd_diagram, cmd_discover, cmd_generate

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DUMMY_PACKAGE = ROOT / "examples" / "dummy_pckg"
EXAMPLE_DUMMY_PYDANTIC_PACKAGE = ROOT / "examples" / "dummy_pckg_pydantic"
EXAMPLE_DUMMY_DIAGRAM = ROOT / "examples" / "dummy_pckgUML.md"
PERSISTED_RECREATED_DUMMY_PACKAGE = (
    ROOT / "examples" / "generated_dummy_pckg_inspect_once"
)


def _inventory_fqcns(inventory_path: Path) -> set[str]:
    _, rows = read_inventory(inventory_path)
    return {fqcn for fqcn, _, _, _ in rows}


def _ensure_example_dummy_package_exists() -> None:
    if EXAMPLE_DUMMY_PACKAGE.exists():
        return

    assert EXAMPLE_DUMMY_DIAGRAM.exists(), (
        "Missing both examples/dummy_pckg and examples/dummy_pckgUML.md; "
        "cannot recreate dummy package fixture."
    )

    source_root = EXAMPLE_DUMMY_PACKAGE / "src"
    source_root.mkdir(parents=True, exist_ok=True)
    recreate_args = argparse.Namespace(
        diagram=str(EXAMPLE_DUMMY_DIAGRAM),
        output=str(source_root),
    )
    assert cmd_generate(recreate_args) == 0
    assert (source_root / "dummy_pckg.py").exists()


def _relative_files(root: Path) -> set[str]:
    return {str(path.relative_to(root)) for path in root.rglob("*") if path.is_file()}


def _relation_signature(inventory_path: Path) -> set[tuple[str, str, str]]:
    classes = rebuild_class_map_from_inventory(inventory_path, style="escaped")
    return {
        (source_fqcn, relation_type.value, target_fqcn)
        for source_fqcn, relation_type, target_fqcn in collect_all_relations(classes)
    }


def _run_discover_and_diagram(
    source_root: Path,
    tmp_path: Path,
    stem: str,
) -> tuple[Path, Path]:
    inventory_out = tmp_path / f"{stem}.txt"
    diagram_out = tmp_path / f"{stem}.md"

    discover_args = argparse.Namespace(
        root=str(source_root),
        output=str(inventory_out),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    diagram_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_out),
        namespace="nested",
        style="escaped",
        aliases=True,
        title="UML Class Diagram",
    )
    assert cmd_discover(discover_args) == 0
    assert inventory_out.exists()
    assert cmd_diagram(diagram_args) == 0
    assert diagram_out.exists()
    return inventory_out, diagram_out


def test_dummy_package_main_instantiates_all_objects(tmp_path: Path) -> None:
    _ensure_example_dummy_package_exists()
    copied_package = tmp_path / "dummy_pckg"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_package)
    source_root = copied_package / "src"
    entrypoint = source_root / "dummy_pckg.py"

    completed = subprocess.run(
        [sys.executable, str(entrypoint)],
        cwd=source_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert "MyABC: Hello World" in completed.stdout
    assert "All dummy_pckg objects instantiated successfully." in completed.stdout


def test_dummy_pydantic_package_generates_similar_diagram(tmp_path: Path) -> None:
    _ensure_example_dummy_package_exists()
    assert EXAMPLE_DUMMY_PYDANTIC_PACKAGE.exists()

    copied_dummy_package = tmp_path / "dummy_pckg"
    copied_pydantic_package = tmp_path / "dummy_pckg_pydantic"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_dummy_package)
    shutil.copytree(EXAMPLE_DUMMY_PYDANTIC_PACKAGE, copied_pydantic_package)

    dummy_inventory, _ = _run_discover_and_diagram(
        copied_dummy_package / "src",
        tmp_path,
        "dummy_pckg",
    )
    pydantic_inventory, pydantic_diagram = _run_discover_and_diagram(
        copied_pydantic_package / "src",
        tmp_path,
        "dummy_pckg_pydantic",
    )

    assert _inventory_fqcns(dummy_inventory) == _inventory_fqcns(pydantic_inventory)
    assert _relation_signature(dummy_inventory) == _relation_signature(
        pydantic_inventory
    )

    pydantic_diagram_text = pydantic_diagram.read_text(encoding="utf-8")
    assert "+composition: list[dummy.dummy_composition]" in pydantic_diagram_text
    assert "+composition: list['dummy.dummy_composition']" not in pydantic_diagram_text
    assert (
        "`dummy_pckg.dummy` *-- `dummy_pckg.dummy.dummy_composition`"
        in pydantic_diagram_text
    )
    assert (
        "`dummy_pckg.dummy` o-- "
        "`subpckg_aggregation.subpckg_aggregation.dummy_aggregation`"
        in pydantic_diagram_text
    )
    assert (
        "`dummy_pckg.dummy.dummy_composition` --> `dummy_pckg.dummy`"
        not in pydantic_diagram_text
    )
    assert (
        "`subpckg_aggregation.subpckg_aggregation.dummy_aggregation` --> "
        "`dummy_pckg.dummy`" not in pydantic_diagram_text
    )


def test_dummy_package_example_cli_integration(tmp_path: Path) -> None:
    _ensure_example_dummy_package_exists()
    copied_package = tmp_path / "dummy_pckg"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_package)

    source_root = copied_package / "src"
    inventory_out = tmp_path / "dummy_pckg.txt"
    diagram_out = tmp_path / "dummy_pckgUML.md"

    discover_args = argparse.Namespace(
        root=str(source_root),
        output=str(inventory_out),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    diagram_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_out),
        namespace="nested",
        style="escaped",
        aliases=True,
        title="UML Class Diagram",
    )

    assert cmd_discover(discover_args) == 0
    assert inventory_out.exists()

    stored_root, rows = read_inventory(inventory_out)
    assert stored_root == source_root.resolve()
    assert rows
    for _, filepath, _, import_root in rows:
        assert filepath.is_relative_to(copied_package.resolve())
        assert import_root == copied_package.resolve()

    assert cmd_diagram(diagram_args) == 0
    assert diagram_out.exists()

    expected_fqcns = {
        "dummy_pckg.dummy",
        "dummy_pckg.dummy.dummy_composition",
        "subpckg_aggregation.subpckg_aggregation.dummy_aggregation",
        "subpckg_association.subpckg_association.dummy_association",
        "subpckg_inheritance.subpckg_inheritance.DummyTypeEnum",
        "subpckg_inheritance.subpckg_inheritance.OrderedEnum",
        "subpckg_inheritance.subpckg_inheritance.dummy_inheritance",
        (
            "subpckg_inheritance.subpckg_inheritance_nested_association."
            "subpckg_inheritance_nested_association."
            "dummy_inheritance_nested_association"
        ),
        (
            "subpckg_inheritance.subpckg_inheritance_nested_inheritance."
            "subpckg_inheritance_nested_inheritance."
            "dummy_inheritance_nested_inheritance"
        ),
        "subpckg_realisation.subpckg_realisation.dummy_realisation",
    }
    assert _inventory_fqcns(inventory_out) == expected_fqcns

    generated_diagram = diagram_out.read_text(encoding="utf-8")

    assert (
        "`subpckg_association.subpckg_association.dummy_association` --> "
        "`dummy_pckg.dummy`"
    ) in generated_diagram
    assert (
        "`dummy_pckg.dummy` ..|> "
        "`subpckg_realisation.subpckg_realisation.dummy_realisation`"
    ) in generated_diagram
    assert "+aggregations: Optional[list[dummy_aggregation]]" in generated_diagram
    assert "-type_: Literal[DummyTypeEnum.DummyPckg]" in generated_diagram
    assert "-type_: Literal[DummyTypeEnum.DummyComposition]" in generated_diagram
    assert "-type_: Literal[DummyTypeEnum.DummyAggregation]" in generated_diagram
    assert "-type_: Literal[DummyTypeEnum.DummyAssociation]" in generated_diagram
    assert "-type_: Literal[DummyTypeEnum.DummyInheritance]" in generated_diagram
    assert (
        "-type_: Literal[DummyTypeEnum.DummyInheritanceNestedAssociation]"
        in generated_diagram
    )
    assert (
        "-type_: Literal[DummyTypeEnum.DummyInheritanceNestedInheritance]"
        in generated_diagram
    )
    assert "-type_: Literal[DummyTypeEnum.DummyRealisation]" in generated_diagram
    assert "+link: dummy_inheritance_nested_association" in generated_diagram
    assert (
        "`subpckg_inheritance.subpckg_inheritance_nested_association."
        "subpckg_inheritance_nested_association.dummy_inheritance_nested_association` "
        "--> `subpckg_inheritance.subpckg_inheritance_nested_inheritance."
        "subpckg_inheritance_nested_inheritance.dummy_inheritance_nested_inheritance`"
    ) in generated_diagram
    assert (
        "`subpckg_inheritance.subpckg_inheritance.OrderedEnum` <|-- "
        "`subpckg_inheritance.subpckg_inheritance.DummyTypeEnum`"
    ) in generated_diagram


def test_dummy_package_example_cli_follow_init_py(tmp_path: Path) -> None:
    _ensure_example_dummy_package_exists()
    copied_package = tmp_path / "dummy_pckg"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_package)

    source_root = copied_package / "src"
    inventory_out = tmp_path / "dummy_pckg_follow_init.txt"
    diagram_out = tmp_path / "dummy_pckg_follow_init.md"

    discover_args = argparse.Namespace(
        root=str(source_root),
        output=str(inventory_out),
        style="escaped",
        follow="init.py",
        namespace_from_root=False,
    )
    diagram_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_out),
        namespace="nested",
        style="escaped",
        aliases=True,
        title="UML Class Diagram",
    )

    assert cmd_discover(discover_args) == 0
    assert inventory_out.exists()
    assert cmd_diagram(diagram_args) == 0
    assert diagram_out.exists()

    fqcns = _inventory_fqcns(inventory_out)
    assert "subpckg_association.dummy_association" in fqcns
    assert "subpckg_realisation.dummy_realisation" in fqcns
    assert "dummy_association" not in fqcns
    assert "dummy_realisation" not in fqcns

    diagram_text = diagram_out.read_text(encoding="utf-8")
    assert "namespace `src`{" not in diagram_text
    assert "namespace `src.subpckg_association`{" not in diagram_text
    assert 'namespace `subpckg_association`["subpckg_association"]{' in diagram_text
    assert "`subpckg_association.dummy_association` --> `dummy_pckg.dummy`" in (
        diagram_text
    )
    assert "`dummy_pckg.dummy` ..|> `subpckg_realisation.dummy_realisation`" in (
        diagram_text
    )
    assert (
        "`subpckg_inheritance.subpckg_inheritance_nested_association."
        "dummy_inheritance_nested_association` --> "
        "`subpckg_inheritance.subpckg_inheritance_nested_inheritance."
        "dummy_inheritance_nested_inheritance`"
    ) in diagram_text


def test_dummy_package_example_cli_namespace_from_root(tmp_path: Path) -> None:
    _ensure_example_dummy_package_exists()
    copied_package = tmp_path / "dummy_pckg"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_package)

    source_root = copied_package / "src"
    inventory_out = tmp_path / "dummy_pckg_from_root.txt"
    diagram_out = tmp_path / "dummy_pckg_from_root.md"

    discover_args = argparse.Namespace(
        root=str(source_root),
        output=str(inventory_out),
        style="escaped",
        follow="path",
        namespace_from_root=True,
    )
    diagram_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_out),
        namespace="nested",
        style="escaped",
        aliases=True,
        title="UML Class Diagram",
    )

    assert cmd_discover(discover_args) == 0
    assert inventory_out.exists()
    assert cmd_diagram(diagram_args) == 0
    assert diagram_out.exists()

    fqcns = _inventory_fqcns(inventory_out)
    assert "src.dummy_pckg.dummy" in fqcns
    assert "dummy_pckg.dummy" not in fqcns

    diagram_text = diagram_out.read_text(encoding="utf-8")
    assert 'namespace `src`["src"]{' in diagram_text
    assert 'namespace `src.dummy_pckg`["src.dummy_pckg"]{' in diagram_text
    assert (
        "`src.subpckg_association.subpckg_association.dummy_association` --> "
        "`src.dummy_pckg.dummy`"
    ) in diagram_text
    assert (
        "`src.subpckg_inheritance.subpckg_inheritance_nested_association."
        "subpckg_inheritance_nested_association.dummy_inheritance_nested_association` "
        "--> `src.subpckg_inheritance.subpckg_inheritance_nested_inheritance."
        "subpckg_inheritance_nested_inheritance.dummy_inheritance_nested_inheritance`"
    ) in diagram_text


def test_dummy_package_example_cli_aliases_off(tmp_path: Path) -> None:
    _ensure_example_dummy_package_exists()
    copied_package = tmp_path / "dummy_pckg"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_package)

    source_root = copied_package / "src"
    inventory_out = tmp_path / "dummy_pckg_aliases_off.txt"
    diagram_out = tmp_path / "dummy_pckg_aliases_off.md"

    discover_args = argparse.Namespace(
        root=str(source_root),
        output=str(inventory_out),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    diagram_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_out),
        namespace="nested",
        style="escaped",
        aliases=False,
        title="UML Class Diagram",
    )

    assert cmd_discover(discover_args) == 0
    assert inventory_out.exists()
    assert cmd_diagram(diagram_args) == 0
    assert diagram_out.exists()

    diagram_text = diagram_out.read_text(encoding="utf-8")
    assert "namespace `dummy_pckg`{" in diagram_text
    assert 'namespace `dummy_pckg`["dummy_pckg"]{' not in diagram_text
    assert "class `dummy_pckg.dummy.dummy_composition`" in diagram_text
    assert (
        'class `dummy_pckg.dummy.dummy_composition`["dummy.dummy_composition"]'
        not in diagram_text
    )


def test_dummy_package_generate_recreates_structure_from_markdown_and_html(
    tmp_path: Path,
) -> None:
    _ensure_example_dummy_package_exists()
    copied_package = tmp_path / "dummy_pckg"
    shutil.copytree(EXAMPLE_DUMMY_PACKAGE, copied_package)

    source_root = copied_package / "src"
    inventory_out = tmp_path / "dummy_pckg.txt"
    diagram_md = tmp_path / "dummy_pckgUML.md"
    diagram_html = tmp_path / "dummy_pckgUML.html"
    generated_md_root = tmp_path / "generated_from_md"
    generated_html_root = tmp_path / "generated_from_html"

    discover_args = argparse.Namespace(
        root=str(source_root),
        output=str(inventory_out),
        style="escaped",
        follow="path",
        namespace_from_root=False,
    )
    diagram_md_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_md),
        namespace="nested",
        style="escaped",
        aliases=True,
        title="UML Class Diagram",
    )
    diagram_html_args = argparse.Namespace(
        inventory=str(inventory_out),
        output=str(diagram_html),
        namespace="nested",
        style="escaped",
        aliases=True,
        title="UML Class Diagram",
    )

    assert cmd_discover(discover_args) == 0
    assert cmd_diagram(diagram_md_args) == 0
    assert cmd_diagram(diagram_html_args) == 0

    generate_md_args = argparse.Namespace(
        diagram=str(diagram_md),
        output=str(generated_md_root),
    )
    generate_html_args = argparse.Namespace(
        diagram=str(diagram_html),
        output=str(generated_html_root),
    )
    assert cmd_generate(generate_md_args) == 0
    assert cmd_generate(generate_html_args) == 0

    # Keep one recreated tree on disk for manual inspection if it does not exist yet.
    if not PERSISTED_RECREATED_DUMMY_PACKAGE.exists():
        shutil.copytree(generated_md_root, PERSISTED_RECREATED_DUMMY_PACKAGE)

    expected_files = {
        "dummy_pckg.py",
        "subpckg_aggregation/__init__.py",
        "subpckg_aggregation/subpckg_aggregation.py",
        "subpckg_association/__init__.py",
        "subpckg_association/subpckg_association.py",
        "subpckg_inheritance/__init__.py",
        "subpckg_inheritance/subpckg_inheritance.py",
        "subpckg_inheritance/subpckg_inheritance_nested_association/__init__.py",
        (
            "subpckg_inheritance/subpckg_inheritance_nested_association/"
            "subpckg_inheritance_nested_association.py"
        ),
        "subpckg_inheritance/subpckg_inheritance_nested_inheritance/__init__.py",
        (
            "subpckg_inheritance/subpckg_inheritance_nested_inheritance/"
            "subpckg_inheritance_nested_inheritance.py"
        ),
        "subpckg_realisation/__init__.py",
        "subpckg_realisation/subpckg_realisation.py",
    }

    md_files = _relative_files(generated_md_root)
    html_files = _relative_files(generated_html_root)
    assert md_files == expected_files
    assert html_files == expected_files

    for relpath in sorted(expected_files):
        md_file = generated_md_root / relpath
        html_file = generated_html_root / relpath
        md_text = md_file.read_text(encoding="utf-8")
        html_text = html_file.read_text(encoding="utf-8")
        assert md_text == html_text
        if md_file.suffix == ".py":
            ast.parse(md_text)

    generated_dummy = (generated_md_root / "dummy_pckg.py").read_text(encoding="utf-8")
    assert "class dummy(dummy_realisation):" in generated_dummy
    assert "inheritance_link: Optional[dummy_inheritance_nested_inheritance]" in (
        generated_dummy
    )
    assert "def MyABC(self) -> str:" in generated_dummy

    generated_realisation = (
        generated_md_root / "subpckg_realisation" / "subpckg_realisation.py"
    ).read_text(encoding="utf-8")
    assert "class dummy_realisation(dummy_inheritance):" in generated_realisation
    assert "def MyABC(self) -> str:" in generated_realisation

    generated_nested_inheritance = (
        generated_md_root
        / "subpckg_inheritance"
        / "subpckg_inheritance_nested_inheritance"
        / "subpckg_inheritance_nested_inheritance.py"
    ).read_text(encoding="utf-8")
    assert (
        "from subpckg_inheritance.subpckg_inheritance import dummy_inheritance"
        in generated_nested_inheritance
    )
    assert (
        "from subpckg_inheritance.subpckg_inheritance_nested_association."
        "subpckg_inheritance_nested_association import "
        "dummy_inheritance_nested_association"
    ) in generated_nested_inheritance
    assert "class dummy_inheritance_nested_inheritance(dummy_inheritance):" in (
        generated_nested_inheritance
    )
    assert "link: dummy_inheritance_nested_association" in generated_nested_inheritance
