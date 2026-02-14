# gui_utils/tree_helpers.py (full)
import re

from PySide6.QtGui import (
    QStandardItem,
    QFont,
    QColor,
    QFontMetrics,
    QStandardItemModel
)
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHeaderView


def populate_tree(tree, config, project, shot_ranges, original_lines):
    model = QStandardItemModel()
    root = model.invisibleRootItem()

    sequences = sorted(config.get(project, {}).keys())

    for seq in sequences:
        seq_item = QStandardItem(seq)
        seq_item.setEditable(False)
        seq_item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        shots = sorted(config.get(project, {}).get(seq, {}).keys())

        for shot_id in shots:
            shot_data = config[project][seq].get(shot_id, {})
            name = ""
            for sub in shot_data.values():
                if "NAME" in sub:
                    name = sub["NAME"]
                    break
            display = f"{shot_id} – {name}" if name else shot_id

            shot_item = QStandardItem(display)
            shot_item.setEditable(False)
            shot_item.setData((seq, shot_id), Qt.ItemDataRole.UserRole)

            key = (seq, shot_id)
            if key in shot_ranges:
                start, end = shot_ranges[key]
                block = original_lines[start:end]
                is_disabled = any(
                    re.match(r"^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$", ln.strip(), re.IGNORECASE)
                    for ln in block
                )
                if is_disabled:
                    shot_item.setForeground(QColor(220, 80, 80))

            current_jobtype = tree.window().selection.selected_jobtype
            if current_jobtype and current_jobtype != "Select Jobtype":
                status_key = f"STATUS_{current_jobtype.upper().replace('_', '')}"
                for sub in shot_data.values():
                    if status_key in sub:
                        status_val = sub[status_key].strip().lower()
                        if status_val == "done":
                            shot_item.setForeground(QColor(100, 180, 255))  # blue
                        elif status_val == "run":
                            shot_item.setForeground(QColor(255, 140, 0))   # orange
                        elif status_val == "changes":
                            shot_item.setForeground(QColor(200, 0, 255))   # purple
                        elif status_val == "omit":
                            shot_item.setForeground(QColor(128, 128, 128)) # dark grey
                        elif status_val == "not_started":
                            shot_item.setForeground(QColor(224, 224, 224))
                        break

            seq_item.appendRow(shot_item)

        root.appendRow(seq_item)

    tree.setModel(model)
    tree.expandAll()


def auto_resize_tree(tree):
    if not tree.model():
        return
    header = tree.header()
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    header.resizeSections(QHeaderView.ResizeToContents)

    fm = QFontMetrics(tree.font())
    max_width = 400

    def measure(item, level=0):
        nonlocal max_width
        text = item.text() or ""
        indent = level * 20
        width = fm.horizontalAdvance(text) + indent + 80
        max_width = max(max_width, width)
        for r in range(item.rowCount()):
            child = item.child(r)
            if child:
                measure(child, level + 1)

    root = tree.model().invisibleRootItem()
    for r in range(root.rowCount()):
        measure(root.child(r))

    tree.setColumnWidth(0, max_width)
    header.setStretchLastSection(False)
    header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
    tree.updateGeometry()