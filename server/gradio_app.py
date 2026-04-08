"""
gradio_app.py — Incident Response Env · Main Entry Point
Run: python -m server.gradio_app
Reads: benchmark.json (auto-created by benchmark_runner.py)
"""
import os

from dashboard_impl import create_dashboard  # absolute import, no dot

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "7861"))
    demo = create_dashboard()
    demo.launch(server_port=port, share=False, show_error=True)
