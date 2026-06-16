from depot import storage
from depot.app import create_app


def test_index_lists_files(client, config):
    storage.save_files(config, [{"name": "Manual", "description": "d", "url": "u", "filename": "m.pdf"}])
    resp = client.get("/")
    assert resp.status_code == 200
    assert b"Manual" in resp.data


def test_index_emits_flat_list_with_controls(client, config):
    storage.save_files(
        config,
        [
            {"name": "LL OS", "description": "", "url": "http://h/ll.zip", "filename": "ll.zip", "tags": ["Vision", "Limelight"]},
            {"name": "WPILib", "description": "", "url": "http://h/w.iso", "filename": "w.iso", "tags": ["WPILib"]},
            {"name": "Mystery", "description": "", "url": "http://h/m.bin", "filename": "m.bin"},
        ],
    )
    html = client.get("/").get_data(as_text=True)
    # Grouping/sorting now happen client-side: server emits each file once...
    assert html.count('data-name="ll os"') == 1
    # ...with the data the JS needs to group/sort.
    assert 'data-tags="Vision|Limelight"' in html
    assert 'id="groupBy"' in html and 'id="sortBy"' in html and 'id="filter"' in html


def test_add_file_with_tags(client, config):
    client.post(
        "/admin/add_file",
        data={"name": "Tagged", "description": "x", "url": "https://h/t.zip", "tags": "Vision, REV"},
        follow_redirects=True,
    )
    assert storage.load_files(config)[0]["tags"] == ["Vision", "REV"]


def test_download_404_when_not_cached(client):
    assert client.get("/download/nope.bin").status_code == 404


def test_download_serves_cached_file(client, config):
    (config.cache_dir / "ok.bin").write_bytes(b"hello")
    resp = client.get("/download/ok.bin")
    assert resp.status_code == 200
    assert resp.data == b"hello"


def test_download_rejects_traversal(client):
    # Should not escape the cache dir.
    resp = client.get("/download/..%2f..%2ffiles.json")
    assert resp.status_code == 404


def test_cache_management_open_without_password(client):
    # Cache management is always reachable by general users.
    assert client.get("/admin").status_code == 200


def test_system_open_when_no_password(client):
    assert client.get("/admin/system").status_code == 200


def test_cache_status_json(client, config):
    storage.save_files(config, [{"name": "A", "description": "", "url": "u", "filename": "a.bin"}])
    (config.cache_dir / "a.bin").write_bytes(b"hello")
    resp = client.get("/admin/cache_status")
    assert resp.status_code == 200
    rows = resp.get_json()
    assert rows[0]["filename"] == "a.bin"
    assert rows[0]["cached"] is True
    assert rows[0]["size"] == "5.0 B"


def test_add_file_appends_and_queues_sync(client, config):
    resp = client.post(
        "/admin/add_file",
        data={"name": "Game", "description": "x", "url": "https://h/game.zip"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    files = storage.load_files(config)
    assert files[0]["filename"] == "game.zip"


def test_upload_secures_filename(client, config):
    import io

    data = {"file": (io.BytesIO(b"data"), "../evil.bin")}
    client.post("/admin/upload_file", data=data, content_type="multipart/form-data")
    # secure_filename strips the path; the file lands flat in the cache dir.
    assert (config.cache_dir / "evil.bin").exists()
    assert not (config.cache_dir.parent / "evil.bin").exists()


def test_export_copies_cached_files(client, config, tmp_path):
    (config.cache_dir / "a.iso").write_bytes(b"data")
    (config.cache_dir / "big.part").write_bytes(b"x")  # in-progress: must be skipped
    dest = tmp_path / "usb"
    dest.mkdir()
    resp = client.post("/admin/export", data={"dest": str(dest)}, follow_redirects=True)
    assert resp.status_code == 200
    assert (dest / "a.iso").read_bytes() == b"data"
    assert not (dest / "big.part").exists()


def test_export_rejects_missing_dest(client, tmp_path):
    resp = client.post(
        "/admin/export", data={"dest": str(tmp_path / "nope")}, follow_redirects=True
    )
    assert b"not an existing folder" in resp.data


def test_delete_file(client, config):
    storage.save_files(config, [{"name": "A", "url": "u", "filename": "a.bin", "description": ""}])
    client.post("/admin/delete_file/0", follow_redirects=True)
    assert storage.load_files(config) == []


def test_index_shows_download_for_cached_and_cache_button_otherwise(client, config):
    storage.save_files(
        config,
        [
            {"name": "Cached", "description": "", "url": "http://h/c.bin", "filename": "c.bin"},
            {"name": "Uncached", "description": "", "url": "http://h/u.bin", "filename": "u.bin"},
        ],
    )
    (config.cache_dir / "c.bin").write_bytes(b"x")
    # Pretend we are online so the cache button (not the offline badge) renders.
    services = client.application.extensions["depot"]
    services.state.set("internet_connected", True)

    html = client.get("/").get_data(as_text=True)
    assert "/download/c.bin" in html          # cached -> direct download
    assert "/cache_and_download/1" in html     # uncached -> cache & download


def test_cache_and_download_redirects_when_already_cached(client, config):
    storage.save_files(config, [{"name": "A", "description": "", "url": "http://h/a.bin", "filename": "a.bin"}])
    (config.cache_dir / "a.bin").write_bytes(b"x")
    resp = client.post("/cache_and_download/0")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/download/a.bin")


def test_cache_and_download_offline_uncached_flashes(client, config):
    storage.save_files(config, [{"name": "A", "description": "", "url": "http://h/a.bin", "filename": "a.bin"}])
    resp = client.post("/cache_and_download/0", follow_redirects=True)
    assert resp.status_code == 200
    assert b"no internet" in resp.data.lower()


def test_cache_and_download_fetches_when_online(client, config, monkeypatch):
    storage.save_files(config, [{"name": "A", "description": "", "url": "http://h/a.bin", "filename": "a.bin"}])
    services = client.application.extensions["depot"]
    services.state.set("internet_connected", True)
    # Pretend the download succeeds by writing the file.
    monkeypatch.setattr(
        services.cache, "download",
        lambda url, path: bool((open(path, "wb").write(b"data"), True)[1]),
    )
    resp = client.post("/cache_and_download/0")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/download/a.bin")


# --- auth-enabled variant -------------------------------------------------
def _auth_client(auth_config):
    return create_app(auth_config, start_workers=False).test_client()


def test_cache_management_stays_open_when_system_locked(auth_config):
    # Setting an admin password must NOT lock general users out of caching.
    client = _auth_client(auth_config)
    assert client.get("/admin").status_code == 200


def test_system_redirects_to_login_when_protected(auth_config):
    client = _auth_client(auth_config)
    resp = client.get("/admin/system")
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_system_routes_locked_when_protected(auth_config):
    client = _auth_client(auth_config)
    # A system-changing action is rejected (redirected to login) without auth.
    resp = client.post("/admin/update_id", data={"system_id": "Hacked"})
    assert resp.status_code == 302
    assert "/admin/login" in resp.headers["Location"]


def test_login_grants_system_access(auth_config):
    client = _auth_client(auth_config)
    assert client.post("/admin/login", data={"password": "wrong"}).status_code == 200
    client.post("/admin/login", data={"password": "hunter2"})
    assert client.get("/admin/system").status_code == 200
