from datetime import timedelta
import math
import signal
import threading
import time
from typing import Any, Callable, TypedDict
from PyQt6 import QtWidgets, QtCore
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
    def shutdown(self):
        self.closing = True
        for input in self.inputs:
            input['device'].unblock()

    def toggle_pause(self):
        if self.pause_btn.isChecked():
            self.pause_btn.setText("Resume")
        else:
            self.pause_btn.setText("Pause")

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
        plot = self.plots.addPlot(title=f"Signal {hostname}")
        plot.showGrid(x=True, y=True)
        curve = plot.plot(pen='y')
        self.plots.nextRow()
        config_widget = self.side_panel.add_device_config()
        adapter = FleaScopeAdapter(device, config_widget, curve)
        config_widget.set_adapter(adapter)

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
    
    def slider_to_value(self, value: int) -> float:
        """Convert slider value to a time frame in seconds.

        :param value: Slider value, between -13 and 1.
        :returns: Time frame in seconds.
        """
        return 2**(value/self.slider_granularity)
    
    def update_slider_display(self, value: int):
        self.slider_value_label.setText(self.pretty_prefix(self.slider_to_value(value)) + "s")


    def __init__(self):
        super().__init__()
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

        self.plot_list = []
        self.curves = []

        def add_plot(hostname):
            plot = self.plots.addPlot(title=f"Signal {hostname}")
            plot.showGrid(x=True, y=True)
            self.plot_list.append(plot)
            self.curves.append( plot.plot(pen='y'))

        for input in self.inputs[:-1]:
            add_plot(input["device"].hostname)
            self.plots.nextRow()

        add_plot(self.inputs[-1]["device"].hostname)

        for plot in self.plot_list[1:]:
            plot.setXLink(self.plot_list[0])

        # === Data State ===
        self.index = np.arange(2000)
        self.ys: list[np.ndarray[Any, np.dtype[np.float64]]] = []
        for _ in self.inputs:
            self.ys.append(np.zeros(2000))

        # === Timer Update ===
        self.update_ts: list[threading.Thread] = []
        for i, input in enumerate(self.inputs):
            t = threading.Thread(
                target=self.update_data, args=(input, i), daemon=True
            )
            t.start()
            self.update_ts.append(t)

    def update_data(self, input: InputType, index: int):
        while not self.closing:
            if self.pause_btn.isChecked():
                time.sleep(0.3)
                continue
            scale = self.slider_to_value(self.slider.value())
            mode = self.dropdown.currentText()

            if mode == "x1":
                probe= input['device'].x1
            else:
                probe = input['device'].x10
            
            capture_time = timedelta(seconds=scale)

            data = probe.read( capture_time, trigger=input['trigger'])

            self.index = data.index
            self.ys[index] = data['bnc']
            self.curves[index].setData(self.index, self.ys[index])

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
