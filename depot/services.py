"""The shared service container.

One :class:`Services` instance is built per app and stored on
``app.extensions["depot"]`` so both request handlers and the background
threads work against the same config and state.
"""

from __future__ import annotations

import logging
import threading

from .cache import CacheManager
from .config import Config
from .monitor import NetMonitor, UpdateChecker
from .state import SystemState

log = logging.getLogger(__name__)


class Services:
    def __init__(self, config: Config):
        self.config = config
        self.state = SystemState()
        self.cache = CacheManager(config, self.state)
        self.net = NetMonitor(config, self.state)
        self.updater = UpdateChecker(config, self.state)
        self._threads: list[threading.Thread] = []

    def start_workers(self) -> None:
        """Launch the background workers as daemon threads."""
        if self._threads:
            return
        targets = {
            "net": self.net.run,
            "cache": self.cache.run,
            "updater": self.updater.run,
        }
        for name, target in targets.items():
            thread = threading.Thread(target=target, name=name, daemon=True)
            thread.start()
            self._threads.append(thread)
        log.info("Started %d background workers.", len(self._threads))
