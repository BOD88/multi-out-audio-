"""
ui/styles.py
============
Dark audio-console QSS theme for Multi-Output Audio Console.
"""

# Colour palette
BG_DEEP = "#0d1117"
BG_PANEL = "#161b22"
BG_CARD = "#1c2128"
BG_CARD_HOVER = "#21262d"
ACCENT = "#00c9a7"          # Teal / active
ACCENT_DIM = "#007a66"
WARN = "#f0a500"            # Yellow warning
DANGER = "#f85149"          # Red / clip
SUCCESS = "#3fb950"         # Green ok
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_MUTED = "#484f58"
BORDER = "#30363d"
SLIDER_GROOVE = "#21262d"
SLIDER_HANDLE = "#00c9a7"
BTN_START = "#238636"
BTN_START_HOVER = "#2ea043"
BTN_STOP = "#b62324"
BTN_STOP_HOVER = "#da3633"

STYLESHEET = f"""
/* ── Global ── */
QWidget {{
    background-color: {BG_DEEP};
    color: {TEXT_PRIMARY};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}}

QMainWindow {{
    background-color: {BG_DEEP};
}}

/* ── Scroll areas ── */
QScrollArea {{
    border: none;
    background-color: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}
QScrollBar:vertical {{
    background: {BG_PANEL};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_SECONDARY};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ── Group boxes / panels ── */
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 6px;
    font-weight: 600;
    color: {TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {ACCENT};
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ── Sliders ── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {SLIDER_GROOVE};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {SLIDER_HANDLE};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: -5px 0;
}}
QSlider::handle:horizontal:hover {{
    background: #00e6bf;
}}
QSlider::groove:vertical {{
    width: 4px;
    background: {SLIDER_GROOVE};
    border-radius: 2px;
}}
QSlider::add-page:vertical {{
    background: {ACCENT};
    border-radius: 2px;
}}
QSlider::handle:vertical {{
    background: {SLIDER_HANDLE};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: 0 -5px;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {BG_CARD_HOVER};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: {ACCENT_DIM};
}}
QPushButton:disabled {{
    color: {TEXT_MUTED};
    border-color: {BG_CARD};
}}

QPushButton#btn_start {{
    background-color: {BTN_START};
    border-color: {BTN_START};
    color: white;
    font-weight: 700;
    font-size: 13px;
    padding: 8px 20px;
}}
QPushButton#btn_start:hover {{
    background-color: {BTN_START_HOVER};
}}
QPushButton#btn_stop {{
    background-color: {BTN_STOP};
    border-color: {BTN_STOP};
    color: white;
    font-weight: 700;
    font-size: 13px;
    padding: 8px 20px;
}}
QPushButton#btn_stop:hover {{
    background-color: {BTN_STOP_HOVER};
}}

/* Mute toggle */
QPushButton#btn_mute {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    min-width: 32px;
    max-width: 32px;
    min-height: 26px;
    max-height: 26px;
    font-size: 13px;
    padding: 0;
}}
QPushButton#btn_mute:checked {{
    background-color: {DANGER};
    border-color: {DANGER};
}}
QPushButton#btn_mute:hover {{
    border-color: {ACCENT};
}}

/* ── Check boxes ── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {BORDER};
    background: {BG_CARD};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: none;
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}

/* ── Labels ── */
QLabel#lbl_section {{
    color: {TEXT_SECONDARY};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel#lbl_status_active {{
    color: {SUCCESS};
    font-weight: 700;
}}
QLabel#lbl_status_inactive {{
    color: {TEXT_SECONDARY};
}}

/* ── ComboBox ── */
QComboBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 4px 8px;
    color: {TEXT_PRIMARY};
    min-width: 200px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {TEXT_SECONDARY};
    width: 0;
    height: 0;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    selection-background-color: {ACCENT_DIM};
    color: {TEXT_PRIMARY};
    padding: 2px;
}}

/* ── Status bar ── */
QStatusBar {{
    background-color: {BG_PANEL};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 11px;
}}

/* ── Tool tips ── */
QToolTip {{
    background-color: {BG_PANEL};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ── Device card frame ── */
QFrame#device_card {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#device_card:hover {{
    border-color: {ACCENT_DIM};
}}
QFrame#device_card[active="true"] {{
    border-color: {ACCENT};
    background-color: #1e2d2a;
}}

/* ── App strip frame ── */
QFrame#app_strip {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
}}
"""

# Exported colours for use by custom widgets
COLOURS = {
    "bg_deep": BG_DEEP,
    "bg_panel": BG_PANEL,
    "bg_card": BG_CARD,
    "accent": ACCENT,
    "warn": WARN,
    "danger": DANGER,
    "success": SUCCESS,
    "text_primary": TEXT_PRIMARY,
    "text_secondary": TEXT_SECONDARY,
    "border": BORDER,
}
