from __future__ import annotations

from typing import Literal, Optional

from subpckg_aggregation.subpckg_aggregation import dummy_aggregation
from subpckg_association.subpckg_association import dummy_association
from subpckg_inheritance.subpckg_inheritance_nested_association import (
    dummy_inheritance_nested_association,
)
from subpckg_inheritance.subpckg_inheritance_nested_inheritance import (
    dummy_inheritance_nested_inheritance,
)
from subpckg_inheritance.subpckg_inheritance import DummyTypeEnum
from subpckg_realisation.subpckg_realisation import dummy_realisation


class dummy(dummy_realisation):
    class dummy_composition:
        type_: Literal[DummyTypeEnum.DummyComposition] = DummyTypeEnum.DummyComposition

        def __init__(self, label: str = "composition") -> None:
            self.label = label

    type_: Literal[DummyTypeEnum.DummyPckg] = DummyTypeEnum.DummyPckg

    def MyABC(self) -> str:
        return "MyABC: Hello World"

    def __init__(
        self,
        association: dummy_association,
        aggregations: Optional[list[dummy_aggregation]] = None,
        inheritance_link: Optional[dummy_inheritance_nested_inheritance] = None,
    ) -> None:
        super().__init__()
        if aggregations is None:
            aggregations = []

        self.association = association
        self.aggregations = aggregations
        self.inheritance_link = inheritance_link
        self.composition = [dummy.dummy_composition() for _ in range(5)]


def main() -> int:
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
    print("All dummy_pckg objects instantiated successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
