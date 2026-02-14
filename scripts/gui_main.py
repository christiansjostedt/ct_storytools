#!/usr/bin/env python3

import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings

from gui_utils.styles import apply_dark_theme
from gui_utils.window_main import StorytoolsWindow


def main():
    app = QApplication(sys.argv)
    apply_dark_theme(app)

    settings = QSettings("ct_storytools", "GUI")

    window = StorytoolsWindow(settings)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()