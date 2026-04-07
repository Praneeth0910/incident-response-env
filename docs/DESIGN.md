# DESIGN.md — Terminal UI Design Specification
> **incident-response-env** · Frontend Design System · Gradio + HTML/CSS

This document is the complete design specification for the incident-response-env frontend. Every visual, typographic, and interaction decision is defined here. AI coding agents must follow this spec exactly.

---

## Design Philosophy

**Aesthetic Direction: Dark Ops Terminal**

This is not a toy dashboard. It is a war room. The UI must communicate:
- **Authority** — this system monitors production infrastructure
- **Urgency** — incidents are live, real-time, critical
- **Precision** — every number matters, every pixel earns its place
- **Power** — the environment benchmarks the best AI models in the world

**One-sentence design brief:**
> _A Bloomberg Terminal crossed with a Kubernetes incident war room — pitch black, amber-on-dark type, monospace everywhere, data density at max._

**What it must NOT look like:**
- A Gradio default UI with gray sliders
- A purple-gradient AI startup landing page
- A pastel "friendly" dashboard
- Anything that could be mistaken for a homework project

---

## Color System

```css
:root {
  /* Backgrounds — layered darkness */
  --bg-void:      #000000;    /* outermost container, true black */
  --bg-terminal:  #0a0a0a;    /* primary surface */
  --bg-panel:     #111111;    /* cards, panels */
  --bg-raised:    #1a1a1a;    /* hover state, elevated items */
  --bg-input:     #0d0d0d;    /* input fields */

  /* Primary accent — amber / amber-orange (SRE alert color) */
  --amber:        #f59e0b;    /* primary actions, highlights */
  --amber-dim:    #92610a;    /* secondary amber, borders */
  --amber-glow:   rgba(245, 158, 11, 0.12);  /* glow backgrounds */

  /* Status colors — all desaturated variants for terminal feel */
  --green:        #22c55e;    /* success, PASS, healthy */
  --green-dim:    #15803d;    /* healthy border */
  --red:          #ef4444;    /* error, FAIL, critical */
  --red-dim:      #991b1b;    /* error border */
  --blue:         #3b82f6;    /* info, step indicators */
  --blue-dim:     #1d4ed8;    /* info border */
  --yellow:       #eab308;    /* warning, degraded */
  --yellow-dim:   #854d0e;    /* warning border */

  /* Text hierarchy */
  --text-primary:   #e8e8e8;  /* main content */
  --text-secondary: #a0a0a0;  /* labels, descriptions */
  --text-muted:     #555555;  /* timestamps, meta */
  --text-amber:     #f59e0b;  /* highlighted values */
  --text-green:     #22c55e;  /* success states */
  --text-red:       #ef4444;  /* error states */

  /* Borders */
  --border-dim:     #1f1f1f;  /* panel separators */
  --border-amber:   #92610a;  /* active panel borders */
  --border-focus:   #f59e0b;  /* focused elements */

  /* Typography */
  --font-mono:    'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
  --font-display: 'Share Tech Mono', 'VT323', monospace; /* for hero/title */
}
```

---

## Typography

**Rule: 100% monospace.** No sans-serif. No serif. Every character is a data point.

```css
/* Import from Google Fonts */
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');

body {
  font-family: var(--font-mono);
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-primary);
  background: var(--bg-void);
  letter-spacing: 0.02em;
}

/* Size scale — all in monospace */
.text-xs    { font-size: 11px; }
.text-sm    { font-size: 12px; }
.text-base  { font-size: 13px; }  /* default */
.text-md    { font-size: 15px; }
.text-lg    { font-size: 18px; }
.text-xl    { font-size: 22px; }
.text-hero  { font-size: 32px; font-family: var(--font-display); letter-spacing: 0.1em; }
```

---

## Layout Structure

