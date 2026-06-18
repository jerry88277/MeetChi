"""
MeetChi GPU ASR Microservice — Offline Transcription + Speaker Diarization

Lightweight FastAPI service that:
  1. Receives audio file path (GCS URL or local path)
  2. Runs Breeze-ASR-25 (CTranslate2/faster-whisper)
  3. Runs WhisperX alignment + pyannote speaker diarization
  4. Updates the Meeting DB with high-quality transcript segments

Designed to run on Cloud Run with L4 GPU, scale-to-zero capable.
"""

import asyncio
import os
import sys
import logging
import json
import time
import tempfile
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.offline_asr import get_offline_asr_provider, BreezeASRProvider, BreezeASRConfig

# Lazy import: diarization_community1 imports pyannote/torch which may fail
# The function is imported at call time in the endpoint instead


# ============================================
# Logging
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ============================================
# FastAPI App
# ============================================
app = FastAPI(
    title="MeetChi GPU ASR Service",
    version="1.0.0",
    description="Offline ASR refinement with Breeze-ASR-25 + Speaker Diarization",
)


# ============================================
# Request / Response Models
# ============================================
class ASRRefineRequest(BaseModel):
    meeting_id: str
    audio_url: str  # GCS URL (gs://...) or local path
    language: str = "zh"
    callback_url: Optional[str] = None

class SegmentResponse(BaseModel):
    start: float
    end: float
    speaker: str
    text: str

class ASRRefineResponse(BaseModel):
    status: str  # "completed", "failed", "skipped"
    meeting_id: str
    segments: list[SegmentResponse] = []
    speakers_count: int = 0
    duration: float = 0.0
    error: Optional[str] = None
    # Phase B: per-speaker centroid embeddings for cross-chunk speaker linking
    speaker_embeddings: dict[str, list[float]] = {}


class DiarizeRequest(BaseModel):
    meeting_id: str
    audio_url: str  # GCS URL (gs://...)
    min_speakers: Optional[int] = None
    max_speakers: Optional[int] = None

class DiarizeSegment(BaseModel):
    speaker: str
    start: float
    end: float

class DiarizeResponse(BaseModel):
    status: str
    meeting_id: str
    segments: list[DiarizeSegment] = []
    speakers_count: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None


# ============================================
# Helper Functions
# ============================================
def _download_from_gcs(gcs_url: str, local_dir: str) -> str:
    """Download audio from GCS to local temp file."""
    from google.cloud import storage as gcs_storage

    parts = gcs_url.replace("gs://", "").split("/", 1)
    bucket_name = parts[0]
    blob_name = parts[1] if len(parts) > 1 else ""

    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)

    local_path = os.path.join(local_dir, os.path.basename(blob_name))
    blob.download_to_filename(local_path)
    logger.info(f"Downloaded {gcs_url} → {local_path}")
    return local_path


# ============================================
# Endpoints
# ============================================
@app.get("/health")
async def health():
    """Health check — also reports GPU and ASR model availability."""
    provider = get_offline_asr_provider()
    gpu_available = False
    try:
        import torch
        gpu_available = torch.cuda.is_available()
    except ImportError:
        pass

    return {
        "status": "healthy",
        "service": "meetchi-gpu-asr",
        "gpu_available": gpu_available,
        "asr_provider": provider.provider_name if provider else None,
        "asr_available": provider is not None and provider.is_available(),
    }


# ============================================
# Plan B: Taiwanese Re-transcription for Low-Confidence Segments
# ============================================

# Confidence threshold — segments below this are likely non-Mandarin
RETRANSCRIBE_CONFIDENCE_THRESHOLD = float(os.getenv("RETRANSCRIBE_CONFIDENCE_THRESHOLD", "-0.7"))
# Breeze-ASR-26 model ID (faster-whisper CTranslate2 format)
ASR26_MODEL_ID = os.getenv("ASR26_MODEL_ID", "paulpengtw/faster-whisper-Breeze-ASR-26")

_asr26_model = None

