"""Aggregation example module."""

from typing import Literal

from pydantic import Field
from pydantic.dataclasses import dataclass

from ..subpckg_inheritance.subpckg_inheritance import DummyTypeEnum


@dataclass
class dummy_aggregation:
    """Example class demonstrating aggregation relationships."""

    type_: Literal[DummyTypeEnum.DummyAggregation] = Field(
        default=DummyTypeEnum.DummyAggregation,
        description="Dummy type discriminator",
    )
    index: int = Field(default=0, ge=0, description="Aggregation index")
