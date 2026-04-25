from judge.llm_client import LLMClient
from judge.llm_judge import AdversarialJudge


def test_judge_returns_triple():
    llm = LLMClient(provider=None)
    judge = AdversarialJudge(llm)
    task_ctx = {
        "domain": "cicd",
        "alert_message": "ALERT X",
        "root_cause": "something",
        "resolution_steps": ["step1"],
        "fault_type": "cpu_spike",
        "fault_component": "auth-service",
        "red_herrings": [],
    }
    res = judge.evaluate("read_job_logs", "Some logs showing error", task_ctx, [])
    assert isinstance(res, tuple)
    assert len(res) == 3
    score, feedback, missed = res
    assert isinstance(score, float)
    assert isinstance(feedback, str)


def test_adversarial_penalty_for_wrong_phase():
    llm = LLMClient(provider=None)
    judge = AdversarialJudge(llm)
    task_ctx = {"domain": "cicd", "alert_message": "x", "resolution_steps": ["step1"],
                "fault_type": "cpu_spike", "fault_component": "auth-service", "red_herrings": []}
    # First action should be observe; simulate a 'restart_service' as first action
    score_fix, feedback_fix, missed_fix = judge.evaluate("restart_service", "Attempted a restart", task_ctx, [])
    # Because no history, restart_service should be penalized (lower than gather action)
    assert score_fix <= 0.5
