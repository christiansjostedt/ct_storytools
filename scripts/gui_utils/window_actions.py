# gui_utils/window_actions.py
from pathlib import Path
import re

from PySide6.QtWidgets import QFileDialog, QMessageBox, QInputDialog, QLineEdit, QMainWindow, QPlainTextEdit, QVBoxLayout, QMenu, QWidget
from PySide6.QtCore import QTimer, Qt, QItemSelectionModel
from PySide6.QtGui import QAction, QFont

from gui_utils.tree_helpers import populate_tree, auto_resize_tree

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
        window, "New Sequence", "Enter new sequence name (e.g. TEST, SQ004):",
        QLineEdit.Normal, ""
    )
    if not ok or not (seq_name := seq_name.strip()):
        return

    shot_id, ok = QInputDialog.getText(
        window, "Initial Shot", f"Enter initial shot ID for '{seq_name}' (e.g. 001):",
        QLineEdit.Normal, "001"
    )
    if not ok or not (shot_id := shot_id.strip()):
        return

    project = window.config_manager.project
    if seq_name in window.config_manager.config.get(project, {}):
        QMessageBox.warning(window, "Duplicate", f"Sequence '{seq_name}' already exists.")
        return

    if shot_id in window.config_manager.config.get(project, {}).get(seq_name, {}):
        QMessageBox.warning(window, "Duplicate", f"Shot '{shot_id}' already exists in '{seq_name}'.")
        return

    new_block_lines = [
        "!---------\n",
        f"SEQUENCE={seq_name}\n",
        f"SHOT={shot_id}\n",
        f"NAME=sh{shot_id}\n",
        "AUDIO_PROMPT=\n",
        "ENVIRONMENT_PROMPT=\n",
        "ACTION_PROMPT=\n",
        "CAMERA_PROMPT=\n",
        "IMG_PROMPT=\n",
        "\n",
    ]

    window.config_manager.original_lines += new_block_lines

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)

        refresh_config(window)
        window.statusBar().showMessage(f"Sequence '{seq_name}' created with initial shot '{shot_id}'", 5000)

        window.last_selected_shot = (seq_name, shot_id)
        QTimer.singleShot(200, lambda: _select_new_shot(window, seq_name, shot_id))

    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def create_new_shot(window):
    project = window.config_manager.project
    sequences = sorted(window.config_manager.config.get(project, {}).keys())

    if not sequences:
        QMessageBox.warning(window, "No Sequences", "Create a sequence first (it will include an initial shot).")
        return

    target_seq = window.selection.selected_seq

    if window.selection.selected_shot and window.selection.selected_seq:
        target_seq = window.selection.selected_seq

    if not target_seq:
        target_seq, ok = QInputDialog.getItem(
            window, "New Shot", "Select sequence to add shot to:",
            sequences, 0, False
        )
        if not ok or not target_seq:
            return

    default_id = "NEW"
    shot_id, ok = QInputDialog.getText(
        window, "New Shot", f"Enter shot ID for sequence '{target_seq}':",
        QLineEdit.Normal, default_id
    )
    if not ok or not (shot_id := shot_id.strip()):
        return

    if shot_id in window.config_manager.config.get(project, {}).get(target_seq, {}):
        QMessageBox.warning(window, "Duplicate", f"Shot '{shot_id}' already exists in '{target_seq}'.")
        return

    insert_line = len(window.config_manager.original_lines)

    if window.selection.selected_shot:
        key = (target_seq, window.selection.selected_shot)
        if key in window.config_manager.shot_ranges:
            _, end = window.config_manager.shot_ranges[key]
            insert_line = end
    else:
        last_end = None
        for (s, sh), (st, en) in window.config_manager.shot_ranges.items():
            if s == target_seq:
                last_end = en
        if last_end is not None:
            insert_line = last_end

    new_block_lines = [
        "!---------\n",
        f"SEQUENCE={target_seq}\n",
        f"SHOT={shot_id}\n",
        f"NAME=sh{shot_id}\n",
        "AUDIO_PROMPT=\n",
        "ENVIRONMENT_PROMPT=\n",
        "ACTION_PROMPT=\n",
        "CAMERA_PROMPT=\n",
        "IMG_PROMPT=\n",
        "\n",
    ]

    window.config_manager.original_lines[insert_line:insert_line] = new_block_lines

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(window.config_manager.original_lines)

        refresh_config(window)

        window.last_selected_shot = (target_seq, shot_id)
        window.statusBar().showMessage(f"Shot '{shot_id}' added to sequence '{target_seq}'", 5000)

        QTimer.singleShot(250, lambda: _select_new_shot(window, target_seq, shot_id))

    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _select_new_shot(window, seq_name, shot_id):
    model = window.tree.model()
    root = model.invisibleRootItem()
    found = False
    for i in range(root.rowCount()):
        seq_item = root.child(i)
        if seq_item.text() == seq_name:
            for j in range(seq_item.rowCount()):
                shot_item = seq_item.child(j)
                data = shot_item.data(Qt.ItemDataRole.UserRole)
                if data and data[1] == shot_id:
                    index = model.indexFromItem(shot_item)
                    window.tree.setCurrentIndex(index)
                    window.tree.selectionModel().select(index, QItemSelectionModel.ClearAndSelect | QItemSelectionModel.Rows)
                    QTimer.singleShot(50, lambda: on_tree_selection_changed(window, None, None))
                    found = True
                    break
            if found:
                break
    if not found:
        window.statusBar().showMessage(f"Shot '{shot_id}' added to '{seq_name}', but auto-select failed – click it manually", 10000)


