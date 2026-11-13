from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

BG = "#0e1318"
SURFACE = "#171e26"
SURFACE_ALT = "#1c2530"
LINE = "#2c3846"
TEXT = "#e7eef5"
MUTED = "#8b99aa"
ACCENT = "#d7f26a"
SELECT = "#243140"
DANGER = "#e07a6a"
OK = "#8fbf9a"
WARN = "#e2c56a"

STYLESHEET = f"""
QMainWindow, QDialog {{
    background: {BG};
    color: {TEXT};
}}
QWidget {{
    color: {TEXT};
    background: transparent;
}}
QMainWindow > QWidget {{
    background: {BG};
}}
QLabel#headline {{
    font-size: 18px;
    font-weight: 600;
    color: {TEXT};
}}
QLabel#title {{
    font-size: 15px;
    font-weight: 600;
}}
QLabel#section {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#muted {{
    color: {MUTED};
}}
QLabel#banner {{
    background: #1a2214;
    color: #d5e7a4;
    border: none;
    border-left: 3px solid {ACCENT};
    padding: 8px 12px;
}}
QLabel#thumb {{
    background: #121920;
    color: {MUTED};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
QFrame#quality {{
    background: #121920;
    border: 1px solid {LINE};
    border-radius: 8px;
}}
QFrame#quality QRadioButton {{
    background: transparent;
    color: {MUTED};
    border: none;
    border-radius: 6px;
    padding: 6px 14px;
    spacing: 0px;
}}
QFrame#quality QRadioButton::indicator {{
    width: 0px;
    height: 0px;
}}
QFrame#quality QRadioButton:hover {{
    color: {TEXT};
}}
QFrame#quality QRadioButton:checked {{
    background: {SELECT};
    color: {TEXT};
}}
QLineEdit, QSpinBox, QPlainTextEdit, QListWidget, QTableWidget {{
    background: #121920;
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 8px 10px;
    selection-background-color: {SELECT};
    selection-color: {TEXT};
}}
QLineEdit#url {{
    min-height: 20px;
    padding: 10px 14px;
    font-size: 14px;
    border-radius: 10px;
}}
QLineEdit:focus, QSpinBox:focus, QPlainTextEdit:focus {{
    border-color: #8ea05a;
}}
QTableView {{
    background: {SURFACE};
    alternate-background-color: {SURFACE_ALT};
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: {SELECT};
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: {SURFACE};
    color: {MUTED};
    border: none;
    border-bottom: 1px solid {LINE};
    padding: 8px 10px;
    font-weight: 600;
}}
QTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    border: 1px solid transparent;
    border-radius: 7px;
    padding: 6px 16px;
    margin-right: 4px;
    font-weight: 600;
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QTabBar::tab:selected {{
    background: {SELECT};
    color: {TEXT};
    border-color: {LINE};
}}
QTableView::item {{
    padding: 4px 8px;
    border: none;
}}
QPushButton {{
    background: transparent;
    color: {TEXT};
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton:hover {{
    background: {SELECT};
    border-color: #3d4d60;
}}
QPushButton:pressed {{
    background: #1b2836;
}}
QPushButton:disabled {{
    color: #5d6b7c;
    background: transparent;
    border-color: #24303c;
}}
QPushButton#primary {{
    background: {ACCENT};
    color: #17200a;
    border: none;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: #e4f98a;
}}
QPushButton#primary:pressed {{
    background: #c6e25a;
}}
QPushButton#primary:disabled {{
    background: #3d4a28;
    color: #8b9474;
}}
QCheckBox {{
    spacing: 8px;
    color: {TEXT};
}}
QMenuBar {{
    background: {BG};
    color: {MUTED};
    spacing: 2px;
}}
QMenuBar::item {{
    padding: 6px 10px;
    background: transparent;
}}
QMenuBar::item:selected {{
    color: {TEXT};
    background: {SELECT};
    border-radius: 6px;
}}
QMenu {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {SELECT};
}}
QStatusBar {{
    background: {BG};
    color: {MUTED};
}}
QSplitter::handle {{
    background: {BG};
    height: 8px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: #3a4858;
    min-height: 28px;
    border-radius: 4px;
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
    height: 0;
}}
QToolTip {{
    background: {SURFACE};
    color: {TEXT};
    border: 1px solid {LINE};
    padding: 6px;
}}
QDialogButtonBox QPushButton {{
    min-width: 72px;
}}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(BG))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor("#121920"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(SURFACE_ALT))
    palette.setColor(QPalette.ColorRole.Text, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(SELECT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#667588"))
    app.setPalette(palette)
    app.setStyleSheet(STYLESHEET)
