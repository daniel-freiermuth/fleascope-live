from PyQt6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import numpy as np
import sys

class Device:
    def __init__(self, name: str, plot_item: pg.PlotItem, x: np.ndarray, config_widget):
        self.name = name
        self.data = np.zeros_like(x)
        self.color = 'y'
        self.mode = 'Sinus'
        self.curve = plot_item.plot(pen=self.color, name=name)
        self.config_widget = config_widget

class DeviceConfigWidget(QtWidgets.QGroupBox):
    def __init__(self, device_name, on_delete, on_config_change):
        super().__init__(device_name)
        self.setLayout(QtWidgets.QFormLayout())

        self.color_button = QtWidgets.QPushButton()
        self.color_button.setFixedWidth(40)
        self.color_button.setStyleSheet("background-color: yellow")
        self.color_button.clicked.connect(self.pick_color)

        self.mode_dropdown = QtWidgets.QComboBox()
        self.mode_dropdown.addItems(["Sinus", "Random", "Flat"])
        self.mode_dropdown.currentTextChanged.connect(on_config_change)

        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setValue(10)
        self.slider.valueChanged.connect(on_config_change)

        self.delete_button = QtWidgets.QPushButton("Delete")
        self.delete_button.clicked.connect(on_delete)

        self.layout().addRow("Color:", self.color_button)
        self.layout().addRow("Mode:", self.mode_dropdown)
        self.layout().addRow("Noise:", self.slider)
        self.layout().addRow(self.delete_button)

    def pick_color(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self.color_button.setStyleSheet(f"background-color: {color.name()}")

    def get_color(self):
        return self.color_button.palette().button().color().name()

    def get_mode(self):
        return self.mode_dropdown.currentText()

    def get_noise(self):
        return max(self.slider.value() / 10, 0.3)

class LivePlotApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Live Plot with Device Manager")
        self.resize(1400, 800)

        self.devices = {}
        self.device_counter = 1
        self.x = np.arange(200)

        # === Main layout ===
        main_layout = QtWidgets.QHBoxLayout(self)

        # === Left: plotting ===
        self.plot_area = pg.GraphicsLayoutWidget()
        main_layout.addWidget(self.plot_area, stretch=4)
        self.plot_layouts = []

        # === Right: control panel ===
        self.sidebar_scroll = QtWidgets.QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_widget = QtWidgets.QWidget()
        self.sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar_widget)
        self.sidebar_scroll.setWidget(self.sidebar_widget)

        main_layout.addWidget(self.sidebar_scroll, stretch=1)

        self.add_device_button = QtWidgets.QPushButton("+ Add Device")
        self.add_device_button.clicked.connect(self.add_device)
        self.sidebar_layout.addWidget(self.add_device_button)
        self.sidebar_layout.addStretch()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(100)

    def add_device(self):
        name = f"Device {self.device_counter}"
        self.device_counter += 1

        if self.plot_layouts:
            self.plot_area.nextRow()
        plot = self.plot_area.addPlot(title=name)
        plot.showGrid(x=True, y=True)
        plot.setLabel('left', name)

        # Config widget
        config_widget = DeviceConfigWidget(
            name,
            on_delete=lambda: self.remove_device(name),
            on_config_change=lambda: self.apply_config(name)
        )
        self.sidebar_layout.insertWidget(self.sidebar_layout.count() - 2, config_widget)

        device = Device(name, plot, self.x, config_widget)
        self.devices[name] = device
        self.plot_layouts.append(plot)

    def remove_device(self, name):
        device = self.devices.pop(name, None)
        if not device:
            return

        device.curve.clear()
        device.config_widget.setParent(None)
        self.rebuild_plots()

    def rebuild_plots(self):
        self.plot_area.clear()
        self.plot_layouts.clear()
        for name, device in self.devices.items():
            self.plot_area.nextRow()
            plot = self.plot_area.addPlot(title=name)
            plot.showGrid(x=True, y=True)
            plot.setLabel('left', name)
            device.curve = plot.plot(pen=device.config_widget.get_color(), name=name)
            self.plot_layouts.append(plot)

    def apply_config(self, name):
        device = self.devices.get(name)
        if device:
            device.color = device.config_widget.get_color()
            device.mode = device.config_widget.get_mode()
            device.curve.setPen(device.color)

    def update_data(self):
        for device in self.devices.values():
            device.data = np.roll(device.data, -1)
            mode = device.config_widget.get_mode()
            scale = device.config_widget.get_noise()

            if mode == "Sinus":
                device.data[-1] = np.sin(np.sum(device.data))
            elif mode == "Random":
                device.data[-1] = np.random.normal(scale=scale)
            else:
                device.data[-1] = 0

            device.curve.setData(self.x, device.data)

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = LivePlotApp()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
