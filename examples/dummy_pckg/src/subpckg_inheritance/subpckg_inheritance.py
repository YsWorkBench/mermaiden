from pydantic import Field
from pydantic.dataclasses import dataclass


@dataclass
class dummy_inheritance:
    identifier: int = Field(
        default=0,
        ge=0,
        description="Base inheritance identifier",
    )
