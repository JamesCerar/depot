"""Background workers: internet monitor and the git update checker.

The LED/relay indicator lives in a separate app; Depot only needs to
know whether the internet is reachable so it can gate cache downloads and show
an online/offline status in the UI.
"""

from __future__ import annotations

import logging
import subprocess
import time

import requests

log = logging.getLogger(__name__)


def check_internet(config) -> bool:
    """True if any of N quick probes to the check URL succeeds."""
    for _ in range(config.internet_check_retries):
        try:
            requests.get(config.internet_check_url, timeout=2)
            return True
        except requests.RequestException:
            continue
    return False


class NetMonitor:
    """Polls the internet and records the result in shared state."""

    def __init__(self, config, state):
        self.config = config
        self.state = state

    def run(self) -> None:
        while True:
            self.state.set("internet_connected", check_internet(self.config))
            time.sleep(self.config.check_interval)


class UpdateChecker:
    """Periodically checks whether the deployed git branch is behind origin."""

    INTERVAL = 300  # seconds

    def __init__(self, config, state):
        self.config = config
        self.state = state

    def run(self) -> None:
        log.info("Update monitor started.")
        while True:
            if self.state.get("internet_connected"):
                self.state.set("update_available", self._is_behind())
            time.sleep(self.INTERVAL)

    def _is_behind(self) -> bool:
        try:
            subprocess.run(
                ["git", "fetch"],
                check=True,
                capture_output=True,
                cwd=self.config.base_dir,
            )
            result = subprocess.run(
                ["git", "status", "-uno"],
                check=True,
                capture_output=True,
                text=True,
                cwd=self.config.base_dir,
            )
            return "Your branch is behind" in result.stdout
        except (subprocess.SubprocessError, OSError) as exc:
            log.error("Update check failed: %s", exc)
            return False
