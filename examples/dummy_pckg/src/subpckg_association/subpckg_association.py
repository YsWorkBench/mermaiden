from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class dummy_association:
    name: str = Field(
        default="dummy-association",
        min_length=1,
        description="Association endpoint name",
    )
