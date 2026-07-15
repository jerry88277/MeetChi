"""Unit tests for MMS-LID Taiwanese routing (line #2)."""
import sys
import types
import numpy as np
import pytest

from app import lid_router
from app.lid_router import select_taiwanese, classify_spans, _clip, SR, LID_MIN_CLIP_S


@pytest.fixture(autouse=True)
def _open_set(monkeypatch):
    """多數單元測試針對開集路由邏輯；預設關閉閉集，個別測試自行開啟。"""
    monkeypatch.setattr(lid_router, "LID_ALLOWED_LANGS", [])


def test_select_taiwanese_closed_set_uses_renorm_nan_prob(monkeypatch):
    """閉集模式：以重正規化後 nan 機率(nan_prob_cs) 或 top-1 路由。"""
    monkeypatch.setattr(lid_router, "LID_ALLOWED_LANGS", ["cmn", "nan", "eng"])
    lid = [
        {"top_lang": "cmn", "top_prob": 0.7, "nan_prob": 0.1, "nan_prob_cs": 0.42, "top3": []},  # cs>=0.35 -> route
        {"top_lang": "cmn", "top_prob": 0.95, "nan_prob": 0.02, "nan_prob_cs": 0.05, "top3": []},  # low -> keep
        {"top_lang": "nan", "top_prob": 0.55, "nan_prob": 0.3, "nan_prob_cs": 0.55, "top3": []},  # top1 nan -> route
    ]
    assert select_taiwanese(lid, cs_nan_prob=0.35) == [0, 2]
    # 提高門檻，第0段被排除（但第2段 top1=nan 仍路由）
    assert select_taiwanese(lid, cs_nan_prob=0.5) == [2]


def test_select_taiwanese_routes_nan_above_threshold():
    lid = [
        {"top_lang": "cmn", "top_prob": 0.98, "nan_prob": 0.01, "top3": [("cmn", 0.98)]},
        {"top_lang": "nan", "top_prob": 0.91, "nan_prob": 0.91, "top3": [("nan", 0.91)]},
        {"top_lang": "nan", "top_prob": 0.40, "nan_prob": 0.40, "top3": [("nan", 0.40)]},
        None,
        {"top_lang": "eng", "top_prob": 0.80, "nan_prob": 0.02, "top3": [("eng", 0.8)]},
    ]
    # 關掉 top-k，純測 top-1 min_prob 路徑
    idx = select_taiwanese(lid, min_prob=0.5, tw_topk=0)
    assert idx == [1]


def test_select_taiwanese_topk_membership_recovers_recall():
    """nan 非 top-1 但在 top-3 → 路由（主 recall 來源）；純華語不誤路由。"""
    lid = [
        {"top_lang": "cmn", "top_prob": 0.6, "nan_prob": 0.1,
         "top3": [("cmn", 0.6), ("nan", 0.1), ("yue", 0.05)]},        # nan 在 top3 -> route
        {"top_lang": "cmn", "top_prob": 0.95, "nan_prob": 0.0,
         "top3": [("cmn", 0.95), ("wuu", 0.01), ("yue", 0.005)]},     # 純華語 -> keep
    ]
    assert select_taiwanese(lid, min_prob=0.5, tw_topk=3) == [0]
    # top-k=1 等效嚴格 top-1，不再撈回
    assert select_taiwanese(lid, min_prob=0.5, tw_topk=1) == []


def test_select_taiwanese_prob_floor_recovers_second_rank():
    """top-1 是 cmn 且 nan 不在 top-k，但絕對機率達 floor → 仍路由。"""
    lid = [
        {"top_lang": "cmn", "top_prob": 0.6, "nan_prob": 0.25,
         "top3": [("cmn", 0.6), ("yue", 0.1), ("wuu", 0.05)]},
        {"top_lang": "cmn", "top_prob": 0.9, "nan_prob": 0.05,
         "top3": [("cmn", 0.9), ("yue", 0.03), ("wuu", 0.02)]},
    ]
    assert select_taiwanese(lid, min_prob=0.5, tw_prob_floor=0.2, tw_topk=0) == [0]
    assert select_taiwanese(lid, min_prob=0.5, tw_prob_floor=1.1, tw_topk=0) == []


