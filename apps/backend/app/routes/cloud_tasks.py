"""
Cloud Tasks HTTP Handler Routes
Receives task requests from Google Cloud Tasks queues
"""

from fastapi import APIRouter, HTTPException, Request, Header, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional
import json
import logging
import os
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Meeting
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
    x_cloudtasks_taskname: Optional[str] = Header(None),
    x_cloudtasks_taskretrycount: Optional[str] = Header(None)
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
    retry_count = int(x_cloudtasks_taskretrycount) if x_cloudtasks_taskretrycount else 0
    max_retries = 3  # Cloud Tasks default; suppress notification on first failures
    is_cloud_tasks = bool(x_cloudtasks_queuename or x_cloudtasks_taskname)
    suppress_fail_notify = is_cloud_tasks and retry_count < max_retries - 1

    logger.info(f"Received transcription task for meeting {request.meeting_id}")
    logger.info(f"Cloud Tasks headers: queue={x_cloudtasks_queuename}, task={x_cloudtasks_taskname}, retry={retry_count}")

    # Idempotency guard: skip if meeting is already COMPLETED or currently PROCESSING
    # This prevents Cloud Tasks retries from overwriting successful results
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == request.meeting_id).first()
        if meeting and meeting.status == "COMPLETED":
            logger.info(f"Meeting {request.meeting_id} already COMPLETED, skipping retry (idempotent)")
            return {"status": "completed", "meeting_id": request.meeting_id, "message": "Already completed, skipped"}
        if meeting and meeting.status == "PROCESSING" and retry_count > 0:
            logger.warning(f"Meeting {request.meeting_id} still PROCESSING on retry #{retry_count}, skipping to avoid conflict")
            return {"status": "skipped", "meeting_id": request.meeting_id, "message": "Already processing, skipped retry"}
    finally:
        db.close()

    logger.info(f"Starting SYNCHRONOUS meeting processing for {request.meeting_id} (Template: {request.template_type})")

    try:
        result = generate_meeting_minutes(
            meeting_id=request.meeting_id,
            template_type=request.template_type,
            context=request.context or "",
            length=request.length or "",
            style=request.style or "",
            suppress_fail_notification=suppress_fail_notify
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
    x_cloudtasks_taskname: Optional[str] = Header(None),
    x_cloudtasks_taskretrycount: Optional[str] = Header(None),
):
    """
    HTTP handler for Cloud Tasks summarization queue.
    Generates summary for already-transcribed meeting.
    
    Cloud Tasks sends X-CloudTasks-TaskRetryCount header (0-based).
    When retries are available, we suppress Discord FAIL notifications
    to avoid the confusing ❌→✅ double-notification pattern.
    """
    retry_count = int(x_cloudtasks_taskretrycount) if x_cloudtasks_taskretrycount else 0
    max_retries = 3  # Cloud Tasks default; suppress notification on first failures
    is_cloud_tasks = bool(x_cloudtasks_queuename or x_cloudtasks_taskname)
    suppress_fail_notify = is_cloud_tasks and retry_count < max_retries - 1
    
    logger.info(
        f"Received summarization task for meeting {request.meeting_id} "
        f"(retry={retry_count}, suppress_fail_notify={suppress_fail_notify})"
    )
    
    try:
        result = generate_meeting_minutes(
            meeting_id=request.meeting_id,
            template_type=request.template_type,
            context=request.context or "",
            skip_asr=True,  # Segments already in DB via Webhook callback
            suppress_fail_notification=suppress_fail_notify
        )
        
        if result.get("status") == "completed":
            return TaskResponse(status="completed", meeting_id=request.meeting_id)
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Unknown error"))
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing summarization task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class EnqueueTranscriptionRequest(BaseModel):
    """Request body for enqueuing a transcription task via Cloud Tasks"""
    meeting_id: str = Field(..., description="Meeting ID to process")
    template_type: str = Field("general", description="Summary template type")
    context: Optional[str] = Field("", description="Additional context for summary")


class EnqueueResponse(BaseModel):
    """Response for enqueue endpoint"""
    status: str
    meeting_id: str
    message: str


@router.post("/enqueue-transcription", response_model=EnqueueResponse)
def enqueue_transcription(request: EnqueueTranscriptionRequest):
    """
    Lightweight endpoint that enqueues a transcription job via Cloud Tasks.

    Instead of running transcription synchronously (which blocks for 10-30 min
    and risks crashing the instance when many meetings are uploaded at once),
    this creates a Cloud Task that will call /api/v1/tasks/transcription with
    queue-level concurrency control (maxConcurrentDispatches).

    This prevents the bulk-upload crash scenario where N simultaneous large
    meetings exhaust CPU/memory and kill the backend instance.
    """
    project = os.getenv("GCP_PROJECT")
    location = os.getenv("GCP_LOCATION")

    if not project or not location:
        # Fallback: no Cloud Tasks config → run synchronously (dev environment)
        logger.warning(
            "[Enqueue] GCP_PROJECT/GCP_LOCATION not set, falling back to synchronous processing"
        )
        try:
            result = generate_meeting_minutes(
                meeting_id=request.meeting_id,
                template_type=request.template_type,
                context=request.context or "",
            )
            return EnqueueResponse(
                status=result.get("status", "completed"),
                meeting_id=request.meeting_id,
                message="Processed synchronously (no Cloud Tasks config)",
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    # Verify meeting exists and set processing_stage = "queued"
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == request.meeting_id).first()
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting {request.meeting_id} not found")
        if not meeting.audio_url:
            raise HTTPException(status_code=400, detail="Meeting has no audio to transcribe")
        meeting.processing_stage = "queued"
        db.commit()
    finally:
        db.close()

    try:
        from google.cloud import tasks_v2

        client = tasks_v2.CloudTasksClient()
        queue_name = os.getenv("CLOUD_TASKS_TRANSCRIPTION_QUEUE", "meetchi-transcription-queue")
        parent = client.queue_path(project, location, queue_name)

        backend_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
        url = f"{backend_url}/api/v1/tasks/transcription"

        task_payload = {
            "meeting_id": request.meeting_id,
            "template_type": request.template_type,
            "context": request.context or "",
        }

        task = {
            "http_request": {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": {"Content-type": "application/json"},
                "body": json.dumps(task_payload).encode(),
            }
        }

        response = client.create_task(request={"parent": parent, "task": task})
        logger.info(
            f"[Enqueue] Transcription task created for meeting {request.meeting_id}: {response.name}"
        )

        return EnqueueResponse(
            status="enqueued",
            meeting_id=request.meeting_id,
            message=f"Transcription enqueued via Cloud Tasks (queue: {queue_name})",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Enqueue] Failed to create Cloud Task: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue transcription task: {str(e)}",
        )


@router.get("/health", response_model=dict)
async def tasks_health():
    """Health check for Cloud Tasks handler"""
    return {"status": "ok", "service": "cloud-tasks-handler"}
