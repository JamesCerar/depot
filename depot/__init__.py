"""Depot - FRC event file cache.

A Flask application that runs on a Raspberry Pi (or any machine) and:
  1. Caches large files locally so teams can download them without internet.
  2. Serves a public download page and an admin panel to manage the cache.

Internet-status LED indication lives in a separate app (wifipi). The package is
organised so the web app and the background workers share a single
:class:`~depot.services.Services` container.
"""

from .app import create_app
from .config import Config

__all__ = ["create_app", "Config"]
__version__ = "2.0.0"
