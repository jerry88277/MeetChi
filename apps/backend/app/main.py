from fastapi import FastAPI, Depends, HTTPException, WebSocket, WebSocketDisconnect, status, BackgroundTasks
from fastapi.responses import JSONResponse # Import JSONResponse
from fastapi.middleware.cors import CORSMiddleware # Import CORSMiddleware
from sqlalchemy import create_engine, String, DateTime, Text, Enum, Float, Boolean, Integer, desc # Import missing types
from sqlalchemy.orm import sessionmaker, Session, relationship # Import relationship for eager loading
from sqlalchemy.ext.declarative import declarative_base # Need to re-declare Base
from sqlalchemy import Column, ForeignKey # Need Column and ForeignKey
from sqlalchemy.orm import selectinload # New: For eager loading relationships

import os
import io
import asyncio
import numpy as np
import logging
import httpx # For async HTTP requests
import uuid # For UUID generation
from datetime import datetime # For datetime fields
from dotenv import load_dotenv
import time
import json
import sys
from logging.handlers import TimedRotatingFileHandler
from pydantic import BaseModel, Field
from typing import List, Optional
import wave # <-- New import

# --- Logging Configuration ---
LOG_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "log")
os.makedirs(LOG_DIR, exist_ok=True)
logger = logging.getLogger()
logger.setLevel(logging.INFO)
if logger.hasHandlers():
    logger.handlers.clear()
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)
log_filename = os.path.join(LOG_DIR, "backend.log")
file_handler = TimedRotatingFileHandler(log_filename, when="midnight", interval=1, backupCount=7, encoding="utf-8")
file_handler.suffix = "%Y-%m-%d"
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
app_logger = logging.getLogger(__name__)

# --- App Initialization ---
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# --- Re-declare Base if needed, or import from models.py ---
# Assuming Base is already declared in models.py and imported via 'from app.models import Base, ...'
from app.models import Base, Meeting, TranscriptSegment, Artifact, TaskStatus # Import all relevant models
from app.vad import VADAudioBuffer
from scripts.transcribe_sprint0 import get_transcription, load_asr_model, logger as asr_logger 

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./sql_app.db")
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://localhost:5000")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from app.celery_app import celery_app
from app.tasks import generate_meeting_minutes # Assuming this task exists

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Pydantic Models for API ---
class TranscriptSegmentRead(BaseModel):
    id: str
    order: int
    start_time: float
    end_time: float
    speaker: Optional[str]
    content_raw: str
    content_polished: Optional[str]
    content_translated: Optional[str]
    is_final: bool

    class Config:
        from_attributes = True

class TranscriptSegmentCreate(BaseModel):
    id: Optional[str] = None
    order: int
    start_time: float
    end_time: float
    speaker: Optional[str] = None
    content_raw: str
    content_polished: Optional[str] = None
    content_translated: Optional[str] = None
    is_final: bool

class MeetingRead(BaseModel):
    id: str
    title: str
    status: str
    created_at: datetime
    updated_at: datetime
    duration: Optional[float]
    audio_url: Optional[str]
    language: str
    template_name: str
    transcript_raw: Optional[str]
    transcript_polished: Optional[str]
    summary_json: Optional[str]
    
    transcript_segments: List[TranscriptSegmentRead] = [] # Include segments for detail view

    class Config:
        from_attributes = True

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    language: str = Field("zh", min_length=2, max_length=10)
    template_name: str = Field("general", min_length=1, max_length=50)

class SummarizeRequestModel(BaseModel):
    transcript: str
    template_name: str = "general"

class SummarizeResponseModel(BaseModel):
    summary: str
    action_items: List[str]
    decisions: List[str]
    risks: List[str]


# --- API Endpoints ---

@app.post("/api/v1/meetings", response_model=MeetingRead, status_code=status.HTTP_201_CREATED)
async def create_meeting(meeting_data: MeetingCreate, db: Session = Depends(get_db)):
    """
    Creates a new meeting entry.
    """
    db_meeting = Meeting(
        title=meeting_data.title,
        language=meeting_data.language,
        template_name=meeting_data.template_name
    )
    db.add(db_meeting)
    db.commit()
    db.refresh(db_meeting) # Refresh to get ID and other defaults
    return MeetingRead.from_orm(db_meeting) # Return Pydantic model

