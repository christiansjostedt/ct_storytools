# gui_utils/window_events.py
from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import QMessageBox
import re


def connect_events(window):
    window.font_combo.currentTextChanged.connect(window._update_editor_font)
    window.jobtype_combo.currentTextChanged.connect(lambda text: on_jobtype_changed(window, text))


def on_tree_selection_changed(window, selected, deselected):
    selected_indexes = window.tree.selectionModel().selectedIndexes()
    shot_count = sum(
        1 for idx in selected_indexes
        if window.tree.model().itemFromIndex(idx).data(Qt.ItemDataRole.UserRole)
    )

    if shot_count == 0:
        window.editor.setPlainText("")
        window.editor.setReadOnly(True)
        window.editor_label.setText("No shots selected")
        window.btn_run_selected.setEnabled(False)
        window.selection.clear_shot_selection()
        window.selection.update_host_checkboxes(window.hosts_layout, window.config_manager.config.get("globals", {}), None)
        return

    current = window.tree.currentIndex()

    # Auto-save previous shot if editor was modified
    if window.selection.has_shot_selected() and window.editor.document().isModified():
        prev_seq = window.selection.selected_seq
        prev_shot = window.selection.selected_shot
        if prev_seq and prev_shot:
            new_text = window.editor.toPlainText()
            success, msg = window.config_manager.save_changes(prev_seq, prev_shot, new_text)
            if success:
                print(f"[AUTO-SAVE] Saved changes to {prev_seq}/{prev_shot}")
                window.statusBar().showMessage("Auto-saved previous shot", 3000)
            else:
                print(f"[AUTO-SAVE ERROR] {msg}")
                window.statusBar().showMessage(f"Auto-save failed: {msg}", 8000)

    if shot_count == 1 and current.isValid():
        item = window.tree.model().itemFromIndex(current)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            seq, shot = data
            window.last_selected_shot = (seq, shot)
            window.selection.set_from_single_shot(seq, shot, window.config_manager.config, window.jobtype_combo)

            key = (seq, shot)
            if key in window.config_manager.shot_ranges:
                start, end = window.config_manager.shot_ranges[key]
                block_lines = window.config_manager.original_lines[start:end]

                filtered_lines = []
                for ln in block_lines:
                    stripped = ln.strip()
                    if not re.match(r'^\s*STATUS\s*[_A-Z0-9]*\s*=', stripped, re.IGNORECASE):
                        filtered_lines.append(ln)

                block_text = "".join(filtered_lines)
                window.editor.setPlainText(block_text)
                window.editor.setReadOnly(False)
                window.editor_label.setText(f"Editing shot: {shot} ({seq})")
            else:
                window.editor.setPlainText("# Block not found")
                window.editor.setReadOnly(True)

            window.btn_run_selected.setEnabled(True)
            window.selection.update_host_checkboxes(
                window.hosts_layout,
                window.config_manager.config.get("globals", {}),
                window.selection.selected_jobtype
            )
            return

    # Multi-shot or no valid current
    window.editor.setPlainText("")
    window.editor.setReadOnly(True)
    window.editor_label.setText(f"{shot_count} shots selected – editor disabled for batch")
    window.btn_run_selected.setEnabled(True)
    window.selection.update_host_checkboxes(
        window.hosts_layout,
        window.config_manager.config.get("globals", {}),
        window.selection.selected_jobtype
    )


def on_tree_current_changed(window, current, previous):
    window.tree.viewport().update()


def on_jobtype_changed(window, text):
    window.selection.on_jobtype_changed(text, window.jobtype_combo, window.tree)
    window.selection.update_host_checkboxes(
        window.hosts_layout,
        window.config_manager.config.get("globals", {}),
        window.selection.selected_jobtype
    )
    window.refresh_tree_only()