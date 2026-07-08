"""
Meeting Merge/Split API Routes
Allows combining multiple meetings or splitting a meeting into parts
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, UploadFile, File, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
import os
import subprocess
import logging
from google.cloud import storage as gcs_storage

from app.models import Meeting, TranscriptSegment, MeetingStatus
from app.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/meetings", tags=["Meeting Operations"])


# ============================================
# Pydantic Models
# ============================================

class MeetingMergeRequest(BaseModel):
    """Request to merge multiple meetings"""
    meeting_ids: List[str] = Field(..., min_items=2, description="List of meeting IDs to merge (order preserved)")
    new_title: str = Field(..., min_length=1, max_length=255)
    delete_originals: bool = Field(False, description="Delete original meetings after merge")


class MeetingSplitRequest(BaseModel):
    """Request to split a meeting at a specific time"""
    split_at_seconds: float = Field(..., gt=0, description="Time in seconds to split the meeting")
    title_part1: Optional[str] = None
    title_part2: Optional[str] = None


class MeetingOperationResponse(BaseModel):
    success: bool
    message: str
    new_meeting_ids: List[str]

class UploadUrlRequest(BaseModel):
    filename: str = "audio.webm"
    contentType: str = "audio/webm"

class UploadUrlResponse(BaseModel):
    uploadUrl: str
    upload_url: str


# ============================================
# Merge Meetings
# ============================================

@router.post("/merge", response_model=MeetingOperationResponse)
async def merge_meetings(
    request: MeetingMergeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Merge multiple meetings into one.
    - Combines audio files using FFmpeg
    - Concatenates transcripts with adjusted timestamps
    - Creates new summary from combined content
    """
    # Validate meetings exist
    meetings = []
    for mid in request.meeting_ids:
        meeting = db.query(Meeting).filter(Meeting.id == mid).first()
        if not meeting:
            raise HTTPException(status_code=404, detail=f"Meeting {mid} not found")
        meetings.append(meeting)
    
    # Create new meeting
    new_meeting_id = str(uuid.uuid4())
    new_meeting = Meeting(
        id=new_meeting_id,
        title=request.new_title,
        status=MeetingStatus.PROCESSING,
        language=meetings[0].language,
        template_name=meetings[0].template_name
    )
    db.add(new_meeting)
    db.flush()
    
    # Merge transcripts
    total_duration = 0.0
    segment_order = 0
    combined_transcript = []
    
    for meeting in meetings:
        # Get segments from this meeting
        segments = db.query(TranscriptSegment).filter(
            TranscriptSegment.meeting_id == meeting.id
        ).order_by(TranscriptSegment.order).all()
        
        for seg in segments:
            # Create new segment with adjusted timestamps
            new_segment = TranscriptSegment(
                id=str(uuid.uuid4()),
                meeting_id=new_meeting_id,
                order=segment_order,
                start_time=seg.start_time + total_duration,
                end_time=seg.end_time + total_duration,
                speaker=seg.speaker,
                content_raw=seg.content_raw,
                content_polished=seg.content_polished,
                content_translated=seg.content_translated,
                is_final=seg.is_final
            )
            db.add(new_segment)
            combined_transcript.append(seg.content_raw)
            segment_order += 1
        
        # Add this meeting's duration
        if meeting.duration:
            total_duration += meeting.duration
    
    # Set combined transcript
    new_meeting.transcript_raw = "\n".join(combined_transcript)
    new_meeting.duration = total_duration
    
    # Schedule audio merge in background
    audio_files = [m.audio_url for m in meetings if m.audio_url and os.path.exists(m.audio_url)]
    if audio_files:
        background_tasks.add_task(
            merge_audio_files,
            audio_files,
            new_meeting_id,
            db
        )
    
    # Delete originals if requested
    if request.delete_originals:
        for meeting in meetings:
            meeting.status = MeetingStatus.COMPLETED  # Mark as archived, don't actually delete
    
    new_meeting.status = MeetingStatus.COMPLETED
    db.commit()
    
    return MeetingOperationResponse(
        success=True,
        message=f"Merged {len(meetings)} meetings successfully",
        new_meeting_ids=[new_meeting_id]
    )


