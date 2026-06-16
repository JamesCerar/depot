"""Shared pytest fixtures.

Every test runs against a temp repo root, so no real files.json is touched.
"""

from __future__ import annotations

import dataclasses

import pytest

from depot.app import create_app
from depot.config import Config


@pytest.fixture
def config(tmp_path):
    cache = tmp_path / "cache"
    cache.mkdir()
    return Config(
        base_dir=tmp_path,
        cache_dir=cache,
        files_config=tmp_path / "files.json",
        id_file=tmp_path / "system_id.txt",
        secret_key="test-secret",
    )


@pytest.fixture
def app(config):
    app = create_app(config, start_workers=False)
    app.config.update(TESTING=True)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_config(config):
    return dataclasses.replace(config, admin_password="hunter2")
