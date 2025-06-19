from datetime import timedelta
import logging
import threading
from typing import Literal, Self

from PyQt6.QtCore import QObject, QThread, QTimer, pyqtBoundSignal, pyqtSignal, pyqtSlot
from pandas import Index, Series
from serial import SerialException
from .device_config_ui import DeviceConfigWidget
from pyfleascope.flea_scope import FleaProbe, FleaScope, Waveform

class FleaScopeAdapter(QObject):
    data: pyqtSignal =pyqtSignal(Index, Series)
    delete_plot = pyqtSignal()
    def __init__(self, device: FleaScope, configWidget: DeviceConfigWidget, toast_manager: pyqtBoundSignal, adapter_list: list[Self]):
        super().__init__()
        self.signal_debounce_lock = threading.Lock()
        self.target_waveform: tuple[Waveform, int] | None = None
        self.configWidget = configWidget
        self.device = device
        self.toast_manager = toast_manager
        self.state : Literal['running'] | Literal['closing'] | Literal['paused'] = "running"
        self.adapter_list = adapter_list
        self.calibration_pending = False

    def is_closing(self) -> bool:
        return self.state == "closing"

    def step(self):
        logging.debug(f"Stepping data update for {self.device.hostname} as {QThread.currentThread().objectName()}")
        if not self.is_closing():
            self.configWidget.set_transportview('running')
            QTimer.singleShot(0, self.update_data)

    def resume(self):
        logging.debug(f"Starting data update thread for {self.device.hostname} as {QThread.currentThread().objectName()}")
        if not self.is_closing():
            self.configWidget.set_transportview('running')
            self.state = "running"
            QTimer.singleShot(0, self.update_data)

    @pyqtSlot()
    def update_data(self):
        scale = self.configWidget.getTimeFrame()
        probe = self.getProbe()
        capture_time = timedelta(seconds=scale)
        trigger = self.configWidget.getTrigger()
        delay = timedelta(seconds=self.configWidget.getDelayValue())
        try:
            data = probe.read( capture_time, trigger, delay)
            if data.size != 0:
                self.data.emit(data.index, data['bnc'])
        except SerialException as e:
            # SerialException -> Stale
            logging.error(f"SerialException while reading data from {self.device.hostname}: {e}")
            self.toast_manager.emit(f"Lost connection to {self.device.hostname}", "error")
            self.state = "closing"
            raise e
        except ValueError as e:
            # ValueError -> Pause
            logging.error(f"ValueError while reading data from {self.device.hostname}: {e}")
            self.toast_manager.emit(f"Error reading data from {self.device.hostname}: {e}", "error")
            self.state = "paused"
        except Exception as e:
            logging.error(f"Unexpected error while reading data from {self.device.hostname}: {e}")
            self.toast_manager.emit(f"Unexpected error reading data from {self.device.hostname}: {e}", "error")
            self.state = "paused"
            raise e
        if self.state == "running":
            QTimer.singleShot(0, self.update_data)
        else:
            self.configWidget.set_transportview('paused')

    
    def removeDevice(self):
        logging.debug(f"Removing device {self.device.hostname} as {QThread.currentThread().objectName()}")
        self.state = "closing"
        self.configWidget.removeDevice()
        self.adapter_list.remove(self)
        self.delete_plot.emit()
    
    def pause(self):
        if not self.is_closing():
            self.state = "paused"
            self.device.unblock()

    def capture_settings_changed(self):
        logging.debug("Capture settings changed, restarting data update thread")
        self.device.unblock()
    
    def getProbe(self) -> FleaProbe:
        if self.configWidget.getProbe() == "x1":
            return self.device.x1
        else:
            return self.device.x10
        
    def send_cal_0_signal(self):
        logging.debug(f"Sending signal to 0V for {self.device.hostname} as {QThread.currentThread().objectName()}")
        with self.signal_debounce_lock:
            if self.calibration_pending:
                return
            self.calibration_pending = True
        QTimer.singleShot(0, self.cal_0)
        self.device.unblock()
    
    @pyqtSlot()
    def cal_0(self):
        logging.debug(f"Calibrating to 0V for {self.device.hostname} as {QThread.currentThread().objectName()}")
        with self.signal_debounce_lock:
            self.calibration_pending = False
        try:
            self.getProbe().calibrate_0()
            self.toast_manager.emit("Calibrated to 0V", "success")
        except ValueError:
            self.toast_manager.emit("Signal too unstable for calibration", "failure")
    
    def send_cal_3v3_signal(self):
        logging.debug(f"Calibrating to 3.3V for {self.device.hostname} as {QThread.currentThread().objectName()}")
        with self.signal_debounce_lock:
            if self.calibration_pending:
                return
            self.calibration_pending = True
        QTimer.singleShot(0, self.cal_3v3)
        self.device.unblock()

    @pyqtSlot()
    def cal_3v3(self):
        logging.debug(f"Calibrating to 3.3V for {self.device.hostname} as {QThread.currentThread().objectName()}")
        with self.signal_debounce_lock:
            self.calibration_pending = False
        try:
            self.getProbe().calibrate_3v3()
            self.toast_manager.emit("Calibrated to 3.3V", "success")
        except ValueError:
            self.toast_manager.emit("Signal too unstable for calibration", "failure")
        
    @pyqtSlot()
    def storeCalibration(self):
        logging.debug(f"Storing calibration for {self.device.hostname} as {QThread.currentThread().objectName()}")
        try:
            self.device.x1.write_calibration_to_flash()
            self.device.x10.write_calibration_to_flash()
            self.toast_manager.emit("Calibration stored", "success")
        except ValueError:
            self.toast_manager.emit("Failed to store calibration", "failure")

    def set_waveform(self, waveform: Waveform, hz: int):
        logging.debug(f"Sending signal waveform to {waveform.name} at {hz}Hz as {QThread.currentThread().objectName()}")
        with self.signal_debounce_lock:
            am_I_first_update = self.target_waveform is None
            self.target_waveform = (waveform, hz)
        if am_I_first_update:
            QTimer.singleShot(0,self._set_waveform)
            self.device.unblock()

    @pyqtSlot()
    def _set_waveform(self):
        with self.signal_debounce_lock:
            assert self.target_waveform is not None, "No target waveform set"
            waveform, hz = self.target_waveform
            logging.debug(f"Setting waveform to {waveform.name} at {hz}Hz as {QThread.currentThread().objectName()}")
            self.target_waveform = None
        self.device.set_waveform(waveform, hz)
    
    def getDevicename(self) -> str:
        return self.device.hostname
    
    def shutdown(self):
        self.state = "closing"
        self.device.unblock()