async def merge_audio_files(audio_files: List[str], meeting_id: str, db: Session):
    """Background task to merge audio files using FFmpeg"""
    try:
        # Create concat file list
        upload_dir = os.path.dirname(audio_files[0])
        concat_file = os.path.join(upload_dir, f"{meeting_id}_concat.txt")
        output_file = os.path.join(upload_dir, f"{meeting_id}_merged.wav")
        
        with open(concat_file, 'w') as f:
            for audio in audio_files:
                f.write(f"file '{audio}'\n")
        
        # Run FFmpeg
        cmd = [
            'ffmpeg', '-f', 'concat', '-safe', '0',
            '-i', concat_file,
            '-c', 'copy',
            output_file
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Update meeting with merged audio
            meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
            if meeting:
                meeting.audio_url = output_file
                db.commit()
            logger.info(f"Audio merge complete: {output_file}")
        else:
            logger.error(f"FFmpeg merge failed: {result.stderr}")
        
        # Cleanup concat file
        os.remove(concat_file)
        
    except Exception as e:
        logger.error(f"Audio merge error: {e}")


# ============================================
# Split Meeting
# ============================================

@router.post("/{meeting_id}/split", response_model=MeetingOperationResponse)
async def split_meeting(
    meeting_id: str,
    request: MeetingSplitRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Split a meeting into two parts at the specified time.
    - Creates two new meetings
    - Splits transcript segments
    - Optionally splits audio file
    """
    # Get original meeting
    original = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not original:
        raise HTTPException(status_code=404, detail="Meeting not found")
    
    split_time = request.split_at_seconds
    
    # Validate split time
    if original.duration and split_time >= original.duration:
        raise HTTPException(
            status_code=400, 
            detail=f"Split time must be less than meeting duration ({original.duration}s)"
        )
    
    # Create two new meetings
    meeting1_id = str(uuid.uuid4())
    meeting2_id = str(uuid.uuid4())
    
    title1 = request.title_part1 or f"{original.title} (Part 1)"
    title2 = request.title_part2 or f"{original.title} (Part 2)"
    
    meeting1 = Meeting(
        id=meeting1_id,
        title=title1,
        status=MeetingStatus.COMPLETED,
        language=original.language,
        template_name=original.template_name,
        duration=split_time
    )
    
    meeting2 = Meeting(
        id=meeting2_id,
        title=title2,
        status=MeetingStatus.COMPLETED,
        language=original.language,
        template_name=original.template_name,
        duration=(original.duration - split_time) if original.duration else None
    )
    
    db.add(meeting1)
    db.add(meeting2)
    db.flush()
    
    # Split segments
    segments = db.query(TranscriptSegment).filter(
        TranscriptSegment.meeting_id == meeting_id
    ).order_by(TranscriptSegment.order).all()
    
    transcript1 = []
    transcript2 = []
    order1 = 0
    order2 = 0
    
    for seg in segments:
        if seg.end_time <= split_time:
            # Entirely in part 1
            new_seg = TranscriptSegment(
                id=str(uuid.uuid4()),
                meeting_id=meeting1_id,
                order=order1,
                start_time=seg.start_time,
                end_time=seg.end_time,
                speaker=seg.speaker,
                content_raw=seg.content_raw,
                content_polished=seg.content_polished,
                is_final=seg.is_final
            )
            db.add(new_seg)
            transcript1.append(seg.content_raw)
            order1 += 1
            
        elif seg.start_time >= split_time:
            # Entirely in part 2
            new_seg = TranscriptSegment(
                id=str(uuid.uuid4()),
                meeting_id=meeting2_id,
                order=order2,
                start_time=seg.start_time - split_time,
                end_time=seg.end_time - split_time,
                speaker=seg.speaker,
                content_raw=seg.content_raw,
                content_polished=seg.content_polished,
                is_final=seg.is_final
            )
            db.add(new_seg)
            transcript2.append(seg.content_raw)
            order2 += 1
            
        else:
            # Segment spans split point - duplicate to both
            new_seg1 = TranscriptSegment(
                id=str(uuid.uuid4()),
                meeting_id=meeting1_id,
                order=order1,
                start_time=seg.start_time,
                end_time=split_time,
                speaker=seg.speaker,
                content_raw=seg.content_raw,
                is_final=seg.is_final
            )
            new_seg2 = TranscriptSegment(
                id=str(uuid.uuid4()),
                meeting_id=meeting2_id,
                order=order2,
                start_time=0,
                end_time=seg.end_time - split_time,
                speaker=seg.speaker,
                content_raw=seg.content_raw,
                is_final=seg.is_final
            )
            db.add(new_seg1)
            db.add(new_seg2)
            transcript1.append(seg.content_raw)
            transcript2.append(seg.content_raw)
            order1 += 1
            order2 += 1
    
    meeting1.transcript_raw = "\n".join(transcript1)
    meeting2.transcript_raw = "\n".join(transcript2)
    
    # Schedule audio split in background
    if original.audio_url and os.path.exists(original.audio_url):
        background_tasks.add_task(
            split_audio_file,
            original.audio_url,
            split_time,
            meeting1_id,
            meeting2_id,
            db
        )
    
    db.commit()
    
    return MeetingOperationResponse(
        success=True,
        message=f"Split meeting into two parts at {split_time}s",
        new_meeting_ids=[meeting1_id, meeting2_id]
    )


async def split_audio_file(
    audio_path: str, 
    split_time: float, 
    meeting1_id: str, 
    meeting2_id: str,
    db: Session
):
    """Background task to split audio file using FFmpeg"""
    try:
        upload_dir = os.path.dirname(audio_path)
        ext = os.path.splitext(audio_path)[1]
        
        output1 = os.path.join(upload_dir, f"{meeting1_id}{ext}")
        output2 = os.path.join(upload_dir, f"{meeting2_id}{ext}")
        
        # Split part 1 (from start to split_time)
        cmd1 = [
            'ffmpeg', '-i', audio_path,
            '-t', str(split_time),
            '-c', 'copy',
            output1
        ]
        
        # Split part 2 (from split_time to end)
        cmd2 = [
            'ffmpeg', '-i', audio_path,
            '-ss', str(split_time),
            '-c', 'copy',
            output2
        ]
        
        result1 = subprocess.run(cmd1, capture_output=True, text=True)
        result2 = subprocess.run(cmd2, capture_output=True, text=True)
        
        if result1.returncode == 0 and result2.returncode == 0:
            # Update meetings with split audio
            m1 = db.query(Meeting).filter(Meeting.id == meeting1_id).first()
            m2 = db.query(Meeting).filter(Meeting.id == meeting2_id).first()
            if m1:
                m1.audio_url = output1
            if m2:
                m2.audio_url = output2
            db.commit()
            logger.info(f"Audio split complete: {output1}, {output2}")
        else:
            logger.error(f"FFmpeg split failed: {result1.stderr} | {result2.stderr}")
        
    except Exception as e:
        logger.error(f"Audio split error: {e}")

@router.post("/{meeting_id}/upload-url", response_model=UploadUrlResponse)
def generate_upload_url(
    meeting_id: str,
    request: UploadUrlRequest,
    db: Session = Depends(get_db)
):
    """Generate a GCS signed URL for direct audio upload from frontend"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # Get bucket name from environment (Terraform sets GCS_BUCKET)
    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="GCS_BUCKET not configured on server")

    import google.auth
    from google.auth.transport import requests as google_requests

    try:
        credentials, project_id = google.auth.default()
        if credentials.token is None:
            credentials.refresh(google_requests.Request())
            
        sa_email = getattr(credentials, "service_account_email", f"meetchi-cloudrun@{project_id}.iam.gserviceaccount.com")

        client = gcs_storage.Client(project=project_id)
        bucket = client.bucket(bucket_name)

        # Support extension from filename
        ext = os.path.splitext(request.filename)[1] if request.filename else ".webm"
        blob_name = f"audio/{meeting_id}{ext}"
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=60),
            method="PUT",
            content_type=request.contentType,
            service_account_email=sa_email,
            access_token=credentials.token
        )

        # Pre-assign audio_url to the meeting so it can be processed later
        meeting.audio_url = f"gs://{bucket_name}/{blob_name}"
        db.commit()

        return UploadUrlResponse(uploadUrl=url, upload_url=url)
    except Exception as e:
        logger.error(f"Failed to generate signed url: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate upload URL")


