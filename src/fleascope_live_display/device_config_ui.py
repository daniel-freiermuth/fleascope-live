from abc import abstractmethod
import math
from collections.abc import Callable
from typing import Literal
from PyQt6 import QtCore
from PyQt6 import QtWidgets
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QButtonGroup, QDial, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QPushButton, QSizePolicy, QStackedLayout, QStyle, QToolButton, QVBoxLayout, QWidget

from pyfleascope.flea_scope import Waveform
from pyfleascope.trigger_config import AnalogTrigger, BitState, BitTriggerBuilder, DigitalTrigger

GRID_SIZE = 30

class TriStateBitButton(QToolButton):
    STATES = [
        ("?", None),
        ("0", QColor("red")),
        ("1", QColor("green"))
    ]

    def __init__(self, bit_index: int):
        super().__init__()
        self.bit_index = bit_index
        self.state_index = 0
        self.setCheckable(True)
        self.setFixedSize(16,16)
        self.setToolTip(f"Bit {bit_index}")
        self.update_state()
        self.clicked.connect(self.next_state)

    def next_state(self):
        self.state_index = (self.state_index + 1) % 3
        self.update_state()

    def update_state(self):
        text, color = self.STATES[self.state_index]
        self.setText(text)
        bg = color.name() if color else "none"
        self.setStyleSheet(f"""
            QToolButton {{
                border: 1px solid gray;
            }}
        """)
    
    def configureBit(self, builder: BitTriggerBuilder):
        if self.state_index == 0:
            return builder.set_bit(self.bit_index, BitState.DONT_CARE)
        elif self.state_index == 1:
            return builder.set_bit(self.bit_index, BitState.LOW)
        elif self.state_index == 2:
            return builder.set_bit(self.bit_index, BitState.HIGH)
        else:
            raise ValueError("Invalid state index")

class BitGrid(QWidget):
    change_sig = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        layout = QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        self.buttons: list[TriStateBitButton] = []
        for i in range(9):
            btn = TriStateBitButton(bit_index=i)
            btn.clicked.connect(self.change_sig.emit)
            self.buttons.append(btn)
            row, col = divmod(i, 3)
            layout.addWidget(btn, row, col)

        self.setLayout(layout)
    
    def getTriggerBuilder(self) -> BitTriggerBuilder:
        builder = DigitalTrigger.start_capturing_when()
        for btn in self.buttons:
            builder = btn.configureBit(builder)
        return builder

def pretty_prefix(x: float):
    """Give the number an appropriate SI prefix.

    :param x: Too big or too small number.
    :returns: String containing a number between 1 and 1000 and SI prefix.
    """
    if x == 0:
        return "0  "

    l = math.floor(math.log10(abs(x)))

    div, mod = divmod(l, 3)
    return "%.3g %s" % (x * 10**(-l + mod), " kMGTPEZYyzafpnµm"[div])

