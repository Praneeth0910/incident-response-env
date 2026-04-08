"""
dashboard_impl.py
=================
Backend implementation for the Incident Response RL Benchmark dashboard.

Fixes applied vs the original:
  1. Removed import of non-existent `benchmark_runner` module — inlined helpers.
  2. Added missing `Optional` to typing imports.
  3. Fixed `_render_benchmark_status` using `Optional` in signature before import.
  4. Fixed `env.state()` call (method exists on IncidentResponseEnv).
  5. Fixed `create_dashboard` return — `build_episode_outputs` now returns the
     exact tuple the Gradio `.click()` handlers expect.
  6. Fixed `execute_action` — env.step() returns (obs, rew, done, info) tuple,
     not four separate objects to unpack into Gradio action; proper attribute access.
  7. `reset_task` now calls `env.reset()` which returns an Observation object
     (not a dict), so uses `.alert`, `.message`, `.done`, `.step`.
  8. Removed `_sync_target_choices` crash when `SERVICES` is a list (was called
     with wrong data type check).
  9. Full DESIGN.md Dark Ops Terminal CSS implemented exactly per spec.
 10. All six tabs wired: Dashboard / Benchmark / Live / Leaderboard / Logs / Help.
 11. benchmark.json load/save inlined without external dependency.
 12. Added `__all__` for clean import.
"""
from __future__ import annotations

import html
import json
import os
import pathlib
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

import gradio as gr

# ── Project imports ───────────────────────────────────────────────────────────
import sys
_root = pathlib.Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from environment import IncidentResponseEnv, TASKS, SERVICES
from models import Action

__all__ = ["create_dashboard"]

# ── Constants ─────────────────────────────────────────────────────────────────
BENCHMARK_FILE = _root / "benchmark.json"

MODEL_CHOICES = [
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "mistralai/Mixtral-8x7B-Instruct-v0.1",
]

DEFAULT_API_BASE = os.getenv("API_BASE_URL", "https://router.huggingface.co/v1")
DEFAULT_ENV_BASE = os.getenv("ENV_BASE_URL", "http://localhost:7860")

# ── Benchmark store helpers (inlined — no external module needed) ──────────────

def clamp_task_score(score: float) -> float:
    return round(max(0.001, min(0.999, float(score))), 4)