def show_context_menu(window, pos):
    index = window.tree.indexAt(pos)
    if not index.isValid():
        return

    item = window.tree.model().itemFromIndex(index)
    if not item:
        return

    menu = QMenu(window)

    data = item.data(Qt.ItemDataRole.UserRole)
    is_shot = bool(data)

    # Get ALL selected shots (not just right-clicked)
    selected_indexes = window.tree.selectionModel().selectedIndexes()
    selected_shots = []
    for idx in selected_indexes:
        item = window.tree.model().itemFromIndex(idx)
        if item:
            item_data = item.data(Qt.ItemDataRole.UserRole)
            if item_data and isinstance(item_data, tuple) and len(item_data) == 2:
                selected_shots.append(item_data)

    selected_shots = list(set(selected_shots))  # dedup

    if is_shot and selected_shots:
        seq, shot = data

        run_menu = menu.addMenu("Run as...")
        for i in range(window.jobtype_combo.count()):
            jt = window.jobtype_combo.itemText(i)
            if jt != "Select Jobtype" and jt.strip():
                action = QAction(jt, window)
                action.triggered.connect(lambda _, j=jt: window.run_manager.run_selected_shots())  # ← use full selection + filtered logic
                run_menu.addAction(action)

        status_menu = menu.addMenu("Mark status")
        for status in ["not_started", "run", "done", "changes", "omit"]:
            action = QAction(status.capitalize(), window)
            action.triggered.connect(lambda _, s=status: _mark_status(window, selected_shots, s))
            status_menu.addAction(action)

        enable_action = QAction("Enable", window)
        enable_action.triggered.connect(lambda: _set_multi_enabled(window, selected_shots))
        disable_action = QAction("Disable", window)
        disable_action.triggered.connect(lambda: _set_multi_disabled(window, selected_shots))

        menu.addAction(enable_action)
        menu.addAction(disable_action)

        delete_action = QAction(f"Delete shot{'s' if len(selected_shots) > 1 else ''}", window)
        delete_action.triggered.connect(lambda: _delete_multi_shots(window, selected_shots))
        menu.addAction(delete_action)

    else:
        seq_name = item.text()
        add_shot_action = QAction("Add new shot here", window)
        add_shot_action.triggered.connect(lambda: create_new_shot(window))
        menu.addAction(add_shot_action)

        delete_seq_action = QAction("Delete sequence (stub)", window)
        delete_seq_action.setEnabled(False)
        menu.addAction(delete_seq_action)

    menu.exec(window.tree.viewport().mapToGlobal(pos))


