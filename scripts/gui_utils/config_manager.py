# gui_utils/config_manager.py
import re
from pathlib import Path

import parser  # config_parser.py – assumed to exist


class ConfigManager:
    def __init__(self):
        self.config_path: Path | None = None
        self.config = {}
        self.original_lines = []
        self.shot_ranges = {}
        self.project = ""

    def load_config(self, path: Path):
        self.config_path = path
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.original_lines = f.readlines()
            self.config = parser.parse_config(str(path))
            self.project = self.config.get("globals", {}).get("PROJECT", "Unknown")
            self._scan_shot_ranges()
            return True, ""
        except Exception as e:
            return False, str(e)

    def save_changes(self, seq, shot, new_text: str):
        if not self.config_path:
            return False, "No config file loaded"
        key = (seq, shot)
        if key not in self.shot_ranges:
            return False, "Shot range not found"
        start, end = self.shot_ranges[key]
        if not new_text.endswith("\n"):
            new_text += "\n"
        new_lines = self.original_lines[:start] + [new_text] + self.original_lines[end:]
        try:
            with open(self.config_path, "w", encoding="utf-8", newline="") as f:
                f.writelines(new_lines)
            self.original_lines = new_lines
            self._scan_shot_ranges()  # Re-scan ranges
            # Reload full parsed config (critical for tree/editor to see changes)
            success, msg = self.load_config(self.config_path)
            if not success:
                print(f"[WARNING] Failed to reload config after save: {msg}")
            return True, "Saved"
        except Exception as e:
            return False, str(e)

    def _scan_shot_ranges(self):
        self.shot_ranges.clear()
        if not self.original_lines:
            return
        current_seq = None
        block_start = -1
        i = 0
        while i < len(self.original_lines):
            line = self.original_lines[i].strip()
            if line.startswith("SEQUENCE="):
                current_seq = line[9:].strip()
                block_start = i
                i += 1
                continue
            if line == "!---------":
                if block_start != -1 and current_seq is not None:
                    shot_id = self._find_shot_in_block(block_start, i)
                    if shot_id:
                        self.shot_ranges[(current_seq, shot_id)] = (block_start, i)
                block_start = i
                i += 1
                continue
            i += 1
        # last block
        if block_start != -1 and current_seq is not None:
            shot_id = self._find_shot_in_block(block_start, len(self.original_lines))
            if shot_id:
                self.shot_ranges[(current_seq, shot_id)] = (block_start, len(self.original_lines))

    def _find_shot_in_block(self, start, end):
        for j in range(end - 1, start - 1, -1):
            l = self.original_lines[j].strip()
            if l.startswith("SHOT="):
                return l[5:].strip()
        return None

    def get_globals_text(self):
        if not self.original_lines:
            return "# No config loaded"
        text = ""
        for line in self.original_lines:
            if line.strip() == "!---------":
                break
            text += line
        return text if text.strip() else "# No globals found"