@router.post("/{meeting_id}/upload-resumable")
def generate_resumable_upload_url(
    meeting_id: str,
    request: UploadUrlRequest,
    db: Session = Depends(get_db)
):
    """Generate a GCS resumable upload session URI.
    
    Resumable uploads are faster than signed PUT for large files because:
    - GCS handles chunking server-side (256KB min chunk)
    - Supports pause/resume without re-uploading
    - Frontend can upload in large chunks (8MB+) with progress tracking
    - More resistant to network interruptions
    
    The returned session_uri is valid for 7 days.
    """
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="GCS_BUCKET not configured on server")

    try:
        import google.auth
        from google.auth.transport import requests as google_requests
        import requests

        credentials, project_id = google.auth.default()
        if credentials.token is None:
            credentials.refresh(google_requests.Request())

        ext = os.path.splitext(request.filename)[1] if request.filename else ".webm"
        blob_name = f"audio/{meeting_id}{ext}"
        content_type = request.contentType or "application/octet-stream"

        # Initiate resumable upload via GCS JSON API
        initiate_url = (
            f"https://storage.googleapis.com/upload/storage/v1/b/{bucket_name}/o"
            f"?uploadType=resumable&name={blob_name}"
        )
        headers = {
            "Authorization": f"Bearer {credentials.token}",
            "Content-Type": "application/json",
            "X-Upload-Content-Type": content_type,
        }
        metadata = {"contentType": content_type}

        resp = requests.post(initiate_url, headers=headers, json=metadata, timeout=10)
        if resp.status_code != 200:
            logger.error(f"GCS resumable initiation failed: {resp.status_code} {resp.text[:200]}")
            raise HTTPException(status_code=502, detail="Failed to initiate resumable upload")

        session_uri = resp.headers.get("Location")
        if not session_uri:
            raise HTTPException(status_code=502, detail="No session URI in GCS response")

        # Pre-assign audio_url
        meeting.audio_url = f"gs://{bucket_name}/{blob_name}"
        db.commit()

        logger.info(f"Resumable upload session created for {meeting_id} ({blob_name})")
        return {"session_uri": session_uri, "blob_name": blob_name}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create resumable upload session: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create resumable upload session")


