"""
diarization_community1.py — Standalone speaker diarization using pyannote community-1.

Loads model from local path (baked into Docker image via GCS).
No HuggingFace token required at runtime.

Usage:
    from app.diarization_community1 import diarize_full_audio
    segments = diarize_full_audio("/path/to/audio.wav")
    # Returns: [{"speaker": "SPEAKER_00", "start": 0.0, "end": 5.2}, ...]
"""

import os
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Model path: baked into image at build time
MODEL_PATH = os.getenv(
    "PYANNOTE_MODEL_PATH",
    "/app/models/pyannote/speaker-diarization-community-1"
)

# Lazy-loaded pipeline singleton
_pipeline = None


def _load_pipeline():
    """Load pyannote pipeline from local model path (no network required)."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    import torch
    from pyannote.audio import Pipeline
    import pyannote.audio.core.model as _pam

    if not os.path.isdir(MODEL_PATH):
        raise FileNotFoundError(
            f"Pyannote model not found at {MODEL_PATH}. "
            "Ensure model is baked into the Docker image."
        )

    logger.info(f"Loading pyannote community-1 from {MODEL_PATH}")

    # PyTorch 2.6+ defaults weights_only=True which breaks pyannote checkpoints.
    # lightning/fabric also explicitly passes weights_only=True.
    # Model was security-scanned (ModelScan PASS) — safe to load with weights_only=False.
    _orig_torch_load = torch.load
    def _patched_load(*args, **kwargs):
        kwargs["weights_only"] = False
        return _orig_torch_load(*args, **kwargs)
    torch.load = _patched_load

    # Lightning 2.4+ uses meta device init, causing "Cannot copy out of meta tensor"
    # in pyannote's Model.setup(). Monkey-patch to skip .to(device) on meta tensors.
    _orig_setup = _pam.Model.setup
    def _safe_setup(self):
        try:
            _orig_setup(self)
        except NotImplementedError:
            logger.warning("Skipping meta tensor .to(device) in Model.setup()")
    _pam.Model.setup = _safe_setup

    device = "cuda" if torch.cuda.is_available() else "cpu"

    try:
        _pipeline = Pipeline.from_pretrained(MODEL_PATH)
        try:
            _pipeline.to(torch.device(device))
        except (NotImplementedError, RuntimeError) as move_err:
            if "meta tensor" in str(move_err) or "Cannot copy" in str(move_err):
                logger.warning(
                    f"Cannot move pipeline to {device} (meta tensor), "
                    f"running on CPU: {move_err}"
                )
            else:
                raise
    finally:
        torch.load = _orig_torch_load
        _pam.Model.setup = _orig_setup

    logger.info(f"Pyannote community-1 loaded on {device}")

    return _pipeline


def diarize_full_audio(
    audio_path: str,
    min_speakers: Optional[int] = None,
    max_speakers: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Run speaker diarization on the full audio file.

    Args:
        audio_path: Path to audio file (any format ffmpeg supports)
        min_speakers: Minimum expected speakers (optional)
        max_speakers: Maximum expected speakers (optional)

    Returns:
        List of speaker segments: [{"speaker": "SPEAKER_00", "start": 0.0, "end": 5.2}, ...]
    """
    import torchaudio

    pipeline = _load_pipeline()

    logger.info(f"Running diarization on {audio_path}")

    # Load audio (pyannote handles resampling internally)
    waveform, sample_rate = torchaudio.load(audio_path)
    audio_input = {"waveform": waveform, "sample_rate": sample_rate}

    # Build kwargs
    kwargs = {}
    if min_speakers is not None:
        kwargs["min_speakers"] = min_speakers
    if max_speakers is not None:
        kwargs["max_speakers"] = max_speakers

    # Run diarization
    result = pipeline(audio_input, **kwargs)

    # pyannote 4.x community-1 returns DiarizeOutput (not Annotation directly)
    # DiarizeOutput is a dataclass with .exclusive_speaker_diarization (Annotation)
    if hasattr(result, 'itertracks'):
        annotation = result
    elif hasattr(result, 'exclusive_speaker_diarization'):
        annotation = result.exclusive_speaker_diarization
    elif hasattr(result, 'annotation'):
        annotation = result.annotation
    elif isinstance(result, tuple):
        annotation = result[0]
    else:
        # Try to iterate keys/values as a fallback
        raise TypeError(
            f"Unexpected diarization output type: {type(result).__name__}. "
            f"Attributes: {dir(result)}"
        )

    # Extract segments
    segments = []
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        segments.append({
            "speaker": speaker,
            "start": round(turn.start, 2),
            "end": round(turn.end, 2),
        })

    speakers = set(s["speaker"] for s in segments)
    logger.info(
        f"Diarization complete: {len(segments)} segments, "
        f"{len(speakers)} speakers: {speakers}"
    )

    return segments


def assign_speakers_to_transcript(
    transcript_segments: List[Dict[str, Any]],
    diarization_segments: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Assign global speaker labels to transcript segments based on time overlap.

    Args:
        transcript_segments: [{start_time, end_time, content_raw, speaker, ...}, ...]
        diarization_segments: [{speaker, start, end}, ...] from diarize_full_audio()

    Returns:
        transcript_segments with updated 'speaker' field
    """
    for tseg in transcript_segments:
        seg_start = tseg.get("start_time", 0)
        seg_end = tseg.get("end_time", 0)

        # Find speaker with maximum overlap
        overlaps: Dict[str, float] = {}
        for dseg in diarization_segments:
            overlap = min(seg_end, dseg["end"]) - max(seg_start, dseg["start"])
            if overlap > 0:
                spk = dseg["speaker"]
                overlaps[spk] = overlaps.get(spk, 0) + overlap

        if overlaps:
            tseg["speaker"] = max(overlaps, key=overlaps.get)

    return transcript_segments