def _load_asr26_model():
    """Lazy-load Breeze-ASR-26 (Taiwanese) model."""
    global _asr26_model
    if _asr26_model is not None:
        return _asr26_model

    from faster_whisper import WhisperModel
    import torch

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    logger.info(f"[ASR-26] Loading Taiwanese model: {ASR26_MODEL_ID} (device={device})")
    _asr26_model = WhisperModel(ASR26_MODEL_ID, device=device, compute_type=compute_type)
    logger.info("[ASR-26] Taiwanese model loaded successfully")
    return _asr26_model


async def _retranscribe_low_confidence(result, audio_path: str):
    """
    Post-processing step for zh-nan (國台英混合) mode.
    
    Identifies segments where ASR-25 had low confidence (likely Taiwanese speech),
    extracts those audio clips, and re-transcribes with Breeze-ASR-26 (Taiwanese ASR).
    Replaces the original segments with ASR-26 results if they're better.
    """
    import subprocess
    from app.offline_asr import ASRResult, ASRSegment

    # Find low-confidence segments
    low_conf_indices = []
    for i, seg in enumerate(result.segments):
        # faster-whisper returns avg_logprob as confidence (negative, closer to 0 = better)
        if seg.confidence < RETRANSCRIBE_CONFIDENCE_THRESHOLD:
            low_conf_indices.append(i)

    if not low_conf_indices:
        logger.info("[ASR-26] No low-confidence segments found, skipping re-transcription")
        return result

    logger.info(
        f"[ASR-26] Found {len(low_conf_indices)}/{len(result.segments)} low-confidence segments "
        f"(threshold={RETRANSCRIBE_CONFIDENCE_THRESHOLD}), re-transcribing with Breeze-ASR-26"
    )

    # Load ASR-26 model
    try:
        model = await asyncio.to_thread(_load_asr26_model)
    except Exception as e:
        logger.warning(f"[ASR-26] Failed to load model, skipping re-transcription: {e}")
        return result

    replaced_count = 0
    for idx in low_conf_indices:
        seg = result.segments[idx]
        try:
            # Extract audio clip for this segment using ffmpeg
            clip_path = f"/tmp/asr26_clip_{idx}.wav"
            duration = seg.end - seg.start
            if duration < 0.5:
                continue

            subprocess.run(
                [
                    "ffmpeg", "-y", "-i", audio_path,
                    "-ss", str(seg.start), "-t", str(duration),
                    "-ar", "16000", "-ac", "1",
                    clip_path,
                ],
                capture_output=True, check=True, timeout=30,
            )

            # Transcribe with ASR-26
            segments_iter, info = await asyncio.to_thread(
                lambda: model.transcribe(
                    clip_path,
                    language="zh",
                    beam_size=5,
                    vad_filter=False,
                    word_timestamps=True,
                )
            )
            asr26_segments = list(segments_iter)

            if asr26_segments:
                # Combine all ASR-26 segment texts
                new_text = " ".join(s.text.strip() for s in asr26_segments if s.text.strip())
                new_confidence = sum(getattr(s, 'avg_logprob', 0) for s in asr26_segments) / len(asr26_segments)

                # Only replace if ASR-26 produced meaningful text and better confidence
                if new_text and new_confidence > seg.confidence:
                    result.segments[idx] = ASRSegment(
                        start=seg.start,
                        end=seg.end,
                        text=new_text,
                        speaker=seg.speaker,
                        confidence=new_confidence,
                        language="nan",
                        words=seg.words,
                    )
                    replaced_count += 1
                    logger.debug(
                        f"[ASR-26] Replaced segment {idx}: "
                        f"conf {seg.confidence:.2f}→{new_confidence:.2f}, "
                        f"'{seg.text[:30]}' → '{new_text[:30]}'"
                    )

            # Cleanup clip
            if os.path.exists(clip_path):
                os.remove(clip_path)

        except Exception as e:
            logger.warning(f"[ASR-26] Failed to re-transcribe segment {idx}: {e}")
            continue

    logger.info(f"[ASR-26] Re-transcription complete: replaced {replaced_count}/{len(low_conf_indices)} segments")
    return result


