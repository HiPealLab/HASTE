# This Python file uses the following encoding: utf-8
import sys
import os
from PySide6.QtWidgets import QApplication
from PySide6.QtUiTools import QUiLoader
from PySide6.QtCore import QFile
from uiCtrl import UIHandler

def get_ui_path(filename: str) -> str:
    """
    Return the correct path to the UI file depending on whether
    the app is running as a PyInstaller bundle or a normal script.
    """
    if getattr(sys, 'frozen', False):  # Running in a PyInstaller bundle
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, filename)

if __name__ == "__main__":
    app = QApplication(sys.argv)

    loader = QUiLoader()
    ui_path = get_ui_path("mainwindow.ui")
    ui_file = QFile(ui_path)

    if not ui_file.open(QFile.ReadOnly):
        print(f"Error: Could not open UI file: {ui_path}")
        sys.exit(1)

    window = loader.load(ui_file)
    ui_file.close()

    if window is None:
        print("Error: Failed to load the UI. It may be malformed.")
        sys.exit(1)

    uiHandler = UIHandler(window)
    uiHandler.setup_ui()

    window.show()
    sys.exit(app.exec())
