"""
gradio_app.py — Incident Response Env · Main Entry Point
Run: python -m server.gradio_app
Reads: benchmark.json (auto-created by benchmark_runner.py)
"""
from __future__ import annotations

import os
import sys


# Ensure both direct execution and module execution can resolve sibling imports.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_server_dir = os.path.dirname(os.path.abspath(__file__))
for _path in (_root, _server_dir):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from dashboard_impl import create_dashboard


def main() -> None:
    port = int(os.getenv("DASHBOARD_PORT", "7861"))
    demo = create_dashboard()
    demo.launch(server_port=port, share=False, show_error=True)


if __name__ == "__main__":
    main()
