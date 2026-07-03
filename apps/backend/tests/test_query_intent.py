"""
Unit tests for app.rag.query_intent — fully mocked Gemini, no network.

Run:
  cd apps/backend
  pytest tests/test_query_intent.py -v

Coverage:
  - QueryIntent schema: scope normalization, ISO date validation, confidence clamp
  - classify_query_intent: happy path / invalid JSON / API error / empty input
                           / topic fallback / date injection via `now`
  - build_meeting_sql_filters: date-only / confidential gating by scope / none
  - passthrough_intent
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from app.rag.query_intent import (
    DEFAULT_SCOPE,
    QUERY_SCOPES,
    TAIPEI_TZ,
    QueryIntent,
    build_meeting_sql_filters,
    classify_query_intent,
    passthrough_intent,
)


def _mock_client(payload_or_text):
    """Build a MagicMock google.genai client returning the given JSON payload."""
    text = payload_or_text if isinstance(payload_or_text, str) else json.dumps(payload_or_text)
    client = MagicMock()
    resp = MagicMock()
    resp.text = text
    client.models.generate_content.return_value = resp
    return client


# ============================================
# QueryIntent schema
# ============================================
class TestQueryIntentSchema:
    def test_unknown_scope_normalizes_to_default(self):
        qi = QueryIntent(scope="banana", topic="x")
        assert qi.scope == DEFAULT_SCOPE

    def test_known_scopes_pass_through(self):
        for s in QUERY_SCOPES:
            assert QueryIntent(scope=s, topic="x").scope == s

    def test_invalid_date_becomes_none(self):
        qi = QueryIntent(topic="x", date_after="2026/06/01", date_before="not-a-date")
        assert qi.date_after is None
        assert qi.date_before is None

    def test_valid_date_kept(self):
        qi = QueryIntent(topic="x", date_after="2026-06-01")
        assert qi.date_after == "2026-06-01"

    def test_confidence_bounds_enforced(self):
        with pytest.raises(Exception):
            QueryIntent(topic="x", confidence=1.5)

    def test_topic_required_nonempty(self):
        with pytest.raises(Exception):
            QueryIntent(topic="")


# ============================================
# passthrough_intent
# ============================================
class TestPassthrough:
    def test_uses_question_as_topic(self):
        qi = passthrough_intent("RAG 架構討論")
        assert qi.topic == "RAG 架構討論"
        assert qi.scope == DEFAULT_SCOPE
        assert qi.confidence == 0.0

    def test_empty_question_safe(self):
        qi = passthrough_intent("   ")
        assert qi.topic  # non-empty placeholder


# ============================================
# classify_query_intent
# ============================================
class TestClassifyQueryIntent:
    def test_happy_path(self):
        client = _mock_client({
            "scope": "cross_meeting",
            "topic": "RAG 架構的共識與分歧",
            "date_after": None,
            "date_before": None,
            "speaker_hints": ["晴威"],
            "meeting_hints": ["奇美廠"],
            "include_confidential": False,
            "confidence": 0.9,
        })
        qi = classify_query_intent("大家對 RAG 架構看法？", client)
        assert qi.scope == "cross_meeting"
        assert qi.topic == "RAG 架構的共識與分歧"
        assert qi.speaker_hints == ["晴威"]
        assert qi.meeting_hints == ["奇美廠"]
        assert qi.confidence == 0.9

    def test_empty_input_returns_passthrough_without_calling_llm(self):
        client = _mock_client({"topic": "should not be used"})
        qi = classify_query_intent("   ", client)
        client.models.generate_content.assert_not_called()
        assert qi.confidence == 0.0

    def test_invalid_json_falls_back(self):
        client = _mock_client("this is not json{{{")
        qi = classify_query_intent("某個問題", client)
        assert qi.topic == "某個問題"
        assert qi.confidence == 0.0

    def test_api_error_falls_back(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("boom")
        qi = classify_query_intent("另一個問題", client)
        assert qi.topic == "另一個問題"
        assert qi.confidence == 0.0

    def test_missing_topic_uses_question(self):
        client = _mock_client({"scope": "unknown", "confidence": 0.3})
        qi = classify_query_intent("我的原始問題", client)
        assert qi.topic == "我的原始問題"

    def test_today_is_injected_into_prompt(self):
        client = _mock_client({"topic": "x"})
        fixed_now = datetime(2026, 7, 3, tzinfo=TAIPEI_TZ)
        classify_query_intent("問題", client, now=fixed_now)
        sent_prompt = client.models.generate_content.call_args.kwargs["contents"]
        assert "2026-07-03" in sent_prompt

    def test_confidence_clamped(self):
        client = _mock_client({"topic": "x", "confidence": 5})
        qi = classify_query_intent("q", client)
        assert qi.confidence == 1.0


# ============================================
# build_meeting_sql_filters
# ============================================
class TestBuildSqlFilters:
    def test_none_intent_yields_empty(self):
        frag, params = build_meeting_sql_filters(None)
        assert frag == ""
        assert params == {}

    def test_no_filters_yields_empty(self):
        qi = QueryIntent(scope="single_meeting", topic="x")
        frag, params = build_meeting_sql_filters(qi)
        assert frag == ""
        assert params == {}

    def test_date_after_only(self):
        qi = QueryIntent(scope="single_meeting", topic="x", date_after="2026-06-01")
        frag, params = build_meeting_sql_filters(qi)
        assert "created_at >= :q_date_after" in frag
        assert params["q_date_after"] == "2026-06-01"
        assert frag.startswith(" AND ")

    def test_date_range_both(self):
        qi = QueryIntent(scope="single_meeting", topic="x",
                         date_after="2026-06-01", date_before="2026-07-01")
        frag, params = build_meeting_sql_filters(qi)
        assert params == {"q_date_after": "2026-06-01", "q_date_before": "2026-07-01"}
        assert "created_at <" in frag

    def test_confidential_excluded_for_cross_meeting(self):
        qi = QueryIntent(scope="cross_meeting", topic="x", include_confidential=False)
        frag, _ = build_meeting_sql_filters(qi)
        assert "is_confidential IS NOT TRUE" in frag

    def test_confidential_kept_when_included(self):
        qi = QueryIntent(scope="cross_meeting", topic="x", include_confidential=True)
        frag, _ = build_meeting_sql_filters(qi)
        assert "is_confidential" not in frag

    def test_confidential_not_applied_for_single_meeting(self):
        qi = QueryIntent(scope="single_meeting", topic="x", include_confidential=False)
        frag, _ = build_meeting_sql_filters(qi)
        assert "is_confidential" not in frag

    def test_custom_alias(self):
        qi = QueryIntent(scope="cross_meeting", topic="x", date_after="2026-06-01")
        frag, _ = build_meeting_sql_filters(qi, meeting_alias="mtg")
        assert "mtg.created_at" in frag
