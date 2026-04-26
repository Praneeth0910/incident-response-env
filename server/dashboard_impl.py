"""
dashboard_impl.py
=================
Backend implementation for the Incident Response RL Benchmark dashboard.
Final Hyper-Polish: Absolute visibility, superior error states, and premium micro-interactions.
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

__all__ = ["create_dashboard", "CUSTOM_CSS", "UI_THEME"]

# ── Constants ─────────────────────────────────────────────────────────────────
BENCHMARK_FILE = _root / "benchmark.json"

# ── Helpers ───────────────────────────────────────────────────────────────────

def clamp_task_score(score: float) -> float:
    return round(max(0.001, min(0.999, float(score))), 4)

def load_benchmark_store(path: pathlib.Path) -> Dict[str, Any]:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except FileNotFoundError:
        pass
    except json.JSONDecodeError as e:
        import shutil, logging
        backup_path = path.with_suffix(".json.bak")
        shutil.copy2(path, backup_path)
        logging.warning(f"Corrupted JSON in {path}, backed up to {backup_path}. Error: {e}")
    return {"leaderboard": [], "latest_run": None}

# ── Premium Polished CSS ──────────────────────────────────────────────────

CUSTOM_CSS = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700;800&family=Share+Tech+Mono&display=swap');

:root {
  --bg-void:      #050505;
  --bg-terminal:  #0a0a0c;
  --bg-panel:     #121212;
  --bg-raised:    #18181b;
  --bg-input:     #020202;
  --amber:        #ff9800;
  --amber-glow:   rgba(255, 152, 0, 0.15);
  --amber-hover:  rgba(255, 152, 0, 0.3);
  --amber-active: rgba(255, 152, 0, 0.4);
  --red:          #ff4d4d;
  --red-bg:       rgba(255, 0, 0, 0.1);
  --red-border:   rgba(255, 77, 77, 0.5);
  --red-glow:     rgba(255, 77, 77, 0.3);
  --green:        #00ff77;
  --text-primary:   #ffffff;
  --text-secondary: #f3f4f6;
  --border-std:     1px solid rgba(255, 152, 0, 0.3);
  --font-mono:    'JetBrains Mono', monospace;
  --font-display: 'Share Tech Mono', monospace;
  --transition:   all 0.2s ease;
}

body, .gradio-container, .gradio-container * {
  font-family: var(--font-mono) !important;
}

/* ── Global Micro-interactions ── */
button, .panel-block, .stat-card, .step-timeline, .help-terminal, input, select, textarea, .service-card {
  transition: all 0.2s ease !important;
}

/* ── Form Items ── */
input, select, textarea {
  background: var(--bg-input) !important;
  border: var(--border-std) !important;
  color: var(--text-primary) !important;
  border-radius: 6px !important;
  padding: 12px !important;
  transition: all 0.2s ease !important;
}
input:focus {
  border-color: var(--amber) !important;
  box-shadow: 0 0 10px rgba(255, 165, 0, 0.4) !important;
}

/* ── Buttons ── */
button { 
  border-radius: 4px !important; 
  font-weight: 800 !important; 
  text-transform: uppercase;
  letter-spacing: 0.05em;
  transition: all 0.2s ease !important;
}
button:hover {
  transform: scale(1.03) !important;
  box-shadow: 0 0 15px rgba(255, 165, 0, 0.4) !important;
}
button:active {
  transform: scale(0.97) !important;
}
button.primary { background: var(--amber) !important; color: #000 !important; border: var(--border-std) !important; }

/* ── Cards & Panels ── */
.panel-block, .stat-card, .step-timeline, .help-terminal, .service-card {
  background: var(--bg-panel) !important;
  border: var(--border-std) !important;
  border-radius: 8px !important;
  padding: 24px !important;
  margin-bottom: 24px !important;
  box-shadow: 0 0 12px var(--amber-glow) !important;
  transition: all 0.2s ease !important;
}
.panel-block:hover, .stat-card:hover, .service-card:hover {
  transform: translateY(-3px) !important;
  box-shadow: 0 0 20px rgba(255,165,0,0.3) !important;
}

/* ── Incident Alert & Status ── */
.alert-banner {
  background: rgba(255,0,0,0.1) !important;
  border: 1px solid rgba(255,0,0,0.5) !important;
  border-left: 8px solid #ff4d4d !important;
  padding: 20px 24px !important;
  border-radius: 6px !important;
  color: #ffffff !important;
  font-weight: 800 !important;
  box-shadow: 0 0 12px rgba(255,0,0,0.3) !important;
  opacity: 1 !important;
}
.alert-banner span { color: #ff4d4d !important; font-weight: 900 !important; opacity: 1 !important; }

.error-box {
  background: rgba(255,0,0,0.1) !important;
  border: 1px solid rgba(255,0,0,0.5) !important;
  box-shadow: 0 0 10px rgba(255,0,0,0.3) !important;
  color: #ff4d4d !important;
  padding: 18px !important;
  border-radius: 6px !important;
  font-weight: 700 !important;
  margin-top: 20px;
}

/* ── Stats ── */
.stat-value { color: var(--amber); font-family: var(--font-display); font-size: 32px; font-weight: 900; }
.stat-label { color: var(--text-secondary); font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.1em; }

/* ── Header ── */
.header-bar {
  padding: 20px 35px;
  background: var(--bg-terminal);
  border-bottom: 3px solid var(--amber);
  margin-bottom: 30px;
  display: flex; gap: 20px; align-items: center;
}
.header-logo { color: var(--amber); font-family: var(--font-display); font-size: 22px; font-weight: 900; letter-spacing: 0.05em; }

.status-bar { border-top: 2px solid var(--amber); padding: 15px 35px; background: var(--bg-terminal); font-size: 13px; color: var(--text-secondary); font-weight: 700; margin-top: 40px; }
.status-item strong { color: #fff; }
"""