def load_benchmark_store(path: pathlib.Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except Exception:
        pass
    return {"leaderboard": [], "latest_run": None}


def save_benchmark_store(path: pathlib.Path, store: Dict[str, Any]) -> None:
    try:
        path.write_text(json.dumps(store, indent=2))
    except Exception:
        pass


def record_run(store: Dict[str, Any], model: str, task_scores: Dict[str, float],
               api_base: str, log_lines: List[str]) -> Dict[str, Any]:
    """Upsert a model result into the leaderboard (latest run per model)."""
    tasks_total = len(task_scores)
    tasks_solved = sum(1 for s in task_scores.values() if s >= 0.6)
    avg = round(sum(task_scores.values()) / tasks_total, 4) if tasks_total else 0.0

    entry = {
        "model": model,
        "task_scores": task_scores,
        "average_score": avg,
        "tasks_solved": tasks_solved,
        "tasks_total": tasks_total,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "api_base": api_base,
    }

    # upsert
    board = [e for e in store.get("leaderboard", []) if e.get("model") != model]
    board.append(entry)
    board.sort(key=lambda e: e["average_score"], reverse=True)

    store["leaderboard"] = board
    store["latest_run"] = {
        **entry,
        "log_lines": log_lines,
        "summary": {
            "average_score": avg,
            "tasks_solved": tasks_solved,
            "tasks_total": tasks_total,
        },
    }
    return store

# ── Dark Ops Terminal CSS (from DESIGN.md) ────────────────────────────────────

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');

:root {
  --bg-void:      #000000;
  --bg-terminal:  #0a0a0a;
  --bg-panel:     #111111;
  --bg-raised:    #1a1a1a;
  --bg-input:     #0d0d0d;
  --amber:        #f59e0b;
  --amber-dim:    #92610a;
  --amber-glow:   rgba(245,158,11,0.12);
  --green:        #22c55e;
  --green-dim:    #15803d;
  --red:          #ef4444;
  --red-dim:      #991b1b;
  --blue:         #3b82f6;
  --blue-dim:     #1d4ed8;
  --yellow:       #eab308;
  --yellow-dim:   #854d0e;
  --text-primary:   #e8e8e8;
  --text-secondary: #a0a0a0;
  --text-muted:     #555555;
  --text-amber:     #f59e0b;
  --text-green:     #22c55e;
  --text-red:       #ef4444;
  --border-dim:     #1f1f1f;
  --border-amber:   #92610a;
  --border-focus:   #f59e0b;
  --font-mono:    'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --font-display: 'Share Tech Mono', 'VT323', monospace;
}

/* ── Global overrides ── */
body, .gradio-container, .gradio-container * {
  font-family: var(--font-mono) !important;
}
body, .gradio-container {
  background: var(--bg-void) !important;
  color: var(--text-primary) !important;
  font-size: 13px !important;
  line-height: 1.6;
  letter-spacing: 0.02em;
}
.dark, .dark body { background: var(--bg-void) !important; }
footer { display: none !important; }

/* ── Inputs ── */
input, select, textarea, .input-wrap textarea {
  background: var(--bg-input) !important;
  border: 1px solid var(--border-dim) !important;
  color: var(--text-primary) !important;
  font-family: var(--font-mono) !important;
  border-radius: 0 !important;
}
input:focus, select:focus, textarea:focus {
  border-color: var(--amber) !important;
  box-shadow: 0 0 0 2px var(--amber-glow) !important;
}

/* ── Buttons ── */
button { font-family: var(--font-mono) !important; border-radius: 0 !important; text-transform: uppercase; letter-spacing: 0.06em; }
button.primary, .primary { background: var(--amber-glow) !important; border: 1px solid var(--amber) !important; color: var(--amber) !important; }
button.primary:hover { background: var(--amber) !important; color: var(--bg-void) !important; }
button.secondary { background: transparent !important; border: 1px solid var(--border-dim) !important; color: var(--text-secondary) !important; }
button.secondary:hover { border-color: var(--amber) !important; color: var(--amber) !important; }
button.stop { background: transparent !important; border: 1px solid var(--red) !important; color: var(--red) !important; }

/* ── Tabs ── */
.tabs, .tabitem { background: transparent !important; border: none !important; }
.tab-nav { border-bottom: 1px solid var(--border-dim) !important; background: var(--bg-void) !important; }
.tab-nav button { background: transparent !important; border: none !important; border-bottom: 2px solid transparent !important; color: var(--text-secondary) !important; padding: 10px 18px !important; font-size: 12px !important; letter-spacing: 0.08em; }
.tab-nav button:hover { color: var(--text-primary) !important; }
.tab-nav button.selected { color: var(--amber) !important; border-bottom-color: var(--amber) !important; }

/* ── Dataframe ── */
.dataframe table { background: var(--bg-panel) !important; color: var(--text-primary) !important; border-collapse: collapse; font-family: var(--font-mono) !important; font-size: 12px; width: 100%; }
.dataframe th { background: var(--bg-void) !important; color: var(--text-muted) !important; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; padding: 8px 12px !important; border-bottom: 1px solid var(--amber-dim) !important; }
.dataframe td { padding: 9px 12px !important; border-bottom: 1px solid var(--border-dim) !important; }
.dataframe tr:hover td { background: var(--bg-raised) !important; }

/* ── Markdown ── */
.prose, .markdown-body, .prose p { color: var(--text-secondary) !important; }
.prose h1,.prose h2,.prose h3 { color: var(--amber) !important; font-family: var(--font-display) !important; }
.prose code { background: var(--bg-panel) !important; color: var(--amber) !important; padding: 1px 4px; border: 1px solid var(--border-dim); }

/* ── Header bar ── */
.header-bar {
  display: flex; align-items: center; gap: 14px;
  padding: 12px 18px;
  background: var(--bg-void);
  border: 1px solid var(--border-dim);
  margin-bottom: 14px;
}
.header-logo { color: var(--amber); font-family: var(--font-display); font-size: 14px; letter-spacing: 0.12em; }
.status-badge { border: 1px solid var(--border-dim); color: var(--text-secondary); font-size: 10px; letter-spacing: 0.12em; padding: 4px 8px; text-transform: uppercase; }
.status-running { background: rgba(34,197,94,0.15); border-color: rgba(34,197,94,0.35); color: var(--green); }
.status-version, .status-benchmark { background: var(--bg-terminal); }

/* Blinking dot */
@keyframes blink { 50% { opacity: 0; } }
.blink { animation: blink 1s step-end infinite; }

/* ── Hero ASCII ── */
.hero-shell pre {
  margin: 0; padding: 18px 20px;
  background: var(--bg-terminal);
  border: 1px solid var(--border-dim);
  color: var(--amber);
  font-family: var(--font-display);
  font-size: 13px; letter-spacing: 0.08em;
  box-shadow: 0 0 24px var(--amber-glow);
  overflow-x: auto;
}
.hero-copy { color: var(--text-secondary); font-size: 12px; line-height: 1.9; margin-top: 10px; }

/* ── Stat cards ── */
.stats-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 12px; margin: 16px 0; }
.stat-card { background: var(--bg-panel); border: 1px solid var(--border-dim); border-top: 2px solid var(--amber); padding: 14px 16px; }
.stat-label { color: var(--text-muted); display: block; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 8px; }
.stat-value { color: var(--amber); display: block; font-family: var(--font-display); font-size: 28px; font-weight: 700; }
.stat-sub { color: var(--text-secondary); display: block; font-size: 11px; margin-top: 4px; }

/* ── Panel blocks ── */
.panel-block { background: var(--bg-panel); border: 1px solid var(--border-dim); padding: 14px 16px; }
.section-label { color: var(--text-muted); display: block; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; margin-bottom: 10px; }
.muted-copy { color: var(--text-secondary); font-size: 12px; line-height: 1.8; }

/* ── Alert banner ── */
.alert-banner {
  background: rgba(239,68,68,0.08);
  border: 1px solid rgba(239,68,68,0.35);
  border-left: 4px solid var(--red);
  color: var(--text-primary);
  padding: 14px 16px;
}
@keyframes pulse-border { 0%,100% { border-left-color: var(--red); } 50% { border-left-color: var(--red-dim); } }
.alert-banner { animation: pulse-border 2s ease-in-out infinite; }

/* ── Status / mini stat grids ── */
.status-grid { display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: 10px; margin-bottom: 12px; }
.mini-stat { background: var(--bg-panel); border: 1px solid var(--border-dim); padding: 10px 12px; }
.mini-stat span { color: var(--text-muted); display: block; font-size: 10px; letter-spacing: 0.14em; text-transform: uppercase; }
.mini-stat strong { color: var(--text-primary); font-size: 13px; }

/* ── Feedback chips ── */
.feedback-chip { display: inline-flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid var(--border-dim); font-size: 12px; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase; margin-top: 10px; }
.feedback-pos { background: rgba(34,197,94,0.10); border-color: rgba(34,197,94,0.35); color: var(--green); }
.feedback-warn { background: rgba(234,179,8,0.10); border-color: rgba(234,179,8,0.35); color: var(--yellow); }
.feedback-neg { background: rgba(239,68,68,0.10); border-color: rgba(239,68,68,0.35); color: var(--red); }

/* ── Error box ── */
.error-box { background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.35); color: #fecaca; margin-top: 12px; padding: 10px 12px; font-size: 12px; }

/* ── Score display ── */
.score-wrap { display: flex; align-items: center; gap: 14px; margin-top: 8px; }
.score-bar { color: var(--amber); font-family: var(--font-display); font-size: 16px; letter-spacing: 0.06em; }
.score-number { color: var(--text-primary); font-size: 14px; font-weight: 700; }

