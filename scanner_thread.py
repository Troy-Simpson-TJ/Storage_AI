"""
scanner_thread.py
Threaded directory scanner using BFS (one directory at a time).

Fix included:
✅ Allows directory symlinks/junctions (important for Documents/OneDrive redirects)
✅ Uses a visited set (real paths) to prevent loops
"""

import os
import threading
import queue
from dataclasses import dataclass
from typing import Callable, List, Tuple


BYTES_IN_MB = 1024 * 1024
BYTES_IN_GB = 1024 * 1024 * 1024


def format_size(num_bytes: int) -> str:
    if num_bytes >= BYTES_IN_GB:
        return f"{num_bytes / BYTES_IN_GB:.2f} GB"
    if num_bytes >= BYTES_IN_MB:
        return f"{num_bytes / BYTES_IN_MB:.2f} MB"
    return f"{num_bytes} B"


@dataclass
class ScanUpdate:
    current_dir: str
    scanned_dirs: int
    scanned_files: int
    top_dirs: List[Tuple[str, int]]
    top_files: List[Tuple[str, int]]


class DirectoryScanner:
    def __init__(
        self,
        root: str,
        on_update: Callable[[ScanUpdate], None],
        on_done: Callable[[str], None],
        max_results: int = 25,
        update_every_dirs: int = 25,
    ):
        self.root = root
        self.on_update = on_update
        self.on_done = on_done
        self.max_results = max_results
        self.update_every_dirs = update_every_dirs

        self._stop_event = threading.Event()
        self._thread = None

        self._dir_queue = queue.Queue()
        self._dir_queue.put(root)

        self.scanned_dirs = 0
        self.scanned_files = 0

        self.dir_sizes = {}  # direct files only
        self.top_files: List[Tuple[str, int]] = []

        # NEW: prevent loops by tracking real paths we've already scanned
        self._visited_realpaths = set()

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def _update_top_files(self, file_path: str, size: int):
        self.top_files.append((file_path, size))
        self.top_files.sort(key=lambda x: x[1], reverse=True)
        if len(self.top_files) > self.max_results:
            self.top_files = self.top_files[: self.max_results]

    def _get_top_dirs(self) -> List[Tuple[str, int]]:
        items = list(self.dir_sizes.items())
        items.sort(key=lambda x: x[1], reverse=True)
        return items[: self.max_results]

    def _send_update(self, current_dir: str):
        self.on_update(
            ScanUpdate(
                current_dir=current_dir,
                scanned_dirs=self.scanned_dirs,
                scanned_files=self.scanned_files,
                top_dirs=self._get_top_dirs(),
                top_files=list(self.top_files),
            )
        )

    def _run(self):
        dirs_since_update = 0

        while not self._dir_queue.empty() and not self._stop_event.is_set():
            current_dir = self._dir_queue.get()

            # NEW: resolve real path and skip if already visited (prevents loops)
            try:
                real = os.path.realpath(current_dir)
            except Exception:
                real = current_dir

            if real in self._visited_realpaths:
                continue
            self._visited_realpaths.add(real)

            self.scanned_dirs += 1
            dirs_since_update += 1

            if current_dir not in self.dir_sizes:
                self.dir_sizes[current_dir] = 0

            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        if self._stop_event.is_set():
                            break

                        # IMPORTANT CHANGE:
                        # We do NOT blanket-skip symlinks anymore,
                        # because Documents/OneDrive folders can be junctions.
                        # Instead we allow directories and rely on visited_realpaths to prevent loops.

                        # Queue subdirectories (including junctions)
                        try:
                            if entry.is_dir(follow_symlinks=True):
                                self._dir_queue.put(entry.path)
                                continue
                        except Exception:
                            continue

                        # Process files (follow_symlinks=False is fine)
                        try:
                            if entry.is_file(follow_symlinks=False):
                                size = entry.stat().st_size
                                self.scanned_files += 1
                                self.dir_sizes[current_dir] += size
                                self._update_top_files(entry.path, size)
                        except Exception:
                            continue

            except Exception:
                # Permission denied / inaccessible
                pass

            if dirs_since_update >= self.update_every_dirs:
                dirs_since_update = 0
                self._send_update(current_dir=current_dir)

        self._send_update(current_dir="(done)")
        self.on_done("Scan stopped." if self._stop_event.is_set() else "Scan finished.")
