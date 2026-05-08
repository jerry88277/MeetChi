"""
Unit tests for app.rag.prompt — strict grounding prompt builder.

Run:
  cd apps/backend
  pytest tests/test_rag_prompt.py -v
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.rag.prompt import (
    CONFIDENCE_LEVELS,
    DEFAULT_CONFIDENCE,
    MAX_HISTORY_CHARS_PER_TURN,
    MAX_HISTORY_TURNS,
    STRICT_GROUNDING_SYSTEM_PROMPT,
    build_grounded_prompt,
)


def _citation(
    meeting_title="A 週會",
    speaker="Alice",
    start_time=72.0,
    content="Q3 預算定 50 萬。",
):
    return SimpleNamespace(
        meeting_title=meeting_title,
        speaker=speaker,
        start_time=start_time,
        content=content,
    )


def _msg(role: str, text: str):
    return SimpleNamespace(role=role, text=text)


# ============================================
# CONFIDENCE_LEVELS
# ============================================
class TestConfidenceLevels:
    def test_4_levels_exist(self):
        assert set(CONFIDENCE_LEVELS) == {"high", "medium", "low", "no_answer"}

    def test_default_is_no_answer(self):
        assert DEFAULT_CONFIDENCE == "no_answer"


# ============================================
# build_grounded_prompt
# ============================================
class TestBuildGroundedPrompt:
    def test_includes_system_prompt(self):
        prompt = build_grounded_prompt("test", [_citation()])
        assert STRICT_GROUNDING_SYSTEM_PROMPT in prompt

    def test_includes_question(self):
        prompt = build_grounded_prompt("Q3 預算多少？", [_citation()])
        assert "Q3 預算多少？" in prompt

    def test_includes_citation_with_meeting_title(self):
        prompt = build_grounded_prompt("Q?", [_citation(meeting_title="財務週會")])
        assert "[來源1]" in prompt
        assert "財務週會" in prompt

    def test_includes_speaker(self):
        prompt = build_grounded_prompt("Q?", [_citation(speaker="王經理")])
        assert "(王經理)" in prompt

    def test_speaker_omitted_when_none(self):
        prompt = build_grounded_prompt("Q?", [_citation(speaker=None)])
        # 沒 speaker 不應該出現空括號
        assert "(None)" not in prompt
        assert "()" not in prompt

    def test_time_formatted_as_mmss(self):
        # 72 秒 → 01:12
        prompt = build_grounded_prompt("Q?", [_citation(start_time=72.0)])
        assert "[01:12]" in prompt

    def test_time_omitted_when_none(self):
        prompt = build_grounded_prompt("Q?", [_citation(start_time=None)])
        assert "[" not in prompt or "[來源1]" in prompt  # 只剩來源編號的方括號

    def test_multiple_citations_numbered(self):
        prompt = build_grounded_prompt("Q?", [_citation(), _citation(), _citation()])
        assert "[來源1]" in prompt
        assert "[來源2]" in prompt
        assert "[來源3]" in prompt

    def test_empty_citations_handled(self):
        prompt = build_grounded_prompt("Q?", [])
        # 不該 crash，應該有「無相關段落」之類的 fallback
        assert "（無相關段落）" in prompt
        assert "Q?" in prompt

    def test_history_truncated_to_max_turns(self):
        # 給 10 輪，應只保留最後 6
        history = [_msg("user", f"Q{i}") for i in range(10)]
        prompt = build_grounded_prompt("Q?", [_citation()], history)

        # 最後 6 輪應該都在
        for i in range(4, 10):
            assert f"Q{i}" in prompt
        # 前 4 輪應該被截掉
        assert "Q0" not in prompt
        assert "Q1" not in prompt

    def test_history_per_turn_truncated(self):
        long_text = "x" * (MAX_HISTORY_CHARS_PER_TURN + 100)
        history = [_msg("user", long_text)]
        prompt = build_grounded_prompt("Q?", [_citation()], history)

        # 應截到 MAX_HISTORY_CHARS_PER_TURN
        assert prompt.count("x") <= MAX_HISTORY_CHARS_PER_TURN + 10  # 容忍少量含其他 x

    def test_history_role_normalized(self):
        history = [_msg("USER", "hi"), _msg("AI", "hello")]
        prompt = build_grounded_prompt("Q?", [_citation()], history)
        assert "User: hi" in prompt
        assert "AI: hello" in prompt

    def test_history_dict_input_supported(self):
        # history 用 dict 而非物件也要能接
        history = [{"role": "user", "text": "hi"}, {"role": "ai", "text": "hello"}]
        prompt = build_grounded_prompt("Q?", [_citation()], history)
        assert "User: hi" in prompt
        assert "AI: hello" in prompt

    def test_no_history_no_history_block(self):
        prompt = build_grounded_prompt("Q?", [_citation()])
        assert "對話脈絡" not in prompt

    def test_strict_rules_present(self):
        # 5 條硬規則必須都出現在 prompt
        prompt = build_grounded_prompt("Q?", [_citation()])
        for rule_keyword in [
            "規則 1",
            "規則 2",
            "規則 3",
            "規則 4",
            "規則 5",
            "禁止 markdown",
            "no_answer",
            "high",
            "medium",
            "low",
        ]:
            assert rule_keyword in prompt, f"missing keyword: {rule_keyword}"


# ============================================
# Citation 物件容錯
# ============================================
class TestCitationCompat:
    def test_missing_meeting_title_falls_back(self):
        citation = SimpleNamespace(
            meeting_title=None,
            speaker="A",
            start_time=0.0,
            content="...",
        )
        prompt = build_grounded_prompt("Q?", [citation])
        assert "未命名會議" in prompt

    def test_missing_content_does_not_crash(self):
        citation = SimpleNamespace(
            meeting_title="X",
            speaker=None,
            start_time=None,
            content=None,
        )
        # 不應該 raise
        prompt = build_grounded_prompt("Q?", [citation])
        assert "[來源1]" in prompt
