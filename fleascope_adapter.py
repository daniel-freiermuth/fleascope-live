from datetime import timedelta
import logging
import threading
import time
from typing import Literal
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
        self.state : Literal['running'] | Literal['closing'] | Literal['step'] | Literal['paused'] = "running"

        self.t = threading.Thread(
            target=self.update_data, daemon=True
        )
        self.t.start()
    
    def is_closing(self) -> bool:
        return self.state == "closing"

    def update_data(self):
        while not self.is_closing():
            if self.state == "paused":
                time.sleep(0.3)
                continue
                
            scale = self.configWidget.getTimeFrame()
            probe = self.getProbe()
            capture_time = timedelta(seconds=scale)
            trigger = self.configWidget.getTrigger()
            data = probe.read( capture_time, trigger)
            self.curve.setData(data.index, data['bnc'])
    
    def pause(self):
        if not self.is_closing():
            self.state = "paused"
            self.device.unblock()

    def start(self):
        if not self.is_closing():
            self.state = "running"

    def capture_settings_changed(self):
        logging.debug("Capture settings changed, restarting data update thread")
        self.device.unblock()
    
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
    
    def shutdown(self):
        self.state = "closing"
        self.device.unblock()
        self.t.join()