```
┌─────────────────────────────────────────────────────────────────────┐
│  HEADER BAR                                                          │
│  [▶ INCIDENT-RESPONSE-ENV]  [● RUNNING]  [v1.0.0]  [BENCHMARK MODE]│
├─────────────────────────────────────────────────────────────────────┤
│  NAV BAR (terminal tabs)                                             │
│  [/dashboard] [/benchmark] [/live] [/leaderboard] [/logs] [/help]  │
├────────────────┬────────────────────────────────────────────────────┤
│  LEFT SIDEBAR  │  MAIN CONTENT AREA                                 │
│  (220px fixed) │  (fills remaining width)                           │
│                │                                                     │
│  SYSTEM STATUS │  Active section renders here                        │
│  TASK SELECT   │  Full height, scrollable                           │
│  MODEL SELECT  │                                                     │
│  QUICK STATS   │                                                     │
│                │                                                     │
├────────────────┴────────────────────────────────────────────────────┤
│  FOOTER / STATUS BAR                                                 │
│  [ENV: READY]  [STEP: 0/10]  [REWARD: 0.0000]  [04-08 10:30:00]   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Sections (Pages)

### `/dashboard` — Mission Control
The default landing view. Communicates the power and purpose of the project immediately.

**Components:**
1. **Hero Block** — ASCII art logo + tagline
2. **Live Metrics Row** — 4 stat cards: Active Tasks / Models Tested / Best Score / Avg Score
3. **Episode Progress** — current episode step-by-step timeline
4. **Quick Actions** — Run Easy / Run Medium / Run Hard buttons

**ASCII Logo:**
```
 ██╗███╗   ██╗ ██████╗██╗██████╗ ███████╗███╗   ██╗████████╗
 ██║████╗  ██║██╔════╝██║██╔══██╗██╔════╝████╗  ██║╚══██╔══╝
 ██║██╔██╗ ██║██║     ██║██║  ██║█████╗  ██╔██╗ ██║   ██║
 ██║██║╚██╗██║██║     ██║██║  ██║██╔══╝  ██║╚██╗██║   ██║
 ██║██║ ╚████║╚██████╗██║██████╔╝███████╗██║ ╚████║   ██║
 ╚═╝╚═╝  ╚═══╝ ╚═════╝╚═╝╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝
       RESPONSE  ENVIRONMENT  ▸  RL  BENCHMARK  v1.0
```

**Stat Cards:**
```
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ MODELS BENCHMARKED│ │  TASKS SOLVED    │ │   BEST SCORE     │ │   AVG SCORE      │
│                  │ │                  │ │                  │ │                  │
│       5          │ │     8 / 15       │ │     1.0000       │ │     0.4791       │
│                  │ │                  │ │                  │ │                  │
│ across 3 tasks   │ │  53.3% success   │ │  Qwen2.5-72B     │ │  all models      │
└──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘
```

**CSS for stat cards:**
```css
.stat-card {
  background: var(--bg-panel);
  border: 1px solid var(--border-dim);
  border-top: 2px solid var(--amber);
  padding: 16px 20px;
  flex: 1;
}
.stat-label {
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--amber);
  font-family: var(--font-display);
}
.stat-sub {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
}
```

---

### `/benchmark` — Multi-LLM Benchmark Runner
Run and compare multiple models side by side.

**Components:**
1. **Model Config Panel** — dropdown to select model, API endpoint input
2. **Run Button** — triggers Inference.py for selected model
3. **Progress Stream** — live step log stream while model runs
4. **Results Table** — comparison table, updates after each model completes

**Results Table Style:**
```
┌────────────────────┬──────────┬──────────┬──────────┬──────────┬──────────┐
│ MODEL              │  EASY    │  MEDIUM  │  HARD    │   AVG    │  STATUS  │
├────────────────────┼──────────┼──────────┼──────────┼──────────┼──────────┤
│ Qwen2.5-72B        │  1.0000  │  0.4373  │  0.0000  │  0.4791  │  1/3 ✓  │
│ Llama-3.3-70B      │   ----   │   ----   │   ----   │   ----   │ PENDING  │
│ Mixtral-8x7B       │   ----   │   ----   │   ----   │   ----   │ PENDING  │
│ GPT-4o-mini        │   ----   │   ----   │   ----   │   ----   │ PENDING  │
│ Gemma2-9B          │   ----   │   ----   │   ----   │   ----   │ PENDING  │
└────────────────────┴──────────┴──────────┴──────────┴──────────┴──────────┘
```

**CSS for table:**
```css
.benchmark-table {
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
.score-pass  { color: var(--green); }
.score-fail  { color: var(--red-dim); }
```

---

### `/live` — Live Episode Viewer
Real-time view of a running episode. The most dramatic section.

**Components:**
1. **Alert Banner** — the incident alert, always visible, red pulsing border
2. **Step Timeline** — vertical timeline of actions taken + rewards
3. **Reward Chart** — live updating bar chart (Chart.js)
4. **Cumulative Score Meter** — large animated score display
5. **Service Map** — 6 service nodes, highlights fault service when discovered

**Alert Banner:**
```css
.alert-banner {
  background: rgba(239, 68, 68, 0.08);
  border: 1px solid var(--red-dim);
  border-left: 4px solid var(--red);
  padding: 12px 16px;
  font-size: 13px;
  color: var(--text-primary);
  animation: pulse-border 2s ease-in-out infinite;
}
@keyframes pulse-border {
  0%, 100% { border-left-color: var(--red); }
  50% { border-left-color: var(--red-dim); }
}
```

**Step Timeline Item:**
```css
.step-item {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-left: 1px solid var(--border-dim);
  margin-left: 8px;
  padding-left: 16px;
  position: relative;
}
.step-item::before {
  content: '';
  position: absolute;
  left: -5px;
  top: 12px;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--amber);
}
.step-number   { color: var(--text-muted); font-size: 11px; min-width: 40px; }
.step-action   { color: var(--amber); }
.step-target   { color: var(--text-primary); }
.step-reward   { margin-left: auto; }
.reward-pos    { color: var(--green); }
.reward-neg    { color: var(--red); }
.reward-zero   { color: var(--text-muted); }
```

---

### `/leaderboard` — Hall of Champions
Model rankings across all tasks.

**Components:**
1. **Podium** — top 3 models with large score display
2. **Full Rankings Table** — all models with per-task breakdown
3. **Score Distribution Chart** — histogram of scores per task

**Podium Style:**
```
         ┌──────────────┐
         │  #1 CHAMPION │
         │  Qwen2.5-72B │
         │   0.4791     │
         └──────────────┘
  ┌──────────────┐  ┌──────────────┐
  │  #2          │  │  #3          │
  │  Llama-3.3   │  │  GPT-4o-mini │
  │  ----        │  │  ----        │
  └──────────────┘  └──────────────┘