@router.post("/{meeting_id}/upload", tags=["Meeting Operations"])
async def upload_audio_proxy(
    meeting_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Proxy audio upload: browser sends multipart to backend, backend streams to GCS.
    Avoids direct browser→GCS connections that may be blocked by corporate proxies."""
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id, Meeting.deleted_at.is_(None)
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="GCS_BUCKET not configured on server")

    try:
        ext = os.path.splitext(file.filename or "audio.webm")[1] or ".webm"
        blob_name = f"audio/{meeting_id}{ext}"

        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        # Stream file directly to GCS — avoids loading entire file into RAM
        blob.upload_from_file(
            file.file,
            content_type=file.content_type or "audio/webm",
            rewind=True,
        )

        meeting.audio_url = f"gs://{bucket_name}/{blob_name}"
        db.commit()

        logger.info(f"[ProxyUpload] meeting={meeting_id} blob={blob_name} size={blob.size}")
        return {"audio_url": meeting.audio_url, "message": "Upload successful"}
    except Exception as e:
        logger.error(f"[ProxyUpload] Failed for meeting {meeting_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


def _compose_blobs(bucket, sources: list, destination, temp_prefix: str) -> None:
    """Compose source blobs into destination, handling GCS's 32-source limit recursively."""
    if len(sources) <= 32:
        destination.compose(sources)
        return
    groups = [sources[i:i + 32] for i in range(0, len(sources), 32)]
    group_blobs = []
    for idx, group in enumerate(groups):
        temp = bucket.blob(f"{temp_prefix}group_{idx:04d}")
        temp.compose(group)
        group_blobs.append(temp)
    _compose_blobs(bucket, group_blobs, destination, temp_prefix + "meta_")
    for t in group_blobs:
        try:
            t.delete()
        except Exception:
            pass


@router.post("/{meeting_id}/upload-chunk", tags=["Meeting Operations"])
async def upload_chunk(
    meeting_id: str,
    request: Request,
    chunk_index: int = Query(..., alias="index", ge=0),
    total_chunks: int = Query(..., alias="total", ge=1),
    filename: str = Query(default="audio.webm"),
    upload_id: str = Query(default="", description="前端生成的上傳追蹤 ID，貫穿前後端 log"),
    db: Session = Depends(get_db),
):
    """Receive one binary chunk and store in GCS. On the last chunk, compose all parts
    into the final audio file. Each chunk is 1 MB, safely under enterprise proxy limits."""
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id, Meeting.deleted_at.is_(None)
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="GCS_BUCKET not configured on server")

    chunk_data = await request.body()
    if not chunk_data:
        raise HTTPException(status_code=400, detail="Empty chunk body")

    uid = f" upload_id={upload_id}" if upload_id else ""
    try:
        client = gcs_storage.Client()
        bucket = client.bucket(bucket_name)

        # Store chunk as a separate blob
        chunk_blob = bucket.blob(f"audio/{meeting_id}/parts/{chunk_index:06d}")
        chunk_blob.upload_from_string(chunk_data, content_type="application/octet-stream")
        logger.info(f"[ChunkedUpload] meeting={meeting_id} chunk={chunk_index}/{total_chunks} size={len(chunk_data)}{uid}")

        # If not the last chunk, just confirm receipt
        if chunk_index < total_chunks - 1:
            return {"status": "chunk_received", "index": chunk_index}

        # === D (2026-07-08): compose 前驗證所有 parts 齊全 ===
        # 先前無腦 range(total) compose，若中間有缺塊 → compose 失敗或產生壞檔。
        # 改為逐一 exists() 檢查，缺塊回明確 409 + 缺塊清單，讓前端只補缺塊後重試。
        source_blobs = [
            bucket.blob(f"audio/{meeting_id}/parts/{i:06d}")
            for i in range(total_chunks)
        ]
        missing = [i for i, b in enumerate(source_blobs) if not b.exists()]
        if missing:
            logger.warning(
                f"[ChunkedUpload] meeting={meeting_id} compose aborted: "
                f"{len(missing)} missing parts {missing[:20]}{'...' if len(missing) > 20 else ''}{uid}"
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "missing_chunks",
                    "message": f"缺少 {len(missing)} 個分塊，請補傳後再合成",
                    "missing_indices": missing,
                    "total_chunks": total_chunks,
                },
            )

        # Last chunk (all parts present): compose all parts into final audio file
        ext = os.path.splitext(filename)[1] if filename else ".webm"
        if not ext:
            ext = ".webm"
        final_blob_name = f"audio/{meeting_id}{ext}"
        final_blob = bucket.blob(final_blob_name)
        _compose_blobs(bucket, source_blobs, final_blob, f"audio/{meeting_id}/meta/")

        # Remux to proper M4A container if the composed file is raw ADTS AAC.
        # Raw AAC (0xFFF1) has no moov atom → browsers can't parse duration.
        # ffmpeg remux adds ftyp+moov+mdat with faststart for streaming.
        import tempfile, subprocess
        with tempfile.TemporaryDirectory(prefix="meetchi-remux-") as tmpdir:
            raw_path = os.path.join(tmpdir, f"raw{ext}")
            final_blob.download_to_filename(raw_path)

            # Check if file needs remux: raw ADTS starts with 0xFF 0xF1
            with open(raw_path, "rb") as f:
                header = f.read(4)
            needs_remux = (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF0) == 0xF0)

            if needs_remux:
                out_path = os.path.join(tmpdir, "remuxed.m4a")
                result = subprocess.run(
                    ["ffmpeg", "-y", "-i", raw_path, "-c", "copy", "-movflags", "+faststart", out_path],
                    capture_output=True, timeout=300
                )
                if result.returncode == 0:
                    final_blob.upload_from_filename(out_path, content_type="audio/mp4")
                    # Force extension to .m4a since we remuxed
                    if ext.lower() != ".m4a":
                        new_blob_name = f"audio/{meeting_id}.m4a"
                        new_blob = bucket.blob(new_blob_name)
                        bucket.copy_blob(final_blob, bucket, new_blob_name)
                        final_blob.delete()
                        final_blob = new_blob
                        final_blob_name = new_blob_name
                    logger.info(f"[ChunkedUpload] Remuxed raw AAC → M4A (faststart) for {meeting_id}")
                else:
                    logger.warning(f"[ChunkedUpload] ffmpeg remux failed: {result.stderr[:500]}")
                    # Fall through — keep composed file as-is
            else:
                logger.info(f"[ChunkedUpload] File already has container (no remux needed) for {meeting_id}")

        # Set proper content-type after compose/remux
        mime_map = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav", 
                    ".webm": "audio/webm", ".ogg": "audio/ogg", ".aac": "audio/aac"}
        final_blob.content_type = mime_map.get(os.path.splitext(final_blob_name)[1].lower(), "audio/mp4")
        final_blob.patch()

        # Cleanup chunk files
        for blob in source_blobs:
            try:
                blob.delete()
            except Exception:
                pass

        meeting.audio_url = f"gs://{bucket_name}/{final_blob_name}"
        db.commit()

        logger.info(f"[ChunkedUpload] Complete: meeting={meeting_id} chunks={total_chunks} blob={final_blob_name}")
        return {"status": "complete", "audio_url": meeting.audio_url}

    except HTTPException:
        # 明確的業務錯誤（如 409 缺塊）直接往上拋，不要被下方轉成 500
        raise
    except Exception as e:
        logger.error(f"[ChunkedUpload] Failed for meeting {meeting_id} chunk {chunk_index}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chunk upload failed: {str(e)}")


