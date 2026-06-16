"""Web layer: public download page + admin panel blueprints."""

from __future__ import annotations

from flask import Flask, current_app

from ..services import Services


def services() -> Services:
    """The Services container for the current app."""
    return current_app.extensions["depot"]


def register_blueprints(app: Flask) -> None:
    from .admin import admin_bp
    from .public import public_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
