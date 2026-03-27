"""Realisation example module."""

from abc import ABC, abstractmethod
from typing import Literal

from ..subpckg_inheritance.subpckg_inheritance import DummyTypeEnum, dummy_inheritance


class dummy_realisation(dummy_inheritance, ABC):
    """Example class demonstrating interface realisation."""

    type_: Literal[DummyTypeEnum.DummyRealisation] = DummyTypeEnum.DummyRealisation

    @abstractmethod
    def MyABC(self) -> str:
        """Example abstract method."""
        raise NotImplementedError
