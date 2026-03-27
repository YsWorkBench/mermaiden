"""Nested inheritance example module."""

from typing import Literal

from pydantic import Field

from ..subpckg_inheritance import DummyTypeEnum, dummy_inheritance
from ..subpckg_inheritance_nested_association import dummy_inheritance_nested_association


class dummy_inheritance_nested_inheritance(dummy_inheritance):
    """Example class demonstrating nested inheritance relationships."""

    type_: Literal[DummyTypeEnum.DummyInheritanceNestedInheritance] = Field(
        default=DummyTypeEnum.DummyInheritanceNestedInheritance,
        description="Dummy type discriminator",
    )
    link: dummy_inheritance_nested_association = Field(
        default_factory=dummy_inheritance_nested_association,
        description="Association to nested inheritance collaborator",
    )
    identifier_: int = Field(
        default=0,
        ge=0,
        description="Dummy UUID identifier",
    )
