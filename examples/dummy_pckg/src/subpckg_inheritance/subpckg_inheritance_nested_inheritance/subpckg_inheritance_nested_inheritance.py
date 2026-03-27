from typing import Literal, Annotated

from pydantic import Field
from pydantic.dataclasses import dataclass

from ..subpckg_inheritance import DummyTypeEnum, dummy_inheritance
from ..subpckg_inheritance_nested_association import dummy_inheritance_nested_association


@dataclass
class dummy_inheritance_nested_inheritance(dummy_inheritance):
    type_: Literal[DummyTypeEnum.DummyInheritanceNestedInheritance] = Field(
        default=DummyTypeEnum.DummyInheritanceNestedInheritance,
        description="Dummy type discriminator",
    )
    link: Annotated[dummy_inheritance_nested_association, 'dummy annotation to see failure'] = Field(
        default_factory=dummy_inheritance_nested_association,
        description="Association to nested inheritance collaborator",
    )
    identifier_: Annotated[int, 'must be positive or not, not sure'] = Field(
        default=0,
        ge=0,
        description="Dummy UUID identifier",
    )
