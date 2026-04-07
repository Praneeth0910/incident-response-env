import gradio as gr
from gradio.themes import Base

custom_css = """
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;700&family=Share+Tech+Mono&display=swap');

:root {
  --bg-void:      #000000;
  --bg-terminal:  #0a0a0a;
  --bg-panel:     #111111;
  --bg-raised:    #1a1a1a;
  --bg-input:     #0d0d0d;

  --amber:        #f59e0b;
  --amber-dim:    #92610a;
  --amber-glow:   rgba(245, 158, 11, 0.12);

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

body, .gradio-container {
  font-family: var(--font-mono) !important;
  font-size: 13px !important;
  line-height: 1.6;
  color: var(--text-primary) !important;
  background-color: var(--bg-void) !important;
  letter-spacing: 0.02em;
}

/* Override Gradio defaults specifically */
.dark, .dark body {
  background-color: var(--bg-void) !important;
}

.svelte-101kdb3 { /* Some general containers */
  background: var(--bg-void) !important;
}

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

.stat-label {
  font-size: 10px;
  letter-spacing: 0.15em;
  color: var(--text-muted);
  text-transform: uppercase;
  margin-bottom: 8px;
  display: block;
}

.stat-value {
  font-size: 28px;
  font-weight: 700;
  color: var(--amber);
  font-family: var(--font-display);
  display: block;
}

.stat-sub {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  display: block;
}

/* Buttons */
button {
  font-family: var(--font-mono) !important;
  border-radius: 0 !important;
  text-transform: uppercase;
}

button.primary {
  background-color: var(--amber-glow) !important;
  border: 1px solid var(--amber) !important;
  color: var(--amber) !important;
}

button.primary:hover {
  background-color: var(--amber) !important;
  color: var(--bg-void) !important;
}

button.stop {
  background-color: transparent !important;
  border: 1px solid var(--red) !important;
  color: var(--red) !important;
}

/* Tabs */
.tabs {
  border: none !important;
  background: transparent !important;
}
.tab-nav {
  border-bottom: 1px solid var(--border-dim) !important;
  margin-bottom: 20px !important;
}
.tabitem {
  border: none !important;
}
.selected {
  color: var(--amber) !important;
  border-bottom: 2px solid var(--amber) !important;
}

/* Inputs */
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

def create_dashboard():
    # We use a base theme then heavily override it via CSS to achieve the Bloomberg terminal look.
    with gr.Blocks(title="Incident Response Env", css=custom_css, theme=Base()) as demo:
        
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
       RESPONSE  ENVIRONMENT  ▸  RL  BENCHMARK  v1.0
</pre>
            </div>
            """)

        with gr.Row():
            gr.HTML("""
            <div style="display: flex; gap: 16px; width: 100%; margin-bottom: 20px;">
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
            </div>
            """)

        with gr.Tabs():
            with gr.TabItem("/dashboard"):
                with gr.Row():
                    with gr.Column(scale=1, variant="panel", elem_classes="bg-terminal"):
                        gr.Markdown("### 📡 STATUS")
                        gr.Markdown("ENV: **READY**\n\nSTEP: **0/10**\n\nREWARD: **0.0000**")
                        
                    with gr.Column(scale=3):
                        gr.Markdown("### ⚡ QUICK ACTIONS")
                        with gr.Row():
                            btn_easy = gr.Button("▶ RUN EASY", elem_classes=["primary"])
                            btn_med = gr.Button("▶ RUN MEDIUM")
                            btn_hard = gr.Button("▶ RUN HARD", elem_classes=["stop"])
                            
                        gr.Markdown("### 📈 EPISODE LOG")
                        log_out = gr.Textbox(
                            value="[SYSTEM] Dashboard initialized...\n[SYSTEM] Awaiting task execution.",
                            lines=8, 
                            interactive=False,
                            label=""
                        )

            with gr.TabItem("/benchmark"):
                gr.Markdown("### 🚀 MULTI-LLM BENCHMARK RUNNER")
                with gr.Row():
                    with gr.Column(scale=2):
                        model_dropdown = gr.Dropdown(
                            choices=["openai/gpt-4o", "anthropic/claude-3-opus", "qwen/qwen2.5-72b", "meta/llama-3-70b"], 
                            value="openai/gpt-4o",
                            label="MODEL ID"
                        )
                        endpoint_input = gr.Textbox(
                            label="API ENDPOINT", 
                            placeholder="https://api.openai.com/v1"
                        )
                    with gr.Column(scale=1):
                        run_bench_btn = gr.Button("▶ EXECUTE BENCHMARK", elem_classes=["primary"])

            with gr.TabItem("/live"):
                gr.Markdown("### 🔴 LIVE INCIDENT FEED")
                gr.Markdown("> Not currently in an active incident.")

    return demo


from .dashboard_impl import create_dashboard