@router.get("/{meeting_id}/upload-parts", tags=["Meeting Operations"])
async def list_upload_parts(
    meeting_id: str,
    total: int = Query(..., ge=1, description="預期總分塊數"),
    db: Session = Depends(get_db),
):
    """C (2026-07-08): 回傳已存在於 GCS 的分塊 index，供前端「只補缺塊」續傳。

    前端上傳前先查此端點，跳過已完成的分塊，中斷後重傳只補缺塊，
    大檔中斷可省去大量重複傳輸。
    """
    meeting = db.query(Meeting).filter(
        Meeting.id == meeting_id, Meeting.deleted_at.is_(None)
    ).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    bucket_name = os.getenv("GCS_BUCKET")
    if not bucket_name:
        raise HTTPException(status_code=500, detail="GCS_BUCKET not configured on server")

    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    prefix = f"audio/{meeting_id}/parts/"
    # 以 list_blobs 一次列出已上傳分塊（避免逐一 exists() N 次呼叫）
    existing = set()
    for blob in client.list_blobs(bucket, prefix=prefix):
        name = blob.name.rsplit("/", 1)[-1]
        if name.isdigit():
            existing.add(int(name))
    uploaded = sorted(i for i in existing if i < total)
    missing = [i for i in range(total) if i not in existing]
    return {
        "meeting_id": meeting_id,
        "total": total,
        "uploaded_indices": uploaded,
        "missing_indices": missing,
        "complete": len(missing) == 0,
    }


