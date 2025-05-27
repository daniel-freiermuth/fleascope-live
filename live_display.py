from datetime import timedelta
import math
import threading
import time
from typing import Any, TypedDict
from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import numpy as np
import sys

from pyfleascope.trigger_config import BitState
from pyfleascope.flea_scope import AnalogTrigger, DigitalTrigger, FleaScope, Waveform

InputType = TypedDict('InputType', {
    'device': FleaScope,
    'trigger': AnalogTrigger | DigitalTrigger
})

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

        # === Initialize FleaScope devices ===
        self.inputs : list[InputType] = [
            {'device': FleaScope.connect('scope1'),
             # 'trigger': AnalogTrigger.start_capturing_when().auto(volts=2),
              'trigger': DigitalTrigger.start_capturing_when().is_matching(),
              },
            {'device': FleaScope.connect('scope2'), 'trigger': DigitalTrigger.start_capturing_when().is_matching()},
        ]

        self.inputs[0]['device'].set_waveform(Waveform.EKG, 1000)

        # === UI

        self.setWindowTitle("FleaScope Live Plot")
        self.resize(1000, 700)

        # === Main layout ===
        layout = QtWidgets.QVBoxLayout(self)

        # === Controls ===
        controls = QtWidgets.QHBoxLayout()
        layout.addLayout(controls)

        # -- Slider
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider_granularity = 10
        self.slider.setRange(-13*self.slider_granularity, 1*self.slider_granularity)
        self.slider.setValue(-55)
        self.slider.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                QtWidgets.QSizePolicy.Policy.Fixed)
        self.slider.valueChanged.connect(self.update_slider_display)
        self.slider_value_label = QtWidgets.QLabel("1.0")
        controls.addWidget(QtWidgets.QLabel("Time Frame"))
        controls.addWidget(self.slider_value_label)
        controls.addWidget(self.slider, stretch=2)

        self.update_slider_display(self.slider.value())

        # -- Drop-down
        self.dropdown = QtWidgets.QComboBox()
        self.dropdown.addItems(["x1", "x10"])
        self.dropdown.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed,
                                    QtWidgets.QSizePolicy.Policy.Fixed)
        controls.addWidget(QtWidgets.QLabel("Probe"))
        controls.addWidget(self.dropdown)

        # -- Checkboxes
        self.check_a = QtWidgets.QCheckBox("Show A")
        self.check_a.setChecked(True)
        self.check_b = QtWidgets.QCheckBox("Show B")
        self.check_b.setChecked(True)
        controls.addWidget(self.check_a)
        controls.addWidget(self.check_b)

        # === Buttons Row ===
        button_row = QtWidgets.QHBoxLayout()
        layout.addLayout(button_row)

        # -- Pause/Resume Button
        self.pause_btn = QtWidgets.QPushButton("Pause")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self.toggle_pause)
        button_row.addWidget(self.pause_btn)

        # -- Save Button
        self.save_btn = QtWidgets.QPushButton("Save Snapshot")
        self.save_btn.clicked.connect(self.save_snapshot)
        button_row.addWidget(self.save_btn)

        # Make them expand properly
        for btn in [self.pause_btn, self.save_btn]:
            btn.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)


        # === Plot Area ===
        self.plots = pg.GraphicsLayoutWidget()
        layout.addWidget(self.plots)

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
    app = QtWidgets.QApplication(sys.argv)
    win = LivePlotApp()
    win.show()
    status = app.exec()
    win.shutdown()
    sys.exit(status)

if __name__ == "__main__":
    main()
