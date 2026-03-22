from abc import ABC, abstractmethod
from .subpckg_inheritance import dummy_inheritance

class dummy_realisation(dummy_inheritance, ABC):
    
    @abstractmethod
    def MyABC(self):
        pass