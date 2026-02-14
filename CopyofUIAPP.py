"""
ui_app.py
- Tkinter UI code with:
  ✅ Blue/Black theme
  ✅ Combobox roots
  ✅ Threaded scanning (scanner_thread.py)
  ✅ Click a list item to open the exact file/folder
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

        # Window settings
        self.title("Storage AI - Threaded Directory Scanner")
        self.geometry("950x560")
        self.minsize(950, 560)

        # Active scanner object (None when not scanning)
        self.scanner = None

        # We store the *real path* for each list row so clicks can open exact items.
        self._dir_paths = []   # list of directory paths (aligned with dir_list rows)
        self._file_paths = []  # list of file paths (aligned with file_list rows)

        # Build and theme UI
        self._apply_theme()
        self._build_ui()

    # ---------------- THEME ----------------

    def _apply_theme(self):
        """
        Apply a blue/black theme.
        Tkinter/ttk theming is limited, so we:
        - set a dark window background
        - style ttk widgets where possible
        - manually style Listbox widgets (they aren't ttk)
        """
        self.BG = "#0b1020"          # near-black with blue tone
        self.PANEL = "#0f1730"       # slightly lighter panel
        self.BLUE = "#2d6cff"        # accent blue
        self.TEXT = "#e8ecff"        # soft light text
        self.MUTED = "#b6c2ff"       # secondary text
        self.LIST_BG = "#070b16"     # list background
        self.LIST_SEL = "#123a8a"    # selection blue
        self.LIST_FG = self.TEXT

        self.configure(bg=self.BG)

        style = ttk.Style(self)

        # Try a modern-ish ttk theme (availability varies)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Generic ttk widget styling
        style.configure(".", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("TLabelframe", background=self.BG, foreground=self.TEXT)
        style.configure("TLabelframe.Label", background=self.BG, foreground=self.MUTED, font=("Segoe UI", 10, "bold"))

        style.configure("TButton", background=self.PANEL, foreground=self.TEXT, bordercolor=self.BLUE)
        style.map("TButton",
                  background=[("active", "#13204a")],
                  foreground=[("active", self.TEXT)])

        style.configure("TEntry", fieldbackground=self.LIST_BG, foreground=self.TEXT)
        style.configure("TCombobox", fieldbackground=self.LIST_BG, foreground=self.TEXT)

        # Combobox dropdown list styling is platform-dependent; we do what we can.
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

        # Get roots (drives + common folders)
        self.roots = get_scan_roots()
        if not self.roots:
            self.roots = ["C:\\"]  # fallback

        self.root_var = tk.StringVar(value=self.roots[0])

        # Combobox for scan roots
        self.root_combo = ttk.Combobox(
            top,
            textvariable=self.root_var,
            values=self.roots,
            state="readonly",
            width=70
        )
        self.root_combo.pack(side="left", padx=8)

        # Start/Stop buttons
        self.start_btn = ttk.Button(top, text="Start Scan", command=self.start_scan)
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = ttk.Button(top, text="Stop", command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        ttk.Label(top, text="Max results:").pack(side="left", padx=(18, 6))
        self.max_results_var = tk.IntVar(value=25)
        ttk.Entry(top, textvariable=self.max_results_var, width=6).pack(side="left")

        # ---------- Status area ----------
        status = ttk.LabelFrame(self, text="Status")
        status.pack(fill="x", padx=12, pady=(0, 10))

        self.current_dir_label = ttk.Label(status, text="Currently scanning: (not started)")
        self.current_dir_label.pack(anchor="w", padx=10, pady=(6, 2))

        self.counts_label = ttk.Label(status, text="Dirs scanned: 0 | Files scanned: 0")
        self.counts_label.pack(anchor="w", padx=10, pady=(0, 6))

        # ---------- Results area ----------
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        # Left panel: directories
        left = ttk.LabelFrame(body, text="Largest Directories (click to open folder)")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        # Right panel: files
        right = ttk.LabelFrame(body, text="Largest Files (click to open file, right-click to reveal)")
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # Listboxes are classic Tk widgets, so we manually style them.
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

        # Bind clicks:
        # - Left click on directory opens that folder
        # - Left click on file opens that file
        # - Right click on file reveals it in folder (Explorer select on Windows)
        self.dir_list.bind("<<ListboxSelect>>", self._on_dir_selected_open)
        self.file_list.bind("<<ListboxSelect>>", self._on_file_selected_open)
        self.file_list.bind("<Button-3>", self._on_file_right_click_reveal)  # right-click

        # Bottom message line
        self.bottom_label = ttk.Label(self, text="", foreground=self.MUTED)
        self.bottom_label.pack(fill="x", padx=12, pady=(0, 10))

    # ---------------- SCAN CONTROL ----------------

    def start_scan(self):
        """Start scanning in a background thread."""
        if self.scanner is not None:
            messagebox.showinfo("Info", "Already scanning.")
            return

        root = self.root_var.get().strip()
        if not root:
            messagebox.showerror("Error", "Pick a scan root first.")
            return

        # Validate max results
        try:
            max_results = int(self.max_results_var.get())
            if max_results < 5:
                max_results = 5
        except ValueError:
            max_results = 25

        # Reset UI lists + backing path arrays
        self.dir_list.delete(0, tk.END)
        self.file_list.delete(0, tk.END)
        self._dir_paths = []
        self._file_paths = []
        self.bottom_label.config(text="Starting scan...")

        # Buttons
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")

        # Create scanner
        self.scanner = DirectoryScanner(
            root=root,
            max_results=max_results,
            update_every_dirs=25,

            # callbacks happen in scanner thread -> wrap thread-safe
            on_update=self._on_scan_update_threadsafe,
            on_done=self._on_scan_done_threadsafe
        )

        self.scanner.start()

    def stop_scan(self):
        """Stop scanning (signals the thread)."""
        if self.scanner:
            self.scanner.stop()
            self.bottom_label.config(text="Stopping scan...")

    # ---------------- THREAD-SAFE WRAPPERS ----------------

    def _on_scan_update_threadsafe(self, update):
        """Scanner thread calls this -> schedule UI update on main thread."""
        self.after(0, lambda: self._apply_update(update))

    def _on_scan_done_threadsafe(self, msg: str):
        """Scanner thread calls this -> schedule UI update on main thread."""
        self.after(0, lambda: self._scan_done(msg))

    # ---------------- UI UPDATE (MAIN THREAD) ----------------

    def _apply_update(self, update):
        """Apply ScanUpdate to the UI."""
        self.current_dir_label.config(text=f"Currently scanning: {update.current_dir}")
        self.counts_label.config(text=f"Dirs scanned: {update.scanned_dirs} | Files scanned: {update.scanned_files}")

        # Update directories list + path map
        self.dir_list.delete(0, tk.END)
        self._dir_paths = []
        for path, size in update.top_dirs:
            self.dir_list.insert(tk.END, f"{format_size(size)}  |  {path}")
            self._dir_paths.append(path)

        # Update files list + path map
        self.file_list.delete(0, tk.END)
        self._file_paths = []
        for path, size in update.top_files:
            self.file_list.insert(tk.END, f"{format_size(size)}  |  {path}")
            self._file_paths.append(path)

    def _scan_done(self, msg: str):
        """Called when scan finishes/stops."""
        self.bottom_label.config(text=msg)
        self.scanner = None
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    # ---------------- CLICK-TO-OPEN ----------------

    def _on_dir_selected_open(self, _event):
        """
        When user selects a directory row, open that folder.
        NOTE: This triggers on every selection change, so we keep it lightweight.
        """
        selection = self.dir_list.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx >= len(self._dir_paths):
            return

        dir_path = self._dir_paths[idx]

        # Open folder if it exists
        if os.path.isdir(dir_path):
            open_folder(dir_path)
            self.bottom_label.config(text=f"Opened folder: {dir_path}")
        else:
            self.bottom_label.config(text="Folder no longer exists or isn't accessible.")

    def _on_file_selected_open(self, _event):
        """When user selects a file row, open that file."""
        selection = self.file_list.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]

        # Open file if it exists
        if os.path.isfile(file_path):
            open_file(file_path)
            self.bottom_label.config(text=f"Opened file: {file_path}")
        else:
            self.bottom_label.config(text="File no longer exists or isn't accessible.")

    def _on_file_right_click_reveal(self, event):
        """
        Right-click on a file list item:
        - Reveal file in folder (Explorer select on Windows).
        """
        # Figure out which row was right-clicked
        idx = self.file_list.nearest(event.y)
        if idx < 0 or idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]
        if os.path.isfile(file_path):
            reveal_in_folder(file_path)
            self.bottom_label.config(text=f"Revealed in folder: {file_path}")
        else:
            self.bottom_label.config(text="File no longer exists or isn't accessible.")
