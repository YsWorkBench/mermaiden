# Dummy Package with Pydantic Models

This is a Pydantic-enhanced version of the `dummy_pckg` example, demonstrating how Pydantic models can be used for UML diagram generation.

## Structure

```
src/
├── __init__.py
├── dummy_pckg.py                    # Main Pydantic models
├── subpckg_aggregation/
│   ├── __init__.py
│   └── subpckg_aggregation.py       # Aggregation Pydantic model
├── subpckg_association/
│   ├── __init__.py
│   └── subpckg_association.py       # Association Pydantic model
├── subpckg_inheritance/
│   ├── __init__.py
│   ├── subpckg_inheritance.py
│   ├── subpckg_inheritance_nested_association/
│   │   ├── __init__.py
│   │   └── subpckg_inheritance_nested_association.py
│   └── subpckg_inheritance_nested_inheritance/
│       ├── __init__.py
│       └── subpckg_inheritance_nested_inheritance.py
└── subpckg_realisation/
    ├── __init__.py
    └── subpckg_realisation.py       # Abstract base class
```

## Key Differences from Original

1. **Pydantic Integration**: All data classes now use `@pydantic.dataclass` decorator
2. **Field Validation**: Added `pydantic.Field` with validation rules and descriptions
3. **Type Safety**: Enhanced type annotations and validation
4. **Default Factories**: Used `default_factory` for complex default values

## Usage

```python
# Run the test script
python src/dummy_pckg.py

# Generate UML diagram
mermaidern discover src --output dummy_pckg_pydantic.txt
mermaidern diagram dummy_pckg_pydantic.txt --output dummy_pckg_pydantic_UML.md
```

## Pydantic Features Demonstrated

- **Data Validation**: Field constraints (min_length, ge=0)
- **Default Values**: Smart defaults and default factories
- **Type Hints**: Comprehensive type annotations
- **Field Descriptions**: Detailed field documentation
- **Inheritance**: Pydantic dataclass inheritance patterns
- **Abstract Classes**: Integration with Python's ABC

This version showcases how modern Python data validation libraries can enhance UML diagram generation with rich metadata and validation rules.
