"""
WebSocket route — real-time audio transcription.

Endpoint: /ws/transcribe

Flow:
  Frontend → audio chunks (16kHz PCM16) → VAD buffer → Gemini ASR
    → optional Smith-Waterman alignment (script mode)
    → optional Gemini polish/translate (transcription mode)
    → push back to client

Heartbeat ping/pong every 25s defends against Cloud Run proxy idle timeout.
"""

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Meeting
from app.vad import VADAudioBuffer
from app.llm_utils import get_gemini_client, polish_text
from app.aligner import MultiSpeakerScriptAligner
from app.asr_helpers import get_transcription_gemini, correct_keywords

logger = logging.getLogger(__name__)
router = APIRouter()


async def polish_transcription_task(
    segment_id: str,
    transcript_text: str,
    previous_context: str,
    source_lang: str,
    target_lang: str,
    websocket: WebSocket,
):
    """Async task to call Gemini for polishing and send result back to WebSocket."""
    try:
        client = get_gemini_client()
        if not client:
            raise Exception("Gemini client unavailable")

        def _run_polish():
            return polish_text(
                client=client,
                raw_text=transcript_text,
                source_lang=source_lang,
                target_lang=target_lang,
            )

        polished_data = await asyncio.to_thread(_run_polish)

        if "error" in polished_data:
            raise Exception(polished_data["error"])

        refined_text = polished_data.get("polished_text", transcript_text)
        translated_text = polished_data.get("translated", "")

        logger.info(f"Polished [{segment_id}]: {refined_text} | Translated: {translated_text}")

        try:
            await websocket.send_json({
                "type": "polished",
                "id": segment_id,
                "content": refined_text,
                "translated": translated_text,
            })
        except RuntimeError as e:
            logger.warning(f"Could not send polished text, websocket probably closed: {e}")
        except Exception as e:
            logger.error(f"Error sending polished text via websocket: {e}")

    except Exception as e:
        logger.error(f"Polishing task failed for segment {segment_id}: {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "id": segment_id,
                "content": "Polishing failed.",
            })
        except Exception:
            pass


