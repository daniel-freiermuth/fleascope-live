from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import numpy as np
import pandas as pd
import sys

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout()
    win.setLayout(layout)

    # Plot widget with legend
    plot_widget = pg.PlotWidget(title="Live DataFrame Plot")
    plot_widget.addLegend()
    layout.addWidget(plot_widget)

    num_series = 3
    window_size = 200  # How many time steps to show

    # Simulated DataFrame with 3 series
    df = pd.DataFrame(np.zeros((window_size, num_series)), columns=['A', 'B', 'C'])
    x_data = np.arange(window_size)

    # Create one curve per series
    curves = {}
    for col in df.columns:
        curves[col] = plot_widget.plot(x_data, df[col], pen=None, name=col, symbol='o', symbolSize=4)

    # Reset button
    reset_btn = QtWidgets.QPushButton("Reset Data")
    layout.addWidget(reset_btn)

    def reset():
        df.loc[:, :] = 0
        for col in df.columns:
            curves[col].setData(x_data, df[col])

    reset_btn.clicked.connect(reset)

    def update():
        nonlocal df
        new_row = {
            'A': np.random.normal(),
            'B': np.random.normal() * 0.5,
            'C': np.sin(len(df) / 10)
        }
        df = pd.concat([df.iloc[1:], pd.DataFrame([new_row])], ignore_index=True)

        for col in df.columns:
            curves[col].setData(x_data, df[col])

    # Timer for live update
    timer = QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(100)

    win.setWindowTitle("Live Multi-Series Plot")
    win.resize(900, 500)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()