def format_engineering(value: float, sigfigs: int) -> tuple[str, int]:
    if value == 0:
        return ("0", 0)

    sign = "-" if value < 0 else ""
    abs_val = abs(value)

    exponent = int(math.floor(math.log10(abs_val)))
    eng_exponent = 3 * (exponent // 3)
    scaled: float = abs_val / (10 ** eng_exponent)

    # Round to significant figures
    digits = sigfigs - int(math.floor(math.log10(scaled))) - 1
    rounded = round(scaled, digits)

    # Format and strip trailing junk
    mantissa = f"{rounded:.{digits}f}".rstrip("0").rstrip(".")
    return (sign + mantissa, eng_exponent)


class Knob(QWidget):
    def __init__(self, title: str, unit: str, steps: int):
        super().__init__()
        self.setFixedSize(GRID_SIZE*2, GRID_SIZE*2)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setLayout(layout)


        title_label = QLabel(title)
        layout.addWidget(title_label)
        font = title_label.font()
        font.setPointSize(int(GRID_SIZE * 0.3))
        title_label.setFont(font)

        self._dial = QDial()
        self._dial.setMinimum(0)
        self._dial.setMaximum(steps - 1)
        self._dial.setFixedSize(int(GRID_SIZE*1), int(GRID_SIZE*1))

        dial_layout = QHBoxLayout()
        dial_layout.setContentsMargins(0, 0, 0, 0)
        dial_layout.setSpacing(0)
        dial_layout.addStretch()
        dial_layout.addWidget(self._dial)
        dial_layout.addStretch()
        layout.addLayout(dial_layout)

        dial_label = QLabel(" (mV):")
        dial_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        dial_label.setContentsMargins(0, 0, 0, 0)
        dial_label.setFont(font)
        layout.addWidget(dial_label)

        self._dial.valueChanged.connect(lambda v: dial_label.setText(f"{pretty_prefix(self._step_to_value(v))}{unit}"))
    
    def setValue(self, a0: float):
        self._dial.setValue(self._value_to_step(a0))
    
    def onValueChanged(self, slot: Callable[[float], None]):
        def f(value: int):
            v = self._step_to_value(value)
            slot(v)
        self._dial.valueChanged.connect(f)
    
    def getValue(self) -> float:
        return self._step_to_value(self._dial.value())

    @abstractmethod
    def _step_to_value(self, step: int) -> float:
        return NotImplemented

    @abstractmethod
    def _value_to_step(self, value: float) -> int:
        return NotImplemented
    
class LinearKnob(Knob):
    def __init__(self, title: str, unit: str, lower_limit: float, upper_limit: float, steps: int=1321):
        super().__init__(title, unit, steps)
        self._upper_limit = upper_limit
        self._lower_limit = lower_limit

    def _step_to_value(self, step: int) -> float:
        return step / self._dial.maximum() * (self._upper_limit - self._lower_limit) + self._lower_limit

    def _value_to_step(self, value: float) -> int:
        return int((value - self._lower_limit) / (self._upper_limit - self._lower_limit) * self._dial.maximum())

    def setLimits(self, lower_limit: float, upper_limit: float):
        self._lower_limit = lower_limit
        self._upper_limit = upper_limit

class MonotonicKnob(LinearKnob):
    def __init__(self, title: str, unit: str,
                 lower_limit: float, upper_limit: float,
                 steps: int=1321):
        super().__init__(title, unit, self._value_to_linear(lower_limit), self._value_to_linear(upper_limit), steps)
    
    def _value_to_linear(self, value: float) -> float:
        return NotImplemented
    
    def _linear_to_value(self, linear_value: float) -> float:
        return NotImplemented
    
    def _step_to_value(self, step: int) -> float:
        linear_value = super()._step_to_value(step)
        return self._linear_to_value(linear_value)

    def _value_to_step(self, value: float) -> int:
        linear_value = self._value_to_linear(value)
        return super()._value_to_step(linear_value)

    def setLimits(self, lower_limit: float, upper_limit: float):
        cur_value = self.getValue()
        self._lower_limit = self._value_to_linear(lower_limit)
        self._upper_limit = self._value_to_linear(upper_limit)
        value = min(max(cur_value, lower_limit), upper_limit)
        self.setValue(value)

class LogKnob(LinearKnob):
    def __init__(self, title: str, unit: str, min_exp: float, max_exp: float, steps: int=1321):
        super().__init__(title, unit, min_exp, max_exp, steps)

    def _step_to_value(self, step: int) -> float:
        return 2** (super()._step_to_value(step))

    def _value_to_step(self, value: float) -> int:
        return super()._value_to_step(math.log(value, 2))
    
class QuadraticKnob(MonotonicKnob):
    def __init__(self, title: str, unit: str, lower_limit: float, upper_limit: float, steps: int=1321):
        super().__init__(title, unit, lower_limit, upper_limit, steps)
    
    def _value_to_linear(self, value: float) -> float:
        if value >= 0:
            return math.sqrt(value)
        else:
            return -math.sqrt(-value)
    
    def _linear_to_value(self, linear_value: float) -> float:
        if linear_value >= 0:
            return linear_value**2
        else:
            return -(linear_value**2)

class WaveformSelector(QWidget):
    waveform_changed = QtCore.pyqtSignal(Waveform, int)

    def emitWaveform(self):
        hz = int(self.dial.getValue())
        if self.sine_button.isChecked():
            waveform = Waveform.SINE
        elif self.square_button.isChecked():
            waveform = Waveform.SQUARE
        elif self.triangle_button.isChecked():
            waveform = Waveform.TRIANGLE
        elif self.ekg_button.isChecked():
            waveform = Waveform.EKG
        else:
            raise ValueError("No waveform selected")
        
        self.waveform_changed.emit(waveform, hz)

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.setContentsMargins(0,0,0,0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)

        trigger_mode_group = QButtonGroup(self)
        trigger_mode_group.setExclusive(True)

        self.sine_button = QToolButton()
        self.sine_button.setText("Si")

        self.square_button = QToolButton()
        self.square_button.setText("Sq")

        self.triangle_button = QToolButton()
        self.triangle_button.setText("️T")

        self.ekg_button = QToolButton()
        self.ekg_button.setText("E")

        for btn in (self.sine_button, self.square_button, self.triangle_button, self.ekg_button):
            btn.setMinimumSize(GRID_SIZE, GRID_SIZE)
            btn.setMaximumSize(GRID_SIZE, GRID_SIZE)
            btn.setCheckable(True)
            btn.clicked.connect(self.emitWaveform)
            trigger_mode_group.addButton(btn)
        
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(0)
        row1.addWidget(self.sine_button)
        row1.addWidget(self.square_button)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(0)
        row2.addWidget(self.triangle_button)
        row2.addWidget(self.ekg_button)
        self.sine_button.setChecked(True)

        layout.addLayout(row1)
        layout.addLayout(row2)

        self.dial = QuadraticKnob("Frequency", "Hz", 10, 4_000_000)
        self.dial.setValue(1000)
        self.dial.onValueChanged(lambda f: self.emitWaveform())

        layout.addWidget(self.dial)
    
class DigitalChannelSelectorWidget(QWidget):
    def __init__(self):
        super().__init__()
        layout = QGridLayout()
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)

        size = int(GRID_SIZE * 2 / 3)

        self.buttons: list[QToolButton] = []
        for i in range(9):
            btn = QToolButton()
            btn.setCheckable(True)
            btn.setText(str(i))
            btn.setFixedSize(size, size)
            self.buttons.append(btn)
            row, col = divmod(i, 3)
            layout.addWidget(btn, row, col)

        self.setLayout(layout)

