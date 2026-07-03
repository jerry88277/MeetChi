"""
Unit tests for app.services.rag_greeting

Run:
  cd apps/backend
  pytest tests/test_rag_greeting.py -v

Strategy: mock SQLAlchemy session; never touch real DB.
All functions in rag_greeting are deterministic — pure unit tests.
"""

from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.rag_greeting import (
    resolve_display_name,
    get_accessible_meeting_stats,
    get_recent_meetings_for_greeting,
    get_pending_action_count,
    extract_top_topics,
    build_greeting_text,
    build_suggested_questions,
    get_last_meeting_summary,
    build_greeting_payload,
)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _db_returning(rows):
    """Return a mock Session whose execute().fetchone() / fetchall() returns rows."""
    mock_result = MagicMock()
    if isinstance(rows, list):
        mock_result.fetchall.return_value = rows
        mock_result.fetchone.return_value = rows[0] if rows else None
    else:
        mock_result.fetchone.return_value = rows
        mock_result.fetchall.return_value = [rows] if rows is not None else []
    db = MagicMock()
    db.execute.return_value = mock_result
    return db


def _row(*values):
    """Minimal row tuple."""
    return tuple(values)


SAMPLE_SUMMARY_JSON = json.dumps({
    "chapters": [
        {"title": "AI 投資 ROI"},
        {"title": "供應鏈優化"},
    ],
    "speaker_contributions": [
        {"speaker": "Alice", "main_topics": ["流程改善", "AI 投資 ROI"]},
    ],
    "action_items": ["確認 AI 預算", "更新供應鏈系統"],
    "next_steps": [
        {"action": "下季 KPI 設定", "owner": "Bob"},
    ],
})


# ─────────────────────────────────────────────
# Test 1: resolve_display_name
# ─────────────────────────────────────────────

class TestResolveDisplayName:
    def test_returns_display_name_from_db(self):
        db = _db_returning(_row("陳小明"))
        assert resolve_display_name(db, "chen@company.com") == "陳小明"

    def test_falls_back_to_upn_prefix_when_no_row(self):
        db = _db_returning(None)
        assert resolve_display_name(db, "jerry_tai@mail.chimei.com.tw") == "jerry_tai"

    def test_falls_back_to_upn_prefix_on_db_error(self):
        db = MagicMock()
        db.execute.side_effect = Exception("DB down")
        assert resolve_display_name(db, "user@domain.com") == "user"

    def test_falls_back_when_display_name_is_empty_string(self):
        db = _db_returning(_row(""))
        result = resolve_display_name(db, "user@domain.com")
        assert result == "user"


# ─────────────────────────────────────────────
# Test 2: get_accessible_meeting_stats
# ─────────────────────────────────────────────

class TestGetAccessibleMeetingStats:
    def test_returns_count_and_date(self):
        last = datetime(2026, 6, 1)
        db = _db_returning(_row(3, last))
        stats = get_accessible_meeting_stats(db, "user@domain.com")
        assert stats["meeting_count"] == 3
        assert stats["last_date"] == last

    def test_returns_zero_for_new_user(self):
        db = _db_returning(_row(0, None))
        stats = get_accessible_meeting_stats(db, "new@domain.com")
        assert stats["meeting_count"] == 0
        assert stats["last_date"] is None

    def test_returns_zero_on_db_error(self):
        db = MagicMock()
        db.execute.side_effect = Exception("timeout")
        stats = get_accessible_meeting_stats(db, "user@domain.com")
        assert stats == {"meeting_count": 0, "last_date": None}


# ─────────────────────────────────────────────
# Test 3: access isolation
# ─────────────────────────────────────────────

class TestAccessIsolation:
    """Verify that DB queries JOIN meeting_participants with the correct user_upn.
    If the UPN in the query doesn't match, no rows are returned — simulated here
    by verifying the upn binding is passed to execute().
    """

    def test_stats_query_passes_user_upn(self):
        db = _db_returning(_row(2, None))
        get_accessible_meeting_stats(db, "alice@company.com")
        call_kwargs = db.execute.call_args
        # The bound parameters dict must contain the correct upn
        bound_params = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("params", {})
        assert bound_params.get("upn") == "alice@company.com"

    def test_different_users_get_different_upn_binding(self):
        db_alice = _db_returning(_row(5, None))
        db_bob = _db_returning(_row(0, None))
        get_accessible_meeting_stats(db_alice, "alice@company.com")
        get_accessible_meeting_stats(db_bob, "bob@company.com")
        alice_params = db_alice.execute.call_args[0][1]
        bob_params = db_bob.execute.call_args[0][1]
        assert alice_params["upn"] == "alice@company.com"
        assert bob_params["upn"] == "bob@company.com"


