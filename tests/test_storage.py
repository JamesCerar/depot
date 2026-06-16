from depot import storage


def test_convert_size():
    assert storage.convert_size(0) == "0 B"
    assert storage.convert_size(512) == "512.0 B"
    assert storage.convert_size(1024) == "1.0 KB"
    assert storage.convert_size(1536) == "1.5 KB"
    assert storage.convert_size(1024**3) == "1.0 GB"


def test_filename_from_url():
    assert storage.filename_from_url("https://x.com/a/b/game.pdf") == "game.pdf"
    assert storage.filename_from_url("https://x.com/file.zip/") == "file.zip"


def test_save_and_load_roundtrip(config):
    data = [{"name": "A", "description": "d", "url": "u", "filename": "a.bin"}]
    assert storage.save_files(config, data)
    assert storage.load_files(config) == data


def test_load_files_missing_returns_empty(config):
    assert storage.load_files(config) == []


def test_system_id_default_and_set(config):
    assert storage.get_system_id(config) == "Depot-Default"
    storage.set_system_id(config, "Field-1")
    assert storage.get_system_id(config) == "Field-1"


def test_get_orphans(config):
    files = [{"filename": "keep.bin"}]
    (config.cache_dir / "keep.bin").write_bytes(b"x")
    (config.cache_dir / "junk.bin").write_bytes(b"x")
    (config.cache_dir / ".hidden").write_bytes(b"x")
    (config.cache_dir / "big.iso.part").write_bytes(b"x")  # in-progress download
    # .part temp files and hidden files are not orphans.
    assert storage.get_orphans(config, files) == ["junk.bin"]


def test_parse_tags():
    assert storage.parse_tags("") == []
    assert storage.parse_tags("Vision") == ["Vision"]
    assert storage.parse_tags("Vision, Limelight ,Vision") == ["Vision", "Limelight"]
    assert storage.parse_tags(" Field / Network , REV ") == ["Field / Network", "REV"]


def test_tags_of_defaults_to_other():
    assert storage.tags_of({"name": "x"}) == ["Other"]
    assert storage.tags_of({"name": "x", "tags": []}) == ["Other"]
    assert storage.tags_of({"name": "x", "tags": ["A", "B"]}) == ["A", "B"]


def test_categorize_csa():
    assert storage.categorize_csa("NI LabVIEW") == "Driver Station"
    assert storage.categorize_csa("WPILibInstaller Windows64") == "WPILib"
    assert storage.categorize_csa("CTRE Phoenix") == "CTRE"
    assert storage.categorize_csa("REVlib Java/C++ API") == "REV"
    assert storage.categorize_csa("Limelight OS 2026 for LL 4") == "Vision"
    assert storage.categorize_csa("Some Random Tool") == "Other"


def test_order_categories_preferred_then_alpha_then_other():
    cats = ["Other", "Zebra", "Vision", "WPILib", "Apple"]
    assert storage.order_categories(cats) == ["WPILib", "Vision", "Apple", "Zebra", "Other"]


def test_sync_csa_tools_assigns_tags(config, monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Software": [
                {"Name": "WPILib Installer", "Description": "", "Uri": "http://h/w.iso", "FileName": "w.iso"},
            ]}

    monkeypatch.setattr("depot.storage.requests.get", lambda *a, **k: FakeResp())
    storage.sync_csa_tools(config)
    assert storage.load_files(config)[0]["tags"] == ["WPILib"]


def test_sync_csa_tools_backfills_tags_on_untagged_existing(config, monkeypatch):
    # An entry imported before tagging existed (no tags) should get tagged.
    storage.save_files(
        config,
        [{"name": "WPILib Installer", "description": "", "url": "http://h/w.iso", "filename": "w.iso"}],
    )

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {"Software": [
                {"Name": "WPILib Installer", "Description": "", "Uri": "http://h/w.iso", "FileName": "w.iso"},
            ]}

    monkeypatch.setattr("depot.storage.requests.get", lambda *a, **k: FakeResp())
    added, skipped = storage.sync_csa_tools(config)
    assert (added, skipped) == (0, 1)
    assert storage.load_files(config)[0]["tags"] == ["WPILib"]


def test_sync_csa_tools_is_additive(config, monkeypatch):
    # Pre-existing list includes one file that the CSA list also contains.
    storage.save_files(
        config,
        [{"name": "Mine", "description": "", "url": "http://h/dup.zip", "filename": "dup.zip"}],
    )

    class FakeResp:
        def raise_for_status(self):
            pass

        def json(self):
            return {
                "Software": [
                    {"Name": "Dup", "Description": "d", "Uri": "http://h/dup.zip", "FileName": "dup.zip"},
                    {"Name": "New", "Description": "n", "Uri": "http://h/new.zip", "FileName": "new.zip"},
                    {"Name": "Header", "Description": "", "Uri": None, "FileName": None},  # skipped
                ]
            }

    monkeypatch.setattr("depot.storage.requests.get", lambda *a, **k: FakeResp())

    added, skipped = storage.sync_csa_tools(config)
    assert (added, skipped) == (1, 1)

    files = storage.load_files(config)
    filenames = [f["filename"] for f in files]
    assert filenames == ["dup.zip", "new.zip"]  # original kept, new appended once
