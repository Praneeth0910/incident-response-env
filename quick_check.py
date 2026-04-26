# quick_check.py — verify the SFT dataset is ready for training
from datasets import load_dataset

dataset = load_dataset("json", data_files="sft_data/trajectories.jsonl")
print(dataset)
print(f"\nTotal rows: {len(dataset['train'])}")
print(f"\nFirst example:")
print(dataset["train"][0])
print(f"\nColumns: {dataset['train'].column_names}")

# Verify minimum quality
rca_ok = sum(1 for x in dataset["train"] if x["rca_correct"])
print(f"\nRCA correct: {rca_ok}/{len(dataset['train'])}")
unique_tasks = set(x["task_id"] for x in dataset["train"])
print(f"Unique tasks: {len(unique_tasks)}")