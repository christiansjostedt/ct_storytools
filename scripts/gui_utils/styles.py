# gui_utils/styles.py
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt


def apply_dark_theme(app):
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(28, 28, 28))
    palette.setColor(QPalette.WindowText, QColor(225, 225, 225))
    palette.setColor(QPalette.Base, QColor(22, 22, 22))
    palette.setColor(QPalette.AlternateBase, QColor(32, 32, 32))
    palette.setColor(QPalette.ToolTipBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ToolTipText, Qt.white)
    palette.setColor(QPalette.Text, QColor(235, 235, 235))
    palette.setColor(QPalette.Button, QColor(40, 40, 40))
    palette.setColor(QPalette.ButtonText, QColor(225, 225, 225))
    palette.setColor(QPalette.Highlight, QColor(70, 130, 180))
    palette.setColor(QPalette.HighlightedText, Qt.white)
    palette.setColor(QPalette.Active, QPalette.Window, QColor(18, 18, 18))
    palette.setColor(QPalette.Active, QPalette.Highlight, QColor(60, 120, 170))
    palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.Text, QColor(120, 120, 120))
    palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(120, 120, 120))
    app.setPalette(palette)
    app.setStyle("Fusion")


# Reusable style strings
TREE_STYLE = """
    QTreeView {
        background-color: #1e1e1e;
        color: #e0e0e0;
        border: none;
        selection-background-color: #4a6a8a;
        selection-color: white;
    }
    QTreeView::item:selected {
        background-color: #4a6a8a;
        color: white;
    }
    QTreeView::item:selected:!active {
        background-color: #3a5a7a;
        color: white;
    }
    /* Very strong rule: any item with red foreground keeps it even when selected */
    QTreeView::item[foreground="rgb(220,80,80)"] {
        color: rgb(220,80,80) !important;
    }
    QTreeView::item:selected[foreground="rgb(220,80,80)"] {
        color: rgb(220,80,80) !important;
        background-color: #4a6a8a;   /* keep selection bg, but force text red */
    }
    QTreeView::item:selected[foreground="rgb(220, 80, 80)"] {
        color: rgb(220,80,80) !important;
    }
"""

EDITOR_STYLE = """
    QPlainTextEdit {
        background-color: #181818;
        color: #e8e8e8;
        border: 1px solid #333333;
    }
"""

LIST_STYLE = """
    QListWidget {
        background-color: #181818;
        color: #e8e8e8;
        border: 1px solid #333333;
    }
"""

GROUPBOX_STYLE = """
    QGroupBox { 
        font-weight: bold; 
        color: #c0c0c0; 
        border: 1px solid #444; 
        border-radius: 4px; 
        margin-top: 12px; 
    }
    QGroupBox::title { 
        subcontrol-origin: margin; 
        subcontrol-position: top left; 
        padding: 0 6px; 
    }
"""