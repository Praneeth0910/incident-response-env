import os
from judge.llm_client import LLMClient


def test_chat_json_fallback_evidence_gathering():
    client = LLMClient(provider=None)
    res = client.chat_json("system", "Please inspect_partition now", temperature=0.0, max_tokens=64)
    assert isinstance(res, dict)
    assert "score" in res and "feedback" in res
    assert res["score"] > 0


def test_chat_json_fallback_skip_offset_penalty():
    client = LLMClient(provider=None)
    # ensure we don't mention inspect_partition so the skip_offset rule triggers
    res = client.chat_json("system", "Agent will skip_offset now without prior inspection", temperature=0.0, max_tokens=64)
    assert isinstance(res, dict)
    assert res.get("score") < 0
    assert res.get("missed_signal") is not None


def test_provider_failure_falls_back():
    # If provider set to openai but library/key not present, client should fallback
    client = LLMClient(provider="openai")
    res = client.chat_json("system", "read_job_logs show error", temperature=0.0, max_tokens=64)
    assert isinstance(res, dict)
    assert "feedback" in res
