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
from typing import Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# Add parent directory to path so we can import app modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.offline_asr import get_offline_asr_provider, BreezeASRProvider, BreezeASRConfig
from app.models import Meeting, TranscriptSegment, MeetingStatus, TaskStatus as TaskStatusModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
# Database
# ============================================
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

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


class ASRRefineResponse(BaseModel):
    status: str  # "completed", "failed", "skipped"
    meeting_id: str
    segments_count: int = 0
    speakers_count: int = 0
    duration: float = 0.0
    error: Optional[str] = None


# ============================================
# Helper Functions
# ============================================
def _update_task_status(db, meeting_id: str, task_name: str, status: str, message: str = None):
    """Create/update TaskStatus record."""
    task = db.query(TaskStatusModel).filter(
        TaskStatusModel.meeting_id == meeting_id,
        TaskStatusModel.task_name == task_name,
    ).first()
    if task:
        task.status = status
        task.message = message
    else:
        task = TaskStatusModel(
            meeting_id=meeting_id,
            task_name=task_name,
            status=status,
            message=message,
        )
        db.add(task)
    db.commit()


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


@app.post("/asr/refine", response_model=ASRRefineResponse)
async def asr_refine(request: ASRRefineRequest):
    """
    Main endpoint: Offline ASR refinement with speaker diarization.
    
    Called by CPU Service after recording ends.
    
    Flow:
      1. Set meeting status to REFINING
      2. Download audio from GCS (if needed)
      3. Run Breeze ASR (CTranslate2) + WhisperX diarization
      4. Replace DB segments with refined results
      5. Set meeting status to COMPLETED
    """
    start_time = time.time()
    meeting_id = request.meeting_id
    logger.info(f"[ASR Refine] Received request for meeting {meeting_id}")

    # Check provider
    provider = get_offline_asr_provider()
    if provider is None:
        logger.error("[ASR Refine] No offline ASR provider available")
        raise HTTPException(status_code=503, detail="ASR provider not available")

    db = SessionLocal()
    temp_dir = None
    try:
        # Validate meeting exists
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting {meeting_id} not found")

        # Set REFINING status
        meeting.status = MeetingStatus.REFINING
        db.commit()
        _update_task_status(db, meeting_id, "offline_asr", "IN_PROGRESS", f"Running {provider.provider_name}")

        # Resolve audio path
        audio_path = request.audio_url
        if audio_path.startswith("gs://"):
            temp_dir = tempfile.mkdtemp(prefix="meetchi-asr-")
            audio_path = _download_from_gcs(audio_path, temp_dir)

        if not os.path.exists(audio_path):
            raise HTTPException(status_code=400, detail=f"Audio file not found: {audio_path}")

        # Run ASR
        result = await provider.transcribe_with_diarization(audio_path, language=request.language)

        if not result.segments:
            logger.warning(f"[ASR Refine] Empty result for {meeting_id}")
            meeting.status = MeetingStatus.COMPLETED
            db.commit()
            _update_task_status(db, meeting_id, "offline_asr", "COMPLETED", "Empty result, kept Gemini transcript")
            return ASRRefineResponse(
                status="skipped", meeting_id=meeting_id,
                duration=time.time() - start_time,
            )

        # Replace segments in DB
        db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()

        new_segments = []
        for idx, seg in enumerate(result.segments):
            new_seg = TranscriptSegment(
                meeting_id=meeting_id,
                order=idx,
                start_time=seg.start,
                end_time=seg.end,
                speaker=seg.speaker,
                content_raw=seg.text,
                content_polished=seg.text,
                is_final=True,
            )
            new_segments.append(new_seg)
        db.add_all(new_segments)

        # Update meeting
        meeting.transcript_raw = result.to_transcript_text(include_speaker=True)
        meeting.status = MeetingStatus.COMPLETED
        db.commit()

        elapsed = time.time() - start_time
        _update_task_status(
            db, meeting_id, "offline_asr", "COMPLETED",
            f"{len(new_segments)} segments, {result.num_speakers} speakers, {elapsed:.1f}s"
        )

        logger.info(
            f"[ASR Refine] Done for {meeting_id}: "
            f"{len(new_segments)} segments, {result.num_speakers} speakers, {elapsed:.1f}s"
        )

        return ASRRefineResponse(
            status="completed",
            meeting_id=meeting_id,
            segments_count=len(new_segments),
            speakers_count=result.num_speakers,
            duration=elapsed,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[ASR Refine] Failed for {meeting_id}: {e}", exc_info=True)
        try:
            if meeting:
                meeting.status = MeetingStatus.COMPLETED  # Fallback: keep Gemini transcript
                db.commit()
            _update_task_status(db, meeting_id, "offline_asr", "FAILED", str(e))
        except Exception:
            pass
        return ASRRefineResponse(
            status="failed", meeting_id=meeting_id,
            error=str(e), duration=time.time() - start_time,
        )
    finally:
        db.close()
        # Clean up temp files
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
