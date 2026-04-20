# Cloud Tasks Compatible Background Tasks
# Removed Celery dependency - now works with direct function calls or Cloud Tasks HTTP triggers

import logging
import os
import json
import subprocess
import sys
from sqlalchemy.orm import Session
from app.models import Meeting, TranscriptSegment, MeetingStatus, TaskStatus as TaskStatusModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from app.llm_utils import get_gemini_client, generate_summary
from app.notify import send_completion_notification
from app.embedding import embed_transcript_segments, embed_meeting_summary

logger = logging.getLogger(__name__)

# Load env to get HF_AUTH_TOKEN
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
HF_AUTH_TOKEN = os.getenv("HF_AUTH_TOKEN")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

WHISPERX_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "exec_whisperx_task_v1.2.py")
TRANSCRIBE_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "transcribe", "json")


def _update_task_status(db: Session, meeting_id: str, task_name: str, status: str, message: str = None):
    """Helper to create/update a TaskStatus record for tracking processing progress."""
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


def run_offline_asr_refinement(meeting_id: str, audio_path: str, language: str = "zh"):
    """
    Plan B: Run offline high-quality ASR + diarization using BreezeASRProvider.
    
    Replaces the old WhisperX subprocess approach with the new OfflineASRProvider abstraction.
    
    Flow:
      1. Set meeting status to REFINING
      2. Run Breeze ASR (CTranslate2) + WhisperX diarization
      3. Replace DB segments with high-quality results
      4. Set meeting status back to COMPLETED
    """
    from app.offline_asr import get_offline_asr_provider
    import asyncio

    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            logger.error(f"[Offline ASR] Meeting {meeting_id} not found")
            return {"status": "failed", "error": "Meeting not found"}

        # Check provider availability
        provider = get_offline_asr_provider()
        if provider is None:
            logger.info(f"[Offline ASR] No provider available, keeping Gemini transcript for {meeting_id}")
            _update_task_status(db, meeting_id, "offline_asr", "SKIPPED", "No offline ASR provider available")
            return {"status": "skipped", "reason": "no_provider"}

        # Set status to REFINING
        meeting.status = MeetingStatus.REFINING
        db.commit()
        _update_task_status(db, meeting_id, "offline_asr", "IN_PROGRESS", f"Running {provider.provider_name}")

        logger.info(f"[Offline ASR] Starting refinement for {meeting_id} with {provider.provider_name}")

        # Run async provider in sync context (tasks.py is called from sync background)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(
                provider.transcribe_with_diarization(audio_path, language=language)
            )
        finally:
            loop.close()

        if not result.segments:
            logger.warning(f"[Offline ASR] Empty result for {meeting_id}, keeping Gemini transcript")
            meeting.status = MeetingStatus.COMPLETED
            db.commit()
            _update_task_status(db, meeting_id, "offline_asr", "COMPLETED", "Empty result, kept Gemini transcript")
            return {"status": "completed", "note": "empty_result_kept_gemini"}

        # Replace DB segments with high-quality offline ASR results
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
                content_polished=seg.text,  # Breeze ASR output is high quality
                is_final=True,
            )
            new_segments.append(new_seg)

        db.add_all(new_segments)

        # Update transcript_raw with speaker-labeled text
        meeting.transcript_raw = result.to_transcript_text(include_speaker=True)
        meeting.status = MeetingStatus.COMPLETED
        db.commit()

        _update_task_status(
            db, meeting_id, "offline_asr", "COMPLETED",
            f"{len(new_segments)} segments, {result.num_speakers} speakers, {result.duration:.1f}s"
        )

        logger.info(
            f"[Offline ASR] Refinement complete for {meeting_id}: "
            f"{len(new_segments)} segments, {result.num_speakers} speakers"
        )
        return {"status": "completed", "meeting_id": meeting_id, "segments": len(new_segments)}

    except Exception as e:
        logger.error(f"[Offline ASR] Failed for {meeting_id}: {e}", exc_info=True)
        try:
            if meeting:
                meeting.status = MeetingStatus.COMPLETED  # Fallback: keep Gemini transcript
                db.commit()
            _update_task_status(db, meeting_id, "offline_asr", "FAILED", str(e))
        except Exception:
            pass
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()