/* ── Step timeline ── */
.step-timeline { background: var(--bg-panel); border: 1px solid var(--border-dim); padding: 14px 16px; }
.step-item { display: flex; gap: 12px; padding: 8px 0 8px 16px; border-left: 1px solid var(--border-dim); margin-left: 8px; position: relative; }
.step-item::before { content:''; position:absolute; left:-5px; top:14px; width:8px; height:8px; border-radius:50%; background:var(--amber); }
.step-number { color: var(--text-muted); font-size: 11px; min-width: 48px; }
.step-action { color: var(--amber); font-weight: 600; }
.step-target { color: var(--text-primary); }
.step-reward { margin-left: auto; white-space: nowrap; }
.reward-pos { color: var(--green); }
.reward-neg { color: var(--red); }
.reward-zero { color: var(--text-muted); }

/* ── Service map ── */
.service-map { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-top: 10px; }
.service-node { background: var(--bg-terminal); border: 1px solid var(--border-dim); padding: 10px 12px; text-align: center; }
.service-node strong { display: block; color: var(--text-secondary); font-size: 11px; }
.service-node span { display: block; color: var(--text-muted); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; margin-top: 4px; }
.service-focus { border-color: var(--amber) !important; background: var(--amber-glow) !important; }
.service-focus strong { color: var(--amber) !important; }
.service-scanned { border-color: var(--border-amber); }
.service-scanned strong { color: var(--text-primary); }
.service-rca { border-color: var(--green-dim) !important; background: rgba(34,197,94,0.08) !important; }
.service-rca strong { color: var(--green) !important; }

/* ── Benchmark table ── */
.benchmark-table table { width: 100%; border-collapse: collapse; font-family: var(--font-mono); font-size: 13px; }
.benchmark-table th { font-size: 10px; letter-spacing: 0.15em; color: var(--text-muted); text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--amber-dim); }
.benchmark-table td { padding: 10px 12px; border-bottom: 1px solid var(--border-dim); color: var(--text-primary); }
.benchmark-table tr:hover td { background: var(--bg-raised); }
.score-high { color: var(--green); }
.score-med  { color: var(--yellow); }
.score-low  { color: var(--red); }

/* ── Summary grid ── */
.summary-grid { display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 10px; margin: 10px 0; }
.summary-card { background: var(--bg-terminal); border: 1px solid var(--border-dim); padding: 10px 12px; }
.summary-card span { color: var(--text-muted); font-size: 10px; letter-spacing: 0.12em; text-transform: uppercase; display: block; }
.summary-card strong { color: var(--text-primary); font-size: 13px; }

/* ── Podium ── */
.podium-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; margin-top: 12px; }
.podium-card { background: var(--bg-panel); border: 1px solid var(--border-dim); border-top: 2px solid var(--amber-dim); padding: 16px; text-align: center; }
.podium-rank { display: block; font-size: 10px; letter-spacing: 0.14em; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px; }
.podium-model { display: block; font-size: 12px; color: var(--text-primary); margin-bottom: 6px; word-break: break-all; }
.podium-score { display: block; font-size: 24px; font-family: var(--font-display); color: var(--amber); }

/* ── Log viewer ── */
.log-viewer { font-family: var(--font-mono); font-size: 12px; line-height: 1.9; padding: 16px; background: var(--bg-terminal); border: 1px solid var(--border-dim); }
.log-start { color: var(--blue); }
.log-step  { color: var(--text-primary); }
.log-end   { color: var(--amber); }
.log-debug { color: var(--text-muted); }
.log-error { color: var(--red); }
.log-warn  { color: var(--yellow); }
.log-info  { color: var(--blue); }
@keyframes type-in { from { opacity:0; transform:translateX(-4px); } to { opacity:1; transform:translateX(0); } }
.log-line-new { animation: type-in 0.1s ease-out; }

/* ── Help terminal ── */
.help-terminal { background: var(--bg-terminal); border: 1px solid var(--border-dim); font-family: var(--font-mono); font-size: 13px; padding: 24px 32px; line-height: 2.1; }
.help-header { display: flex; justify-content: space-between; color: var(--text-muted); font-size: 11px; border-bottom: 1px solid var(--border-dim); padding-bottom: 8px; margin-bottom: 16px; }
.help-section-title { color: var(--text-primary); font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; margin-top: 20px; display: block; }
.help-command { color: var(--amber); display: inline-block; min-width: 200px; }
.help-desc { color: var(--text-secondary); }

/* ── Status bar (footer) ── */
.status-bar { display: flex; gap: 24px; flex-wrap: wrap; padding: 8px 20px; background: var(--bg-void); border-top: 1px solid var(--border-dim); font-size: 11px; color: var(--text-muted); margin-top: 14px; }
.status-item { display: flex; gap: 6px; }
.status-item strong { color: var(--text-primary); }
.status-item .good { color: var(--green); }
.status-item .bad  { color: var(--red); }

/* ── Scan line animation ── */
.panel { position: relative; overflow: hidden; }
.panel::after { content:''; position:absolute; top:0; left:0; right:0; height:2px; background: linear-gradient(90deg, transparent, var(--amber-glow), transparent); animation: scan 4s linear infinite; opacity:0.3; pointer-events:none; }
@keyframes scan { 0% { top:0; } 100% { top:100%; } }
"""

# ── State helpers ─────────────────────────────────────────────────────────────

def _fresh_ui_state(task_id: str = "task_easy") -> Dict[str, Any]:
    return {
        "task_id": task_id,
        "alert": "",
        "history": [],
        "last_message": "Reset a task to begin a guided incident run.",
        "last_reward": 0.0,
        "last_reason": "no signal",
        "done": False,
        "step": 0,
        "score": 0.001,
        "status": "READY",
        "error": "",
        "terminal_log": [
            "[SYSTEM] Dashboard ready.",
            f"[SYSTEM] Benchmark store: {BENCHMARK_FILE}",
        ],
    }


def _append_terminal(state: Dict[str, Any], line: str) -> None:
    state["terminal_log"].append(line)
    state["terminal_log"] = state["terminal_log"][-120:]


def _feedback_meta(reward: float) -> Tuple[str, str, str]:
    if reward > 0.02:
        return "POSITIVE", "feedback-pos", "&#10003;"
    if reward < 0:
        return "NEGATIVE", "feedback-neg", "&#10007;"
    return "CAUTION", "feedback-warn", "&#9888;"


def _ascii_bar(score: float, width: int = 24) -> str:
    score = clamp_task_score(score)
    filled = max(0, min(width, int(round(score * width))))
    return f"[{'#' * filled}{'.' * (width - filled)}]"


def _timestamp_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ── HTML renderers ────────────────────────────────────────────────────────────

def _render_header_bar() -> str:
    return """
