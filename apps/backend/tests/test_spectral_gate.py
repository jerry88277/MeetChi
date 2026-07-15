"""Unit tests for pre-Whisper spectral gate (幻覺抑制訊號層)."""
import numpy as np
import pytest

from app.spectral_gate import (
    GateConfig, compute_gate, apply_gate, _frame_features, _robust_z, SR,
)


def _muffled_murmur(dur_s, sr=SR, f0=110.0):
    """低頻主導、悶、缺高頻 articulation 的遠場 murmur（模擬幻覺區）。"""
    t = np.arange(int(dur_s * sr)) / sr
    sig = np.zeros_like(t)
    # 少數低頻諧波 + 慢調變，能量集中在 <750Hz，幾乎無 >2kHz
    for k, amp in [(1, 1.0), (2, 0.5), (3, 0.25)]:
        sig += amp * np.sin(2 * np.pi * f0 * k * t)
    sig *= (0.6 + 0.4 * np.sin(2 * np.pi * 0.5 * t))
    # 低頻 hum
    sig += 0.3 * np.sin(2 * np.pi * 60 * t)
    return sig.astype(np.float32)


def _articulate_speech(dur_s, sr=SR, f0=140.0):
    """有明顯高頻 articulation（子音/formant）的近場清晰語音（模擬真實區）。"""
    t = np.arange(int(dur_s * sr)) / sr
    sig = np.zeros_like(t)
    # 豐富諧波涵蓋到 3–4kHz（articulation），高階諧波不過度衰減
    for k in range(1, 30):
        sig += (1.0 / (k ** 0.5)) * np.sin(2 * np.pi * f0 * k * t)
    # 加強高頻摩擦噪音（子音）陣發：2–4kHz 頻帶噪音
    rng = np.random.default_rng(0)
    noise = rng.normal(0, 1, len(t))
    carrier = np.sin(2 * np.pi * 3000 * t)  # 3kHz 載波把噪音搬到高頻
    burst = (np.sin(2 * np.pi * 3 * t) > 0.3).astype(np.float32)
    sig += 1.2 * noise * carrier * burst
    return sig.astype(np.float32)


def _normalize(x):
    peak = np.max(np.abs(x)) + 1e-9
    return (x / peak * 0.3).astype(np.float32)


def test_features_separate_muffled_vs_articulate():
    murmur = _normalize(_muffled_murmur(6))
    speech = _normalize(_articulate_speech(6))
    _, tilt_m, cpp_m, hf_m = _frame_features(murmur, SR, 1.5, 0.5)
    _, tilt_s, cpp_s, hf_s = _frame_features(speech, SR, 1.5, 0.5)
    # 真實語音頻譜傾斜（高/低頻比）與高頻占比應高於悶 murmur
    assert np.median(tilt_s) > np.median(tilt_m)
    assert np.median(hf_s) > np.median(hf_m)


def test_leading_gate_masks_opening_hallucination():
    """開頭 8s murmur + 後 8s 真實語音 → leading 模式應遮住開頭、保留真實。"""
    murmur = _normalize(_muffled_murmur(8))
    speech = _normalize(_articulate_speech(8))
    audio = np.concatenate([murmur, speech])
    cfg = GateConfig()
    cfg.mode = "leading"
    masked, res = apply_gate(audio, SR, cfg)

    assert res.spans, "應偵測到開頭幻覺區並產生遮罩"
    first_s, first_e = res.spans[0]
    assert first_s < 1.0, "遮罩應從開頭附近開始"
    # 遮罩不得侵入真實語音區（8s 之後）
    assert all(e <= 8.5 for _, e in res.spans), f"遮罩越界到真實區: {res.spans}"
    # 真實語音區（>9s）應維持原樣（未被歸零）
    real_region = masked[int(9 * SR):]
    assert np.max(np.abs(real_region)) > 0.01, "真實語音區不應被遮罩"
    # 開頭遮罩區應被歸零
    assert np.max(np.abs(masked[:int(1 * SR)])) < 1e-6


def test_all_real_speech_not_gated():
    """整段皆清晰真實語音 → 不應遮罩（絕對高頻護欄生效）。"""
    speech = _normalize(_articulate_speech(12))
    cfg = GateConfig()
    cfg.mode = "leading"
    masked, res = apply_gate(speech, SR, cfg)
    assert res.gated_frac < 0.1, f"真實語音被誤遮 frac={res.gated_frac}"
    assert np.max(np.abs(masked)) > 0.01


def test_max_gate_frac_cap():
    """整段皆 murmur → leading 找不到真實起點，遮到護欄上限但不超過。"""
    murmur = _normalize(_muffled_murmur(12))
    cfg = GateConfig()
    cfg.mode = "leading"
    cfg.max_gate_frac = 0.7
    _, res = apply_gate(murmur, SR, cfg)
    assert res.gated_frac <= 0.7 + 1e-6


def test_full_mode_masks_muffled_spans_protects_articulate():
    """full 模式（預設）：悶區 → 遮；清晰真實語音 → 絕對高頻護欄保護不遮。"""
    murmur = _normalize(_muffled_murmur(8))
    speech = _normalize(_articulate_speech(8))
    # 交錯：murmur, speech, murmur, speech
    audio = np.concatenate([murmur, speech, murmur, speech])
    cfg = GateConfig()
    cfg.mode = "full"
    masked, res = apply_gate(audio, SR, cfg)
    assert res.spans, "應偵測到悶區並遮罩"
    # 清晰語音區 [8,16] 與 [24,32] 應大致完整保留
    for lo, hi in [(9, 15), (25, 31)]:
        region = masked[int(lo * SR):int(hi * SR)]
        assert np.max(np.abs(region)) > 0.01, f"真實語音區 [{lo},{hi}] 被誤遮"


def test_robust_z_zero_mad():
    x = np.array([5.0, 5.0, 5.0, 5.0])
    z = _robust_z(x)
    assert np.all(np.isfinite(z))
