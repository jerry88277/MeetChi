"""
MeetChi GPU ASR Microservice — Offline Transcription + Speaker Diarization

Lightweight FastAPI service that:
  1. Receives audio file path (GCS URL or local path)
  2. Runs Breeze-ASR-25 (CTranslate2/faster-whisper)
  3. Runs WhisperX alignment + pyannote speaker diarization
  4. Updates the Meeting DB with high-quality transcript segments

Designed to run on Cloud Run with L4 GPU, scale-to-zero capable.
"""

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
    
    # Send callback after processing completes (still within the HTTP request)
    if request.callback_url and response_payload:
        logger.info(f"[ASR Refine] Sending callback to {request.callback_url}")
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    request.callback_url,
                    json=response_payload.model_dump()
                )
                if resp.status_code >= 400:
                    logger.warning(f"[ASR Refine] Callback failed with status {resp.status_code}: {resp.text}")
                else:
                    logger.info(f"[ASR Refine] Callback successful status {resp.status_code}")
        except Exception as e:
            logger.error(f"[ASR Refine] Failed to send callback for {meeting_id}: {e}")

    return response_payload


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