class TriggerPanel(QWidget):
    settings_changed_sig = QtCore.pyqtSignal()
    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        self.setContentsMargins(0,0,0,0)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0,0,0,0)
        self.layout.setSpacing(0)
    
    @abstractmethod
    def getTrigger(self) -> AnalogTrigger | DigitalTrigger:
        return NotImplemented

class AnalogTriggerPanel(TriggerPanel):
    def __init__(self):
        super().__init__()

        trigger_mode_group = QButtonGroup(self)
        trigger_mode_group.setExclusive(True)

        self.analog_level_time = QToolButton()
        self.analog_level_time.setText("↩️")

        self.analog_rising = QToolButton()
        self.analog_rising.setText("↗️")

        self.analog_level = QToolButton()
        self.analog_level.setText("➡️️")

        self.analog_falling = QToolButton()
        self.analog_falling.setText("↘️")

        for btn in (self.analog_level_time, self.analog_rising, self.analog_level, self.analog_falling):
            btn.setFixedSize(GRID_SIZE, GRID_SIZE)
            btn.setCheckable(True)
            btn.clicked.connect(self.settings_changed_sig.emit)
            trigger_mode_group.addButton(btn)
        
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(0)
        row1.addWidget(self.analog_level_time)
        row1.addWidget(self.analog_rising)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(0)
        row2.addWidget(self.analog_level)
        row2.addWidget(self.analog_falling)
        self.analog_level_time.setChecked(True)

        self.layout.addLayout(row1)
        self.layout.addLayout(row2)

        self.dial = LinearKnob("Level", "V", -66, 66)
        self.dial.setValue(1)
        self.dial.onValueChanged(lambda f: self.settings_changed_sig.emit())

        self.layout.addWidget(self.dial)
    
    def getTrigger(self) -> AnalogTrigger:
        level = self.dial.getValue()
        if self.analog_level_time.isChecked():
            return AnalogTrigger.start_capturing_when().auto(level)
        elif self.analog_rising.isChecked():
            return AnalogTrigger.start_capturing_when().rising_edge(level)
        elif self.analog_level.isChecked():
            return AnalogTrigger.start_capturing_when().level(level)
        elif self.analog_falling.isChecked():
            return AnalogTrigger.start_capturing_when().falling_edge(level)
        else:
            raise ValueError("No trigger mode selected")

