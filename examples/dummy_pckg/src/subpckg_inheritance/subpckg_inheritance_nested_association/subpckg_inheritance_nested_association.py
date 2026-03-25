from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class dummy_inheritance_nested_association:
    role: str = Field(
        default="nested-association",
        min_length=1,
        description="Nested association role",
    )
