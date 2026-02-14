"""
filesystem_sources.py
- This module finds directories/roots that are good options to scan.
- These options will appear in the Combobox inside the UI.

On Windows, we include:
- Mounted drives (C:\, D:\, etc.)
- Common user folders (Desktop, Downloads, Documents, etc.)

We use psutil to list partitions (drives).
"""

import os
import psutil


def get_scan_roots():
    """
    Returns a list of scan root paths that exist on the computer.

    Example Windows output:
    [
      "C:\\",
      "D:\\",
      "C:\\Users\\T\\Downloads",
      "C:\\Users\\T\\Documents"
    ]
    """

    roots = []

    # 1) Add all "normal" mounted partitions (drives)
    #    psutil.disk_partitions(all=False) returns partition info.
    for part in psutil.disk_partitions(all=False):
        mountpoint = part.mountpoint  # e.g. "C:\\"
        if mountpoint and os.path.exists(mountpoint):
            roots.append(mountpoint)

    # 2) Add common user folders (Windows style)
    #    USERPROFILE is like "C:\\Users\\Troy"
    userprofile = os.environ.get("USERPROFILE")
    if userprofile and os.path.exists(userprofile):
        common_names = ["Desktop", "Downloads", "Documents", "Pictures", "Videos", "Music"]
        for name in common_names:
            path = os.path.join(userprofile, name)
            if os.path.exists(path):
                roots.append(path)

    # 3) Remove duplicates but keep order (stable de-dupe)
    seen = set()
    cleaned = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            cleaned.append(r)

    return cleaned
