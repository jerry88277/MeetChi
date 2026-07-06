# Cloud Tasks Compatible Background Tasks
# Removed Celery dependency - now works with direct function calls or Cloud Tasks HTTP triggers

import logging
import os
import json
import subprocess
import sys
import uuid
from datetime import datetime
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


def get_glossary_map(db: Session, meeting_id: str, user_upn: str = None) -> dict:
    """
    C1: Build merged glossary map (wrong_text → correct_text) for post-correction.
    Union of Global (user-level) + Local (meeting-level), Local overrides on conflict.
    """
    from app.models import UserGlossary, MeetingGlossary
    
    merged = {}
    
    # Global entries (if user_upn provided)
    if user_upn:
        global_entries = db.query(UserGlossary).filter(
            UserGlossary.user_upn == user_upn.lower().strip()
        ).all()
        for e in global_entries:
            merged[e.wrong_text] = e.correct_text
    
    # Local entries (always, override global)
    local_entries = db.query(MeetingGlossary).filter(
        MeetingGlossary.meeting_id == meeting_id
    ).all()
    for e in local_entries:
        merged[e.wrong_text] = e.correct_text
    
    return merged


def get_whisper_prompt(db: Session, meeting_id: str, user_upn: str = None) -> str:
    """
    C1: Generate Whisper initial_prompt with glossary hotwords.
    Injects correct terms into prompt so ASR recognizes them better.
    """
    glossary_map = get_glossary_map(db, meeting_id, user_upn)
    if not glossary_map:
        return ""
    
    correct_terms = list(set(glossary_map.values()))
    return "以下是本次會議可能出現的專有名詞：" + "、".join(correct_terms)


def apply_glossary_correction(db: Session, meeting_id: str, user_upn: str = None) -> int:
    """
    C1: Apply glossary-based post-correction to all segments of a meeting.
    Replaces wrong_text with correct_text in content_raw and content_polished.
    
    Returns number of segments modified.
    """
    from app.models import TranscriptSegment
    
    glossary_map = get_glossary_map(db, meeting_id, user_upn)
    if not glossary_map:
        return 0
    
    segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.meeting_id == meeting_id
    ).all()
    
    modified_count = 0
    for seg in segments:
        changed = False
        raw = seg.content_raw or ""
        polished = seg.content_polished or ""
        
        for wrong, correct in glossary_map.items():
            if wrong in raw:
                raw = raw.replace(wrong, correct)
                changed = True
            if wrong in polished:
                polished = polished.replace(wrong, correct)
                changed = True
        
        if changed:
            seg.content_raw = raw
            seg.content_polished = polished
            modified_count += 1
    
    if modified_count > 0:
        db.commit()
        logger.info(f"[Glossary] Applied corrections to {modified_count} segments for meeting {meeting_id}")
    
    return modified_count


def _link_speakers_across_chunks(
    chunk_speaker_embeddings: dict,
) -> dict:
    """Phase B: Cross-chunk speaker linking via embedding cosine similarity clustering.

    Given per-chunk speaker embeddings, clusters speakers across chunks by comparing
    their voice embedding centroids. Returns a mapping from chunk-local speaker IDs
    (e.g., "SPEAKER_00_c0") to global consistent IDs (e.g., "SPEAKER_A").

    Algorithm:
      1. Flatten all (chunk_idx, speaker_label, embedding) into a list
      2. Compute pairwise cosine similarity matrix
      3. Agglomerative clustering with threshold (0.7 cosine similarity)
      4. Assign global labels based on cluster membership

    Args:
        chunk_speaker_embeddings: {chunk_idx: {"SPEAKER_00": [float, ...], ...}}

    Returns:
        Mapping {"SPEAKER_00_c0": "SPEAKER_A", "SPEAKER_01_c0": "SPEAKER_B", ...}
        Returns empty dict if clustering fails.
    """
    import numpy as np

    try:
        # 1. Flatten embeddings
        entries = []  # [(chunk_key, embedding_vector), ...]
        for chunk_idx, speakers in chunk_speaker_embeddings.items():
            for spk_label, embedding in speakers.items():
                chunk_key = f"{spk_label}_c{chunk_idx}"
                entries.append((chunk_key, np.array(embedding, dtype=np.float32)))

        if len(entries) < 2:
            # Only 1 speaker across all chunks, trivial mapping
            if entries:
                return {entries[0][0]: "SPEAKER_A"}
            return {}

        # 2. Compute cosine similarity matrix
        keys = [e[0] for e in entries]
        embeddings = np.stack([e[1] for e in entries])

        # Normalize (should already be normalized, but ensure)
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        embeddings_norm = embeddings / norms

        # Cosine similarity matrix
        sim_matrix = embeddings_norm @ embeddings_norm.T

        # 3. Agglomerative clustering with distance threshold
        # Convert similarity to distance: distance = 1 - similarity
        distance_matrix = 1.0 - sim_matrix
        np.fill_diagonal(distance_matrix, 0)

        # Simple single-linkage clustering with threshold
        SIMILARITY_THRESHOLD = float(os.getenv("SPEAKER_LINK_THRESHOLD", "0.65"))
        distance_threshold = 1.0 - SIMILARITY_THRESHOLD

        n = len(entries)
        cluster_labels = list(range(n))  # Each entry starts in its own cluster

        # Greedy agglomerative: merge pairs with distance < threshold
        # Use average-linkage for robustness
        merged = True
        while merged:
            merged = False
            # Find unique clusters
            unique_clusters = list(set(cluster_labels))
            if len(unique_clusters) <= 1:
                break

            best_pair = None
            best_dist = float('inf')

            for i, ci in enumerate(unique_clusters):
                for j, cj in enumerate(unique_clusters):
                    if i >= j:
                        continue
                    # Average-linkage distance between clusters
                    members_i = [idx for idx, c in enumerate(cluster_labels) if c == ci]
                    members_j = [idx for idx, c in enumerate(cluster_labels) if c == cj]
                    avg_dist = np.mean([
                        distance_matrix[a, b]
                        for a in members_i
                        for b in members_j
                    ])
                    if avg_dist < best_dist:
                        best_dist = avg_dist
                        best_pair = (ci, cj)

            if best_pair and best_dist < distance_threshold:
                # Merge: relabel all cj → ci
                ci, cj = best_pair
                cluster_labels = [ci if c == cj else c for c in cluster_labels]
                merged = True

        # 4. Assign global speaker labels
        # Map cluster IDs to sequential labels
        unique_final = sorted(set(cluster_labels))
        cluster_to_label = {}
        for idx, cid in enumerate(unique_final):
            if idx < 26:
                cluster_to_label[cid] = f"SPEAKER_{chr(65 + idx)}"  # A, B, C, ...
            else:
                cluster_to_label[cid] = f"SPEAKER_{idx:02d}"

        mapping = {}
        for i, key in enumerate(keys):
            mapping[key] = cluster_to_label[cluster_labels[i]]

        logger.info(
            f"[SpeakerLink] Clustered {len(entries)} chunk-speakers → "
            f"{len(unique_final)} global speakers "
            f"(threshold={SIMILARITY_THRESHOLD})"
        )

        return mapping

    except Exception as e:
        logger.error(f"[SpeakerLink] Cross-chunk speaker linking failed: {e}", exc_info=True)
        return {}


