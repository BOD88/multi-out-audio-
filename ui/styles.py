"""
ui/styles.py
============
Dark and light audio-console QSS themes for Multi-Output Audio Console.
"""

# ── Dark colour palette ──
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

# ── Light colour palette ──
L_BG_DEEP = "#f6f8fa"
L_BG_PANEL = "#ffffff"
L_BG_CARD = "#ffffff"
L_BG_CARD_HOVER = "#f0f2f5"
L_ACCENT = "#0a8f7f"
L_ACCENT_DIM = "#0d6e63"
L_WARN = "#d48806"
L_DANGER = "#cf222e"
L_SUCCESS = "#1a7f37"
L_TEXT_PRIMARY = "#1f2328"
L_TEXT_SECONDARY = "#656d76"
L_TEXT_MUTED = "#8b949e"
L_BORDER = "#d0d7de"
L_SLIDER_GROOVE = "#e1e4e8"
L_SLIDER_HANDLE = "#0a8f7f"
L_BTN_START = "#1a7f37"
L_BTN_START_HOVER = "#2ea043"
L_BTN_STOP = "#cf222e"
L_BTN_STOP_HOVER = "#a40e26"


def _build_stylesheet(
    bg_deep, bg_panel, bg_card, bg_card_hover,
    accent, accent_dim, warn, danger, success,
    text_primary, text_secondary, text_muted,
    border, slider_groove, slider_handle,
    btn_start, btn_start_hover, btn_stop, btn_stop_hover,
    card_active_bg="#1e2d2a",
) -> str:
    return f"""
/* ── Global ── */
QWidget {{
    background-color: {bg_deep};
    color: {text_primary};
    font-family: "Segoe UI", Arial, sans-serif;
    font-size: 12px;
}}

QMainWindow {{
    background-color: {bg_deep};
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
    background: {bg_panel};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {border};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {text_secondary};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

/* ── Group boxes / panels ── */
QGroupBox {{
    border: 1px solid {border};
    border-radius: 6px;
    margin-top: 14px;
    padding-top: 6px;
    font-weight: 600;
    color: {text_secondary};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 6px;
    color: {accent};
    font-size: 11px;
    letter-spacing: 1px;
    text-transform: uppercase;
}}

/* ── Sliders ── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {slider_groove};
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {accent};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {slider_handle};
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
    background: {slider_groove};
    border-radius: 2px;
}}
QSlider::add-page:vertical {{
    background: {accent};
    border-radius: 2px;
}}
QSlider::handle:vertical {{
    background: {slider_handle};
    width: 14px;
    height: 14px;
    border-radius: 7px;
    margin: 0 -5px;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {bg_card};
    color: {text_primary};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 5px 14px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {bg_card_hover};
    border-color: {accent};
}}
QPushButton:pressed {{
    background-color: {accent_dim};
}}
QPushButton:disabled {{
    color: {text_muted};
    border-color: {bg_card};
}}

QPushButton#btn_start {{
    background-color: {btn_start};
    border-color: {btn_start};
    color: white;
    font-weight: 700;
    font-size: 13px;
    padding: 8px 20px;
}}
QPushButton#btn_start:hover {{
    background-color: {btn_start_hover};
}}
QPushButton#btn_stop {{
    background-color: {btn_stop};
    border-color: {btn_stop};
    color: white;
    font-weight: 700;
    font-size: 13px;
    padding: 8px 20px;
}}
QPushButton#btn_stop:hover {{
    background-color: {btn_stop_hover};
}}

/* Mute toggle */
QPushButton#btn_mute {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 4px;
    min-width: 32px;
    max-width: 32px;
    min-height: 26px;
    max-height: 26px;
    font-size: 13px;
    padding: 0;
}}
QPushButton#btn_mute:checked {{
    background-color: {danger};
    border-color: {danger};
}}
QPushButton#btn_mute:hover {{
    border-color: {accent};
}}

/* ── Check boxes ── */
QCheckBox {{
    color: {text_primary};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid {border};
    background: {bg_card};
}}
QCheckBox::indicator:checked {{
    background: {accent};
    border-color: {accent};
    image: none;
}}
QCheckBox::indicator:hover {{
    border-color: {accent};
}}

/* ── Labels ── */
QLabel#lbl_section {{
    color: {text_secondary};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
}}
QLabel#lbl_status_active {{
    color: {success};
    font-weight: 700;
}}
QLabel#lbl_status_inactive {{
    color: {text_secondary};
}}

/* ── ComboBox ── */
QComboBox {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 8px;
    color: {text_primary};
    min-width: 200px;
}}
QComboBox:hover {{
    border-color: {accent};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox::down-arrow {{
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 6px solid {text_secondary};
    width: 0;
    height: 0;
    margin-right: 6px;
}}
QComboBox QAbstractItemView {{
    background-color: {bg_panel};
    border: 1px solid {border};
    selection-background-color: {accent_dim};
    color: {text_primary};
    padding: 2px;
}}

/* ── Status bar ── */
QStatusBar {{
    background-color: {bg_panel};
    color: {text_secondary};
    border-top: 1px solid {border};
    font-size: 11px;
}}

/* ── Tool tips ── */
QToolTip {{
    background-color: {bg_panel};
    color: {text_primary};
    border: 1px solid {border};
    padding: 4px 8px;
    border-radius: 4px;
}}

/* ── Device card frame ── */
QFrame#device_card {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 8px;
}}
QFrame#device_card:hover {{
    border-color: {accent_dim};
}}
QFrame#device_card[active="true"] {{
    border-color: {accent};
    background-color: {card_active_bg};
}}

/* ── App strip frame ── */
QFrame#app_strip {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 6px;
}}

/* ── Line Edit (search) ── */
QLineEdit {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 4px 8px;
    color: {text_primary};
}}
QLineEdit:focus {{
    border-color: {accent};
}}

/* ── Log panel ── */
QPlainTextEdit#log_panel {{
    background-color: {bg_card};
    border: 1px solid {border};
    border-radius: 4px;
    color: {text_secondary};
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 11px;
    padding: 4px;
}}
"""


