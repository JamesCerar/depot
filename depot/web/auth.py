"""Optional admin authentication.

If ``admin_password`` is unset the admin panel is open (matching the original
behaviour). If it is set, admin routes require a session login.
"""

from __future__ import annotations

from functools import wraps

from flask import redirect, request, session, url_for

from . import services

_SESSION_KEY = "admin_authed"


def is_authed() -> bool:
    cfg = services().config
    if not cfg.auth_enabled:
        return True
    return session.get(_SESSION_KEY, False)


def login(password: str) -> bool:
    cfg = services().config
    if cfg.auth_enabled and password == cfg.admin_password:
        session[_SESSION_KEY] = True
        return True
    return False


def logout() -> None:
    session.pop(_SESSION_KEY, None)


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_authed():
            return redirect(url_for("admin.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped
