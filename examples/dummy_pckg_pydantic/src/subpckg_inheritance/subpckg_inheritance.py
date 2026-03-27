"""Inheritance example module."""

from enum import Enum
from typing import Literal

from pydantic import Field, BaseModel


class OrderedEnum(Enum):
    """Enum base class supporting ordering comparisons by value."""

    def __lt__(self, other: object) -> bool:
        if self.__class__ is other.__class__:
            return bool(self.value < other.value)
        return NotImplemented

    def __le__(self, other: object) -> bool:
        if self.__class__ is other.__class__:
            return bool(self.value <= other.value)
        return NotImplemented

    def __gt__(self, other: object) -> bool:
        if self.__class__ is other.__class__:
            return bool(self.value > other.value)
        return NotImplemented

    def __ge__(self, other: object) -> bool:
        if self.__class__ is other.__class__:
            return bool(self.value >= other.value)
        return NotImplemented


class DummyTypeEnum(OrderedEnum):
    """Enum describing class-specific dummy package kinds."""

    DummyPckg = 1
    DummyComposition = 2
    DummyAggregation = 3
    DummyAssociation = 4
    DummyInheritance = 5
    DummyInheritanceNestedAssociation = 6
    DummyInheritanceNestedInheritance = 7
    DummyRealisation = 8


class dummy_inheritance(BaseModel):
    """Example class demonstrating inheritance relationships."""

    type_: Literal[DummyTypeEnum.DummyInheritance] = Field(
        default=DummyTypeEnum.DummyInheritance,
        description="Dummy type discriminator",
    )
    identifier: int = Field(
        default=0,
        ge=0,
        description="Base inheritance identifier",
    )
