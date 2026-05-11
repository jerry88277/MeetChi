"""Audio split for long meetings (>20 min) — enables parallel GPU ASR.

設計（Phase A，2026-05-11）：
  1. duration > LONG_AUDIO_THRESHOLD_SEC (1200s = 20 min) 觸發拆解
  2. 用 ffmpeg `-ss <offset> -i <input> -t <chunk_sec> -c copy <chunk>` 切片
     stream copy 速度極快（不重編碼），唯一缺點是切點貼齊 keyframe，
     可能有 ±1s drift；對 ASR 字幕影響可忽略
  3. 每個 chunk 上傳至 `gs://{bucket}/audio/_chunks/{meeting_id}/chunk_{N:03d}.{ext}`
  4. 回傳 [(chunk_gs_url, offset_sec), ...] 供 caller 平行 POST 到 GPU service
  5. 處理完後 caller 須呼叫 cleanup_chunks 清掉 GCS 暫存

已知限制（Phase A 接受）：
  - Speaker diarization 跨 chunk 不連貫（SPEAKER_0 in chunk 1 ≠ SPEAKER_0 in chunk 2）
    將透過 frontend speaker_mappings 手動對應；未來 Phase B 補 voice embedding re-cluster
  - chunk 邊界恰好切到對話中段：ASR 模型內 sliding window 會延伸捕捉，影響極小

未來 Phase B 升級點：
  - Voice embedding cross-chunk re-cluster
  - chunk 邊界 overlap (e.g., 30s) 後 dedupe segments
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import List, Tuple

logger = logging.getLogger(__name__)

# Threshold: 20 minutes (1200 sec)。短於此就單一 ASR 不拆。
LONG_AUDIO_THRESHOLD_SEC = int(os.getenv("LONG_AUDIO_THRESHOLD_SEC", "1200"))
# Chunk 大小 (sec)：等於 threshold；可獨立設定
CHUNK_SEC = int(os.getenv("AUDIO_CHUNK_SEC", "1200"))


def get_audio_duration(local_path: str) -> float:
    """Use ffprobe to read accurate duration of an audio/video file."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            local_path,
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return float(result.stdout.strip())


def split_audio_to_chunks(
    audio_gs_url: str,
    meeting_id: str,
    chunk_sec: int = CHUNK_SEC,
) -> List[Tuple[str, float]]:
    """Download audio from GCS, split via ffmpeg, upload each chunk back to GCS.

    Returns:
        List of (chunk_gs_url, time_offset_sec) tuples, ordered by chunk index.
        time_offset_sec 是該 chunk 在原音檔中的起始秒數，用於 segment 時戳補正。

    Raises:
        ValueError: 若 audio_gs_url 格式錯誤
        subprocess.CalledProcessError: ffmpeg / ffprobe 失敗
        google.api_core.exceptions.*: GCS 上下載失敗
    """
    if not audio_gs_url.startswith("gs://"):
        raise ValueError(f"audio_gs_url must be gs:// format, got: {audio_gs_url[:60]}")

    from google.cloud import storage as gcs_storage

    parts = audio_gs_url.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)

    with tempfile.TemporaryDirectory(prefix="meetchi-split-") as tmpdir:
        # 1. Download original audio
        local_input = os.path.join(tmpdir, os.path.basename(blob_name))
        logger.info(f"[AudioSplit] Downloading {audio_gs_url} → {local_input}")
        bucket.blob(blob_name).download_to_filename(local_input)

        # 2. Probe duration
        duration = get_audio_duration(local_input)
        n_chunks = max(1, int((duration + chunk_sec - 1) // chunk_sec))
        ext = os.path.splitext(local_input)[1] or ".mp4"
        logger.info(
            f"[AudioSplit] duration={duration:.1f}s, splitting into {n_chunks} chunks "
            f"(chunk_sec={chunk_sec})"
        )

        # 3. Split & upload each chunk
        chunks: List[Tuple[str, float]] = []
        for i in range(n_chunks):
            offset = i * chunk_sec
            chunk_local = os.path.join(tmpdir, f"chunk_{i:03d}{ext}")
            # ffmpeg: -ss before -i 用 input seek (fast)，stream copy 不重編碼
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(offset),
                "-i", local_input,
                "-t", str(chunk_sec),
                "-c", "copy",
                "-loglevel", "warning",
                chunk_local,
            ]
            logger.info(f"[AudioSplit] chunk {i+1}/{n_chunks}: offset={offset}s")
            subprocess.run(cmd, check=True, capture_output=True, timeout=180)

            # Sanity check: chunk file exists and non-empty
            if not os.path.exists(chunk_local) or os.path.getsize(chunk_local) < 1024:
                raise RuntimeError(
                    f"[AudioSplit] chunk {i} too small ({os.path.getsize(chunk_local)} bytes); "
                    f"ffmpeg may have silently failed"
                )

            chunk_gs_blob = f"audio/_chunks/{meeting_id}/chunk_{i:03d}{ext}"
            bucket.blob(chunk_gs_blob).upload_from_filename(chunk_local)
            chunk_url = f"gs://{bucket_name}/{chunk_gs_blob}"
            chunks.append((chunk_url, float(offset)))
            logger.info(f"[AudioSplit]   uploaded {chunk_url} ({os.path.getsize(chunk_local)} bytes)")

        logger.info(f"[AudioSplit] complete: {n_chunks} chunks uploaded for {meeting_id}")
        return chunks


def cleanup_chunks(audio_gs_url: str, meeting_id: str) -> int:
    """Delete chunk files from GCS after processing complete.
    Returns number of chunks deleted. Failures logged but not raised.
    """
    try:
        from google.cloud import storage as gcs_storage

        parts = audio_gs_url.replace("gs://", "").split("/", 1)
        bucket_name = parts[0]

        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        prefix = f"audio/_chunks/{meeting_id}/"
        blobs = list(bucket.list_blobs(prefix=prefix))

        for blob in blobs:
            try:
                blob.delete()
            except Exception as e:
                logger.warning(f"[AudioSplit] Failed to delete {blob.name}: {e}")

        logger.info(f"[AudioSplit] Cleaned up {len(blobs)} chunks under {prefix}")
        return len(blobs)
    except Exception as e:
        logger.warning(f"[AudioSplit] Cleanup failed (non-fatal): {e}")
        return 0


def should_use_parallel_split(duration_sec: float | None) -> bool:
    """Decision helper: 是否該走 parallel split path."""
    if duration_sec is None:
        return False
    return duration_sec > LONG_AUDIO_THRESHOLD_SEC
