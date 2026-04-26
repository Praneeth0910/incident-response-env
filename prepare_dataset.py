import json, sys
import shutil
sys.path.insert(0, '.')
from datasets import Dataset

ALLOWED = [
    "check_metrics",
    "check_health",
    "read_logs",
    "restart_service"
]

def clean(sample):
    if sample["action_type"] not in ALLOWED:
        return None
    
    return {
        "text": f"""You are an expert SRE agent.

Incident:
{sample['incident']}

Output:
{{"action_type": "{sample['action_type']}", "target": "{sample['service_name']}"}}"""
    }

# Load trajectories
trajs = [json.loads(l) for l in open("sft_data/trajectories.jsonl")]

# Keep only correct ones
correct_trajs = [t for t in trajs if t["rca_correct"]]
print(f"Using {len(correct_trajs)} correct trajectories")

data_list = []
for t in correct_trajs:
    for step in t["steps"]:
        action_str = step["action"]
        try:
            if action_str.startswith("{"):
                action_dict = json.loads(action_str)
                a_type = action_dict["action_type"]
                target = action_dict["service_name"]
            else:
                a_type, target = action_str.split(":", 1)
        except Exception:
            continue
            
        sample = {
            "incident": step["observation"],
            "action_type": a_type,
            "service_name": target
        }
        res = clean(sample)
        if res:
            data_list.append(res)

counter_example_sample = {
    "incident": "10 partitions on topic payments are under-replicated.\nOne broker (id: 3) is alive but not syncing.\nISR shows only 2 of 3 replicas.\nDisk I/O on broker-3 is at 98%.",
    "action_type": "check_metrics",
    "service_name": "broker-3"
}
ce_res = clean(counter_example_sample)
if ce_res:
    data_list.append(ce_res)

dataset = Dataset.from_list(data_list)

# 90/10 split
split = dataset.train_test_split(test_size=0.1, seed=42)

# Save as JSONL files
split["train"].to_json("sft_data/train_data.jsonl")
split["test"].to_json("sft_data/eval_data.jsonl")

shutil.rmtree("sft_data/hf_dataset", ignore_errors=True)

# Overwrite hf_dataset to retain DatasetDict with train/test splits
split.save_to_disk("sft_data/hf_dataset")

print(f"Dataset saved!")
print(f"Train: {len(split['train'])} | Eval: {len(split['test'])}")

# Preview
print("\nSample:")
print(split["train"][0])