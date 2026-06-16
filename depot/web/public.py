"""Public-facing routes: the download landing page and file downloads."""

from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    send_from_directory,
    url_for,
)

from .. import storage
from . import services

public_bp = Blueprint("public", __name__)


@public_bp.route("/")
def index():
    svc = services()
    files = storage.load_files(svc.config)

    # Emit a flat list of cards with data attributes; the page does grouping,
    # sorting and search on the client so switching is instant and offline.
    items = []
    for i, item in enumerate(files):
        filename = item.get("filename", "")
        path = svc.config.cache_dir / filename
        cached = bool(filename) and path.exists()
        size_bytes = path.stat().st_size if cached else None
        items.append(
            {
                **item,
                "index": i,
                "tags": storage.tags_of(item),
                "cached": cached,
                "size_bytes": size_bytes,
                "size_label": storage.convert_size(size_bytes) if size_bytes else "",
                "added": item.get("added") or "",
            }
        )
    # Default order for no-JS clients: alphabetical.
    items.sort(key=lambda e: (e.get("name") or "").lower())

    return render_template(
        "index.html",
        files=items,
        total=len(files),
        category_order=storage.CATEGORY_ORDER + [storage.UNTAGGED],
        state=svc.state.snapshot(),
    )


@public_bp.route("/download/<path:filename>")
def download(filename: str):
    svc = services()
    target = (svc.config.cache_dir / filename).resolve()
    # Guard against path traversal: must stay inside the cache dir.
    if svc.config.cache_dir.resolve() not in target.parents or not target.is_file():
        abort(404, "File not cached yet.")
    return send_from_directory(svc.config.cache_dir, filename, as_attachment=True)


@public_bp.route("/cache_and_download/<int:index>", methods=["POST"])
def cache_and_download(index: int):
    """Fetch a not-yet-cached file on demand, then hand it to the browser."""
    svc = services()
    files = storage.load_files(svc.config)
    if not (0 <= index < len(files)):
        abort(404)

    item = files[index]
    filename = item.get("filename")
    url = item.get("url")
    if not filename or not url:
        abort(404)

    local_path = svc.config.cache_dir / filename
    if not local_path.exists():
        if not svc.state.get("internet_connected"):
            flash(
                f"“{item.get('name')}” isn’t cached yet and there’s no internet "
                "to fetch it right now.",
                "error",
            )
            return redirect(url_for("public.index"))
        svc.config.cache_dir.mkdir(parents=True, exist_ok=True)
        if not svc.cache.download(url, local_path):
            flash(f"Couldn’t download “{item.get('name')}”. Please try again later.", "error")
            return redirect(url_for("public.index"))

    return redirect(url_for("public.download", filename=filename))
