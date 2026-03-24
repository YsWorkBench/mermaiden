#pragma once
from typing import Optional, List

from subpckg_realisation.subpckg_realisation import dummy_realisation
from subpckg_association.subpckg_association import dummy_association
from subpckg_aggregation.subpckg_aggregation import dummy_aggregation

class dummy(dummy_realisation):

    class dummy_composition:
        pass

    def MyABC(self):
        print("MyABC: Hello World")

    def __init__(
        self,
        association: dummy_association,
        aggregations: Optional[List[dummy_aggregation]] = None,
    ):
        super().__init__()
        self.association = association
        self.aggregations = aggregations
        self.composition = [dummy.dummy_composition() for _ in range(5)]


if __name__ == "__main__":
    instance1 = dummy_association()
    instances2 = [dummy_aggregation() for _ in range(5)]
    instance3 = dummy(instance1, instances2)
    instance3.MyABC()