```

---

### `/logs` — Raw Log Stream
Full log output from the last benchmark run. Feels like a real terminal.

**Components:**
1. **Log Level Filter** — toggle [START] [STEP] [END] [DEBUG] [ERROR]
2. **Search Bar** — filter logs by text
3. **Log Output** — scrollable, color-coded by level
4. **Download Button** — save logs as .txt

**Log Color Coding:**
```css
.log-start  { color: var(--blue); }     /* [START] */
.log-step   { color: var(--text-primary); } /* [STEP] */
.log-end    { color: var(--amber); }    /* [END] */
.log-debug  { color: var(--text-muted); }  /* [DEBUG] */
.log-error  { color: var(--red); }     /* [ERROR] */
.log-warn   { color: var(--yellow); }   /* [WARN] */
.log-info   { color: var(--blue); }    /* INFO: */
.log-reward-pos { color: var(--green); } /* reward=+x.xx */
.log-reward-neg { color: var(--red); }  /* reward=-x.xx */
```

---

### `/help` — Terminal Help System
The `/help` page is itself styled as a terminal man page. Users navigate with keyboard or click commands.

**Layout:**
```
┌─────────────────────────────────────────────────────────────────────┐
│  INCIDENT-RESPONSE-ENV(1)       USER COMMANDS       VERSION 1.0.0   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  NAME                                                                │
│       incident-response-env — RL benchmark for LLM incident response│
│                                                                      │
│  SYNOPSIS                                                            │
│       /dashboard    Mission control and overview                     │
│       /benchmark    Run multi-model benchmarks                       │
│       /live         Watch a live agent episode                       │
│       /leaderboard  Model performance rankings                       │
│       /logs         Raw log stream viewer                            │
│       /help         This page                                        │
│                                                                      │
│  AVAILABLE COMMANDS                                                  │
│       run easy      Start a task_easy episode                        │
│       run medium    Start a task_medium episode                      │
│       run hard      Start a task_hard episode                        │
│       run all       Benchmark all tasks sequentially                 │
│       reset         Reset current episode                            │
│       grade         Show current episode score                       │
│       state         Show environment state (debug mode)              │
│       clear         Clear log output                                 │
│       export        Save benchmark results as JSON                   │
│                                                                      │
│  KEYBOARD SHORTCUTS                                                  │
│       1-6           Navigate sections (1=dashboard, 6=help)         │
│       R             Run current task                                 │
│       Escape        Cancel running task                              │
│       /             Focus command input                              │
│       ?             Toggle this help panel                           │
│                                                                      │
│  SCORING                                                             │
│       Score range   [0.0, 1.0]                                      │
│       Pass threshold ≥ 0.6                                           │
│       Perfect score  1.0 (fast + correct RCA + full evidence)        │
│                                                                      │
│  ENVIRONMENT                                                         │
│       REST API      http://localhost:7860                            │
│       Endpoints     /reset  /step  /state  /grade  /tasks            │
│       Protocol      OpenEnv v1.0                                     │
│                                                                      │
│  SEE ALSO                                                            │
│       docs/AGENT.md           Agent operating manual                 │
│       docs/ENVIRONMENT.md     Full API reference                     │
│       docs/BENCHMARK.md       Running multi-LLM benchmarks          │
│       docs/REWARDS.md         Reward function specification          │
│       docs/SKILLS.md          Agent skill taxonomy                   │
│                                                                      │
│  ── Press any navigation key or type a command ──                   │
└─────────────────────────────────────────────────────────────────────┘
```

**Help Page CSS:**
```css
.help-terminal {
  background: var(--bg-terminal);
  border: 1px solid var(--border-dim);
  font-family: var(--font-mono);
  font-size: 13px;
  padding: 24px 32px;
  line-height: 2;
}
.help-section-title {
  color: var(--text-primary);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-top: 20px;
}
.help-command {
  color: var(--amber);
  display: inline-block;
  min-width: 180px;
}
.help-desc { color: var(--text-secondary); }
.help-header {
  display: flex;
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 11px;
  border-bottom: 1px solid var(--border-dim);
  padding-bottom: 8px;
  margin-bottom: 16px;
}
```

---

## Navigation Bar

```css
.nav-bar {
  display: flex;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border-dim);
  padding: 0;
  overflow-x: auto;
}
.nav-item {
  padding: 12px 20px;
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--text-secondary);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
  transition: color 0.15s, border-color 0.15s;
}
.nav-item:hover { color: var(--text-primary); }
.nav-item.active {
  color: var(--amber);
  border-bottom-color: var(--amber);
}
```

---

## Header Bar

```css
.header-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 12px 20px;
  background: var(--bg-void);
  border-bottom: 1px solid var(--border-dim);
}
.header-logo {
  font-family: var(--font-display);
  font-size: 14px;
  letter-spacing: 0.12em;
  color: var(--amber);
}
.header-logo::before { content: '▶ '; }
.status-badge {
  font-size: 10px;
  letter-spacing: 0.12em;
  padding: 3px 8px;
  border-radius: 2px;
}
.status-running {
  background: rgba(34, 197, 94, 0.15);
  color: var(--green);
  border: 1px solid var(--green-dim);
}
.status-running::before { content: '● '; animation: blink 1s step-end infinite; }
@keyframes blink { 50% { opacity: 0; } }
```

---

## Status Bar (Footer)

Always visible at the bottom. Updates in real time.

```
[ENV: READY]  [STEP: 4/10]  [REWARD: +0.1000]  [SCORE: 0.2700]  [2026-04-08 10:30:45]
```

```css
.status-bar {
  display: flex;
  gap: 24px;
  padding: 8px 20px;
  background: var(--bg-void);
  border-top: 1px solid var(--border-dim);
  font-size: 11px;
  color: var(--text-muted);
}
.status-item span.label { color: var(--text-muted); margin-right: 4px; }
.status-item span.value { color: var(--text-primary); }
.status-item span.value.good { color: var(--green); }
.status-item span.value.bad  { color: var(--red); }
```

---

## Command Input (Global)

A terminal-style command input always accessible via `/` key.

```css
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
```

---

## Animations & Motion

```css
/* Scan line effect on panels (subtle) */
.panel::after {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, var(--amber-glow), transparent);
  animation: scan 4s linear infinite;
  opacity: 0.3;
}
@keyframes scan {
  0%   { top: 0; }
  100% { top: 100%; }
}