class AudioUrlResponse(BaseModel):
    audio_url: str

@router.get("/{meeting_id}/audio-url", response_model=AudioUrlResponse)
def get_audio_url(
    meeting_id: str,
    db: Session = Depends(get_db)
):
    """Generate a GCS signed URL for direct audio download/playback from frontend"""
    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.audio_url or not meeting.audio_url.startswith("gs://"):
        # Not a GCS URL or no audio
        return AudioUrlResponse(audio_url=meeting.audio_url or "")

    import google.auth
    from google.auth.transport import requests as google_requests

    try:
        credentials, project_id = google.auth.default()
        if credentials.token is None:
            credentials.refresh(google_requests.Request())
            
        sa_email = getattr(credentials, "service_account_email", f"meetchi-cloudrun@{project_id}.iam.gserviceaccount.com")

        client = gcs_storage.Client(project=project_id)
        
        # Parse gs://bucket_name/blob_name
        parts = meeting.audio_url.replace("gs://", "").split("/", 1)
        if len(parts) != 2:
            return AudioUrlResponse(audio_url="")
            
        bucket_name, blob_name = parts[0], parts[1]
        bucket = client.bucket(bucket_name)

        # 2026-07-06 Feature #1：若存在降噪後的播放檔則優先提供，讓使用者聽到後端
        # 降噪處理後的音檔（找不到則回退原始音檔）。音檔為扁平結構 audio/{id}.m4a，
        # 故降噪檔以 meeting_id 命名放同目錄：{dir}/{meeting_id}_denoised.m4a。
        dir_prefix = blob_name.rsplit("/", 1)[0] if "/" in blob_name else ""
        denoised_blob_name = f"{dir_prefix}/{meeting_id}_denoised.m4a" if dir_prefix else f"{meeting_id}_denoised.m4a"
        try:
            denoised_blob = bucket.blob(denoised_blob_name)
            if denoised_blob.exists():
                blob_name = denoised_blob_name
                logger.info(f"[audio-url] serving denoised playback for {meeting_id}: {denoised_blob_name}")
        except Exception as _de:
            logger.warning(f"[audio-url] denoised probe failed ({meeting_id}), fallback original: {_de}")

        blob = bucket.blob(blob_name)

        # Reload blob metadata to get the actual stored content-type
        # This avoids mismatch when file extension doesn't match actual format
        # (e.g., .m4a file that's actually raw ADTS AAC)
        blob.reload()
        stored_content_type = blob.content_type

        # If GCS has no content-type or it's generic, infer from extension
        import mimetypes
        if not stored_content_type or stored_content_type in ("application/octet-stream", "None"):
            ext = os.path.splitext(blob_name)[1].lower()
            mime_map = {".m4a": "audio/mp4", ".mp3": "audio/mpeg", ".wav": "audio/wav", ".webm": "audio/webm", ".ogg": "audio/ogg", ".aac": "audio/aac"}
            stored_content_type = mime_map.get(ext) or mimetypes.guess_type(blob_name)[0] or "audio/mpeg"

        url = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(minutes=120),
            method="GET",
            service_account_email=sa_email,
            access_token=credentials.token,
            response_type=stored_content_type,
        )

        return AudioUrlResponse(audio_url=url)
    except Exception as e:
        logger.error(f"Failed to generate signed GET url: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate playback URL")


