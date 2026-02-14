# gui_utils/window_events.py
from PySide6.QtCore import QTimer, Qt


def connect_events(window):
    window.btn_new_seq.clicked.connect(lambda: create_new_sequence(window))
    window.btn_new_shot.clicked.connect(lambda: create_new_shot(window))
    window.btn_run_all.clicked.connect(lambda: run_all_threaded(window))
    window.btn_run_selected.clicked.connect(lambda: run_selected_threaded(window))
    window.font_combo.currentTextChanged.connect(window._update_editor_font)
    window.jobtype_combo.currentTextChanged.connect(lambda text: on_jobtype_changed(window, text))


def on_tree_selection_changed(window, selected, deselected):
    print("on_tree_selection_changed triggered")

    selected_indexes = window.tree.selectionModel().selectedIndexes()
    shot_count = sum(
        1 for idx in selected_indexes
        if window.tree.model().itemFromIndex(idx).data(Qt.ItemDataRole.UserRole)
    )
    print(f"  shot_count: {shot_count}")

    if shot_count == 0:
        print("  No shots selected - clearing editor")
        window.editor.setPlainText("")
        window.editor.setReadOnly(True)
        window.editor_label.setText("No shots selected")
        window.btn_run_selected.setEnabled(False)
        window.selection.clear_shot_selection()
        window.selection.update_host_checkboxes(window.hosts_layout, window.config_manager.config.get("globals", {}), None)
        return

    current = window.tree.currentIndex()
    print(f"  Current index valid: {current.isValid()}")

    if shot_count == 1 and current.isValid():
        item = window.tree.model().itemFromIndex(current)
        data = item.data(Qt.ItemDataRole.UserRole)
        print(f"  Selected item data: {data}")
        if data:
            seq, shot = data
            print(f"  Updating editor for shot {shot} in seq {seq}")
            window.last_selected_shot = (seq, shot)
            window.selection.set_from_single_shot(seq, shot, window.config_manager.config, window.jobtype_combo)

            key = (seq, shot)
            if key in window.config_manager.shot_ranges:
                start, end = window.config_manager.shot_ranges[key]
                block_text = "".join(window.config_manager.original_lines[start:end])
                print(f"  Setting editor text (length {len(block_text)})")
                window.editor.setPlainText(block_text)
                window.editor.setReadOnly(False)
                window.editor_label.setText(f"Editing shot: {shot} ({seq})")
            else:
                print("  Block not found")
                window.editor.setPlainText("# Block not found")
                window.editor.setReadOnly(True)

            window.btn_run_selected.setEnabled(True)
            window.selection.update_host_checkboxes(
                window.hosts_layout,
                window.config_manager.config.get("globals", {}),
                window.selection.selected_jobtype
            )
            return

    print("  Multi-shot or no valid current - disabling editor")
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