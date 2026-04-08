"""
gradio_app.py — Incident Response Env · Main Entry Point
Run: python server/gradio_app.py
Reads: benchmark.json (auto-created by benchmark_runner.py)
"""
import sys
import os

# Ensure root project dir is importable (for environment, benchmark_runner, models)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Ensure server dir is importable (for dashboard_impl)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dashboard_impl import create_dashboard  # absolute import, no dot

if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", "7861"))
    demo = create_dashboard()
    demo.launch(server_port=port, share=False, show_error=True)
