"""Runtime data home — where Rubrick reads/writes its systems, learning store, and caches.

The engine is an installed package now, so it must NOT assume its code lives next to its data.
The data home is `RUBRICK_HOME` if set, else the current working directory. Secrets (`.env.local`),
`systems/`, `learned.json`, and `.cache/` all resolve under it. For local dev you run from the repo
root, so the default (cwd) keeps everything where it has always been; for an installed server, set
`RUBRICK_HOME` to the directory that holds your systems.
"""

from __future__ import annotations

import os
import pathlib


def home() -> pathlib.Path:
    """The data root: $RUBRICK_HOME, or the current working directory."""
    h = os.environ.get("RUBRICK_HOME")
    return pathlib.Path(h).expanduser() if h else pathlib.Path.cwd()


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
