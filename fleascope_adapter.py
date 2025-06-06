from datetime import timedelta
import logging
import threading
import time
from typing import Callable, Literal, Self

from PyQt6.QtCore import QObject, QTimer, pyqtBoundSignal, pyqtSignal, pyqtSlot
from pandas import Index, Series
from device_config_ui import DeviceConfigWidget, IFleaScopeAdapter
from pyfleascope.flea_scope import FleaProbe, FleaScope, Waveform
from toats import ToastManager
import pyqtgraph as pg

class FleaScopeAdapter(QObject, IFleaScopeAdapter):
    data: pyqtSignal =pyqtSignal(Index, Series)
    delete_plot = pyqtSignal()
    def __init__(self, device: FleaScope, configWidget: DeviceConfigWidget, toast_manager: pyqtBoundSignal, adapter_list: list[Self]):
        super().__init__()
        self.deviceLock  = threading.Lock()
        self.queuelock = threading.Lock()
        self.waveformlock = threading.Lock()
        self.target_waveform: tuple[Waveform, int] | None = None
        self.commandWaiting = False
        self.configWidget = configWidget
        self.device = device
        self.toast_manager = toast_manager
        self.state : Literal['running'] | Literal['closing'] | Literal['step'] | Literal['paused'] = "running"
        self.adapter_list = adapter_list

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
            if self.commandWaiting:
                time.sleep(0.1)
                continue
            self.deviceLock.acquire()
            scale = self.configWidget.getTimeFrame()
            probe = self.getProbe()
            capture_time = timedelta(seconds=scale)
            trigger = self.configWidget.getTrigger()
            try:
                data = probe.read( capture_time, trigger)
            except:
                self.deviceLock.release()
                self.toast_manager.emit(f"Lost connection to {self.device.hostname}", "error")
                self.removeDevice()
                break
            if data.size != 0:
                self.data.emit(data.index, data['bnc'])
            self.deviceLock.release()
    
    def removeDevice(self):
        logging.debug(f"Removing device {self.device.hostname}")
        self.state = "closing"
        self.configWidget.removeDevice()
        self.adapter_list.remove(self)
        self.delete_plot.emit()
    
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
    
    def grabDeviceLock(self):
        self.queuelock.acquire()
        self.commandWaiting = True
        self.capture_settings_changed()
        self.deviceLock.acquire()
        self.commandWaiting = False
        self.queuelock.release()
    
    @pyqtSlot()
    def cal_0(self):
        self.grabDeviceLock()
        self.getProbe().calibrate_0()
        self.deviceLock.release()
        self.toast_manager.emit("Calibrated to 0V", "success")

    @pyqtSlot()
    def cal_3v3(self):
        self.grabDeviceLock
        self.getProbe().calibrate_3v3()
        self.deviceLock.release()
        self.toast_manager.emit("Calibrated to 3.3V", "success")

    @pyqtSlot(Waveform, int)
    def set_waveform(self, waveform: Waveform, hz: int):
        logging.debug(f"Setting waveform to {waveform.name} at {hz}Hz")
        self.waveformlock.acquire()
        am_I_first_update = self.target_waveform is None
        self.target_waveform = (waveform, hz)
        self.toast_manager.emit(f"Setting waveform to {waveform.name} at {hz}Hz", "info")
        self.waveformlock.release()
        if not am_I_first_update:
            return
        self.grabDeviceLock()
        self.waveformlock.acquire()
        waveform, hz = self.target_waveform
        self.target_waveform = None
        self.waveformlock.release()
        self.device.set_waveform(waveform, hz)
        self.deviceLock.release()
    
    def getDevicename(self) -> str:
        return self.device.hostname
    
    def shutdown(self):
        self.state = "closing"
        self.device.unblock()
        self.t.join()