/* Type-in animation for log lines */
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
```

---

## Gradio Implementation Notes

When building with Gradio (`gradio.py`):

```python
import gradio as gr

# Use gr.Blocks with custom CSS
with gr.Blocks(
    css=open("static/terminal.css").read(),
    theme=gr.themes.Base(
        primary_hue="amber",
        neutral_hue="gray",
        font=gr.themes.GoogleFont("JetBrains Mono"),
    ),
    title="Incident Response Env"
) as demo:
    # Apply dark theme via CSS override
    # Load JetBrains Mono from Google Fonts in custom head
    pass
```

**Gradio component mapping:**
| Design Component | Gradio Widget |
|---|---|
| Stat cards | `gr.HTML` with custom CSS |
| Step timeline | `gr.HTML` updated via `gr.State` |
| Reward chart | `gr.Plot` (Plotly) |
| Log stream | `gr.Textbox(lines=20, max_lines=20)` |
| Benchmark table | `gr.Dataframe` |
| Command input | `gr.Textbox` with `submit` trigger |
| Navigation tabs | `gr.Tabs` with `gr.TabItem` |
| Status bar | `gr.HTML` at bottom of layout |

---

## File Structure for Frontend

```
incident-response-env/
├── gradio_app.py          # Main Gradio application
├── static/
│   ├── terminal.css       # Full CSS from this spec
│   ├── terminal.js        # Navigation, keyboard shortcuts
│   └── ascii_logo.txt     # ASCII art logo
├── components/
│   ├── dashboard.py       # Dashboard tab components
│   ├── benchmark.py       # Benchmark runner tab
│   ├── live_viewer.py     # Live episode viewer
│   ├── leaderboard.py     # Rankings tab
│   ├── log_viewer.py      # Log stream tab
│   └── help_page.py       # Help / man page tab
└── docs/
    └── DESIGN.md          # This file
```
