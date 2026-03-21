![logo](imgs/Mermaiden_banner_small.png)

A Python package to discover class relationships in Python packages and draw them into Mermaid UML class diagrams. As of today (March 2026), this project is related to:

+ The [pymermaider](https://github.com/diceroll123/pymermaider) project, but the issue was pymermaider could only generate one diagram for each single python module with incorrect joint namespace handling. Additionally, it couldn't handle complex class relationships properly.
+ The [mermaid-py](https://github.com/ouhammmourachid/mermaid-py) which couldn't handle class diagrams at the time I started this AI coding adventure.

Indeed, everything in this adventure was assisted by AI, even the logo. 

## Features

- [x] **Two-phase extraction**: Discover classes first, then generate diagrams
- [x] **Recursive scanning**: Analyzes entire Python packages automatically
- [x] **Namespace-aware**: Respects Python package structure and `__init__.py` files
- [ ] **Multiple relationship types**: TODO correct the handling of Inheritance, composition, aggregation, and association
- [x] **Type extraction**: Supports type hints and inferred types
- [x] **Flexible output**: Generate both Markdown and HTML Mermaid diagrams
- [x] **Command-line interface**: Easy-to-use CLI with `mermaiden` command

## Compatibility

This package is compatible with Python `3.10+` and Mermaid `10.7.0` with some extra compatibility with Mermaid `11.X.0`.

## Installation

### From Source

Install the package in editable mode from the source repository:

```bash
# Using pip
pip install -e .

# Or using uv (recommended)
uv pip install -e .
```

### Development Installation

For development with optional dependencies:

```bash
# Using pip
pip install -e ".[dev]"

# Or using uv
uv pip install -e ".[dev]"
```

## Usage

### Command Line Interface

After installation, you can use the `mermaiden` command:

```bash
# Phase 1: Discover classes in a Python package
mermaiden discover ./src --output classes.txt
```

Which will create a file `classes.txt` with the following content extracted from the `ctypes` module:

```
# ROOT	/usr/lib/python3.13/ctypes
# FQCN	FILEPATH	LINENO	IMPORT_ROOT
ctypes.CDLL	/usr/lib/python3.13/ctypes/__init__.py	322	/usr/lib/python3.13
ctypes.CDLL._FuncPtr	/usr/lib/python3.13/ctypes/__init__.py	384	/usr/lib/python3.13
```

The different columns are:
- `FQCN`: Fully Qualified Class Name
- `FILEPATH`: Path to the file containing the class
- `LINENO`: Line number where the class is defined
- `IMPORT_ROOT`: Root directory for imports

> [!NOTE] TODO
> Check the `IMPORT_ROOT` usage, which is the root directory for imports, and might be unnecessary as the `FILEPATH` already contains the full path.

```bash       
# Phase 2: Generate Mermaid UML diagram from inventory
mermaiden diagram classes.txt --output UMLdiagram.md
```

Which generates a Markdown file `UMLdiagram.md` with the following content for the `ctypes` module:

::include{examples/ctypesUML}

### Advanced Options

```bash
# Generate HTML output instead of Markdown
mermaiden diagram classes.txt --output diagram.html

# Customize namespace rendering (nested or legacy)
mermaiden diagram classes.txt --namespace nested

# Choose identifier style (flat or escaped)
mermaiden diagram classes.txt --style flat

# Custom titles
mermaiden diagram classes.txt --markdown-title "My Project UML" --html-title "My Project Diagram"
```

### Python API

You can also use the package directly in Python code:

```python
from mermaiden import main
import sys

# Use the CLI programmatically
sys.argv = ["mermaiden", "discover", "./src", "--output", "classes.txt"]
main()

sys.argv = ["mermaiden", "diagram", "classes.txt", "--output", "diagram.md"]
main()
```

### The choice of the extra parameters

As of October 2025, `Gitlab 18.0` uses Mermaid `10.7.0`, most probably because the huge amounts of bugs introduced in `11.X.0` versions. To make the tool compatible with Gitlab's version of Mermaid `10.7.0`, this project uses some extra parameters:

+ `--style`
  + `flat`: Uses the flat style (default) to remove the `.` of in submodule names and replace them by `_`:

```
classDiagram
    namespace mypackage_subpackage {
        ...
    }
```

  + `escaped`: Uses the markdown escape character (backtick) introduced in versions `>= 11.4.0` but randomly broken in version `11.13.0` of the live mermaid editor when testing:

```
classDiagram
    namespace `mypackage.subpackage` {
        ...
    }
```

+ `--namespace`
  + `flat`: Uses the flat namespace format (default) with the namespace include class trick:

```
classDiagram
    namespace `mypackage.subpackage` {
        class subsubpackage
        class MySubPackageClass{
            ...
        }
    }
    namespace `mypackage.subpackage.subsubpackage` {
        class MySubSubPackageClass{
            ...
        }
    }
```

  + `nested`: Uses the nested namespace format introduced in versions `>= 11.3.0` but randomly broken for recursive namespaces in version `11.13.0` of the live mermaid editor when testing:

```
classDiagram
    namespace `mypackage.subpackage` {
        class MySubPackageClass{
            ...
        }
        namespace `mypackage.subpackage.subsubpackage` {
            class MySubSubPackageClass{
                ...
            }
        }
        
    }
```

So this package wishes to be able to use all the new functionalities of Mermaid in future stable versions while being compatible with older versions.

## Two-Phase Workflow

1. **Discovery Phase**: Scan your Python source code and create an inventory file containing class information
2. **Diagram Phase**: Read a potentially manually filtered inventory file and generate a Mermaid UML class diagram either in markdown or HTML format.

This two-phase approach allows you to:
- Save and reuse class inventories
- Manually filter the inventory file to focus on specific classes or relationships
- Generate multiple diagram formats from the same analysis
- Share class information without exposing source code

> [!NOTE]
> The HTML version lets you save the diagram as a PDF or SVG image file which is particularly useful for a huge amount of classes in the UML diagram.

## Output Formats

### Markdown (.md)
Generates a Markdown file with embedded Mermaid diagram that can be rendered by:
- GitHub/GitLab
- Obsidian
- Mermaid Live Editor
- Any Markdown viewer with Mermaid support

### HTML (.html)
Generates a standalone HTML file with:
- Embedded Mermaid.js library
- Interactive diagram rendering
- No external dependencies

## License

This project is licensed under the GNU General Public License v3.0 or later. See the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For development:

```bash
# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/
isort src/

# Type checking
mypy src/
```

## Examples

### Basic Usage
```bash
# Analyze a Django project
mermaiden discover ./myproject --output django_classes.txt
mermaiden diagram django_classes.txt --output django_uml.md

# Analyze a FastAPI application
mermaiden discover ./app --output fastapi_classes.txt
mermaiden diagram fastapi_classes.txt --output fastapi_uml.html --html-title "FastAPI Architecture"
```

### Custom Configuration
```bash
# Use escaped identifiers for better compatibility
mermaiden diagram classes.txt --style escaped --namespace legacy
```

## Support

If you encounter any issues or have questions, please file an issue on the project repository or fork it to contribute.