@router.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket, db: Session = Depends(get_db)):
    """Real-time transcription endpoint."""
    await websocket.accept()
    logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} connected for transcription.")

    # Audio is managed by frontend IndexedDB and uploaded via REST API.
    # The WebSocket is strictly stateless for live transcription.

    current_meeting_id: Optional[str] = None

    # Initialize VAD Buffer
    RATE = 16000
    vad_buffer = VADAudioBuffer(
        sample_rate=RATE,
        silence_threshold=0.3,
        min_silence_duration=0.6,
        max_duration=7,
    )

    # Pseudo-streaming state
    last_partial_time = time.time()
    current_segment_id = str(uuid.uuid4())
    previous_context = ""

    # Overlapping window buffer (currently 0.0 — VAD splits at silence)
    OVERLAP_DURATION_SECONDS = 0.0
    last_flushed_segment_np = np.array([], dtype=np.float32)

    # Language config (default: ZH -> EN)
    source_lang = "zh"
    target_lang = "en"

    custom_initial_prompt = ""
    operation_mode = "transcription"
    script_aligner = MultiSpeakerScriptAligner()

    first_audio_time = None
    current_meeting_id = None

    # WebSocket heartbeat — defends against Cloud Run proxy idle timeout (~60s)
    WS_PING_INTERVAL = 25

    async def _heartbeat_ping(ws: WebSocket, interval: int = 25):
        try:
            while True:
                await asyncio.sleep(interval)
                try:
                    await ws.send_json({"type": "ping"})
                except Exception:
                    break  # WebSocket closed
        except asyncio.CancelledError:
            pass  # Task cancelled on disconnect — expected

    heartbeat_task = asyncio.create_task(_heartbeat_ping(websocket, WS_PING_INTERVAL))

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                logger.info("Received WebSocket disconnect frame.")
                break

            # 1. Configuration message (text)
            if "text" in message:
                try:
                    config = json.loads(message["text"])
                    if config.get("type") == "pong":
                        continue
                    if config.get("type") == "ping":
                        await websocket.send_json({"type": "pong"})
                        continue
                    if config.get("type") == "config":
                        source_lang = config.get("source_lang", source_lang)
                        target_lang = config.get("target_lang", target_lang)
                        custom_initial_prompt = config.get("initial_prompt", "")
                        if "meeting_id" in config:
                            current_meeting_id = config["meeting_id"]
                            logger.info(f"Received meeting_id: {current_meeting_id}")

                        if "overlap_duration" in config:
                            OVERLAP_DURATION_SECONDS = float(config["overlap_duration"])

                        if "mode" in config:
                            operation_mode = config["mode"]
                            logger.info(f"[DEBUG] Received mode: {operation_mode}")
                            if operation_mode == "alignment":
                                logger.info(f"[DEBUG] Alignment mode activated. initial_prompt length: {len(custom_initial_prompt)}")
                                logger.info(f"[DEBUG] initial_prompt preview: {custom_initial_prompt[:200]}")
                                script_aligner.load_script(custom_initial_prompt)
                                logger.info(f"[DEBUG] Loaded {len(script_aligner.segments)} segments for Alignment Mode.")
                                logger.info(f"[DEBUG] Flattened text length: {len(script_aligner.full_cn_text)} characters")
                                if len(script_aligner.segments) > 0:
                                    first_seg = script_aligner.segments[0]
                                    logger.info(f"[DEBUG] First segment: [{first_seg['start_idx']}-{first_seg['end_idx']}] {first_seg['source'][:30]}...")

                        logger.info(f"Config updated: {source_lang} -> {target_lang} | Prompt len: {len(custom_initial_prompt)} | Overlap: {OVERLAP_DURATION_SECONDS} | Mode: {operation_mode}")
                except Exception as e:
                    logger.error(f"Failed to parse config message: {e}")
                continue

            # 2. Audio data (bytes)
            if "bytes" in message:
                data = message["bytes"]
                if first_audio_time is None:
                    first_audio_time = time.time()
                    logger.info("First audio packet received. Starting forced speech window.")
            else:
                continue

            # Force speech for the first 3.0s to prevent initial clipping
            is_initial_phase = False
            if first_audio_time is not None:
                is_initial_phase = (time.time() - first_audio_time) < 3.0

            audio_bytes = vad_buffer.process_chunk(data, force_speech=is_initial_phase)

            # Final transcription (split event)
            if audio_bytes:
                audio_np_current = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

                audio_for_transcription = audio_np_current
                if last_flushed_segment_np.size > 0:
                    overlap_samples = int(OVERLAP_DURATION_SECONDS * RATE)
                    overlap_from_previous = last_flushed_segment_np[-min(overlap_samples, last_flushed_segment_np.size):]
                    audio_for_transcription = np.concatenate((overlap_from_previous, audio_np_current))

                last_flushed_segment_np = audio_np_current

                if audio_for_transcription.size > 0:
                    logger.info(f"Transcribing {len(audio_for_transcription)/RATE:.2f} seconds of audio (VAD split with overlap)...")

                    combined_prompt = f"{custom_initial_prompt} {previous_context}".strip()

                    try:
                        transcript_text = await asyncio.wait_for(
                            get_transcription_gemini(audio_for_transcription, source_lang, combined_prompt),
                            timeout=30.0,
                        )
                        logger.info(f"Gemini ASR Output: '{transcript_text}'")
                    except asyncio.TimeoutError:
                        logger.error(f"Gemini ASR timed out for segment {current_segment_id}. Skipping segment.")
                        transcript_text = ""
                    except Exception as e:
                        logger.error(f"Gemini ASR error for segment {current_segment_id}: {e}", exc_info=True)
                        transcript_text = ""

                    if transcript_text:
                        logger.info(f"Raw Transcription [{current_segment_id}]: {transcript_text}")

                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": transcript_text,
                        })

                        # Alignment Mode
                        alignment_success = False
                        if operation_mode == "alignment" and script_aligner.has_script():
                            corrected_text = correct_keywords(transcript_text)
                            if corrected_text != transcript_text:
                                logger.info(f"[DEBUG] Corrections applied: '{transcript_text}' -> '{corrected_text}'")

                            logger.info(f"[DEBUG] Attempting alignment for transcript: '{corrected_text}'")
                            logger.info(f"[DEBUG] Current cursor position: {script_aligner.current_cursor} / {len(script_aligner.full_cn_text)}")

                            match_result = script_aligner.find_match(corrected_text, threshold=0.4, alignment_mode=True)
                            if match_result:
                                is_global = match_result.get('is_global_resync', False)
                                is_low_conf = match_result.get('low_confidence', False)
                                resync_tag = " [GLOBAL RESYNC]" if is_global else ""
                                conf_tag = " [LOW CONFIDENCE]" if is_low_conf else ""
                                match_symbol = "WARN" if is_low_conf else "OK"

                                logger.info(f"[DEBUG] {match_symbol} Alignment Match!{resync_tag}{conf_tag} Score: {match_result['score']:.2f}")
                                logger.info(f"[DEBUG]    Cursor: {match_result.get('cursor_position', 'N/A')}")

                                all_matches = match_result.get('all_matches', [match_result])
                                logger.info(f"[DEBUG]    Matched {len(all_matches)} segment(s)")

                                for idx, seg_match in enumerate(all_matches):
                                    seg_low_conf = seg_match.get('low_confidence', False)
                                    conf_marker = " [?]" if seg_low_conf else ""
                                    logger.info(f"[DEBUG]    [{seg_match['index']}]{conf_marker} {seg_match['source'][:30]}... -> {seg_match['target'][:30]}...")

                                    seg_id = current_segment_id if idx == 0 else f"{current_segment_id}-{idx}"
                                    await websocket.send_json({
                                        "type": "polished",
                                        "id": seg_id,
                                        "content": seg_match['source'],
                                        "translated": seg_match['target'],
                                        "low_confidence": seg_low_conf,
                                    })

                                alignment_success = True
                            else:
                                failures = script_aligner.consecutive_failures
                                logger.info(f"[DEBUG] X Alignment completely failed for: '{corrected_text[:50]}...' (failures: {failures}/{script_aligner.MAX_CONSECUTIVE_FAILURES})")
                                if failures >= script_aligner.MAX_CONSECUTIVE_FAILURES:
                                    logger.info(f"[DEBUG] !! Next attempt will trigger GLOBAL RESYNC")
                        elif operation_mode == "alignment":
                            logger.warning(f"[DEBUG] Alignment mode active but no script loaded!")

                        # Polish/translate (transcription mode only, when alignment didn't succeed)
                        if not alignment_success and operation_mode != "alignment":
                            asyncio.create_task(polish_transcription_task(
                                current_segment_id,
                                transcript_text,
                                previous_context,
                                source_lang,
                                target_lang,
                                websocket,
                            ))

                        previous_context = transcript_text
                        current_segment_id = str(uuid.uuid4())
                        last_partial_time = time.time()
                    else:
                        logger.info(f"Received empty transcription from ASR for [{current_segment_id}]. Clearing partial.")
                        await websocket.send_json({
                            "type": "raw",
                            "id": current_segment_id,
                            "content": "",
                        })
                        current_segment_id = str(uuid.uuid4())
                        last_partial_time = time.time()

    except WebSocketDisconnect:
        logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} disconnected.")
    except RuntimeError as e:
        if "disconnect message" in str(e):
            logger.info(f"WebSocket client {websocket.client.host}:{websocket.client.port} disconnected (RuntimeError).")
        else:
            logger.error(f"WebSocket Runtime error: {e}", exc_info=True)
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        if heartbeat_task:
            heartbeat_task.cancel()

        # Update Meeting's duration stat
        if current_meeting_id:
            try:
                meeting_to_update = db.query(Meeting).filter(Meeting.id == current_meeting_id).first()
                if meeting_to_update:
                    if first_audio_time is not None:
                        meeting_to_update.duration = time.time() - first_audio_time
                        logger.info(f"Meeting {current_meeting_id} live duration updated: {meeting_to_update.duration:.1f}s")
                    db.commit()
            except Exception as e:
                logger.error(f"Error updating meeting state on disconnect: {e}")

        logger.info("WebSocket disconnect cleanup finished.")
