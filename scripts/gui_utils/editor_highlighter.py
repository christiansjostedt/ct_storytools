# gui_utils/editor_highlighter.py
from PySide6.QtGui import QSyntaxHighlighter, QTextCharFormat, QColor, QFont
from PySide6.QtCore import QRegularExpression, QRegularExpressionMatchIterator
import hashlib


class ShotEditorHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.formats = {}  # cache per variable name

    def get_format_for_variable(self, var_name):
        if var_name not in self.formats:
            # Original color logic – deterministic but good spread
            h = hashlib.md5(var_name.encode()).hexdigest()
            r = int(h[0:2], 16) % 128 + 100  # 100-227 range
            g = int(h[2:4], 16) % 128 + 100
            b = int(h[4:6], 16) % 128 + 100
            color = QColor(r, g, b)

            fmt = QTextCharFormat()
            fmt.setForeground(color)
            fmt.setFontWeight(QFont.Weight.Bold)
            self.formats[var_name] = fmt

        return self.formats[var_name]

    def highlightBlock(self, text):
        # Match lines like VARIABLE=anything
        pattern = QRegularExpression(r"^([A-Z_]+)=(.*)$")
        iterator = pattern.globalMatch(text)

        while iterator.hasNext():
            match = iterator.next()
            var_name = match.captured(1)
            var_start = match.capturedStart()
            var_len = match.capturedLength()

            # Highlight variable name
            self.setFormat(var_start, len(var_name), self.get_format_for_variable(var_name))

            # Highlight value with same color (normal weight)
            value_fmt = QTextCharFormat(self.get_format_for_variable(var_name))
            value_fmt.setFontWeight(QFont.Weight.Normal)
            value_start = match.capturedStart(2)
            value_len = match.capturedLength(2)
            self.setFormat(value_start, value_len, value_fmt)