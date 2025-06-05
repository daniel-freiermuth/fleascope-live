from abc import abstractmethod
from PyQt6.QtWidgets import QGroupBox

class IFleaScopeAdapter:
    @abstractmethod
    def getDevicename(self) -> str:
        return NotImplemented


class DeviceConfigWidget(QGroupBox):
    def set_adapter(self, adapter: IFleaScopeAdapter):
        self.adapter = adapter
        self.setTitle(adapter.getDevicename())

