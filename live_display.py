from datetime import timedelta
import math
import signal
import threading
import time
from typing import Any, Callable, TypedDict
from PyQt6 import QtWidgets, QtCore
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QToolButton, QWidget, QGridLayout, QLabel, QComboBox, QColorDialog, QCheckBox, QPushButton, QVBoxLayout
import pyqtgraph as pg
import numpy as np
import sys

from pyfleascope.trigger_config import BitState
from pyfleascope.flea_scope import AnalogTrigger, DigitalTrigger, FleaProbe, FleaScope, Waveform

from toats import ToastManager
from device_config_ui import DeviceConfigWidget, IFleaScopeAdapter
from fleascope_adapter import FleaScopeAdapter

InputType = TypedDict('InputType', {
    'device': FleaScope,
    'trigger': AnalogTrigger | DigitalTrigger
})

class SidePanel(QtWidgets.QScrollArea):
    # QScrollArea -> QWidget -> QVBoxLayout
    def _add_device(self):
        self.add_device_button.setEnabled(False)
        self.add_device_button.setChecked(True)
        self.setFixedWidth(360)
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
    
    def add_device_config(self):
        widget = DeviceConfigWidget()
        self.layout.insertWidget(self.layout.count() - 2, widget)
        return widget

    def __init__(self, toast_manager: ToastManager, add_device: Callable[[FleaScope], None]):
        super().__init__()
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
        config_widget = self.side_panel.add_device_config()

        adapter = FleaScopeAdapter(device, config_widget, self.toast_signal, self.devices)
        adapter.delete_plot.connect(lambda: self.plots.removeItem(plot))
        adapter.data.connect(curve.setData)

        config_widget.set_adapter(adapter)
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