@router.get("/{meeting_id}/audio-stream")
def stream_audio(
    meeting_id: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """Stream audio through backend proxy — bypasses enterprise proxy/firewall
    blocking direct GCS access. Supports Range requests for seeking."""
    from fastapi.responses import StreamingResponse

    meeting = db.query(Meeting).filter(Meeting.id == meeting_id).first()
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.audio_url or not meeting.audio_url.startswith("gs://"):
        raise HTTPException(status_code=404, detail="No audio available")

    parts = meeting.audio_url.replace("gs://", "").split("/", 1)
    if len(parts) != 2:
        raise HTTPException(status_code=404, detail="Invalid audio URL")

    bucket_name, blob_name = parts[0], parts[1]
    client = gcs_storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    blob.reload()

    file_size = blob.size
    content_type = blob.content_type or "audio/mp4"

    # Parse Range header
    range_header = request.headers.get("range")
    if range_header:
        # e.g. "bytes=0-1023" or "bytes=0-"
        range_spec = range_header.replace("bytes=", "")
        parts_range = range_spec.split("-")
        start = int(parts_range[0]) if parts_range[0] else 0
        end_str = parts_range[1] if len(parts_range) > 1 else ""
        
        # For open-ended range (bytes=0-), limit to prevent Cloud Run timeout
        # Most browsers request in chunks anyway, so this is just a safety net
        # Cloud Run response limit: 32MB. Use 31MB to leave room for headers.
        MAX_RANGE_CHUNK = 31 * 1024 * 1024  # 31MB max per request
        if end_str:
            end = min(int(end_str), file_size - 1)
        else:
            # Open-ended: cap at 32MB from start
            end = min(start + MAX_RANGE_CHUNK - 1, file_size - 1)
        
        end = min(end, file_size - 1)
        length = end - start + 1

        def iter_range():
            stream = blob.open("rb")
            stream.seek(start)
            remaining = length
            chunk_size = 64 * 1024  # 64KB chunks
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = stream.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data
            stream.close()

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=3600",
        }
        return StreamingResponse(iter_range(), status_code=206, headers=headers, media_type=content_type)
    else:
        # No Range header: treat as bytes=0-31MB to prevent Cloud Run timeout on large files
        # Browsers will automatically request more chunks if needed
        # Cloud Run response limit: 32MB. Use 31MB to leave room for headers.
        MAX_INITIAL_CHUNK = 31 * 1024 * 1024  # 31MB
        start = 0
        end = min(MAX_INITIAL_CHUNK - 1, file_size - 1)
        length = end - start + 1
        
        def iter_range():
            stream = blob.open("rb")
            stream.seek(start)
            remaining = length
            chunk_size = 64 * 1024
            while remaining > 0:
                read_size = min(chunk_size, remaining)
                data = stream.read(read_size)
                if not data:
                    break
                remaining -= len(data)
                yield data
            stream.close()
        
        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=3600",
        }
        return StreamingResponse(iter_range(), status_code=206, headers=headers, media_type=content_type)
