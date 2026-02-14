# gui_utils/window_actions.py
from pathlib import Path
import re

from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog, QLineEdit, QMainWindow, QPlainTextEdit, QVBoxLayout, QMenu
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction  # FIXED: added QAction here

from gui_utils.tree_helpers import populate_tree, auto_resize_tree

# Import handlers for reconnect and manual call
from gui_utils.window_events import on_tree_selection_changed, on_tree_current_changed


def open_config(window):
    file_path, _ = QFileDialog.getOpenFileName(
        window, "Open Config File", "", "Text Files (*.txt);;All Files (*)"
    )
    if file_path:
        window.config_manager.config_path = Path(file_path)
        refresh_config(window)


def refresh_config(window):
    if not window.config_manager.config_path or not window.config_manager.config_path.exists():
        QMessageBox.warning(window, "Error", "No valid config file selected.")
        return

    success, msg = window.config_manager.load_config(window.config_manager.config_path)
    if not success:
        QMessageBox.critical(window, "Parse Error", f"Failed to load config:\n{msg}")
        return

    window.project_lbl.setText(f"Project: {window.config_manager.project}")
    window.statusBar().showMessage(f"Project: {window.config_manager.project} | {window.config_manager.config_path.name}")

    populate_tree(
        window.tree,
        window.config_manager.config,
        window.config_manager.project,
        window.config_manager.shot_ranges,
        window.config_manager.original_lines
    )
    auto_resize_tree(window.tree)

    # Re-connect signals after model change
    selection_model = window.tree.selectionModel()
    if selection_model is not None:
        selection_model.selectionChanged.connect(lambda s, d: on_tree_selection_changed(window, s, d))
        selection_model.currentChanged.connect(lambda c, p: on_tree_current_changed(window, c, p))

    QTimer.singleShot(0, window.tree.expandAll)

    window.act_save.setEnabled(True)
    window.btn_new_seq.setEnabled(True)
    window.btn_new_shot.setEnabled(True)
    window.btn_run_all.setEnabled(True)

    window.selection.update_host_checkboxes(
        window.hosts_layout,
        window.config_manager.config.get("globals", {}),
        window.selection.selected_jobtype
    )

    # Force initial update after load
    QTimer.singleShot(100, lambda: on_tree_selection_changed(window, None, None))


def save_changes(window):
    if not window.selection.selected_shot or not window.config_manager.config_path:
        QMessageBox.warning(window, "Cannot save", "No shot selected or no file loaded.")
        return

    new_text = window.editor.toPlainText()
    success, msg = window.config_manager.save_changes(
        window.selection.selected_seq,
        window.selection.selected_shot,
        new_text
    )
    if success:
        QMessageBox.information(window, "Saved", msg)
        refresh_config(window)
    else:
        QMessageBox.critical(window, "Save failed", msg)


def view_globals(window):
    text = window.config_manager.get_globals_text()
    dialog = QMainWindow(window)
    dialog.setWindowTitle("Globals Section")
    dialog.resize(800, 600)
    text_edit = QPlainTextEdit()
    text_edit.setReadOnly(True)
    text_edit.setFont(QFont("Consolas", 11))
    text_edit.setPlainText(text)
    text_edit.setStyleSheet("background-color: #181818; color: #e8e8e8;")
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.addWidget(text_edit)
    dialog.setCentralWidget(central)
    dialog.show()


def create_new_sequence(window):
    seq_name, ok = QInputDialog.getText(
        window, "New Sequence", "Enter sequence name/ID:",
        QLineEdit.Normal, ""
    )
    if not ok or not seq_name.strip():
        return

    seq_name = seq_name.strip()

    new_block = f"SEQUENCE={seq_name}\n\n"
    window.config_manager.original_lines.append(new_block)

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)
        refresh_config(window)
        window.statusBar().showMessage(f"Added sequence '{seq_name}'", 3000)
    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def create_new_shot(window):
    current_seq = window.selection.selected_seq
    sequences = sorted(window.config_manager.config.get(window.config_manager.project, {}).keys())

    if not sequences:
        QMessageBox.warning(window, "No sequences", "Create a sequence first.")
        return

    if current_seq:
        chosen_seq = current_seq
    else:
        chosen_seq, ok = QInputDialog.getItem(
            window, "New Shot", "Select sequence to add shot to:", sequences, 0, False
        )
        if not ok:
            return

    shot_id, ok = QInputDialog.getText(
        window, "New Shot", "Enter shot ID:",
        QLineEdit.Normal, ""
    )
    if not ok or not shot_id.strip():
        return

    shot_id = shot_id.strip()

    insert_pos = len(window.config_manager.original_lines)
    in_seq = False
    for i in range(len(window.config_manager.original_lines) - 1, -1, -1):
        line = window.config_manager.original_lines[i].strip()
        if line.startswith("SEQUENCE="):
            if line[9:].strip() == chosen_seq:
                in_seq = True
            else:
                if in_seq:
                    break
        if in_seq and line == "!---------":
            insert_pos = i + 1
            break

    new_block = f"\n!---------\nSHOT={shot_id}\nNAME=New Shot\n# Add your job settings here\n\n"
    window.config_manager.original_lines.insert(insert_pos, new_block)

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)
        refresh_config(window)
        window.statusBar().showMessage(f"Added shot '{shot_id}' under '{chosen_seq}'", 3000)
    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def run_all_threaded(window):
    jobtype = window.selection.get_active_jobtype()
    window.executor.run_all_threaded(
        window.config_manager.config_path,
        [jobtype],
        window.selection.selected_seq
    )


