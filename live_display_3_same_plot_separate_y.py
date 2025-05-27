from PyQt6 import QtWidgets, QtCore
import pyqtgraph as pg
import numpy as np
import sys

def main():
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QWidget()
    layout = QtWidgets.QVBoxLayout()
    win.setLayout(layout)

    # === Create plot area ===
    plot_widget = pg.PlotWidget(title="Shared X, Separate Y-Axes")
    plot_widget.addLegend()
    layout.addWidget(plot_widget)

    # === Primary viewbox (default y-axis) ===
    vb1 = plot_widget.getViewBox()
    curve1 = plot_widget.plot(pen='y', name='Signal A')  # y-axis 1

    # === Secondary viewbox (new y-axis) ===
    vb2 = pg.ViewBox()
    plot_widget.scene().addItem(vb2)
    plot_widget.getPlotItem().showAxis('right')
    plot_widget.getPlotItem().getAxis('right').linkToView(vb2)
    vb2.setXLink(vb1)  # Link X axis
    curve2 = pg.PlotDataItem(pen='r', name='Signal B')
    vb2.addItem(curve2)

    # === Update view positions when resized ===
    def update_views():
        vb2.setGeometry(plot_widget.getViewBox().sceneBoundingRect())
        vb2.linkedViewChanged(vb1, vb2.XAxis)

    vb1.sigResized.connect(update_views)

    # === Simulated data ===
    x_data = np.arange(200)
    y1 = np.zeros(200)
    y2 = np.zeros(200)

    # === Update logic ===
    def update():
        nonlocal y1, y2
        y1 = np.roll(y1, -1)
        y2 = np.roll(y2, -1)
        y1[-1] = np.random.normal(loc=0, scale=1)
        y2[-1] = 50 + np.sin(len(y2) / 10) * 10
        curve1.setData(x_data, y1)
        curve2.setData(x_data, y2)

    # === Timer ===
    timer = QtCore.QTimer()
    timer.timeout.connect(update)
    timer.start(100)

    win.setWindowTitle("Live Plot: Multiple Y-Axes")
    win.resize(900, 500)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
