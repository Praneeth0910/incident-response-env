from reward import EvidenceTracker, compute_step_reward, compute_rca_reward


def test_evidence_tracker_counts():
    ev = EvidenceTracker()
    ev.logs_read = True
    ev.secrets_inspected = True
    assert ev.evidence_count_cicd() == 2


def test_compute_step_reward_cicd_read_logs():
    task = {"domain": "cicd", "fault_type": "cpu_spike", "max_steps": 10}
    ev = EvidenceTracker()
    r = compute_step_reward("read_job_logs", task, step_count=1, actions_taken=[], evidence=ev)
    assert isinstance(r, float)
    assert r > 0
    assert ev.logs_read


def test_compute_step_reward_redundant_penalty():
    task = {"domain": "cicd", "max_steps": 10}
    ev = EvidenceTracker()
    r = compute_step_reward("read_job_logs", task, step_count=6, actions_taken=["read_job_logs", "read_job_logs"], evidence=ev)
    assert r == -0.2


def test_compute_rca_reward_correct():
    task = {"domain": "cicd", "fault_component": "auth-service", "max_steps": 10}
    ev = EvidenceTracker()
    ev.logs_read = True
    ev.action_integrity_checked = True
    r = compute_rca_reward("auth-service", task, step_count=3, evidence=ev)
    assert r > 0.5


def test_kafka_skip_offset_penalty():
    task = {"domain": "kafka", "fault_type": "partition_corrupt", "max_steps": 10}
    ev = EvidenceTracker()
    r = compute_step_reward("skip_offset", task, step_count=1, actions_taken=[], evidence=ev)
    assert r < 0
