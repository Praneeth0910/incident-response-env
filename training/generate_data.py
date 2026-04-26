"""
training/generate_data.py

Generate high-quality SFT training data by running expert agent on all tasks.
Exports trajectories in a format suitable for supervised fine-tuning.
"""

from __future__ import annotations
import sys
import json
from pathlib import Path
from datetime import datetime

# Allow importing from the project root when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from environment import IncidentResponseEnv, TASKS
from training.expert_agent import run_expert_on_all_tasks


def generate_sft_dataset(output_dir: str = "sft_data", num_episodes_per_task: int = 1) -> None:
    """
    Generate SFT dataset by running expert on all tasks.
    Each trajectory becomes a training example.
    
    Args:
        output_dir: Directory to write JSON files
        num_episodes_per_task: Repeat each task N times (for robustness)
    """
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    env = IncidentResponseEnv()
    all_trajectories = []
    stats = {
        "total_episodes": 0,
        "successful_rcas": 0,
        "avg_score": 0.0,
        "avg_reward": 0.0,
        "by_domain": {},
    }
    
    from training.expert_agent import ExpertAgent
    
    # Run expert on each task
    print(f"Generating SFT dataset with {len(TASKS)} tasks x {num_episodes_per_task} episodes...")
    trajectories = []
    for task_id, task in TASKS.items():
        for episode_num in range(num_episodes_per_task):
            try:
                expert = ExpertAgent(task)
                traj = expert.run_episode(env, task_id, seed=episode_num)
                trajectories.append(traj)
                print(f"{task_id}: score={traj.final_score:.3f} reward={traj.total_reward:.3f} rca={traj.rca_correct}")
            except Exception as e:
                print(f"{task_id}: FAILED - {e}")
                
    all_trajectories.extend(trajectories)
    
    # Compute statistics
    if trajectories:
        stats["total_episodes"] = len(trajectories)
        stats["successful_rcas"] = sum(1 for t in trajectories if t.rca_correct)
        stats["avg_score"] = sum(t.final_score for t in trajectories) / len(trajectories)
        stats["avg_reward"] = sum(t.total_reward for t in trajectories) / len(trajectories)
        
        # Per-domain stats
        for domain_name in ["cicd", "kafka"]:
            domain_trajs = [t for t in trajectories if t.domain == domain_name]
            if domain_trajs:
                stats["by_domain"][domain_name] = {
                    "count": len(domain_trajs),
                    "avg_score": sum(t.final_score for t in domain_trajs) / len(domain_trajs),
                    "successful_rcas": sum(1 for t in domain_trajs if t.rca_correct),
                }
    
    # Write trajectories as JSONL
    trajectories_file = output_path / "trajectories.jsonl"
    with open(trajectories_file, "w") as f:
        for traj in all_trajectories:
            record = {
                "task_id": traj.task_id,
                "domain": traj.domain,
                "steps": traj.steps,
                "total_reward": traj.total_reward,
                "final_score": traj.final_score,
                "rca_correct": traj.rca_correct,
            }
            f.write(json.dumps(record) + "\n")
    
    # Write statistics
    stats_file = output_path / "generation_stats.json"
    stats["generated_at"] = datetime.utcnow().isoformat()
    stats["trajectories_file"] = str(trajectories_file)
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)
    
    print(f"\nDataset generation complete!")
    print(f"  Trajectories: {trajectories_file}")
    print(f"  Statistics: {stats_file}")
    print(f"  Total episodes: {stats['total_episodes']}")
    print(f"  Successful RCAs: {stats['successful_rcas']} ({100*stats['successful_rcas']/max(1,stats['total_episodes']):.1f}%)")
    print(f"  Avg score: {stats['avg_score']:.3f}")
    print(f"  Avg reward: {stats['avg_reward']:.3f}")


if __name__ == "__main__":
    generate_sft_dataset(output_dir="sft_data", num_episodes_per_task=19)
