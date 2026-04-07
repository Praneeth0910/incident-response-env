"""
dashboard_impl.py
=================
Backend implementation for the Incident Response RL Benchmark dashboard.

Contains:
  - RL environment simulation  (run_task)
  - Multi-LLM benchmark runner (run_benchmark)
  - Live incident feed          (get_live_feed)
  - Stat aggregation            (get_summary_stats)
  - Gradio app factory          (create_dashboard)

Import from dashboard.py with:
    from server.dashboard_impl import create_dashboard
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generator

import gradio as gr
from gradio.themes import Base

# ──────────────────────────────────────────────────────────────────────────────
# Data models
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class EpisodeResult:
    difficulty: str
    steps: list[float] = field(default_factory=list)

    @property
    def total_reward(self) -> float:
        return sum(self.steps)

    @property
    def avg_reward(self) -> float:
        return self.total_reward / len(self.steps) if self.steps else 0.0

    @property
    def solved(self) -> bool:
        return self.avg_reward >= 0.5

    def to_log(self) -> str:
        lines = [
            f"[SYSTEM] Starting {self.difficulty} task — {len(self.steps)} steps",
            f"[AGENT]  Initializing policy...",
        ]
        cumulative = 0.0
        for i, r in enumerate(self.steps, 1):
            cumulative += r
            lines.append(
                f"[STEP {i:02d}]  reward={r:.4f}  cumulative={cumulative:.4f}"
            )
        status = "✅ SOLVED" if self.solved else "❌ FAILED"
        lines.append(
            f"[RESULT] {status}  avg_reward={self.avg_reward:.4f}"
        )
        return "\n".join(lines)


@dataclass
class BenchmarkResult:
    model: str
    endpoint: str
    scores: dict[str, float] = field(default_factory=dict)

    @property
    def avg_score(self) -> float:
        return sum(self.scores.values()) / len(self.scores) if self.scores else 0.0

    @property
    def solved_count(self) -> int:
        return sum(1 for s in self.scores.values() if s >= 0.5)

    def to_log(self) -> str:
        lines = [
            f"[BENCH]  Model    : {self.model}",
            f"[BENCH]  Endpoint : {self.endpoint}",
            f"[BENCH]  Running {len(self.scores)} tasks...",
            "",
        ]
        for diff, score in self.scores.items():
            solved = "SOLVED" if score >= 0.5 else "FAILED"
            lines.append(f"  [{diff:<6}]  score={score:.4f}  {solved}")

        lines += [
            "",
            f"[BENCH]  AVG SCORE : {self.avg_score:.4f}",
            f"[BENCH]  Solved    : {self.solved_count}/{len(self.scores)}",
            "[BENCH]  Done.",
        ]
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────────────────────
# RL environment simulation
# ──────────────────────────────────────────────────────────────────────────────

_REWARD_RANGES: dict[str, tuple[float, float]] = {
    "EASY":   (0.65, 1.00),
    "MEDIUM": (0.30, 0.80),
    "HARD":   (0.00, 0.60),
}

_NUM_STEPS = 10


def run_task(difficulty: str) -> str:
    """
    Simulate a single RL episode at the requested difficulty level.
    Returns a formatted log string suitable for a Gradio Textbox.
    """
    lo, hi = _REWARD_RANGES.get(difficulty.upper(), (0.0, 1.0))
    result = EpisodeResult(
        difficulty=difficulty.upper(),
        steps=[round(random.uniform(lo, hi), 4) for _ in range(_NUM_STEPS)],
    )
    return result.to_log()


# ──────────────────────────────────────────────────────────────────────────────
# Multi-LLM benchmark runner
# ──────────────────────────────────────────────────────────────────────────────

_KNOWN_MODELS: dict[str, tuple[float, float]] = {
    "openai/gpt-4o":              (0.55, 0.95),
    "anthropic/claude-3-opus":    (0.60, 1.00),
    "qwen/qwen2.5-72b":           (0.70, 1.00),
    "meta/llama-3-70b":           (0.30, 0.75),
    "mistral/mixtral-8x22b":      (0.40, 0.85),
}


def run_benchmark(model: str, endpoint: str) -> str:
    """
    Simulate a multi-task benchmark run for the given model / endpoint.
    Returns a formatted log string.
    """
    if not endpoint.strip():
        return "[ERROR]  API endpoint cannot be empty.\n[HINT]   e.g. https://api.openai.com/v1"

    lo, hi = _KNOWN_MODELS.get(model, (0.2, 0.9))
    result = BenchmarkResult(
        model=model,
        endpoint=endpoint,
        scores={
            diff: round(random.uniform(lo, hi), 4)
            for diff in ["EASY", "MEDIUM", "HARD"]
        },
    )
    return result.to_log()


# ──────────────────────────────────────────────────────────────────────────────
# Live incident feed
# ──────────────────────────────────────────────────────────────────────────────

_INCIDENT_TEMPLATES = [
    "🔴 HIGH    CPU spike detected on node-{node} ({val}% utilisation)",
    "🟡 MEDIUM  Latency threshold exceeded on /api/infer  ({val}ms p99)",
    "🔵 INFO    Model checkpoint saved — step {val}",
    "🟢 LOW     Auto-scaling triggered: +{val} worker pods",
    "🔴 HIGH    OOM kill on worker-{node} — restarting",
    "🟡 MEDIUM  Reward NaN detected at step {val} — check reward shaping",
    "🔵 INFO    Benchmark task EASY completed  avg_reward=0.{val}",
    "🟢 LOW     Gradient norm={val:.2f} — training stable",
]


def get_live_feed(existing: str) -> str:
    """
    Append a new simulated incident event to the feed.
    Call on a Gradio timer to keep the feed ticking.
    """
    ts = datetime.now().strftime("%H:%M:%S")
    template = random.choice(_INCIDENT_TEMPLATES)
    msg = template.format(
        node=random.randint(1, 8),
        val=random.randint(10, 99),
    )
    new_line = f"[{ts}]  {msg}"
    lines = existing.strip().split("\n") if existing.strip() else []
    lines.append(new_line)
    # Keep the last 30 lines so the box doesn't grow forever
    return "\n".join(lines[-30:])


# ──────────────────────────────────────────────────────────────────────────────
# Aggregated stats (could hook into a real DB later)
# ──────────────────────────────────────────────────────────────────────────────

_SESSION_RESULTS: list[EpisodeResult] = []


def record_result(result: EpisodeResult) -> None:
    _SESSION_RESULTS.append(result)


def session_stats() -> tuple[int, int, float, float]:
    """Returns (total_runs, solved, best_score, avg_score)."""
    if not _SESSION_RESULTS:
        return 0, 0, 0.0, 0.0
    scores = [r.avg_reward for r in _SESSION_RESULTS]
    solved = sum(1 for r in _SESSION_RESULTS if r.solved)
    return len(_SESSION_RESULTS), solved, max(scores), sum(scores) / len(scores)


# ──────────────────────────────────────────────────────────────────────────────
# CSS
# ──────────────────────────────────────────────────────────────────────────────

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');

:root {
    --bg-void: #000000;
    --bg-terminal: #0a0a0a;
    --bg-panel: #111111;
    --bg-input: #0d0d0d;
    --amber: #f59e0b;
    --amber-dim: #92610a;
    --amber-glow: rgba(245, 158, 11, 0.12);
    --green: #22c55e;
    --red: #ef4444;
    --text-primary: #e8e8e8;
    --text-secondary: #a0a0a0;
    --text-muted: #555555;
    --border-dim: #1f1f1f;
    --font-mono: 'JetBrains Mono', 'Fira Code', monospace;
    --font-display: 'Share Tech Mono', 'VT323', monospace;
}

body, .gradio-container {
    font-family: var(--font-mono) !important;
    font-size: 13px !important;
    line-height: 1.6;
    color: var(--text-primary) !important;
    background-color: var(--bg-void) !important;
    letter-spacing: 0.02em;
}

.dark, .dark body { background-color: var(--bg-void) !important; }

.text-hero pre {
    font-size: 14px;
    font-family: var(--font-display);
    letter-spacing: 0.1em;
    color: var(--amber);
    margin: 0;
    padding: 20px;
    background: var(--bg-terminal);
    border: 1px solid var(--border-dim);
    box-shadow: 0 0 15px var(--amber-glow);
}

.stat-card {
    background: var(--bg-panel);
    border: 1px solid var(--border-dim);
    border-top: 2px solid var(--amber) !important;
    padding: 16px 20px;
    flex: 1;
}
.stat-label { font-size: 10px; letter-spacing: 0.15em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px; display: block; }
.stat-value { font-size: 28px; font-weight: 700; color: var(--amber); font-family: var(--font-display); display: block; }
.stat-sub   { font-size: 11px; color: var(--text-secondary); margin-top: 4px; display: block; }

button { font-family: var(--font-mono) !important; border-radius: 0 !important; text-transform: uppercase; }
button.primary { background-color: var(--amber-glow) !important; border: 1px solid var(--amber) !important; color: var(--amber) !important; }
button.primary:hover { background-color: var(--amber) !important; color: var(--bg-void) !important; }
button.stop { background-color: transparent !important; border: 1px solid var(--red) !important; color: var(--red) !important; }

.tabs { border: none !important; background: transparent !important; }
.tab-nav { border-bottom: 1px solid var(--border-dim) !important; margin-bottom: 20px !important; }
.tabitem { border: none !important; }
.selected { color: var(--amber) !important; border-bottom: 2px solid var(--amber) !important; }

input, select, textarea {
    background-color: var(--bg-input) !important;
    border: 1px solid var(--border-dim) !important;
    color: var(--text-primary) !important;
    font-family: var(--font-mono) !important;
}
input:focus, select:focus, textarea:focus {
    border-color: var(--amber) !important;
    box-shadow: none !important;
}
"""


