"""
simulators/kafka_simulator.py

Kafka cluster state machine for SRE incident training.
Models incidents documented by PagerDuty (Aug 2025), Factor House (Feb 2026),
ING, Confluent, and Lenses.io.

Observability traps are first-class: aggregate metrics intentionally look healthy
for zombie consumer, poison pill, and silent lag scenarios.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class PartitionState:
    partition_id: int
    leader_broker: int
    isr_replicas: list[int]
    leo: int                          # log end offset
    hw: int                           # high watermark
    consumer_offsets: dict[str, int]  # group_id → committed offset
    lag: dict[str, int]               # group_id → lag
    stuck_at_offset: int | None = None
    stuck_message_schema_error: str | None = None

@dataclass
class TopicState:
    name: str
    partition_count: int
    replication_factor: int
    partitions: dict[int, PartitionState]
    message_rate_per_sec: int
    retention_ms: int
    cleanup_policy: str

@dataclass
class ConsumerMemberState:
    member_id: str
    client_id: str
    host: str
    assigned_partitions: dict[str, list[int]]
    last_heartbeat_seconds_ago: int
    is_processing: bool
    crash_count_last_hour: int

@dataclass
class ConsumerGroupState:
    group_id: str
    status: Literal["stable","rebalancing","dead","empty"]
    members: list[ConsumerMemberState]
    total_lag: int
    last_commit_seconds_ago: int
    committed_offsets: dict[str, dict[int, int]]

@dataclass
class BrokerState:
    broker_id: int
    status: Literal["leader","follower","offline","recovering"]
    heap_used_mb: int
    heap_max_mb: int
    gc_pause_ms: int
    isr_count: int
    log_segment_size_gb: float
    network_threads_active: int
    network_threads_max: int
    log_lines: list[str]             # recent broker.log lines

@dataclass
class SchemaRegistryState:
    status: Literal["healthy","degraded","unreachable"]
    schema_versions: dict[str, int]
    compatibility_mode: str
    recent_failures: list[str]
    deleted_schemas: list[str] = field(default_factory=list)

@dataclass
class ClusterConfig:
    kafka_version: str
    kraft_mode: bool
    zookeeper_status: str | None
    topic_count: int = 0


# ── KafkaSimulator ────────────────────────────────────────────────────────────

class KafkaSimulator:
    """
    Kafka cluster state machine.

    Observability traps are by design:
    - get_cluster_metrics() total_consumer_lag is an AVERAGE — hides stuck partitions
    - check_consumer_lag() without per_partition=True masks stuck partitions
    - Broker health check returns 200 even while OOM-killing
    """

    def __init__(self):
        self.brokers: dict[int, BrokerState] = {}
        self.topics: dict[str, TopicState] = {}
        self.consumer_groups: dict[str, ConsumerGroupState] = {}
        self.schema_registry = SchemaRegistryState("healthy",{},
            "BACKWARD",[])
        self.cluster_config = ClusterConfig("3.7.0", True, None)
        self._task: dict = {}

    # ── Fault injection ───────────────────────────────────────────────────────

    def generate_incident_state(self, task: dict) -> None:
        self._task = task
        fault = task.get("fault_type","")
        self._seed_healthy_baseline()
        injectors = {
            "poison_pill":          self._inject_poison_pill,
            "zombie_consumer":      self._inject_zombie_consumer,
            "broker_oom_cascade":   self._inject_broker_oom,
            "isr_churn":            self._inject_isr_churn,
            "rebalance_storm":      self._inject_rebalance_storm,
            "schema_desync":        self._inject_schema_desync,
            "retry_amplification":  self._inject_retry_amplification,
            "silent_lag":           self._inject_silent_lag,
            "topic_sprawl":         self._inject_topic_sprawl,
            "producer_epoch":       self._inject_producer_epoch,
        }
        injectors.get(fault, lambda: None)()

    def _seed_healthy_baseline(self) -> None:
        for bid in [0, 1, 2]:
            self.brokers[bid] = BrokerState(
                bid, "leader" if bid == 0 else "follower",
                heap_used_mb=2048, heap_max_mb=4096, gc_pause_ms=120,
                isr_count=3, log_segment_size_gb=1.0,
                network_threads_active=8, network_threads_max=8,
                log_lines=["[INFO] Broker started successfully."]
            )
        for topic_name, partitions in [("orders", 8), ("payments", 4),
                                        ("inventory-events", 6), ("checkout-events", 4),
                                        ("email-dispatch", 8)]:
            parts = {}
            for pid in range(partitions):
                leo = random.randint(9_000_000, 10_000_000)
                parts[pid] = PartitionState(
                    pid, 0, [0, 1, 2], leo, leo - 100,
                    {"order-fulfillment": leo - random.randint(50, 200),
                     "email-dispatch": leo - random.randint(50, 200)},
                    {"order-fulfillment": random.randint(50, 200),
                     "email-dispatch": random.randint(50, 200)}
                )
            self.topics[topic_name] = TopicState(topic_name, partitions, 3,
                parts, 1200, 604_800_000, "delete")
        
        self.consumer_groups = {
            "order-fulfillment": ConsumerGroupState(
                "order-fulfillment","stable",
                [ConsumerMemberState("member-1", "order-svc-1", "10.0.1.10",
                    {"orders": [0, 1, 2]}, 2, True, 0)],
                sum(p.lag.get("order-fulfillment", 0) for p in self.topics["orders"].partitions.values()),
                5, {}),
            "email-dispatch": ConsumerGroupState(
                "email-dispatch","stable",
                [ConsumerMemberState("member-2", "email-svc-1", "10.0.1.20",
                    {"email-dispatch": [0, 1, 2]}, 3, True, 0)],
                sum(p.lag.get("email-dispatch", 0) for p in self.topics["email-dispatch"].partitions.values()),
                4, {}),
        }
        self.schema_registry = SchemaRegistryState(
            "healthy",{"orders-value":8,"payments-value":5,"inventory-events-value":7},
            "BACKWARD",[])
        self.cluster_config = ClusterConfig("3.7.0",True,None,topic_count=47)

    def _inject_poison_pill(self) -> None:
        stuck_offset = 8_847_293
        topic = self.topics["orders"]
        # Partitions 0,1,3..7 look fine; partition 2 is stuck
        for pid, part in topic.partitions.items():
            if pid == 2:
                part.stuck_at_offset = stuck_offset
                part.stuck_message_schema_error = "Avro schema validation failed: unknown field in message"
                part.lag["order-fulfillment"] = part.leo - stuck_offset
            else:
                part.lag["order-fulfillment"] = random.randint(5, 50)
        group = self.consumer_groups["order-fulfillment"]
        group.total_lag = sum(p.lag.get("order-fulfillment",0)
                              for p in topic.partitions.values())
        # Members heartbeating but member assigned to partition 2 is looping
        for m in group.members:
            if 2 in m.assigned_partitions.get("orders",[]):
                m.crash_count_last_hour = 47
                m.is_processing = False

    def _inject_zombie_consumer(self) -> None:
        group = self.consumer_groups["order-fulfillment"]
        group.total_lag = 2_100_000
        group.last_commit_seconds_ago = 7200
        for m in group.members:
            m.is_processing = False
            m.last_heartbeat_seconds_ago = 5   # heartbeat sends, but no commits

    def _inject_broker_oom(self) -> None:
        b = self.brokers[0]
        b.heap_used_mb = b.heap_max_mb - 128
        b.gc_pause_ms = 2800
        b.status = "offline"
        b.log_lines = [
            "[WARN] GC overhead limit exceeded. Heap at 98%.",
            "[ERROR] java.lang.OutOfMemoryError: Java heap space",
            "[ERROR] Broker 0 shutting down due to unrecoverable error.",
            "[INFO] Leadership moving to broker 1 for all partitions.",
        ]
        # 12 underreplicated partitions
        for topic in list(self.topics.values())[:3]:
            for pid in list(topic.partitions.keys())[:4]:
                topic.partitions[pid].isr_replicas = [1, 2]  # broker 0 gone

    def _inject_isr_churn(self) -> None:
        b = self.brokers[2]
        b.status = "recovering"
        b.log_lines = [
            "[INFO] Broker 2 restarted, beginning log recovery.",
            "[INFO] Replica fetch lag: 12,847,291 messages behind leader.",
            "[INFO] ISR shrink: partition orders-5 ISR=[0,1] (broker 2 removed).",
            "[INFO] Estimated time to rejoin ISR: 18 minutes at current fetch rate.",
        ]
        for topic in self.topics.values():
            for pid, part in topic.partitions.items():
                part.isr_replicas = [0, 1]
                part.hw = part.leo - 500

    def _inject_rebalance_storm(self) -> None:
        group = self.consumer_groups["order-fulfillment"]
        group.status = "rebalancing"
        group.total_lag = 0  # no processing happening
        group.last_commit_seconds_ago = 30
        for m in group.members:
            m.last_heartbeat_seconds_ago = random.randint(1, 3)
            m.is_processing = False
            m.crash_count_last_hour = 0

    def _inject_schema_desync(self) -> None:
        self.schema_registry.recent_failures.append(
            "Schema ID 6 not found for subject 'inventory-events-value'. "
            "Producer at 10.0.2.44 using deleted schema version.")
        self.schema_registry.deleted_schemas.append("inventory-events-value:v6")
        group = self.consumer_groups.get("email-dispatch")
        if group:
            group.total_lag = 450_000
            group.last_commit_seconds_ago = 3600

    def _inject_retry_amplification(self) -> None:
        b = self.brokers[0]
        b.network_threads_active = b.network_threads_max
        b.log_lines = [
            "[WARN] Request handler thread pool exhausted.",
            "[WARN] Dropping incoming connections: queue full (847 pending).",
            "[ERROR] ProduceRequest timeout for topic 'orders' partition 0.",
            "[ERROR] Network thread saturation — retry storm in progress.",
        ]

    def _inject_silent_lag(self) -> None:
        """The 'context gap' from Factor House Feb 2026."""
        group = self.consumer_groups["email-dispatch"]
        topic = self.topics["email-dispatch"]
        # Partition 4 stuck; others fine
        for pid, part in topic.partitions.items():
            if pid == 4:
                part.stuck_at_offset = 2_847_291
                part.stuck_message_schema_error = "Consumer stuck at offset"
                part.lag["email-dispatch"] = 2_100_000
            else:
                part.lag["email-dispatch"] = random.randint(50, 400)
        # Average lag looks fine: (2_100_000 + 7*200) / 8 ≈ 262_675
        # But that's still a high average — set up to be masked
        group.total_lag = sum(p.lag.get("email-dispatch",0)
                              for p in topic.partitions.values())

    def _inject_topic_sprawl(self) -> None:
        self.cluster_config.topic_count = 12_047
        for b in self.brokers.values():
            b.log_lines = [
                "[WARN] Metadata load time: 847s on last broker restart.",
                "[WARN] Slow startup: 12,047 topics × 12 partitions = 144,564 logs to recover.",
                "[INFO] Consumer group join timeout: metadata not yet loaded.",
            ]

    def _inject_producer_epoch(self) -> None:
        topic = self.topics["payments"]
        for pid, part in list(topic.partitions.items())[:2]:
            # Duplicate sequence numbers at these offsets
            part.stuck_at_offset = None
            part.stuck_message_schema_error = (
                "Producer epoch reset detected at offset 4_821_000. "
                "Idempotency guard bypassed: duplicate transaction_id entries present.")
        self.brokers[0].log_lines = [
            "[INFO] Producer epoch reset for client payment-service-prod-1.",
            "[WARN] Sequence number conflict: epoch 0 reused. Accepting as new producer.",
            "[WARN] Idempotency violation window: 14:47:23 → 14:51:07 UTC.",
        ]

    # ── Investigation actions ─────────────────────────────────────────────────

    def get_cluster_metrics(self) -> dict:
        online = sum(1 for b in self.brokers.values() if b.status != "offline")
        underreplicated = sum(
            1 for t in self.topics.values()
            for p in t.partitions.values()
            if len(p.isr_replicas) < t.replication_factor
        )
        # Return AVERAGE lag — this is the observability trap
        total_lag = sum(g.total_lag for g in self.consumer_groups.values())
        group_count = len(self.consumer_groups) or 1
        return {
            "broker_count": len(self.brokers),
            "online_brokers": online,
            "underreplicated_partitions": underreplicated,
            "total_consumer_lag": total_lag,
            "avg_lag_per_group": total_lag // group_count,  # ← intentionally misleading aggregate
            "topic_count": self.cluster_config.topic_count,
            "kafka_version": self.cluster_config.kafka_version,
            "note": "Aggregate lag may hide per-partition skew. Use check_consumer_lag() for detail.",
        }

    def check_consumer_lag(self, group_id: str | None = None,
                           topic: str | None = None, per_partition: bool = False) -> dict:
        if group_id:
            g = self.consumer_groups.get(group_id)
            if not g:
                return {"error": f"Group '{group_id}' not found"}
            t = self.topics.get(topic) if topic else None
            result = {"group_id": group_id, "status": g.status,
                      "total_lag": g.total_lag,
                      "last_commit_seconds_ago": g.last_commit_seconds_ago}
            if t and per_partition:
                result["per_partition_lag"] = {
                    pid: p.lag.get(group_id, 0) 
                    for pid, p in t.partitions.items()
                }
            return result
        return {gid: {"total_lag": g.total_lag, "status": g.status}
                for gid, g in self.consumer_groups.items()}

    def inspect_partition(self, topic: str, partition_id: int) -> dict:
        t = self.topics.get(topic)
        if not t:
            return {"error": f"Topic '{topic}' not found"}
        p = t.partitions.get(partition_id)
        if p is None:
            return {"error": f"Partition {partition_id} not found"}
        result = p.__dict__.copy()
        if p.stuck_at_offset:
            result["diagnosis_hint"] = (
                f"Consumer committed offset has not advanced past {p.stuck_at_offset}. "
                f"Message at this offset may be unprocessable.")
        return result

    def check_isr_status(self, topic: str | None = None) -> dict:
        topics = {topic: self.topics[topic]} if topic and topic in self.topics else self.topics
        result = {}
        for tname, t in topics.items():
            underrep = [pid for pid, p in t.partitions.items()
                        if len(p.isr_replicas) < t.replication_factor]
            result[tname] = {
                "replication_factor": t.replication_factor,
                "underreplicated_partitions": underrep,
            }
        return result

    def describe_consumer_group(self, group_id: str) -> dict:
        g = self.consumer_groups.get(group_id)
        if not g:
            return {"error": f"Group '{group_id}' not found"}
        return g.__dict__

    def read_broker_logs(self, broker_id: int | None = None, lines: int = 20) -> str:
        brokers = [self.brokers[broker_id]] if broker_id is not None else list(self.brokers.values())
        out = []
        for b in brokers:
            out.append(f"=== Broker {b.broker_id} [{b.status}] heap={b.heap_used_mb}/{b.heap_max_mb}MB ===")
            out.extend(b.log_lines[-lines:])
        return "\n".join(out)

    def read_consumer_logs(self, group_id: str, lines: int = 30) -> str:
        g = self.consumer_groups.get(group_id)
        if not g:
            return f"Group '{group_id}' not found."
        fault = self._task.get("fault_type","")
        log_generators = {
            "poison_pill": [
                f"[{group_id}] ConsumerRecord fetched: topic=orders partition=2 offset=8847293",
                f"[{group_id}] Deserialization failed: Avro schema validation error",
                f"[{group_id}] Message decode failed. No handler. Retrying.",
                f"[{group_id}] Heartbeat sent. No commit progress.",
            ],
            "zombie_consumer": [
                f"[{group_id}] Consumer group rebalance initiated.",
                f"[{group_id}] Rebalance completed. Assigned 2 partitions.",
                f"[{group_id}] Heartbeat sent. Processing: false. No offset advances in 120 minutes.",
                f"[{group_id}] Still alive but lag growing: {g.total_lag} messages.",
            ],
        }
        lines_out = log_generators.get(fault, [f"[{group_id}] Processing normally."])
        return "\n".join(lines_out[:lines])

    def check_schema_registry(self, subject: str | None = None) -> dict:
        if subject:
            version = self.schema_registry.schema_versions.get(subject)
            return {
                "subject": subject,
                "version": version,
                "status": "healthy" if version else "schema_not_found",
            }
        return self.schema_registry.__dict__

    def skip_offset(self, group_id: str, topic: str, partition: int,
                    to_offset: int) -> dict:
        g = self.consumer_groups.get(group_id)
        if not g:
            return {"success": False, "message": "Group not found"}
        if g.status != "empty":
            return {"success": False,
                    "message": "Cannot skip offset: group is not empty. Reset group first."}
        t = self.topics.get(topic)
        if t and partition in t.partitions:
            p = t.partitions[partition]
            p.consumer_offsets[group_id] = to_offset
            p.lag[group_id] = p.leo - to_offset
            return {"success": True, "message": f"Offset advanced to {to_offset}"}
        return {"success": False, "message": "Topic/partition not found"}

    def restart_consumer_group(self, group_id: str) -> dict:
        g = self.consumer_groups.get(group_id)
        if not g:
            return {"success": False}
        before = len(g.members)
        for m in g.members:
            m.is_processing = True
            m.last_heartbeat_seconds_ago = 1
        g.status = "stable"
        g.last_commit_seconds_ago = 1
        return {"members_before": before, "members_after": before,
                "rebalance_triggered": True, "new_status": "stable"}

    def increase_broker_heap(self, broker_id: int, new_heap_mb: int) -> dict:
        b = self.brokers.get(broker_id)
        if not b:
            return {"success": False}
        b.heap_max_mb = new_heap_mb
        return {"success": True, "restart_required": True,
                "estimated_downtime_seconds": 45, "new_heap_mb": new_heap_mb}

    def check_dead_letter_queue(self, topic: str) -> dict:
        dlq_topic = f"{topic}.dlq"
        has_dlq = dlq_topic in self.topics
        return {
            "dlq_topic": dlq_topic,
            "exists": has_dlq,
            "message_count": 0 if not has_dlq else random.randint(10, 1000),
            "recommendation": "Configure DLQ to avoid infinite retry loops" if not has_dlq else "DLQ active.",
        }