UI_THEME = gr.themes.Base(
    primary_hue="amber",
    neutral_hue="gray",
    font=gr.themes.GoogleFont("JetBrains Mono"),
)

# ── State helpers ─────────────────────────────────────────────────────────────

def _fresh_ui_state(task_id: str = "task_cpu_spike") -> Dict[str, Any]:
    return {
        "task_id": task_id, "alert": "", "history": [], "last_message": "Reset a task to begin a guided incident run.",
        "last_reward": 0.0, "last_reason": "READY", "done": False, "step": 0, "score": 0.001,
        "status": "READY", "error": "", "terminal_log": ["[SYSTEM] Dashboard ready."]
    }

def _ascii_bar(score: float, width: int = 24) -> str:
    score = clamp_task_score(score)
    filled = max(0, min(width, int(round(score * width))))
    return f"[{'#' * filled}{'.' * (width - filled)}]"

# ── HTML renderers ────────────────────────────────────────────────────────────

def _render_header_bar() -> str:
    return """
<div class="header-bar">
  <span class="header-logo">&#9654; INCIDENT-RESPONSE-ENV</span>
  <span style="border: 2px solid var(--green); color: var(--green); font-size: 11px; padding: 4px 10px; border-radius: 4px; font-weight: 900;">RUNNING</span>
  <span style="border: 2px solid #444; color: #fff; font-size: 11px; padding: 4px 10px; border-radius: 4px; font-weight: 800;">v1.0.0</span>
</div>"""

def _render_footer_bar(state: Dict[str, Any]) -> str:
    task_meta = TASKS.get(state["task_id"], next(iter(TASKS.values())))
    return f"""
<div class="status-bar" style="display: flex; gap: 40px;">
  <span class="status-item">SYSTEM: <strong>{html.escape(state['status'])}</strong></span>
  <span class="status-item">LEVEL: <strong>{html.escape(task_meta['difficulty'].upper())}</strong></span>
  <span class="status-item">STEP: <strong>{state['step']} / {task_meta['max_steps']}</strong></span>
  <span class="status-item">SCORE: <strong>{clamp_task_score(state['score']):.4f}</strong></span>
</div>"""

