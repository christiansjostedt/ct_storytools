#!/usr/bin/env python3
# GUI for CT Storytools Launcher (Fixed DnD Integration - TkinterDnD Root with CTkFrame)
# Requirements: pip install customtkinter tkinterdnd2 requests
# - CustomTkinter for dark theme and modern UI.
# - tkinterdnd2 for drag-and-drop file support (fixed: TkinterDnD.Tk root with CTkFrame for widgets).
# Run in the venv with Python 3.11+.
# Calls slimmed launcher.run_all/config_storytools_execution.
import customtkinter as ctk
from tkinter import messagebox, filedialog, Entry  # For standard Entry for DnD
from tkinterdnd2 import TkinterDnD, DND_FILES  # FIXED: TkinterDnD.Tk root
import threading  # For non-blocking execution
import sys
import os
# Import your modules (adjust if needed)
import parser  # Your config_parser.py
from launcher import run_all, run_storytools_execution  # Slimmed launcher

sys.path.insert(0, os.path.dirname(__file__))

ctk.set_appearance_mode("dark")  # Dark theme
ctk.set_default_color_theme("blue")


class StorytoolsGUI:
    def __init__(self, root):
        self.root = root
        self.config_path = None
        self.config = None
        self.project = ""
        self.sequences = []
        self.selected_seq = None
        self.shots = {}  # {seq: [shot_ids]}
        self.selected_shot = None
        self.selected_jobtype = None
        self.jobtypes = ['ct_flux_t2i', 'ct_wan2_5s', 'ct_qwen_i2i']  # Hardcoded for now
        self.main_frame = ctk.CTkFrame(root)  # FIXED: CTkFrame on TkinterDnD.Tk root
        self.main_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.create_widgets()
        self.bind_drop_target()  # For drag-drop

    def create_widgets(self):
        # Config Path Entry
        path_frame = ctk.CTkFrame(self.main_frame)
        path_frame.pack(pady=10, padx=10, fill="x")
        ctk.CTkLabel(path_frame, text="Config File Path:").pack(anchor="w", padx=5, pady=5)
        # FIXED: Use standard Tkinter Entry on root for DnD support, styled dark
        self.path_entry = Entry(path_frame, width=50, bg="#2b2b2b", fg="white", insertbackground="white", relief="flat")
        self.path_entry.pack(padx=5, pady=5, fill="x")
        self.path_entry.insert(0, "Drag/drop or browse config file here")  # Placeholder
        self.path_entry.bind('<FocusIn>', self.on_entry_focus_in)
        self.path_entry.bind('<FocusOut>', self.on_entry_focus_out)
        browse_btn = ctk.CTkButton(path_frame, text="Browse", command=self.browse_file)
        browse_btn.pack(pady=5)
        # Refresh Button
        self.refresh_btn = ctk.CTkButton(self.main_frame, text="Refresh Config", command=self.refresh_config)
        self.refresh_btn.pack(pady=5)
        # Project Label
        self.project_label = ctk.CTkLabel(self.main_frame, text="Project: None", font=ctk.CTkFont(size=14, weight="bold"))
        self.project_label.pack(pady=10)
        # Sequence Dropdown
        ctk.CTkLabel(self.main_frame, text="Sequence:").pack(anchor="w", padx=20)
        self.seq_var = ctk.StringVar(value="Select Sequence")
        self.seq_dropdown = ctk.CTkOptionMenu(
            self.main_frame, variable=self.seq_var, values=["None"], command=self.on_seq_change
        )
        self.seq_dropdown.pack(pady=5, padx=20)
        # Shot Dropdown
        ctk.CTkLabel(self.main_frame, text="Shot:").pack(anchor="w", padx=20)
        self.shot_var = ctk.StringVar(value="Select Shot")
        self.shot_dropdown = ctk.CTkOptionMenu(
            self.main_frame, variable=self.shot_var, values=["None"], command=self.on_shot_change
        )
        self.shot_dropdown.pack(pady=5, padx=20)
        # Job Type Dropdown
        ctk.CTkLabel(self.main_frame, text="Job Type:").pack(anchor="w", padx=20)
        self.jobtype_var = ctk.StringVar(value="Select Job Type")
        self.jobtype_dropdown = ctk.CTkOptionMenu(
            self.main_frame, variable=self.jobtype_var, values=["None"], command=self.on_jobtype_change
        )
        self.jobtype_dropdown.pack(pady=5, padx=20)
        # Buttons
        btn_frame = ctk.CTkFrame(self.main_frame)
        btn_frame.pack(pady=20, padx=10, fill="x")
        self.run_all_btn = ctk.CTkButton(btn_frame, text="Run All", command=self.run_all_threaded, fg_color="green")
        self.run_all_btn.pack(pady=5, side="left", expand=True)
        self.run_selected_btn = ctk.CTkButton(btn_frame, text="Run Selected", command=self.run_selected_threaded, fg_color="orange")
        self.run_selected_btn.pack(pady=5, side="right", expand=True)

    def on_entry_focus_in(self, event):
        if self.path_entry.get() == "Drag/drop or browse config file here":
            self.path_entry.delete(0, 'end')

    def on_entry_focus_out(self, event):
        if not self.path_entry.get():
            self.path_entry.insert(0, "Drag/drop or browse config file here")

    def bind_drop_target(self):
        # FIXED: Register DnD directly on the standard Entry (on TkinterDnD.Tk root)
        self.path_entry.drop_target_register(DND_FILES)
        self.path_entry.dnd_bind('<<Drop>>', self.on_drop)

    def on_drop(self, event):
        """Handle file drop."""
        # FIXED: Use event.data directly for parsing in standard Entry on TkinterDnD root
        files = self.root.tk.splitlist(event.data)
        if files:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, files[0])  # Take first file
            self.refresh_config()

    def browse_file(self):
        """Open file dialog."""
        file = filedialog.askopenfilename(filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if file:
            self.path_entry.delete(0, "end")
            self.path_entry.insert(0, file)
            self.refresh_config()

    def refresh_config(self):
        """Parse config and populate GUI."""
        path = self.path_entry.get().strip()
        if path == "Drag/drop or browse config file here" or not path or not os.path.exists(path):
            messagebox.showerror("Error", "Invalid config path!")
            return
        try:
            self.config = parser.parse_config(path)
            self.config_path = path
            project = self.config['globals'].get('PROJECT', 'Unknown')
            self.project_label.configure(text=f"Project: {project}")
            self.sequences = sorted(self.config[project].keys())
            self.seq_dropdown.configure(values=self.sequences)
            # FIXED: Preserve selection if it still exists
            if self.sequences:
                if self.selected_seq and self.selected_seq in self.sequences:
                    self.seq_var.set(self.selected_seq)
                    self.on_seq_change(self.selected_seq)  # Refresh shots/checkboxes for this seq
                else:
                    # Fall back to first
                    self.seq_var.set(self.sequences[0])
                    self.on_seq_change(self.sequences[0])
            else:
                self.seq_dropdown.configure(values=["None"])
                self.seq_var.set("Select Sequence")
                self.shot_dropdown.configure(values=["None"])
                self.shot_var.set("Select Shot")
                self.jobtype_dropdown.configure(values=["None"])
                self.jobtype_var.set("Select Job Type")
                self.selected_jobtype = None
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse config:\n{str(e)}")
            print(f"Debug - Parse error: {e}", file=sys.stderr)  # To terminal

    def on_seq_change(self, selection):
        """Update shots dropdown and jobtype dropdown."""
        self.selected_seq = selection if selection != "Select Sequence" else None
        if self.selected_seq and self.config:
            project = self.config['globals']['PROJECT']
            shots = sorted(self.config[project][self.selected_seq].keys())
            self.shots[self.selected_seq] = shots
            self.shot_dropdown.configure(values=shots)
            # FIXED: Preserve shot selection if it still exists under this seq
            if shots:
                if self.selected_shot and self.selected_shot in shots:
                    self.shot_var.set(self.selected_shot)
                    self.on_shot_change(self.selected_shot)  # Refresh jobtype for this shot
                else:
                    # Fall back to first shot
                    self.shot_var.set(shots[0])
                    self.on_shot_change(shots[0])
            else:
                self.shot_dropdown.configure(values=["None"])
                self.shot_var.set("Select Shot")
                self.jobtype_dropdown.configure(values=["None"])
                self.jobtype_var.set("Select Job Type")
                self.selected_jobtype = None
        else:
            self.shot_dropdown.configure(values=["None"])
            self.shot_var.set("Select Shot")
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job Type")
            self.selected_jobtype = None

    def on_shot_change(self, selection):
        """Update jobtype dropdown based on available JOBTYPEs."""
        self.selected_shot = selection if selection != "Select Shot" else None
        if self.selected_shot and self.selected_seq and self.config:
            project = self.config['globals']['PROJECT']
            # Collect all unique JOBTYPEs across subshots under this SHOT
            available_jts = set()
            for subshot_id in self.config[project][self.selected_seq][self.selected_shot]:
                shot_data = self.config[project][self.selected_seq][self.selected_shot][subshot_id]
                jobtype_str = shot_data.get('JOBTYPE') or shot_data.get('IMAGE_JOBTYPE') or shot_data.get('VIDEO_JOBTYPE')
                if jobtype_str:
                    jts = [jt.strip() for jt in jobtype_str.split(',') if jt.strip()]
                    available_jts.update(jt for jt in jts if jt in self.jobtypes)  # Filter to known
            # Update jobtype dropdown
            available_list = sorted(list(available_jts)) if available_jts else ["None"]
            self.jobtype_dropdown.configure(values=available_list)
            if available_list != ["None"]:
                if self.selected_jobtype and self.selected_jobtype in available_list:
                    self.jobtype_var.set(self.selected_jobtype)
                else:
                    self.jobtype_var.set(available_list[0])
                self.selected_jobtype = self.jobtype_var.get()
            else:
                self.jobtype_var.set("Select Job Type")
                self.selected_jobtype = None
        else:
            self.jobtype_dropdown.configure(values=["None"])
            self.jobtype_var.set("Select Job Type")
            self.selected_jobtype = None

    def on_jobtype_change(self, selection):
        """Update selected jobtype."""
        self.selected_jobtype = selection if selection != "Select Job Type" else None

    def get_selected_jobtype(self):
        """Get the selected jobtype."""
        return self.selected_jobtype if self.selected_jobtype and self.selected_jobtype != "Select Job Type" else None

    def run_all_threaded(self):
        """Run all in thread (non-blocking)."""
        if not self.config:
            messagebox.showerror("Error", "Load a config first!")
            return
        selected_jt = self.get_selected_jobtype()
        if not selected_jt:
            messagebox.showerror("Error", "Select a job type!")
            return
        allowed = [selected_jt]
        threading.Thread(target=self._run_all, args=(allowed,), daemon=True).start()

    def _run_all(self, allowed):
        try:
            # Call with filter (slimmed launcher handles JSON/send)
            run_all(self.config_path, allowed_jobtypes=allowed)
            # Success popup removed
        except Exception as e:
            messagebox.showerror("Execution Error", f"Failed to queue jobs:\n{str(e)}")
            print(f"Debug - Run all error: {e}", file=sys.stderr)

    def run_selected_threaded(self):
        """Run selected in thread."""
        if not self.selected_seq or not self.selected_shot:
            messagebox.showerror("Error", "Select sequence and shot first!")
            return
        selected_jt = self.get_selected_jobtype()
        if not selected_jt:
            messagebox.showerror("Error", "Select a job type!")
            return
        allowed = [selected_jt]
        threading.Thread(target=self._run_selected, args=(allowed,), daemon=True).start()

    def _run_selected(self, allowed):
        try:
            # Call with targets and filter (slimmed)
            run_storytools_execution(
                config=self.config,
                allowed_jobtypes=allowed,
                target_sequence=self.selected_seq,
                target_shot=self.selected_shot
            )
            # Success popup removed
        except Exception as e:
            messagebox.showerror("Execution Error", f"Failed to queue jobs:\n{str(e)}")
            print(f"Debug - Run selected error: {e}", file=sys.stderr)


if __name__ == "__main__":
    # FIXED: Use TkinterDnD.Tk as root for DnD, then CTkFrame for widgets
    root = TkinterDnD.Tk()
    root.title("ct_storytools")
    root.configure(bg="#2b2b2b")  # Dark background to match theme
    app = StorytoolsGUI(root)
    root.mainloop()