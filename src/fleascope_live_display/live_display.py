import math
import signal
from collections.abc import Callable
from typing import TypedDict
from PyQt6 import QtWidgets
from PyQt6.QtCore import QObject, QThread, pyqtSignal
from PyQt6.QtWidgets import QStyle
import pyqtgraph as pg
import sys

from pyfleascope.flea_scope import AnalogTrigger, DigitalTrigger, FleaScope, FleaConnector

from .toasts import ToastManager
from .device_config_ui import DeviceConfigWidget
from .fleascope_adapter import FleaScopeAdapter

InputType = TypedDict('InputType', {
    'device': FleaScope,
    'trigger': AnalogTrigger | DigitalTrigger
})

class AvailableDevicesWorker(QObject):
    finished = pyqtSignal(list)

    def run(self):
        values = [d.name for d in FleaConnector.get_available_devices()]
        self.finished.emit(values)


class SidePanel(QtWidgets.QScrollArea):
    # QScrollArea -> QWidget -> QVBoxLayout
    def _add_device(self):
        self.add_device_button.setEnabled(False)
        self.add_device_button.setChecked(True)
        device_name = self.device_name_input.currentText().strip()
        if device_name:
            try:
                self.newDeviceCallback(device_name)
                self.device_name_input.removeItem(self.device_name_input.currentIndex())
            except Exception as e:
                self.toast_manager.show(f"Failed to connect to {device_name}: {e}", level="error")
        self.add_device_button.setEnabled(True)
        self.add_device_button.setChecked(False)
    
    def add_device_config(self, title: str):
        widget = DeviceConfigWidget(title)
        self.layout.insertWidget(self.layout.count() - 2, widget)
        return widget

    def __init__(self, toast_manager: ToastManager, add_device: Callable[[str], None]):
        super().__init__()
        self.setFixedWidth(360)
        self.setWidgetResizable(True)
        widget = QtWidgets.QWidget()
        self.layout = QtWidgets.QVBoxLayout(widget)
        self.setWidget(widget)
        self.newDeviceCallback = add_device

        self.toast_manager = toast_manager

        # === Device name input + add button ===
        add_row = QtWidgets.QHBoxLayout()
        self.device_name_input = QtWidgets.QComboBox()
        self.device_name_input.setEditable(True)
        self.device_name_input.setPlaceholderText("Device name")

        self.button = QtWidgets.QToolButton()
        self.button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
        self.button.clicked.connect(self.load_items)

        self.add_device_button = QtWidgets.QPushButton("+ Add Device")
        self.add_device_button.clicked.connect(self._add_device)

        add_row.addWidget(self.device_name_input)
        add_row.addWidget(self.button)
        add_row.addWidget(self.add_device_button)
        self.load_items()

        self.layout.addStretch()
        self.layout.addLayout(add_row)

    def load_items(self):
        self.button.setEnabled(False)

        self.thread = QThread()
        self.worker = AvailableDevicesWorker()
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.populate_combo)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.start()

    def populate_combo(self, items):
        self.device_name_input.clear()
        self.device_name_input.addItems(items)
        self.device_name_input.setCurrentIndex(0)
        self.button.setEnabled(True)


class LivePlotApp(QtWidgets.QWidget):
    toast_signal = pyqtSignal(str, str)
    def shutdown(self):
        for adapter in self.devices:
            adapter.shutdown()

    def pretty_prefix(self, x: float):
        """Give the number an appropriate SI prefix.

        :param x: Too big or too small number.
        :returns: String containing a number between 1 and 1000 and SI prefix.
        """
        if x == 0:
            return "0  "

        l = math.floor(math.log10(abs(x)))

        div, mod = divmod(l, 3)
        return "%.3g %s" % (x * 10**(-l + mod), " kMGTPEZYyzafpnµm"[div])
    
    def add_device(self, hostname: str):
        if any(filter(lambda d: d.getDevicename() == hostname, self.devices)):
            self.toast_manager.show(f"Device {hostname} already added", level="warning")
            return
        device = FleaScope.connect(hostname)
        self.toast_manager.show(f"Connected to {hostname}", level="success")
        plot: pg.PlotItem = self.plots.addPlot(title=f"Signal {hostname}")
        plot.showGrid(x=True, y=True)
        curve = plot.plot(pen='y')
        self.plots.nextRow()
        config_widget = self.side_panel.add_device_config(device.hostname)

        adapter = FleaScopeAdapter(device, config_widget, self.toast_signal, self.devices)
        adapter.delete_plot.connect(lambda: self.plots.removeItem(plot))
        adapter.data.connect(curve.setData)

        workerThread = QThread()
        adapter.moveToThread(workerThread)
        workerThread.started.connect(adapter.update_data)
        workerThread.setObjectName(f"AdapterThread-{hostname}")
        workerThread.start()
        self.worker_threads.append(workerThread)

        config_widget.cal_0v_sig.connect(lambda: adapter.send_cal_0_signal())
        config_widget.cal_3v3_sig.connect(lambda: adapter.send_cal_3v3_signal())
        config_widget.waveform_changed.connect(lambda waveform, hz: adapter.set_waveform(waveform, hz))
        config_widget.trigger_settings_changed_sig.connect(lambda: adapter.capture_settings_changed())
        config_widget.remove_device_sig.connect(lambda: adapter.removeDevice())
        config_widget.save_cal_sig.connect(adapter.storeCalibration)
        config_widget.pause_sig.connect(lambda: adapter.pause())
        config_widget.resume_sig.connect(adapter.resume)
        config_widget.step_sig.connect(adapter.step)
        config_widget.rename_device_sig.connect(adapter.set_hostname)

        self.devices.append(adapter)

    def save_snapshot(self):
        filename = QtWidgets.QFileDialog.getSaveFileName(self, "Save Plot", "", "CSV Files (*.csv)")[0]
        if filename:
            import pandas as pd
            df = pd.DataFrame({
                "x": self.x,
                # "A": self.y_a,
                # "B": self.y_b
            })
            df.to_csv(filename, index=False)
            print(f"Saved to {filename}")
    
    def __init__(self):
        super().__init__()
        self.toast_signal.connect(lambda msg, level: self.toast_manager.show(msg, level=level))
        self.toast_manager = ToastManager(self)
        self.devices: list[FleaScopeAdapter] = []

        self.setWindowTitle("FleaScope Live Plot")
        self.resize(1000, 700)
        layout = QtWidgets.QHBoxLayout(self)

        # === Plot Area ===
        self.plots = pg.GraphicsLayoutWidget()
        layout.addWidget(self.plots)

        self.side_panel = SidePanel(self.toast_manager, self.add_device)
        layout.addWidget(self.side_panel)

        # plot.setXLink(self.plot_list[0])
        self.worker_threads = []


def main():
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app = QtWidgets.QApplication(sys.argv)
    win = LivePlotApp()
    win.show()
    status = app.exec()
    win.shutdown()
    sys.exit(status)

if __name__ == "__main__":
    main()
