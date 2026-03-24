from typing import Optional

from pydantic import Field

from ..subpckg_inheritance import dummy_inheritance
from ..subpckg_inheritance_nested_association import dummy_inheritance_nested_association

class dummy_inheritance_nested_inheritance(dummy_inheritance):
    link: Optional[dummy_inheritance_nested_association] = Field(description = '', default = dummy_inheritance_nested_association)
