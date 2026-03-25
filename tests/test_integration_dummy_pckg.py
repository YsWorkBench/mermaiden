from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys

from inventory import read_inventory
from mermaiden import cmd_diagram, cmd_discover

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DUMMY_PACKAGE = ROOT / "examples" / "dummy_pckg"


def _inventory_fqcns(inventory_path: Path) -> set[str]:
    _, rows = read_inventory(inventory_path)
    return {fqcn for fqcn, _, _, _ in rows}


def test_dummy_package_main_instantiates_all_objects(tmp_path: Path) -> None:
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


def test_dummy_package_example_cli_integration(tmp_path: Path) -> None:
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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
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
    assert "+link: dummy_inheritance_nested_association" in generated_diagram
    assert (
        "`subpckg_inheritance.subpckg_inheritance_nested_association."
        "subpckg_inheritance_nested_association.dummy_inheritance_nested_association` "
        "--> `subpckg_inheritance.subpckg_inheritance_nested_inheritance."
        "subpckg_inheritance_nested_inheritance.dummy_inheritance_nested_inheritance`"
    ) in generated_diagram


def test_dummy_package_example_cli_follow_init_py(tmp_path: Path) -> None:
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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
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
        html_title="HTML UML Class Diagram",
        markdown_title="Mardown UML Class Diagram",
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
