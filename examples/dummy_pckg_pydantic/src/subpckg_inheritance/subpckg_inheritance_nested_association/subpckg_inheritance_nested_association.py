"""Nested association example module."""

from typing import Literal

from pydantic import Field

from ...subpckg_inheritance.subpckg_inheritance import DummyTypeEnum


class dummy_inheritance_nested_association:
    """Example class demonstrating nested association relationships."""

    type_: Literal[DummyTypeEnum.DummyInheritanceNestedAssociation] = Field(
        default=DummyTypeEnum.DummyInheritanceNestedAssociation,
        description="Dummy type discriminator",
    )
    role: str = Field(
        default="nested-association",
        min_length=1,
        description="Nested association role",
    )
