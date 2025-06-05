from PyQt6 import QtCore
from PyQt6.QtWidgets import QLabel, QWidget


class Toast(QLabel):
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

    def __init__(self, parent: QWidget, message:str, duration:int, stack_index: int, level: str="info"):
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

    def reposition(self, stack_index: int):
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
    def __init__(self, parent: QWidget):
        self.parent: QWidget = parent
        self.toasts: list[Toast] = []

    def show(self, message:str, duration:int=3000, level:str="info"):
        toast = Toast(self.parent, message, duration, len(self.toasts), level)
        toast.closed.connect(lambda: self._remove_toast(toast))
        self.toasts.append(toast)

    def _remove_toast(self, toast:Toast):
        if toast in self.toasts:
            self.toasts.remove(toast)
            self._reposition_toasts()

    def _reposition_toasts(self):
        for i, toast in enumerate(self.toasts):
            toast.reposition(i)
