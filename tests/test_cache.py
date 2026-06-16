from depot.cache import CacheManager
from depot.state import SystemState


def test_update_status_reports_cached_and_missing(config):
    state = SystemState()
    cache = CacheManager(config, state)
    (config.cache_dir / "here.bin").write_bytes(b"abc")

    cache.update_status(
        [
            {"name": "Here", "url": "u", "filename": "here.bin"},
            {"name": "Gone", "url": "u", "filename": "gone.bin"},
        ]
    )

    rows = {r["name"]: r for r in state.cache_log}
    assert rows["Here"]["cached"] is True
    assert rows["Here"]["size"] == "3.0 B"
    assert rows["Gone"]["cached"] is False


def test_download_writes_file_and_clears_progress(config, monkeypatch):
    state = SystemState()
    cache = CacheManager(config, state)

    class FakeResp:
        status_code = 200
        headers = {"content-length": "5"}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def iter_content(self, chunk_size):
            yield b"hello"

    monkeypatch.setattr("depot.cache.requests.get", lambda *a, **k: FakeResp())

    target = config.cache_dir / "out.bin"
    assert cache.download("http://x/out.bin", target) is True
    assert target.read_bytes() == b"hello"
    assert state.progress_of("out.bin") is None  # cleared after completion
    assert not (config.cache_dir / "out.bin.part").exists()


def test_sweep_partials_removes_leftover_part_files(config):
    state = SystemState()
    cache = CacheManager(config, state)
    (config.cache_dir / "a.iso.part").write_bytes(b"x")
    (config.cache_dir / "keep.bin").write_bytes(b"x")
    cache._sweep_partials()
    assert not (config.cache_dir / "a.iso.part").exists()
    assert (config.cache_dir / "keep.bin").exists()


def test_download_failure_leaves_no_partial(config, monkeypatch):
    state = SystemState()
    cache = CacheManager(config, state)

    class FakeResp:
        status_code = 404
        headers = {}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("depot.cache.requests.get", lambda *a, **k: FakeResp())

    target = config.cache_dir / "out.bin"
    assert cache.download("http://x/out.bin", target) is False
    assert not target.exists()
    assert not (config.cache_dir / "out.bin.part").exists()
