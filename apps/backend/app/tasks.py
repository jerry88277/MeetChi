from app.celery_app import celery_app
import logging
import os
import json
import httpx
import subprocess
import sys
from sqlalchemy.orm import Session
from app.models import Meeting, TranscriptSegment, MeetingStatus
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load env to get HF_AUTH_TOKEN
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# Database Setup
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:5000")
HF_AUTH_TOKEN = os.getenv("HF_AUTH_TOKEN")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

WHISPERX_SCRIPT_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scripts", "exec_whisperx_task_v1.2.py")
TRANSCRIBE_OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "transcribe", "json")

def generate_summary_core(meeting_id: str, template_type: str = "general", context: str = "", length: str = "", style: str = ""):
    """
    Core logic: 
    1. Run WhisperX script for high-quality transcription + diarization.
    2. Update DB with new segments.
    3. Generate summary using LLM.
    """
    logger.info(f"Starting CORE meeting processing for {meeting_id} (Template: {template_type})")
    
    db = SessionLocal()
    try:
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            logger.error(f"Meeting {meeting_id} not found.")
            return {"status": "failed", "error": "Meeting not found"}

        # 1. Run WhisperX (if audio exists)
        if meeting.audio_url and os.path.exists(meeting.audio_url):
            logger.info(f"Audio found: {meeting.audio_url}. Running WhisperX...")
            
            # Prepare environment for subprocess
            env = os.environ.copy()
            if HF_AUTH_TOKEN:
                env["HF_TOKEN"] = HF_AUTH_TOKEN
            
            # Run script: python script.py "filename.wav" "1"
            # Simpler: Copy audio to `apps/backend/upload`
            upload_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "upload")
            os.makedirs(upload_dir, exist_ok=True)
            
            audio_filename = os.path.basename(meeting.audio_url)
            target_audio_path = os.path.join(upload_dir, audio_filename)
            
            import shutil
            if meeting.audio_url != target_audio_path:
                shutil.copy2(meeting.audio_url, target_audio_path)
                logger.info(f"Copied audio to upload dir: {target_audio_path}")

            try:
                # Execute WhisperX Script using the current python interpreter
                cmd = [sys.executable, WHISPERX_SCRIPT_PATH, audio_filename, "1"]
                logger.info(f"Executing: {" ".join(cmd)}")
                
                # We use the current python interpreter
                process = subprocess.run(
                    cmd, 
                    env=env,
                    capture_output=True,
                    text=True,
                    encoding='utf-8' 
                )
                
                if process.returncode != 0:
                    logger.error(f"WhisperX failed: {process.stderr}")
                else:
                    logger.info("WhisperX completed successfully.")
                    
                    # 2. Parse JSON Output and Update DB
                    json_filename = os.path.splitext(audio_filename)[0] + ".json"
                    json_path = os.path.join(TRANSCRIBE_OUTPUT_DIR, json_filename)
                    
                    if os.path.exists(json_path):
                        with open(json_path, 'r', encoding='utf-8') as f:
                            whisper_data = json.load(f)
                        
                        # Clear existing segments (Real-time ones are inferior)
                        db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()
                        
                        new_segments = []
                        for idx, seg in enumerate(whisper_data['segments']):
                            # Handle speaker label
                            speaker = seg.get('speaker', None)
                            
                            new_seg = TranscriptSegment(
                                meeting_id=meeting_id,
                                order=idx,
                                start_time=seg['start'],
                                end_time=seg['end'],
                                speaker=speaker,
                                content_raw=seg['text'],
                                content_polished=seg['text'], # Assume WhisperX output is good enough
                                is_final=True
                            )
                            new_segments.append(new_seg)
                        
                        db.add_all(new_segments)
                        db.commit()
                        logger.info(f"Updated DB with {len(new_segments)} high-quality segments.")
                    else:
                        logger.error(f"WhisperX output JSON not found: {json_path}")

            except Exception as e:
                logger.error(f"Error executing WhisperX: {e}")

        else:
            logger.warning("No audio file found. Skipping WhisperX refinement.")

        # 3. Generate Summary (using whatever segments are in DB now)
        segments = db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).order_by(TranscriptSegment.order).all()
        
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

        # Call LLM Service
        try:
            with httpx.Client(timeout=180.0) as client: 
                response = client.post(
                    f"{LLM_SERVICE_URL}/summarize",
                    json={
                        "text": transcript_text,
                        "template_name": template_type,
                        "extra_instructions": extra_instructions_str
                    }
                )
                response.raise_for_status()
                summary_data = response.json()
                
                meeting.summary_json = json.dumps(summary_data, ensure_ascii=False)
                # Store full text snapshot
                meeting.transcript_raw = transcript_text
                
                db.commit()
                logger.info(f"Successfully generated summary for {meeting_id}")
                
                return {"status": "completed", "meeting_id": meeting_id}

        except Exception as e:
             logger.error(f"Error calling LLM Service: {e}")
             return {"status": "failed", "error": str(e)}

    except Exception as e:
        logger.error(f"Unexpected error in generate_summary_core: {e}")
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()

@celery_app.task(bind=True)
def generate_meeting_minutes(self, meeting_id: str, template_type: str = "general"):
    """
    Celery wrapper task.
    """
    return generate_summary_core(meeting_id, template_type)