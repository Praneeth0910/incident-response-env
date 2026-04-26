import sys
import json
sys.path.insert(0, '.')
from training.generate_data import generate_sft_dataset

generate_sft_dataset(
    output_dir="sft_data",
    num_episodes_per_task=30
)

noisy_variants = [
    {
        "rca_correct": True,
        "steps": [
            {
                "observation": "Incident:\n10 partitions on topic payments are under-replicated.\nOne broker (id: 3) is alive but not syncing.\nISR shows only 2 of 3 replicas.\nDisk I/O on broker-3 is at 98%.\n[DEBUG] cache miss spike observed on broker-3 (ignore — known flap).",
                "action": '{"reasoning": "Disk I/O at 98% is the primary signal — restart would cause data loss, must diagnose first.", "action_type": "check_metrics", "service_name": "broker-3", "confidence": "high"}'
            }
        ]
    },
    {
        "rca_correct": True,
        "steps": [
            {
                "observation": "Incident:\nConsumer group orders-processor lag is 2.1M.\nCPU on consumer host is at 23% (normal range).\n[DEBUG] cache miss spike observed — unrelated background process.\nThread count is within limits.",
                "action": '{"reasoning": "Lag is high but CPU and threads are normal; need to inspect logs for hidden anomalies before taking destructive action.", "action_type": "read_logs", "service_name": "orders-processor", "confidence": "high"}'
            }
        ]
    },
    {
        "rca_correct": True,
        "steps": [
            {
                "observation": "Incident:\nAPI gateway returning 502 errors at 4% rate.\nDownstream payment-service health: DEGRADED.\n[DEBUG] cache miss spike observed on gateway (known issue, filed as NON-CRITICAL).\nDB query latency: 850ms (elevated).",
                "action": '{"reasoning": "Gateway errors likely stem from degraded downstream payment-service; checking health is the most logical next step.", "action_type": "check_health", "service_name": "payment-service", "confidence": "high"}'
            }
        ]
    }
]

with open("sft_data/trajectories.jsonl", "a", encoding="utf-8") as f:
    for variant in noisy_variants:
        f.write(json.dumps(variant) + "\n")