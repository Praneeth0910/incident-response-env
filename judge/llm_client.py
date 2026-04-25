"""
judge/llm_client.py

Minimal LLM client used by the judge. This implementation provides a lightweight
mock fallback when no external LLM provider is configured. It is intentionally
simple so the repo can run offline during development and testing.
"""

from __future__ import annotations
import os
import json
import logging

logger = logging.getLogger(__name__)


class LLMClient:
    """Lightweight LLM client with a simple mock fallback.

    Production: extend this class to call OpenAI/Anthropic APIs.
    Development: by default this returns deterministic heuristic JSON.
    """

    def __init__(self, provider: str | None = None, api_key: str | None = None):
        self.provider = provider or os.environ.get("LLM_PROVIDER")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 256) -> dict:
        """Return a JSON-like dict for the judge.

        This mock examines the prompts for key diagnostics and returns a simple
        score+feedback pair. Replace with a real API call in production.
        """
        text = (system_prompt or "") + "\n" + (user_prompt or "")
        text = text.lower()

        # Heuristic rules (conservative): reward evidence-gathering actions
        if any(k in text for k in ("inspect_partition","read_job_logs","check_action_integrity","read_audit_log","check_runner_status")):
            return {"score": 0.6, "feedback": "Good evidence-gathering step.", "missed_signal": None}

        # Penalize skip_offset without inspection
        if "skip_offset" in text and "inspect_partition" not in text:
            return {"score": -0.4, "feedback": "Skipping offsets without inspection is risky.", "missed_signal": "inspect_partition"}

        # Neutral default
        return {"score": 0.0, "feedback": "Neutral judgement (mock LLM).", "missed_signal": None}
