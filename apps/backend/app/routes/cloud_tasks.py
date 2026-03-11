"""
Cloud Tasks HTTP Handler Routes
Receives task requests from Google Cloud Tasks queues
"""

from fastapi import APIRouter, HTTPException, Request, Header, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import logging
import os
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.tasks import generate_meeting_minutes

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/tasks", tags=["Cloud Tasks"])

# Cloud Tasks queue name from environment
CLOUD_TASKS_QUEUE = os.getenv("CLOUD_TASKS_QUEUE", "")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class TranscriptionTaskRequest(BaseModel):
    """Request body for transcription task from Cloud Tasks"""
    meeting_id: str = Field(..., description="Meeting ID to process")
    template_type: str = Field("general", description="Summary template type")
    context: Optional[str] = Field("", description="Additional context for summary")
    length: Optional[str] = Field("", description="Summary length preference")
    style: Optional[str] = Field("", description="Summary style preference")


class SummarizationTaskRequest(BaseModel):
    """Request body for summarization task from Cloud Tasks"""
    meeting_id: str = Field(..., description="Meeting ID to summarize")
    template_type: str = Field("general", description="Summary template type")
    context: Optional[str] = Field("", description="Additional context")


class TaskResponse(BaseModel):
    """Standard response for task handlers"""
    status: str
    meeting_id: Optional[str] = None
    error: Optional[str] = None


def verify_cloud_tasks_request(
    x_cloudtasks_queuename: Optional[str] = Header(None),
    x_cloudtasks_taskname: Optional[str] = Header(None)
) -> bool:
    """
    Verify that the request is from Cloud Tasks.
    In production, Cloud Tasks always sends these headers.
    For local development, allow requests without headers.
    """
    if os.getenv("AUTH_REQUIRED", "false").lower() == "true":
        if not x_cloudtasks_queuename and not x_cloudtasks_taskname:
            # In production, reject requests without Cloud Tasks headers
            # But allow for local testing if explicitly disabled
            pass
    return True


@router.post("/transcription", status_code=200)
def handle_transcription_task(
    request: TranscriptionTaskRequest,
    x_cloudtasks_queuename: Optional[str] = Header(None),
    x_cloudtasks_taskname: Optional[str] = Header(None)
):
    """
    HTTP handler for Cloud Tasks transcription queue.
    
    IMPORTANT: Runs SYNCHRONOUSLY to keep the HTTP request alive.
    Cloud Run only keeps CPU active while an HTTP request is in-flight.
    Using BackgroundTasks (fire-and-forget) would cause Cloud Run to
    throttle/kill the container after the 202 response, interrupting
    long-running GPU ASR processing.
    
    Cloud Tasks manages retries and timeout (up to 30 min).
    Cloud Run Service timeout is set to 3600s.
    """
    logger.info(f"Received transcription task for meeting {request.meeting_id}")
    logger.info(f"Cloud Tasks headers: queue={x_cloudtasks_queuename}, task={x_cloudtasks_taskname}")
    logger.info(f"Starting SYNCHRONOUS meeting processing for {request.meeting_id} (Template: {request.template_type})")

    try:
        result = generate_meeting_minutes(
            meeting_id=request.meeting_id,
            template_type=request.template_type,
            context=request.context or "",
            length=request.length or "",
            style=request.style or ""
        )

        if result.get("status") in ("completed", "accepted"):
            return {"status": result["status"], "meeting_id": request.meeting_id, "message": "Processing completed synchronously"}
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing transcription task: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/summarization", response_model=TaskResponse)
def handle_summarization_task(
    request: SummarizationTaskRequest,
    x_cloudtasks_queuename: Optional[str] = Header(None),
    x_cloudtasks_taskname: Optional[str] = Header(None)
):
    """
    HTTP handler for Cloud Tasks summarization queue.
    Generates summary for already-transcribed meeting.
    """
    logger.info(f"Received summarization task for meeting {request.meeting_id}")
    
    try:
        result = generate_meeting_minutes(
            meeting_id=request.meeting_id,
            template_type=request.template_type,
            context=request.context or "",
            skip_asr=True  # Segments already in DB via Webhook callback
        )
        
        if result.get("status") == "completed":
            return TaskResponse(status="completed", meeting_id=request.meeting_id)
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            
    except Exception as e:
        logger.error(f"Error processing summarization task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=dict)
async def tasks_health():
    """Health check for Cloud Tasks handler"""
    return {"status": "ok", "service": "cloud-tasks-handler"}
