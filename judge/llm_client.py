"""judge/llm_client.py

Production-capable LLM client with optional OpenAI and Anthropic support.

Behaviour:
 - If `provider` is explicitly set or `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`
   environment variables are present, the client attempts to call the real API
   with a small retry/backoff strategy.
 - If no provider is configured or all remote calls fail, falls back to a
   deterministic heuristic mock (keeps existing offline behaviour).

The implementation keeps external imports local to the call-site so the
module can be imported in CI even if the provider libraries are missing.
"""

from __future__ import annotations
import os
import json
import time
import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, provider: Optional[str] = None, api_key: Optional[str] = None, max_retries: int = 3):
        self.provider = (provider or os.environ.get("LLM_PROVIDER") or None)
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        self.max_retries = int(max_retries)

    def _parse_json_snippet(self, text: str) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except Exception:
            # Try to extract a JSON object from the text blob
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    pass
        # Fallback conservative response
        return {"score": 0.0, "feedback": text[:240], "missed_signal": None}

    def _call_openai(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> dict:
        try:
            import openai
        except Exception as e:
            raise RuntimeError("openai library not available") from e

        openai.api_key = self.api_key
        model = os.environ.get("OPENAI_MODEL", "gpt-3.5-turbo")
        messages = [
            {"role": "system", "content": system_prompt or ""},
            {"role": "user", "content": user_prompt or ""},
        ]

        for attempt in range(self.max_retries):
            try:
                resp = openai.ChatCompletion.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                text = resp["choices"][0]["message"]["content"]
                return self._parse_json_snippet(text)
            except Exception as e:
                logger.warning("OpenAI attempt %d failed: %s", attempt + 1, e)
                if attempt + 1 >= self.max_retries:
                    raise
                time.sleep(2 ** attempt)

    def _call_anthropic(self, system_prompt: str, user_prompt: str, temperature: float, max_tokens: int) -> dict:
        # Anthropic expects a single prompt string. Use the classical /v1/complete endpoint.
        model = os.environ.get("ANTHROPIC_MODEL", "claude-2")
        url = f"https://api.anthropic.com/v1/complete"
        headers = {"x-api-key": self.api_key, "Content-Type": "application/json"}
        prompt = (system_prompt or "") + "\n\n" + (user_prompt or "")

        payload = {
            "model": model,
            "prompt": prompt,
            "max_tokens_to_sample": int(max_tokens),
            "temperature": float(temperature),
        }

        for attempt in range(self.max_retries):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=30)
                resp.raise_for_status()
                data = resp.json()
                # Anthropic returns text in `completion`
                text = data.get("completion") or data.get("completion", "")
                return self._parse_json_snippet(text)
            except Exception as e:
                logger.warning("Anthropic attempt %d failed: %s", attempt + 1, e)
                if attempt + 1 >= self.max_retries:
                    raise
                time.sleep(2 ** attempt)

    def chat_json(self, system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 256) -> dict:
        """Ask the configured LLM to return JSON. Falls back to a local heuristic.

        Returns a dict with at least `score` and `feedback` keys. May include
        `missed_signal` if the model returns it.
        """
        provider = self.provider
        if not provider:
            # Auto-detect from available API keys
            if os.environ.get("OPENAI_API_KEY"):
                provider = "openai"
            elif os.environ.get("ANTHROPIC_API_KEY"):
                provider = "anthropic"

        # Preferred providers first
        if provider == "openai":
            try:
                return self._call_openai(system_prompt, user_prompt, temperature, max_tokens)
            except Exception as e:
                logger.exception("OpenAI call failed, falling back: %s", e)
        elif provider == "anthropic":
            try:
                return self._call_anthropic(system_prompt, user_prompt, temperature, max_tokens)
            except Exception as e:
                logger.exception("Anthropic call failed, falling back: %s", e)

        # Legacy heuristic fallback (deterministic, suitable for offline tests)
        text = ((system_prompt or "") + "\n" + (user_prompt or "")).lower()
        if any(k in text for k in ("inspect_partition", "read_job_logs", "check_action_integrity", "read_audit_log", "check_runner_status")):
            return {"score": 0.6, "feedback": "Good evidence-gathering step.", "missed_signal": None}
        if "skip_offset" in text and "inspect_partition" not in text:
            return {"score": -0.4, "feedback": "Skipping offsets without inspection is risky.", "missed_signal": "inspect_partition"}
        return {"score": 0.0, "feedback": "Neutral judgement (mock LLM).", "missed_signal": None}
