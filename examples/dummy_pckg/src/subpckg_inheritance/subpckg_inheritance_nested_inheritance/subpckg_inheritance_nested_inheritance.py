from pydantic import Field
from pydantic.dataclasses import dataclass

from ..subpckg_inheritance import dummy_inheritance
from ..subpckg_inheritance_nested_association import dummy_inheritance_nested_association


@dataclass
class dummy_inheritance_nested_inheritance(dummy_inheritance):
    link: dummy_inheritance_nested_association = Field(
        default_factory=dummy_inheritance_nested_association,
        description="Association to nested inheritance collaborator",
    )
    identifier_: int = Field(
        default=0,
        ge=0,
        description="Dummy UUID identifier",
    )
