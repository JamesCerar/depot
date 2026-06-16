<p align="center">
  <img src="static/logo-wordmark.svg" alt="Depot — FRC file cache" width="320">
</p>

# Depot

Depot is an FRC event **file cache** — a local download hub. It pre-caches
large files (FRC software, game manuals, vendor libraries, etc.) onto a box so
teams can grab them over the venue network without internet, much like the CSA
USB Tool but always-on and self-serve.

> Internet-status LED indication lives in a separate app so the indicator keeps
> working independently of this web app.

## What it does

- Caches files listed in `files.json` (added by URL, uploaded, or bulk-loaded
  from Jamie Sinn's CSA-USB-Tool season list, which Depot auto-tags by vendor).
- Serves a public page where teams browse (grouped/sorted/searchable by tag),
  download cached files, or trigger an on-demand "Cache & Download".
- Provides a Cache Management page (open) and a password-lockable System page.
- Exports the whole cache to a folder (e.g. a mounted USB stick).

Runs on any machine — there is no hardware dependency.

## Project layout

```
depot/
  depot/               Python package
    app.py             Flask application factory
    __main__.py        entry point: python -m depot
    config.py          defaults + config.toml + DEPOT_* env vars
    state.py           thread-safe shared runtime state
    storage.py         files.json, tags, system id, disk + size helpers
    cache.py           downloader + background cache sync worker
    monitor.py         internet monitor + git update checker
    services.py        wires everything together; starts workers
    web/               public + admin Flask blueprints (+ optional auth)
  templates/           Jinja templates (base + pages)
  static/              CSS + logos (all self-hosted; no CDNs)
  tests/               pytest suite
  config.example.toml  copy to config.toml to override settings
  launcher.sh          git pull + start, run by systemd
```

## Configuration

All settings have built-in defaults. To override, copy `config.example.toml` to
`config.toml` and edit it, or set `DEPOT_*` environment variables (env wins over
the file). Common knobs:

| Setting | Default | Notes |
|---|---|---|
| `[server] port` | `80` | HTTP port |
| `[admin] password` | *(unset)* | Blank = System page open; set to require login |
| `[cache] verify_ssl` | `false` | Many FRC mirrors have broken certs |

## Development

Run it on a laptop:

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
DEPOT_PORT=8080 .venv/bin/python -m depot
# open http://localhost:8080
```

Run the tests:

```bash
.venv/bin/pip install pytest
.venv/bin/python -m pytest
```

## Install on the Raspberry Pi

 1. SSH into the box (user `depot`).
 2. Clone and set up:
    ```bash
    sudo apt-get update && sudo apt install -y git python3-venv
    git clone git@github.com:JamesCerar/depot.git
    cd depot
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip
    pip install -r requirements.txt
    deactivate
    chmod +x launcher.sh
    ```
 3. (Optional) set an admin password:
    ```bash
    cp config.example.toml config.toml
    nano config.toml   # uncomment and set [admin] password
    ```
 4. Create the service `sudo nano /etc/systemd/system/depot.service`:
    ```ini
    [Unit]
    Description=Depot file cache
    After=network.target

    [Service]
    User=root
    Group=root
    WorkingDirectory=/home/depot/depot
    ExecStart=/bin/bash /home/depot/depot/launcher.sh
    Restart=always
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
    ```
 5. Enable and start:
    ```bash
    sudo systemctl enable depot.service
    sudo systemctl start depot.service
    sudo chown -R depot:depot /home/depot/depot
    ```
