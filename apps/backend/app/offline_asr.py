"""
Offline ASR Provider — Abstraction for post-recording high-quality transcription.

Plan B Architecture:
  - Realtime: Gemini Flash Lite API (unchanged)
  - Offline:  Breeze-ASR-25 via faster-whisper (CTranslate2) + WhisperX diarization

Provider Pattern:
  OfflineASRProvider (ABC)
    ├── BreezeASRProvider — CTranslate2 + WhisperX (current)
    └── Chirp3Provider    — Google STT V2 (future Plan D)
"""

import os
import logging
import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================
# Data Classes
# ============================================

@dataclass
class ASRSegment:
    """A single transcribed segment with optional speaker label."""
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    confidence: float = 1.0
    language: str = "zh"
    words: List[Dict] = field(default_factory=list)


@dataclass
class ASRResult:
    """Complete ASR result from offline processing."""
    segments: List[ASRSegment]
    language: str = "zh"
    duration: float = 0.0
    num_speakers: int = 0

    def to_transcript_text(self, include_speaker: bool = True) -> str:
        """Format segments into readable transcript text."""
        lines = []
        for seg in self.segments:
            prefix = f"[{seg.speaker}] " if include_speaker and seg.speaker else ""
            lines.append(f"{prefix}{seg.text}")
        return "\n".join(lines)


# ============================================
# ASR Configuration
# ============================================

class ASRDevice(Enum):
    CPU = "cpu"
    CUDA = "cuda"
    AUTO = "auto"


@dataclass
class BreezeASRConfig:
    """Configuration for Breeze ASR (CTranslate2/faster-whisper)."""
    model_name: str = "SoybeanMilk/faster-whisper-Breeze-ASR-25"
    device: str = "auto"  # "auto", "cuda", "cpu"
    compute_type: str = "auto"  # "float16", "int8_float16", "int8", "auto"
    beam_size: int = 5
    language: str = "zh"
    vad_filter: bool = True
    vad_parameters: Dict = field(default_factory=lambda: {
        "min_silence_duration_ms": 500,
        "speech_pad_ms": 200,
    })
    # WhisperX diarization settings
    enable_diarization: bool = True
    min_speakers: int = 1
    max_speakers: int = 10
    hf_token: Optional[str] = None  # Required for pyannote diarization


# ============================================
# Abstract Base Class
# ============================================

class OfflineASRProvider(ABC):
    """
    Abstract interface for offline ASR providers.
    
    Subclasses implement the actual transcription + diarization logic.
    This pattern allows easy swapping between:
      - BreezeASRProvider (GPU, CTranslate2)
      - Chirp3Provider (API, Google STT V2) — future
    """

    @abstractmethod
    async def transcribe_with_diarization(
        self,
        audio_path: str,
        language: str = "zh",
        **kwargs,
    ) -> ASRResult:
        """
        Transcribe audio file with speaker diarization.
        
        Args:
            audio_path: Path to audio file (WAV, MP3, etc.)
            language: Source language code
            **kwargs: Provider-specific options
            
        Returns:
            ASRResult with segments including speaker labels
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is ready to use."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider name."""
        ...


# ============================================
# Breeze ASR Provider (CTranslate2 / faster-whisper)
# ============================================

