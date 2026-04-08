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

import html
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Generator, Dict, Any, List, Tuple

import gradio as gr

from benchmark_runner import (
    BENCHMARK_FILE,
    clamp_task_score,
    load_benchmark_store,
    run_benchmark,
)
from environment import IncidentResponseEnv, SERVICES, TASKS
from models import Action


MODEL_CHOICES = [
    "openai/gpt-4o",
    "openai/gpt-4o-mini",
    "Qwen/Qwen2.5-72B-Instruct",
    "meta-llama/Llama-3.3-70B-Instruct",
    "llama-3.3-70b-versatile",
    "mixtral-8x7b-32768",
]

DEFAULT_API_BASE = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
DEFAULT_ENV_BASE = os.getenv("ENV_BASE_URL", "http://localhost:7860")

custom_css = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');

:root {
  --bg-void: #000000;
  --bg-terminal: #0a0a0a;
  --bg-panel: #111111;
  --bg-input: #0d0d0d;
  --amber: #f59e0b;
  --amber-glow: rgba(245, 158, 11, 0.12);
  --green: #22c55e;
  --yellow: #eab308;
  --red: #ef4444;
  --text-primary: #e8e8e8;
  --text-secondary: #a0a0a0;
  --text-muted: #666666;
  --border-dim: #232323;
  --font-mono: 'JetBrains Mono', monospace;
  --font-display: 'Share Tech Mono', monospace;
}

body, .gradio-container {
  background: var(--bg-void) !important;
  color: var(--text-primary) !important;
  font-family: var(--font-mono) !important;
}

.dark, .dark body, .svelte-101kdb3 {
  background: var(--bg-void) !important;
}

.hero-shell pre {
  margin: 0;
  padding: 18px 20px;
  background: var(--bg-terminal);
  border: 1px solid var(--border-dim);
  color: var(--amber);
  font-family: var(--font-display);
  font-size: 15px;
  letter-spacing: 0.12em;
  box-shadow: 0 0 20px var(--amber-glow);
}

.stats-grid, .status-grid, .summary-grid {
  display: grid;
  gap: 12px;
}

.stats-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin: 18px 0 10px 0;
}

.status-grid {
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-bottom: 12px;
}

.summary-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.stat-card, .panel-block, .summary-card, .mini-stat {
  background: var(--bg-panel);
  border: 1px solid var(--border-dim);
}

.stat-card {
  border-top: 2px solid var(--amber);
  padding: 14px 16px;
}

.panel-block, .summary-card, .mini-stat {
  padding: 12px 14px;
}

.stat-label, .section-label, .mini-stat span, .summary-card span {
  color: var(--text-muted);
  display: block;
  font-size: 10px;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.stat-value {
  color: var(--amber);
  display: block;
  font-family: var(--font-display);
  font-size: 28px;
  font-weight: 700;
}

.stat-sub, .muted-copy {
  color: var(--text-secondary);
  display: block;
  font-size: 12px;
  line-height: 1.7;
}

.alert-banner {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.35);
  border-left: 4px solid var(--red);
  color: var(--text-primary);
  padding: 14px 16px;
}

.feedback-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: 1px solid var(--border-dim);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.feedback-pos { background: rgba(34, 197, 94, 0.10); border-color: rgba(34, 197, 94, 0.35); color: var(--green); }
.feedback-warn { background: rgba(234, 179, 8, 0.10); border-color: rgba(234, 179, 8, 0.35); color: var(--yellow); }
.feedback-neg { background: rgba(239, 68, 68, 0.10); border-color: rgba(239, 68, 68, 0.35); color: var(--red); }

.error-box {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid rgba(239, 68, 68, 0.35);
  color: #fecaca;
  margin-top: 12px;
  padding: 10px 12px;
}

.score-wrap {
  align-items: center;
  display: flex;
  gap: 14px;
}

.score-bar {
  color: var(--amber);
  font-family: var(--font-display);
  font-size: 17px;
  letter-spacing: 0.08em;
}

.score-number {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 700;
}

.header-bar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 12px 18px;
  background: var(--bg-void);
  border: 1px solid var(--border-dim);
  margin-bottom: 14px;
}

.header-logo {
  color: var(--amber);
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.12em;
}

.status-badge {
  border: 1px solid var(--border-dim);
  color: var(--text-secondary);
  font-size: 10px;
  letter-spacing: 0.12em;
  padding: 4px 8px;
  text-transform: uppercase;
}

