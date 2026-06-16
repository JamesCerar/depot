"""Flask application factory."""

from __future__ import annotations

import logging
import os

import urllib3
from flask import Flask

from .config import BASE_DIR, Config, load_config
from .services import Services
from .storage import get_system_id
from .web import register_blueprints

log = logging.getLogger(__name__)


def create_app(config: Config | None = None, *, start_workers: bool = False) -> Flask:
    config = config or load_config()

    # The cache intentionally downloads from mirrors with broken certs when
    # verify_ssl is off; silence the per-request warning in that case only.
    if not config.verify_ssl:
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # Templates/static ship with the code, so resolve them from the package
    # root (BASE_DIR), independent of config.base_dir which holds runtime data.
    app = Flask(
        __name__,
        template_folder=str(BASE_DIR / "templates"),
        static_folder=str(BASE_DIR / "static"),
    )
    app.secret_key = config.secret_key or os.urandom(32)

    services = Services(config)
    app.extensions["depot"] = services

    @app.context_processor
    def inject_globals():
        return {
            "system_id": get_system_id(config),
            "auth_enabled": config.auth_enabled,
        }

    register_blueprints(app)

    if start_workers:
        services.start_workers()

    return app
