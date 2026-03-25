from pydantic import Field
from pydantic.dataclasses import dataclass

@dataclass
class dummy_aggregation:
    index: int = Field(default=0, ge=0, description="Aggregation index")
