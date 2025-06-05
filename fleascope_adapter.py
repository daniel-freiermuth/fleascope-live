from device_config_ui import DeviceConfigWidget, IFleaScopeAdapter
from pyfleascope.flea_scope import FleaProbe, FleaScope
from toats import ToastManager
import pyqtgraph as pg

class FleaScopeAdapter(IFleaScopeAdapter):
    def __init__(self, device: FleaScope, configWidget: DeviceConfigWidget, curve: pg.PlotDataItem, toast_manager: ToastManager):
        self.configWidget = configWidget
        self.device = device
        self.curve = curve
        self.toast_manager = toast_manager
    
    def pause(self):
        pass

    def start(self):
        pass

    def settings_changed(self):
        pass
    
    def getProbe(self) -> FleaProbe:
        if self.configWidget.getProble() == "x1":
            return self.device.x1
        else:
            return self.device.x10
    
    def cal_0(self):
        self.getProbe().calibrate_0()
        self.toast_manager.show("Calibrated to 0V", level="success")

    def cal_3v3(self):
        self.getProbe().calibrate_3v3()
        self.toast_manager.show("Calibrated to 3.3V", level="success")
    
    def getDevicename(self) -> str:
        return self.device.hostname