async def _run_asr_processing(request: ASRRefineRequest, start_time: float) -> ASRRefineResponse:
    """Run ASR processing synchronously and return result."""
    meeting_id = request.meeting_id
    temp_dir = None

    try:
        provider = get_offline_asr_provider()
        if provider is None:
            raise Exception("ASR provider not available")

        # Resolve audio path
        audio_path = request.audio_url
        if audio_path.startswith("gs://"):
            temp_dir = tempfile.mkdtemp(prefix="meetchi-asr-")
            audio_path = _download_from_gcs(audio_path, temp_dir)

        if not os.path.exists(audio_path):
            raise Exception(f"Audio file not found: {audio_path}")

        # Run ASR synchronously
        result = await provider.transcribe_with_diarization(audio_path, language=request.language)

        # Plan B: Low-confidence re-transcription with Breeze-ASR-26 (Taiwanese)
        # Only when language="zh-nan" (國台英混合 mode selected by user)
        if request.language == "zh-nan" and result.segments:
            result = await _retranscribe_low_confidence(result, audio_path)

        if not result.segments:
            logger.warning(f"[ASR Refine] Empty result for {meeting_id}")
            return ASRRefineResponse(
                status="skipped", meeting_id=meeting_id,
                duration=time.time() - start_time,
            )

        # Prepare segment response
        response_segments = []
        for seg in result.segments:
            response_segments.append(SegmentResponse(
                start=seg.start,
                end=seg.end,
                speaker=seg.speaker or "",
                text=seg.text
            ))

        elapsed = time.time() - start_time
        logger.info(
            f"[ASR Refine] Done for {meeting_id}: "
            f"{len(response_segments)} segments, {result.num_speakers} speakers, {elapsed:.1f}s"
        )

        return ASRRefineResponse(
            status="completed",
            meeting_id=meeting_id,
            segments=response_segments,
            speakers_count=result.num_speakers,
            duration=elapsed,
            speaker_embeddings=result.speaker_embeddings,
        )

    except Exception as e:
        logger.error(f"[ASR Refine] Failed for {meeting_id}: {e}", exc_info=True)
        return ASRRefineResponse(
            status="failed", meeting_id=meeting_id,
            error=str(e), duration=time.time() - start_time,
        )
    finally:
        # Clean up temp files
        if temp_dir:
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

@app.post("/asr/refine", response_model=ASRRefineResponse, status_code=200)
async def asr_refine(request: ASRRefineRequest):
    """
    Main endpoint: Offline ASR refinement with speaker diarization.
    
    IMPORTANT: Runs SYNCHRONOUSLY to keep the HTTP request alive.
    Cloud Run only keeps CPU active while an HTTP request is in-flight.
    Using BackgroundTasks would cause Cloud Run to kill the container
    after the 202 response, interrupting long-running transcription.
    
    Cloud Run Service timeout is set to 3600s to support long audio files.
    """
    start_time = time.time()
    meeting_id = request.meeting_id
    logger.info(f"[ASR Refine] Received request for meeting {meeting_id}")

    # Check provider quickly
    provider = get_offline_asr_provider()
    if provider is None:
        logger.error("[ASR Refine] No offline ASR provider available")
        raise HTTPException(status_code=503, detail="ASR provider not available")

    # Run ASR synchronously (this is the key fix!)
    response_payload = await _run_asr_processing(request, start_time)
    
    # Send callback after processing completes (still within the HTTP request).
    #
    # 2026-05-11 (incident): empty exception 訊息讓 root cause 看不出來；
    #   payload 含 2138 segments ~ 數 MB，30s timeout 對 cold-start backend 偏短。
    # 修法：
    #   1. timeout 30s → 120s（容忍 backend cold start + 大 payload 寫入）
    #   2. 失敗 retry 3 次，指數退避 5s/15s/45s（總 ~80s 上限）
    #   3. log exc_info=True 把 traceback 整段印出來，下次出事不再瞎猜
    #   4. payload 體積實測印出來，方便日後評估是否 chunked send
    if request.callback_url and response_payload:
        payload_dict = response_payload.model_dump()
        try:
            payload_size_kb = len(json.dumps(payload_dict)) / 1024
            logger.info(
                f"[ASR Refine] Sending callback to {request.callback_url} "
                f"(payload {payload_size_kb:.1f} KB)"
            )
        except Exception:
            logger.info(f"[ASR Refine] Sending callback to {request.callback_url}")

        backoff_s = [0, 5, 15]  # 第 1 次立刻；失敗後等 5s；再失敗等 15s；總 3 次
        callback_ok = False
        
        # Cloud Run service-to-service auth: fetch OIDC ID token
        auth_headers = {}
        try:
            import google.auth.transport.requests
            import google.oauth2.id_token
            auth_req = google.auth.transport.requests.Request()
            token = google.oauth2.id_token.fetch_id_token(auth_req, request.callback_url)
            auth_headers = {"Authorization": f"Bearer {token}"}
        except Exception as auth_err:
            logger.warning(f"[ASR Refine] Could not fetch ID token for callback: {auth_err}")
        
        for attempt, wait_s in enumerate(backoff_s, start=1):
            if wait_s > 0:
                await asyncio.sleep(wait_s)
            try:
                async with httpx.AsyncClient(timeout=120.0) as client:
                    resp = await client.post(request.callback_url, json=payload_dict, headers=auth_headers)
                if resp.status_code >= 400:
                    logger.warning(
                        f"[ASR Refine] Callback attempt {attempt}/3 failed "
                        f"with status {resp.status_code}: {resp.text[:300]}"
                    )
                    if 400 <= resp.status_code < 500:
                        # 4xx 不重試（payload 本身有問題，retry 沒意義）
                        break
                    continue  # 5xx 重試
                logger.info(
                    f"[ASR Refine] Callback successful (attempt {attempt}/3, "
                    f"status {resp.status_code})"
                )
                callback_ok = True
                break
            except Exception as e:
                logger.warning(
                    f"[ASR Refine] Callback attempt {attempt}/3 raised {type(e).__name__}: {e!r}",
                    exc_info=True,
                )

        if not callback_ok:
            logger.error(
                f"[ASR Refine] Callback failed after 3 attempts for {meeting_id}; "
                f"backend will not learn this meeting is done. "
                f"Manual recovery: POST {request.callback_url} with this meeting's segments."
            )

    return response_payload


