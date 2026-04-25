#!/usr/bin/env python
"""Quick script to regenerate SFT dataset after Bug 2 fix."""

from training.generate_data import generate_sft_dataset

if __name__ == "__main__":
    print("Regenerating SFT dataset after ExpertAgent task_id fix...")
    generate_sft_dataset("sft_data")
    print("Done!")