<div class="header-bar">
  <span class="header-logo">&#9654; INCIDENT-RESPONSE-ENV</span>
  <span class="status-badge status-running"><span class="blink">&#9679;</span> RUNNING</span>
  <span class="status-badge status-version">v1.0.0</span>
  <span class="status-badge status-benchmark">BENCHMARK MODE</span>
</div>"""


def _render_footer_bar(state: Dict[str, Any]) -> str:
    task_meta = TASKS.get(state["task_id"], TASKS["task_easy"])
    return f"""
<div class="status-bar">
  <span class="status-item">ENV: <strong>{html.escape(state['status'])}</strong></span>
  <span class="status-item">TASK: <strong>{html.escape(task_meta['difficulty'].upper())}</strong></span>
  <span class="status-item">STEP: <strong>{state['step']} / {task_meta['max_steps']}</strong></span>
  <span class="status-item">REWARD: <strong class="{'good' if state['last_reward'] > 0 else 'bad' if state['last_reward'] < 0 else ''}">{state['last_reward']:+.4f}</strong></span>
  <span class="status-item">SCORE: <strong>{clamp_task_score(state['score']):.4f}</strong></span>
  <span class="status-item">TIME: <strong>{_timestamp_text()}</strong></span>
</div>"""


def _render_stats_cards(store: Dict[str, Any]) -> str:
    leaderboard = store.get("leaderboard", [])
    model_count = len(leaderboard)
    solved = sum(item.get("tasks_solved", 0) for item in leaderboard)
    total_tasks = sum(item.get("tasks_total", 0) for item in leaderboard)
    average_score = (
        sum(item.get("average_score", 0.0) for item in leaderboard) / model_count
        if model_count else 0.0
    )
    best = leaderboard[0] if leaderboard else None
    solved_text = f"{solved} / {total_tasks}" if total_tasks else "0 / 0"
    solved_sub = f"{(solved / total_tasks) * 100:.1f}% success" if total_tasks else "No model runs yet"
    best_value = f"{best['average_score']:.4f}" if best else "--"
    best_sub = best["model"] if best else "Waiting for benchmark.json"
    return f"""
<div class="stats-grid">
  <div class="stat-card"><span class="stat-label">Models Benchmarked</span><span class="stat-value">{model_count}</span><span class="stat-sub">latest run per model</span></div>
  <div class="stat-card"><span class="stat-label">Tasks Solved</span><span class="stat-value">{solved_text}</span><span class="stat-sub">{solved_sub}</span></div>
  <div class="stat-card"><span class="stat-label">Best Average</span><span class="stat-value">{best_value}</span><span class="stat-sub">{html.escape(best_sub)}</span></div>
  <div class="stat-card"><span class="stat-label">Average Score</span><span class="stat-value">{average_score:.4f}</span><span class="stat-sub">across latest model runs</span></div>
</div>"""


def _render_alert(alert: str) -> str:
    if not alert:
        return (
            '<div class="panel-block"><span class="section-label">Incident Alert</span>'
            '<div class="muted-copy">No active incident. Reset a task to start a run.</div></div>'
        )
    return (
        '<div class="alert-banner"><span class="section-label">&#9888; Incident Alert</span>'
        f"<div style='margin-top:8px;font-size:13px;'>{html.escape(alert)}</div></div>"
    )


def _render_status_panel(state: Dict[str, Any]) -> str:
    task_meta = TASKS.get(state["task_id"], TASKS["task_easy"])
    feedback_label, feedback_class, icon = _feedback_meta(state["last_reward"])
    error_block = (
        f'<div class="error-box">{html.escape(str(state["error"]))}</div>'
        if state.get("error") else ""
    )
    return f"""
<div class="panel-block">
  <span class="section-label">Run Status</span>
  <div class="status-grid">
    <div class="mini-stat"><span>Task</span><strong>{html.escape(task_meta['name'])}</strong></div>
    <div class="mini-stat"><span>Step</span><strong>{state['step']} / {task_meta['max_steps']}</strong></div>
    <div class="mini-stat"><span>Reward</span><strong>{state['last_reward']:+.4f}</strong></div>
    <div class="mini-stat"><span>Status</span><strong>{html.escape(state['status'])}</strong></div>
  </div>
  <div class="feedback-chip {feedback_class}"><span>{icon}</span><span>{feedback_label}</span></div>
  <div class="muted-copy" style="margin-top:8px;"><strong>Reason:</strong> {html.escape(state['last_reason'])}</div>
  {error_block}
</div>"""


def _render_score_panel(score: float, label: str) -> str:
    safe = clamp_task_score(score)
    return f"""
<div class="panel-block">
  <span class="section-label">{html.escape(label)}</span>
  <div class="score-wrap">
    <span class="score-bar">{_ascii_bar(safe)}</span>
    <span class="score-number">{safe:.4f}</span>
  </div>
</div>"""


def _render_episode_timeline(state: Dict[str, Any]) -> str:
    if not state["history"]:
        return """
<div class="step-timeline">
  <span class="section-label">Step Timeline</span>
  <div class="muted-copy">No steps yet. Reset a task and start investigating.</div>
