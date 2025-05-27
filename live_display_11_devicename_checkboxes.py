from PyQt6 import QtWidgets, QtCore, QtGui
import pyqtgraph as pg
import numpy as np
import sys

class Toast(QtWidgets.QLabel):
    closed = QtCore.pyqtSignal()

    COLORS = {
        "success": "#4caf50",
        "warning": "#ffb300",
        "error": "#e53935",
        "info": "#333"
    }

    ICONS = {
        "success": "✅",
        "warning": "⚠️",
        "error": "❌",
        "info": "ℹ️"
    }

    def __init__(self, parent, message, duration, stack_index, level="info"):
        super().__init__(parent)
        icon = self.ICONS.get(level, "")
        color = self.COLORS.get(level, "#333")

        self.setText(f"{icon} {message}")
        self.setStyleSheet(f"""
            background-color: {color};
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-weight: bold;
        """)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setWindowFlags(QtCore.Qt.WindowType.FramelessWindowHint |
                            QtCore.Qt.WindowType.ToolTip)
        self.adjustSize()
        self.stack_index = stack_index
        self.reposition(stack_index)
        self.show()

        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.close)
        self.timer.start(duration)

    def reposition(self, stack_index):
        parent_geo = self.parent().geometry()
        x = parent_geo.width() - self.width() - 20
        y = parent_geo.height() - self.height() - 20 - stack_index * (self.height() + 10)
        self.move(x, y)

    def mousePressEvent(self, event):
        self.close()

    def close(self):
        if self.isVisible():
            super().close()
            self.closed.emit()

class ToastManager:
    def __init__(self, parent):
        self.parent = parent
        self.toasts = []

    def show(self, message, duration=3000, level="info"):
        toast = Toast(self.parent, message, duration, len(self.toasts), level)
        toast.closed.connect(lambda: self._remove_toast(toast))
        self.toasts.append(toast)

    def _remove_toast(self, toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            self._reposition_toasts()

    def _reposition_toasts(self):
        for i, toast in enumerate(self.toasts):
            toast.reposition(i)

class Device:
    def __init__(self, name: str, plot_item: pg.PlotItem, x: np.ndarray, config_widget):
        self.name = name
        self.data = np.zeros_like(x, dtype=float)
        self.color = 'y'
        self.mode = 'Sinus'
        self.curve = plot_item.plot(pen=self.color, name=name)
        self.config_widget = config_widget
        self.step = 0

class DeviceConfigWidget(QtWidgets.QGroupBox):
    def __init__(self, device_name, on_delete, on_config_change):
        super().__init__()
        self.setTitle(device_name)
        self.setStyleSheet("DeviceConfigWidget { border: 1px solid #ccc; border-radius: 6px; margin-top: 20px; }")

        layout = QtWidgets.QGridLayout()
        self.setLayout(layout)

        # 'X' icon button in the corner
        self.delete_button = QtWidgets.QToolButton()
        self.delete_button.setIcon(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_TitleBarCloseButton))
        self.delete_button.setToolTip("Remove device")
        self.delete_button.setStyleSheet("border: none;")
        self.delete_button.clicked.connect(on_delete)

        layout.addWidget(self.delete_button, 0, 2, alignment=QtCore.Qt.AlignmentFlag.AlignRight)

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

        layout.addWidget(QtWidgets.QLabel("Color:"), 1, 0)
        layout.addWidget(self.color_button, 1, 1)
        layout.addWidget(QtWidgets.QLabel("Mode:"), 2, 0)
        layout.addWidget(self.mode_dropdown, 2, 1)
        layout.addWidget(QtWidgets.QLabel("Noise:"), 3, 0)
        layout.addWidget(self.slider, 3, 1, 1, 2)

        # 3x3 checkbox grid
        self.checkbox_grid = []
        grid_widget = QtWidgets.QWidget()
        grid_layout = QtWidgets.QGridLayout(grid_widget)
        for i in range(3):
            row = []
            for j in range(3):
                cb = QtWidgets.QCheckBox()
                grid_layout.addWidget(cb, i, j)
                row.append(cb)
            self.checkbox_grid.append(row)

        layout.addWidget(QtWidgets.QLabel("Matrix:"), 4, 0)
        layout.addWidget(grid_widget, 4, 1, 1, 2)

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
        self.toast_manager = ToastManager(self)

        main_layout = QtWidgets.QHBoxLayout(self)

        self.plot_area = pg.GraphicsLayoutWidget()
        main_layout.addWidget(self.plot_area, stretch=4)
        self.plot_layouts = []

        self.sidebar_scroll = QtWidgets.QScrollArea()
        self.sidebar_scroll.setWidgetResizable(True)
        self.sidebar_widget = QtWidgets.QWidget()
        self.sidebar_layout = QtWidgets.QVBoxLayout(self.sidebar_widget)
        self.sidebar_scroll.setWidget(self.sidebar_widget)

        main_layout.addWidget(self.sidebar_scroll, stretch=1)

        # === Device name input + add button ===
        add_row = QtWidgets.QHBoxLayout()
        self.device_name_input = QtWidgets.QLineEdit()
        self.device_name_input.setPlaceholderText("Device name")
        self.add_device_button = QtWidgets.QPushButton("+ Add Device")
        self.add_device_button.clicked.connect(self.add_device)
        add_row.addWidget(self.device_name_input)
        add_row.addWidget(self.add_device_button)

        self.sidebar_layout.addLayout(add_row)
        self.sidebar_layout.addStretch()

        self.timer = QtCore.QTimer()
        self.timer.timeout.connect(self.update_data)
        self.timer.start(100)

    def add_device(self):
        typed_name = self.device_name_input.text().strip()
        name = typed_name if typed_name else f"Device {self.device_counter}"
        self.device_counter += 1
        self.device_name_input.clear()

        try:
            if name.endswith("3"):
                raise RuntimeError("Could not connect to device")

            if self.plot_layouts:
                self.plot_area.nextRow()
            plot = self.plot_area.addPlot(title=name)
            plot.showGrid(x=True, y=True)
            plot.setLabel('left', name)

            config_widget = DeviceConfigWidget(
                name,
                on_delete=lambda: self.remove_device(name),
                on_config_change=lambda: self.apply_config(name)
            )
            self.sidebar_layout.insertWidget(self.sidebar_layout.count() - 2, config_widget)

            device = Device(name, plot, self.x, config_widget)
            self.devices[name] = device
            self.plot_layouts.append(plot)

            self.toast_manager.show(f"✅ Connected to {name}", level="success")

        except Exception as e:
            self.toast_manager.show(str(e), level="error")

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
                device.step += 1
                device.data[-1] = np.sin(device.step * 0.1)
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