class DigitalTriggerPanel(TriggerPanel):
    def __init__(self):
        super().__init__()

        trigger_mode_group = QButtonGroup(self)
        trigger_mode_group.setExclusive(True)

        self.analog_level_time = QToolButton()
        self.analog_level_time.setText("↩️")

        self.analog_rising = QToolButton()
        self.analog_rising.setText("↗️")

        self.analog_level = QToolButton()
        self.analog_level.setText("➡️️")

        self.analog_falling = QToolButton()
        self.analog_falling.setText("↘️")

        for btn in (self.analog_level_time, self.analog_rising, self.analog_level, self.analog_falling):
            btn.setFixedSize(GRID_SIZE, GRID_SIZE)
            btn.setCheckable(True)
            btn.clicked.connect(self.settings_changed_sig.emit)
            trigger_mode_group.addButton(btn)
        
        row1 = QHBoxLayout()
        row1.setContentsMargins(0, 0, 0, 0)
        row1.setSpacing(0)
        row1.addWidget(self.analog_level_time)
        row1.addWidget(self.analog_rising)

        row2 = QHBoxLayout()
        row2.setContentsMargins(0, 0, 0, 0)
        row2.setSpacing(0)
        row2.addWidget(self.analog_level)
        row2.addWidget(self.analog_falling)
        self.analog_level_time.setChecked(True)

        self.layout.addLayout(row1)
        self.layout.addLayout(row2)

        self.bit_grid = BitGrid()
        self.bit_grid.change_sig.connect(self.settings_changed_sig.emit)

        self.layout.addWidget(self.bit_grid)
    
    def getTrigger(self) -> DigitalTrigger:
        if self.analog_level_time.isChecked():
            return self.bit_grid.getTriggerBuilder().auto()
        elif self.analog_rising.isChecked():
            return self.bit_grid.getTriggerBuilder().starts_matching()
        elif self.analog_level.isChecked():
            return self.bit_grid.getTriggerBuilder().is_matching()
        elif self.analog_falling.isChecked():
            return self.bit_grid.getTriggerBuilder().stops_matching()
        else:
            raise ValueError("No trigger mode selected")
    