</div>"""
    items = ['<div class="step-timeline"><span class="section-label">Step Timeline</span>']
    for item in state["history"]:
        rew = item["reward"]
        reward_class = "reward-pos" if rew > 0.02 else "reward-neg" if rew < 0 else "reward-zero"
        items.append(f"""
<div class="step-item">
  <span class="step-number">STEP {item['step']:02d}</span>
  <div style="flex:1;">
    <span class="step-action">{html.escape(item['action'])}</span>
    <span class="step-target"> → {html.escape(item['target'])}</span>
    <div class="muted-copy" style="font-size:11px;margin-top:3px;">{html.escape(item['reason'])}</div>
  </div>
  <span class="step-reward {reward_class}">{rew:+.4f}</span>
</div>""")
    items.append("</div>")
    return "".join(items)


def _render_service_map(state: Dict[str, Any]) -> str:
    touched = {item["target"] for item in state["history"] if item.get("target") in SERVICES}
    focused = state["history"][-1]["target"] if state["history"] else None
    rca_target = None
    if state["done"]:
        for item in reversed(state["history"]):
            if item["action"] == "declare_rca" and item["target"] in SERVICES:
                rca_target = item["target"]
                break

    nodes = ['<div class="panel-block"><span class="section-label">Service Map</span><div class="service-map">']
    for service in SERVICES:
        label, node_class = "IDLE", "service-node"
        if service == rca_target and state["last_reward"] > 0:
            label, node_class = "RCA ✓", "service-node service-rca"
        elif service == focused:
            label, node_class = "FOCUS", "service-node service-focus"
        elif service in touched:
            label, node_class = "SCANNED", "service-node service-scanned"
        nodes.append(f'<div class="{node_class}"><strong>{html.escape(service)}</strong><span>{label}</span></div>')
    nodes.append("</div></div>")
    return "".join(nodes)


def _history_rows(state: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for item in state["history"]:
        rows.append([
            item["step"], item["feedback"], f"{item['reward']:+.4f}",
            item["action"], item["target"], item["reason"],
            "yes" if item["done"] else "no",
        ])
    return rows or [[0, "IDLE", "+0.0000", "-", "-", "No actions recorded yet.", "no"]]


def _benchmark_rows(store: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for idx, item in enumerate(store.get("leaderboard", []), start=1):
        ts = item.get("task_scores", {})
        rows.append([
            idx, item.get("model", "unknown"),
            f"{ts.get('task_easy', 0.001):.4f}",
            f"{ts.get('task_medium', 0.001):.4f}",
            f"{ts.get('task_hard', 0.001):.4f}",
            f"{item.get('average_score', 0.001):.4f}",
            f"{item.get('tasks_solved', 0)} / {item.get('tasks_total', len(TASKS))}",
            item.get("timestamp", ""),
        ])
    return rows


def _render_benchmark_status(report: Optional[Dict[str, Any]] = None, error: str = "") -> str:
    if error:
        return f"""<div class="panel-block"><span class="section-label">Benchmark Status</span>
<div class="feedback-chip feedback-neg"><span>&#10007;</span><span>Run Failed</span></div>
<div class="error-box">{html.escape(error)}</div></div>"""
    if not report:
        return """<div class="panel-block"><span class="section-label">Benchmark Status</span>
<div class="muted-copy">No benchmark run recorded yet. Run a model here or call <code>python inference.py</code>.</div></div>"""
    summary = report.get("summary", {})
    return f"""<div class="panel-block"><span class="section-label">Benchmark Status</span>
<div class="feedback-chip feedback-pos"><span>&#10003;</span><span>Benchmark Complete</span></div>
<div class="muted-copy" style="margin-top:10px;">
  <strong>Model:</strong> {html.escape(report.get('model', 'unknown'))}<br>
  <strong>Average Score:</strong> {summary.get('average_score', 0.001):.4f}<br>
  <strong>Solved:</strong> {summary.get('tasks_solved', 0)} / {summary.get('tasks_total', len(TASKS))}<br>
  <strong>File:</strong> {html.escape(str(BENCHMARK_FILE))}
</div></div>"""


def _render_benchmark_summary(report: Optional[Dict[str, Any]]) -> str:
    if not report:
        return """<div class="panel-block"><span class="section-label">Latest Benchmark</span>
<div class="muted-copy">benchmark.json will appear after the first model run.</div></div>"""
    summary = report.get("summary", {})
    return f"""<div class="panel-block"><span class="section-label">Latest Benchmark Summary</span>
<div class="summary-grid">
  <div class="summary-card"><span>Model</span><strong>{html.escape(report.get('model','unknown'))}</strong></div>
  <div class="summary-card"><span>Avg Score</span><strong>{summary.get('average_score',0.001):.4f}</strong></div>
  <div class="summary-card"><span>Solved</span><strong>{summary.get('tasks_solved',0)} / {summary.get('tasks_total',len(TASKS))}</strong></div>
</div>
<div class="muted-copy"><strong>Timestamp:</strong> {html.escape(report.get('timestamp',''))}</div></div>"""


def _render_podium(store: Dict[str, Any]) -> str:
    leaderboard = store.get("leaderboard", [])[:3]
    if not leaderboard:
        return """<div class="panel-block"><span class="section-label">Hall of Champions</span>
<div class="muted-copy">Run a benchmark to populate the leaderboard podium.</div></div>"""
    labels = ["#1 Champion", "#2 Contender", "#3 Contender"]
    cards = ['<div class="panel-block"><span class="section-label">Hall of Champions</span><div class="podium-grid">']
    for i in range(3):
        item = leaderboard[i] if i < len(leaderboard) else None
        if item is None:
            cards.append(f'<div class="podium-card"><span class="podium-rank">{labels[i]}</span><span class="podium-model">--</span><span class="podium-score">----</span></div>')
        else:
            cards.append(f"""<div class="podium-card">
  <span class="podium-rank">{labels[i]}</span>
  <span class="podium-model">{html.escape(item['model'])}</span>
  <span class="podium-score">{item['average_score']:.4f}</span>
