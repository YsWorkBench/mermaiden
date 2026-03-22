#pragma once
from . import *

class dummy(dummy_realisation):

    class dummy_composition:
        pass

    def MyABC(self):
        print("MyABC: Hello World")

    def __init__(
        self,
        association: dummy_association,
        aggregations: tuple(None, list[dummy_aggregation]) = None,
    ):
        super().__init__()
        self.association = association
        self.aggregations = aggregations
        self.composition = [dummy_composition() for _ in range(5)]


if __name__ == "__main__":
    instance1 = dummy_association()
    instances2 = [dummy_aggregation() for _ in range(5)]
    instance3 = dummy(instance1, instances2)
    instance3.MyABC()