def _try_global_diarization(
    all_segments: list,
    audio_url: str,
    meeting_id: str,
    gpu_asr_url: str,
) -> list:
    """
    Call GPU service /asr/diarize to get consistent global speaker labels.
    Falls back to per-chunk labels if diarization fails.
    """
    import httpx

    try:
        logger.info(f"[ParallelASR] {meeting_id}: requesting global diarization")
        resp = httpx.post(
            f"{gpu_asr_url.rstrip('/')}/asr/diarize",
            json={
                "meeting_id": meeting_id,
                "audio_url": audio_url,
            },
            timeout=1800.0,  # 30 min max for long meetings
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "completed" or not data.get("segments"):
            logger.warning(
                f"[ParallelASR] Global diarization returned status={data.get('status')}, "
                f"keeping per-chunk labels"
            )
            return all_segments

        # Re-assign speakers based on global diarization
        diar_segments = data["segments"]
        reassigned = 0
        for seg in all_segments:
            seg_start = seg["start_time"]
            seg_end = seg["end_time"]

            # Find speaker with maximum overlap
            overlaps = {}
            for dseg in diar_segments:
                overlap = min(seg_end, dseg["end"]) - max(seg_start, dseg["start"])
                if overlap > 0:
                    spk = dseg["speaker"]
                    overlaps[spk] = overlaps.get(spk, 0) + overlap

            if overlaps:
                seg["speaker"] = max(overlaps, key=overlaps.get)
                reassigned += 1

        logger.info(
            f"[ParallelASR] Global diarization assigned {reassigned}/{len(all_segments)} segments, "
            f"{data.get('speakers_count', '?')} speakers, took {data.get('duration_seconds', '?'):.1f}s"
        )
        return all_segments

    except Exception as e:
        logger.warning(
            f"[ParallelASR] Global diarization failed (non-fatal), "
            f"keeping per-chunk labels: {type(e).__name__}: {e}"
        )
        return all_segments


def _merge_short_segments(
    segments: list,
    max_chars: int = 20,
    max_gap_seconds: float = 1.5,
    target_min_chars: int = 30,
) -> list:
    """
    Merge consecutive short segments from the same speaker for readability.

    Rules:
      - Only merge if both current and next segment are from the same speaker
      - Only merge if the gap between segments is <= max_gap_seconds
      - Only merge if current segment text is <= max_chars
      - Stop merging once combined text reaches target_min_chars
      - Preserve start_time of first segment and end_time of last merged segment
    """
    if not segments:
        return segments

    merged = []
    i = 0
    while i < len(segments):
        current = dict(segments[i])  # copy
        i += 1

        # Try to absorb following short segments from same speaker
        while i < len(segments):
            next_seg = segments[i]
            current_text = (current.get("content_raw") or "").strip()
            next_text = (next_seg.get("content_raw") or "").strip()

            # Stop conditions
            if not next_text:
                break
            if next_seg.get("speaker") != current.get("speaker"):
                break
            if len(current_text) > max_chars and len(current_text) >= target_min_chars:
                break
            gap = next_seg.get("start_time", 0) - current.get("end_time", 0)
            if gap > max_gap_seconds:
                break

            # Merge
            current["content_raw"] = (current_text + next_text).strip()
            current["end_time"] = next_seg.get("end_time", current.get("end_time"))
            i += 1

        merged.append(current)

    logger.info(
        f"[SegmentMerge] {len(segments)} → {len(merged)} segments "
        f"({100 - 100*len(merged)/max(len(segments),1):.0f}% reduction)"
    )
    return merged


def _process_split_audio_sync(
    meeting_id: str,
    audio_url: str,
    gpu_asr_url: str,
    language: str,
    db: Session,
    suppress_fail_notification: bool,
):
    """Phase A.1 (2026-05-12)：duration > 1200s 走拆解 + 平行 GPU ASR path.

    流程：
      1. 拆 audio_url → N 個 chunks 上 GCS (audio_split.split_audio_to_chunks)
      2. 全局 GPU Semaphore 限流 POST 給 GPU service（跨會議共享）
      3. 各 chunk 失敗 → 最多 5 次 retry（defensive，semaphore 已大幅降低 429）
      4. 各 chunk segments 套 offset 合併
      5. 全部寫進 TranscriptSegment table
      6. 觸發 generate_summary_core(skip_asr=True) 跑 summary
      7. 所有 chunk 都拿到 final 結果（成功或重試後失敗）後才 cleanup GCS chunks

    全局排隊機制 (2026-06-23):
      - 取代舊的 per-meeting asyncio.Semaphore(ASR_PARALLELISM)
      - 使用 threading.Semaphore 實現跨 BackgroundTask thread 的全局限流
      - GPU_GLOBAL_CONCURRENCY=25 (env)：全局最多 25 concurrent GPU requests
      - GPU_PER_MEETING_MAX=10 (env)：單場最多佔 10 slots，防止大會議餓死小會議
      - 排隊取代 429 retry：chunk 等前面完成後立刻送出，零浪費

    Returns dict {status, meeting_id, ...}; 與 single-audio path 同格式
    """
    import asyncio
    from app.audio_split import split_audio_to_chunks, cleanup_chunks
    from app.models import TranscriptSegment

    # 全局 GPU semaphore（跨會議共享，取代舊的 per-meeting semaphore）
    from app.gpu_semaphore import (
        acquire_gpu_slot_async,
        release_gpu_slot,
        cleanup_meeting,
        get_stats as get_gpu_stats,
        stagger_wait,
    )

    chunks: list = []  # for finally cleanup
    cleanup_done = False
    try:
        # 0. 階梯觸發：多場會議同時觸發時，間隔 30s 讓 GPU autoscaler 漸進升溫
        stagger_elapsed = stagger_wait(meeting_id)
        if stagger_elapsed > 0:
            logger.info(
                f"[ParallelASR] {meeting_id[:8]} stagger wait done ({stagger_elapsed:.1f}s)"
            )

        # 1. Split audio → upload chunks
        logger.info(f"[ParallelASR] splitting audio for {meeting_id}")
        chunks = split_audio_to_chunks(audio_url, meeting_id)
        n_chunks = len(chunks)
        logger.info(
            f"[ParallelASR] {meeting_id} split into {n_chunks} chunks "
            f"(global GPU queue, stagger={stagger_elapsed:.0f}s)"
        )

        # 2. Semaphore-limited POST：每個 chunk 一次 retry on failure
        async def call_gpu_once(chunk_url: str, offset: float, idx: int, attempt: int) -> dict:
            """單次 POST，connect timeout 90s (cold start), read timeout 3600s。"""
            import httpx
            timeout = httpx.Timeout(connect=90.0, read=3600.0, write=30.0, pool=90.0)
            async with httpx.AsyncClient(timeout=timeout) as client:
                logger.info(
                    f"[ParallelASR] chunk {idx+1}/{n_chunks} → GPU "
                    f"(offset={offset:.0f}s, attempt={attempt})"
                )
                resp = await client.post(
                    f"{gpu_asr_url.rstrip('/')}/asr/refine",
                    json={
                        "meeting_id": f"{meeting_id}__chunk_{idx:03d}",
                        "audio_url": chunk_url,
                        "language": language,
                        "callback_url": None,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                data["_chunk_offset"] = offset
                data["_chunk_idx"] = idx
                logger.info(
                    f"[ParallelASR] chunk {idx+1}/{n_chunks} done attempt={attempt}: "
                    f"{len(data.get('segments', []))} segments"
                )
                return data

        async def call_gpu_with_retry(chunk_url: str, offset: float, idx: int) -> dict:
            """Global semaphore-guarded POST + up to 7 retries.
            
            每次 attempt 獨立 acquire/release slot：
            - 成功：acquire → GPU call → release
            - 失敗：acquire → GPU call (429) → release → backoff → next attempt
            釋放 slot 讓其他 chunks 有機會通過（提高整體 throughput）。
            """
            max_attempts = 7
            for attempt in range(1, max_attempts + 1):
                # 排隊等 GPU slot（全局限流）
                wait_time = await acquire_gpu_slot_async(meeting_id)
                if wait_time > 1.0:
                    logger.info(
                        f"[ParallelASR] chunk {idx+1}/{n_chunks} queued {wait_time:.1f}s for GPU slot"
                    )
                try:
                    result = await call_gpu_once(chunk_url, offset, idx, attempt=attempt)
                    return result
                except Exception as e:
                    if attempt == max_attempts:
                        logger.error(
                            f"[ParallelASR] chunk {idx+1}/{n_chunks} failed after {max_attempts} attempts "
                            f"({type(e).__name__}: {e})"
                        )
                        raise
                    err_str = str(e)
                    # 429/503 = GPU cold start (60-90s) or overload
                    if "429" in err_str or "503" in err_str:
                        backoff = 30 * attempt  # 30s, 60s, 90s, 120s, 150s, 180s
                    else:
                        backoff = 5 * attempt
                    logger.warning(
                        f"[ParallelASR] chunk {idx+1}/{n_chunks} attempt {attempt} failed "
                        f"({type(e).__name__}: {e}); retrying in {backoff}s"
                    )
                    await asyncio.sleep(backoff)
                finally:
                    release_gpu_slot(meeting_id)

        async def run_all_chunks():
            # 設定足夠大的 executor 避免 asyncio.to_thread starvation
            # 需要 >= per_meeting_max 的 threads 來避免 deadlock
            import concurrent.futures
            loop = asyncio.get_event_loop()
            loop.set_default_executor(
                concurrent.futures.ThreadPoolExecutor(max_workers=max(20, n_chunks + 2))
            )
            tasks = [
                call_gpu_with_retry(url, off, i)
                for i, (url, off) in enumerate(chunks)
            ]
            return await asyncio.gather(*tasks, return_exceptions=True)

        results = asyncio.run(run_all_chunks())

        # Log GPU queue stats after all chunks processed
        gpu_stats = get_gpu_stats()
        logger.info(
            f"[ParallelASR] {meeting_id} GPU queue stats: "
            f"concurrent={gpu_stats['current_concurrent']}, "
            f"peak={gpu_stats['peak_concurrent']}, "
            f"queued={gpu_stats['total_queued']}, "
            f"avg_wait={gpu_stats['avg_queue_wait_sec']}s"
        )

        # Check for chunk-level failures (after retry)
        failed_chunks = [i for i, r in enumerate(results) if isinstance(r, Exception)]
        if failed_chunks:
            err_msgs = "; ".join(
                f"chunk_{i}: {type(results[i]).__name__}: {results[i]}"
                for i in failed_chunks[:3]
            )
            raise RuntimeError(
                f"[ParallelASR] {len(failed_chunks)}/{n_chunks} chunks failed after retry: {err_msgs}"
            )

        # 3. Merge segments with time offset
        all_segments = []
        order_counter = 0
        # Collect per-chunk speaker embeddings for Phase B cross-chunk linking
        chunk_speaker_embeddings = {}  # {chunk_idx: {"SPEAKER_00": [float, ...], ...}}
        for result in results:
            offset = result["_chunk_offset"]
            chunk_idx = result["_chunk_idx"]
            for seg in result.get("segments", []):
                all_segments.append({
                    "start_time": seg["start"] + offset,
                    "end_time": seg["end"] + offset,
                    "speaker": seg.get("speaker", "") or "",
                    "_chunk_idx": chunk_idx,
                    "content_raw": seg.get("text", ""),
                    "content_polished": None,
                })
                order_counter += 1
            # Collect embeddings if returned by GPU service
            embs = result.get("speaker_embeddings")
            if embs:
                chunk_speaker_embeddings[chunk_idx] = embs

        # Phase B: Cross-chunk speaker linking via embedding clustering
        # Falls back to Phase A suffix encoding if embeddings unavailable
        skip_global_diar = os.getenv("SKIP_GLOBAL_DIARIZATION", "false").lower() == "true"

        if skip_global_diar and chunk_speaker_embeddings:
            # Phase B: Use embeddings to link speakers across chunks
            try:
                logger.info(
                    f"[ParallelASR] {meeting_id}: Phase B starting — "
                    f"{len(chunk_speaker_embeddings)} chunks with embeddings"
                )
                speaker_mapping = _link_speakers_across_chunks(chunk_speaker_embeddings)
                if speaker_mapping:
                    n_global = len(set(speaker_mapping.values()))
                    logger.info(
                        f"[ParallelASR] {meeting_id}: Phase B speaker linking — "
                        f"mapped {len(speaker_mapping)} chunk-speakers "
                        f"→ {n_global} global speakers"
                    )
                    # Apply mapping: (chunk_idx, local_speaker) → global_speaker
                    for seg in all_segments:
                        spk = seg["speaker"]
                        cidx = seg["_chunk_idx"]
                        if spk:
                            key = f"{spk}_c{cidx}"
                            seg["speaker"] = speaker_mapping.get(key, key)
                        del seg["_chunk_idx"]
                else:
                    raise ValueError("Empty speaker mapping returned")
            except Exception as e:
                # Fallback: Phase A suffix encoding
                logger.warning(f"[ParallelASR] {meeting_id}: Phase B linking failed ({e}), falling back to Phase A suffixes", exc_info=True)
                for seg in all_segments:
                    spk = seg["speaker"]
                    cidx = seg["_chunk_idx"]
                    if spk:
                        seg["speaker"] = f"{spk}_c{cidx}"
                    del seg["_chunk_idx"]
        elif skip_global_diar:
            # No embeddings available, use Phase A suffix encoding
            logger.info(f"[ParallelASR] {meeting_id}: skipping global diarization, no embeddings available (Phase A fallback)")
            for seg in all_segments:
                spk = seg["speaker"]
                cidx = seg["_chunk_idx"]
                if spk:
                    seg["speaker"] = f"{spk}_c{cidx}"
                del seg["_chunk_idx"]
        else:
            # Global diarization mode: suffix first, then override with global labels
            for seg in all_segments:
                spk = seg["speaker"]
                cidx = seg["_chunk_idx"]
                if spk:
                    seg["speaker"] = f"{spk}_c{cidx}"
                del seg["_chunk_idx"]

        # Sort by start_time then by chunk_idx (stable)
        all_segments.sort(key=lambda s: s["start_time"])

        # 3.5 Global diarization: re-assign speakers using full-audio pyannote
        # This replaces per-chunk SPEAKER_XX_cN labels with consistent global IDs
        # Can be skipped via env var for faster processing (uses per-chunk labels instead)
        if skip_global_diar:
            logger.info(f"[ParallelASR] {meeting_id}: skipping global diarization (SKIP_GLOBAL_DIARIZATION=true)")
        else:
            all_segments = _try_global_diarization(
                all_segments, audio_url, meeting_id, gpu_asr_url
            )

        # 3.6 Merge consecutive short segments from same speaker for readability
        all_segments = _merge_short_segments(all_segments)

        # 4. Write all segments to DB
        meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
        if not meeting:
            raise RuntimeError(f"Meeting {meeting_id} disappeared during processing")

        # Clear existing segments (Phase A 接受全量覆蓋)
        db.query(TranscriptSegment).filter(TranscriptSegment.meeting_id == meeting_id).delete()

        from app.models import TranscriptSegment as TS
        for order, seg_data in enumerate(all_segments):
            db.add(TS(
                id=str(uuid.uuid4()),
                meeting_id=meeting_id,
                order=order,
                start_time=seg_data["start_time"],
                end_time=seg_data["end_time"],
                speaker=seg_data["speaker"],
                content_raw=seg_data["content_raw"],
                content_polished=seg_data["content_polished"],
                is_final=True,
            ))
        db.commit()
        logger.info(
            f"[ParallelASR] {meeting_id}: wrote {len(all_segments)} merged segments to DB "
            f"(from {n_chunks} chunks)"
        )

        # C1: Apply glossary-based post-correction after writing segments
        try:
            user_upn = meeting.owner_upn
            corrected = apply_glossary_correction(db, meeting_id, user_upn)
            if corrected > 0:
                logger.info(f"[ParallelASR] Glossary correction applied to {corrected} segments")
        except Exception as e:
            logger.warning(f"[ParallelASR] Glossary correction failed (non-fatal): {e}")

        # 5. Cleanup chunks from GCS — 只在所有 chunk 都 settled 後執行
        # （Phase A.1 修：原版 cleanup 在 failed_chunks 觸發 raise 前就跑，
        # 與 Cloud Run queue 中仍在等的 chunk race，造成 404 連鎖失敗）
        cleanup_chunks(audio_url, meeting_id)
        cleanup_done = True
        cleanup_meeting(meeting_id)  # 釋放 per-meeting semaphore 記憶體

        # 5.5 Checkpoint: ASR 完成，設為 TRANSCRIBED 讓前端可顯示逐字稿。
        # 即使後續摘要失敗，使用者仍能看到轉錄結果，不需重新上傳。
        meeting.status = MeetingStatus.TRANSCRIBED
        meeting.transcription_completed_at = datetime.utcnow()
        db.commit()
        logger.info(f"[ParallelASR] {meeting_id}: set status=TRANSCRIBED (checkpoint)")

        # 6. Trigger summary generation (synchronously continue)
        # 方案 B: 摘要失敗不覆蓋 TRANSCRIBED，使用者可立即看逐字稿
        _update_task_status(
            db, meeting_id, "offline_asr", "COMPLETED",
            f"Parallel ASR complete ({n_chunks} chunks)"
        )

        logger.info(f"[ParallelASR] {meeting_id}: invoking summary generation (skip_asr=True)")
        meeting.processing_stage = "summarizing"
        db.commit()
        try:
            return generate_summary_core(
                meeting_id,
                template_type=meeting.template_name or "general",
                skip_asr=True,
                suppress_fail_notification=suppress_fail_notification,
            )
        except Exception as summary_err:
            # 摘要失敗：保留 TRANSCRIBED 狀態，使用者仍可查看逐字稿
            logger.error(f"[ParallelASR] {meeting_id}: summary generation failed (transcript preserved): {summary_err}")
            try:
                meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
                if meeting:
                    meeting.status = MeetingStatus.TRANSCRIBED
                    meeting.failure_reason = (
                        f"摘要生成失敗 ({type(summary_err).__name__})：{str(summary_err)[:200]}\n\n"
                        "逐字稿已完成，可直接查看。點「僅重新生成摘要」即可重試，無需重跑轉錄。"
                    )
                    meeting.processing_stage = None
                    db.commit()
            except Exception:
                pass
            return {"status": "transcribed", "meeting_id": meeting_id, "message": "ASR done, summary failed but transcript preserved"}

    except Exception as e:
        logger.error(f"[ParallelASR] {meeting_id} failed: {e}", exc_info=True)
        # 2026-05-25 (Y7): 寫 failure_reason 給 user 看，分類 ASR 階段失敗
        # 注意：如果已經通過 TRANSCRIBED checkpoint，不要覆蓋為 FAILED
        _fail_reason = (
            f"平行 ASR 處理失敗 ({type(e).__name__})：{str(e)[:200]}\n\n"
            "可能原因：GPU service 繁忙、network 中斷、或 audio 切片問題。"
            "建議：點「重新從頭轉錄」再試；若連續失敗請點「立即回報」。"
        )
        if not suppress_fail_notification:
            try:
                meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
                if meeting:
                    # 如果逐字稿已完成 (TRANSCRIBED)，保留該狀態
                    if meeting.status == MeetingStatus.TRANSCRIBED:
                        meeting.failure_reason = (
                            f"摘要生成階段失敗 ({type(e).__name__})：{str(e)[:200]}\n\n"
                            "逐字稿已完成，可直接查看。點「僅重新生成摘要」即可重試。"
                        )
                    else:
                        meeting.status = MeetingStatus.FAILED
                        meeting.failure_reason = _fail_reason
                    meeting.processing_stage = None
                    db.commit()
            except Exception:
                pass
        _update_task_status(db, meeting_id, "offline_asr", "FAILED", f"ParallelASR error: {str(e)}")
        # cleanup chunks even on failure（若 success 路徑沒走到 cleanup_done=True）
        if not cleanup_done and chunks:
            try:
                from app.audio_split import cleanup_chunks
                cleanup_chunks(audio_url, meeting_id)
            except Exception:
                pass
        cleanup_meeting(meeting_id)  # 釋放 per-meeting semaphore 記憶體
        return {"status": "failed", "error": f"Parallel ASR failed: {str(e)}"}


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
            meeting.completed_at = datetime.utcnow()
            meeting.processing_stage = None
            # 2026-07-03：0 段落多為靜音/無訊號音檔 —— 依 audio_stats 給使用者可讀原因，
            # 而非清空 failure_reason 讓使用者以為系統壞掉。
            silent_reason = None
            try:
                if meeting.audio_stats:
                    _st = json.loads(meeting.audio_stats)
                    if _st.get("health") == "silent":
                        silent_reason = _st.get("health_label_zh")
            except Exception:  # noqa: BLE001
                pass
            meeting.failure_reason = silent_reason  # None if audio was fine (genuine empty)
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
        meeting.completed_at = datetime.utcnow()
        meeting.processing_stage = None
        meeting.failure_reason = None  # Clear stale failure_reason from prior attempts
        db.commit()

        # C1: Apply glossary-based post-correction
        try:
            user_upn = meeting.owner_upn
            corrected = apply_glossary_correction(db, meeting_id, user_upn)
            if corrected > 0:
                logger.info(f"[Offline ASR] Glossary correction applied to {corrected} segments")
        except Exception as e:
            logger.warning(f"[Offline ASR] Glossary correction failed (non-fatal): {e}")

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
                meeting.completed_at = meeting.completed_at or datetime.utcnow()
                meeting.processing_stage = None
                meeting.failure_reason = None  # Clear stale failure_reason
                db.commit()
            _update_task_status(db, meeting_id, "offline_asr", "FAILED", str(e))
        except Exception:
            pass
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()



def _compute_and_store_audio_stats(meeting, db):
    """下載會議音檔、分析健康報告（時長/音量/聲道/靜音/削波），存 meeting.audio_stats。

    在轉錄開始前呼叫一次，GPU/local/split 全路徑共用。檔案通常僅數 MB，
    下載 + ffmpeg volumedetect 成本低。任一步驟失敗不影響主轉錄流程。
    """
    from app.audio_stats import analyze_audio_stats

    audio_url = meeting.audio_url
    if not audio_url:
        return

    local_path = None
    downloaded = False
    try:
        if audio_url.startswith("gs://"):
            from google.cloud import storage as gcs_storage

            parts = audio_url.replace("gs://", "").split("/", 1)
            bucket_name = parts[0]
            blob_name = parts[1] if len(parts) > 1 else ""
            temp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")
            os.makedirs(temp_dir, exist_ok=True)
            local_path = os.path.join(temp_dir, "stats_" + os.path.basename(blob_name))
            gcs_storage.Client().bucket(bucket_name).blob(blob_name).download_to_filename(local_path)
            downloaded = True
        else:
            local_path = audio_url

        stats = analyze_audio_stats(local_path)
        meeting.audio_stats = json.dumps(stats, ensure_ascii=False)
        db.commit()
        logger.info(f"[audio_stats] stored for {meeting.id}: health={stats.get('health')}")
    finally:
        if downloaded and local_path and os.path.exists(local_path):
            try:
                os.remove(local_path)
            except Exception:
                pass


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
            # 2026-07-03：先分析上傳音檔「原始狀態」健康報告（時長/音量/聲道/靜音/削波），
            # 存 meeting.audio_stats 供前端呈現。在 GPU/local/split 分支之前執行，全路徑覆蓋。
            # 永不影響主流程（helper 內部吞例外）。
            try:
                _compute_and_store_audio_stats(meeting, db)
            except Exception as _e:  # noqa: BLE001
                logger.warning(f"[audio_stats] non-fatal failure for {meeting_id}: {_e}")

            gpu_asr_url = os.getenv("GPU_ASR_SERVICE_URL")
            logger.info(f"[DEBUG] GPU_ASR_SERVICE_URL env value: '{gpu_asr_url}'")
            if gpu_asr_url:
                logger.info(f"GPU_ASR_SERVICE_URL is set ({gpu_asr_url}). Triggering remote GPU ASR refinement...")

                # Set status to PROCESSING and stage to transcribing
                meeting.status = MeetingStatus.PROCESSING
                meeting.processing_stage = "transcribing"
                db.commit()
                logger.info(f"Set meeting {meeting_id} status to PROCESSING, stage=transcribing")

                # 2026-05-11 Phase A：duration > 20 min 走 parallel split path
                from app.audio_split import should_use_parallel_split

                if should_use_parallel_split(meeting.duration):
                    logger.info(
                        f"[ParallelASR] meeting {meeting_id} duration={meeting.duration:.0f}s, "
                        f"using audio split + parallel GPU ASR"
                    )
                    return _process_split_audio_sync(meeting_id, meeting.audio_url, gpu_asr_url, meeting.language or "zh", db, suppress_fail_notification)

                # Short audio：original single-call path
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
                        meeting.processing_stage = None
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
        # Set processing_stage to "summarizing"
        meeting.processing_stage = "summarizing"
        db.commit()
        logger.info(f"Set meeting {meeting_id} processing_stage=summarizing")

        # Re-query meeting to get updated segments
        db.refresh(meeting)
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.meeting_id == meeting_id
        ).order_by(TranscriptSegment.order).all()
        
        if not segments:
            logger.warning(f"No transcript segments found for meeting {meeting_id}")
            # 靜音/無訊號音檔會產生 0 段落。此時必須落在終態並給使用者可讀原因，
            # 否則會卡在 TRANSCRIBED/summarizing（呼叫端把非 completed 視為 500，
            # Cloud Tasks 重試又因狀態非 PENDING/FAILED 被 skip → 永久卡住）。
            meeting.status = MeetingStatus.COMPLETED
            meeting.completed_at = datetime.utcnow()
            meeting.processing_stage = None
            silent_reason = "未偵測到可辨識語音，請確認麥克風或錄音來源是否正常後重新上傳。"
            try:
                if meeting.audio_stats:
                    _st = json.loads(meeting.audio_stats)
                    if _st.get("health") == "silent" and _st.get("health_label_zh"):
                        silent_reason = _st["health_label_zh"]
            except Exception:  # noqa: BLE001
                pass
            meeting.failure_reason = silent_reason
            db.commit()
            logger.info(
                f"Meeting {meeting_id} finalized COMPLETED with empty transcript "
                f"(silent audio): {silent_reason}"
            )
            return {"status": "completed", "reason": "empty_transcript"}

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

            summary_json_data = summary_data
            meeting.summary_json = json.dumps(summary_json_data, ensure_ascii=False)
            # Store full text snapshot
            meeting.transcript_raw = transcript_text
            
            # Phase 8.1: Auto-populate speaker_mappings from CoT speaker_roles
            # 2026-05-22 (feedback 5/22 #1)：color 改以 display_name 為 key 分配，
            # Phase A.1 平行 ASR 會產生 12+ 個 SPEAKER_NN_cM labels 對應同個人，
            # 若 color 按 speaker_id 順序分配會出現「同一人多色」混亂。LLM 已
            # 被指示把同一人的所有 _cM 變體用同一個 display_name（見
            # template_engine.COT_ROLE_INFERENCE_BLOCK），這裡只要 display_name
            # 相同就共用同色，自然完成跨 chunk 合併視覺。
            speaker_roles = summary_data.get("speaker_roles")
            if speaker_roles and not meeting.speaker_mappings:
                SPEAKER_COLORS = [
                    "#5FB7AC", "#2D428B", "#48B070", "#E4831A",
                    "#D2343D", "#EDD414", "#513A57", "#1E455E"
                ]
                display_name_to_color: dict = {}
                mappings = {}
                for sr in speaker_roles:
                    sid = sr.get("speaker_id") or f"Speaker_{len(mappings)}"
                    display = sr.get("display_name") or sid
                    if display not in display_name_to_color:
                        display_name_to_color[display] = SPEAKER_COLORS[
                            len(display_name_to_color) % len(SPEAKER_COLORS)
                        ]
                    mappings[sid] = {
                        "display_name": display,
                        "role": sr.get("role", "未知"),
                        "color": display_name_to_color[display],
                    }
                meeting.speaker_mappings = json.dumps(mappings, ensure_ascii=False)
                unique_people = len(display_name_to_color)
                logger.info(
                    f"Auto-populated speaker_mappings for {meeting_id}: "
                    f"{len(mappings)} labels → {unique_people} unique people"
                )

            # Fallback: if LLM didn't produce speaker_roles, generate default
            # mappings from transcript segments so frontend speaker legend shows up
            if not meeting.speaker_mappings:
                # transcript_segments is an ORM relationship (InstrumentedList),
                # not a JSON string — iterate ORM objects directly
                unique_speakers = sorted(set(
                    seg.speaker for seg in meeting.transcript_segments if seg.speaker
                ))
                if unique_speakers:
                    SPEAKER_COLORS = [
                        "#5FB7AC", "#2D428B", "#48B070", "#E4831A",
                        "#D2343D", "#EDD414", "#513A57", "#1E455E"
                    ]
                    fallback_mappings = {}
                    for i, sid in enumerate(unique_speakers):
                        fallback_mappings[sid] = {
                            "display_name": f"講者 {i + 1}",
                            "role": "",
                            "color": SPEAKER_COLORS[i % len(SPEAKER_COLORS)],
                        }
                    meeting.speaker_mappings = json.dumps(fallback_mappings, ensure_ascii=False)
                    logger.info(
                        f"Fallback speaker_mappings for {meeting_id}: "
                        f"{len(fallback_mappings)} speakers from segments"
                    )

            meeting.status = MeetingStatus.COMPLETED
            meeting.completed_at = datetime.utcnow()
            meeting.processing_stage = None
            meeting.failure_reason = None  # Clear stale failure_reason from prior attempts

            db.commit()

            try:
                count = _sync_action_items(db, meeting.id, summary_json_data)
                db.commit()
                logger.info(f"[greeting] synced {count} action items for meeting {meeting.id}")
            except Exception as e:
                logger.warning(f"[greeting] action item sync failed for {meeting.id}: {e}")
                db.rollback()
            
            # Phase RAG: Auto-embed transcript segments + summary for cross-meeting search
            try:
                seg_count = embed_transcript_segments(db, meeting_id)
                sum_ok = embed_meeting_summary(db, meeting_id)
                logger.info(f"[Embedding] Auto-embed complete: {seg_count} segments, summary={'OK' if sum_ok else 'SKIP'}")
            except Exception as emb_err:
                # Embedding failure must NOT break the core pipeline
                logger.warning(f"[Embedding] Auto-embed failed (non-fatal): {emb_err}")

            # Summary V2 (Q7, 2026-05-11): 補 cross_meeting_refs 進 summary_json
            # 用 pgvector 查同 owner 近期會議；similarity >= 0.7 才列。
            # 必須在 embed_meeting_summary 之後，才有 summary_embedding 可用。
            try:
                from app.embedding import find_cross_meeting_refs
                refs = find_cross_meeting_refs(db, meeting_id, top_k=5, min_similarity=0.7)
                if refs:
                    # 重新讀 summary_data 附上 cross_meeting_refs 並寫回
                    sj = json.loads(meeting.summary_json) if meeting.summary_json else {}
                    sj["cross_meeting_refs"] = refs
                    meeting.summary_json = json.dumps(sj, ensure_ascii=False)
                    db.commit()
                    logger.info(f"[CrossRef] Wrote {len(refs)} cross-meeting refs into summary_json")
            except Exception as cref_err:
                # Cross-ref 失敗不擋主流程
                logger.warning(f"[CrossRef] Failed (non-fatal): {cref_err}")
            
            # Phase 9.2: Fire-and-forget Discord notification
            send_completion_notification(meeting, "completed")
            
            return {"status": "completed", "meeting_id": meeting_id}

        except Exception as e:
             logger.error(f"Error calling Gemini Service: {e}")
             # 2026-05-25 (Y7): 分類 Gemini summary 階段常見失敗，給 user 具體說明
             err_str = str(e)
             if "MAX_TOKENS" in err_str.upper() or "Failed to parse JSON" in err_str:
                 fail_reason = (
                     "AI 摘要回應過長被截斷（會議內容極多，超出單次回應上限）。\n\n"
                     "解法：點「僅重新生成摘要」會用更簡短設定重試；若仍失敗，可能"
                     "需要把會議拆成幾段分別處理。"
                 )
             elif "INVALID_ARGUMENT" in err_str or "400" in err_str[:10]:
                 fail_reason = (
                     "AI 服務拒絕請求（可能 schema 或設定問題）。\n\n"
                     "解法：請點「立即回報」交給 IT 協助，已自動帶上會議 ID。"
                 )
             elif "timeout" in err_str.lower() or "ReadError" in err_str:
                 fail_reason = (
                     "AI 服務回應逾時或連線中斷。\n\n"
                     "解法：點「僅重新生成摘要」再試；通常重試一次就會成功。"
                 )
             else:
                 fail_reason = (
                     f"AI 摘要生成失敗 ({type(e).__name__})：{err_str[:200]}\n\n"
                     "解法：先試「僅重新生成摘要」；若連續失敗請「立即回報」。"
                 )
             if not suppress_fail_notification:
                 # If transcription was already done (skip_asr=True), keep TRANSCRIBED
                 # so user can still view the transcript. Only pure ASR failures go to FAILED.
                 if skip_asr:
                     meeting.status = MeetingStatus.TRANSCRIBED
                 else:
                     meeting.status = MeetingStatus.FAILED
                 meeting.failure_reason = fail_reason
                 meeting.processing_stage = None
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


def _sync_action_items(db, meeting_id: str, summary_json: dict) -> int:
    """
    Parse action_items / next_steps from summary_json and upsert into meeting_action_items.
    Idempotent: deletes existing items for the meeting first, then re-inserts.
    Returns count of items inserted.
    """
    from app.models import MeetingActionItem
    import uuid as _uuid

    # Delete stale items
    db.query(MeetingActionItem).filter(MeetingActionItem.meeting_id == meeting_id).delete()

    items = []
    # Parse action_items list
    for raw in (summary_json.get("action_items") or []):
        text = raw if isinstance(raw, str) else str(raw)
        text = text.strip()
        if not text:
            continue
        items.append(MeetingActionItem(
            id=str(_uuid.uuid4()),
            meeting_id=meeting_id,
            source_type="action_item",
            text=text,
            normalized_text=text.lower(),
            status="pending",
        ))

    # Parse next_steps list (may be dicts with assignee/due_date)
    for raw in (summary_json.get("next_steps") or []):
        if isinstance(raw, dict):
            text = (raw.get("action") or raw.get("text") or str(raw)).strip()
            assignee = raw.get("assignee") or raw.get("owner")
            due = raw.get("due_date") or raw.get("due")
        else:
            text = str(raw).strip()
            assignee = None
            due = None
        if not text:
            continue
        items.append(MeetingActionItem(
            id=str(_uuid.uuid4()),
            meeting_id=meeting_id,
            source_type="next_step",
            text=text,
            normalized_text=text.lower(),
            assignee=assignee,
            status="pending",
        ))

    for item in items:
        db.add(item)
    db.flush()
    return len(items)


def generate_meeting_minutes(meeting_id: str, template_type: str = "general", context: str = "", length: str = "", style: str = "", skip_asr: bool = False, suppress_fail_notification: bool = False):
    """
    Wrapper function for backward compatibility.
    Previously was a Celery task, now a direct function call.
    Can be invoked via Cloud Tasks HTTP handler or directly.
    """
    return generate_summary_core(meeting_id, template_type, context, length, style, skip_asr=skip_asr, suppress_fail_notification=suppress_fail_notification)