</div>""")
    cards.append("</div></div>")
    return "".join(cards)


def _render_help_terminal() -> str:
    return """
<div class="help-terminal">
  <div class="help-header">
    <span>INCIDENT-RESPONSE-ENV(1)</span>
    <span>USER COMMANDS</span>
    <span>VERSION 1.0.0</span>
  </div>
  <span class="help-section-title">NAME</span>
  <div><span class="help-command">  incident-response-env</span><span class="help-desc">RL benchmark for LLM incident response</span></div>
  <span class="help-section-title">SECTIONS</span>
  <div><span class="help-command">  /dashboard</span><span class="help-desc">Mission control — manual episode runner</span></div>
  <div><span class="help-command">  /benchmark</span><span class="help-desc">Run multi-model benchmarks, persist benchmark.json</span></div>
  <div><span class="help-command">  /live</span><span class="help-desc">Step timeline, rewards, service focus map</span></div>
  <div><span class="help-command">  /leaderboard</span><span class="help-desc">Top model rankings, podium</span></div>
  <div><span class="help-command">  /logs</span><span class="help-desc">Raw log stream from last benchmark</span></div>
  <div><span class="help-command">  /help</span><span class="help-desc">This page</span></div>
  <span class="help-section-title">ACTIONS</span>
  <div><span class="help-command">  check_health</span><span class="help-desc">UP / DEGRADED / DOWN status</span></div>
  <div><span class="help-command">  check_metrics</span><span class="help-desc">Latency, error rate, CPU, memory</span></div>
  <div><span class="help-command">  read_logs</span><span class="help-desc">Recent log lines from service</span></div>
  <div><span class="help-command">  run_db_query</span><span class="help-desc">Diagnostic SQL — target: postgres-db</span></div>
  <div><span class="help-command">  restart_service</span><span class="help-desc">Restart (penalised if wrong service)</span></div>
  <div><span class="help-command">  rollback_deployment</span><span class="help-desc">Rollback (penalised if wrong service)</span></div>
  <div><span class="help-command">  declare_rca</span><span class="help-desc">Declare root cause — ends episode</span></div>
  <span class="help-section-title">SCORING</span>
  <div><span class="help-command">  Pass threshold</span><span class="help-desc">&ge; 0.6</span></div>
  <div><span class="help-command">  Evidence</span><span class="help-desc">+0.05 to +0.12 per relevant find</span></div>
  <div><span class="help-command">  Correct fix</span><span class="help-desc">+0.30</span></div>
  <div><span class="help-command">  Correct RCA</span><span class="help-desc">+0.50 + time bonus</span></div>
  <div><span class="help-command">  Redundant</span><span class="help-desc">&minus;0.05</span></div>
  <span class="help-section-title">ENDPOINTS</span>
  <div><span class="help-command">  POST /reset</span><span class="help-desc">{"task_id": "task_easy", "seed": 42}</span></div>
  <div><span class="help-command">  POST /step</span><span class="help-desc">{"action_type": "check_health", "target": "api-gateway"}</span></div>
  <div><span class="help-command">  GET  /state</span><span class="help-desc">Ground truth debug state</span></div>
  <div><span class="help-command">  GET  /grade</span><span class="help-desc">{"score": 0.xxxx}</span></div>
  <div><span class="help-command">  GET  /tasks</span><span class="help-desc">List all tasks</span></div>
</div>"""


def _filter_log_text(store: Dict[str, Any], level: str = "ALL", query: str = "") -> str:
    latest_run = store.get("latest_run") or {}
    lines = list(latest_run.get("log_lines", []))
    if level != "ALL":
        marker = f"[{level}]"
        lines = [l for l in lines if marker in l]
    if query:
        low = query.lower()
        lines = [l for l in lines if low in l.lower()]
    return "\n".join(lines) if lines else "[LOG] No matching lines found."

# ── Episode output builder ────────────────────────────────────────────────────
# Returns exactly the outputs wired to Gradio .click():
#   state, status_panel, alert_html, timeline_html, history_df_rows,
#   score_panel, service_map, footer_bar

def _build_episode_outputs(env: IncidentResponseEnv, state: Dict[str, Any]) -> Tuple:
    return (
        state,
        _render_status_panel(state),
        _render_alert(state["alert"]),
        _render_episode_timeline(state),
        _history_rows(state),
        _render_score_panel(state["score"], "Live Score"),
        _render_service_map(state),
        _render_footer_bar(state),
    )

# ── Dashboard factory ─────────────────────────────────────────────────────────

def create_dashboard(env_instance: Optional[IncidentResponseEnv] = None) -> gr.Blocks:
    env = env_instance or IncidentResponseEnv()
    initial_store = load_benchmark_store(BENCHMARK_FILE)
    initial_state = _fresh_ui_state()

    # ── Event handlers ────────────────────────────────────────────────────────

    def reset_task(task_id: str, current_state: Dict[str, Any]):
        state = _fresh_ui_state(task_id)
        try:
            obs = env.reset(task_id=task_id)
            state.update({
                "alert": obs.alert,
                "last_message": obs.message,
                "last_reason": "Environment reset. Pick an action to investigate.",
                "done": obs.done,
                "step": obs.step,
                "score": 0.001,
                "status": "ACTIVE",
            })
            _append_terminal(state, f"[RESET] task={task_id}")
            _append_terminal(state, f"[ALERT] {obs.alert}")
        except Exception as exc:
            state["status"] = "ERROR"
            state["error"] = f"Could not reset environment: {exc}"
            _append_terminal(state, f"[ERROR] {state['error']}")
        return _build_episode_outputs(env, state)

    def execute_action(task_id: str, action_type: str, target: str, current_state: Dict[str, Any]):
        state = dict(current_state)
        state["task_id"] = task_id
        state["error"] = ""
        try:
            action = Action(action_type=action_type, target=target)
            obs, reward, done, info = env.step(action)

            state["alert"] = obs.alert
            state["last_message"] = obs.message
            state["last_reward"] = float(reward.value)
            state["last_reason"] = reward.reason
            state["done"] = done
            state["step"] = obs.step
            state["score"] = (
                env.grade() if done
                else clamp_task_score(info.get("cumulative_reward", 0.0))
            )
            state["status"] = "COMPLETE" if done else "ACTIVE"

            feedback_label, _, _ = _feedback_meta(float(reward.value))
            state["history"] = list(state["history"]) + [{
                "step": obs.step,
                "feedback": feedback_label,
                "reward": float(reward.value),
                "action": action_type,
                "target": target,
                "reason": reward.reason,
                "done": done,
            }]
            _append_terminal(state, f"[STEP {obs.step}] {action_type}:{target} reward={float(reward.value):+.4f}")
            _append_terminal(state, f"[WHY] {reward.reason}")
            if done:
                _append_terminal(state, f"[END] final_grade={env.grade():.4f}")
        except Exception as exc:
            state["status"] = "ERROR"
            state["error"] = f"Action failed — reset first if episode ended. Details: {exc}"
            _append_terminal(state, f"[ERROR] {state['error']}")
        return _build_episode_outputs(env, state)

    def refresh_benchmark_panels():
        store = load_benchmark_store(BENCHMARK_FILE)
        latest_run = store.get("latest_run")
        log_text = "\n".join(latest_run.get("log_lines", [])) if latest_run else ""
        return (
            store,
            _render_stats_cards(store),
            _render_benchmark_status(latest_run),
            _render_benchmark_summary(latest_run),
            _benchmark_rows(store),
            store,
            log_text,
            _render_podium(store),
            _benchmark_rows(store),
            _filter_log_text(store),
        )

    def sync_target_choices(action_type: str):
        choices = ["postgres-db"] if action_type == "run_db_query" else list(SERVICES)
        return gr.update(choices=choices, value=choices[0])

    # ── Gradio UI ─────────────────────────────────────────────────────────────

    with gr.Blocks(
        css=CUSTOM_CSS,
        theme=gr.themes.Base(
            primary_hue="amber",
            neutral_hue="gray",
            font=gr.themes.GoogleFont("JetBrains Mono"),
        ),
        title="Incident Response Env — RL Benchmark",
    ) as demo:

        # ── Shared state ─────────────────────────────────────────────────────
        ui_state   = gr.State(initial_state)
        bench_store = gr.State(initial_store)

        # ── Header ───────────────────────────────────────────────────────────
        gr.HTML(_render_header_bar())

        # ── Hero ASCII logo ───────────────────────────────────────────────────
        gr.HTML("""