STYLESHEET = _build_stylesheet(
    BG_DEEP, BG_PANEL, BG_CARD, BG_CARD_HOVER,
    ACCENT, ACCENT_DIM, WARN, DANGER, SUCCESS,
    TEXT_PRIMARY, TEXT_SECONDARY, TEXT_MUTED,
    BORDER, SLIDER_GROOVE, SLIDER_HANDLE,
    BTN_START, BTN_START_HOVER, BTN_STOP, BTN_STOP_HOVER,
)

STYLESHEET_LIGHT = _build_stylesheet(
    L_BG_DEEP, L_BG_PANEL, L_BG_CARD, L_BG_CARD_HOVER,
    L_ACCENT, L_ACCENT_DIM, L_WARN, L_DANGER, L_SUCCESS,
    L_TEXT_PRIMARY, L_TEXT_SECONDARY, L_TEXT_MUTED,
    L_BORDER, L_SLIDER_GROOVE, L_SLIDER_HANDLE,
    L_BTN_START, L_BTN_START_HOVER, L_BTN_STOP, L_BTN_STOP_HOVER,
    card_active_bg="#e6f7f2",
)

# Exported colours for use by custom widgets (dark theme defaults)
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

COLOURS_LIGHT = {
    "bg_deep": L_BG_DEEP,
    "bg_panel": L_BG_PANEL,
    "bg_card": L_BG_CARD,
    "accent": L_ACCENT,
    "warn": L_WARN,
    "danger": L_DANGER,
    "success": L_SUCCESS,
    "text_primary": L_TEXT_PRIMARY,
    "text_secondary": L_TEXT_SECONDARY,
    "border": L_BORDER,
}