def _mark_status(window, shots, status_val):
    if not shots:
        return

    jobtype = window.selection.selected_jobtype
    if not jobtype or jobtype == "Select Jobtype":
        QMessageBox.warning(window, "No Jobtype", "Please select a jobtype first.")
        return

    status_key = f"STATUS_{jobtype.upper().replace('_', '')}"

    original_lines = window.config_manager.original_lines[:]
    original_ranges = window.config_manager.shot_ranges.copy()

    affected_ranges = sorted(
        [(original_ranges.get((seq, shot), None), (seq, shot)) for seq, shot in shots],
        key=lambda x: x[0][0] if x[0] else 999999
    )

    new_lines = []
    current_pos = 0
    affected_count = 0

    for (orig_start, orig_end), (seq, shot) in affected_ranges:
        if orig_start is None or orig_end is None:
            continue

        new_lines.extend(original_lines[current_pos:orig_start])

        block_lines = original_lines[orig_start:orig_end]

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
            if new_block and not new_block[-1].strip():
                new_block.insert(-1, f"{status_key}={status_val}\n")
            else:
                new_block.append(f"{status_key}={status_val}\n")

        new_lines.extend(new_block)
        current_pos = orig_end
        affected_count += 1

    new_lines.extend(original_lines[current_pos:])

    if affected_count == 0:
        window.statusBar().showMessage("No shots affected", 3000)
        return

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(new_lines)

        window.config_manager.original_lines = new_lines
        refresh_config(window)
        window.statusBar().showMessage(f"Marked {affected_count} shot(s) as {status_val}", 3000)

    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _set_multi_enabled(window, shots):
    if not shots:
        return

    original_lines = window.config_manager.original_lines[:]
    original_ranges = window.config_manager.shot_ranges.copy()

    affected_ranges = sorted(
        [(original_ranges.get((seq, shot), None), (seq, shot)) for seq, shot in shots],
        key=lambda x: x[0][0] if x[0] else 999999
    )

    new_lines = []
    current_pos = 0
    affected_count = 0

    for (orig_start, orig_end), (seq, shot) in affected_ranges:
        if orig_start is None or orig_end is None:
            continue

        new_lines.extend(original_lines[current_pos:orig_start])

        block_lines = original_lines[orig_start:orig_end]

        is_disabled = any(
            re.match(r'^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$', ln.strip(), re.IGNORECASE)
            for ln in block_lines
        )

        if is_disabled:
            new_block = [
                ln for ln in block_lines
                if not re.match(r'^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$', ln.strip(), re.IGNORECASE)
            ]
            new_lines.extend(new_block)
            affected_count += 1
        else:
            new_lines.extend(block_lines)

        current_pos = orig_end

    new_lines.extend(original_lines[current_pos:])

    if affected_count == 0:
        window.statusBar().showMessage("No disabled shots to enable", 3000)
        return

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(new_lines)

        window.config_manager.original_lines = new_lines
        refresh_config(window)
        window.statusBar().showMessage(f"Enabled {affected_count} shot(s)", 3000)

    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _set_multi_disabled(window, shots):
    if not shots:
        return

    original_lines = window.config_manager.original_lines[:]
    original_ranges = window.config_manager.shot_ranges.copy()

    affected_ranges = sorted(
        [(original_ranges.get((seq, shot), None), (seq, shot)) for seq, shot in shots],
        key=lambda x: x[0][0] if x[0] else 999999
    )

    new_lines = []
    current_pos = 0
    affected_count = 0

    for (orig_start, orig_end), (seq, shot) in affected_ranges:
        if orig_start is None or orig_end is None:
            continue

        new_lines.extend(original_lines[current_pos:orig_start])

        block_lines = original_lines[orig_start:orig_end]

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
            new_lines.extend(new_block)
            affected_count += 1
        else:
            new_lines.extend(block_lines)

        current_pos = orig_end

    new_lines.extend(original_lines[current_pos:])

    if affected_count == 0:
        window.statusBar().showMessage("All selected shots already disabled", 3000)
        return

    try:
        with open(window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
            f.writelines(new_lines)

        window.config_manager.original_lines = new_lines
        refresh_config(window)
        window.statusBar().showMessage(f"Disabled {affected_count} shot(s)", 3000)

    except Exception as e:
        QMessageBox.critical(window, "Save failed", str(e))


def _delete_multi_shots(window, shots):
    if not shots:
        return
    reply = QMessageBox.question(
        window,
        "Confirm Delete",
        f"Delete {len(shots)} shot(s)? This cannot be undone.\n\nSelected shots:\n" + "\n".join([f"{seq}/{shot}" for seq, shot in shots]),
        QMessageBox.Yes | QMessageBox.No
    )
    if reply == QMessageBox.Yes:
        QMessageBox.information(window, "Not implemented", "Multi-shot delete not yet implemented.\n(Coming soon)")