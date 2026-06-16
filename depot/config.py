"""Configuration loading.

Settings come from three layers, lowest priority first:

  1. Built-in defaults (this file).
  2. A ``config.toml`` file at the repo root (optional).
  3. ``DEPOT_*`` environment variables (optional).

Paths (cache dir, files.json, system_id.txt) live at the repo root.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

# Repo root = parent of this package directory.
BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    # --- paths ---
    base_dir: Path = BASE_DIR
    cache_dir: Path = BASE_DIR / "cache"
    files_config: Path = BASE_DIR / "files.json"
    id_file: Path = BASE_DIR / "system_id.txt"

    # --- web server ---
    host: str = "0.0.0.0"
    port: int = 80
    secret_key: str = ""  # blank -> a random key is generated at startup

    # --- cache / downloads ---
    sync_interval: int = 60          # seconds between cache sync passes
    check_interval: int = 10         # seconds between internet checks
    csa_tools_url: str = (
        "https://raw.githubusercontent.com/JamieSinn/"
        "CSA-USB-Tool/main/Lists/FRC2026.json"
    )
    internet_check_url: str = "http://1.1.1.1"
    internet_check_retries: int = 10
    verify_ssl: bool = False         # many FRC mirrors have broken certs

    # --- admin ---
    admin_password: str = ""         # blank -> admin panel is open (no login)

    @property
    def auth_enabled(self) -> bool:
        return bool(self.admin_password)


# Maps a flat key -> (toml_section, toml_key, converter). The same flat key is
# also used for the DEPOT_<UPPER> environment variable.
_FIELDS = {
    "host": ("server", "host", str),
    "port": ("server", "port", int),
    "secret_key": ("server", "secret_key", str),
    "sync_interval": ("cache", "sync_interval", int),
    "check_interval": ("cache", "check_interval", int),
    "csa_tools_url": ("cache", "csa_tools_url", str),
    "internet_check_url": ("cache", "internet_check_url", str),
    "internet_check_retries": ("cache", "internet_check_retries", int),
    "verify_ssl": ("cache", "verify_ssl", bool),
    "admin_password": ("admin", "password", str),
}


def _coerce(value, converter):
    if converter is bool and isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return converter(value)


def load_config(path: Path | None = None) -> Config:
    """Build a :class:`Config` from defaults, ``config.toml`` and env vars."""
    cfg = Config()
    overrides: dict[str, object] = {}

    toml_path = path or (BASE_DIR / "config.toml")
    data: dict = {}
    if toml_path.exists():
        with open(toml_path, "rb") as f:
            data = tomllib.load(f)

    for key, (section, toml_key, converter) in _FIELDS.items():
        # config.toml
        if section in data and toml_key in data[section]:
            overrides[key] = _coerce(data[section][toml_key], converter)
        # environment variable wins over the file
        env = os.environ.get(f"DEPOT_{key.upper()}")
        if env is not None:
            overrides[key] = _coerce(env, converter)

    return replace(cfg, **overrides) if overrides else cfg