def generate_summary_core(meeting_id: str, template_type: str = "general", context: str = "", length: str = "", style: str = "", skip_asr: bool = False, suppress_fail_notification: bool = False):
    """
    Core logic for meeting processing:
    1. Run offline ASR refinement (Breeze ASR via OfflineASRProvider) if audio exists.
    2. Update DB with new segments.
    3. Generate summary using LLM (Gemini Direct).
    
    Can be called directly or via Cloud Tasks HTTP handler.
    """
    # Template Key Mapping: Frontend keys -> LLM service keys
    TEMPLATE_KEY_MAP = {
        "bant": "sales_bant",
        "star": "hr_star",
        "rd": "rd",
        "general": "general"
    }
    # Apply mapping (fallback to original if not in map)
    llm_template = TEMPLATE_KEY_MAP.get(template_type, template_type)
    
    logger.info(f"Starting CORE meeting processing for {meeting_id} (Template: {template_type} -> {llm_template})")
    
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            logger.error(f"Meeting {meeting_id} not found.")
            return {"status": "failed", "error": "Meeting not found"}

        # 1. Run Offline ASR Refinement (if audio exists and not skipped)
        if meeting.audio_url and not skip_asr:
            gpu_asr_url = os.getenv("GPU_ASR_SERVICE_URL")
            logger.info(f"[DEBUG] GPU_ASR_SERVICE_URL env value: '{gpu_asr_url}'")
            if gpu_asr_url:
                logger.info(f"GPU_ASR_SERVICE_URL is set ({gpu_asr_url}). Triggering remote GPU ASR refinement...")
                
                # Set status to PROCESSING immediately so frontend can track
                meeting.status = MeetingStatus.PROCESSING
                db.commit()
                logger.info(f"Set meeting {meeting_id} status to PROCESSING")
                
                try:
                    import httpx
                    
                    # Generate public callback URL for GPU to hit back
                    backend_public_url = os.getenv("BACKEND_PUBLIC_URL", "http://localhost:8000")
                    callback_url = f"{backend_public_url.rstrip('/')}/api/v1/callbacks/asr-done"
                    
                    # GPU ASR timeout must match Cloud Run Service timeout (3600s)
                    # GPU processes audio synchronously and returns result + hits callback
                    with httpx.Client(timeout=3600.0) as client:
                        response = client.post(
                            f"{gpu_asr_url.rstrip('/')}/asr/refine",
                            json={
                                "meeting_id": meeting_id,
                                "audio_url": meeting.audio_url,
                                "language": meeting.language or "zh",
                                "callback_url": callback_url
                            }
                        )
                        response.raise_for_status()
                        result_data = response.json()
                        logger.info(f"Triggered remote GPU ASR: status {result_data.get('status')}")
                        
                        _update_task_status(db, meeting_id, "offline_asr", "IN_PROGRESS", 
                                            f"Triggered remote GPU ASR. Awaiting callback at {callback_url}")
                        
                        # Return 'accepted' so Cloud Tasks/Background Tasks can finish the current worker
                        return {"status": "accepted", "meeting_id": meeting_id, "message": "GPU ASR Refinement started in background"}
                        
                except Exception as e:
                    logger.error(f"Remote GPU ASR trigger failed for meeting {meeting_id}: {e}")
                    if not suppress_fail_notification:
                        meeting.status = MeetingStatus.FAILED
                        db.commit()
                    _update_task_status(db, meeting_id, "offline_asr", "FAILED", f"Remote trigger error: {str(e)}")
                    # Return 'failed' so the cloud task handler will return 500 and trigger a retry
                    return {"status": "failed", "error": f"Remote GPU ASR trigger failed: {str(e)}"}
            else:
                logger.info("GPU_ASR_SERVICE_URL not set. Running local offline ASR refinement...")
                audio_path = meeting.audio_url
                # Handle GCS URLs: download to temp file first
                if audio_path.startswith("gs://"):
                    logger.info(f"Audio is on GCS: {audio_path}. Downloading for offline ASR...")
                    try:
                        from google.cloud import storage as gcs_storage
                        import tempfile

                        # Parse gs:// URL
                        parts = audio_path.replace("gs://", "").split("/", 1)
                        bucket_name = parts[0]
                        blob_name = parts[1] if len(parts) > 1 else ""

                        client = gcs_storage.Client()
                        bucket = client.bucket(bucket_name)
                        blob = bucket.blob(blob_name)

                        # Download to temp file
                        temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")
                        os.makedirs(temp_dir, exist_ok=True)
                        local_path = os.path.join(temp_dir, os.path.basename(blob_name))
                        blob.download_to_filename(local_path)
                        audio_path = local_path
                        logger.info(f"Downloaded audio to: {audio_path}")
                    except Exception as e:
                        logger.error(f"Failed to download audio from GCS: {e}")
                        audio_path = None

                if audio_path and os.path.exists(audio_path):
                    logger.info(f"Audio found: {audio_path}. Running offline ASR refinement...")
                    language = meeting.language or "zh"
                    asr_result = run_offline_asr_refinement(meeting_id, audio_path, language)
                    logger.info(f"Offline ASR result: {asr_result}")

                    # Clean up temp file if we downloaded from GCS
                    if meeting.audio_url.startswith("gs://") and audio_path != meeting.audio_url:
                        try:
                            os.remove(audio_path)
                        except Exception:
                            pass
                else:
                    logger.warning(f"Audio file not accessible: {meeting.audio_url}")
        else:
            logger.warning("No audio file found. Skipping offline ASR refinement.")

        # 2. Generate Summary (using whatever segments are in DB now)
        # Re-query meeting to get updated segments
        db.refresh(meeting)
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.meeting_id == meeting_id
        ).order_by(TranscriptSegment.order).all()
        
        if not segments:
            logger.warning(f"No transcript segments found for meeting {meeting_id}")
            return {"status": "skipped", "reason": "empty_transcript"}

        # Construct text with Speaker Labels
        lines = []
        for seg in segments:
            label = f"[{seg.speaker}] " if seg.speaker else ""
            content = seg.content_polished or seg.content_raw
            lines.append(f"{label}{content}")
        transcript_text = "\n".join(lines)

        # Construct extra instructions
        extra_instructions = []
        if context:
            extra_instructions.append(f"背景知識與關鍵字：{context}")
        if length:
            extra_instructions.append(f"摘要長度：{length} (short=簡短, medium=適中, long=詳細)")
        if style:
            extra_instructions.append(f"摘要風格：{style} (formal=正式, casual=口語)")
        
        extra_instructions_str = "\n".join(extra_instructions)

        # Call Gemini Direct via llm_utils
        try:
            client = get_gemini_client()
            if not client:
                raise Exception("Gemini Client initialization failed")

            summary_data = generate_summary(
                client=client,
                text=transcript_text,
                template_name=llm_template,
                extra_instructions=extra_instructions_str
            )
            
            # Check for error in response (covers both {"error": ...} and {"error": ..., "raw_text": ...})
            if "error" in summary_data:
                 raise Exception(summary_data["error"])

            meeting.summary_json = json.dumps(summary_data, ensure_ascii=False)
            # Store full text snapshot
            meeting.transcript_raw = transcript_text
            
            # Phase 8.1: Auto-populate speaker_mappings from CoT speaker_roles
            speaker_roles = summary_data.get("speaker_roles")
            if speaker_roles and not meeting.speaker_mappings:
                SPEAKER_COLORS = [
                    "#5FB7AC", "#2D428B", "#48B070", "#E4831A",
                    "#D2343D", "#EDD414", "#513A57", "#1E455E"
                ]
                mappings = {}
                for i, sr in enumerate(speaker_roles):
                    sid = sr.get("speaker_id", f"Speaker_{i}")
                    mappings[sid] = {
                        "display_name": sr.get("display_name", sid),
                        "role": sr.get("role", "未知"),
                        "color": SPEAKER_COLORS[i % len(SPEAKER_COLORS)]
                    }
                meeting.speaker_mappings = json.dumps(mappings, ensure_ascii=False)
                logger.info(f"Auto-populated speaker_mappings for {meeting_id}: {len(mappings)} speakers")
            
            meeting.status = MeetingStatus.COMPLETED
            
            db.commit()
            logger.info(f"Successfully generated summary for {meeting_id}")
            
            # Phase RAG: Auto-embed transcript segments + summary for cross-meeting search
            try:
                seg_count = embed_transcript_segments(db, meeting_id)
                sum_ok = embed_meeting_summary(db, meeting_id)
                logger.info(f"[Embedding] Auto-embed complete: {seg_count} segments, summary={'OK' if sum_ok else 'SKIP'}")
            except Exception as emb_err:
                # Embedding failure must NOT break the core pipeline
                logger.warning(f"[Embedding] Auto-embed failed (non-fatal): {emb_err}")
            
            # Phase 9.2: Fire-and-forget Discord notification
            send_completion_notification(meeting, "completed")
            
            return {"status": "completed", "meeting_id": meeting_id}

        except Exception as e:
             logger.error(f"Error calling Gemini Service: {e}")
             if not suppress_fail_notification:
                 meeting.status = MeetingStatus.FAILED
                 db.commit()
                 send_completion_notification(meeting, "failed")
             else:
                 logger.info(f"Suppressed FAILED status and Discord notification for {meeting_id} (Cloud Tasks will retry)")
             return {"status": "failed", "error": str(e)}

    except Exception as e:
        logger.error(f"Unexpected error in generate_summary_core: {e}")
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


def generate_meeting_minutes(meeting_id: str, template_type: str = "general", context: str = "", length: str = "", style: str = "", skip_asr: bool = False, suppress_fail_notification: bool = False):
    """
    Wrapper function for backward compatibility.
    Previously was a Celery task, now a direct function call.
    Can be invoked via Cloud Tasks HTTP handler or directly.
    """
    return generate_summary_core(meeting_id, template_type, context, length, style, skip_asr=skip_asr, suppress_fail_notification=suppress_fail_notification)