class DeviceConfigWidget(QGroupBox):
    cal_0v_sig = QtCore.pyqtSignal()
    save_cal_sig = QtCore.pyqtSignal()
    cal_3v3_sig = QtCore.pyqtSignal()
    remove_device_sig = QtCore.pyqtSignal()
    trigger_settings_changed_sig = QtCore.pyqtSignal()
    pause_sig = QtCore.pyqtSignal()
    resume_sig = QtCore.pyqtSignal()
    step_sig = QtCore.pyqtSignal()
    rename_device_sig = QtCore.pyqtSignal(str)

    def set_transportview(self, name: Literal['paused', 'running']):
        if name == 'paused':
            self.transport_control.setCurrentIndex(0)
        elif name == 'running':
            self.transport_control.setCurrentIndex(1)
        else:
            raise ValueError("Invalid transport view name. Use 'paused' or 'running'.")

    def getProbe(self):
        if self.x1_button.isChecked():
            return "x1"
        elif self.x10_button.isChecked():
            return "x10"
        else:
            raise ValueError("No probe selected")
        
    def getTimeFrame(self) -> float:
        return self.time_frame_dial.getValue()
    
    def getTrigger(self) -> AnalogTrigger | DigitalTrigger:
        return self.value_stack.currentWidget().getTrigger()

    def getDelayValue(self) -> float:
        return self.delay_dial.getValue()
    
    def removeDevice(self):
        p = self.parent()
        assert p is not None, "DeviceConfigWidget must be a child of a parent widget"
        p.layout().removeWidget(self)
        self.deleteLater()

    def offerRenameDevice(self):
        text, ok = QInputDialog.getText(self, "Input new device name", "Name:")
        if ok:
            self.setTitle(text)
            self.rename_device_sig.emit(text)
    
    def __init__(self, title: str):
        super().__init__()
        self.setTitle(title)
        main_layout = QGridLayout(self)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(0,0,0,0)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        led = QLabel("🔴")
        main_layout.addWidget(led, 0, 0, 1, 1)

        rename_button = QToolButton()
        rename_button.setText("R")
        rename_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        rename_button.clicked.connect(self.offerRenameDevice)
        main_layout.addWidget(rename_button, 1, 0)

        self.transport_control = QStackedLayout()
        controls_when_paused_l = QHBoxLayout()
        controls_when_paused_l.setContentsMargins(0, 0, 0, 0)
        controls_when_paused_l.setSpacing(0)
        controls_when_paused_w = QWidget()
        controls_when_paused_w.setLayout(controls_when_paused_l)

        play_button = QToolButton()
        play_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        play_button.setToolTip("Continously sample")
        play_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        controls_when_paused_l.addWidget(play_button)
        play_button.clicked.connect(self.resume_sig)

        step_button = QToolButton()
        step_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaSkipForward))
        step_button.setToolTip("Capture one sample")
        step_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        controls_when_paused_l.addWidget(step_button)
        step_button.clicked.connect(self.step_sig)

        pause_button = QToolButton()
        pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
        pause_button.setToolTip("Pause sampling")
        pause_button.setFixedSize(2*GRID_SIZE, GRID_SIZE)
        pause_button.clicked.connect(self.pause_sig)

        self.transport_control.addWidget(controls_when_paused_w)
        self.transport_control.addWidget(pause_button)

        self.transport_control.setCurrentIndex(1)

        main_layout.addLayout(self.transport_control, 0, 1, 1, 2)

        self.time_frame_dial = LogKnob("Capture", "s", -13, 1.5)
        self.time_frame_dial.setValue(0.1)
        self.time_frame_dial.onValueChanged(lambda f: self.trigger_settings_changed_sig.emit())
        self.delay_dial = QuadraticKnob("Delay", "s", 0, 1)
        self.delay_dial.setValue(0.1)
        self.delay_dial.setValue(0)
        self.delay_dial.onValueChanged(lambda f: self.trigger_settings_changed_sig.emit())
        self.time_frame_dial.onValueChanged(lambda time: self.delay_dial.setLimits(0, time*400))

        main_layout.addWidget(self.time_frame_dial, 2, 0, 2, 2)
        main_layout.addWidget(self.delay_dial, 2, 2, 2, 2)

        # Trigger mode selector (Analog / Digital)
        self.analog_btn = QPushButton("A")
        self.digital_btn = QPushButton("D")

        for btn in (self.analog_btn, self.digital_btn):
            btn.setCheckable(True)
            btn.setFixedWidth(GRID_SIZE)
            btn.setFixedHeight(GRID_SIZE)
            btn.setContentsMargins(0, 0, 0, 0)

        mode_group = QButtonGroup(self)
        mode_group.setExclusive(True)
        mode_group.addButton(self.analog_btn)
        mode_group.addButton(self.digital_btn)
        self.analog_btn.setChecked(True)

        main_layout.addWidget(self.analog_btn, 0, 3, 1, 1)
        main_layout.addWidget(self.digital_btn, 1,3, 1, 1)

        # Stacked mode-specific layout
        self.value_stack = QStackedLayout()

        analog_trigger_panel = AnalogTriggerPanel()
        self.value_stack.addWidget(analog_trigger_panel)
        analog_trigger_panel.settings_changed_sig.connect(self.trigger_settings_changed_sig.emit)

        digital_trigger_panel = DigitalTriggerPanel()
        self.value_stack.addWidget(digital_trigger_panel)
        digital_trigger_panel.settings_changed_sig.connect(self.trigger_settings_changed_sig.emit)

        stack_container = QWidget()
        stack_container.setLayout(self.value_stack)
        stack_container.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        main_layout.addWidget(stack_container, 0, 4, 4, 2)

        # Button logic
        self.analog_btn.clicked.connect(lambda: self.value_stack.setCurrentIndex(0))
        self.analog_btn.clicked.connect(self.trigger_settings_changed_sig.emit)
        self.digital_btn.clicked.connect(lambda: self.value_stack.setCurrentIndex(1))
        self.digital_btn.clicked.connect(self.trigger_settings_changed_sig.emit)

        waveform_ui = WaveformSelector()
        main_layout.addWidget(waveform_ui, 0, 6, 4, 2)
        self.waveform_changed = waveform_ui.waveform_changed

        main_layout.addWidget(DigitalChannelSelectorWidget(), 2, 8, 2, 2)

        bnc_button = QToolButton()
        bnc_button.setText("P")
        bnc_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        bnc_button.setCheckable(True)
        main_layout.addWidget(bnc_button, 3, 10)
        bnc_button.setChecked(True)

        self.x1_button = QToolButton()
        self.x1_button.setText("x1")
        self.x1_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        self.x1_button.setCheckable(True)
        self.x1_button.clicked.connect(self.trigger_settings_changed_sig.emit)
        main_layout.addWidget(self.x1_button, 0, 8)

        self.x10_button = QToolButton()
        self.x10_button.setText("x10")
        self.x10_button.setCheckable(True)
        self.x10_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        self.x10_button.clicked.connect(self.trigger_settings_changed_sig.emit)
        main_layout.addWidget(self.x10_button, 1, 8)

        buttongroup = QButtonGroup(self)
        buttongroup.setExclusive(True)
        buttongroup.addButton(self.x1_button)
        buttongroup.addButton(self.x10_button)
        self.x1_button.setChecked(True)

        cal_0v = QToolButton()
        cal_0v.setText("0V")
        cal_0v.setFixedSize(GRID_SIZE, GRID_SIZE)
        cal_0v.clicked.connect(self.cal_0v_sig.emit)
        main_layout.addWidget(cal_0v, 0, 9)

        cal_3v3 = QToolButton()
        cal_3v3.setText("3.3")
        cal_3v3.setFixedSize(GRID_SIZE, GRID_SIZE)
        cal_3v3.clicked.connect(self.cal_3v3_sig.emit)
        main_layout.addWidget(cal_3v3, 1, 9)

        delete_button = QToolButton()
        delete_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogDiscardButton))
        delete_button.setToolTip("Remove device")
        delete_button.setFixedSize(GRID_SIZE, GRID_SIZE)
        delete_button.clicked.connect(self.remove_device_sig.emit)

        main_layout.addWidget(delete_button, 0, 10)

        main_layout.addWidget(ColorButton(), 1, 10)

        save = QToolButton()
        save.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton))
        save.setToolTip("Save calibration")
        save.setFixedSize(GRID_SIZE, GRID_SIZE)
        save.clicked.connect(self.save_cal_sig)

        main_layout.addWidget(save, 2, 10)


class ColorButton(QToolButton):
        # self.color_button = QtWidgets.QPushButton()
    def __init__(self):
        super().__init__()
        self.setFixedSize(GRID_SIZE, GRID_SIZE)
        self.setStyleSheet("background-color: yellow; border: 1px solid gray;")
        self.setToolTip("Pick color")
        self.clicked.connect(self.pick_color)

    def pick_color(self):
        color = QtWidgets.QColorDialog.getColor()
        if color.isValid():
            self.setStyleSheet(f"background-color: {color.name()}; border: 1px solid gray;")

    def get_color(self):
        return self.palette().button().color().name()