# ─────────────────────────────────────────────
# Test 4: extract_top_topics
# ─────────────────────────────────────────────

class TestExtractTopTopics:
    def test_extracts_chapter_titles_with_higher_weight(self):
        meetings = [
            {"summary_json": SAMPLE_SUMMARY_JSON, "title": "週會"},
        ]
        topics = extract_top_topics(meetings, max_topics=3)
        # "AI 投資 ROI" appears as chapter (weight 2) + speaker topic (weight 1) = 3
        assert "AI 投資 ROI" in topics

    def test_returns_empty_for_no_meetings(self):
        assert extract_top_topics([]) == []

    def test_handles_malformed_summary_json(self):
        """Malformed JSON should be silently skipped, not raise."""
        meetings = [
            {"summary_json": "NOT_JSON", "title": "壞會議"},
            {"summary_json": SAMPLE_SUMMARY_JSON, "title": "好會議"},
        ]
        topics = extract_top_topics(meetings)
        assert isinstance(topics, list)  # no exception, returns list

    def test_handles_none_summary_json(self):
        meetings = [{"summary_json": None, "title": "無摘要會議"}]
        topics = extract_top_topics(meetings)
        assert topics == []

    def test_respects_max_topics_limit(self):
        meetings = [{"summary_json": SAMPLE_SUMMARY_JSON, "title": "週會"}]
        topics = extract_top_topics(meetings, max_topics=1)
        assert len(topics) <= 1

    def test_handles_dict_summary_json(self):
        """summary_json may already be a parsed dict (SQLAlchemy JSON column)."""
        sj_dict = json.loads(SAMPLE_SUMMARY_JSON)
        meetings = [{"summary_json": sj_dict, "title": "週會"}]
        topics = extract_top_topics(meetings)
        assert len(topics) > 0


# ─────────────────────────────────────────────
# Test 5: get_pending_action_count
# ─────────────────────────────────────────────

class TestGetPendingActionCount:
    def test_returns_correct_count(self):
        db = _db_returning(_row(4))
        assert get_pending_action_count(db, "user@domain.com") == 4

    def test_returns_zero_when_table_missing(self):
        """meeting_action_items may not exist on first deploy — should return 0, not raise."""
        db = MagicMock()
        db.execute.side_effect = Exception("no such table: meeting_action_items")
        assert get_pending_action_count(db, "user@domain.com") == 0

    def test_returns_zero_for_no_pending_items(self):
        db = _db_returning(_row(0))
        assert get_pending_action_count(db, "user@domain.com") == 0


# ─────────────────────────────────────────────
# Test 6: build_greeting_text
# ─────────────────────────────────────────────

class TestBuildGreetingText:
    def test_welcome_message_for_new_user(self):
        text = build_greeting_text("Jerry", 0, [], None, 0)
        assert "Jerry" in text
        assert "第一場" in text  # onboarding hint

    def test_returning_user_with_topics(self):
        text = build_greeting_text("Jerry", 5, ["AI 投資", "KPI"], None, 0)
        assert "Jerry" in text
        assert "AI 投資" in text
        assert "5" in text

    def test_includes_pending_prompt_when_positive_but_no_count(self):
        # 2026-07-03：待辦「數量」不再顯示（系統無勾選/消除機制），
        # 但仍在有待辦時給中性引導；斷言引導出現且不含數字。
        text = build_greeting_text("Jerry", 3, ["AI"], None, 2)
        assert "待辦" in text  # 中性引導出現
        assert "2" not in text  # 數量不顯示

    def test_no_pending_prompt_when_zero(self):
        text = build_greeting_text("Jerry", 3, ["AI"], None, 0)
        assert "待辦" not in text
        assert "待追蹤" not in text


# ─────────────────────────────────────────────
# Test 7: build_suggested_questions
# ─────────────────────────────────────────────

class TestBuildSuggestedQuestions:
    def test_always_returns_exactly_3(self):
        questions = build_suggested_questions([], None, 0)
        assert len(questions) == 3

    def test_includes_pending_question_when_count_positive(self):
        questions = build_suggested_questions(["AI"], None, 3)
        assert any("待辦" in q or "待追蹤" in q or "未解決" in q for q in questions)

    def test_includes_topic_question(self):
        questions = build_suggested_questions(["供應鏈優化"], None, 0)
        assert any("供應鏈優化" in q for q in questions)

    def test_no_duplicate_questions(self):
        questions = build_suggested_questions(["AI", "KPI"], None, 1)
        assert len(questions) == len(set(questions))


