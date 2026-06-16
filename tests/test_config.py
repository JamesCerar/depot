from depot.config import load_config


def test_toml_and_env_layering(tmp_path, monkeypatch):
    toml = tmp_path / "config.toml"
    toml.write_text(
        "[server]\nport = 8080\n[admin]\npassword = \"fromfile\"\n",
        encoding="utf-8",
    )

    cfg = load_config(toml)
    assert cfg.port == 8080
    assert cfg.admin_password == "fromfile"
    assert cfg.auth_enabled is True
    assert cfg.host == "0.0.0.0"  # default preserved

    # env overrides the file
    monkeypatch.setenv("DEPOT_PORT", "9090")
    monkeypatch.setenv("DEPOT_VERIFY_SSL", "true")
    cfg = load_config(toml)
    assert cfg.port == 9090
    assert cfg.verify_ssl is True


def test_defaults_when_no_file(tmp_path):
    cfg = load_config(tmp_path / "does-not-exist.toml")
    assert cfg.port == 80
    assert cfg.auth_enabled is False
