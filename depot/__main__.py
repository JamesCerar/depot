"""Run the Depot app: ``python -m depot``.

Starts the background workers and serves the Flask app. This is the entry point
used by ``launcher.sh`` on the Pi.
"""

from __future__ import annotations

import logging

from .app import create_app
from .config import load_config


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config()
    app = create_app(config, start_workers=True)

    # threaded so a slow on-demand "Cache & Download" doesn't block the
    # admin page or other users.
    app.run(host=config.host, port=config.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
