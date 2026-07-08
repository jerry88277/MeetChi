"""
Callback routes from external services (e.g. GPU ASR)
"""
from fastapi import APIRouter, HTTPException, Depends, Request, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Meeting, TranscriptSegment, MeetingStatus
from app.tasks import _update_task_status, generate_summary_core
import os
import json
from google.cloud import tasks_v2

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/callbacks", tags=["Callbacks"])


async def verify_asr_callback(request: Request) -> bool:
    """驗證 /asr-done 回呼確實來自我方 GPU 服務（service-to-service）。

    GPU 服務已用 `google.oauth2.id_token.fetch_id_token(audience=callback_url)`
    附上 Google 簽發的 OIDC ID token。此處驗證該 token 的簽章與 audience。

    以 env `CALLBACK_AUTH_REQUIRED` 閘控（預設 false）：
      - false：向後相容，不強制（僅記錄），供既有部署平滑過渡。
      - true ：無有效 OIDC token 一律 401，杜絕任意人偽造 ASR 結果寫入會議。
    """
    enforce = os.getenv("CALLBACK_AUTH_REQUIRED", "false").lower() == "true"
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if not auth or not auth.lower().startswith("bearer "):
        if enforce:
            raise HTTPException(status_code=401, detail="Missing callback credentials")
        logger.warning("[Callback] no bearer token (enforcement off — allowing)")
        return True

    token = auth.split(" ", 1)[1].strip()
    try:
        import google.auth.transport.requests
        import google.oauth2.id_token
        google_req = google.auth.transport.requests.Request()
        # 不用 request.url 當 audience：Cloud Run 內部轉發可能是 http/不同 host，
        # 會與 GPU 簽發時的 audience（= BACKEND_PUBLIC_URL + callback path）不符。
        # 改為先驗簽章（audience=None），再手動比對 aud / SA email。
        claims = google.oauth2.id_token.verify_token(token, google_req, audience=None)
        iss = claims.get("iss", "")
        if iss not in ("https://accounts.google.com", "accounts.google.com"):
            raise ValueError(f"unexpected issuer {iss}")
        backend_url = (os.getenv("BACKEND_PUBLIC_URL", "") or "").rstrip("/")
        expected_aud = f"{backend_url}/api/v1/callbacks/asr-done" if backend_url else None
        aud = claims.get("aud", "")
        email = claims.get("email", "")
        # 通過條件（任一）：audience 與設定的 callback URL 相符；或 email 為本專案的
        # Cloud Run 服務帳號（service-to-service）。兩者皆為我方 GPU 才可能成立。
        aud_ok = expected_aud is not None and aud == expected_aud
        sa_ok = email.endswith(".iam.gserviceaccount.com") and os.getenv("GCP_PROJECT", "") in email
        if not (aud_ok or sa_ok):
            raise ValueError(f"aud/email not trusted (aud={aud}, email={email})")
        return True
    except Exception as e:  # noqa: BLE001
        if enforce:
            logger.error(f"[Callback] OIDC verification failed: {e}")
            raise HTTPException(status_code=401, detail="Invalid callback credentials")
        logger.warning(f"[Callback] OIDC verification failed (enforcement off — allowing): {e}")
        return True


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
async def handle_asr_done(payload: ASRDonePayload, background_tasks: BackgroundTasks, db: Session = Depends(get_db), _auth: bool = Depends(verify_asr_callback)):
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

        # C1: Apply glossary-based post-correction
        try:
            from app.tasks import apply_glossary_correction
            user_upn = meeting.owner_upn
            corrected = apply_glossary_correction(db, meeting_id, user_upn)
            if corrected > 0:
                logger.info(f"[Callback] Glossary correction applied to {corrected} segments for {meeting_id}")
        except Exception as e:
            logger.warning(f"[Callback] Glossary correction failed (non-fatal): {e}")
        
    elif payload.status == "failed":
        logger.error(f"[Callback] Remote GPU ASR failed: {payload.error}")
        _update_task_status(db, meeting_id, "offline_asr", "FAILED", f"Remote error: {payload.error}")
        meeting.status = MeetingStatus.FAILED  # ASR failed → FAILED (not COMPLETED)
        meeting.processing_stage = None
        db.commit()
    elif payload.status == "skipped":
        logger.warning(f"[Callback] Remote GPU ASR skipped")
        _update_task_status(db, meeting_id, "offline_asr", "SKIPPED", "Remote GPU ASR skipped")
        meeting.status = MeetingStatus.COMPLETED
        meeting.processing_stage = None
        # 2026-07-03：GPU 對靜音/無訊號音檔多半回 skipped（VAD 找不到語音）。
        # 若 audio_stats 判為 silent，補上使用者可讀原因（與 completed+empty 分支一致）。
        try:
            if meeting.audio_stats:
                _st = json.loads(meeting.audio_stats)
                if _st.get("health") == "silent":
                    meeting.failure_reason = _st.get("health_label_zh") or meeting.failure_reason
        except Exception:  # noqa: BLE001
            pass
        db.commit()
    elif payload.status == "completed" and not payload.segments:
        # 2026-07-03：GPU 完成但 0 段落 —— 過去所有 if/elif 皆落空，狀態懸置，
        # 使用者誤以為系統壞掉。多半是「實質靜音／無訊號」音檔（麥克風未開等）。
        # 明確收斂為 COMPLETED，並依 audio_stats 給使用者可讀原因。
        reason = "未偵測到可辨識語音（音檔可能為靜音或無有效聲音訊號）"
        try:
            if meeting.audio_stats:
                _st = json.loads(meeting.audio_stats)
                if _st.get("health") == "silent":
                    reason = _st.get("health_label_zh") or reason
        except Exception:  # noqa: BLE001
            pass
        logger.warning(f"[Callback] Completed with 0 segments for {meeting_id}: {reason}")
        _update_task_status(db, meeting_id, "offline_asr", "COMPLETED", "Completed with 0 segments (silent/empty audio)")
        meeting.status = MeetingStatus.COMPLETED
        meeting.processing_stage = None
        meeting.completed_at = meeting.completed_at or datetime.utcnow()
        meeting.failure_reason = reason
        db.commit()
        
    # Only trigger summarization when ASR completed successfully with segments.
    # Failed/skipped status should NOT enqueue a summary task.
    if payload.status == "completed" and payload.segments:
        # Set processing_stage to summarizing before enqueueing summary task
        meeting.processing_stage = "summarizing"
        db.commit()

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
