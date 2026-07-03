"""Audio health analysis for uploaded meeting recordings.

讓使用者知道自己上傳音檔的「原始狀態」：時長、聲道、取樣率、音量（peak/mean dBFS），
並判斷是否為「實質靜音／無訊號」「音量過低」「削波(clipping)」等常見問題。

背景（2026-07-03 診斷）：部分會議狀態顯示 COMPLETED 但 0 段落，使用者誤以為系統壞掉。
實測 bc41c457 / c2c92ef2 兩檔 peak≈-80dBFS、每窗 RMS 平坦於 -97dB、ZCR≈0.466（隨機雜訊
特徵），屬「擷取端沒錄到聲音」（麥克風未開／權限被擋／錄到無訊號裝置），並非小聲語音。
故 ASR 產出 0 段落是「正確」行為 —— 真正該做的是把音檔原始狀態明確呈現給使用者。

實作：以 ffmpeg `volumedetect`（peak/mean dBFS + 0dB histogram）+ ffprobe（codec/聲道/取樣率/
時長）單檔分析，backend 容器已內建 ffmpeg（見 Dockerfile）。
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# --- 判定門檻（dBFS）---------------------------------------------------------
# 實測：正常語音 peak 接近 0dBFS；靜音檔 peak≈-80dBFS。
SILENCE_PEAK_DBFS = -50.0      # peak 低於此 → 實質靜音／無訊號（不可救）
LOW_VOLUME_PEAK_DBFS = -18.0   # peak 低於此（但高於靜音）→ 音量偏低（多半可救）
LOW_VOLUME_MEAN_DBFS = -40.0   # mean 低於此 → 整體偏小聲
CLIP_RATIO = 0.05              # 0dB 樣本占比超過此 → 疑似削波（advisory；避免正規化音檔誤報）


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _probe_format(local_path: str) -> dict:
    """ffprobe：取 codec / 聲道 / 取樣率 / 時長。"""
    out = {"codec": None, "channels": None, "sample_rate": None, "duration_sec": None}
    try:
        r = _run([
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_streams", "-show_format", local_path,
        ], timeout=60)
        data = json.loads(r.stdout or "{}")
        audio = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
        if audio:
            out["codec"] = audio.get("codec_name")
            out["channels"] = int(audio["channels"]) if audio.get("channels") is not None else None
            out["sample_rate"] = int(audio["sample_rate"]) if audio.get("sample_rate") else None
        dur = (data.get("format") or {}).get("duration")
        if dur is not None:
            out["duration_sec"] = round(float(dur), 3)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audio_stats] ffprobe failed for {local_path}: {e}")
    return out


def _volumedetect(local_path: str) -> dict:
    """ffmpeg volumedetect：取 mean/peak dBFS 與 0dB 樣本占比（削波指標）。"""
    out = {"peak_dbfs": None, "mean_dbfs": None, "clip_ratio": None}
    try:
        r = _run([
            "ffmpeg", "-hide_banner", "-i", local_path,
            "-af", "volumedetect", "-f", "null", os.devnull,
        ], timeout=180)
        text = r.stderr or ""
        m = re.search(r"mean_volume:\s*(-?[\d.]+) dB", text)
        p = re.search(r"max_volume:\s*(-?[\d.]+) dB", text)
        # n_samples 會印兩次（第一次為 0 的 setup 行）—— 取最大值才是實際樣本數
        n_all = [int(x) for x in re.findall(r"n_samples:\s*(\d+)", text)]
        h0 = re.search(r"histogram_0db:\s*(\d+)", text)
        if m:
            out["mean_dbfs"] = float(m.group(1))
        if p:
            out["peak_dbfs"] = float(p.group(1))
        total = max(n_all) if n_all else 0
        if h0 and total > 0:
            out["clip_ratio"] = round(int(h0.group(1)) / total, 5)
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audio_stats] volumedetect failed for {local_path}: {e}")
    return out


def _classify(peak: Optional[float], mean: Optional[float], clip_ratio: Optional[float]) -> tuple[str, str, list[str]]:
    """回傳 (health, health_label_zh, warnings)。"""
    warnings: list[str] = []

    if peak is None:
        return "unknown", "無法分析音量", warnings

    if peak < SILENCE_PEAK_DBFS:
        warnings.append("silent")
        return ("silent",
                "未偵測到可辨識語音（可能麥克風未開啟、權限被擋，或錄到無聲音源）",
                warnings)

    health = "ok"
    label = "音檔正常"

    if peak < LOW_VOLUME_PEAK_DBFS or (mean is not None and mean < LOW_VOLUME_MEAN_DBFS):
        warnings.append("low_volume")
        health = "low_volume"
        label = "音量偏低（辨識可能受影響，建議提高錄音音量或靠近麥克風）"

    if clip_ratio is not None and clip_ratio > CLIP_RATIO and (peak is not None and peak >= -0.1):
        warnings.append("clipping")
        if health == "ok":
            health = "clipping"
            label = "音量過大／可能削波失真（辨識可能受影響，建議降低錄音增益）"

    return health, label, warnings


def analyze_audio_stats(local_path: str) -> dict:
    """分析單一本機音檔，回傳可序列化的健康報告 dict。

    永不 raise：任一步驟失敗只記 log 並在對應欄位留 None，確保不影響主轉錄流程。
    """
    stats: dict = {
        "duration_sec": None, "channels": None, "sample_rate": None, "codec": None,
        "peak_dbfs": None, "mean_dbfs": None, "clip_ratio": None,
        "health": "unknown", "health_label_zh": "無法分析音量",
        "warnings": [], "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        if not local_path or not os.path.exists(local_path):
            logger.warning(f"[audio_stats] file not found: {local_path}")
            return stats
        stats.update(_probe_format(local_path))
        stats.update(_volumedetect(local_path))
        health, label, warnings = _classify(
            stats.get("peak_dbfs"), stats.get("mean_dbfs"), stats.get("clip_ratio")
        )
        stats["health"] = health
        stats["health_label_zh"] = label
        stats["warnings"] = warnings
        logger.info(
            f"[audio_stats] {os.path.basename(local_path)}: "
            f"peak={stats['peak_dbfs']}dBFS mean={stats['mean_dbfs']}dBFS "
            f"dur={stats['duration_sec']}s ch={stats['channels']} health={health}"
        )
    except Exception as e:  # noqa: BLE001
        logger.warning(f"[audio_stats] analyze failed for {local_path}: {e}")
    return stats


def is_silent(stats: Optional[dict]) -> bool:
    """便利判斷：音檔是否實質靜音（供 pipeline 決定是否略過重運算）。"""
    return bool(stats) and stats.get("health") == "silent"
