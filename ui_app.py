"""
ui_app.py
Tkinter UI with:
- Blue/Black theme
- Combobox for scan roots
- Threaded scanning
- Click to open folders/files
- Right-click file to reveal in folder (Explorer select on Windows)
- Progress bar (Red -> Yellow -> Green) and "Done" on completion
"""

import os
import math
import tkinter as tk
from tkinter import ttk, messagebox

from filesystem_sources import get_scan_roots
from scanner_thread import DirectoryScanner, format_size
from open_utils import open_file, open_folder, reveal_in_folder


class StorageScannerApp(tk.Tk):
    def __init__(self):
        super().__init__()

        self.title("Storage AI - Threaded Directory Scanner")
        self.geometry("980x590")
        self.minsize(980, 590)

        self.scanner = None

        # Mapping arrays so clicking a list row opens the exact path
        self._dir_paths = []
        self._file_paths = []

        self._apply_theme()
        self._build_ui()

    # ---------------- THEME ----------------
    def _apply_theme(self):
        self.BG = "#0b1020"        # black-blue background
        self.PANEL = "#0f1730"     # panel
        self.BLUE = "#2d6cff"      # accent
        self.TEXT = "#e8ecff"      # text
        self.MUTED = "#b6c2ff"     # muted text
        self.LIST_BG = "#070b16"   # list background
        self.LIST_SEL = "#123a8a"  # selection
        self.LIST_FG = self.TEXT

        self.configure(bg=self.BG)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure(".", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("TLabelframe", background=self.BG, foreground=self.TEXT)
        style.configure(
            "TLabelframe.Label",
            background=self.BG,
            foreground=self.MUTED,
            font=("Segoe UI", 10, "bold")
        )

        style.configure("TButton", background=self.PANEL, foreground=self.TEXT, bordercolor=self.BLUE)
        style.map("TButton", background=[("active", "#13204a")], foreground=[("active", self.TEXT)])

        style.configure("TEntry", fieldbackground=self.LIST_BG, foreground=self.TEXT)
        style.configure("TCombobox", fieldbackground=self.LIST_BG, foreground=self.TEXT)

        # Combobox dropdown list colors (platform dependent)
        self.option_add("*TCombobox*Listbox.background", self.LIST_BG)
        self.option_add("*TCombobox*Listbox.foreground", self.TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", self.LIST_SEL)
        self.option_add("*TCombobox*Listbox.selectForeground", self.TEXT)

        # Progressbar styles (red/yellow/green)
        style.configure("Red.Horizontal.TProgressbar", troughcolor=self.LIST_BG, background="#d64545")
        style.configure("Yellow.Horizontal.TProgressbar", troughcolor=self.LIST_BG, background="#f1c40f")
        style.configure("Green.Horizontal.TProgressbar", troughcolor=self.LIST_BG, background="#2ecc71")

    # ---------------- UI BUILD ----------------
    def _build_ui(self):
        # ---------- Top controls ----------
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="Choose scan root:").pack(side="left")

        self.roots = get_scan_roots()
        if not self.roots:
            self.roots = ["C:\\"]

        self.root_var = tk.StringVar(value=self.roots[0])
        self.root_combo = ttk.Combobox(
            top,
            textvariable=self.root_var,
            values=self.roots,
            state="readonly",
            width=70
        )
        self.root_combo.pack(side="left", padx=8)

        self.start_btn = ttk.Button(top, text="Start Scan", command=self.start_scan)
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = ttk.Button(top, text="Stop", command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        ttk.Label(top, text="Max results:").pack(side="left", padx=(18, 6))
        self.max_results_var = tk.IntVar(value=25)
        ttk.Entry(top, textvariable=self.max_results_var, width=6).pack(side="left")

        # ---------- Status area (Progress Bar replaces "Currently scanning") ----------
        status = ttk.LabelFrame(self, text="Status")
        status.pack(fill="x", padx=12, pady=(0, 10))

        # Main status text: "Scanning..." or "Done"
        self.progress_text = tk.StringVar(value="Not started")
        self.progress_label = ttk.Label(status, textvariable=self.progress_text)
        self.progress_label.pack(anchor="w", padx=10, pady=(6, 2))

        # Progress bar (estimated progress while scanning)
        self.progress_value = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            status,
            variable=self.progress_value,
            maximum=100.0,
            mode="determinate",
            style="Red.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 6))

        # Show current directory under the bar
        self.current_dir_text = tk.StringVar(value="Current dir: (not started)")
        self.current_dir_label = ttk.Label(status, textvariable=self.current_dir_text, foreground=self.MUTED)
        self.current_dir_label.pack(anchor="w", padx=10, pady=(0, 6))

        self.counts_label = ttk.Label(status, text="Dirs scanned: 0 | Files scanned: 0")
        self.counts_label.pack(anchor="w", padx=10, pady=(0, 8))

        # ---------- Results area ----------
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        left = ttk.LabelFrame(body, text="Largest Directories (click to open folder)")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = ttk.LabelFrame(body, text="Largest Files (click to open, right-click to reveal)")
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        self.dir_list = tk.Listbox(
            left,
            bg=self.LIST_BG,
            fg=self.LIST_FG,
            selectbackground=self.LIST_SEL,
            selectforeground=self.TEXT,
            highlightthickness=1,
            highlightbackground=self.BLUE,
            relief="flat"
        )
        self.dir_list.pack(fill="both", expand=True, padx=10, pady=10)

        self.file_list = tk.Listbox(
            right,
            bg=self.LIST_BG,
            fg=self.LIST_FG,
            selectbackground=self.LIST_SEL,
            selectforeground=self.TEXT,
            highlightthickness=1,
            highlightbackground=self.BLUE,
            relief="flat"
        )
        self.file_list.pack(fill="both", expand=True, padx=10, pady=10)

        # Bind clicks
        self.dir_list.bind("<<ListboxSelect>>", self._on_dir_selected_open)
        self.file_list.bind("<<ListboxSelect>>", self._on_file_selected_open)
        self.file_list.bind("<Button-3>", self._on_file_right_click_reveal)

        self.bottom_label = ttk.Label(self, text="", foreground=self.MUTED)
        self.bottom_label.pack(fill="x", padx=12, pady=(0, 10))

    # ---------------- Progress helpers ----------------
    def _estimated_progress(self, scanned_dirs: int) -> float:
        """
        We don't know total directories up front.
        Use a curve that rises toward ~95% while scanning.
        On completion we force 100%.
        """
        # Tune factor: smaller -> fills faster, bigger -> fills slower
        p = 95.0 * (1.0 - math.exp(-scanned_dirs / 2500.0))
        return max(0.0, min(95.0, p))

    def _set_progress_style(self, value: float):
        """Red -> Yellow -> Green based on progress value."""
        if value < 33:
            self.progress_bar.config(style="Red.Horizontal.TProgressbar")
        elif value < 66:
            self.progress_bar.config(style="Yellow.Horizontal.TProgressbar")
        else:
            self.progress_bar.config(style="Green.Horizontal.TProgressbar")

    # ---------------- SCAN CONTROL ----------------
    def start_scan(self):
        if self.scanner is not None:
            messagebox.showinfo("Info", "Already scanning.")
            return

        root = self.root_var.get().strip()
        if not root:
            messagebox.showerror("Error", "Pick a scan root first.")
            return

        try:
            max_results = int(self.max_results_var.get())
            if max_results < 5:
                max_results = 5
        except ValueError:
            max_results = 25

        # Reset lists + path maps
        self.dir_list.delete(0, tk.END)
        self.file_list.delete(0, tk.END)
        self._dir_paths = []
        self._file_paths = []

        # Reset progress UI
        self.progress_value.set(0.0)
        self.progress_text.set("Scanning...")
        self.current_dir_text.set("Current dir: (starting...)")
        self._set_progress_style(0.0)

        self.bottom_label.config(text="Starting scan...")

        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        self.scanner = DirectoryScanner(
            root=root,
            max_results=max_results,
            update_every_dirs=25,
            on_update=self._on_scan_update_threadsafe,
            on_done=self._on_scan_done_threadsafe,
        )
        self.scanner.start()

    def stop_scan(self):
        if self.scanner:
            self.scanner.stop()
            self.bottom_label.config(text="Stopping scan...")

    # ---------------- Thread-safe wrappers ----------------
    def _on_scan_update_threadsafe(self, update):
        self.after(0, lambda: self._apply_update(update))

    def _on_scan_done_threadsafe(self, msg: str):
        self.after(0, lambda: self._scan_done(msg))

    # ---------------- UI updates (main thread) ----------------
    def _apply_update(self, update):
        # Update labels
        self.current_dir_text.set(f"Current dir: {update.current_dir}")
        self.counts_label.config(text=f"Dirs scanned: {update.scanned_dirs} | Files scanned: {update.scanned_files}")

        # Update progress bar (estimated)
        est = self._estimated_progress(update.scanned_dirs)
        self.progress_value.set(est)
        self._set_progress_style(est)
        self.progress_text.set("Scanning...")

        # Update directories list + paths map
        self.dir_list.delete(0, tk.END)
        self._dir_paths = []
        for path, size in update.top_dirs:
            self.dir_list.insert(tk.END, f"{format_size(size)}  |  {path}")
            self._dir_paths.append(path)

        # Update files list + paths map
        self.file_list.delete(0, tk.END)
        self._file_paths = []
        for path, size in update.top_files:
            self.file_list.insert(tk.END, f"{format_size(size)}  |  {path}")
            self._file_paths.append(path)

    def _scan_done(self, msg: str):
        # Force progress to done
        self.progress_value.set(100.0)
        self.progress_bar.config(style="Green.Horizontal.TProgressbar")
        self.progress_text.set("Done")
        self.current_dir_text.set("Current dir: (done)")

        self.bottom_label.config(text=msg)

        self.scanner = None
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    # ---------------- Click-to-open ----------------
    def _on_dir_selected_open(self, _event):
        selection = self.dir_list.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self._dir_paths):
            return

        dir_path = self._dir_paths[idx]
        if os.path.isdir(dir_path):
            open_folder(dir_path)
            self.bottom_label.config(text=f"Opened folder: {dir_path}")
        else:
            self.bottom_label.config(text="Folder not accessible or no longer exists.")

    def _on_file_selected_open(self, _event):
        selection = self.file_list.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]
        if os.path.isfile(file_path):
            open_file(file_path)
            self.bottom_label.config(text=f"Opened file: {file_path}")
        else:
            self.bottom_label.config(text="File not accessible or no longer exists.")

    def _on_file_right_click_reveal(self, event):
        idx = self.file_list.nearest(event.y)
        if idx < 0 or idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]
        if os.path.isfile(file_path):
            reveal_in_folder(file_path)
            self.bottom_label.config(text=f"Revealed in folder: {file_path}")
        else:
            self.bottom_label.config(text="File not accessible or no longer exists.")
