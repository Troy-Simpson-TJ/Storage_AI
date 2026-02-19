"""
ui_app.py

WHAT THIS FILE DOES (high level):
1) Shows a UI where you can pick a scan root and start/stop scanning.
2) Shows top largest directories + files.
3) Lets you click directories to open them.
4) Lets you click files to open them, right-click to reveal them in Explorer.
5) Adds a "Recycle Bin" drop target:
   - Drag a FILE row from the Files list
   - When your mouse is over the bin -> bin image switches OPEN
   - When you move away -> switches CLOSED
   - When you drop on the bin -> the file is sent to Windows Recycle Bin (send2trash)

IMPORTANT:
- The scanning happens in scanner_thread.py (background thread).
- The UI updates MUST happen on the main Tkinter thread (we use .after()).
"""

import os
import math
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

# send2trash safely sends files to the OS Recycle Bin instead of deleting permanently
from send2trash import send2trash  # pip install send2trash
from PIL import Image, ImageTk

from filesystem_sources import get_scan_roots
from scanner_thread import DirectoryScanner, format_size
from open_utils import open_file, open_folder, reveal_in_folder

def resource_path(relative_path: str) -> str:
    """
    Returns a usable absolute path to bundled resources.

    - In VS Code / normal python runs: uses your project folder
    - In PyInstaller onefile exe: uses the temporary _MEIPASS folder
    """
    try:
        base_path = sys._MEIPASS  # type: ignore[attr-defined]
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)



class StorageScannerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        
        # Load custom window icon from images folder
        # ✅ Window icon (must be .ico for iconbitmap)
        icon_path = resource_path("images/appicon.ico")
        if os.path.exists(icon_path):
            self.iconbitmap(icon_path)


        # ---------------- Window setup ----------------
        self.title("Storage Analyzer")
        self.geometry("980x590")
        self.minsize(980, 590)

        # Will hold our DirectoryScanner instance while scanning is active
        self.scanner = None

        # These arrays map Listbox row index -> real path string.
        # Example: if you click row 0 in file_list, file_path = self._file_paths[0].
        self._dir_paths = [] 
        self._file_paths = []

        # ---------------- Drag-drop state (FILES ONLY) ----------------
        # When user clicks and moves mouse enough, we treat it as a drag.
        self._dragging = False              # True when drag actually started
        self._drag_index = None             # Which file row is being dragged
        self._drag_start_x = 0              # Where mouse down started (screen coordinates)
        self._drag_start_y = 0
        self._drag_ghost = None             # A tiny label that follows mouse (feedback)
        self._drag_threshold = 6            # Pixels needed to count as a "drag" vs a click

        # We use global bindings so dropping still works if the mouse leaves the listbox
        self._global_drag_bindings_active = False

        # Recycle bin images (two states)
        self.bin_closed_img = None
        self.bin_open_img = None

        # Theme first (defines colors), then build UI
        self._apply_theme()
        self._build_ui()

    # ---------------- THEME ----------------
    def _apply_theme(self):
        """Defines theme colors and applies ttk style rules."""
        self.BG = "#0b1020"        # deep blue-black background
        self.PANEL = "#0f1730"     # panel background color
        self.BLUE = "#2d6cff"      # accent blue
        self.TEXT = "#e8ecff"      # main text color
        self.MUTED = "#b6c2ff"     # softer text color
        self.LIST_BG = "#070b16"   # listbox background
        self.LIST_SEL = "#123a8a"  # selection background
        self.LIST_FG = self.TEXT

        self.configure(bg=self.BG)

        style = ttk.Style(self)

        # Try to use "clam" because it is easiest to style consistently
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Default styling for ttk widgets
        style.configure(".", background=self.BG, foreground=self.TEXT, font=("Segoe UI", 10))
        style.configure("TFrame", background=self.BG)
        style.configure("TLabel", background=self.BG, foreground=self.TEXT)
        style.configure("TLabelframe", background=self.BG, foreground=self.TEXT)

        # Style the label of a LabelFrame (the title text)
        style.configure(
            "TLabelframe.Label",
            background=self.BG,
            foreground=self.MUTED,
            font=("Segoe UI", 10, "bold")
        )

        # Buttons
        style.configure("TButton", background=self.PANEL, foreground=self.TEXT, bordercolor=self.BLUE)
        style.map("TButton",
                  background=[("active", "#13204a")],
                  foreground=[("active", self.TEXT)])

        # Text entry and combobox style
        style.configure("TEntry", fieldbackground=self.LIST_BG, foreground=self.TEXT)
        style.configure("TCombobox", fieldbackground=self.LIST_BG, foreground=self.TEXT)

        # Combobox dropdown list colors (works differently on some systems, but helps)
        self.option_add("*TCombobox*Listbox.background", self.LIST_BG)
        self.option_add("*TCombobox*Listbox.foreground", self.TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", self.LIST_SEL)
        self.option_add("*TCombobox*Listbox.selectForeground", self.TEXT)

        # Progressbar styles for different colors based on "progress"
        style.configure("Red.Horizontal.TProgressbar", troughcolor=self.LIST_BG, background="#d64545")
        style.configure("Yellow.Horizontal.TProgressbar", troughcolor=self.LIST_BG, background="#f1c40f")
        style.configure("Green.Horizontal.TProgressbar", troughcolor=self.LIST_BG, background="#2ecc71")

    # ---------------- UI BUILD ----------------
    def _build_ui(self):
        """Creates every widget and places them on the window."""
        
        # ---------- Top controls row ----------
        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="Choose a File Directory:").pack(side="left")

        # This comes from filesystem_sources.py
        self.roots = get_scan_roots()
        if not self.roots:
            self.roots = ["C:\\"]  # fallback directory if nothing found or selected

        self.root_var = tk.StringVar(value=self.roots[0])
        self.root_combo = ttk.Combobox(
            top,
            textvariable=self.root_var,
            values=self.roots,
            state="readonly",
            width=70
        )
        self.root_combo.pack(side="left", padx=8)

        # Start / Stop scan buttons
        self.start_btn = ttk.Button(top, text="Start Scan", command=self.start_scan)
        self.start_btn.pack(side="left", padx=6)

        self.stop_btn = ttk.Button(top, text="Stop", command=self.stop_scan, state="disabled")
        self.stop_btn.pack(side="left", padx=6)

        # Max results entry
        ttk.Label(top, text="Max results:").pack(side="left", padx=(18, 6))
        vcmd = (self.register(lambda s: s.isdigit() or s == ""), "%P")
        self.max_results_var = tk.StringVar(value="25")

        ttk.Entry(
            top,
            textvariable=self.max_results_var,
            width=6,
            validate="key",
            validatecommand=vcmd
        ).pack(side="left")


        # ---------- Status area ----------
        status = ttk.LabelFrame(self, text="Status")
        status.pack(fill="x", padx=12, pady=(0, 10))

        # Text above progress bar
        self.progress_text = tk.StringVar(value="Not started")
        ttk.Label(status, textvariable=self.progress_text).pack(anchor="w", padx=10, pady=(6, 2))

        # Progress bar (we estimate progress since we don't know total directories)
        self.progress_value = tk.DoubleVar(value=0.0)
        self.progress_bar = ttk.Progressbar(
            status,
            variable=self.progress_value,
            maximum=100.0,
            mode="determinate",
            style="Red.Horizontal.TProgressbar"
        )
        self.progress_bar.pack(fill="x", padx=10, pady=(0, 6))

      # ---------- Recycle Bin drop target (IMAGE ONLY) ----------
        # Use tk.Frame here so bg + height behave predictably
        bin_row = tk.Frame(status, bg=self.BG, height=90)
        bin_row.pack(fill="x", padx=10, pady=(0, 6))
        bin_row.pack_propagate(False)  # <- prevents shrinking smaller than height

        closed_path = resource_path("images/ClosedRecycleBin.png")
        open_path = resource_path("images/OpenRecycleBin.png")

        # Pick a fixed on-screen size (change this)
        BIN_W, BIN_H = 96, 172

        def load_resized_png(path: str):
            img = Image.open(path).convert("RGBA")
            img = img.resize((BIN_W, BIN_H), Image.LANCZOS)  # type: ignore
            return ImageTk.PhotoImage(img)


        try:
            self.bin_closed_img = load_resized_png(closed_path)
            self.bin_open_img = load_resized_png(open_path)
        except Exception as e:
            # Show the real error instead of silently failing
            messagebox.showerror("Image Load Error", f"Recycle bin images failed:\n\n{e}")
            self.bin_closed_img = None
            self.bin_open_img = None

        if self.bin_closed_img is not None:
            self.bin_label = tk.Label(bin_row, image=self.bin_closed_img, bg=self.BG, bd=0)
        else:
            self.bin_label = tk.Label(bin_row, text="(bin image failed)", bg=self.BG, fg=self.MUTED)

        self.bin_label.pack(side="left", padx=6, pady=6)
        self.bin_label.bind("<Button-1>", self._open_recycle_bin)
        

        ttk.Label(
            bin_row,
            text="Drag FILES onto the bin to send to Recycle Bin",
            foreground=self.MUTED
        ).pack(side="left", padx=12)

        # Current directory text while scanning
        self.current_dir_text = tk.StringVar(value="Current dir: (not started)")
        ttk.Label(status, textvariable=self.current_dir_text, foreground=self.MUTED).pack(anchor="w", padx=10, pady=(0, 6))

        # Counts display
        self.counts_label = ttk.Label(status, text="Dirs scanned: 0 | Files scanned: 0")
        self.counts_label.pack(anchor="w", padx=10, pady=(0, 8))

        # ---------- Results area (lists) ----------
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        left = ttk.LabelFrame(body, text="Largest Directories (click to open folder)")
        left.pack(side="left", fill="both", expand=True, padx=(0, 6))

        right = ttk.LabelFrame(body, text="Largest Files (click to open, right-click to reveal)")
        right.pack(side="left", fill="both", expand=True, padx=(6, 0))

        # Directory listbox
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

        # Files listbox
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

        # Directory click opens folder
        self.dir_list.bind("<<ListboxSelect>>", self._on_dir_selected_open)

        # File list uses special events because we want click AND drag on same list
        self.file_list.bind("<Button-1>", self._file_mouse_down)
        self.file_list.bind("<B1-Motion>", self._file_mouse_drag_local)
        self.file_list.bind("<ButtonRelease-1>", self._file_mouse_up_local)

        # Right click reveal stays separate
        self.file_list.bind("<Button-3>", self._on_file_right_click_reveal)

        # Bottom status label
        self.bottom_label = ttk.Label(self, text="", foreground=self.MUTED)
        self.bottom_label.pack(fill="x", padx=12, pady=(0, 10))

    # ---------------- Bin image switching ----------------
    def _set_bin_open(self):
        """Switch recycle bin image to OPEN when hovered (only if image exists)."""
        if self.bin_open_img is not None:
            self.bin_label.config(image=self.bin_open_img)

    def _set_bin_closed(self):
        """Switch recycle bin image to CLOSED when not hovered (only if image exists)."""
        if self.bin_closed_img is not None:
            self.bin_label.config(image=self.bin_closed_img)
            
    def _open_recycle_bin(self, _event=None):
        """
        Open Windows Recycle Bin in Explorer when user clicks the bin image.
        """
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer.exe", "shell:RecycleBinFolder"], shell=False)
            else:
                messagebox.showinfo("Info", "Recycle Bin opening is only supported on Windows.")
        except Exception as e:
            messagebox.showerror("Error", f"Could not open Recycle Bin.\n\n{e}")


    # ---------------- Progress helpers ----------------
    def _estimated_progress(self, scanned_dirs: int) -> float:
        """
        We don't know total directories in advance.
        Use an exponential curve that approaches 95% as scanning continues.
        On completion we force 100%.
        """
        p = 95.0 * (1.0 - math.exp(-scanned_dirs / 2500.0))
        return max(0.0, min(95.0, p))

    def _set_progress_style(self, value: float):
        """Change bar color based on estimated percent."""
        if value < 33:
            self.progress_bar.config(style="Red.Horizontal.TProgressbar")
        elif value < 66:
            self.progress_bar.config(style="Yellow.Horizontal.TProgressbar")
        else:
            self.progress_bar.config(style="Green.Horizontal.TProgressbar")

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

        # Read max results safely
        try:
            max_results = int(self.max_results_var.get())
            if max_results < 5:
                max_results = 5
        except ValueError:
            max_results = 25

        # Clear UI lists + maps
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

        # Create scanner thread object
        self.scanner = DirectoryScanner(
            root=root,
            max_results=max_results,
            update_every_dirs=25,
            on_update=self._on_scan_update_threadsafe,
            on_done=self._on_scan_done_threadsafe,
        )
        self.scanner.start()

    def stop_scan(self):
        """Ask scanner thread to stop."""
        if self.scanner:
            self.scanner.stop()
            self.bottom_label.config(text="Stopping scan...")

    # Thread-safe wrappers: scanner thread calls these, but UI must update on main thread
    def _on_scan_update_threadsafe(self, update):
        self.after(0, lambda: self._apply_update(update))

    def _on_scan_done_threadsafe(self, msg: str):
        self.after(0, lambda: self._scan_done(msg))

    # ---------------- UI updates (main thread) ----------------
    def _apply_update(self, update):
        """Apply scanner updates to UI."""
        self.current_dir_text.set(f"Current dir: {update.current_dir}")
        self.counts_label.config(text=f"Dirs scanned: {update.scanned_dirs} | Files scanned: {update.scanned_files}")

        est = self._estimated_progress(update.scanned_dirs)
        self.progress_value.set(est)
        self._set_progress_style(est)
        self.progress_text.set("Scanning...")

        # Directories list and map
        self.dir_list.delete(0, tk.END)
        self._dir_paths = []
        for path, size in update.top_dirs:
            self.dir_list.insert(tk.END, f"{format_size(size)}  |  {path}")
            self._dir_paths.append(path)

        # Files list and map
        self.file_list.delete(0, tk.END)
        self._file_paths = []
        for path, size in update.top_files:
            self.file_list.insert(tk.END, f"{format_size(size)}  |  {path}")
            self._file_paths.append(path)

    def _scan_done(self, msg: str):
        """Called when scanner finishes or stops."""
        self.progress_value.set(100.0)
        self.progress_bar.config(style="Green.Horizontal.TProgressbar")
        self.progress_text.set("Done")
        self.current_dir_text.set("Current dir: (done)")
        self.bottom_label.config(text=msg)

        self.scanner = None
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")

    # ---------------- Directories click-to-open ----------------
    def _on_dir_selected_open(self, _event):
        """Open selected directory in file explorer."""
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

    # ---------------- Drag support (Files only) ----------------
    def _start_global_drag_bindings(self):
        """
        Bind mouse move/release at the application level,
        so drop detection still works even when mouse leaves file_list.
        """
        if self._global_drag_bindings_active:
            return
        self._global_drag_bindings_active = True
        self.bind_all("<B1-Motion>", self._file_mouse_drag_global, add="+")
        self.bind_all("<ButtonRelease-1>", self._file_mouse_up_global, add="+")

    def _file_mouse_down(self, event):
        """
        User pressed mouse on file list.
        - We remember the index.
        - We DO NOT open file yet, because they might be dragging.
        """
        idx = self.file_list.nearest(event.y)
        if idx < 0 or idx >= len(self._file_paths):
            self._drag_index = None
            self._dragging = False
            return

        self._drag_index = idx
        self._dragging = False
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root

        # Visually select the item
        self.file_list.selection_clear(0, tk.END)
        self.file_list.selection_set(idx)

        # Stop default listbox handling so our behavior is consistent
        return "break"

    def _file_mouse_drag_local(self, event):
        """
        Mouse moved while button held down on the file list.
        If moved enough -> start drag mode.
        """
        if self._drag_index is None:
            return

        dx = abs(event.x_root - self._drag_start_x)
        dy = abs(event.y_root - self._drag_start_y)  # FIXED: y_root is correct

        # If movement passes threshold, start dragging
        if not self._dragging and (dx >= self._drag_threshold or dy >= self._drag_threshold):
            self._dragging = True
            self._start_global_drag_bindings()

            # Create floating "ghost" label once
            if self._drag_ghost is None:
                self._drag_ghost = tk.Label(
                    self,
                    text="Drop on Recycle Bin",
                    bg=self.PANEL,
                    fg=self.TEXT,
                    padx=8,
                    pady=4
                )

        if self._dragging:
            self._update_drag_visuals(event.x_root, event.y_root)

    def _file_mouse_drag_global(self, event):
        """Global drag handler: keeps hover detection working anywhere in the window."""
        if not self._dragging:
            return
        self._update_drag_visuals(event.x_root, event.y_root)

    def _update_drag_visuals(self, x_root, y_root):
        """
        While dragging:
        - move the ghost label to follow the mouse
        - if the mouse is over the bin label, show OPEN image
        - otherwise show CLOSED image
        """
        if self._drag_ghost is not None:
            # Convert screen coords to window coords
            self._drag_ghost.place(
                x=x_root - self.winfo_rootx() + 12,
                y=y_root - self.winfo_rooty() + 12
            )

        if self._is_over_widget(x_root, y_root, self.bin_label):
            self._set_bin_open()
        else:
            self._set_bin_closed()

    def _file_mouse_up_local(self, event):
        """
        Mouse released inside file_list.
        If we were NOT dragging, treat this as a normal click -> open file.
        If we WERE dragging, global release handles the drop action.
        """
        if self._drag_index is None:
            return

        if not self._dragging:
            idx = self._drag_index
            self._drag_index = None

            if 0 <= idx < len(self._file_paths):
                file_path = self._file_paths[idx]
                if os.path.isfile(file_path):
                    open_file(file_path)
                    self.bottom_label.config(text=f"Opened file: {file_path}")
                else:
                    self.bottom_label.config(text="File not accessible or no longer exists.")

    def _file_mouse_up_global(self, event):
        """
        Mouse released anywhere.
        If dragging AND released over the bin:
            -> confirm -> send2trash -> remove from list
        Always resets bin to CLOSED and hides ghost.
        """
        if self._drag_index is None:
            return

        idx = self._drag_index
        was_dragging = self._dragging

        # Reset visuals now
        self._set_bin_closed()
        if self._drag_ghost is not None:
            self._drag_ghost.place_forget()

        # Reset drag state
        self._drag_index = None
        self._dragging = False

        # If it wasn't a drag, do nothing here (local handler already opened file)
        if not was_dragging:
            return

        # Validate index
        if idx < 0 or idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]

        # Only act if dropped on bin
        if self._is_over_widget(event.x_root, event.y_root, self.bin_label):
            if not os.path.isfile(file_path):
                self.bottom_label.config(text="That item is not a file.")
                return

            confirm = messagebox.askyesno(
                "Send to Recycle Bin",
                f"Move this file to Recycle Bin?\n\n{file_path}"
            )
            if not confirm:
                return

            try:
                send2trash(file_path)
                self.bottom_label.config(text=f"Sent to Recycle Bin: {file_path}")

                # Remove from UI list immediately
                try:
                    current_idx = self._file_paths.index(file_path)
                    self.file_list.delete(current_idx)
                    del self._file_paths[current_idx]
                except ValueError:
                    pass

            except Exception as e:
                messagebox.showerror("Error", f"Could not send to Recycle Bin.\n\n{e}")

    def _is_over_widget(self, x_root: int, y_root: int, widget: tk.Widget) -> bool:
        """
        Returns True if a SCREEN coordinate is inside the widget rectangle.
        This is how we know if the mouse is 'over the recycle bin'.
        """
        wx = widget.winfo_rootx()
        wy = widget.winfo_rooty()
        ww = widget.winfo_width()
        wh = widget.winfo_height()
        return (wx <= x_root <= wx + ww) and (wy <= y_root <= wy + wh)

    # ---------------- Right-click reveal ----------------
    def _on_file_right_click_reveal(self, event):
        """Right click -> reveal file in Explorer (selects it)."""
        idx = self.file_list.nearest(event.y)
        if idx < 0 or idx >= len(self._file_paths):
            return

        file_path = self._file_paths[idx]
        if os.path.isfile(file_path):
            reveal_in_folder(file_path)
            self.bottom_label.config(text=f"Revealed in folder: {file_path}")
        else:
            self.bottom_label.config(text="File not accessible or no longer exists.")