def _render_stats_cards(store: Dict[str, Any]) -> str:
    lb = store.get("leaderboard", [])
    total_runs = len(lb)
    best = lb[0] if lb else None
    
    best_score_str = f"{best['average_score']:.4f}" if best else "--"
    avg_quality = sum(e['average_score'] for e in lb) / total_runs if total_runs else 0
    success_rate = sum(1 for e in lb if e.get('average_score', 0)>=0.6)
    
    return f"""
<div style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; margin-bottom: 25px;">
  <div class="stat-card"><span class="stat-label">Total Runs</span><span class="stat-value">{total_runs}</span></div>
  <div class="stat-card"><span class="stat-label">Success Rate</span><span class="stat-value">{success_rate}/{total_runs if total_runs else 0}</span></div>
  <div class="stat-card"><span class="stat-label">Best Score</span><span class="stat-value">{best_score_str}</span></div>
  <div class="stat-card"><span class="stat-label">Avg Quality</span><span class="stat-value">{avg_quality:.4f}</span></div>
</div>"""

def _render_alert(alert: str) -> str:
    if not alert: 
        return '<div class="panel-block"><span class="stat-label">No Active Alerts</span><div style="color: #ffffff; font-size: 14px; margin-top: 8px; font-weight: 600;">System operating within normal parameters.</div></div>'
    return f"""<div class="alert-banner">
  <span style="font-size: 12px; text-transform: uppercase; display: block; margin-bottom: 10px;">Critical Incident Detected</span>
  <div style="font-size: 16px; line-height: 1.4;">{html.escape(alert)}</div>
</div>"""

def _render_status_panel(state: Dict[str, Any]) -> str:
    task_meta = TASKS.get(state["task_id"], next(iter(TASKS.values())))
    error_block = f'<div class="error-box">{html.escape(str(state["error"]))}</div>' if state.get("error") else ""
    # Reason box styling: use error-box style if it's a negative reward/reason
    reason_style = 'color: #ffffff;'
    if "REASON" in state["last_reason"].upper() or state.get("last_reward", 0) < 0:
        return f"""<div class="panel-block"><span class="stat-label">Active Session</span>
        <div style="display: flex; gap: 40px; margin: 20px 0;">
          <div><span class="stat-label">Task</span><div style="font-weight: 900; font-size: 20px;">{html.escape(task_meta['name'])}</div></div>
          <div><span class="stat-label">Progress</span><div style="font-weight: 900; font-size: 20px;">{state['step']} / {task_meta['max_steps']}</div></div>
          <div><span class="stat-label">Status</span><div style="font-weight: 900; font-size: 20px; color: var(--amber);">{html.escape(state['status'])}</div></div>
        </div>
        <div class="error-box" style="margin-top: 15px;"><strong>SYSTEM FEEDBACK:</strong> {html.escape(state['last_reason'])}</div>
        {error_block}</div>"""
    
    return f"""
<div class="panel-block">
  <span class="stat-label">Session Status</span>
  <div style="display: flex; gap: 40px; margin: 20px 0;">
    <div><span class="stat-label">Task</span><div style="font-weight: 900; font-size: 20px;">{html.escape(task_meta['name'])}</div></div>
    <div><span class="stat-label">Steps</span><div style="font-weight: 900; font-size: 20px;">{state['step']} / {task_meta['max_steps']}</div></div>
    <div><span class="stat-label">Status</span><div style="font-weight: 900; font-size: 20px; color: var(--amber);">{html.escape(state['status'])}</div></div>
  </div>
  <div style="margin-top: 15px; color: #ffffff; font-size: 14px; font-weight: 600;"><strong>Signal:</strong> {html.escape(state['last_reason'])}</div>
  {error_block}
</div>"""

def _render_score_panel(score: float, label: str) -> str:
    safe = clamp_task_score(score)
    return f"""<div class="panel-block"><span class="stat-label">{html.escape(label)}</span>
<div style="display: flex; align-items: center; gap: 20px; margin-top: 15px;">
  <span style="color: var(--amber); font-family: var(--font-display); font-size: 22px; letter-spacing: 2px;">{_ascii_bar(safe)}</span>
  <span style="font-weight: 900; font-size: 20px;">{safe:.4f}</span>
</div></div>"""

def _render_episode_timeline(state: Dict[str, Any]) -> str:
    if not state["history"]: return '<div class="panel-block"><span class="stat-label">Live Feed</span><div style="color: #666; margin-top: 10px;">Waiting for deployment commands...</div></div>'
    items = ['<div class="step-timeline"><span class="stat-label">History Feed</span>']
    for row in state["history"]:
        rew = row["reward"]
        items.append(f"""<div style="padding: 12px 0; border-bottom: 1px solid #1a1a1a; display: flex; justify-content: space-between; align-items: center;">
  <div><span style="color: var(--amber); font-weight: 900; font-size: 12px; margin-right: 15px;">STP_{row['step']:03d}</span> <strong style="font-size: 14px;">{html.escape(row['action'])}</strong> @ {html.escape(row['target'])}</div>
  <div style="color: {'var(--green)' if rew > 0 else 'var(--red)' if rew < 0 else '#fff'}; font-weight: 900;">{rew:+.4f}</div>
</div>""")
    return "".join(items) + "</div>"

