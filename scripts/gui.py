#!/usr/bin/env python3
# GUI for CT Storytools Launcher + Shot Text Editor (original text format)
# Requirements: pip install customtkinter tkinterdnd2 requests pillow
import customtkinter as ctk
from tkinter import messagebox, filedialog, Entry
from tkinterdnd2 import TkinterDnD, DND_FILES
import threading
import sys
import os
import re
import json
from PIL import Image

# Import your modules (adjust if needed)
import parser  # Your config_parser.py
from launcher import run_all, run_storytools_execution  # Slimmed launcher

sys.path.insert(0, os.path.dirname(__file__))

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class StorytoolsGUI:
    def __init__(self, root):
        self.root = root
        self.config_path = None
        self.config = None
        self.original_lines = None
        self.shot_ranges = {}  # (seq, shot) → (start incl. !---------, end excl. next)
        self.project = ""
        self.sequences = []
        self.selected_seq = None
        self.shots = {}
        self.selected_shot = None
        self.selected_jobtype = None
        self.jobtypes = ['ct_flux_t2i', 'ct_wan2_5s', 'ct_qwen_i2i']

        self.main_frame = ctk.CTkFrame(root)
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.create_widgets()
        self.bind_drop_target()

    def create_widgets(self):
        path_frame = ctk.CTkFrame(self.main_frame)
        path_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(path_frame, text="Config File Path:").pack(anchor="w", padx=5, pady=5)
        self.path_entry = Entry(path_frame, width=50, bg="#2b2b2b", fg="white",
                                insertbackground="white", relief="flat")
        self.path_entry.pack(padx=5, pady=5, fill="x")
        self.path_entry.insert(0, "Drag/drop or browse config file here")
        self.path_entry.bind('<FocusIn>', self.on_entry_focus_in)
        self.path_entry.bind('<FocusOut>', self.on_entry_focus_out)
        ctk.CTkButton(path_frame, text="Browse", command=self.browse_file).pack(pady=5)

        self.refresh_btn = ctk.CTkButton(self.main_frame, text="Refresh Config", command=self.refresh_config)
        self.refresh_btn.pack(pady=5)

        self.project_label = ctk.CTkLabel(self.main_frame, text="Project: None",
                                          font=ctk.CTkFont(size=14, weight="bold"))
        self.project_label.pack(pady=10)

        ctk.CTkLabel(self.main_frame, text="Sequence:").pack(anchor="w", padx=20)
        self.seq_var = ctk.StringVar(value="Select Sequence")
        self.seq_dropdown = ctk.CTkOptionMenu(self.main_frame, variable=self.seq_var,
                                              values=["None"], command=self.on_seq_change)
        self.seq_dropdown.pack(pady=5, padx=20)

        ctk.CTkLabel(self.main_frame, text="Shot:").pack(anchor="w", padx=20)
        self.shot_var = ctk.StringVar(value="Select Shot")
        self.shot_dropdown = ctk.CTkOptionMenu(self.main_frame, variable=self.shot_var,
                                               values=["None"], command=self.on_shot_change)
        self.shot_dropdown.pack(pady=5, padx=20)

        ctk.CTkLabel(self.main_frame, text="Job Type:").pack(anchor="w", padx=20)
        self.jobtype_var = ctk.StringVar(value="Select Job Type")
        self.jobtype_dropdown = ctk.CTkOptionMenu(self.main_frame, variable=self.jobtype_var,
                                                  values=["None"], command=self.on_jobtype_change)
        self.jobtype_dropdown.pack(pady=5, padx=20)

        ctk.CTkLabel(self.main_frame, text="Shot Editor (original text format)").pack(anchor="w", padx=20, pady=(10,0))
        self.editor_info = ctk.CTkLabel(self.main_frame,
            text="Only lines for the selected shot • globals excluded\n\nDrop liked Flux PNG here to read & set SEED_START=",
            font=ctk.CTkFont(size=11, slant="italic"), text_color="gray")
        self.editor_info.pack(anchor="w", padx=20, pady=(2,6))

        self.shot_editor = ctk.CTkTextbox(self.main_frame, height=260, width=560, wrap="none")
        self.shot_editor.pack(pady=6, padx=20, fill="both")

        # Enable drag & drop on the textbox
        self.shot_editor.drop_target_register(DND_FILES)
        self.shot_editor.dnd_bind('<<Drop>>', self.on_image_drop)

        # Buttons row
        edit_btn_frame = ctk.CTkFrame(self.main_frame)
        edit_btn_frame.pack(pady=10, padx=20, fill="x")
        self.save_btn = ctk.CTkButton(edit_btn_frame, text="Save Shot Changes", command=self.save_changes)
        self.save_btn.pack(side="left", padx=(0, 10))
        self.new_shot_btn = ctk.CTkButton(edit_btn_frame, text="New Shot", command=self.create_new_shot, fg_color="#4CAF50")
        self.new_shot_btn.pack(side="left")

        btn_frame = ctk.CTkFrame(self.main_frame)
        btn_frame.pack(pady=20, padx=10, fill="x")
        ctk.CTkButton(btn_frame, text="Run All", command=self.run_all_threaded,
                      fg_color="green").pack(pady=5, side="left", expand=True)
        ctk.CTkButton(btn_frame, text="Run Selected", command=self.run_selected_threaded,
                      fg_color="orange").pack(pady=5, side="right", expand=True)

    def on_image_drop(self, event):
        if not self.selected_seq or not self.selected_shot:
            messagebox.showwarning("No shot selected", "Select a sequence and shot first.")
            return

        data = event.data.strip()
        filepath = data[1:-1] if data.startswith('{') and data.endswith('}') else data

        if not os.path.isfile(filepath) or not filepath.lower().endswith('.png'):
            return

        try:
            with Image.open(filepath) as img:
                seed_str = None

                # Try to extract from ComfyUI-style 'prompt' JSON (most reliable for your case)
                if img.info and 'prompt' in img.info:
                    try:
                        json_data = json.loads(img.info['prompt'])
                        for node_id, node in json_data.items():
                            if node.get('class_type') == 'KSampler':
                                seed = node['inputs'].get('seed')
                                if seed is not None:
                                    seed_str = str(seed)
                                    break
                    except (json.JSONDecodeError, KeyError, TypeError):
                        pass

                # Fallback: look for any numeric seed-like value in any text chunk
                if not seed_str and img.info:
                    for value in img.info.values():
                        if isinstance(value, str):
                            m = re.search(r'\b\d{8,12}\b', value)
                            if m:
                                seed_str = m.group(0)
                                break

                if not seed_str:
                    messagebox.showwarning("Seed not found", "No seed number found in metadata.")
                    return

                # Insert as SEED_START= (no extra comment line)
                current_text = self.shot_editor.get("1.0", "end").rstrip()
                lines = current_text.splitlines()

                insert_pos = 0
                for idx, line in enumerate(lines):
                    s = line.strip()
                    if s and not s.startswith(('#', '!')) and ('=' in s):
                        insert_pos = idx + 1
                        break

                new_line = f"SEED_START={seed_str}"
                new_lines = lines[:insert_pos] + [new_line] + lines[insert_pos:]
                updated = "\n".join(new_lines) + "\n"

                self.shot_editor.delete("1.0", "end")
                self.shot_editor.insert("1.0", updated)

                # Silent success - no popup, no comment in file

        except Exception as e:
            messagebox.showerror("Error reading image", f"Failed to read metadata:\n{str(e)}")

    # ────────────────────────────────────────────────
    # The rest of the code remains unchanged
    # ────────────────────────────────────────────────

    def on_entry_focus_in(self, event):
        if self.path_entry.get() == "Drag/drop or browse config file here":
            self.path_entry.delete(0, 'end')

    def on_entry_focus_out(self, event):
        if not self.path_entry.get():
            self.path_entry.insert(0, "Drag/drop or browse config file here")

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

    def refresh_config(self):
        path = self.path_entry.get().strip()
        if path in ("", "Drag/drop or browse config file here") or not os.path.exists(path):
            messagebox.showerror("Error", "Invalid config path!")
            return

        try:
            with open(path, encoding='utf-8') as f:
                self.original_lines = f.readlines()

            self.config = parser.parse_config(path)
            self.config_path = path

            project = self.config['globals'].get('PROJECT', 'Unknown')
            self.project_label.configure(text=f"Project: {project}")

            self.sequences = sorted(self.config.get(project, {}).keys())
            self.seq_dropdown.configure(values=self.sequences or ["None"])

            self.shot_ranges.clear()
            self._scan_shot_ranges()

            if self.sequences:
                if self.selected_seq in self.sequences:
                    self.seq_var.set(self.selected_seq)
                else:
                    self.seq_var.set(self.sequences[0])
                self.on_seq_change(self.seq_var.get())
            else:
                self._clear_dropdowns()

        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse:\n{str(e)}")
            print(f"Parse error: {e}", file=sys.stderr)

    def _clear_dropdowns(self):
        self.seq_var.set("Select Sequence")
        self.shot_var.set("Select Shot")
        self.jobtype_var.set("Select Job Type")
        self.selected_seq = self.selected_shot = self.selected_jobtype = None
        self.shot_editor.delete("1.0", "end")

    def _scan_shot_ranges(self):
        if not self.original_lines:
            return

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

    def on_seq_change(self, selection):
        self.selected_seq = None if selection == "Select Sequence" else selection

        if not self.selected_seq:
            self.shot_dropdown.configure(values=["None"])
            self.shot_var.set("Select Shot")
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job Type")
            self.selected_jobtype = None
            self.shot_editor.delete("1.0", "end")
            return

        project = self.config['globals']['PROJECT']
        shots = sorted(self.config[project].get(self.selected_seq, {}).keys())
        self.shots[self.selected_seq] = shots
        self.shot_dropdown.configure(values=shots or ["None"])

        if shots:
            self.shot_var.set(self.selected_shot if self.selected_shot in shots else shots[0])
            self.on_shot_change(self.shot_var.get())
        else:
            self.shot_var.set("Select Shot")
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job Type")
            self.selected_jobtype = None
            self.shot_editor.delete("1.0", "end")

    def on_shot_change(self, selection):
        self.selected_shot = None if selection == "Select Shot" else selection

        if not self.selected_shot or not self.selected_seq:
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job Type")
            self.selected_jobtype = None
            self.shot_editor.delete("1.0", "end")
            return

        project = self.config['globals']['PROJECT']

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
            self.jobtype_var.set(self.selected_jobtype if self.selected_jobtype in avail_list else avail_list[0])
            self.selected_jobtype = self.jobtype_var.get()
        else:
            self.jobtype_var.set("Select Job Type")
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

    def on_jobtype_change(self, selection):
        self.selected_jobtype = None if selection == "Select Job Type" else selection

    def get_selected_jobtype(self):
        jt = self.selected_jobtype
        return jt if jt and jt != "Select Job Type" else None

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

            new_lines = (
                self.original_lines[:start] +
                [edited_text] +
                self.original_lines[end:]
            )

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

        project = self.config['globals']['PROJECT']
        current_shot_data = {}
        if self.selected_shot:
            current_shot_data = self.config[project][self.selected_seq].get(self.selected_shot, {})

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
        if self.selected_shot and 'NAME' in current_shot_data.get('', {}):
            last_name = current_shot_data['']['NAME']
            if re.match(r'^[A-Za-z](\d{3})C(\d{3})$', last_name):
                prefix, num_str, c_part = last_name[0], last_name[1:4], last_name[4:]
                new_num = int(num_str) + 1
                new_name = f"{prefix}{new_num:03d}{c_part}"
            elif re.match(r'^sh\d{4}$', last_name):
                num = int(last_name[2:]) + 1
                new_name = f"sh{num:04d}"

        new_block_lines = ["!---------\n", f"SEQUENCE={self.selected_seq}\n", f"SHOT={new_shot_id}\n", f"NAME={new_name}\n"]

        if self.selected_shot:
            current_key = (self.selected_seq, self.selected_shot)
            if current_key in self.shot_ranges:
                start, end = self.shot_ranges[current_key]
                current_block = self.original_lines[start:end]
                for line in current_block:
                    s = line.strip()
                    if s.startswith(('!---------', 'SEQUENCE=', 'SHOT=', 'NAME=')):
                        continue
                    if s:
                        new_block_lines.append(line)
        else:
            new_block_lines.extend([
                "JOBTYPE=ct_flux_t2i\n",
                "POSITIVE_PROMPT=New shot prompt here\n",
                "NEGATIVE_PROMPT=blurry, low quality\n",
                "ENVIRONMENT_PROMPT=Describe environment here\n",
                "\n"
            ])

        try:
            with open(self.config_path, 'a', encoding='utf-8', newline='') as f:
                f.writelines(new_block_lines)

            self.refresh_config()

            if new_shot_id in self.shots.get(self.selected_seq, []):
                self.shot_var.set(new_shot_id)
                self.on_shot_change(new_shot_id)

        except Exception as e:
            messagebox.showerror("Failed to Create Shot", str(e))

    def run_all_threaded(self):
        if not self.config:
            messagebox.showerror("Error", "Load config first!")
            return
        jt = self.get_selected_jobtype()
        if not jt:
            messagebox.showerror("Error", "Select job type!")
            return
        threading.Thread(target=self._run_all, args=([jt],), daemon=True).start()

    def _run_all(self, allowed):
        try:
            run_all(self.config_path, allowed_jobtypes=allowed)
        except Exception as e:
            messagebox.showerror("Run Error", str(e))

    def run_selected_threaded(self):
        if not self.selected_seq or not self.selected_shot:
            messagebox.showerror("Error", "Select sequence + shot!")
            return
        jt = self.get_selected_jobtype()
        if not jt:
            messagebox.showerror("Error", "Select job type!")
            return
        threading.Thread(target=self._run_selected, args=([jt],), daemon=True).start()

    def _run_selected(self, allowed):
        try:
            run_storytools_execution(
                config=self.config,
                allowed_jobtypes=allowed,
                target_sequence=self.selected_seq,
                target_shot=self.selected_shot
            )
        except Exception as e:
            messagebox.showerror("Run Error", str(e))


if __name__ == "__main__":
    root = TkinterDnD.Tk()
    root.title("ct_storytools")
    root.configure(bg="#2b2b2b")
    app = StorytoolsGUI(root)
    root.mainloop()