.status-running {
  background: rgba(34, 197, 94, 0.15);
  border-color: rgba(34, 197, 94, 0.35);
  color: var(--green);
}

.status-version,
.status-benchmark {
  background: var(--bg-terminal);
}

.dashboard-shell {
  display: grid;
  grid-template-columns: minmax(240px, 280px) minmax(0, 1fr);
  gap: 16px;
}

.sidebar-stack,
.main-stack {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.hero-copy {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 1.8;
  margin-top: 10px;
}

.step-timeline {
  background: var(--bg-panel);
  border: 1px solid var(--border-dim);
  padding: 14px 16px;
}

.step-item {
  display: flex;
  gap: 12px;
  padding: 8px 0 8px 16px;
  border-left: 1px solid var(--border-dim);
  margin-left: 8px;
  position: relative;
}

.step-item::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 14px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--amber);
}

.step-number {
  color: var(--text-muted);
  font-size: 11px;
  min-width: 42px;
}

.step-action {
  color: var(--amber);
  font-weight: 600;
}

.step-target {
  color: var(--text-primary);
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

/* Sidebar constraint — DESIGN.md: 220px fixed */
.sidebar-col { min-width: 220px; max-width: 280px; }

/* Scan line animation */
.panel {
  position: relative;
  overflow: hidden;
}
.panel::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--amber-glow), transparent);
  animation: scan 4s linear infinite;
  opacity: 0.3;
  pointer-events: none;
}
@keyframes scan {
  0%   { top: 0; }
  100% { top: 100%; }
}

/* Type-in animation for new log lines */
@keyframes type-in {
  from { opacity: 0; transform: translateX(-4px); }
  to   { opacity: 1; transform: translateX(0); }
}
.log-line-new { animation: type-in 0.1s ease-out; }

/* Score meter fill */
@keyframes fill-meter {
  from { width: 0%; }
  to   { width: var(--target-width); }
}
.score-meter-fill {
  animation: fill-meter 0.8s cubic-bezier(0.25, 0.46, 0.45, 0.94) forwards;
}

/* Command input */
.command-input-wrap {
  display: flex;
  align-items: center;
  background: var(--bg-input);
  border: 1px solid var(--border-amber);
  padding: 8px 12px;
  gap: 8px;
}
.command-prompt { color: var(--amber); font-size: 14px; }
.command-prompt::before { content: '$ '; }
.command-input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-family: var(--font-mono);
  font-size: 13px;
  flex: 1;
  caret-color: var(--amber);
}

/* Log viewer color coding — DESIGN.md */
.log-viewer {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.9;
  padding: 16px;
  background: var(--bg-terminal);
  border: 1px solid var(--border-dim);
}
.log-start  { color: var(--blue); }
.log-step   { color: var(--text-primary); }
.log-end    { color: var(--amber); }
.log-debug  { color: var(--text-muted); }
.log-error  { color: var(--red); }
.log-warn   { color: var(--yellow); }
.log-info   { color: var(--blue); }

/* Benchmark table — DESIGN.md */
.benchmark-table table {
  width: 100%;
  border-collapse: collapse;
  font-family: var(--font-mono);
  font-size: 13px;
}
.benchmark-table th {
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  text-align: left;
  padding: 8px 12px;
  border-bottom: 1px solid var(--amber-dim);
}
.benchmark-table td {
  padding: 10px 12px;
  border-bottom: 1px solid var(--border-dim);
  color: var(--text-primary);
}
.benchmark-table tr:hover td { background: var(--bg-raised); }
.score-high  { color: var(--green); }
.score-med   { color: var(--yellow); }
.score-low   { color: var(--red); }

/* Alert pulse animation — DESIGN.md */
@keyframes pulse-border {
  0%, 100% { border-left-color: var(--red); }
  50% { border-left-color: var(--red-dim); }
}
.alert-banner { animation: pulse-border 2s ease-in-out infinite; }

/* Blink animation for status badge */
@keyframes blink { 50% { opacity: 0; } }
.status-running::before { content: ''; animation: blink 1s step-end infinite; }