def run_selected_threaded(window):
    jobtype = window.selection.get_active_jobtype()
    window.executor.run_selected_threaded(
        window.config_manager.config,
        [jobtype],
        window.selection.selected_seq,
        window.selection.selected_shot
    )


def show_context_menu(window, position):
    selected_indexes = window.tree.selectionModel().selectedIndexes()
    if not selected_indexes:
        return

    menu = QMenu(window)

    shots = []
    sequences = set()

    for idx in selected_indexes:
        item = window.tree.model().itemFromIndex(idx)
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            seq, shot = data
            shots.append((seq, shot))
        else:
            sequences.add(item.text())

    if shots:
        run_menu = menu.addMenu(f"Run {len(shots)} shot(s) as...")

        all_jobtypes = set()
        for seq, shot in shots:
            shot_data = window.config_manager.config.get(
                window.config_manager.project, {}
            ).get(seq, {}).get(shot, {})
            for sub in shot_data.values():
                for key in ['JOBTYPE', 'IMAGE_JOBTYPE', 'VIDEO_JOBTYPE']:
                    if key in sub:
                        jts = [jt.strip() for jt in sub[key].split(',') if jt.strip()]
                        all_jobtypes.update(jts)

        if not all_jobtypes:
            all_jobtypes = {"(no jobtype detected)"}

        for jt in sorted(all_jobtypes):
            act = QAction(f"Run as {jt}", window)
            act.triggered.connect(lambda checked=False, j=jt: _run_multi_shots(window, shots, j))
            run_menu.addAction(act)

        current_jt = window.selection.selected_jobtype
        if current_jt and current_jt != "Select Jobtype":
            status_menu = menu.addMenu(f"Status for {current_jt}")

            act_done = QAction("Mark Done", window)
            act_done.triggered.connect(lambda: _set_multi_status(window, shots, current_jt, "done"))
            status_menu.addAction(act_done)

            act_run = QAction("Mark Run", window)
            act_run.triggered.connect(lambda: _set_multi_status(window, shots, current_jt, "run"))
            status_menu.addAction(act_run)

            act_changes = QAction("Mark Changes", window)
            act_changes.triggered.connect(lambda: _set_multi_status(window, shots, current_jt, "changes"))
            status_menu.addAction(act_changes)

            act_omit = QAction("Mark Omit", window)
            act_omit.triggered.connect(lambda: _set_multi_status(window, shots, current_jt, "omit"))
            status_menu.addAction(act_omit)

            act_not_started = QAction("Mark Not Started", window)
            act_not_started.triggered.connect(lambda: _set_multi_status(window, shots, current_jt, "not_started"))
            status_menu.addAction(act_not_started)

        act_enable = QAction("Set Enabled", window)
        act_enable.triggered.connect(lambda: _set_multi_enabled(window, shots))
        menu.addAction(act_enable)

        act_disable = QAction("Set Disabled", window)
        act_disable.triggered.connect(lambda: _set_multi_disabled(window, shots))
        menu.addAction(act_disable)

        act_delete = QAction(f"Delete {len(shots)} shot(s)", window)
        act_delete.triggered.connect(lambda: _delete_multi_shots(window, shots))
        menu.addAction(act_delete)

    if sequences:
        seq_menu = menu.addMenu(f"Run {len(sequences)} sequence(s) as...")
        for jt in JOBTYPE_LIST[1:]:
            act = QAction(f"Run as {jt}", window)
            act.triggered.connect(
                lambda checked=False, j=jt: [
                    _run_sequence_with_jobtype(window, s, j) for s in sequences
                ]
            )
            seq_menu.addAction(act)

    if menu.actions():
        menu.exec(window.tree.viewport().mapToGlobal(position))