class BreezeASRProvider(OfflineASRProvider):
    """
    Offline ASR using SoybeanMilk/faster-whisper-Breeze-ASR-25.
    
    Pipeline:
      1. faster-whisper transcribe (CTranslate2 engine)
      2. WhisperX forced alignment (word-level timestamps)
      3. pyannote speaker diarization
      4. WhisperX speaker assignment
    """

    def __init__(self, config: Optional[BreezeASRConfig] = None):
        self.config = config or BreezeASRConfig(
            hf_token=os.getenv("HF_AUTH_TOKEN") or os.getenv("HF_TOKEN"),
        )
        self._model = None
        self._initialized = False

    @property
    def provider_name(self) -> str:
        return "Breeze-ASR-25 (CTranslate2)"

    def is_available(self) -> bool:
        """Check if faster-whisper and dependencies are importable."""
        try:
            import faster_whisper  # noqa: F401
            return True
        except ImportError:
            return False

    def _resolve_device(self) -> str:
        """Resolve 'auto' device to actual device."""
        if self.config.device != "auto":
            return self.config.device
        try:
            import torch
            return "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            return "cpu"

    def _resolve_compute_type(self, device: str) -> str:
        """Resolve 'auto' compute type based on device."""
        if self.config.compute_type != "auto":
            return self.config.compute_type
        return "float16" if device == "cuda" else "int8"

    def _load_model(self):
        """Lazy-load the faster-whisper model."""
        if self._model is not None:
            return

        from faster_whisper import WhisperModel

        device = self._resolve_device()
        compute_type = self._resolve_compute_type(device)

        logger.info(
            f"Loading Breeze ASR model: {self.config.model_name} "
            f"(device={device}, compute_type={compute_type})"
        )

        self._model = WhisperModel(
            self.config.model_name,
            device=device,
            compute_type=compute_type,
        )
        self._initialized = True
        logger.info("Breeze ASR model loaded successfully.")

    def _transcribe_sync(self, audio_path: str, language: str) -> ASRResult:
        """
        Synchronous transcription pipeline:
        1. faster-whisper transcription
        2. WhisperX alignment (if available)
        3. pyannote diarization (if enabled and available)
        """
        self._load_model()

        # --- Step 1: CTranslate2 Transcription ---
        logger.info(f"[Breeze ASR] Step 1/3: Transcribing {audio_path}")
        segments_iter, info = self._model.transcribe(
            audio_path,
            language=language,
            beam_size=self.config.beam_size,
            vad_filter=self.config.vad_filter,
            vad_parameters=self.config.vad_parameters,
            word_timestamps=True,
        )

        # Materialize iterator
        raw_segments = list(segments_iter)
        logger.info(
            f"[Breeze ASR] Transcription done: {len(raw_segments)} segments, "
            f"language={info.language}, prob={info.language_probability:.2f}, "
            f"duration={info.duration:.1f}s"
        )

        if not raw_segments:
            return ASRResult(segments=[], language=language, duration=info.duration)

        # Convert to ASRSegment list
        asr_segments = [
            ASRSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                confidence=seg.avg_log_prob,
                language=language,
                words=[
                    {"word": w.word, "start": w.start, "end": w.end, "probability": w.probability}
                    for w in (seg.words or [])
                ],
            )
            for seg in raw_segments
        ]

        # --- Step 2: WhisperX Alignment (optional) ---
        asr_segments = self._try_whisperx_alignment(audio_path, asr_segments, language)

        # --- Step 3: Speaker Diarization (optional) ---
        if self.config.enable_diarization:
            asr_segments = self._try_diarization(audio_path, asr_segments)

        num_speakers = len(set(s.speaker for s in asr_segments if s.speaker))

        return ASRResult(
            segments=asr_segments,
            language=language,
            duration=info.duration,
            num_speakers=num_speakers,
        )

    def _try_whisperx_alignment(
        self, audio_path: str, segments: List[ASRSegment], language: str
    ) -> List[ASRSegment]:
        """Attempt WhisperX forced alignment for better word-level timestamps."""
        try:
            import whisperx

            device = self._resolve_device()
            logger.info("[Breeze ASR] Step 2/3: WhisperX alignment")

            audio = whisperx.load_audio(audio_path)
            align_model, align_metadata = whisperx.load_align_model(
                language_code=language, device=device
            )

            # Convert ASRSegment to WhisperX format
            whisperx_segments = [
                {"start": s.start, "end": s.end, "text": s.text} for s in segments
            ]
            result = whisperx.align(
                whisperx_segments, align_model, align_metadata, audio, device
            )

            # Update segments with aligned timestamps
            aligned = result.get("segments", [])
            if aligned:
                updated = []
                for a in aligned:
                    updated.append(ASRSegment(
                        start=a.get("start", 0),
                        end=a.get("end", 0),
                        text=a.get("text", ""),
                        language=language,
                        words=a.get("words", []),
                    ))
                logger.info(f"[Breeze ASR] Alignment done: {len(updated)} segments")
                return updated

        except ImportError:
            logger.info("[Breeze ASR] WhisperX not available, skipping alignment")
        except Exception as e:
            logger.warning(f"[Breeze ASR] Alignment failed: {e}, using raw timestamps")

        return segments

    def _try_diarization(
        self, audio_path: str, segments: List[ASRSegment]
    ) -> List[ASRSegment]:
        """Attempt speaker diarization using WhisperX + pyannote."""
        if not self.config.hf_token:
            logger.warning(
                "[Breeze ASR] HF_TOKEN not set, skipping diarization. "
                "Set HF_AUTH_TOKEN env var for speaker diarization."
            )
            return segments

        try:
            import whisperx

            device = self._resolve_device()
            logger.info("[Breeze ASR] Step 3/3: Speaker diarization")

            diarize_model = whisperx.DiarizationPipeline(
                use_auth_token=self.config.hf_token,
                device=device,
            )
            diarize_segments = diarize_model(
                audio_path,
                min_speakers=self.config.min_speakers,
                max_speakers=self.config.max_speakers,
            )

            # Convert to WhisperX format for assignment
            whisperx_result = {
                "segments": [
                    {"start": s.start, "end": s.end, "text": s.text, "words": s.words}
                    for s in segments
                ]
            }
            result = whisperx.assign_word_speakers(diarize_segments, whisperx_result)

            # Update segments with speaker labels
            assigned = result.get("segments", [])
            updated = []
            for a in assigned:
                updated.append(ASRSegment(
                    start=a.get("start", 0),
                    end=a.get("end", 0),
                    text=a.get("text", ""),
                    speaker=a.get("speaker"),
                    language=segments[0].language if segments else "zh",
                    words=a.get("words", []),
                ))

            num_speakers = len(set(s.speaker for s in updated if s.speaker))
            logger.info(
                f"[Breeze ASR] Diarization done: {num_speakers} speakers detected"
            )
            return updated

        except ImportError:
            logger.info("[Breeze ASR] WhisperX/pyannote not available, skipping diarization")
        except Exception as e:
            logger.warning(f"[Breeze ASR] Diarization failed: {e}")

        return segments

    async def transcribe_with_diarization(
        self,
        audio_path: str,
        language: str = "zh",
        **kwargs,
    ) -> ASRResult:
        """
        Async wrapper — runs the sync pipeline in a thread pool.
        
        GPU inference blocks the event loop, so we offload to a thread.
        """
        logger.info(
            f"[Breeze ASR] Starting offline transcription: {audio_path} (lang={language})"
        )
        return await asyncio.to_thread(self._transcribe_sync, audio_path, language)


# ============================================
# Provider Factory
# ============================================

_provider_instance: Optional[OfflineASRProvider] = None


def get_offline_asr_provider() -> Optional[OfflineASRProvider]:
    """
    Get or create the offline ASR provider singleton.
    
    Returns None if no provider is available (e.g., CPU-only deployment).
    """
    global _provider_instance

    if _provider_instance is not None:
        return _provider_instance

    # Try Breeze ASR (GPU preferred)
    provider = BreezeASRProvider()
    if provider.is_available():
        _provider_instance = provider
        logger.info(f"Offline ASR provider: {provider.provider_name}")
        return _provider_instance

    logger.info("No offline ASR provider available (faster-whisper not installed)")
    return None
