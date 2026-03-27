"""Association example module."""

from typing import Literal

from pydantic import Field
from pydantic.dataclasses import dataclass

from ..subpckg_inheritance.subpckg_inheritance import DummyTypeEnum


@dataclass
class dummy_association:
    """Example class demonstrating association relationships."""

    type_: Literal[DummyTypeEnum.DummyAssociation] = Field(
        default=DummyTypeEnum.DummyAssociation,
        description="Dummy type discriminator",
    )
    name: str = Field(
        default="dummy-association",
        min_length=1,
        description="Association endpoint name",
    )