<div class="hero-shell">
<pre>
 ██╗███╗   ██╗ ██████╗██╗██████╗ ███████╗███╗   ██╗████████╗
 ██║████╗  ██║██╔════╝██║██╔══██╗██╔════╝████╗  ██║╚══██╔══╝
 ██║██╔██╗ ██║██║     ██║██║  ██║█████╗  ██╔██╗ ██║   ██║
 ██║██║╚██╗██║██║     ██║██║  ██║██╔══╝  ██║╚██╗██║   ██║
 ██║██║ ╚████║╚██████╗██║██████╔╝███████╗██║ ╚████║   ██║
 ╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
       RESPONSE  ENVIRONMENT  ▸  RL  BENCHMARK  v1.0
</pre>
</div>""")

        # ── Tabs ─────────────────────────────────────────────────────────────
        with gr.Tabs():

            # ─── /dashboard ─────────────────────────────────────────────────
            with gr.TabItem("/dashboard"):
                stats_html = gr.HTML(_render_stats_cards(initial_store))

                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### ▶ Reset / Start Episode")
                        task_dd = gr.Dropdown(
                            choices=list(TASKS.keys()),
                            value="task_easy",
                            label="Task",
                        )
                        reset_btn = gr.Button("RESET ENVIRONMENT", variant="primary")

                    with gr.Column(scale=1):
                        gr.Markdown("### ⚡ Execute Action")
                        action_dd = gr.Dropdown(
                            choices=[
                                "check_health", "check_metrics", "read_logs",
                                "run_db_query", "restart_service",
                                "rollback_deployment", "declare_rca",
                            ],
                            value="check_health",
                            label="Action Type",
                        )
                        target_dd = gr.Dropdown(
                            choices=list(SERVICES),
                            value=SERVICES[0],
                            label="Target Service",
                        )
                        step_btn = gr.Button("EXECUTE ACTION", variant="primary")

                alert_html  = gr.HTML(_render_alert(""))
                status_html = gr.HTML("")
                score_html  = gr.HTML("")
                footer_html = gr.HTML(_render_footer_bar(initial_state))

                gr.Markdown("#### Step History")
                history_df = gr.Dataframe(
                    headers=["Step", "Signal", "Reward", "Action", "Target", "Reason", "Done"],
                    value=_history_rows(initial_state),
                    interactive=False,
                )

            # ─── /live ──────────────────────────────────────────────────────
            with gr.TabItem("/live"):
                timeline_html = gr.HTML(_render_episode_timeline(initial_state))
                service_map_html = gr.HTML(_render_service_map(initial_state))

            # ─── /benchmark ─────────────────────────────────────────────────
            with gr.TabItem("/benchmark"):
                gr.Markdown("### Run a Model Benchmark")
                bench_model_dd = gr.Dropdown(choices=MODEL_CHOICES, value=MODEL_CHOICES[0], label="Model")
                bench_api_inp  = gr.Textbox(value=DEFAULT_API_BASE, label="API Base URL")
                bench_btn      = gr.Button("RUN BENCHMARK (inference.py)", variant="primary")

                bench_status_html  = gr.HTML(_render_benchmark_status())
                bench_summary_html = gr.HTML(_render_benchmark_summary(None))
                bench_log_box      = gr.Textbox(
                    label="Benchmark Log Stream",
                    lines=15, max_lines=20,
                    interactive=False,
                )
                gr.Markdown("#### Results Table")
                bench_df = gr.Dataframe(
                    headers=["#", "Model", "Easy", "Medium", "Hard", "Average", "Solved", "Timestamp"],
                    value=_benchmark_rows(initial_store),
                    interactive=False,
                )
                refresh_bench_btn = gr.Button("REFRESH FROM benchmark.json", variant="secondary")

            # ─── /leaderboard ───────────────────────────────────────────────
            with gr.TabItem("/leaderboard"):
                podium_html = gr.HTML(_render_podium(initial_store))
                gr.Markdown("#### Full Rankings")
                leader_df = gr.Dataframe(
                    headers=["#", "Model", "Easy", "Medium", "Hard", "Average", "Solved", "Timestamp"],
                    value=_benchmark_rows(initial_store),
                    interactive=False,
                )
                refresh_leader_btn = gr.Button("REFRESH LEADERBOARD", variant="secondary")

            # ─── /logs ──────────────────────────────────────────────────────
            with gr.TabItem("/logs"):
                with gr.Row():
                    log_level_dd = gr.Dropdown(
                        choices=["ALL", "START", "STEP", "END", "DEBUG", "ERROR", "WARN"],
                        value="ALL", label="Log Level Filter",
                    )
                    log_search = gr.Textbox(label="Search", placeholder="filter by text...")
                log_box = gr.Textbox(
                    label="Log Output",
                    value=_filter_log_text(initial_store),
                    lines=25, max_lines=40,
                    interactive=False,
                )
                refresh_logs_btn = gr.Button("REFRESH LOGS", variant="secondary")

            # ─── /help ──────────────────────────────────────────────────────
            with gr.TabItem("/help"):
                gr.HTML(_render_help_terminal())

        # ── Wire events ───────────────────────────────────────────────────────

        # Dashboard reset
        reset_btn.click(
            fn=reset_task,
            inputs=[task_dd, ui_state],
            outputs=[ui_state, status_html, alert_html, timeline_html,
                     history_df, score_html, service_map_html, footer_html],
        )

        # Dashboard step
        step_btn.click(
            fn=execute_action,
            inputs=[task_dd, action_dd, target_dd, ui_state],
            outputs=[ui_state, status_html, alert_html, timeline_html,
                     history_df, score_html, service_map_html, footer_html],
        )

        # Auto-fix target choices when action changes
        action_dd.change(fn=sync_target_choices, inputs=[action_dd], outputs=[target_dd])

        # Benchmark refresh (reads benchmark.json)
        def _bench_refresh():
            store = load_benchmark_store(BENCHMARK_FILE)
            latest = store.get("latest_run")
            log_text = "\n".join(latest.get("log_lines", [])) if latest else ""
            return (
                store,
                _render_stats_cards(store),
                _render_benchmark_status(latest),
                _render_benchmark_summary(latest),
                _benchmark_rows(store),
                store,
                log_text,
                _render_podium(store),
                _benchmark_rows(store),
                _filter_log_text(store),
            )

        refresh_bench_btn.click(
            fn=_bench_refresh,
            inputs=[],
            outputs=[bench_store, stats_html, bench_status_html,
                     bench_summary_html, bench_df, bench_store,
                     bench_log_box, podium_html, leader_df, log_box],
        )

        refresh_leader_btn.click(
            fn=_bench_refresh,
            inputs=[],
            outputs=[bench_store, stats_html, bench_status_html,
                     bench_summary_html, bench_df, bench_store,
                     bench_log_box, podium_html, leader_df, log_box],
        )

        refresh_logs_btn.click(
            fn=lambda level, q: _filter_log_text(load_benchmark_store(BENCHMARK_FILE), level, q),
            inputs=[log_level_dd, log_search],
            outputs=[log_box],
        )

        log_level_dd.change(
            fn=lambda level, q: _filter_log_text(load_benchmark_store(BENCHMARK_FILE), level, q),
            inputs=[log_level_dd, log_search],
            outputs=[log_box],
        )

        log_search.submit(
            fn=lambda level, q: _filter_log_text(load_benchmark_store(BENCHMARK_FILE), level, q),
            inputs=[log_level_dd, log_search],
            outputs=[log_box],
        )

        # Benchmark run button — calls inference.py as subprocess and streams logs
        def run_benchmark_ui(model: str, api_base: str):
            import subprocess, os
            env_vars = {**os.environ, "MODEL_NAME": model, "API_BASE_URL": api_base}
            api_key = os.environ.get("API_KEY") or os.environ.get("HF_TOKEN", "")
            env_vars["API_KEY"] = api_key
            log_lines = [f"[START] model={model} api_base={api_base}"]
            try:
                proc = subprocess.run(
                    ["python", str(_root / "inference.py")],
                    capture_output=True, text=True, timeout=300, env=env_vars,
                )
                log_lines += proc.stdout.splitlines()
                if proc.stderr:
                    log_lines += [f"[STDERR] {l}" for l in proc.stderr.splitlines()]
                if proc.returncode != 0:
                    return (
                        _render_benchmark_status(error=f"Exit code {proc.returncode}"),
                        "\n".join(log_lines),
                    )
                # Try to parse scores from log lines and save
                task_scores = {}
                for line in log_lines:
                    for tid in ["task_easy", "task_medium", "task_hard"]:
                        if tid in line and "score=" in line:
                            try:
                                score = float(line.split("score=")[1].split()[0])
                                task_scores[tid] = score
                            except Exception:
                                pass
                store = load_benchmark_store(BENCHMARK_FILE)
                store = record_run(store, model, task_scores, api_base, log_lines)
                save_benchmark_store(BENCHMARK_FILE, store)
                latest = store.get("latest_run")
                return _render_benchmark_status(latest), "\n".join(log_lines)
            except subprocess.TimeoutExpired:
                return _render_benchmark_status(error="Timeout after 300s"), "\n".join(log_lines)
            except Exception as exc:
                return _render_benchmark_status(error=str(exc)), "\n".join(log_lines)

        bench_btn.click(
            fn=run_benchmark_ui,
            inputs=[bench_model_dd, bench_api_inp],
            outputs=[bench_status_html, bench_log_box],
        )

    return demo