"""Thread-safe shared runtime state.

The web request threads and the three background worker threads all read and
write this object, so every access goes through a lock. Templates receive a
plain-dict :meth:`SystemState.snapshot` rather than the live object.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


@dataclass
class SystemState:
    internet_connected: bool = False
    force_refresh: bool = False
    update_available: bool = False
    last_sync: str = "Never"
    # filename -> percent complete (0-100), or -1 when total size is unknown.
    download_progress: dict[str, int] = field(default_factory=dict)
    # list of dicts describing each configured file's cache status.
    cache_log: list[dict] = field(default_factory=list)

    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)

    # -- generic helpers -------------------------------------------------
    def get(self, name: str):
        with self._lock:
            return getattr(self, name)

    def set(self, name: str, value) -> None:
        with self._lock:
            setattr(self, name, value)

    def toggle(self, name: str) -> bool:
        with self._lock:
            value = not getattr(self, name)
            setattr(self, name, value)
            return value

    # -- download progress ----------------------------------------------
    def set_progress(self, filename: str, percent: int) -> None:
        with self._lock:
            self.download_progress[filename] = percent

    def clear_progress(self, filename: str) -> None:
        with self._lock:
            self.download_progress.pop(filename, None)

    def progress_of(self, filename: str):
        with self._lock:
            return self.download_progress.get(filename)

    # -- template view ---------------------------------------------------
    def snapshot(self) -> dict:
        """A consistent, read-only copy for rendering templates."""
        with self._lock:
            return {
                "internet_connected": self.internet_connected,
                "force_refresh": self.force_refresh,
                "update_available": self.update_available,
                "last_sync": self.last_sync,
                "download_progress": dict(self.download_progress),
                "cache_log": list(self.cache_log),
            }
