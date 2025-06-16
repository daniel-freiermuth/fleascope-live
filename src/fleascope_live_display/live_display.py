import math
import signal
from collections.abc import Callable
from typing import TypedDict
from PyQt6 import QtWidgets
from PyQt6.QtCore import QThread, pyqtSignal
import pyqtgraph as pg
import sys

from pyfleascope.flea_scope import AnalogTrigger, DigitalTrigger, FleaScope

from fleascope_live_display.toats import ToastManager
from fleascope_live_display.device_config_ui import DeviceConfigWidget
from fleascope_live_display.fleascope_adapter import FleaScopeAdapter

InputType = TypedDict('InputType', {
    'device': FleaScope,
    'trigger': AnalogTrigger | DigitalTrigger
})

class SidePanel(QtWidgets.QScrollArea):
    # QScrollArea -> QWidget -> QVBoxLayout
    def _add_device(self):
        self.add_device_button.setEnabled(False)
        self.add_device_button.setChecked(True)
        device_name = self.device_name_input.text().strip()
        if device_name:
            try:
                device = FleaScope.connect(device_name)
                self.toast_manager.show(f"Connected to {device_name}", level="success")
                self.device_name_input.clear()
                self.newDeviceCallback(device)
            except Exception as e:
                self.toast_manager.show(f"Failed to connect to {device_name}: {e}", level="error")
        self.add_device_button.setEnabled(True)
        self.add_device_button.setChecked(False)
    
    def add_device_config(self, title: str):
        widget = DeviceConfigWidget(title)
        self.layout.insertWidget(self.layout.count() - 2, widget)
        return widget

    def __init__(self, toast_manager: ToastManager, add_device: Callable[[FleaScope], None]):
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
        self.device_name_input = QtWidgets.QLineEdit()
        self.device_name_input.setPlaceholderText("Device name")
        self.add_device_button = QtWidgets.QPushButton("+ Add Device")
        self.add_device_button.clicked.connect(self._add_device)
        add_row.addWidget(self.device_name_input)
        add_row.addWidget(self.add_device_button)

        self.layout.addStretch()
        self.layout.addLayout(add_row)

class LivePlotApp(QtWidgets.QWidget):
    closing = False
    toast_signal = pyqtSignal(str, str)
    def shutdown(self):
        self.closing = True
        for input in self.inputs:
            input['device'].unblock()

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
    
    def add_device(self, device: FleaScope):
        hostname = device.hostname
        if any(filter(lambda d: d.getDevicename() == hostname, self.devices)):
            self.toast_manager.show(f"Device {hostname} already added", level="warning")
            return
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
