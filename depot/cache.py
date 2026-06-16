"""Cache downloader and the background sync worker."""

from __future__ import annotations

import logging
import os
import time

import requests

from . import storage

log = logging.getLogger(__name__)

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
)
_CHUNK = 16384


class CacheManager:
    def __init__(self, config, state):
        self.config = config
        self.state = state

    # -- status ----------------------------------------------------------
    def update_status(self, files: list[dict]) -> None:
        """Recompute the per-file cache table shown in the admin panel."""
        log_rows = []
        for item in files:
            filename = item.get("filename", "")
            local_path = self.config.cache_dir / filename
            cached = local_path.exists()

            size = "-"
            if cached:
                try:
                    size = storage.convert_size(local_path.stat().st_size)
                except OSError:
                    size = "Error"

            log_rows.append(
                {
                    "name": item.get("name"),
                    "cached": cached,
                    "url": item.get("url"),
                    "filename": filename,
                    "size": size,
                    "progress": self.state.progress_of(filename),
                    "tags": item.get("tags") or [],
                }
            )
        self.state.set("cache_log", log_rows)

    # -- download --------------------------------------------------------
    def download(self, url: str, local_path) -> bool:
        filename = os.path.basename(local_path)
        headers = {"User-Agent": _BROWSER_UA}
        self.state.set_progress(filename, 0)
        # Download to a temp file so an interrupted transfer never looks cached.
        tmp_path = f"{local_path}.part"

        log.info("Downloading %s ...", filename)
        try:
            with requests.get(
                url,
                stream=True,
                timeout=(10, 60),
                headers=headers,
                verify=self.config.verify_ssl,
            ) as response:
                if response.status_code != 200:
                    log.error("HTTP %s for %s", response.status_code, filename)
                    return False

                total = response.headers.get("content-length")
                total = int(total) if total and total.isdigit() else None

                with open(tmp_path, "wb") as f:
                    if total is None:
                        self.state.set_progress(filename, -1)  # unknown size
                        for chunk in response.iter_content(_CHUNK):
                            f.write(chunk)
                    else:
                        done = 0
                        for chunk in response.iter_content(_CHUNK):
                            f.write(chunk)
                            done += len(chunk)
                            percent = int(100 * done / total)
                            if percent > (self.state.progress_of(filename) or 0):
                                self.state.set_progress(filename, percent)

            os.replace(tmp_path, local_path)
            log.info("Cached %s", filename)
            return True

        except requests.RequestException as exc:
            log.error("Download failed for %s: %s", filename, exc)
            return False
        except OSError as exc:
            log.error("Write failed for %s: %s", filename, exc)
            return False
        finally:
            self.state.clear_progress(filename)
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass

    def download_missing(self, files: list[dict]) -> None:
        for item in files:
            filename = item.get("filename")
            url = item.get("url")
            if not filename or not url:
                continue
            local_path = self.config.cache_dir / filename
            if not local_path.exists():
                self.download(url, local_path)

    # -- worker loop -----------------------------------------------------
    def _sweep_partials(self) -> None:
        """Delete leftover .part files (e.g. from a download cut short by a
        restart) so they don't linger or get flagged."""
        for partial in self.config.cache_dir.glob("*.part"):
            try:
                partial.unlink()
                log.info("Removed stale partial download %s", partial.name)
            except OSError as exc:
                log.error("Could not remove %s: %s", partial.name, exc)

    def run(self) -> None:
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self._sweep_partials()
        while True:
            self._wait_for_tick()
            try:
                files = storage.load_files(self.config)
                self.update_status(files)
                if self.state.get("internet_connected"):
                    self.download_missing(files)
                    self.state.set("last_sync", time.strftime("%H:%M:%S"))
                self.update_status(files)
            except Exception:  # never let the worker die
                log.exception("Cache sync pass failed")

    def _wait_for_tick(self) -> None:
        """Sleep up to sync_interval, waking early on a forced refresh."""
        for _ in range(self.config.sync_interval):
            if self.state.get("force_refresh"):
                self.state.set("force_refresh", False)
                return
            time.sleep(1)
