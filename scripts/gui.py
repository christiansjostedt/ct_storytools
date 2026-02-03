#!/usr/bin/env python3
# GUI for CT Storytools Launcher + Shot Text Editor (compact layout 2025–2026)
# Updated: QWEN_CAMERATRANSFORMATION_MODE is now GLOBAL (autosaves to globals section)

import customtkinter as ctk
from tkinter import messagebox, filedialog, Entry, simpledialog
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
import sys
import os
import re
import shutil

import parser  # Your config_parser.py
from launcher import run_all, run_storytools_execution

sys.path.insert(0, os.path.dirname(__file__))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class StorytoolsGUI:
    def __init__(self, root):
        self.root = root
        self.config_path = None
        self.config = None
        self.original_lines = None
        self.shot_ranges = {}
        self.project = ""
        self.sequences = []
        self.selected_seq = None
        self.shots = {}
        self.selected_shot = None
        self.selected_jobtype = None
        self.jobtypes = ['ct_flux_t2i', 'ct_wan2_5s', 'ct_qwen_i2i', 'ct_qwen_cameratransform']
        self.host_selections = {}
        self.host_frame = None
        self.host_checkboxes = []

        self.qwen_mode_var = ctk.StringVar(value="5angles")
        self.qwen_modes = ["5angles", "10angles", "20angles", "FrontBackLeftRight", "TT"]  # fallback
        self.qwen_mode_dropdown = None

        # Debounce timer for autosave
        self.autosave_timer = None

        self.main_frame = ctk.CTkFrame(root)
        self.main_frame.pack(fill="both", expand=True, padx=8, pady=8)

        self.create_widgets()
        self.bind_drop_target()

        # Trace dropdown changes → trigger autosave
        self.qwen_mode_var.trace_add("write", self.on_mode_change)

    def create_widgets(self):
        # Top: Path + Browse
        path_frame = ctk.CTkFrame(self.main_frame)
        path_frame.pack(pady=(4,8), padx=4, fill="x")

        ctk.CTkLabel(path_frame, text="Config:", font=("Segoe UI", 12)).pack(side="left", padx=(0,6))
        self.path_entry = Entry(path_frame, width=45, bg="#2b2b2b", fg="white",
                                insertbackground="white", relief="flat", font=("Segoe UI", 12))
        self.path_entry.pack(side="left", fill="x", expand=True, padx=(0,6))
        self.path_entry.insert(0, "Drag file or click Browse")
        self.path_entry.bind('<FocusIn>', self.on_entry_focus_in)
        self.path_entry.bind('<FocusOut>', self.on_entry_focus_out)

        ctk.CTkButton(path_frame, text="Browse", width=80, command=self.browse_file).pack(side="left")

        self.refresh_btn = ctk.CTkButton(self.main_frame, text="↻ Refresh", width=90, command=self.refresh_config)
        self.refresh_btn.pack(pady=(0,8))

        self.project_label = ctk.CTkLabel(self.main_frame, text="Project: None",
                                          font=ctk.CTkFont(size=13, weight="bold"))
        self.project_label.pack(pady=(0,6))

        # Controls row: Seq / Shot / Job / Mode
        controls_row = ctk.CTkFrame(self.main_frame)
        controls_row.pack(fill="x", pady=4)

        ctk.CTkLabel(controls_row, text="Seq:", width=40, anchor="e").pack(side="left", padx=(4,2))
        self.seq_var = ctk.StringVar(value="Select Sequence")
        self.seq_dropdown = ctk.CTkOptionMenu(controls_row, variable=self.seq_var, width=140,
                                              values=["None"], command=self.on_seq_change)
        self.seq_dropdown.pack(side="left", padx=2)

        ctk.CTkLabel(controls_row, text="Shot:", width=40, anchor="e").pack(side="left", padx=(12,2))
        self.shot_var = ctk.StringVar(value="Select Shot")
        self.shot_dropdown = ctk.CTkOptionMenu(controls_row, variable=self.shot_var, width=140,
                                               values=["None"], command=self.on_shot_change)
        self.shot_dropdown.pack(side="left", padx=2)

        ctk.CTkLabel(controls_row, text="Job:", width=40, anchor="e").pack(side="left", padx=(12,2))
        self.jobtype_var = ctk.StringVar(value="Select Job")
        self.jobtype_dropdown = ctk.CTkOptionMenu(controls_row, variable=self.jobtype_var, width=140,
                                                  values=["None"], command=self.on_jobtype_change)
        self.jobtype_dropdown.pack(side="left", padx=2)

        # Mode — right next to Job
        ctk.CTkLabel(controls_row, text="Mode:", width=40, anchor="e").pack(side="left", padx=(20,2))
        self.qwen_mode_dropdown = ctk.CTkOptionMenu(controls_row, variable=self.qwen_mode_var,
                                                    values=self.qwen_modes, width=180)
        self.qwen_mode_dropdown.pack_forget()

        # Hosts
        host_label_frame = ctk.CTkFrame(self.main_frame)
        host_label_frame.pack(fill="x", pady=(4,2))
        ctk.CTkLabel(host_label_frame, text="Hosts:", font=("Segoe UI", 11)).pack(side="left", padx=4)

        self.host_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.host_frame.pack(pady=(0,6), padx=4, fill="x")

        # Editor
        ctk.CTkLabel(self.main_frame, text="Shot Editor", font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=4, pady=(4,2))

        self.editor_info = ctk.CTkLabel(self.main_frame,
            text="Drop liked Flux PNG here to set SEED_START • globals excluded",
            font=ctk.CTkFont(size=10, slant="italic"), text_color="gray")
        self.editor_info.pack(anchor="w", padx=4, pady=(0,4))

        self.shot_editor = ctk.CTkTextbox(self.main_frame, height=340, wrap="none", font=("Consolas", 12))
        self.shot_editor.pack(pady=2, padx=4, fill="both", expand=True)
        self.shot_editor.drop_target_register(DND_FILES)
        self.shot_editor.dnd_bind('<<Drop>>', self.on_image_drop)

        # Edit controls
        edit_row = ctk.CTkFrame(self.main_frame)
        edit_row.pack(pady=(6,4), padx=4, fill="x")

        self.prev_shot_btn = ctk.CTkButton(edit_row, text="← Prev", width=80, command=self.prev_shot,
                                           fg_color="#FF9800")
        self.prev_shot_btn.pack(side="left", padx=(0,4))

        self.save_btn = ctk.CTkButton(edit_row, text="Save", width=80, command=self.save_changes)
        self.save_btn.pack(side="left", padx=4)

        self.next_shot_btn = ctk.CTkButton(edit_row, text="Next →", width=80, command=self.next_shot,
                                           fg_color="#FF9800")
        self.next_shot_btn.pack(side="left", padx=4)

        self.new_shot_btn = ctk.CTkButton(edit_row, text="+ Shot", width=80, command=self.create_new_shot,
                                          fg_color="#4CAF50")
        self.new_shot_btn.pack(side="left", padx=4)

        self.new_seq_btn = ctk.CTkButton(edit_row, text="+ Seq", width=80, command=self.create_new_sequence,
                                         fg_color="#2196F3")
        self.new_seq_btn.pack(side="left")

        # Run buttons
        run_row = ctk.CTkFrame(self.main_frame)
        run_row.pack(pady=(4,8), padx=4, fill="x")

        ctk.CTkButton(run_row, text="Run All", command=self.run_all_threaded,
                      fg_color="green", width=140).pack(side="left", expand=True, fill="x", padx=(0,6))
        ctk.CTkButton(run_row, text="Run Selected", command=self.run_selected_threaded,
                      fg_color="orange", width=140).pack(side="right", expand=True, fill="x", padx=(6,0))

        self.root.bind('<Control-Left>', lambda e: self.prev_shot())
        self.root.bind('<Control-Right>', lambda e: self.next_shot())

    def update_mode_visibility(self):
        if self.selected_jobtype == 'ct_qwen_cameratransform':
            self.qwen_mode_dropdown.pack(side="left", padx=2)
            self.editor_info.configure(
                text="Camera transform — Mode autosaves globally on change",
                text_color="#81C784"
            )
            # Load global value from config (not from shot block)
            if 'globals' in self.config and 'QWEN_CAMERATRANSFORMATION_MODE' in self.config['globals']:
                val = self.config['globals']['QWEN_CAMERATRANSFORMATION_MODE'].strip()
                if val in self.qwen_modes:
                    self.qwen_mode_var.set(val)
        else:
            self.qwen_mode_dropdown.pack_forget()
            self.editor_info.configure(
                text="Drop liked Flux PNG here to set SEED_START • globals excluded",
                text_color="gray"
            )

    def on_mode_change(self, *args):
        """Triggered when dropdown value changes — debounce autosave to global section"""
        if self.selected_jobtype != 'ct_qwen_cameratransform':
            return

        new_value = self.qwen_mode_var.get().strip()
        if not new_value:
            return

        # Get current global value
        current_value = None
        if 'globals' in self.config and 'QWEN_CAMERATRANSFORMATION_MODE' in self.config['globals']:
            current_value = self.config['globals']['QWEN_CAMERATRANSFORMATION_MODE'].strip()

        if new_value != current_value:
            if self.autosave_timer:
                self.root.after_cancel(self.autosave_timer)
            self.autosave_timer = self.root.after(100, lambda: self._autosave_global_mode(new_value))

    def _autosave_global_mode(self, mode_value):
        """Update QWEN_CAMERATRANSFORMATION_MODE in the global section and save file"""
        try:
            # Find the global section (before first !---------)
            global_end = 0
            for i, line in enumerate(self.original_lines):
                if line.strip().startswith('!---------'):
                    global_end = i
                    break
            else:
                global_end = len(self.original_lines)

            global_lines = self.original_lines[:global_end]
            new_global_lines = []
            mode_written = False
            for line in global_lines:
                stripped = line.strip()
                if stripped.startswith("QWEN_CAMERATRANSFORMATION_MODE="):
                    new_global_lines.append(f"QWEN_CAMERATRANSFORMATION_MODE={mode_value}\n")
                    mode_written = True
                else:
                    new_global_lines.append(line)
            if not mode_written:
                # Insert after last non-empty global line
                insert_pos = len(new_global_lines) - 1
                while insert_pos >= 0 and not new_global_lines[insert_pos].strip():
                    insert_pos -= 1
                new_global_lines.insert(insert_pos + 1, f"QWEN_CAMERATRANSFORMATION_MODE={mode_value}\n")
                new_global_lines.append("\n")  # ensure blank line

            # Rebuild full file
            new_file_lines = new_global_lines + self.original_lines[global_end:]
            with open(self.config_path, 'w', encoding='utf-8', newline='') as f:
                f.writelines(new_file_lines)

            self.original_lines = new_file_lines

            # Reload config to sync globals
            self.config = parser.parse_config(self.config_path)

            # Feedback
            self.editor_info.configure(
                text=f"Global mode autosaved: {mode_value}",
                text_color="#4CAF50"
            )
            self.root.after(2000, lambda: self.update_mode_visibility())  # revert hint

        except Exception as e:
            print(f"Global autosave failed: {e}")
            self.editor_info.configure(text=f"Autosave failed: {str(e)}", text_color="red")

    def bind_drop_target(self):
        self.path_entry.drop_target_register(DND_FILES)
        self.path_entry.dnd_bind('<<Drop>>', self.on_drop)

    def on_drop(self, event):
        files = self.root.tk.splitlist(event.data)
        if files:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, files[0])
            self.refresh_config()

    def browse_file(self):
        file = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, file)
            self.refresh_config()

    def on_entry_focus_in(self, event):
        if self.path_entry.get() == "Drag file or click Browse":
            self.path_entry.delete(0, 'end')

    def on_entry_focus_out(self, event):
        if not self.path_entry.get():
            self.path_entry.insert(0, "Drag file or click Browse")

    def on_image_drop(self, event):
        pass  # placeholder

    def update_host_selection(self):
        for widget in self.host_frame.winfo_children():
            widget.destroy()
        self.host_checkboxes = []

        if not self.selected_jobtype or not self.config or 'globals' not in self.config:
            return

        host_key = self._get_host_key_for_jobtype(self.selected_jobtype)
        if not host_key:
            return

        host_str = self.config['globals'].get(host_key.replace('_HOSTS','_HOST'), '')
        hosts = [h.strip() for h in host_str.split(',') if h.strip()]
        if not hosts:
            ctk.CTkLabel(self.host_frame, text="No hosts", font=("Segoe UI", 10)).pack(anchor="w")
            return

        if self.selected_jobtype not in self.host_selections:
            self.host_selections[self.selected_jobtype] = set(hosts)

        selected = self.host_selections[self.selected_jobtype]

        for host in hosts:
            var = ctk.BooleanVar(value=(host in selected))
            cb = ctk.CTkCheckBox(self.host_frame, text=host, variable=var,
                                 font=("Segoe UI", 11), width=20,
                                 command=lambda h=host, v=var: self.on_host_toggle(h, v.get()))
            cb.pack(side="left", padx=(0,12), pady=1)
            self.host_checkboxes.append((host, var))

    def _get_host_key_for_jobtype(self, jt):
        mapping = {
            'ct_flux_t2i': 'FLUX_HOST',
            'ct_wan2_5s': 'WAN_HOST',
            'ct_qwen_i2i': 'QWEN_HOST',
            'ct_qwen_cameratransform': 'QWEN_HOST'
        }
        return mapping.get(jt)

    def on_host_toggle(self, host, is_selected):
        if self.selected_jobtype:
            s = self.host_selections.setdefault(self.selected_jobtype, set())
            if is_selected:
                s.add(host)
            else:
                s.discard(host)

    def apply_host_restriction(self):
        if not self.selected_jobtype or not self.config_path:
            return None, None
        host_key = self._get_host_key_for_jobtype(self.selected_jobtype)
        if not host_key:
            return None, None
        selected_hosts = self.host_selections.get(self.selected_jobtype, set())
        if not selected_hosts:
            return None, None
        with open(self.config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        original_line = None
        line_idx = -1
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(host_key + '=') or stripped.startswith(host_key + ' ='):
                original_line = line.rstrip('\n')
                line_idx = i
                break
        if line_idx == -1:
            print(f"Warning: {host_key}= not found")
            return None, None
        new_value = ', '.join(sorted(selected_hosts))
        new_line = f"{host_key}={new_value}\n"
        backup_path = self.config_path + ".bak_host"
        shutil.copy2(self.config_path, backup_path)
        lines[line_idx] = new_line
        with open(self.config_path, 'w', encoding='utf-8', newline='') as f:
            f.writelines(lines)
        print(f"Restricted → {host_key}={new_value}")
        return original_line, line_idx

    def restore_original_hosts(self, original_line, line_idx):
        if original_line is None or line_idx is None or not self.config_path:
            return
        with open(self.config_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if 0 <= line_idx < len(lines):
            lines[line_idx] = original_line.rstrip('\n') + '\n'
            with open(self.config_path, 'w', encoding='utf-8', newline='') as f:
                f.writelines(lines)
            print("Restored hosts")
        backup = self.config_path + ".bak_host"
        if os.path.exists(backup):
            try:
                os.remove(backup)
            except:
                pass

    def refresh_config(self):
        path = self.path_entry.get().strip()
        if path in ("", "Drag file or click Browse") or not os.path.exists(path):
            messagebox.showerror("Error", "Invalid config path!")
            return
        try:
            with open(path, encoding='utf-8') as f:
                self.original_lines = f.readlines()
            self.config = parser.parse_config(path)
            self.config_path = path

            # Load QWEN_CAMERATRANSFORMATION_MODES from globals if present
            if 'globals' in self.config and 'QWEN_CAMERATRANSFORMATION_MODES' in self.config['globals']:
                modes_str = self.config['globals']['QWEN_CAMERATRANSFORMATION_MODES'].strip()
                parsed_modes = [m.strip() for m in modes_str.split(',') if m.strip()]
                if parsed_modes:
                    self.qwen_modes = parsed_modes
                    if self.qwen_mode_dropdown:
                        self.qwen_mode_dropdown.configure(values=self.qwen_modes)

            # Load global QWEN_CAMERATRANSFORMATION_MODE if present
            if 'globals' in self.config and 'QWEN_CAMERATRANSFORMATION_MODE' in self.config['globals']:
                default_mode = self.config['globals']['QWEN_CAMERATRANSFORMATION_MODE'].strip()
                if default_mode in self.qwen_modes:
                    self.qwen_mode_var.set(default_mode)

            project = self.config['globals'].get('PROJECT', 'Unknown')
            self.project_label.configure(text=f"Project: {project}")
            self.sequences = sorted(self.config.get(project, {}).keys())
            self.seq_dropdown.configure(values=self.sequences or ["None"])
            self.shot_ranges.clear()
            self._scan_shot_ranges()
            if self.sequences:
                self.seq_var.set(self.selected_seq if self.selected_seq in self.sequences else self.sequences[0])
                self.on_seq_change(self.seq_var.get())
            else:
                self._clear_dropdowns()
            self.update_host_selection()
            self.update_mode_visibility()
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse:\n{str(e)}")
            print(f"Parse error: {e}", file=sys.stderr)

    def run_all_threaded(self):
        if not self.config or not self.config_path:
            messagebox.showerror("Error", "Load config first!")
            return
        jt = self.get_selected_jobtype()
        if not jt:
            messagebox.showerror("Error", "Select job type!")
            return
        threading.Thread(target=self._run_with_host_control, args=(run_all, [jt], None, None), daemon=True).start()

    def run_selected_threaded(self):
        if not self.selected_seq or not self.selected_shot:
            messagebox.showerror("Error", "Select sequence + shot!")
            return
        jt = self.get_selected_jobtype()
        if not jt:
            messagebox.showerror("Error", "Select job type!")
            return
        threading.Thread(target=self._run_with_host_control,
                         args=(run_storytools_execution, [jt], self.selected_seq, self.selected_shot),
                         daemon=True).start()

    def _run_with_host_control(self, runner_func, allowed, target_seq=None, target_shot=None):
        original_line = None
        line_idx = None
        try:
            original_line, line_idx = self.apply_host_restriction()
            self.config = parser.parse_config(self.config_path)
            if target_seq and target_shot:
                runner_func(
                    config=self.config,
                    allowed_jobtypes=allowed,
                    target_sequence=target_seq,
                    target_shot=target_shot
                )
            else:
                runner_func(self.config_path, allowed_jobtypes=allowed)
        except Exception as e:
            messagebox.showerror("Run Error", str(e))
        finally:
            self.restore_original_hosts(original_line, line_idx)
            self.root.after(0, self.refresh_config)

    def prev_shot(self):
        if not self.selected_seq or not self.selected_shot: return
        project = self.config['globals'].get('PROJECT')
        if not project: return
        current_shots = sorted(self.config[project].get(self.selected_seq, {}).keys())
        if len(current_shots) <= 1: return
        try:
            idx = current_shots.index(self.selected_shot)
            new_shot = current_shots[(idx - 1) % len(current_shots)]
            self.shot_var.set(new_shot)
            self.on_shot_change(new_shot)
        except ValueError:
            pass

    def next_shot(self):
        if not self.selected_seq or not self.selected_shot: return
        project = self.config['globals'].get('PROJECT')
        if not project: return
        current_shots = sorted(self.config[project].get(self.selected_seq, {}).keys())
        if len(current_shots) <= 1: return
        try:
            idx = current_shots.index(self.selected_shot)
            new_shot = current_shots[(idx + 1) % len(current_shots)]
            self.shot_var.set(new_shot)
            self.on_shot_change(new_shot)
        except ValueError:
            pass

    def on_seq_change(self, selection):
        self.selected_seq = None if selection == "Select Sequence" else selection
        if not self.selected_seq:
            self.shot_dropdown.configure(values=["None"])
            self.shot_var.set("Select Shot")
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job")
            self.selected_jobtype = None
            self.shot_editor.delete("1.0", "end")
            self.prev_shot_btn.configure(state="disabled")
            self.next_shot_btn.configure(state="disabled")
            self.update_host_selection()
            self.update_mode_visibility()
            return

        project = self.config['globals'].get('PROJECT')
        shots = sorted(self.config[project].get(self.selected_seq, {}).keys())
        self.shots[self.selected_seq] = shots
        self.shot_dropdown.configure(values=shots or ["None"])

        state = "normal" if len(shots) > 1 else "disabled"
        self.prev_shot_btn.configure(state=state)
        self.next_shot_btn.configure(state=state)

        if shots:
            self.shot_var.set(self.selected_shot if self.selected_shot in shots else shots[0])
            self.on_shot_change(self.shot_var.get())
        else:
            self.shot_var.set("Select Shot")
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job")
            self.selected_jobtype = None
            self.shot_editor.delete("1.0", "end")
            self.update_host_selection()
            self.update_mode_visibility()

    def on_shot_change(self, selection):
        self.selected_shot = None if selection == "Select Shot" else selection
        if not self.selected_shot or not self.selected_seq:
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job")
            self.selected_jobtype = None
            self.shot_editor.delete("1.0", "end")
            self.update_mode_visibility()
            self.update_host_selection()
            return

        project = self.config['globals'].get('PROJECT')
        available_jts = set()
        shot_container = self.config[project][self.selected_seq].get(self.selected_shot, {})

        for sub_data in shot_container.values():
            jt_str = sub_data.get('JOBTYPE') or sub_data.get('IMAGE_JOBTYPE') or sub_data.get('VIDEO_JOBTYPE') or ''
            if jt_str:
                jts = [jt.strip() for jt in jt_str.split(',') if jt.strip()]
                available_jts.update(jt for jt in jts if jt in self.jobtypes)

        avail_list = sorted(available_jts) or ["None"]
        self.jobtype_dropdown.configure(values=avail_list)

        if avail_list != ["None"]:
            jt = self.selected_jobtype if self.selected_jobtype in avail_list else avail_list[0]
            self.jobtype_var.set(jt)
            self.selected_jobtype = jt
        else:
            self.jobtype_var.set("None")
            self.selected_jobtype = None

        key = (self.selected_seq, self.selected_shot)
        if key in self.shot_ranges:
            start, end = self.shot_ranges[key]
            block = ''.join(self.original_lines[start:end])
            self.shot_editor.delete("1.0", "end")
            self.shot_editor.insert("1.0", block)
        else:
            self.shot_editor.delete("1.0", "end")
            self.shot_editor.insert("1.0", f"# Could not locate block for shot '{self.selected_shot}'\n")

        self.update_mode_visibility()
        self.update_host_selection()

    def on_jobtype_change(self, selection):
        self.selected_jobtype = None if selection in ("Select Job", "None") else selection
        self.update_mode_visibility()
        self.update_host_selection()

    def get_selected_jobtype(self):
        jt = self.selected_jobtype
        return jt if jt and jt != "Select Job" else None

    def save_changes(self):
        if not self.selected_seq or not self.selected_shot or not self.original_lines:
            messagebox.showerror("Error", "No shot selected or no file loaded.")
            return

        key = (self.selected_seq, self.selected_shot)
        if key not in self.shot_ranges:
            messagebox.showerror("Error", "Original block position not found.")
            return

        try:
            edited_text = self.shot_editor.get("1.0", "end")
            if edited_text and not edited_text.endswith('\n'):
                edited_text += '\n'

            start, end = self.shot_ranges[key]
            new_lines = self.original_lines[:start] + [edited_text] + self.original_lines[end:]

            with open(self.config_path, 'w', encoding='utf-8', newline='') as f:
                f.writelines(new_lines)

            self.original_lines = new_lines
            self.refresh_config()

        except Exception as e:
            messagebox.showerror("Save Failed", str(e))

    def create_new_shot(self):
        if not self.selected_seq:
            messagebox.showerror("Error", "Select a sequence first!")
            return

        project = self.config['globals'].get('PROJECT')
        max_num = 0
        for shot_id in self.config[project].get(self.selected_seq, {}):
            try:
                num = int(shot_id)
                max_num = max(max_num, num)
            except ValueError:
                pass

        next_num = max_num + 1
        new_shot_id = f"{next_num:04d}"
        new_name = f"sh{next_num:04d}"

        new_block_lines = [
            "!---------\n",
            f"SEQUENCE={self.selected_seq}\n",
            f"SHOT={new_shot_id}\n",
            f"NAME={new_name}\n",
            "ENVIRONMENT_PROMPT=\n",
            "POSITIVE_PROMPT=\n",
            "\n"
        ]

        try:
            with open(self.config_path, 'a', encoding='utf-8', newline='') as f:
                f.writelines(new_block_lines)
            self.refresh_config()
            if new_shot_id in self.shots.get(self.selected_seq, []):
                self.shot_var.set(new_shot_id)
                self.on_shot_change(new_shot_id)
        except Exception as e:
            messagebox.showerror("Failed to Create Shot", str(e))

    def create_new_sequence(self):
        new_seq_name = simpledialog.askstring("New Sequence", "Enter sequence name:", parent=self.root)
        if not new_seq_name or not new_seq_name.strip():
            return
        new_seq_name = new_seq_name.strip()

        new_block_lines = [
            "\n",
            "!---------\n",
            f"SEQUENCE={new_seq_name}\n",
            "SHOT=0001\n",
            "NAME=sh0001\n",
            "ENVIRONMENT_PROMPT=\n",
            "POSITIVE_PROMPT=\n",
            "\n"
        ]

        try:
            with open(self.config_path, 'a', encoding='utf-8', newline='') as f:
                f.writelines(new_block_lines)
            self.refresh_config()
            if new_seq_name in self.sequences:
                self.seq_var.set(new_seq_name)
                self.on_seq_change(new_seq_name)
                shots = self.shots.get(new_seq_name, [])
                if "0001" in shots:
                    self.shot_var.set("0001")
                    self.on_shot_change("0001")
        except Exception as e:
            messagebox.showerror("Failed to Create Sequence", str(e))

    def _clear_dropdowns(self):
        self.seq_var.set("Select Sequence")
        self.shot_var.set("Select Shot")
        self.jobtype_var.set("Select Job")
        self.selected_seq = self.selected_shot = self.selected_jobtype = None
        self.shot_editor.delete("1.0", "end")
        self.update_mode_visibility()
        self.update_host_selection()

    def _scan_shot_ranges(self):
        if not self.original_lines: return
        self.shot_ranges.clear()
        current_seq = None
        block_start = -1
        i = 0
        while i < len(self.original_lines):
            line = self.original_lines[i].strip()
            if line.startswith('SEQUENCE='):
                current_seq = line[9:].strip()
                i += 1
                continue
            if line.startswith('!---------'):
                if block_start != -1 and current_seq is not None:
                    shot_id = None
                    for j in range(i - 1, block_start - 1, -1):
                        l = self.original_lines[j].strip()
                        if l.startswith('SHOT='):
                            shot_id = l[5:].strip()
                            break
                    if shot_id:
                        self.shot_ranges[(current_seq, shot_id)] = (block_start, i)
                block_start = i
                i += 1
                continue
            i += 1

        if block_start != -1 and current_seq is not None:
            shot_id = None
            for j in range(len(self.original_lines) - 1, block_start - 1, -1):
                l = self.original_lines[j].strip()
                if l.startswith('SHOT='):
                    shot_id = l[5:].strip()
                    break
            if shot_id:
                self.shot_ranges[(current_seq, shot_id)] = (block_start, len(self.original_lines))


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    root.title("ct_storytools")
    root.configure(bg="#2b2b2b")
    root.geometry("720x740")
    app = StorytoolsGUI(root)
    root.mainloop()