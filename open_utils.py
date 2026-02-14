"""
open_utils.py
- Opens a file or folder using the operating system.

Windows:
- open_file(path): opens the file directly (default app)
- reveal_in_folder(path): opens File Explorer and selects the file

macOS/Linux:
- open_file(path): opens with default handler
- reveal_in_folder(path): opens the containing folder
"""

import os
import sys
import subprocess


def open_file(path: str):
    """Open a file with the OS default app."""
    path = os.path.abspath(path)

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
        return

    # Linux / other
    subprocess.run(["xdg-open", path], check=False)


def open_folder(path: str):
    """Open a folder in the OS file manager."""
    path = os.path.abspath(path)

    if sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]
        return

    if sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
        return

    subprocess.run(["xdg-open", path], check=False)


def reveal_in_folder(file_path: str):
    """
    Reveal a file in its folder.
    On Windows: selects the file in Explorer.
    Else: opens containing folder.
    """
    file_path = os.path.abspath(file_path)

    if sys.platform.startswith("win"):
        # Explorer select file
        subprocess.run(["explorer", "/select,", file_path], check=False)
        return

    # macOS/Linux fallback: open containing folder
    open_folder(os.path.dirname(file_path))
