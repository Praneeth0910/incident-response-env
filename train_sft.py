"""
train_sft.py

Supervised Fine-Tuning for the SRE incident-response agent.
Reads trajectories from sft_data/trajectories.jsonl, formats them into
ChatML multi-turn conversations, and fine-tunes a LoRA adapter on Qwen3.5-2B.

Uses standard HuggingFace PEFT + TRL stack for maximum GPU memory efficiency
on constrained hardware (6GB VRAM).

Requirements: peft, trl>=0.24, transformers>=5, datasets, torch (CUDA), bitsandbytes
"""

import os, sys, json
sys.path.insert(0, '.')
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
# Force very aggressive chunking so fused CE loss doesn't OOM
os.environ["UNSLOTH_CE_LOSS_N_CHUNKS"] = "128"
os.environ["UNSLOTH_CE_LOSS_TARGET_GB"] = "2"   # cap fused loss memory

from unsloth import FastModel
from datasets import load_dataset
from transformers import TrainingArguments
from trl import SFTTrainer

# ── Load dataset ──────────────────────────────────────────────────────────────
DATA_FILE = "sft_data/trajectories.jsonl"
print(f"Loading dataset from {DATA_FILE}...")
raw = load_dataset("json", data_files=DATA_FILE)["train"]
print(f"Total examples: {len(raw)}")

# Filter to only RCA-correct trajectories (skip bad expert runs)
raw = raw.filter(lambda x: x["rca_correct"])
print(f"After filtering (rca_correct=True): {len(raw)}")

split = raw.train_test_split(test_size=0.1, seed=42)
train_data = split["train"]
eval_data  = split["test"]
print(f"Train: {len(train_data)} | Eval: {len(eval_data)}")

# ── Format into ChatML multi-turn conversations ──────────────────────────────
SYSTEM = (
    "You are an expert SRE agent investigating a production incident.\n"
    "Analyze the observation and choose the best next action.\n"
    "Respond ONLY with valid JSON with keys: reasoning, action_type, service_name, confidence.\n"
    "action_type must be one of: [check_metrics, check_health, read_logs, "
    "restart_service, run_db_query, rollback_deployment, declare_rca]"
)

def format_fn(examples):
    texts = []
    for i in range(len(examples["task_id"])):
        task_id = examples["task_id"][i]
        domain  = examples["domain"][i]
        steps   = examples["steps"][i]

        conversation = f"<|im_start|>system\n{SYSTEM}<|im_end|>\n"

        for j, step in enumerate(steps):
            obs         = step.get("observation", "")[:120]
            action_str  = step.get("action", "check_health:unknown")
            reward      = step.get("reward", 0.0)
            judge_score = step.get("judge_score", 0.5)

            # parse "action_type:service_name"
            if ":" in action_str:
                action_type, service_name = action_str.split(":", 1)
            else:
                action_type, service_name = action_str, "unknown"

            # confidence based on blended reward + judge score
            blended = (0.7 * reward) + (0.3 * (judge_score or 0.5))
            confidence = "high" if blended > 0.1 else "medium" if blended > 0.05 else "low"

            # reasoning — derived from observation signal
            obs_snippet = obs[:100].strip() if obs else "no observation"
            reasoning = (
                f"Observation shows {obs_snippet}. "
                f"{action_type} on {service_name} is the most relevant next step."
            )

            # Build user turn with context
            user_turn = (
                f"<|im_start|>user\n"
                f"[Task: {task_id} | Domain: {domain} | Step: {j+1}/{len(steps)}]\n"
                f"{obs}<|im_end|>\n"
            )
            assistant_turn = (
                f"<|im_start|>assistant\n"
                f"{json.dumps({'reasoning': reasoning, 'action_type': action_type, 'service_name': service_name, 'confidence': confidence})}"
                f"<|im_end|>\n"
            )

            conversation += user_turn + assistant_turn

        texts.append(conversation)
    return {"text": texts}

train_data = train_data.map(format_fn, batched=True, remove_columns=train_data.column_names)
eval_data  = eval_data.map(format_fn,  batched=True, remove_columns=eval_data.column_names)

print(f"\n{'='*60}")
print(f"Sample formatted conversation (first 500 chars):")
print(f"{'='*60}")
print(train_data[0]["text"][:500])
print(f"{'='*60}\n")

# ── Load model ────────────────────────────────────────────────────────────────
print("Loading model...")
model, tokenizer = FastModel.from_pretrained(
    model_name     = "unsloth/Qwen3.5-2B",
    max_seq_length = 256,
    load_in_4bit   = True,
    load_in_16bit  = False,
)

# Ensure tokenizer has proper pad token for batched training
if tokenizer.pad_token is None:
    tokenizer.pad_token = tokenizer.eos_token

print("Adding LoRA...")
model = FastModel.get_peft_model(
    model,
    r                          = 4,
    lora_alpha                 = 8,
    target_modules             = ["q_proj", "v_proj"],
    lora_dropout               = 0.0,
    bias                       = "none",
    use_gradient_checkpointing = "unsloth",
)

# ── Training args ─────────────────────────────────────────────────────────────
training_args = TrainingArguments(
    output_dir                  = "./sft_output",
    num_train_epochs            = 2,
    per_device_train_batch_size = 1,
    gradient_accumulation_steps = 8,
    learning_rate               = 5e-5,
    warmup_steps                = 50,
    lr_scheduler_type           = "cosine",
    weight_decay                = 0.01,
    logging_steps               = 10,
    eval_strategy               = "epoch",
    save_strategy               = "epoch",
    load_best_model_at_end      = True,
    metric_for_best_model       = "eval_loss",
    bf16                        = True,
    fp16                        = False,
    optim                       = "adamw_8bit",
    report_to                   = "none",
    dataloader_pin_memory       = False,
)

trainer = SFTTrainer(
    model              = model,
    tokenizer          = tokenizer,
    train_dataset      = train_data,
    eval_dataset       = eval_data,
    dataset_text_field = "text",
    max_seq_length     = 256,
    packing            = True,
    args               = training_args,
)

print(f"\nTraining config:")
print(f"  Train samples:  {len(train_data)}")
print(f"  Eval samples:   {len(eval_data)}")
print(f"  Epochs:         {training_args.num_train_epochs}")
print(f"  Batch (eff):    {training_args.per_device_train_batch_size * training_args.gradient_accumulation_steps}")
print(f"  Learning rate:  {training_args.learning_rate}")
print(f"  Max seq length: 256 (packed)")
print()

print("Starting training...")
trainer.train()

print("\nSaving model...")
model.save_pretrained("./sft_output/final")
tokenizer.save_pretrained("./sft_output/final")
print("DONE ✅")