@app.get("/api/v1/meetings", response_model=List[MeetingRead])
async def list_meetings(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """
    List historical meetings.
    """
    meetings = db.query(Meeting).options(
        # Load segments if needed, or keep it light for list view
        # selectinload(Meeting.transcript_segments)
    ).order_by(desc(Meeting.created_at)).offset(skip).limit(limit).all()
    return [MeetingRead.from_orm(m) for m in meetings]

@app.get("/api/v1/meetings/{meeting_id}", response_model=MeetingRead)
async def get_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """
    Get meeting details including transcript and summary.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).options(
        selectinload(Meeting.transcript_segments), # Eager load segments
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return MeetingRead.from_orm(meeting)

@app.post("/api/v1/meetings/{meeting_id}/add_segments")
async def add_transcript_segments(meeting_id: str, segments: List[TranscriptSegmentCreate], db: Session = Depends(get_db)):
    """
    Adds a list of transcript segments to a specific meeting.
    This is typically called after a recording has finished.
    """
    db_meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not db_meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    new_segments = []
    for segment_data in segments:
        data = segment_data.dict(exclude_unset=True)
        if "id" not in data or data["id"] is None:
            data["id"] = str(uuid.uuid4())
        new_segment = TranscriptSegment(**data, meeting_id=meeting_id) # Assign meeting_id
        db.add(new_segment)
        new_segments.append(new_segment)
    
    db.commit()
    db.refresh(db_meeting) 
    return {"message": f"Added {len(new_segments)} segments to meeting {meeting_id}"}


@app.post("/api/v1/meetings/{meeting_id}/generate-summary")
def trigger_summary_generation(
    meeting_id: str, 
    template_type: str = "general", 
    context: str = "",
    length: str = "medium",
    style: str = "formal",
    background_tasks: BackgroundTasks = None, 
    db: Session = Depends(get_db)
):
    """
    Trigger background task to generate meeting minutes.
    FORCE FALLBACK MODE: Skip Celery to avoid Redis connection timeouts in dev environment without Redis.
    """
    app_logger.info(f"Triggering local background summary for {meeting_id}")
    
    # Fallback: Run in background task (local thread)
    from app.tasks import generate_summary_core
    background_tasks.add_task(generate_summary_core, meeting_id, template_type, context, length, style)
    
    return JSONResponse(
        content={"message": "Summary generation started (Local Force)", "task_id": "local-force"},
        status_code=status.HTTP_200_OK
    )

CORRECTIONS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "corrections.json")

@app.get("/api/v1/settings/corrections")
async def get_corrections():
    """Get current keyword correction rules."""
    if os.path.exists(CORRECTIONS_CONFIG_PATH):
        with open(CORRECTIONS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

@app.post("/api/v1/settings/corrections")
async def update_corrections(corrections: dict):
    """Update keyword correction rules."""
    try:
        with open(CORRECTIONS_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(corrections, f, ensure_ascii=False, indent=4)
        return {"message": "Corrections updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save corrections: {e}")

@app.delete("/api/v1/meetings/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(meeting_id: str, db: Session = Depends(get_db)):
    """
    Delete a meeting and its associated resources (audio file, transcripts).
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # 1. Delete Audio File
    if meeting.audio_url and os.path.exists(meeting.audio_url):
        try:
            os.remove(meeting.audio_url)
            app_logger.info(f"Deleted audio file: {meeting.audio_url}")
        except Exception as e:
            app_logger.error(f"Failed to delete audio file {meeting.audio_url}: {e}")

    # 2. Delete Transcripts (Cascade delete handles this usually, but let's be explicit if needed)
    # SQLAlchemy relationship with cascade="all, delete" is preferred, but manual for now:
    db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()
    
    # 3. Delete Meeting Record
    db.delete(meeting)
    db.commit()
    
    return None

@app.post("/api/v1/summarize", response_model=SummarizeResponseModel)
async def summarize_full_transcript(request_data: SummarizeRequestModel):
    """
    Triggers a summarization task for a full transcript using the LLM service.
    """
    app_logger.info(f"Received summarization request for transcript (len: {len(request_data.transcript)}) with template: {request_data.template_name}")
    try:
        async with httpx.AsyncClient() as client:
            llm_response = await client.post(
                f"{LLM_SERVICE_URL}/summarize",
                json={
                    "text": request_data.transcript,
                    "template_name": request_data.template_name
                },
                timeout=120.0 # Longer timeout for summarization
            )
            llm_response.raise_for_status()
            summary_data = llm_response.json()
            
            return SummarizeResponseModel(
                summary=summary_data.get("summary", "無法生成摘要。"),
                action_items=summary_data.get("action_items", []),
                decisions=summary_data.get("decisions", []),
                risks=summary_data.get("risks", [])
            )
    except Exception as e:
        app_logger.error(f"Error calling LLM /summarize service: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate summary: {e}")


# Load ASR model during startup
@app.on_event("startup")
async def on_startup():
    app_logger.info("Application startup event triggered.")
    Base.metadata.create_all(bind=engine)
    app_logger.info("Database tables checked/created.")
    
    app_logger.info("Pre-loading ASR model...")
    try:
        await asyncio.to_thread(load_asr_model)
        app_logger.info("ASR model pre-loaded successfully.")
    except Exception as e:
        app_logger.critical(f"Failed to pre-load ASR model during startup: {e}")
        raise RuntimeError("ASR model pre-loading failed. Cannot start application.") from e

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.get("/db-test")
def db_test(db: Session = Depends(get_db)):
    try:
        db.scalar("SELECT 1")
        return {"message": "Database connection successful!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database connection failed: {e}")

async def polish_transcription_task(segment_id: str, transcript_text: str, previous_context: str, source_lang: str, target_lang: str, websocket: WebSocket):
    """
    Async task to call LLM service for polishing and send result back to WebSocket.
    Includes previous_context for better semantic accuracy.
    """
    try:
        async with httpx.AsyncClient() as client:
            llm_response = await client.post(
                f"{LLM_SERVICE_URL}/polish",
                json={
                    "text": transcript_text,
                    "previous_context": previous_context,
                    "source_lang": source_lang,
                    "target_lang": target_lang
                },
                timeout=30.0 
            )
            llm_response.raise_for_status() 
            polished_data = llm_response.json()
            
            # New format: {'refined': '...', 'translated': '...'}
            # Fallback to 'polished_text' or raw text if keys missing
            refined_text = polished_data.get("refined", polished_data.get("polished_text", transcript_text))
            translated_text = polished_data.get("translated", "")

            # DEFENSIVE CODING: Ensure these are strings, not dicts
            if isinstance(refined_text, dict):
                refined_text = refined_text.get('content', str(refined_text))
            if isinstance(translated_text, dict):
                translated_text = translated_text.get('content', str(translated_text))
            
            refined_text = str(refined_text)
            translated_text = str(translated_text)

            app_logger.info(f"Polished [{segment_id}]: {refined_text} | Translated: {translated_text}")

            # Send polished transcript to frontend
            try:
                await websocket.send_json({
                    "type": "polished",
                    "id": segment_id,
                    "content": refined_text, 
                    "translated": translated_text
                })
            except RuntimeError as e:
                # WebSocket might be closed/disconnected
                app_logger.warning(f"Could not send polished text, websocket probably closed: {e}")
            except Exception as e:
                app_logger.error(f"Error sending polished text via websocket: {e}")

    except Exception as e:
        app_logger.error(f"Polishing task failed for segment {segment_id}: {e}")
        # Optionally notify frontend of error
        try:
            await websocket.send_json({
                "type": "error",
                "id": segment_id,
                "content": "Polishing failed."
            })
        except:
            pass

# WebSocket Endpoint for Real-time Transcription
@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket, db: Session = Depends(get_db)): # Inject DB session
    await websocket.accept()
    app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} connected for transcription.")

    # --- Audio Recording Setup ---
    AUDIO_SAVE_DIR = os.path.join(os.path.dirname(__file__), "..", "transcribe", "audio")
    os.makedirs(AUDIO_SAVE_DIR, exist_ok=True) # Ensure dir exists
    audio_file_path = os.path.join(AUDIO_SAVE_DIR, f"{uuid.uuid4()}.wav")
    wav_file = None 
    
    # Store meeting_id received from frontend for associating audio
    current_meeting_id: Optional[str] = None

    # Initialize VAD Buffer (Defaults from vad.py: 5.0s max)
    RATE = 16000
    CHANNELS = 1
    SAMPLE_WIDTH = 2 # 16-bit audio
    vad_buffer = VADAudioBuffer(
        sample_rate=RATE, 
        silence_threshold=0.3, 
        min_silence_duration=0.6, 
        max_duration=7
    )
    
    # Pseudo-streaming state
    last_partial_time = time.time()
    current_segment_id = str(uuid.uuid4())
    previous_context = "" # Store the last finalized transcript for context
    
    # --- Overlapping Window Buffer ---
    # Store history of processed audio to prepend to next segment
    # Set to 0.0 to prevent duplication issues, relying on VAD to split at silence.
    OVERLAP_DURATION_SECONDS = 0.0 
    last_flushed_segment_np = np.array([], dtype=np.float32) # Store the last VAD-flushed segment
    
    # Language Configuration (Default: ZH -> EN)
    source_lang = "zh"
    target_lang = "en"
    
    # Custom Initial Prompt from Frontend
    custom_initial_prompt = ""
    
    first_audio_time = None # Track time of first audio packet

    try:
        while True:
            # Receive message (can be text or bytes)
            message = await websocket.receive()
            
            # 1. Handle Configuration Messages (Text)
            if "text" in message:
                try:
                    config = json.loads(message["text"])
                    if config.get("type") == "config":
                        source_lang = config.get("source_lang", source_lang)
                        target_lang = config.get("target_lang", target_lang)
                        custom_initial_prompt = config.get("initial_prompt", "")
                        # Receive meeting_id from frontend (essential for saving audio_url)
                        if "meeting_id" in config:
                            current_meeting_id = config["meeting_id"]
                            app_logger.info(f"Received meeting_id: {current_meeting_id}")
                        
                        if "overlap_duration" in config:
                            OVERLAP_DURATION_SECONDS = float(config["overlap_duration"])
                            
                        app_logger.info(f"Config updated: {source_lang} -> {target_lang} | Prompt len: {len(custom_initial_prompt)} | Overlap: {OVERLAP_DURATION_SECONDS}")
                except Exception as e:
                    app_logger.error(f"Failed to parse config message: {e}")
                continue # Skip audio processing for this loop iteration

            # 2. Handle Audio Data (Bytes)
            if "bytes" in message:
                data = message["bytes"]
                if first_audio_time is None:
                    first_audio_time = time.time()
                    app_logger.info("First audio packet received. Starting forced speech window.")
                
                # --- Audio File Writing ---
                if wav_file is None:
                    wav_file = wave.open(audio_file_path, 'wb')
                    wav_file.setnchannels(CHANNELS)
                    wav_file.setsampwidth(SAMPLE_WIDTH)
                    wav_file.setframerate(RATE)
                    app_logger.info(f"Opened WAV file for writing: {audio_file_path}")
                wav_file.writeframes(data) # Write raw bytes
                # --- End Audio File Writing ---

            else:
                continue # Should not happen if receive() returns correctly
            
            # Process chunk with VAD
            # Force speech for the first 3.0 seconds to prevent initial clipping
            is_initial_phase = False
            if first_audio_time is not None:
                is_initial_phase = (time.time() - first_audio_time) < 3.0
            
            # Returns bytes only if a split point (silence or max duration) is reached
            audio_bytes = vad_buffer.process_chunk(data, force_speech=is_initial_phase)

            # --- Partial Transcription (Every 2.0s) ---
            now = time.time()
            if not audio_bytes and (now - last_partial_time) > 2.0:
                snapshot_bytes = vad_buffer.snapshot()
                if snapshot_bytes:
                    snapshot_np = np.frombuffer(snapshot_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    # Only transcribe if we have at least 1s of audio to avoid noise hallucinations
                    if snapshot_np.size > 16000:
                        # Use previous_context as initial_prompt for ASR consistency
                        combined_prompt = f"{custom_initial_prompt} {previous_context}".strip()
                        partial_text = await asyncio.to_thread(get_transcription, snapshot_np, source_lang, combined_prompt)
                        # Filter extremely short partials
                        if partial_text and len(partial_text.strip()) > 1:
                            await websocket.send_json({
                                "type": "partial",
                                "id": current_segment_id,
                                "content": partial_text
                            })
                        last_partial_time = now

            # --- Final Transcription (Split Event) ---
            if audio_bytes:
                audio_np_current = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                audio_for_transcription = audio_np_current
                # Prepend overlap from the last flushed segment
                if last_flushed_segment_np.size > 0:
                    overlap_samples = int(OVERLAP_DURATION_SECONDS * RATE)
                    overlap_from_previous = last_flushed_segment_np[-min(overlap_samples, last_flushed_segment_np.size):]
                    audio_for_transcription = np.concatenate((overlap_from_previous, audio_np_current))
                
                # Update last flushed segment for next overlap
                last_flushed_segment_np = audio_np_current
                
                if audio_for_transcription.size > 0:
                    app_logger.info(f"Transcribing {len(audio_for_transcription)/RATE:.2f} seconds of audio (VAD split with overlap)...")
                    
                    # Use previous_context as initial_prompt for ASR consistency
                    combined_prompt = f"{custom_initial_prompt} {previous_context}".strip()
                    
                    try:
                        # Add a timeout for ASR transcription to prevent service hang
                        # Longer timeout (e.g., 10s) to accommodate potentially slow ASR or longer segments
                        transcript_text = await asyncio.wait_for(
                            asyncio.to_thread(get_transcription, audio_for_transcription, source_lang, combined_prompt),
                            timeout=20.0 
                        )
                        app_logger.info(f"ASR Output: '{transcript_text}'") # Log ASR output for debugging
                    except asyncio.TimeoutError:
                        app_logger.error(f"ASR transcription timed out for segment {current_segment_id}. Skipping segment.")
                        transcript_text = "" # Treat as empty on timeout
                    except Exception as e:
                        app_logger.error(f"Error during ASR transcription for segment {current_segment_id}: {e}", exc_info=True)
                        transcript_text = "" # Treat as empty on error
                    
                    if transcript_text:
                        app_logger.info(f"Raw Transcription [{current_segment_id}]: {transcript_text}")

                        # 1. Send raw transcript (Finalize the segment)
                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": transcript_text
                        })

                        # 2. Call LLM service asynchronously (Non-blocking)
                        # Pass previous_context AND language settings
                        asyncio.create_task(polish_transcription_task(
                            current_segment_id, 
                            transcript_text, 
                            previous_context, 
                            source_lang,
                            target_lang,
                            websocket
                        ))
                        
                        # Update context for next segment
                        previous_context = transcript_text
                        
                        # Prepare for next segment
                        current_segment_id = str(uuid.uuid4())
                        last_partial_time = time.time()

                    else:
                        app_logger.info(f"Received empty transcription from ASR for [{current_segment_id}]. Clearing partial.")
                        # Send empty raw to finalize/clear the partial on frontend
                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": "" 
                        })
                        # Reset ID anyway to prevent Partial ghosting if previous was noise
                        current_segment_id = str(uuid.uuid4())
                        last_partial_time = time.time()

    except WebSocketDisconnect:
        app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} disconnected.")
    except RuntimeError as e:
        # Starlette/FastAPI might raise RuntimeError on receive if disconnected
        if "disconnect message" in str(e):
            app_logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} disconnected (RuntimeError).")
        else:
            app_logger.error(f"WebSocket Runtime error: {e}", exc_info=True)
    except Exception as e:
        app_logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        if wav_file:
            wav_file.close()
            app_logger.info(f"Closed WAV file: {audio_file_path}")
            
            # Update Meeting's audio_url
            if current_meeting_id:
                meeting_to_update = db.query(Meeting).filter(Meeting.id == current_meeting_id).first()
                if meeting_to_update:
                    meeting_to_update.audio_url = audio_file_path
                    db.commit()
                    app_logger.info(f"Updated meeting {current_meeting_id} with audio_url: {audio_file_path}")