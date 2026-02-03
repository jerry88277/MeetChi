"""
Meeting Merge/Split API Routes
Allows combining multiple meetings or splitting a meeting into parts
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import uuid
import os
import subprocess
import logging

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