def _run_multi_shots(window, shots, jobtype):
    for seq, shot in shots:
        _run_shot_with_jobtype(window, seq, shot, jobtype)


def _run_shot_with_jobtype(window, seq, shot, jobtype):
    window.selection.selected_seq = seq
    window.selection.selected_shot = shot
    window.selection.selected_jobtype = jobtype
    window.jobtype_combo.setCurrentText(jobtype)
    run_selected_threaded(window)


def _run_sequence_with_jobtype(window, seq, jobtype):
    window.selection.selected_seq = seq
    window.selection.selected_jobtype = jobtype
    window.jobtype_combo.setCurrentText(jobtype)
    run_all_threaded(window)


def _set_multi_status(window, shots, jobtype, status_val):
    if not shots or not jobtype:
        return

    changes = []
    for seq, shot in shots:
        key = (seq, shot)
        if key not in window.config_manager.shot_ranges:
            continue
        start, end = window.config_manager.shot_ranges[key]
        block_lines = window.config_manager.original_lines[start:end]

        status_key = f"STATUS_{jobtype.upper().replace('_', '')}"

        new_block = []
        added = False
        for ln in block_lines:
            if status_key in ln:
                if status_val != "not_started":
                    new_block.append(f"{status_key}={status_val}\n")
                    added = True
            else:
                new_block.append(ln)

        if not added and status_val != "not_started":
            new_block.append(f"{status_key}={status_val}\n")

        new_text = "".join(new_block)
        changes.append((start, end, new_text))

    if not changes:
        window.statusBar().showMessage("No shots affected", 3000)
        return

    changes.sort(key=lambda x: x[0], reverse=True)
    for start, end, new_text in changes:
        window.config_manager.original_lines[start:end] = [new_text]

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)
        refresh_config(window)
        window.statusBar().showMessage(f"Marked {len(changes)} shot(s) as {status_val}", 3000)
    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _set_multi_enabled(window, shots):
    if not shots:
        return

    changes = []
    for seq, shot in shots:
        key = (seq, shot)
        if key not in window.config_manager.shot_ranges:
            continue
        start, end = window.config_manager.shot_ranges[key]
        block_lines = window.config_manager.original_lines[start:end]

        is_disabled = any(
            re.match(r'^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$', ln.strip(), re.IGNORECASE)
            for ln in block_lines
        )

        if is_disabled:
            new_block = [
                ln for ln in block_lines
                if not re.match(r'^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$', ln.strip(), re.IGNORECASE)
            ]
            new_text = "".join(new_block)
            changes.append((start, end, new_text))

    if not changes:
        window.statusBar().showMessage("No disabled shots to enable", 3000)
        return

    changes.sort(key=lambda x: x[0], reverse=True)
    for start, end, new_text in changes:
        window.config_manager.original_lines[start:end] = [new_text]

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)
        refresh_config(window)
        window.statusBar().showMessage(f"Enabled {len(changes)} shot(s)", 3000)
    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _set_multi_disabled(window, shots):
    if not shots:
        return

    changes = []
    for seq, shot in shots:
        key = (seq, shot)
        if key not in window.config_manager.shot_ranges:
            continue
        start, end = window.config_manager.shot_ranges[key]
        block_lines = window.config_manager.original_lines[start:end]

        is_disabled = any(
            re.match(r'^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$', ln.strip(), re.IGNORECASE)
            for ln in block_lines
        )

        if not is_disabled:
            new_block = block_lines[:]
            if new_block and not new_block[-1].strip():
                new_block.insert(-1, "DISABLED=1\n")
            else:
                new_block.append("DISABLED=1\n")
            new_text = "".join(new_block)
            changes.append((start, end, new_text))

    if not changes:
        window.statusBar().showMessage("All selected shots already disabled", 3000)
        return

    changes.sort(key=lambda x: x[0], reverse=True)
    for start, end, new_text in changes:
        window.config_manager.original_lines[start:end] = [new_text]

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)
        refresh_config(window)
        window.statusBar().showMessage(f"Disabled {len(changes)} shot(s)", 3000)
    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _delete_multi_shots(window, shots):
    if not shots:
        return
    reply = QMessageBox.question(
        window,
        "Confirm Delete",
        f"Delete {len(shots)} shot(s)? This cannot be undone.",
        QMessageBox.Yes | QMessageBox.No
    )
    if reply == QMessageBox.Yes:
        QMessageBox.information(window, "Not implemented", "Multi-shot delete not yet implemented.\n(Coming soon)")