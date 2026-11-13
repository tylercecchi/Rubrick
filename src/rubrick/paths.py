"""Runtime data home — where Rubrick reads/writes its systems, learning store, and caches.

The engine is an installed package, so it must NOT assume its code lives next to its data.
The data home is, in order:

  1. $RUBRICK_HOME, when set (how an MCP client or a script pins it);
  2. the folder chosen in the app's setup, saved in ~/.rubrick/config.json;
  3. the current folder, when it already holds Rubrick data (systems/ or learned.json) —
     older setups and running from the repo keep working unchanged;
  4. ~/Rubrick.

Secrets (`.env.local`), `systems/`, `learned.json`, and `.cache/` resolve under it. Many modules
fix their cache paths at import, so a change of home takes effect on the next start (the app
restarts itself when the folder is changed in setup).
"""

from __future__ import annotations

import json
import os
import pathlib

DEFAULT_HOME = pathlib.Path("~/Rubrick").expanduser()


def config_dir() -> pathlib.Path:
    """Rubrick's own settings and tools (not product data): ~/.rubrick, or $RUBRICK_CONFIG_DIR."""
    d = pathlib.Path(os.environ.get("RUBRICK_CONFIG_DIR", "~/.rubrick")).expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def config() -> dict:
    f = config_dir() / "config.json"
    try:
        return json.loads(f.read_text()) if f.exists() else {}
    except (OSError, ValueError):
        return {}


def save_config(**values) -> dict:
    c = {**config(), **values}
    (config_dir() / "config.json").write_text(json.dumps(c, indent=2))
    return c


def _has_data(d: pathlib.Path) -> bool:
    return (d / "learned.json").exists() or any((d / "systems").glob("*.json"))


def home_source() -> str:
    """Which rule chose the data home: env, config, folder, or default."""
    if os.environ.get("RUBRICK_HOME"):
        return "env"
    if config().get("home"):
        return "config"
    return "folder" if _has_data(pathlib.Path.cwd()) else "default"


def home() -> pathlib.Path:
    """The data root (see the module doc for the order)."""
    src = home_source()
    if src == "env":
        return pathlib.Path(os.environ["RUBRICK_HOME"]).expanduser()
    if src == "config":
        return pathlib.Path(config()["home"]).expanduser()
    if src == "folder":
        return pathlib.Path.cwd()
    DEFAULT_HOME.mkdir(parents=True, exist_ok=True)
    return DEFAULT_HOME


def cache_dir() -> pathlib.Path:
    """Regenerable LLM-extraction caches (gitignored)."""
    d = home() / ".cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def systems_dir() -> pathlib.Path:
    """Compiled product systems live here (created on demand)."""
    d = home() / "systems"
    d.mkdir(parents=True, exist_ok=True)
    return d
