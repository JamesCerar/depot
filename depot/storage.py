"""File-list persistence and disk helpers.

The cache is described by ``files.json`` (a list of ``{name, description, url,
filename, tags}`` entries; ``tags`` is an optional list of strings). This module
owns reading/writing that file plus the small filesystem helpers the rest of the
app needs.
"""

from __future__ import annotations

import json
import logging
import math
import shutil
import time

import requests

log = logging.getLogger(__name__)

# Default bucket for files with no tags.
UNTAGGED = "Other"

# Preferred order for category sections on the download page. Anything not
# listed is appended alphabetically, with UNTAGGED always last.
CATEGORY_ORDER = [
    "Driver Station",
    "WPILib",
    "CTRE",
    "REV",
    "Vision",
    "Limelight",
    "Studica",
    "Thrifty",
    "Dashboards",
    "Field / Network",
]

# Keyword -> category rules for auto-tagging the CSA Tools list (first match
# wins). Keywords are matched case-insensitively against the item name.
_CSA_RULES: list[tuple[tuple[str, ...], str]] = [
    (("labview", "compactrio", "game tools", "ni "), "Driver Station"),
    (("wpilib", "vs code", "vscode"), "WPILib"),
    (("ctre", "phoenix"), "CTRE"),
    (("rev",), "REV"),
    (("limelight", "apriltag", "rpiboot", "etcher", "balena"), "Vision"),
    (("studica", "navx"), "Studica"),
    (("thrifty",), "Thrifty"),
    (("qdash", "dashboard"), "Dashboards"),
    (("vh-109", "vivid", "network assistant"), "Field / Network"),
]


def parse_tags(raw: str) -> list[str]:
    """Parse a comma-separated tag string into a de-duplicated list."""
    seen: list[str] = []
    for part in (raw or "").split(","):
        tag = part.strip()
        if tag and tag not in seen:
            seen.append(tag)
    return seen


def tags_of(item: dict) -> list[str]:
    """The tags on a file entry, or ``[UNTAGGED]`` if it has none."""
    tags = item.get("tags")
    return list(tags) if tags else [UNTAGGED]


def categorize_csa(name: str) -> str:
    """Pick a category for a CSA Tools entry from its name."""
    low = (name or "").lower()
    for keywords, category in _CSA_RULES:
        if any(k in low for k in keywords):
            return category
    return UNTAGGED


def order_categories(categories) -> list[str]:
    """Order category names: preferred list first, then alpha, UNTAGGED last."""
    present = set(categories)
    ordered = [c for c in CATEGORY_ORDER if c in present]
    extras = sorted(
        c for c in present if c not in CATEGORY_ORDER and c != UNTAGGED
    )
    ordered.extend(extras)
    if UNTAGGED in present:
        ordered.append(UNTAGGED)
    return ordered


def load_files(config) -> list[dict]:
    try:
        with open(config.files_config, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except FileNotFoundError:
        return []
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Could not read %s: %s", config.files_config, exc)
        return []


def save_files(config, data: list[dict]) -> bool:
    try:
        with open(config.files_config, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return True
    except OSError as exc:
        log.error("Could not write %s: %s", config.files_config, exc)
        return False


def get_system_id(config) -> str:
    try:
        with open(config.id_file, "r", encoding="utf-8") as f:
            value = f.read().strip()
            if value:
                return value
    except OSError:
        pass
    return "Depot-Default"


def set_system_id(config, value: str) -> bool:
    try:
        with open(config.id_file, "w", encoding="utf-8") as f:
            f.write(value.strip())
        return True
    except OSError as exc:
        log.error("Could not write system id: %s", exc)
        return False


def get_orphans(config, files: list[dict]) -> list[str]:
    """Files present in the cache dir that are not in the configured list."""
    if not config.cache_dir.exists():
        return []
    on_disk = {p.name for p in config.cache_dir.iterdir() if p.is_file()}
    expected = {item["filename"] for item in files if item.get("filename")}
    # Ignore hidden files and in-progress/leftover download temp files (.part).
    return sorted(
        f for f in (on_disk - expected)
        if not f.startswith(".") and not f.endswith(".part")
    )


def disk_usage(path="/") -> dict:
    """Total/used/free in GB plus percent used."""
    total, used, free = shutil.disk_usage(path)
    return {
        "total": round(total / 2**30, 1),
        "used": round(used / 2**30, 1),
        "free": round(free / 2**30, 1),
        "percent": round(used / total * 100, 1) if total else 0,
    }


def convert_size(size_bytes: int) -> str:
    if size_bytes <= 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    i = min(int(math.floor(math.log(size_bytes, 1024))), len(units) - 1)
    value = round(size_bytes / math.pow(1024, i), 2)
    return f"{value} {units[i]}"


def filename_from_url(url: str) -> str:
    return url.rstrip("/").split("/")[-1]


def sync_csa_tools(config) -> tuple[int, int]:
    """Add any files from the CSA-USB-Tool season list that aren't present yet.

    This is additive: existing entries (and any manually added files) are kept.
    Returns ``(added, skipped)``. Raises on network/parse errors.
    """
    response = requests.get(config.csa_tools_url, timeout=10)
    response.raise_for_status()
    remote = response.json()

    files = load_files(config)
    by_filename = {item.get("filename"): item for item in files}

    added = skipped = 0
    changed = False
    for entry in remote.get("Software", []):
        filename = entry.get("FileName")
        if not filename:
            continue  # skip dropdown/separator objects

        existing = by_filename.get(filename)
        if existing is not None:
            skipped += 1
            # Backfill tags on entries imported before tagging existed.
            if not existing.get("tags"):
                existing["tags"] = [categorize_csa(existing.get("name") or entry.get("Name"))]
                changed = True
            continue

        new_item = {
            "name": entry.get("Name"),
            "description": entry.get("Description"),
            "url": entry.get("Uri"),
            "filename": filename,
            "tags": [categorize_csa(entry.get("Name"))],
            "added": int(time.time()),
        }
        files.append(new_item)
        by_filename[filename] = new_item
        added += 1
        changed = True

    if changed:
        save_files(config, files)
    log.info("CSA sync: added %d, skipped %d already present.", added, skipped)
    return added, skipped
