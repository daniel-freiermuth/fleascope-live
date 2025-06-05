from PyQt6.QtWidgets import QGroupBox

class IFleaScopeAdapter:
    pass

class DeviceConfigWidget(QGroupBox):
    def set_adapter(self, adapter: IFleaScopeAdapter):
        self.adapter = adapter