/* Help page extras */
.help-desc { color: var(--text-secondary); }
.help-section-title {
  color: var(--text-primary);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 20px;
}
"""


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
            f"[SYSTEM] Benchmark store path: {BENCHMARK_FILE}",
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


def _render_header_bar() -> str:
    return """
    <div class="header-bar">
      <span class="header-logo">[&#9654; INCIDENT-RESPONSE-ENV]</span>
      <span class="status-badge status-running">&#9679; RUNNING</span>
      <span class="status-badge status-version">v1.0.0</span>
      <span class="status-badge status-benchmark">BENCHMARK MODE</span>
    </div>
    """


def _render_footer_bar(state: Dict[str, Any]) -> str:
    task_meta = TASKS.get(state["task_id"], TASKS["task_easy"])
    return f"""
    <div class="status-bar">
      <span class="status-item">ENV:<strong>{html.escape(state['status'])}</strong></span>
      <span class="status-item">TASK:<strong>{html.escape(task_meta['difficulty'].upper())}</strong></span>
      <span class="status-item">STEP:<strong>{state['step']} / {task_meta['max_steps']}</strong></span>
      <span class="status-item">REWARD:<strong>{state['last_reward']:+.4f}</strong></span>
      <span class="status-item">SCORE:<strong>{clamp_task_score(state['score']):.4f}</strong></span>
      <span class="status-item">TIME:<strong>{_timestamp_text()}</strong></span>
    </div>
    """


def _render_stats_cards(store: Dict[str, Any]) -> str:
    leaderboard = store.get("leaderboard", [])
    model_count = len(leaderboard)
    solved = sum(item.get("tasks_solved", 0) for item in leaderboard)
    total_tasks = sum(item.get("tasks_total", 0) for item in leaderboard)
    average_score = (
        sum(item.get("average_score", 0.0) for item in leaderboard) / model_count
        if model_count
        else 0.0
    )
    best = leaderboard[0] if leaderboard else None
    solved_text = f"{solved} / {total_tasks}" if total_tasks else "0 / 0"
    solved_sub = (
        f"{(solved / total_tasks) * 100:.1f}% success"
        if total_tasks
        else "No model runs yet"
    )
    best_value = f"{best['average_score']:.4f}" if best else "--"
    best_sub = best["model"] if best else "Waiting for benchmark.json"
    return f"""
    <div class="stats-grid">
      <div class="stat-card"><span class="stat-label">Models Benchmarked</span><span class="stat-value">{model_count}</span><span class="stat-sub">latest run per model</span></div>
      <div class="stat-card"><span class="stat-label">Tasks Solved</span><span class="stat-value">{solved_text}</span><span class="stat-sub">{solved_sub}</span></div>
      <div class="stat-card"><span class="stat-label">Best Average</span><span class="stat-value">{best_value}</span><span class="stat-sub">{html.escape(best_sub)}</span></div>
      <div class="stat-card"><span class="stat-label">Average Score</span><span class="stat-value">{average_score:.4f}</span><span class="stat-sub">across latest model runs</span></div>
    </div>
    """


def _render_alert(alert: str) -> str:
    if not alert:
        return (
            '<div class="panel-block"><span class="section-label">Incident Alert</span>'
            '<div class="muted-copy">No active incident. Reset a task to start a run.</div></div>'
        )
    return (
        '<div class="alert-banner"><span class="section-label">Incident Alert</span>'
        f"<div>{html.escape(alert)}</div></div>"
    )


def _render_status_panel(state: Dict[str, Any]) -> str:
    task_meta = TASKS[state["task_id"]]
    feedback_label, feedback_class, icon = _feedback_meta(state["last_reward"])
    error_block = (
        f'<div class="error-box">{html.escape(state["error"])}</div>'
        if state.get("error")
        else ""
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
      <div class="muted-copy"><strong>Reason:</strong> {html.escape(state['last_reason'])}</div>
      {error_block}
    </div>
    """


def _render_score_panel(score: float, label: str) -> str:
    safe_score = clamp_task_score(score)
    return f"""
    <div class="panel-block">
      <span class="section-label">{html.escape(label)}</span>
      <div class="score-wrap">
        <span class="score-bar">{_ascii_bar(safe_score)}</span>
        <span class="score-number">{safe_score:.4f}</span>
      </div>
    </div>
    """


def _history_rows(state: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for item in state["history"]:
        rows.append(
            [
                item["step"],
                item["feedback"],
                f"{item['reward']:+.4f}",
                item["action"],
                item["target"],
                item["reason"],
                "yes" if item["done"] else "no",
            ]
        )
    return rows or [[0, "IDLE", "+0.0000", "-", "-", "No actions recorded yet.", "no"]]


def _benchmark_rows(store: Dict[str, Any]) -> List[List[Any]]:
    rows = []
    for index, item in enumerate(store.get("leaderboard", []), start=1):
        task_scores = item.get("task_scores", {})
        rows.append(
            [
                index,
                item.get("model", "unknown"),
                f"{task_scores.get('task_easy', 0.001):.4f}",
                f"{task_scores.get('task_medium', 0.001):.4f}",
                f"{task_scores.get('task_hard', 0.001):.4f}",
                f"{item.get('average_score', 0.001):.4f}",
                f"{item.get('tasks_solved', 0)} / {item.get('tasks_total', len(TASKS))}",
                item.get("timestamp", ""),
            ]
        )
    return rows


def _render_benchmark_status(
    report: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> str:
    if error:
        return f"""
        <div class="panel-block">
          <span class="section-label">Benchmark Status</span>
          <div class="feedback-chip feedback-neg"><span>&#10007;</span><span>Run Failed</span></div>
          <div class="error-box">{html.escape(error)}</div>
        </div>
        """
    if not report:
        return """
        <div class="panel-block">
          <span class="section-label">Benchmark Status</span>
          <div class="muted-copy">No benchmark run recorded yet. Run a model here or call <code>python inference.py</code>.</div>
        </div>
        """
    summary = report.get("summary", {})
    return f"""
    <div class="panel-block">
      <span class="section-label">Benchmark Status</span>
      <div class="feedback-chip feedback-pos"><span>&#10003;</span><span>Benchmark Complete</span></div>
      <div class="muted-copy">
        <strong>Model:</strong> {html.escape(report.get('model', 'unknown'))}<br>
        <strong>Average Score:</strong> {summary.get('average_score', 0.001):.4f}<br>
        <strong>Solved:</strong> {summary.get('tasks_solved', 0)} / {summary.get('tasks_total', len(TASKS))}<br>
        <strong>File:</strong> {html.escape(str(BENCHMARK_FILE))}
      </div>
    </div>
    """


def _render_benchmark_summary(report: Optional[Dict[str, Any]]) -> str:
    if not report:
        return """
        <div class="panel-block">
          <span class="section-label">Latest Benchmark</span>
          <div class="muted-copy">benchmark.json will appear after the first model run.</div>
        </div>
        """
    summary = report.get("summary", {})
    return f"""
    <div class="panel-block">
      <span class="section-label">Latest Benchmark Summary</span>
      <div class="summary-grid">
        <div class="summary-card"><span>Model</span><strong>{html.escape(report.get('model', 'unknown'))}</strong></div>
        <div class="summary-card"><span>Average Score</span><strong>{summary.get('average_score', 0.001):.4f}</strong></div>
        <div class="summary-card"><span>Solved</span><strong>{summary.get('tasks_solved', 0)} / {summary.get('tasks_total', len(TASKS))}</strong></div>
      </div>
      <div class="muted-copy"><strong>Timestamp:</strong> {html.escape(report.get('timestamp', ''))}<br><strong>API Base:</strong> {html.escape(report.get('api_base', ''))}</div>
    </div>
    """


def _render_episode_timeline(state: Dict[str, Any]) -> str:
    if not state["history"]:
        return """
        <div class="step-timeline">
          <span class="section-label">Step Timeline</span>
          <div class="muted-copy">No steps yet. Reset a task and start investigating.</div>
        </div>
        """

    items = ['<div class="step-timeline"><span class="section-label">Step Timeline</span>']
    for item in state["history"]:
        reward_class = (
            "reward-pos" if item["reward"] > 0.02 else
            "reward-neg" if item["reward"] < 0 else
            "reward-zero"
        )
        items.append(
            f"""
            <div class="step-item">
              <span class="step-number">STEP {item['step']}</span>
              <div>
                <span class="step-action">{html.escape(item['action'])}</span>
                <span class="step-target"> - {html.escape(item['target'])}</span>
                <span class="step-reason">{html.escape(item['reason'])}</span>
              </div>
              <span class="step-reward {reward_class}">{item['reward']:+.4f}</span>
            </div>
            """
        )
    items.append("</div>")
    return "".join(items)


def _render_service_map(state: Dict[str, Any]) -> str:
    touched = {
        item["target"]
        for item in state["history"]
        if item.get("target") in SERVICES
    }
    focused = state["history"][-1]["target"] if state["history"] else None
    rca_target = None
    if state["done"]:
        for item in reversed(state["history"]):
            if item["action"] == "declare_rca" and item["target"] in SERVICES:
                rca_target = item["target"]
                break

    nodes = ['<div class="panel-block"><span class="section-label">Service Map</span><div class="service-map">']
    for service in SERVICES:
        label = "IDLE"
        node_class = "service-node"
        if service == rca_target and state["last_reward"] > 0:
            label = "RCA"
            node_class += " service-rca"
        elif service == focused:
            label = "FOCUS"
            node_class += " service-focus"
        elif service in touched:
            label = "SCANNED"
            node_class += " service-scanned"
        nodes.append(
            f'<div class="{node_class}"><strong>{html.escape(service)}</strong><span>{label}</span></div>'
        )
    nodes.append("</div></div>")
    return "".join(nodes)


def _render_podium(store: Dict[str, Any]) -> str:
    leaderboard = store.get("leaderboard", [])[:3]
    if not leaderboard:
        return """
        <div class="panel-block">
          <span class="section-label">Hall of Champions</span>
          <div class="muted-copy">Run a benchmark to populate the leaderboard podium.</div>
        </div>
        """

    cards = ['<div class="podium-grid">']
    labels = ["#1 Champion", "#2 Contender", "#3 Contender"]
    for index in range(3):
        item = leaderboard[index] if index < len(leaderboard) else None
        if item is None:
            cards.append(
                f'<div class="podium-card"><span class="podium-rank">{labels[index]}</span><span class="podium-model">--</span><span class="podium-score">----</span></div>'
            )
            continue
        cards.append(
            f"""
            <div class="podium-card">
              <span class="podium-rank">{labels[index]}</span>
              <span class="podium-model">{html.escape(item['model'])}</span>
              <span class="podium-score">{item['average_score']:.4f}</span>
            </div>
            """
        )
    cards.append("</div>")
    return "".join(cards)


def _render_help_terminal() -> str:
    return """
    <div class="help-terminal">
      <div class="help-header">
        <span>INCIDENT-RESPONSE-ENV(1)</span>
        <span>USER COMMANDS</span>
        <span>VERSION 1.0.0</span>
      </div>
      <div><span class="help-command">/dashboard</span>Mission control and manual episode runner</div>
      <div><span class="help-command">/benchmark</span>Run multi-model benchmarks and persist benchmark.json</div>
      <div><span class="help-command">/live</span>Watch step timeline, rewards, and service focus</div>
      <div><span class="help-command">/leaderboard</span>See the top latest runs per model</div>
      <div><span class="help-command">/logs</span>Inspect the last benchmark log stream</div>
      <div><span class="help-command">/help</span>Read the operating manual and debug state</div>
      <br>
      <div><span class="help-command">run easy</span>Reset task_easy for guided RCA</div>
      <div><span class="help-command">run medium</span>Reset task_medium for guided RCA</div>
      <div><span class="help-command">run hard</span>Reset task_hard for guided RCA</div>
      <div><span class="help-command">grade</span>Inspect the current environment score</div>
      <div><span class="help-command">state</span>Open the JSON environment state inspector</div>
      <div><span class="help-command">export</span>Use benchmark.json as the persistent benchmark store</div>
      <br>
      <div><span class="help-command">Strategy</span>Investigate first, avoid repeats, then declare RCA only when the faulty service is clear.</div>
      <div><span class="help-command">Endpoints</span>/reset  /step  /state  /grade  /tasks</div>
      <div><span class="help-command">Docs</span>docs/ENVIRONMENT.md  docs/BENCHMARK.md  docs/DESIGN.md</div>
    </div>
    """


def _filter_log_text(store: Dict[str, Any], level: str = "ALL", query: str = "") -> str:
    latest_run = store.get("latest_run") or {}
    lines = list(latest_run.get("log_lines", []))
    if level != "ALL":
        marker = f"[{level}]"
        lines = [line for line in lines if marker in line]
    if query:
        lowered = query.lower()
        lines = [line for line in lines if lowered in line.lower()]
    return "\n".join(lines) if lines else "[LOG] No matching lines."


def _inspector_state_json(env: IncidentResponseEnv) -> Dict[str, Any]:
    try:
        return env.state()
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


def _build_episode_outputs(
    env: IncidentResponseEnv,
    state: Dict[str, Any],
) -> Tuple[
    Dict[str, Any],
    str,
    str,
    str,
    List[List[Any]],
    str,
    str,
    Dict[str, Any],
    str,
    str,
]:
    return (
        state,
        _render_status_panel(state),
        _render_alert(state["alert"]),
        _render_episode_timeline(state),
        _history_rows(state),
        _render_score_panel(state["score"], "Live Score"),
        _render_service_map(state),
        _inspector_state_json(env),
        f"{env.grade():.4f}",
        _render_footer_bar(state),
    )


def _sync_target_choices(action_type: str) -> gr.update:
    choices = ["postgres-db"] if action_type == "run_db_query" else SERVICES
    return gr.update(choices=choices, value=choices[0])


def create_dashboard(env_instance: Optional[IncidentResponseEnv] = None):
    env = env_instance or IncidentResponseEnv()
    initial_store = load_benchmark_store(BENCHMARK_FILE)
    initial_state = _fresh_ui_state()

    def reset_task(task_id: str, current_state: Dict[str, Any]):
        state = _fresh_ui_state(task_id)
        try:
            observation = env.reset(task_id=task_id)
            state.update(
                {
                    "alert": observation.alert,
                    "last_message": observation.message,
                    "last_reason": "Environment reset. Pick an action to investigate.",
                    "done": observation.done,
                    "step": observation.step,
                    "score": 0.001,
                    "status": "ACTIVE",
                }
            )
            _append_terminal(state, f"[RESET] task={task_id}")
            _append_terminal(state, f"[ALERT] {observation.alert}")
        except Exception as exc:
            state["status"] = "ERROR"
            state["error"] = f"Could not reset the environment: {exc}"
            _append_terminal(state, f"[ERROR] {state['error']}")
        return _build_episode_outputs(env, state)

    def execute_action(
        task_id: str,
        action_type: str,
        target: str,
        current_state: Dict[str, Any],
    ):
        state = dict(current_state)
        state["task_id"] = task_id
        state["error"] = ""
        try:
            observation, reward, done, info = env.step(
                Action(action_type=action_type, target=target)
            )
            state["alert"] = observation.alert
            state["last_message"] = observation.message
            state["last_reward"] = float(reward.value)
            state["last_reason"] = reward.reason
            state["done"] = done
            state["step"] = observation.step
            state["score"] = (
                env.grade()
                if done
                else clamp_task_score(info.get("cumulative_reward", 0.0))
            )
            state["status"] = "COMPLETE" if done else "ACTIVE"

            feedback_label, _, _ = _feedback_meta(float(reward.value))
            state["history"] = list(state["history"]) + [
                {
                    "step": observation.step,
                    "feedback": feedback_label,
                    "reward": float(reward.value),
                    "action": action_type,
                    "target": target,
                    "reason": reward.reason,
                    "done": done,
                }
            ]

            _append_terminal(
                state,
                f"[STEP {observation.step}] action={action_type}:{target} reward={float(reward.value):+.4f}",
            )
            _append_terminal(state, f"[WHY] {reward.reason}")
            if done:
                _append_terminal(state, f"[END] final_grade={env.grade():.4f}")
        except Exception as exc:
            state["status"] = "ERROR"
            state["error"] = (
                "Action could not be executed. Reset a task first if the episode has "
                f"ended or the environment is idle. Details: {exc}"
            )
            _append_terminal(state, f"[ERROR] {state['error']}")
        return _build_episode_outputs(env, state)

    def refresh_episode(current_state: Dict[str, Any]):
        return _build_episode_outputs(env, dict(current_state))

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

    def execute_benchmark_run(
        model_name: str,
        api_base_url: str,
        api_key: str,
        env_base_url: str,
    ):
        try:
            report = run_benchmark(
                model_name=model_name,
                api_base_url=api_base_url.strip(),
                api_key=api_key.strip(),
                env_base_url=env_base_url.strip(),
                benchmark_file=BENCHMARK_FILE,
            )
            store = load_benchmark_store(BENCHMARK_FILE)
            return (
                store,
                _render_stats_cards(store),
                _render_benchmark_status(report),
                _render_benchmark_summary(report),
                _benchmark_rows(store),
                store,
                "\n".join(report.get("log_lines", [])),
                _render_podium(store),
                _benchmark_rows(store),
                _filter_log_text(store),
            )
        except Exception as exc:
            store = load_benchmark_store(BENCHMARK_FILE)
            latest_run = store.get("latest_run")
            log_text = "\n".join(latest_run.get("log_lines", [])) if latest_run else ""
            return (
                store,
                _render_stats_cards(store),
                _render_benchmark_status(error=str(exc)),
                _render_benchmark_summary(latest_run),
                _benchmark_rows(store),
                store,
                log_text,
                _render_podium(store),
                _benchmark_rows(store),
                _filter_log_text(store),
            )

    def quick_reset(task_id: str):
        return (task_id, *reset_task(task_id, _fresh_ui_state(task_id)))

    def filter_logs(store: Dict[str, Any], level: str, query: str):
        return _filter_log_text(store, level, query)

    with gr.Blocks(title="Incident Response Env") as demo:
        gr.HTML(f"<style>{custom_css}</style>")
        gr.HTML(_render_header_bar())

        stats_html = gr.HTML(_render_stats_cards(initial_store))
        ui_state = gr.State(initial_state)
        benchmark_store_state = gr.State(initial_store)

        with gr.Tabs():
            with gr.TabItem("/dashboard"):
                with gr.Row():
                    with gr.Column(scale=1):
                        status_html = gr.HTML(_render_status_panel(initial_state))
                        task_dropdown = gr.Dropdown(choices=list(TASKS.keys()), value="task_easy", label="Task Select")
                        with gr.Row():
                            btn_easy = gr.Button("Run Easy", variant="primary")
                            btn_medium = gr.Button("Run Medium")
                            btn_hard = gr.Button("Run Hard")
                        action_dropdown = gr.Dropdown(
                            choices=[
                                "read_logs",
                                "check_metrics",
                                "check_health",
                                "run_db_query",
                                "restart_service",
                                "rollback_deployment",
                                "declare_rca",
                            ],
                            value="read_logs",
                            label="Action",
                        )
                        target_dropdown = gr.Dropdown(choices=SERVICES, value=SERVICES[0], label="Target")
                        with gr.Row():
                            act_btn = gr.Button("Execute Action", variant="primary")
                            reset_btn = gr.Button("Reset Task")
                        with gr.Row():
                            refresh_btn = gr.Button("Refresh View")
                            grade_btn = gr.Button("Grade")
                    with gr.Column(scale=2):
                        model_dropdown = gr.Dropdown(
                            choices=MODEL_CHOICES,
                            value="openai/gpt-4o",
                            label="MODEL ID",
                        )
                        endpoint_input = gr.Textbox(
                            label="API ENDPOINT",
                            placeholder="https://api.openai.com/v1",
                        )
                    with gr.Column(scale=1):
                        model_input = gr.Dropdown(choices=MODEL_CHOICES, value=MODEL_CHOICES[0], label="Model Config")
                        api_base_input = gr.Textbox(value=DEFAULT_API_BASE, label="API Endpoint")
                        api_key_input = gr.Textbox(value="", label="API Key", type="password")
                        env_base_input = gr.Textbox(value=DEFAULT_ENV_BASE, label="Environment Base")
                        run_benchmark_btn = gr.Button("Execute Benchmark", variant="primary")
                        refresh_benchmark_btn = gr.Button("Reload benchmark.json")
                    with gr.Column(scale=2):
                        benchmark_status_html = gr.HTML(_render_benchmark_status(initial_store.get("latest_run")))
                        benchmark_summary_html = gr.HTML(_render_benchmark_summary(initial_store.get("latest_run")))
                        benchmark_table = gr.Dataframe(
                            headers=["Rank", "Model", "Easy", "Medium", "Hard", "Average", "Solved", "Updated"],
                            value=_benchmark_rows(initial_store),
                            interactive=False,
                            wrap=True,
                        )
                        benchmark_json = gr.JSON(value=initial_store, label="benchmark.json")
                        benchmark_log = gr.Textbox(
                            value="\n".join((initial_store.get("latest_run") or {}).get("log_lines", [])),
                            label="Benchmark Stream",
                            lines=12,
                            interactive=False,
                        )

            with gr.TabItem("/live"):
                live_alert_html = gr.HTML(_render_alert(""))
                with gr.Row():
                    with gr.Column(scale=2):
                        timeline_html = gr.HTML(_render_episode_timeline(initial_state))
                        history_table = gr.Dataframe(
                            headers=["Step", "Feedback", "Reward", "Action", "Target", "Reason", "Done"],
                            value=_history_rows(initial_state),
                            interactive=False,
                            wrap=True,
                        )
                    with gr.Column(scale=1):
                        live_score_html = gr.HTML(_render_score_panel(0.001, "Cumulative Score Meter"))
                        service_map_html = gr.HTML(_render_service_map(initial_state))

            with gr.TabItem("/leaderboard"):
                podium_html = gr.HTML(_render_podium(initial_store))
                leaderboard_table = gr.Dataframe(
                    headers=["Rank", "Model", "Easy", "Medium", "Hard", "Average", "Solved", "Updated"],
                    value=_benchmark_rows(initial_store),
                    interactive=False,
                    wrap=True,
                )

            with gr.TabItem("/logs"):
                with gr.Row():
                    log_level = gr.Dropdown(
                        choices=["ALL", "START", "STEP", "END", "DEBUG", "ERROR", "WARN", "FILE"],
                        value="ALL",
                        label="Log Level Filter",
                    )
                    log_query = gr.Textbox(label="Search", placeholder="Filter by model, task, or error text")
                logs_viewer = gr.Textbox(
                    value=_filter_log_text(initial_store),
                    label="Raw Log Stream",
                    lines=18,
                    interactive=False,
                )

            with gr.TabItem("/help"):
                gr.HTML(_render_help_terminal())
                with gr.Row():
                    with gr.Column(scale=1):
                        refresh_state_btn = gr.Button("Refresh State", variant="primary")
                        inspector_grade_btn = gr.Button("Get Grade")
                        grade_text = gr.Textbox(value="0.0010", label="Current Grade", interactive=False)
                    with gr.Column(scale=2):
                        state_json = gr.JSON(value=_inspector_state_json(env), label="State Inspector")

        footer_html = gr.HTML(_render_footer_bar(initial_state))

        episode_outputs = [
            ui_state,
            status_html,
            live_alert_html,
            timeline_html,
            history_table,
            live_score_html,
            service_map_html,
            state_json,
            grade_text,
            footer_html,
        ]

        benchmark_outputs = [
            benchmark_store_state,
            stats_html,
            benchmark_status_html,
            benchmark_summary_html,
            benchmark_table,
            benchmark_json,
            benchmark_log,
            podium_html,
            leaderboard_table,
            logs_viewer,
        ]

        action_dropdown.change(fn=_sync_target_choices, inputs=action_dropdown, outputs=target_dropdown)
        reset_btn.click(fn=reset_task, inputs=[task_dropdown, ui_state], outputs=episode_outputs)
        act_btn.click(
            fn=execute_action,
            inputs=[task_dropdown, action_dropdown, target_dropdown, ui_state],
            outputs=episode_outputs,
        )
        refresh_btn.click(fn=refresh_episode, inputs=ui_state, outputs=episode_outputs)
        grade_btn.click(fn=refresh_episode, inputs=ui_state, outputs=episode_outputs)
        refresh_state_btn.click(fn=refresh_episode, inputs=ui_state, outputs=episode_outputs)
        inspector_grade_btn.click(fn=refresh_episode, inputs=ui_state, outputs=episode_outputs)
        btn_easy.click(fn=lambda: quick_reset("task_easy"), inputs=None, outputs=[task_dropdown] + episode_outputs)
        btn_medium.click(fn=lambda: quick_reset("task_medium"), inputs=None, outputs=[task_dropdown] + episode_outputs)
        btn_hard.click(fn=lambda: quick_reset("task_hard"), inputs=None, outputs=[task_dropdown] + episode_outputs)
        run_benchmark_btn.click(
            fn=execute_benchmark_run,
            inputs=[model_input, api_base_input, api_key_input, env_base_input],
            outputs=benchmark_outputs,
        )
        refresh_benchmark_btn.click(fn=refresh_benchmark_panels, outputs=benchmark_outputs)
        log_level.change(fn=filter_logs, inputs=[benchmark_store_state, log_level, log_query], outputs=logs_viewer)
        log_query.change(fn=filter_logs, inputs=[benchmark_store_state, log_level, log_query], outputs=logs_viewer)
        demo.load(fn=refresh_benchmark_panels, outputs=benchmark_outputs)

    return demo


# ──────────────────────────────────────────────────────────────────────────────
# Entry point (run this file directly for dev)
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_dashboard()
    app.launch(show_error=True)