def test_select_taiwanese_respects_custom_lang_set(monkeypatch):
    monkeypatch.setattr(lid_router, "TAIWANESE_LANGS", {"nan", "hak"})
    lid = [
        {"top_lang": "hak", "top_prob": 0.7, "nan_prob": 0.0, "top3": [("hak", 0.7)]},
        {"top_lang": "cmn", "top_prob": 0.9, "nan_prob": 0.0, "top3": [("cmn", 0.9)]},
        {"top_lang": "nan", "top_prob": 0.6, "nan_prob": 0.6, "top3": [("nan", 0.6)]},
    ]
    assert select_taiwanese(lid, min_prob=0.5, tw_prob_floor=1.1, tw_topk=0) == [0, 2]


def test_clip_truncates_to_max():
    audio = np.ones(int(30 * SR), dtype=np.float32)
    clip = _clip(audio, 0.0, 30.0, SR)
    # 應被截斷到 LID_MAX_CLIP_S 秒
    assert len(clip) <= int(lid_router.LID_MAX_CLIP_S * SR) + 1


def test_classify_short_spans_shortcircuit_no_model():
    """全部太短 → 在載入模型/torch 前就回全 None（不需 GPU 依賴）。"""
    audio = np.ones(int(5 * SR), dtype=np.float32)
    spans = [(0.0, 0.3), (1.0, 1.2)]  # 皆 < LID_MIN_CLIP_S
    res = classify_spans(audio, spans, SR)
    assert res == [None, None]


def test_classify_spans_batches_with_mocked_model(monkeypatch):
    """以 numpy 支撐的假 torch 驗證批次路徑：dict 結構、nan_prob、短段落跳過。"""
    audio = np.ones(int(20 * SR), dtype=np.float32)
    spans = [(0.0, 3.0), (3.0, 3.2), (4.0, 8.0)]  # 第 2 段太短

    class _NT:
        """numpy-backed tensor 包裝，支援程式碼用到的少數 op。"""
        def __init__(self, a): self.a = np.asarray(a)
        def to(self, device): return self
        def max(self, dim=-1):
            return _NT(self.a.max(axis=dim)), _NT(self.a.argmax(axis=dim))
        def __getitem__(self, idx): return _NT(self.a[idx])
        def item(self): return self.a.item()
        @property
        def shape(self): return self.a.shape

    fake_torch = types.ModuleType("torch")
    class _NoGrad:
        def __enter__(self): return self
        def __exit__(self, *a): return False
    fake_torch.no_grad = lambda: _NoGrad()
    fake_torch.softmax = lambda t, dim=-1: _NT(
        np.exp(t.a) / np.exp(t.a).sum(axis=dim, keepdims=True))

    def _topk(t, k, dim=-1):
        a = t.a
        idx = np.argsort(-a, axis=dim)[..., :k]
        val = np.take_along_axis(a, idx, axis=dim)
        return _NT(val), _NT(idx)
    fake_torch.topk = _topk
    monkeypatch.setitem(sys.modules, "torch", fake_torch)

    class _FakeModel:
        class config:
            num_labels = 2
            id2label = {0: "nan", 1: "cmn"}
        def parameters(self):
            class _P: device = "cpu"
            return iter([_P()])
        def __call__(self, **kw):
            # 第1候選 nan 主導，第2候選 cmn 主導
            return type("O", (), {"logits": _NT([[2.0, 0.1], [0.2, 2.0]])})()
    def _fake_extractor(batch, sampling_rate, return_tensors, padding):
        return {"input_values": _NT(np.zeros(len(batch)))}

    monkeypatch.setattr(lid_router, "_load_lid", lambda: (_FakeModel(), _fake_extractor))

    res = classify_spans(audio, spans, SR)
    assert res[1] is None, "太短段落應跳過"
    assert res[0]["top_lang"] == "nan" and res[0]["nan_prob"] > 0.8
    assert res[2]["top_lang"] == "cmn" and res[2]["nan_prob"] < 0.2
    assert select_taiwanese(res, min_prob=0.5, tw_prob_floor=1.1, tw_topk=0) == [0]
