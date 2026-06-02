#!/usr/bin/env python3
"""
main.py
=======
Entry point for Multi-Output Audio Console.

Run with:
    python main.py

Or on Windows, double-click run.bat.
"""

import sys
import logging


def _check_dependencies() -> None:
    """Validate required packages and provide helpful install instructions."""
    missing = []

    packages = {
        "PyQt5": "PyQt5",
        "sounddevice": "sounddevice",
        "numpy": "numpy",
    }
    # pycaw / comtypes are Windows-only and optional (degrade gracefully)
    for import_name, pip_name in packages.items():
        try:
            __import__(import_name)
        except ImportError:
            missing.append(pip_name)

    if missing:
        print("=" * 60)
        print("  Multi-Output Audio Console — Missing dependencies")
        print("=" * 60)
        print(f"\n  The following packages are not installed:\n")
        for pkg in missing:
            print(f"    • {pkg}")
        print(
            f"\n  Please run:\n"
            f"    pip install {' '.join(missing)}\n"
            f"\n  Or install all requirements:\n"
            f"    pip install -r requirements.txt\n"
        )
        sys.exit(1)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )
    # Suppress noisy library loggers
    for name in ("sounddevice", "comtypes", "PyQt5"):
        logging.getLogger(name).setLevel(logging.WARNING)


def main() -> None:
    _check_dependencies()
    _configure_logging()

    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont

    # Enable High-DPI support
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Multi-Output Audio Console")
    app.setApplicationVersion("2.0.0")
    app.setOrganizationName("BOD88")
    app.setStyle("Fusion")  # Required base for dark QSS theme

    # Keep app running when main window is hidden (system tray)
    app.setQuitOnLastWindowClosed(False)

    # Default font
    font = QFont("Segoe UI", 10)
    app.setFont(font)

    from ui.main_window import MainWindow

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