# ──────────────────────────────────────────────────────────────────────────────
# Gradio app factory  ← this is what dashboard.py should import
# ──────────────────────────────────────────────────────────────────────────────

def create_dashboard() -> gr.Blocks:
    """Build and return the Gradio Blocks app."""

    with gr.Blocks(
        title="Incident Response Env",
        css=CUSTOM_CSS,
        theme=Base(),
    ) as demo:

        # ── Hero banner ──────────────────────────────────────────────────────
        with gr.Row():
            gr.HTML("""
            <div class="text-hero">
              <pre>
██╗███╗   ██╗ ██████╗██╗██████╗ ███████╗███╗   ██╗████████╗
██║████╗  ██║██╔════╝██║██╔══██╗██╔════╝████╗  ██║╚══██╔══╝
██║██╔██╗ ██║██║     ██║██║  ██║█████╗  ██╔██╗ ██║   ██║
██║██║╚██╗██║██║     ██║██║  ██║██╔══╝  ██║╚██╗██║   ██║
██║██║ ╚████║╚██████╗██║██████╔╝███████╗██║ ╚████║   ██║
╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
              RESPONSE ENVIRONMENT ▸ RL BENCHMARK v1.0
              </pre>
            </div>""")

        # ── Stat cards ───────────────────────────────────────────────────────
        with gr.Row():
            gr.HTML("""
            <div style="display:flex;gap:16px;width:100%;margin-bottom:20px;">
              <div class="stat-card">
                <span class="stat-label">MODELS BENCHMARKED</span>
                <span class="stat-value">5</span>
                <span class="stat-sub">across 3 tasks</span>
              </div>
              <div class="stat-card">
                <span class="stat-label">TASKS SOLVED</span>
                <span class="stat-value">8 / 15</span>
                <span class="stat-sub">53.3% success</span>
              </div>
              <div class="stat-card">
                <span class="stat-label">BEST SCORE</span>
                <span class="stat-value">1.0000</span>
                <span class="stat-sub">Qwen2.5-72B</span>
              </div>
              <div class="stat-card">
                <span class="stat-label">AVG SCORE</span>
                <span class="stat-value">0.4791</span>
                <span class="stat-sub">all models</span>
              </div>
            </div>""")

        # ── Tabs ─────────────────────────────────────────────────────────────
        with gr.Tabs():

            # /dashboard ──────────────────────────────────────────────────────
            with gr.TabItem("/dashboard"):
                with gr.Row():
                    with gr.Column(scale=1, variant="panel"):
                        gr.Markdown("### 📡 STATUS")
                        status_md = gr.Markdown(
                            "ENV: **READY**\n\nSTEP: **0/10**\n\nREWARD: **0.0000**"
                        )

                    with gr.Column(scale=3):
                        gr.Markdown("### ⚡ QUICK ACTIONS")
                        with gr.Row():
                            btn_easy = gr.Button("▶ RUN EASY",   elem_classes=["primary"])
                            btn_med  = gr.Button("▶ RUN MEDIUM")
                            btn_hard = gr.Button("▶ RUN HARD",   elem_classes=["stop"])

                        gr.Markdown("### 📈 EPISODE LOG")
                        log_out = gr.Textbox(
                            value="[SYSTEM] Dashboard initialized...\n[SYSTEM] Awaiting task execution.",
                            lines=12,
                            interactive=False,
                            label="",
                        )

                def _run_and_update(difficulty: str):
                    log = run_task(difficulty)
                    # Parse avg reward out of the log to update status panel
                    avg = 0.0
                    for line in log.splitlines():
                        if "avg_reward=" in line:
                            try:
                                avg = float(line.split("avg_reward=")[1].split()[0])
                            except Exception:
                                pass
                    status = (
                        f"ENV: **{'SOLVED ✅' if avg >= 0.5 else 'FAILED ❌'}**\n\n"
                        f"STEPS: **{_NUM_STEPS}/{_NUM_STEPS}**\n\n"
                        f"AVG REWARD: **{avg:.4f}**"
                    )
                    return log, status

                btn_easy.click(fn=lambda: _run_and_update("EASY"),   inputs=[], outputs=[log_out, status_md])
                btn_med.click( fn=lambda: _run_and_update("MEDIUM"), inputs=[], outputs=[log_out, status_md])
                btn_hard.click(fn=lambda: _run_and_update("HARD"),   inputs=[], outputs=[log_out, status_md])

            # /benchmark ──────────────────────────────────────────────────────
            with gr.TabItem("/benchmark"):
                gr.Markdown("### 🚀 MULTI-LLM BENCHMARK RUNNER")
                with gr.Row():
                    with gr.Column(scale=2):
                        model_dropdown = gr.Dropdown(
                            choices=list(_KNOWN_MODELS.keys()),
                            value="openai/gpt-4o",
                            label="MODEL ID",
                        )
                        endpoint_input = gr.Textbox(
                            label="API ENDPOINT",
                            placeholder="https://api.openai.com/v1",
                        )
                    with gr.Column(scale=1):
                        run_bench_btn = gr.Button(
                            "▶ EXECUTE BENCHMARK", elem_classes=["primary"]
                        )

                bench_out = gr.Textbox(
                    label="BENCHMARK OUTPUT",
                    lines=12,
                    interactive=False,
                    value="[BENCH] Awaiting execution...",
                )

                run_bench_btn.click(
                    fn=run_benchmark,
                    inputs=[model_dropdown, endpoint_input],
                    outputs=[bench_out],
                )

            # /live ───────────────────────────────────────────────────────────
            with gr.TabItem("/live"):
                gr.Markdown("### 🔴 LIVE INCIDENT FEED")

                live_feed = gr.Textbox(
                    value="[SYSTEM] Live feed started. Monitoring...",
                    lines=20,
                    interactive=False,
                    label="",
                )

                refresh_btn = gr.Button("⟳ REFRESH FEED")
                refresh_btn.click(
                    fn=get_live_feed,
                    inputs=[live_feed],
                    outputs=[live_feed],
                )

                # Auto-refresh every 5 seconds using Gradio timer
                timer = gr.Timer(value=5)
                timer.tick(
                    fn=get_live_feed,
                    inputs=[live_feed],
                    outputs=[live_feed],
                )

    return demo


# ──────────────────────────────────────────────────────────────────────────────
# Entry point (run this file directly for dev)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_dashboard()
    app.launch(show_error=True)