def _render_service_map(state: Dict[str, Any]) -> str:
    nodes = ['<div class="panel-block"><span class="stat-label">Topology</span><div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 20px;">']
    for svc in SERVICES:
        nodes.append(f'<div class="service-card" style="padding: 15px !important; margin-bottom: 0 !important; font-size: 13px !important; color: #ffffff !important;">{html.escape(svc)}</div>')
    return "".join(nodes) + "</div></div>"

def _history_rows(state: Dict[str, Any]) -> List[List[Any]]:
    return [[i["step"], i["reward"], i["action"], i["target"], "YES" if i["done"] else "NO"] for i in state["history"]] or [[0, 0.0, "READY", "-", "NO"]]

def _benchmark_rows(store: Dict[str, Any]) -> List[List[Any]]:
    return [[idx+1, i["model"], i["average_score"], f"{i['tasks_solved']}/{i['tasks_total']}", i["timestamp"]] for idx, i in enumerate(store.get("leaderboard", []))]

def _render_help_terminal() -> str:
    return """<div class="help-terminal"><div style="border-bottom: 1px solid #333; padding-bottom: 10px; margin-bottom: 20px; color: #888; font-size: 12px;">INCIDENT-RESPONSE手册页</div>
<div style="color: var(--amber); font-weight: 900; margin-bottom: 10px;">OPERATIONS</div>
<div style="margin-left: 20px; line-height: 1.8;">
  <strong>POST /reset</strong> - Initialize incident scenario<br>
  <strong>POST /step</strong>  - Execute investigation or mitigation<br>
  <strong>POST /grade</strong> - Finalize report and calc score
</div></div>"""

# ── Dashboard factory ─────────────────────────────────────────────────────────

