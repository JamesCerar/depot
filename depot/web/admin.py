"""Admin blueprint.

Two areas live under ``/admin``:

* **Cache management** (``/admin``) — open to general users: the file list,
  add/upload/edit/delete, CSA Tools load, force refresh, orphan cleanup.
* **System** (``/admin/system``) — gated by the admin password: system identity,
  hardware/LED controls, and service restart.

When no admin password is configured both areas are reachable; setting one locks
only the System area.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
from pathlib import Path

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from werkzeug.utils import secure_filename

from .. import storage
from . import services
from .auth import is_authed, login, login_required, logout

log = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _back():
    """Back to the cache-management page."""
    return redirect(url_for("admin.dashboard"))


def _system_back():
    """Back to the locked system page."""
    return redirect(url_for("admin.system"))


# ======================================================================
# Authentication (guards the System area only)
# ======================================================================
@admin_bp.route("/login", endpoint="login", methods=["GET", "POST"])
def login_view():
    if is_authed():
        return _system_back()
    if request.method == "POST":
        if login(request.form.get("password", "")):
            return redirect(request.args.get("next") or url_for("admin.system"))
        flash("Incorrect password.", "error")
    return render_template("login.html")


@admin_bp.route("/logout", methods=["POST"])
def logout_view():
    logout()
    flash("Logged out.", "ok")
    return redirect(url_for("public.index"))


# ======================================================================
# Cache management — open to general users
# ======================================================================
@admin_bp.route("")
def dashboard():
    svc = services()
    files = storage.load_files(svc.config)
    svc.cache.update_status(files)
    return render_template(
        "manage.html",
        state=svc.state.snapshot(),
        files=files,
        disk=storage.disk_usage(),
        orphans=storage.get_orphans(svc.config, files),
    )


@admin_bp.route("/cache_status")
def cache_status():
    """Live cache status as JSON, polled by the cache page to update in place."""
    svc = services()
    files = storage.load_files(svc.config)
    svc.cache.update_status(files)
    rows = [
        {
            "filename": r["filename"],
            "cached": r["cached"],
            "size": r["size"],
            "progress": r["progress"],
        }
        for r in svc.state.get("cache_log")
    ]
    return jsonify(rows)


@admin_bp.route("/add_file", methods=["POST"])
def add_file():
    svc = services()
    name = request.form.get("name", "").strip()
    url = request.form.get("url", "").strip()
    if name and url:
        files = storage.load_files(svc.config)
        files.append(
            {
                "name": name,
                "description": request.form.get("description", "").strip(),
                "url": url,
                "filename": storage.filename_from_url(url),
                "tags": storage.parse_tags(request.form.get("tags", "")),
                "added": int(time.time()),
            }
        )
        storage.save_files(svc.config, files)
        svc.state.set("force_refresh", True)
        flash(f"Added “{name}”. Sync starting…", "ok")
    else:
        flash("Name and URL are required.", "error")
    return _back()


@admin_bp.route("/edit_file/<int:index>")
def edit_view(index: int):
    svc = services()
    files = storage.load_files(svc.config)
    if 0 <= index < len(files):
        return render_template(
            "edit.html", file=files[index], index=index, state=svc.state.snapshot()
        )
    return _back()


@admin_bp.route("/update_file/<int:index>", methods=["POST"])
def update_file(index: int):
    svc = services()
    files = storage.load_files(svc.config)
    if 0 <= index < len(files):
        url = request.form.get("url", "").strip()
        files[index]["name"] = request.form.get("name", "").strip()
        files[index]["description"] = request.form.get("description", "").strip()
        files[index]["url"] = url
        files[index]["filename"] = storage.filename_from_url(url)
        files[index]["tags"] = storage.parse_tags(request.form.get("tags", ""))
        storage.save_files(svc.config, files)
        svc.state.set("force_refresh", True)
        flash("File updated.", "ok")
    return _back()


@admin_bp.route("/delete_file/<int:index>", methods=["POST"])
def delete_file(index: int):
    svc = services()
    files = storage.load_files(svc.config)
    if 0 <= index < len(files):
        removed = files.pop(index)
        storage.save_files(svc.config, files)
        flash(f"Removed “{removed.get('name')}” from the list.", "ok")
    return _back()


@admin_bp.route("/refresh", methods=["POST"])
def refresh():
    services().state.set("force_refresh", True)
    flash("Cache refresh queued.", "ok")
    return _back()


@admin_bp.route("/getcsatools", methods=["POST"])
def get_csa_tools():
    svc = services()
    try:
        added, skipped = storage.sync_csa_tools(svc.config)
        if added:
            svc.state.set("force_refresh", True)
        flash(
            f"Added {added} new file(s) from the CSA Tools list "
            f"({skipped} already present).",
            "ok",
        )
    except Exception as exc:  # network/parse errors
        log.error("CSA sync failed: %s", exc)
        flash(f"CSA Tools sync failed: {exc}", "error")
    return _back()


@admin_bp.route("/cleanup", methods=["POST"])
def cleanup():
    svc = services()
    files = storage.load_files(svc.config)
    deleted = 0
    for name in storage.get_orphans(svc.config, files):
        try:
            (svc.config.cache_dir / name).unlink()
            deleted += 1
        except OSError as exc:
            log.error("Could not delete orphan %s: %s", name, exc)
    flash(f"Deleted {deleted} unused file(s).", "ok")
    return _back()


@admin_bp.route("/export", methods=["POST"])
def export():
    """Copy every cached file to a destination folder (e.g. a mounted USB)."""
    svc = services()
    dest = request.form.get("dest", "").strip()
    if not dest:
        flash("Enter a destination folder to export to.", "error")
        return _back()

    dest_path = Path(dest)
    if not dest_path.is_dir():
        flash(f"Destination “{dest}” is not an existing folder.", "error")
        return _back()
    if dest_path.resolve() == svc.config.cache_dir.resolve():
        flash("Destination is the cache itself — choose a different folder.", "error")
        return _back()

    copied = errors = 0
    for f in sorted(svc.config.cache_dir.iterdir()):
        if not f.is_file() or f.name.startswith(".") or f.name.endswith(".part"):
            continue
        try:
            shutil.copy2(f, dest_path / f.name)
            copied += 1
        except OSError as exc:
            errors += 1
            log.error("Export failed for %s: %s", f.name, exc)

    if errors:
        flash(f"Exported {copied} file(s) to {dest}; {errors} failed (see logs).", "error")
    else:
        flash(f"Exported {copied} file(s) to {dest}.", "ok")
    return _back()


@admin_bp.route("/upload_file", methods=["POST"])
def upload_file():
    svc = services()
    file = request.files.get("file")
    if not file or not file.filename:
        flash("No file selected.", "error")
        return _back()

    filename = secure_filename(file.filename)
    if not filename:
        flash("Invalid filename.", "error")
        return _back()

    svc.config.cache_dir.mkdir(parents=True, exist_ok=True)
    file.save(svc.config.cache_dir / filename)
    svc.state.clear_progress(filename)
    flash(f"Uploaded {filename}.", "ok")
    return _back()


# ======================================================================
# System — password-locked
# ======================================================================
@admin_bp.route("/system")
@login_required
def system():
    svc = services()
    return render_template("system.html", state=svc.state.snapshot())


@admin_bp.route("/update_id", methods=["POST"])
@login_required
def update_id():
    svc = services()
    new_id = request.form.get("system_id", "").strip()
    if new_id:
        storage.set_system_id(svc.config, new_id)
        flash("System ID updated.", "ok")
    return _system_back()


@admin_bp.route("/system/restart", methods=["POST"])
@login_required
def restart():
    # Exit shortly after responding; systemd (Restart=always) relaunches us,
    # and launcher.sh does a git pull on the way back up.
    flash("Restarting… this page will be unavailable for a moment.", "ok")
    threading.Timer(1.0, lambda: os._exit(0)).start()
    return _system_back()
