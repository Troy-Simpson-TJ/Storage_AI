"""
filesystem_sources.py
Builds scan roots for the combobox.

Fix:
Adds OneDrive redirected folders (Desktop/Documents/etc.) when present.
This solves the "Desktop has nothing / doesn't scan" issue on many Windows PCs.
"""

import os
import psutil


def _add_if_exists(roots: list, path: str):
    """Helper: add a path if it exists and isn't already in the list."""
    if path and os.path.exists(path) and path not in roots:
        roots.append(path)


def get_scan_roots():
    roots = []

    # ------------------------------------------------------------
    # 1) Drives / partitions (C:\, D:\, etc.)
    # ------------------------------------------------------------
    for part in psutil.disk_partitions(all=False):
        mountpoint = part.mountpoint
        _add_if_exists(roots, mountpoint)

    # ------------------------------------------------------------
    # 2) User profile folders (local)
    # ------------------------------------------------------------
    userprofile = os.environ.get("USERPROFILE")  # e.g. C:\Users\tjsim
    if userprofile and os.path.exists(userprofile):
        for name in ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]:
            _add_if_exists(roots, os.path.join(userprofile, name))

    # ------------------------------------------------------------
    # 3) OneDrive redirected folders (IMPORTANT on many PCs)
    # ------------------------------------------------------------
    onedrive = os.environ.get("OneDrive")  # e.g. C:\Users\tjsim\OneDrive
    if onedrive and os.path.exists(onedrive):
        for name in ["Desktop", "Documents", "Downloads", "Pictures", "Videos", "Music"]:
            _add_if_exists(roots, os.path.join(onedrive, name))

    # ------------------------------------------------------------
    # 4) Stable de-dupe (just in case)
    # ------------------------------------------------------------
    seen = set()
    cleaned = []
    for r in roots:
        r = os.path.abspath(r)
        if r not in seen:
            seen.add(r)
            cleaned.append(r)

    return cleaned
