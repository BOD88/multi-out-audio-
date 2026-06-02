"""
ui/mini_window.py
=================
Compact floating mini-mode window for the Multi-Output Audio Console.

Shows a master VU meter, volume control, mute toggle, routing status,
and an expand button that returns to the main window.
"""

from PyQt5.QtCore import QPoint, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QWidget

from .styles import COLOURS
from .vu_meter import VUMeter


class MiniWindow(QWidget):
    """Compact always-on-top controller window for mini mode."""

    # Signals for the main window to connect
    volume_changed = pyqtSignal(int)       # volume 0-100
    mute_toggled = pyqtSignal(bool)
    routing_toggled = pyqtSignal()
    expand_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._drag_offset = QPoint()

        self.setWindowFlags(
            Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setFixedSize(300, 100)
        self.setObjectName("mini_window")

        self._build_ui()
        self._connect_signals()
        self.set_muted(False)
        self.set_routing_active(False)

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        self._vu = VUMeter(bar_count=2)
        self._vu.setFixedSize(24, 76)
        self._vu.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        root.addWidget(self._vu, alignment=Qt.AlignVCenter)

        slider_col = QVBoxLayout()
        slider_col.setContentsMargins(0, 0, 0, 0)
        slider_col.setSpacing(6)

        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(0, 100)
        self._slider.setValue(100)
        self._slider.setFixedWidth(120)
        self._slider.setToolTip("Master volume")
        slider_col.addStretch(1)
        slider_col.addWidget(self._slider)
        slider_col.addStretch(1)
        root.addLayout(slider_col, stretch=1)

        self._btn_mute = QPushButton("🔊")
        self._btn_mute.setObjectName("btn_mute")
        self._btn_mute.setCheckable(True)
        self._btn_mute.setToolTip("Mute audio")
        root.addWidget(self._btn_mute, alignment=Qt.AlignVCenter)

        self._btn_routing = QPushButton("▶")
        self._btn_routing.setObjectName("btn_routing")
        self._btn_routing.setCheckable(True)
        self._btn_routing.setToolTip("Start audio routing")
        root.addWidget(self._btn_routing, alignment=Qt.AlignVCenter)

        self._btn_expand = QPushButton("↗")
        self._btn_expand.setObjectName("btn_expand")
        self._btn_expand.setToolTip("Expand to the main window")
        root.addWidget(self._btn_expand, alignment=Qt.AlignVCenter)

        self.setStyleSheet(
            f"""
            QWidget#mini_window {{
                background: transparent;
            }}
            QSlider::groove:horizontal {{
                height: 4px;
                background: {COLOURS['bg_panel']};
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {COLOURS['accent']};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                background: {COLOURS['accent']};
                width: 14px;
                height: 14px;
                border-radius: 7px;
                margin: -5px 0;
            }}
            QPushButton {{
                background-color: {COLOURS['bg_card']};
                color: {COLOURS['text_primary']};
                border: 1px solid {COLOURS['border']};
                border-radius: 6px;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                font-size: 14px;
                padding: 0;
            }}
            QPushButton:hover {{
                border-color: {COLOURS['accent']};
                background-color: {COLOURS['bg_panel']};
            }}
            QPushButton:pressed {{
                background-color: {COLOURS['accent']};
            }}
            QPushButton#btn_mute:checked {{
                background-color: {COLOURS['danger']};
                border-color: {COLOURS['danger']};
            }}
            QPushButton#btn_routing:checked {{
                background-color: {COLOURS['success']};
                border-color: {COLOURS['success']};
                color: {COLOURS['bg_deep']};
            }}
            QPushButton#btn_routing:!checked {{
                color: {COLOURS['text_secondary']};
            }}
            QPushButton#btn_expand {{
                font-size: 15px;
            }}
            """
        )


    def _connect_signals(self) -> None:
        self._slider.valueChanged.connect(self.volume_changed.emit)
        self._btn_mute.toggled.connect(self._on_mute_toggled)
        self._btn_routing.clicked.connect(self.routing_toggled.emit)
        self._btn_expand.clicked.connect(self.expand_requested.emit)

    def _on_mute_toggled(self, muted: bool) -> None:
        self._btn_mute.setText("🔇" if muted else "🔊")
        self.mute_toggled.emit(muted)

    def set_levels(self, left: float, right: float) -> None:
        self._vu.set_levels(left, right)

    def set_volume(self, value: int) -> None:
        self._slider.blockSignals(True)
        self._slider.setValue(int(value))
        self._slider.blockSignals(False)

    def set_muted(self, muted: bool) -> None:
        self._btn_mute.blockSignals(True)
        self._btn_mute.setChecked(muted)
        self._btn_mute.setText("🔇" if muted else "🔊")
        self._btn_mute.blockSignals(False)

    def set_routing_active(self, active: bool) -> None:
        self._btn_routing.blockSignals(True)
        self._btn_routing.setChecked(active)
        self._btn_routing.setText("⏹" if active else "▶")
        self._btn_routing.setToolTip(
            "Stop audio routing" if active else "Start audio routing"
        )
        self._btn_routing.blockSignals(False)

    def mousePressEvent(self, event) -> None:    # for dragging
        if event.button() == Qt.LeftButton:
            self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:     # for dragging
        if event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        rect = self.rect().adjusted(0, 0, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)

        painter.fillPath(path, QColor(13, 17, 23, 220))
        painter.setPen(QColor(COLOURS['border']))
        painter.drawPath(path)
        painter.end()
