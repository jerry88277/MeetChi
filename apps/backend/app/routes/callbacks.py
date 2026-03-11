"""
Callback routes from external services (e.g. GPU ASR)
"""
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import logging
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Meeting, TranscriptSegment, MeetingStatus
from app.tasks import _update_task_status, generate_summary_core
import os
import json
from google.cloud import tasks_v2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/callbacks", tags=["Callbacks"])

class SegmentData(BaseModel):
    start: float
    end: float
    speaker: str
    text: str

class ASRDonePayload(BaseModel):
    status: str
    meeting_id: str
    segments: List[SegmentData] = []
    speakers_count: int = 0
    duration: float = 0.0
    error: Optional[str] = None

@router.post("/asr-done", status_code=200)
async def handle_asr_done(payload: ASRDonePayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Webhook receiver for GPU ASR completion.
    """
    meeting_id = payload.meeting_id
    logger.info(f"[Callback] Received ASR done for {meeting_id} with status: {payload.status}")

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        logger.error(f"[Callback] Meeting {meeting_id} not found")
        raise HTTPException(status_code=404, detail="Meeting not found")

    if payload.status == "completed" and payload.segments:
        _update_task_status(db, meeting_id, "offline_asr", "COMPLETED", 
                            f"Received {len(payload.segments)} segments from remote GPU")
        
        # Wipe existing segments
        db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()
        
        new_segments = []
        for idx, s in enumerate(payload.segments):
            new_seg = TranscriptSegment(
                meeting_id=meeting_id,
                order=idx,
                start_time=s.start,
                end_time=s.end,
                speaker=s.speaker,
                content_raw=s.text,
                content_polished=s.text,
                is_final=True,
            )
            new_segments.append(new_seg)
        db.add_all(new_segments)
        
        # Update transcript_raw
        lines = [f"[{s.speaker}] {s.text}" if s.speaker else s.text for s in payload.segments]
        meeting.transcript_raw = "\n".join(lines)
        db.commit()
        logger.info(f"[Callback] Updated DB with remote GPU ASR results for {meeting_id}")
        
    elif payload.status == "failed":
        logger.error(f"[Callback] Remote GPU ASR failed: {payload.error}")
        _update_task_status(db, meeting_id, "offline_asr", "FAILED", f"Remote error: {payload.error}")
        meeting.status = MeetingStatus.COMPLETED # Fallback
        db.commit()
    elif payload.status == "skipped":
        logger.warning(f"[Callback] Remote GPU ASR skipped")
        _update_task_status(db, meeting_id, "offline_asr", "SKIPPED", "Remote GPU ASR skipped")
        meeting.status = MeetingStatus.COMPLETED
        db.commit()
        
    # Only trigger summarization when ASR completed successfully with segments.
    # Failed/skipped status should NOT enqueue a summary task.
    if payload.status == "completed" and payload.segments:
        # Use Cloud Tasks instead of BackgroundTasks to avoid CPU throttling
        # on the Cloud Run instance that just returned an HTTP 202.
        project = os.getenv("GCP_PROJECT")
        location = os.getenv("GCP_LOCATION")
        
        if project and location:
            try:
                client = tasks_v2.CloudTasksClient()
                parent = client.queue_path(project, location, "meetchi-summarization-queue")
                
                backend_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
                url = f"{backend_url}/api/v1/tasks/summarization"
                
                task_payload = {
                    "meeting_id": meeting_id,
                    "template_type": "general",
                    "context": ""
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
                logger.info(f"[Callback] Successfully enqueued summarization task: {response.name}")
            except Exception as e:
                logger.error(f"[Callback] Failed to enqueue summarization task, falling back to BackgroundTasks: {e}")
                # CRITICAL: skip_asr=True — segments already in DB, only generate summary
                background_tasks.add_task(generate_summary_core, meeting_id=meeting_id, 
                                          template_type="general", context="", skip_asr=True)
        else:
            logger.warning("[Callback] GCP_PROJECT or GCP_LOCATION not set. using BackgroundTasks.")
            background_tasks.add_task(generate_summary_core, meeting_id=meeting_id, 
                                      template_type="general", context="", skip_asr=True)
    else:
        logger.info(f"[Callback] Skipping summarization — status={payload.status}, segments={len(payload.segments)}")
    
    return {"status": "ok", "message": "Callback processed"}
