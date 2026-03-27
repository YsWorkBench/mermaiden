"""Main dummy package module with Pydantic models and nested classes."""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import Field, ConfigDict
from pydantic.dataclasses import dataclass

from .subpckg_aggregation.subpckg_aggregation import dummy_aggregation
from .subpckg_association.subpckg_association import dummy_association
from .subpckg_inheritance.subpckg_inheritance import DummyTypeEnum
from .subpckg_inheritance.subpckg_inheritance_nested_association import (
    dummy_inheritance_nested_association,
)
from .subpckg_inheritance.subpckg_inheritance_nested_inheritance import (
    dummy_inheritance_nested_inheritance,
)
from .subpckg_realisation.subpckg_realisation import dummy_realisation


class dummy(dummy_realisation):
    """Main dummy class demonstrating composition and inheritance with Pydantic."""
    model_config = ConfigDict(extra='ignore')

    @dataclass
    class dummy_composition:
        """Example nested class for composition."""

        type_: Literal[DummyTypeEnum.DummyComposition] = Field(
            default=DummyTypeEnum.DummyComposition,
            description="Dummy type discriminator",
        )
        label: str = Field(default="composition", description="Composition label")


    type_: Literal[DummyTypeEnum.DummyPckg] = Field(
        default=DummyTypeEnum.DummyPckg,
        description="Dummy type discriminator",
    )
    association: dummy_association = Field(description="Association relationship")
    aggregations: Optional[list[dummy_aggregation]] = Field(
        default=None,
        description="List of aggregation relationships",
    )
    inheritance_link: Optional[dummy_inheritance_nested_inheritance] = Field(
        default=None,
        description="Nested inheritance relationship",
    )
    composition: list['dummy.dummy_composition'] = Field(
        default_factory=lambda: [dummy_composition() for _ in range(5)],
        description="Composition relationships",
    )

    def MyABC(self) -> str:
        """Implementation of abstract method."""
        return "MyABC: Hello World"


def main() -> int:
    """Main function to test Pydantic model instantiation."""
    association = dummy_association(name="primary-association")
    aggregations = [dummy_aggregation(index=i) for i in range(5)]
    nested_association = dummy_inheritance_nested_association(role="main-link")
    nested_inheritance = dummy_inheritance_nested_inheritance(
        link=nested_association,
        identifier=1,
        identifier_=99,
    )
    instance = dummy(
        association=association,
        aggregations=aggregations,
        inheritance_link=nested_inheritance,
    )

    # Type checking assertions
    assert isinstance(association, dummy_association)
    assert all(isinstance(item, dummy_aggregation) for item in aggregations)
    assert isinstance(nested_association, dummy_inheritance_nested_association)
    assert isinstance(nested_inheritance, dummy_inheritance_nested_inheritance)
    assert isinstance(instance, dummy)
    assert isinstance(instance.association, dummy_association)
    assert len(instance.aggregations) == 5
    assert isinstance(
        instance.inheritance_link.link, dummy_inheritance_nested_association
    )
    assert len(instance.composition) == 5

    message = instance.MyABC()
    assert isinstance(message, str)
    print(message)
    print("All dummy_pckg_pydantic objects instantiated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