# ============================================
# Diarize Endpoint (Full-Audio Speaker Diarization)
# ============================================
@app.post("/asr/diarize", response_model=DiarizeResponse)
async def asr_diarize(request: DiarizeRequest):
    """
    Run speaker diarization on full audio using pyannote community-1.
    
    This endpoint is called AFTER parallel ASR chunks are merged,
    to assign consistent global speaker labels across the entire meeting.
    """
    start_time = time.time()
    meeting_id = request.meeting_id
    temp_dir = None

    logger.info(f"[Diarize] Received request for {meeting_id}")

    try:
        # Lazy import to avoid blocking app startup if pyannote has issues
        from app.diarization_community1 import diarize_full_audio

        # Download audio from GCS
        audio_path = request.audio_url
        if audio_path.startswith("gs://"):
            temp_dir = tempfile.mkdtemp(prefix="meetchi-diarize-")
            audio_path = _download_from_gcs(audio_path, temp_dir)

        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        # Run diarization
        segments = await asyncio.to_thread(
            diarize_full_audio,
            audio_path,
            min_speakers=request.min_speakers,
            max_speakers=request.max_speakers,
        )

        elapsed = time.time() - start_time
        speakers = set(s["speaker"] for s in segments)

        logger.info(
            f"[Diarize] Done for {meeting_id}: "
            f"{len(segments)} segments, {len(speakers)} speakers, {elapsed:.1f}s"
        )

        return DiarizeResponse(
            status="completed",
            meeting_id=meeting_id,
            segments=[DiarizeSegment(**s) for s in segments],
            speakers_count=len(speakers),
            duration_seconds=elapsed,
        )

    except Exception as e:
        logger.error(f"[Diarize] Failed for {meeting_id}: {e}", exc_info=True)
        return DiarizeResponse(
            status="failed",
            meeting_id=meeting_id,
            error=str(e),
            duration_seconds=time.time() - start_time,
        )
    finally:
        if temp_dir:
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass


# ============================================
# Startup
# ============================================
@app.on_event("startup")
async def startup():
    """Pre-warm: load ASR model on startup to reduce first-request latency."""
    logger.info("GPU ASR Service starting up...")
    provider = get_offline_asr_provider()
    if provider and hasattr(provider, '_load_model'):
        logger.info("Pre-loading ASR model...")
        try:
            provider._load_model()
            logger.info("ASR model pre-loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to pre-load ASR model: {e}")
