"""`rubrick` — command-line entry point.

    rubrick ui [--port 7317] [--no-browser]   open the local app (review and toggle systems)
    rubrick mcp                               run the MCP server (same as `rubrick-mcp`)

Data lives in $RUBRICK_HOME, the folder chosen in the app's setup, the current folder if it
already holds Rubrick data, or ~/Rubrick.
"""

from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="rubrick", description="Rubrick product systems")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ui = sub.add_parser("ui", help="open the local app for reviewing and toggling product systems")
    ui.add_argument("--port", type=int, default=7317)
    ui.add_argument("--no-browser", action="store_true", help="don't open a browser tab")
    sub.add_parser("mcp", help="run the MCP server for coding agents")
    a = ap.parse_args(argv)
    if a.cmd == "ui":
        from rubrick.ui.server import serve
        serve(port=a.port, open_browser=not a.no_browser)
    elif a.cmd == "mcp":
        from rubrick.rubrick_mcp import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()
