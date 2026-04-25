"""
judge/llm_judge.py

Lightweight LLM judge implementing LLMJudge and AdversarialJudge. Uses the
`LLMClient` from `judge.llm_client`. For development the LLM client is a mock;
replace `LLMClient.chat_json` with an API-backed implementation for production.
"""

from __future__ import annotations
import json
import logging
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# Personas
PERSONAS = {
    "junior": "You are a senior SRE mentoring a junior engineer during an incident. Be encouraging.",
    "senior": "You are a staff SRE evaluating an engineer's incident response. Apply standard expectations.",
    "principal": "You are a principal SRE evaluating with high standards. Reward efficiency and evidence."
}

# Domain system prompts
CICD_JUDGE_SYSTEM = """You are a Principal SRE specialising in CI/CD security and pipeline reliability.
Return JSON only: {"score": <-1.0 to 1.0>, "feedback": "<1-2 sentences>", "missed_signal": "<what to check next or null>"}
"""

KAFKA_JUDGE_SYSTEM = """You are a Principal SRE who has operated Kafka at scale.
Return JSON only: {"score": <-1.0 to 1.0>, "feedback": "<1-2 sentences>", "missed_signal": "<str or null>"}
"""

# Phase detection sets
_CICD_OBSERVE   = ("check_pipeline_status","check_runner_status","check_action_integrity")
_CICD_GATHER    = ("read_job_logs","inspect_secret","read_audit_log")
_CICD_FIX       = ("rollback_workflow","rotate_secret","pin_action_to_sha","isolate_runner","restart_service")

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


class LLMJudge:
    def __init__(self, llm: LLMClient):
        self.llm = llm

    def evaluate(self, action: str, observation: str, task_context: dict, history: list, persona: str = "senior") -> tuple[float, str, str | None]:
        domain = task_context.get("domain", "cicd")
        system = CICD_JUDGE_SYSTEM if domain == "cicd" else KAFKA_JUDGE_SYSTEM

        history_summary = "\n".join(
            f"  Step {h.get('step', '?')}: {h.get('action','')} → reward {h.get('reward',0):.2f}"
            for h in (history or [])[-5:]
        ) or "  (first step)"

        user_prompt = f"""Evaluate this SRE action during a {domain.upper()} incident.\n\nINCIDENT:\n- Alert: {task_context.get('alert_message','')}\n- Root cause: {task_context.get('root_cause','')}\n- Correct fix: {task_context.get('resolution_steps',[''])[0]}\n\nAGENT ACTION:\n- Action: {action}\n- Observation: {str(observation)[:500]}\n\nRECENT HISTORY:\n{history_summary}\n"""

        try:
            result = self.llm.chat_json(system + "\n\n" + PERSONAS.get(persona, ""), user_prompt, temperature=0.2, max_tokens=256)
            score = max(-1.0, min(1.0, float(result.get("score", 0.0))))
            feedback = result.get("feedback", "")
            missed = result.get("missed_signal") if isinstance(result, dict) else None
            return score, feedback, missed
        except Exception as e:
            logger.error(f"LLMJudge error: {e}", exc_info=True)
            return 0.0, f"Judge error: {type(e).__name__}", None

    def score_rca(self, declared_component: str, task_context: dict, history: list) -> tuple[float, str]:
        correct = task_context.get("fault_component", "")
        evidence_actions = {h.get("action") for h in (history or [])}
        ideal = set(task_context.get("ideal_investigation_path", []))
        coverage = len(evidence_actions & ideal) / max(len(ideal), 1)

        if declared_component.lower() == correct.lower():
            base = 0.50 + coverage * 0.30
            feedback = f"Correct. Evidence coverage {coverage:.0%}."
            return min(0.999, base), feedback
        else:
            return -0.40, f"Wrong component '{declared_component}'. Correct: '{correct}'."


class AdversarialJudge(LLMJudge):
    _RED_HERRING_TERMS = {"unrelated","clean","no errors","green","healthy","passing","status operational","no recent changes","exit code 0"}

    def evaluate(self, action: str, observation: str, task_context: dict, history: list, persona: str = "senior") -> tuple[float, str, str | None]:
        base_score, feedback, missed = super().evaluate(action, observation, task_context, history, persona)

        domain = task_context.get("domain", "cicd")
        current_phase = _detect_phase(action, domain)

        # Phase-order enforcement
        if self._is_phase_order_correct(current_phase, domain, history):
            base_score += 0.15
        else:
            base_score -= 0.20

        # Red-herring awareness
        if self._touches_red_herring(str(observation), task_context.get("red_herrings", [])):
            if current_phase not in ("fix", "declare"):
                base_score -= 0.05

        base_score = max(-1.0, min(1.0, base_score))
        return base_score, feedback, missed

    def _is_phase_order_correct(self, current_phase: str, domain: str, history: list) -> bool:
        if not history:
            return current_phase == "observe"
        current_order = _PHASE_ORDER.get(current_phase, 0)
        past_phases = [_detect_phase(h.get("action",""), domain) for h in (history or [])]
        max_past = max((_PHASE_ORDER.get(p, 0) for p in past_phases), default=0)
        return current_order <= max_past + 1

    def _touches_red_herring(self, observation: str, red_herrings: list[str]) -> bool:
        obs_lower = observation.lower()
        for herring in red_herrings:
            if herring.lower() in obs_lower:
                return True
        # Also check generic terms
        for term in self._RED_HERRING_TERMS:
            if term in obs_lower:
                return True
        return False
