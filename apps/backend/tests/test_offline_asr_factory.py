"""
Unit tests for app.offline_asr.get_offline_asr_provider — factory selection.

Bug context: 線上 v15-community1 image 跑 pyannote v4.0，但 default
BreezeASRProvider 用 v3.x API，diarization 全 fail，speaker 全合一。
本 factory 須依 DIARIZATION_MODEL env 選對應 provider。

Run:
  cd apps/backend
  pytest tests/test_offline_asr_factory.py -v
"""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """每個 test 之間重置 _provider_instance singleton。"""
    import app.offline_asr as oa
    monkeypatch.setattr(oa, "_provider_instance", None)
    yield


class TestGetOfflineAsrProviderDefaultMode:
    """DIARIZATION_MODEL 未設或非 community-1 時，回傳 BreezeASRProvider。"""

    def test_no_env_var_returns_default(self, monkeypatch):
        monkeypatch.delenv("DIARIZATION_MODEL", raising=False)

        from app.offline_asr import get_offline_asr_provider, BreezeASRProvider
        with patch.object(BreezeASRProvider, "is_available", return_value=True):
            provider = get_offline_asr_provider()

        assert provider is not None
        assert isinstance(provider, BreezeASRProvider)

    def test_unrecognized_value_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("DIARIZATION_MODEL", "some-other-value")

        from app.offline_asr import get_offline_asr_provider, BreezeASRProvider
        with patch.object(BreezeASRProvider, "is_available", return_value=True):
            provider = get_offline_asr_provider()

        assert isinstance(provider, BreezeASRProvider)

    def test_uppercase_community_one_normalized(self, monkeypatch):
        """factory 要 case-insensitive — COMMUNITY-1 也應 trigger community1 path。"""
        monkeypatch.setenv("DIARIZATION_MODEL", "COMMUNITY-1")

        # Inject a fake community1 module
        fake_module = MagicMock()
        FakeCommunity1Provider = MagicMock(name="BreezeASRCommunity1Provider")
        instance = MagicMock(provider_name="Fake-Community1")
        instance.is_available.return_value = True
        FakeCommunity1Provider.return_value = instance
        fake_module.BreezeASRCommunity1Provider = FakeCommunity1Provider

        with patch.dict("sys.modules", {"app.offline_asr_community1": fake_module}):
            from app.offline_asr import get_offline_asr_provider
            provider = get_offline_asr_provider()

        assert provider is instance


class TestGetOfflineAsrProviderCommunity1Mode:
    """DIARIZATION_MODEL=community-1 時，回傳 BreezeASRCommunity1Provider。"""

    def test_community1_env_returns_community1_provider(self, monkeypatch):
        monkeypatch.setenv("DIARIZATION_MODEL", "community-1")

        # Inject fake module
        fake_module = MagicMock()
        FakeProvider = MagicMock(name="BreezeASRCommunity1Provider")
        instance = MagicMock(provider_name="Breeze-ASR-25-Community1 (CTranslate2 + pyannote v4.0)")
        instance.is_available.return_value = True
        FakeProvider.return_value = instance
        fake_module.BreezeASRCommunity1Provider = FakeProvider

        with patch.dict("sys.modules", {"app.offline_asr_community1": fake_module}):
            from app.offline_asr import get_offline_asr_provider
            provider = get_offline_asr_provider()

        assert provider is instance
        FakeProvider.assert_called_once()

    def test_community1_unavailable_falls_back_to_default(self, monkeypatch):
        """若 community1 provider .is_available()=False，回退到 default。"""
        monkeypatch.setenv("DIARIZATION_MODEL", "community-1")

        # Community1 reports not-available
        fake_module = MagicMock()
        FakeProvider = MagicMock()
        instance = MagicMock()
        instance.is_available.return_value = False
        FakeProvider.return_value = instance
        fake_module.BreezeASRCommunity1Provider = FakeProvider

        from app.offline_asr import BreezeASRProvider
        with patch.dict("sys.modules", {"app.offline_asr_community1": fake_module}), \
             patch.object(BreezeASRProvider, "is_available", return_value=True):
            from app.offline_asr import get_offline_asr_provider
            provider = get_offline_asr_provider()

        assert isinstance(provider, BreezeASRProvider)

    def test_community1_import_fail_falls_back_to_default(self, monkeypatch):
        """若 community1 module import 失敗（如未在 image 內），回退到 default。"""
        monkeypatch.setenv("DIARIZATION_MODEL", "community-1")

        # 用 mock import_module 觸發 ImportError
        from app.offline_asr import BreezeASRProvider

        # Patch sys.modules：刪除 community1 + 讓 importlib 找不到
        import sys
        if "app.offline_asr_community1" in sys.modules:
            monkeypatch.delitem(sys.modules, "app.offline_asr_community1")

        # 用 patch finder 強制丟 ImportError
        original_find_spec = importlib.util.find_spec

        def fake_find_spec(name, *args, **kwargs):
            if name == "app.offline_asr_community1":
                return None
            return original_find_spec(name, *args, **kwargs)

        with patch("importlib.util.find_spec", side_effect=fake_find_spec), \
             patch.object(BreezeASRProvider, "is_available", return_value=True):
            # 真正 trigger ImportError 的方式：把 community1 import 直接 patch
            with patch.dict("sys.modules", {"app.offline_asr_community1": None}):
                from app.offline_asr import get_offline_asr_provider
                provider = get_offline_asr_provider()

        assert isinstance(provider, BreezeASRProvider)


class TestGetOfflineAsrProviderSingleton:
    """確認 singleton 行為：第二次呼叫返回同物件。"""

    def test_singleton_returns_same_instance(self, monkeypatch):
        monkeypatch.delenv("DIARIZATION_MODEL", raising=False)

        from app.offline_asr import get_offline_asr_provider, BreezeASRProvider
        with patch.object(BreezeASRProvider, "is_available", return_value=True):
            p1 = get_offline_asr_provider()
            p2 = get_offline_asr_provider()

        assert p1 is p2


class TestGetOfflineAsrProviderNoProvider:
    """既無 community1 也無 default 可用時回 None（CPU-only 部署）。"""

    def test_no_provider_returns_none(self, monkeypatch):
        monkeypatch.delenv("DIARIZATION_MODEL", raising=False)

        from app.offline_asr import get_offline_asr_provider, BreezeASRProvider
        with patch.object(BreezeASRProvider, "is_available", return_value=False):
            provider = get_offline_asr_provider()

        assert provider is None
