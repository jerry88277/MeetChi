"""
Unit tests for app.intent_classifier — fully mocked Gemini, no network.

Run:
  cd apps/backend
  pytest tests/test_intent_classifier.py -v

Coverage targets:
  - resolve_template_name: known / legacy / unknown / empty
  - classify_intent: short input / happy path / unknown template / invalid JSON
                     / API error / input truncation
  - IntentResult schema: confidence bounds, template_name validation
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.intent_classifier import (
    DEFAULT_TEMPLATE,
    LEGACY_ALIAS,
    MAX_INPUT_CHARS,
    MIN_INPUT_CHARS,
    SYSTEM_TEMPLATES,
    IntentResult,
    classify_intent,
    resolve_template_name,
)


# ============================================
# resolve_template_name
# ============================================
class TestResolveTemplateName:
    def test_known_system_name_passes_through(self):
        for name in SYSTEM_TEMPLATES:
            assert resolve_template_name(name) == name

    def test_unknown_name_falls_back_to_default(self):
        assert resolve_template_name("nonexistent") == DEFAULT_TEMPLATE
        assert resolve_template_name("marketing") == DEFAULT_TEMPLATE

    def test_empty_or_none_falls_back(self):
        assert resolve_template_name("") == DEFAULT_TEMPLATE
        assert resolve_template_name(None) == DEFAULT_TEMPLATE  # type: ignore[arg-type]

    def test_legacy_alias_resolution(self, monkeypatch):
        # 動態 patch LEGACY_ALIAS 確保 resolution 真的有走那一支
        monkeypatch.setitem(LEGACY_ALIAS, "old_name", "general")
        assert resolve_template_name("old_name") == "general"


# ============================================
# IntentResult schema
# ============================================
class TestIntentResultSchema:
    def test_valid_construction(self):
        r = IntentResult(template_name="general", confidence=0.7, reason="通用會議")
        assert r.template_name == "general"
        assert r.confidence == 0.7
        assert r.reason == "通用會議"

    def test_confidence_upper_bound(self):
        with pytest.raises(ValidationError):
            IntentResult(template_name="general", confidence=1.5, reason="x")

    def test_confidence_lower_bound(self):
        with pytest.raises(ValidationError):
            IntentResult(template_name="general", confidence=-0.1, reason="x")

    def test_unknown_template_rejected(self):
        with pytest.raises(ValidationError):
            IntentResult(template_name="marketing", confidence=0.5, reason="x")

    def test_reason_max_length(self):
        # max_length=200，超過會 fail
        with pytest.raises(ValidationError):
            IntentResult(template_name="general", confidence=0.5, reason="x" * 201)


# ============================================
# classify_intent — short input short-circuit
# ============================================
class TestClassifyIntentShortInput:
    def test_empty_string_returns_default_without_calling_llm(self):
        client = MagicMock()
        result = classify_intent("", client)
        assert result.template_name == DEFAULT_TEMPLATE
        assert result.confidence == 0.0
        assert "過短" in result.reason
        client.models.generate_content.assert_not_called()

    def test_below_min_chars_skips_llm(self):
        client = MagicMock()
        # 100 字 < MIN_INPUT_CHARS (200)
        result = classify_intent("a" * 100, client)
        assert result.template_name == DEFAULT_TEMPLATE
        client.models.generate_content.assert_not_called()

    def test_whitespace_only_treated_as_empty(self):
        client = MagicMock()
        result = classify_intent("   \n\n\t   " * 30, client)  # 全是空白
        assert result.template_name == DEFAULT_TEMPLATE
        client.models.generate_content.assert_not_called()


# ============================================
# classify_intent — happy path
# ============================================
class TestClassifyIntentHappyPath:
    @staticmethod
    def _client_returning(payload: dict) -> MagicMock:
        client = MagicMock()
        response = MagicMock()
        response.text = json.dumps(payload)
        client.models.generate_content.return_value = response
        return client

    def test_classifies_sales_meeting(self):
        client = self._client_returning({
            "template_name": "sales_bant",
            "confidence": 0.92,
            "reason": "提到客戶預算與簽約時程",
        })
        text = "客戶 Q3 預算大概 50 萬，需求是端到端 RAG 平台。" * 20
        result = classify_intent(text, client)
        assert result.template_name == "sales_bant"
        assert result.confidence == 0.92
        assert "預算" in result.reason

    def test_classifies_interview(self):
        client = self._client_returning({
            "template_name": "hr_star",
            "confidence": 0.85,
            "reason": "候選人講之前帶團隊上線案例",
        })
        text = "面試官: 請描述過去帶領團隊的經驗。" * 20
        result = classify_intent(text, client)
        assert result.template_name == "hr_star"

    def test_classifies_rd_meeting(self):
        client = self._client_returning({
            "template_name": "rd",
            "confidence": 0.80,
            "reason": "討論 K8s 架構升級風險",
        })
        text = "我們 K8s 升級風險評估，pgvector 升級向量檢索效能。" * 15
        result = classify_intent(text, client)
        assert result.template_name == "rd"

    def test_classifies_general_when_no_specific_pattern(self):
        client = self._client_returning({
            "template_name": "general",
            "confidence": 0.55,
            "reason": "通用週會",
        })
        text = "本週進度報告，下週重點。" * 30
        result = classify_intent(text, client)
        assert result.template_name == "general"


# ============================================
# classify_intent — fallback paths
# ============================================
class TestClassifyIntentFallback:
    def test_unknown_template_from_llm_falls_back(self):
        client = MagicMock()
        response = MagicMock()
        response.text = json.dumps({
            "template_name": "marketing",  # 不在 SYSTEM_TEMPLATES
            "confidence": 0.5,
            "reason": "...",
        })
        client.models.generate_content.return_value = response

        text = "x" * 300
        result = classify_intent(text, client)
        # resolve_template_name 把 marketing → general
        assert result.template_name == DEFAULT_TEMPLATE

    def test_invalid_json_falls_back(self):
        client = MagicMock()
        response = MagicMock()
        response.text = "this is not json {{{"
        client.models.generate_content.return_value = response

        text = "y" * 300
        result = classify_intent(text, client)
        assert result.template_name == DEFAULT_TEMPLATE
        assert result.confidence == 0.0
        assert "JSON" in result.reason or "非合法" in result.reason

    def test_api_exception_falls_back(self):
        client = MagicMock()
        client.models.generate_content.side_effect = RuntimeError("API down")

        text = "z" * 300
        result = classify_intent(text, client)
        assert result.template_name == DEFAULT_TEMPLATE
        assert result.confidence == 0.0
        assert "RuntimeError" in result.reason

    def test_response_text_none_falls_back(self):
        # Gemini 偶爾會回傳 response.text = None (safety filter 等)
        client = MagicMock()
        response = MagicMock()
        response.text = None
        client.models.generate_content.return_value = response

        text = "w" * 300
        result = classify_intent(text, client)
        assert result.template_name == DEFAULT_TEMPLATE
        assert result.confidence == 0.0

    def test_confidence_clamping(self):
        # Gemini 偶爾回傳 1.5 之類 → 應 clamp 到 1.0
        client = MagicMock()
        response = MagicMock()
        response.text = json.dumps({
            "template_name": "general",
            "confidence": 1.5,  # overflow
            "reason": "x",
        })
        client.models.generate_content.return_value = response

        text = "v" * 300
        result = classify_intent(text, client)
        assert result.confidence == 1.0  # clamped


# ============================================
# classify_intent — input truncation
# ============================================
class TestClassifyIntentTruncation:
    def test_long_input_is_truncated(self):
        client = MagicMock()
        response = MagicMock()
        response.text = json.dumps({
            "template_name": "general",
            "confidence": 0.5,
            "reason": "通用",
        })
        client.models.generate_content.return_value = response

        long_text = "a" * (MAX_INPUT_CHARS * 3)  # 3 倍長度
        classify_intent(long_text, client)

        # 確認送進 generate_content 的 prompt 內 transcript 段不含完整 long_text
        call_kwargs = client.models.generate_content.call_args.kwargs
        prompt = call_kwargs["contents"]
        # prompt 含 header + truncated transcript；總長 < 原文長度
        assert len(prompt) < len(long_text)
        # 但至少包含 MIN_INPUT_CHARS 數量的 transcript
        assert prompt.count("a") >= MIN_INPUT_CHARS

    def test_max_output_tokens_capped(self):
        client = MagicMock()
        response = MagicMock()
        response.text = json.dumps({
            "template_name": "general",
            "confidence": 0.5,
            "reason": "x",
        })
        client.models.generate_content.return_value = response

        classify_intent("a" * 300, client)
        config = client.models.generate_content.call_args.kwargs["config"]
        assert config["max_output_tokens"] == 256
        assert config["temperature"] == 0.1
        assert config["response_mime_type"] == "application/json"
