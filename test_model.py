from unsloth import FastModel
import torch

# Load your trained model
model, tokenizer = FastModel.from_pretrained(
    model_name = "unsloth/Qwen2.5-1.5B",   # YOUR trained model
    max_seq_length = 1024,
    load_in_4bit = False,
    load_in_16bit = True,
)

FastModel.for_inference(model)

# Your test case
prompt = """
You are an expert SRE agent. Before choosing an action, reason step by step.

STRICT RULES:
- Output ONLY valid JSON
- No extra text outside the JSON
- JSON must have exactly these keys: "reasoning", "action_type", "service_name", "confidence"
- action_type must be one of: ["check_metrics", "check_health", "read_logs", "restart_service"]
- confidence must be: "high", "medium", or "low"
- reasoning must be 1 sentence max — identify the most critical signal first

DANGER SIGNALS (always investigate before acting):
- disk I/O > 85%  → never restart, always check_metrics first
- "under-replicated" → check_metrics on the affected broker
- "lag spike" → read_logs on the consumer before any restart

Example output format:
{
  "reasoning": "Disk I/O at 98% on broker-3 is the primary signal; restart would cause data loss.",
  "action_type": "check_metrics",
  "service_name": "broker-3",
  "confidence": "high"
}

Incident:
10 partitions on topic payments are under-replicated.
One broker (id: 3) is alive but not syncing.
ISR shows only 2 of 3 replicas.
Disk I/O on broker-3 is at 98%.

Output:
"""

inputs = tokenizer(prompt, return_tensors="pt").to("cuda")

outputs = model.generate(
    **inputs,
    max_new_tokens=60,
    temperature=0.0,
    do_sample=False,
    eos_token_id=tokenizer.eos_token_id
)
response = tokenizer.decode(outputs[0], skip_special_tokens=True)

print("\n===== MODEL OUTPUT =====\n")
print(response)