# ─────────────────────────────────────────────
# Test 8: get_last_meeting_summary
# ─────────────────────────────────────────────

class TestGetLastMeetingSummary:
    def test_returns_none_for_empty_list(self):
        assert get_last_meeting_summary([]) is None

    def test_extracts_title_and_key_actions(self):
        meetings = [{"title": "Q2 策略會議", "created_at": datetime(2026, 6, 1), "summary_json": SAMPLE_SUMMARY_JSON}]
        result = get_last_meeting_summary(meetings)
        assert result["title"] == "Q2 策略會議"
        assert len(result["key_actions"]) > 0
        assert "確認 AI 預算" in result["key_actions"]

    def test_handles_malformed_summary_json(self):
        meetings = [{"title": "壞格式", "created_at": None, "summary_json": "BAD{"}]
        result = get_last_meeting_summary(meetings)
        assert result is not None
        assert result["title"] == "壞格式"
        assert result["key_actions"] == []


# ─────────────────────────────────────────────
# Test 9: build_greeting_payload (integration)
# ─────────────────────────────────────────────

class TestBuildGreetingPayload:
    def _make_db(self, meeting_count=3, pending_count=1):
        db = MagicMock()
        call_count = [0]

        def execute_side_effect(query, params=None):
            result = MagicMock()
            q = str(query)
            if "display_name" in q:
                result.fetchone.return_value = _row("陳小明")
            elif "COUNT(DISTINCT" in q:
                result.fetchone.return_value = _row(meeting_count, datetime(2026, 5, 1))
            elif "summary_json IS NOT NULL" in q:
                rows = [
                    _row("m1", "Q2 週會", datetime(2026, 5, 1), SAMPLE_SUMMARY_JSON),
                ]
                result.fetchall.return_value = rows
            elif "meeting_action_items" in q:
                result.fetchone.return_value = _row(pending_count)
            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []
            return result

        db.execute.side_effect = execute_side_effect
        return db

    def test_normal_user_returns_complete_payload(self):
        db = self._make_db(meeting_count=3, pending_count=2)
        payload = build_greeting_payload(db, "chen@company.com")

        assert payload["display_name"] == "陳小明"
        assert payload["meeting_count"] == 3
        assert isinstance(payload["top_topics"], list)
        assert isinstance(payload["suggested_questions"], list)
        assert len(payload["suggested_questions"]) == 3
        assert payload["pending_action_count"] == 2
        assert isinstance(payload["greeting_text"], str)
        assert len(payload["greeting_text"]) > 0

    def test_new_user_returns_fallback_payload(self):
        """New user: no meetings, no summaries, no pending actions."""
        db = MagicMock()

        def execute_new_user(query, params=None):
            result = MagicMock()
            q = str(query)
            if "display_name" in q:
                result.fetchone.return_value = None          # no display name
            elif "COUNT(DISTINCT" in q:
                result.fetchone.return_value = _row(0, None) # 0 meetings
            elif "summary_json IS NOT NULL" in q:
                result.fetchall.return_value = []            # no summaries
            elif "meeting_action_items" in q:
                result.fetchone.return_value = _row(0)       # 0 pending
            else:
                result.fetchone.return_value = None
                result.fetchall.return_value = []
            return result

        db.execute.side_effect = execute_new_user
        payload = build_greeting_payload(db, "new@company.com")

        assert payload["meeting_count"] == 0
        assert payload["top_topics"] == []
        assert "第一場" in payload["greeting_text"]
        assert len(payload["suggested_questions"]) == 3

    def test_never_raises_on_complete_db_failure(self):
        """build_greeting_payload must always return a dict, never raise."""
        db = MagicMock()
        db.execute.side_effect = Exception("DB completely down")
        payload = build_greeting_payload(db, "user@domain.com")

        assert isinstance(payload, dict)
        assert "greeting_text" in payload
        assert "suggested_questions" in payload
        assert len(payload["suggested_questions"]) == 3

    def test_payload_keys_match_api_response_model(self):
        """Ensure all keys expected by RagGreetingResponse Pydantic model are present."""
        db = self._make_db()
        payload = build_greeting_payload(db, "user@domain.com")
        expected_keys = {
            "display_name", "meeting_count", "top_topics",
            "last_meeting", "pending_action_count",
            "greeting_text", "suggested_questions"
        }
        assert expected_keys.issubset(payload.keys())
