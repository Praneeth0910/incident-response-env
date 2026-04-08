# ============================================================
# HOW TO TEST THE API ON WINDOWS POWERSHELL
# PowerShell's "curl" is actually Invoke-WebRequest, which
# does NOT support -X, -H, -d flags. Use the snippets below.
# ============================================================

# ── 1. Health check ──────────────────────────────────────────
Invoke-RestMethod -Uri "http://localhost:7860/health" -Method GET

# ── 2. Reset episode ─────────────────────────────────────────
Invoke-RestMethod -Uri "http://localhost:7860/reset" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"task_id": "task_easy", "seed": 42}'

# ── 3. Take a step ───────────────────────────────────────────
Invoke-RestMethod -Uri "http://localhost:7860/step" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{"action_type": "check_health", "target": "notification-service"}'

# ── 4. Get ground truth state ─────────────────────────────────
Invoke-RestMethod -Uri "http://localhost:7860/state" -Method GET

# ── 5. Get score ─────────────────────────────────────────────
Invoke-RestMethod -Uri "http://localhost:7860/grade" -Method GET

# ── 6. List tasks ────────────────────────────────────────────
Invoke-RestMethod -Uri "http://localhost:7860/tasks" -Method GET

# ── 7. Open web UI in browser ────────────────────────────────
Start-Process "http://localhost:7860/gradio"

# ============================================================
# STARTING THE SERVER (if port 7860 is blocked, use 8080)
# ============================================================

# Option A — normal start
uvicorn server.app:app --host 0.0.0.0 --port 7860 --reload

# Option B — if port 7860 is blocked by Windows firewall/another process
uvicorn server.app:app --host 0.0.0.0 --port 8080 --reload
# Then change ENV_BASE_URL in your .env to http://localhost:8080

# Option C — run as administrator (fixes WinError 10013)
# Right-click PowerShell → "Run as Administrator", then run Option A

# ============================================================
# SETTING ENV VARS IN POWERSHELL (for local testing)
# ============================================================
$env:API_BASE_URL = "https://router.huggingface.co/v1"
$env:API_KEY      = "hf_YOUR_TOKEN_HERE"
$env:MODEL_NAME   = "Qwen/Qwen2.5-72B-Instruct"
$env:ENV_BASE_URL = "http://localhost:7860"

python inference.py