def create_dashboard(env_instance: Optional[IncidentResponseEnv] = None) -> gr.Blocks:
    env = env_instance or IncidentResponseEnv()
    initial_store = load_benchmark_store(BENCHMARK_FILE)
    initial_state = _fresh_ui_state()

    def reset_task(task_id: str, current_state: Dict[str, Any]):
        state = _fresh_ui_state(task_id)
        try:
            obs = env.reset(task_id=task_id)
            state.update({"alert": obs.alert, "last_reason": "Environment reset. Ready for input.", "status": "ACTIVE"})
        except Exception as exc: state["status"] = "ERROR"; state["error"] = str(exc)
        return _build_episode_outputs(env, state)

    def execute_action(task_id: str, action_type: str, target: str, current_state: Dict[str, Any]):
        state = dict(current_state)
        try:
            action = Action(action_type=action_type, target=target)
            obs, reward, done, info = env.step(action)
            state.update({"alert": obs.alert, "last_reward": float(reward.value), "last_reason": reward.reason, "done": done, "step": obs.step, "score": env.grade() if done else float(info.get("cumulative_reward", 0.0)), "status": "COMPLETE" if done else "ACTIVE"})
            state["history"] = list(state["history"]) + [{"step": obs.step, "reward": float(reward.value), "action": action_type, "target": target, "done": done}]
        except Exception as exc: state["status"] = "ERROR"; state["error"] = str(exc)
        return _build_episode_outputs(env, state)

    def _build_episode_outputs(env, state):
        return (state, _render_status_panel(state), _render_alert(state["alert"]), _render_episode_timeline(state), _history_rows(state), _render_score_panel(state["score"], "Live Alpha Score"), _render_service_map(state), _render_footer_bar(state))

    with gr.Blocks(title="Incident Response SRE Control Panel") as demo:
        ui_state = gr.State(initial_state)
        gr.HTML(_render_header_bar())
        
        # ── Refined Logo Section ──
        gr.HTML("""<div style="margin: 15px 0 35px 0; text-align: center;">
<pre style="display: inline-block; text-align: left; background: #0c0c0c; padding: 22px; border: 1px solid rgba(255, 152, 0, 0.25); border-radius: 8px; color: #ff9800; font-family: 'Share Tech Mono', monospace; line-height: 1.1; font-size: 12px; font-weight: 800; box-shadow: 0 0 12px rgba(255,152,0,0.15);">
 ██╗███╗   ██╗ ██████╗██╗██████╗ ███████╗███╗   ██╗████████╗
 ██║████╗  ██║██╔════╝██║██╔══██╗██╔════╝████╗  ██║╚══██╔══╝
 ██║██╔██╗ ██║██║     ██║██║  ██║█████╗  ██╔██╗ ██║   ██║
 ██║██║╚██╗██║██║     ██║██║  ██║██╔══╝  ██║╚██╗██║   ██║
 ██║██║ ╚████║╚██████╗██║██████╔╝███████╗██║ ╚████║   ██║
 ╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
 <span style="display: block; margin-top: 12px; letter-spacing: 0.35em; font-size: 14px; font-weight: 900;">RESPONSE ENVIRONMENT ▸ RL BENCHMARK v1.0</span>
</pre></div>""")

        with gr.Tabs():
            with gr.TabItem("/dashboard"):
                stats_html = gr.HTML(_render_stats_cards(initial_store))
                with gr.Row():
                    with gr.Column():
                        task_dd = gr.Dropdown(choices=list(TASKS.keys()), value="task_cpu_spike", label="SCENARIO")
                        reset_btn = gr.Button("INITIALIZE", variant="primary")
                    with gr.Column():
                        action_dd = gr.Dropdown(choices=["check_health", "check_metrics", "read_logs", "run_db_query", "restart_service", "rollback_deployment", "declare_rca"], value="check_health", label="COMMAND")
                        target_dd = gr.Dropdown(choices=list(SERVICES), value=SERVICES[0], label="TARGET")
                        step_btn = gr.Button("EXECUTE", variant="primary")
                alert_html, status_html, score_html, footer_html = gr.HTML(""), gr.HTML(""), gr.HTML(""), gr.HTML("")
                timeline_html, service_map_html = gr.HTML(""), gr.HTML("")
                history_df = gr.Dataframe(headers=["STEP", "REW", "ACTION", "TARGET", "DONE"], value=_history_rows(initial_state))
            with gr.TabItem("/live"): 
                gr.HTML("Timeline:"); gr.HTML(value=timeline_html.value if hasattr(timeline_html, 'value') else "")
                gr.HTML("Service Map:"); gr.HTML(value=service_map_html.value if hasattr(service_map_html, 'value') else "")
            with gr.TabItem("/benchmark"): 
                benchmark_df = gr.Dataframe(headers=["#", "MODEL", "AVG", "SOLVED", "TS"], value=_benchmark_rows(initial_store))
                benchmark_refresh_btn = gr.Button("REFRESH", size="sm")
            with gr.TabItem("/leaderboard"): 
                leaderboard_df = gr.Dataframe(headers=["#", "MODEL", "AVG", "SOLVED", "TS"], value=_benchmark_rows(initial_store))
                leaderboard_refresh_btn = gr.Button("REFRESH", size="sm")
            with gr.TabItem("/help"): gr.HTML(_render_help_terminal())

        reset_btn.click(fn=reset_task, inputs=[task_dd, ui_state], outputs=[ui_state, status_html, alert_html, timeline_html, history_df, score_html, service_map_html, footer_html])
        step_btn.click(fn=execute_action, inputs=[task_dd, action_dd, target_dd, ui_state], outputs=[ui_state, status_html, alert_html, timeline_html, history_df, score_html, service_map_html, footer_html])
        action_dd.change(fn=lambda a: gr.update(choices=["postgres-db"] if a=="run_db_query" else list(SERVICES)), inputs=[action_dd], outputs=[target_dd])
        
        # BUG FIX 5: Add refresh handlers for benchmark/leaderboard tabs
        benchmark_refresh_btn.click(fn=lambda: _benchmark_rows(load_benchmark_store(BENCHMARK_FILE)), outputs=[benchmark_df])
        leaderboard_refresh_btn.click(fn=lambda: _benchmark_rows(load_benchmark_store(BENCHMARK_FILE)), outputs=[leaderboard_df])

    return demo