# gui_utils/run_manager.py
from pathlib import Path
from datetime import datetime
import re

from PySide6.QtCore import Qt

from gui_utils.constants import JOBTYPE_HOST_MAPPING
from launcher import run_storytools_execution
import parser


class RunManager:
    def __init__(self, window):
        self.window = window

    def _get_checked_hosts_str(self, jobtype: str) -> str:
        checked = self.window.selection.host_selections.get(jobtype, set())
        return ','.join(sorted(h.strip() for h in checked if h.strip()))

    def _override_host_in_line(self, line: str, host_key: str, new_value: str) -> str:
        stripped = line.strip()
        if not stripped or '=' not in line:
            return line

        key_part, _, _ = line.partition('=')
        key_stripped = key_part.strip()

        if key_stripped == host_key or key_stripped == f"{host_key}_HOSTS":
            indent = key_part[:len(key_part) - len(key_part.lstrip())]
            return f"{indent}{key_stripped}={new_value if new_value else ''}\n"
        return line

    def _is_shot_skippable(self, seq, shot, jobtype):
        key = (seq, shot)
        if key not in self.window.config_manager.shot_ranges:
            return True, "Range missing"

        start, end = self.window.config_manager.shot_ranges[key]
        block_lines = self.window.config_manager.original_lines[start:end]

        is_disabled = any(
            re.match(r'^\s*DISABLED\s*=\s*(1|yes|true|on)\s*$', ln.strip(), re.IGNORECASE)
            for ln in block_lines
        )
        if is_disabled:
            return True, "Disabled"

        status_key = f"STATUS_{jobtype.upper().replace('_', '')}"
        is_omitted = any(
            re.match(rf'^\s*{status_key}\s*=\s*omit\s*$', ln.strip(), re.IGNORECASE)
            for ln in block_lines
        )
        if is_omitted:
            return True, "Omitted"

        return False, ""

    def _build_shot_block(self, seq, shot, host_key=None, host_str=''):
        key = (seq, shot)
        if key not in self.window.config_manager.shot_ranges:
            return []

        start, end = self.window.config_manager.shot_ranges[key]
        block = self.window.config_manager.original_lines[start:end]

        if not host_key:
            return block

        return [self._override_host_in_line(ln, host_key, host_str) for ln in block]

    def create_temp_config(self, seq, shot, jobtype: str, use_editor: bool = False) -> tuple[Path | None, str]:
        skip, reason = self._is_shot_skippable(seq, shot, jobtype)
        if skip:
            return None, f"Skipped {seq}/{shot}: {reason}"

        globals_dict = self.window.config_manager.config.get('globals', {}).copy()

        derived = ['FLUX_HOSTS', 'WAN_HOSTS', 'LTX_HOSTS', 'QWEN_HOSTS']
        removed = [k for k in derived if k in globals_dict]
        for k in removed:
            del globals_dict[k]
        if removed:
            print(f"[DEBUG] Removed parser-derived keys: {', '.join(removed)}")

        host_key = JOBTYPE_HOST_MAPPING.get(jobtype)
        host_str = self._get_checked_hosts_str(jobtype)

        if host_key:
            globals_dict[host_key] = host_str

        globals_lines = []
        seen = set()
        for k, v in sorted(globals_dict.items()):
            if k in seen: continue
            seen.add(k)
            val = ','.join(str(x).strip() for x in v if x) if isinstance(v, (list, tuple)) else (v or '')
            globals_lines.append(f"{k}={val}\n")

        if use_editor:
            editor_text = self.window.editor.toPlainText().rstrip() + '\n'
            shot_lines = editor_text.splitlines(keepends=True)
            if host_key:
                shot_lines = [self._override_host_in_line(ln, host_key, host_str) for ln in shot_lines]
        else:
            shot_lines = self._build_shot_block(seq, shot, host_key, host_str)

        full_content = globals_lines + ['\n', '!---------\n', '\n'] + shot_lines

        launch_dir = Path(__file__).parent / "launch_configs"
        launch_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_shot = shot.replace('/', '_')
        filename = f"run_{self.window.config_manager.project}_{jobtype}_{seq}_{safe_shot}_{ts}.txt"
        temp_path = launch_dir / filename

        try:
            with open(temp_path, "w", encoding="utf-8", newline="") as f:
                f.writelines(full_content)
            print(f"[INFO] Temp config created: {temp_path}")
            return temp_path, str(temp_path)
        except Exception as e:
            return None, f"Failed to write config for {seq}/{shot}: {str(e)}"

    def _mark_as_run(self, seq, shot, jobtype):
        status_key = f"STATUS_{jobtype.upper().replace('_', '')}"
        key = (seq, shot)
        if key not in self.window.config_manager.shot_ranges:
            return False

        start, end = self.window.config_manager.shot_ranges[key]
        original_lines = self.window.config_manager.original_lines[:]

        status_line_idx = None
        for i in range(start, end):
            stripped = original_lines[i].strip()
            if stripped.startswith(status_key + '='):
                status_line_idx = i
                break

        new_status = f"{status_key}=run\n"

        if status_line_idx is not None:
            original_lines[status_line_idx] = new_status
        else:
            insert_pos = end - 1
            while insert_pos > start and original_lines[insert_pos].strip() == '':
                insert_pos -= 1
            original_lines.insert(insert_pos + 1, new_status)

        try:
            with open(self.window.config_manager.config_path, "w", encoding="utf-8", newline="") as f:
                f.writelines(original_lines)
            self.window.config_manager.original_lines = original_lines

            success, msg = self.window.config_manager.load_config(self.window.config_manager.config_path)
            if success:
                print(f"[DEBUG] Re-parsed config after marking {seq}/{shot}")
            else:
                print(f"[WARNING] Failed to re-parse after marking: {msg}")

            return True
        except Exception as e:
            print(f"[ERROR] Failed to mark status for {seq}/{shot}: {e}")
            return False

    def run_selected_shots(self):
        jobtype = self.window.selection.get_active_jobtype()
        if not jobtype or jobtype == "Select Jobtype":
            self.window.statusBar().showMessage("Select a jobtype first", 5000)
            return

        selected_indexes = self.window.tree.selectionModel().selectedIndexes()
        selected_shots = []
        for idx in selected_indexes:
            item = self.window.tree.model().itemFromIndex(idx)
            if item:
                data = item.data(Qt.ItemDataRole.UserRole)
                if data and isinstance(data, tuple) and len(data) == 2:
                    selected_shots.append(data)

        if not selected_shots:
            self.window.statusBar().showMessage("No shots selected", 5000)
            return

        print(f"[INFO] Launching {len(selected_shots)} shot(s) as {jobtype}")

        success_count = 0
        skipped_count = 0
        for seq, shot in selected_shots:
            skip, reason = self._is_shot_skippable(seq, shot, jobtype)
            if skip:
                print(f"[SKIP] {seq}/{shot}: {reason}")
                skipped_count += 1
                continue

            use_editor = (len(selected_shots) == 1 and
                          seq == self.window.selection.selected_seq and
                          shot == self.window.selection.selected_shot)

            temp_path, msg = self.create_temp_config(seq, shot, jobtype, use_editor)
            if not temp_path:
                print(f"[ERROR] {msg}")
                continue

            try:
                parsed = parser.parse_config(str(temp_path))
                run_storytools_execution(
                    config=parsed,
                    allowed_jobtypes=[jobtype],
                    target_sequence=None,
                    target_shot=None
                )
                success_count += 1
                self._mark_as_run(seq, shot, jobtype)

                # Delete temp config unless "Keep temp configs" is checked
                if not self.window.keep_temp_checkbox.isChecked():
                    try:
                        temp_path.unlink()
                        print(f"[INFO] Deleted temp config: {temp_path}")
                    except Exception as del_e:
                        print(f"[WARNING] Failed to delete temp config {temp_path}: {del_e}")
            except Exception as e:
                print(f"[ERROR] Launch failed for {seq}/{shot}: {e}")

        total = len(selected_shots)
        msg = f"Submitted {success_count}/{total} {jobtype} job(s)"
        if skipped_count > 0:
            msg += f" ({skipped_count} skipped)"
        self.window.statusBar().showMessage(msg, 8000)
        print(f"[INFO] {msg}")

        self.window.refresh_tree_only()

    def run_all_shots(self):
        if not self.window.config_manager.config_path:
            self.window.statusBar().showMessage("No config loaded", 5000)
            return

        jobtype = self.window.selection.get_active_jobtype()
        if not jobtype or jobtype == "Select Jobtype":
            self.window.statusBar().showMessage("Select a jobtype first", 5000)
            return

        self.window.statusBar().showMessage("Run All: not yet implemented – use multi-select for now", 10000)
        print("[INFO] Run All clicked – batch-all logic can go here later")