"""
Dual ASR Module - Parallel Mandarin + Taiwanese Transcription
Uses WhisperX (Mandarin) + Whisper-Taiwanese, then LLM fusion
"""

import os
import json
import logging
import asyncio
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor
from app.llm_utils import get_gemini_client, GEMINI_MODEL

logger = logging.getLogger(__name__)

# ============================================
# Data Classes
# ============================================

@dataclass
class ASRSegment:
    """Represents a transcribed segment"""
    start: float
    end: float
    text: str
    speaker: Optional[str] = None
    confidence: float = 1.0
    language: str = "zh"


@dataclass
class ASRModel:
    """Model configuration"""
    name: str
    language: str
    model_path: str
    device: str = "cuda"
    
    
# ============================================
# Model Registry
# ============================================

class ModelRegistry:
    """Registry for ASR and LLM models"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.asr_models: Dict[str, ASRModel] = {
            "whisperx-zh": ASRModel(
                name="WhisperX Mandarin",
                language="zh",
                model_path="large-v3",
                device="cuda"
            ),
            "whisper-taiwanese": ASRModel(
                name="Whisper Taiwanese",
                language="nan",  # ISO 639-3 for Taiwanese Hokkien
                model_path="gacky1601/whisper-small-taiwanese-asr-v2",
                device="cuda"
            ),
        }
        
        self.llm_models: Dict[str, dict] = {
            "breeze-7b": {
                "name": "Breeze-7B",
                "provider": "local",
                "model_path": "MediaTek-Research/Breeze-7B-Instruct-v1_0"
            },
            "gemini-flash": {
                "name": "Gemini 2.5 Flash",
                "provider": "gcp",
                "model_id": GEMINI_MODEL
            }
        }
        
        self._initialized = True
    
    def get_asr_model(self, model_id: str) -> Optional[ASRModel]:
        return self.asr_models.get(model_id)
    
    def list_asr_models(self) -> List[dict]:
        return [
            {"id": k, "name": v.name, "language": v.language}
            for k, v in self.asr_models.items()
        ]
    
    def list_llm_models(self) -> List[dict]:
        return [
            {"id": k, "name": v["name"], "provider": v["provider"]}
            for k, v in self.llm_models.items()
        ]


# ============================================
# Dual ASR Engine
# ============================================

class DualASREngine:
    """
    Parallel ASR engine for Mandarin + Taiwanese
    Runs both models and uses LLM to select best result per segment
    """
    
    def __init__(self):
        self.registry = ModelRegistry()
        self.executor = ThreadPoolExecutor(max_workers=2)
        self._whisperx_model = None
        self._taiwanese_model = None
    
    def _load_whisperx(self):
        """Lazy load WhisperX model"""
        if self._whisperx_model is None:
            try:
                import whisperx
                device = "cuda"
                compute_type = "float16"
                self._whisperx_model = whisperx.load_model(
                    "large-v3", 
                    device, 
                    compute_type=compute_type
                )
                logger.info("WhisperX model loaded")
            except Exception as e:
                logger.error(f"Failed to load WhisperX: {e}")
                raise
        return self._whisperx_model
    
    def _load_taiwanese_model(self):
        """Lazy load Taiwanese Whisper model"""
        if self._taiwanese_model is None:
            try:
                from transformers import pipeline
                self._taiwanese_model = pipeline(
                    "automatic-speech-recognition",
                    model="gacky1601/whisper-small-taiwanese-asr-v2",
                    device="cuda"
                )
                logger.info("Taiwanese ASR model loaded")
            except Exception as e:
                logger.error(f"Failed to load Taiwanese model: {e}")
                raise
        return self._taiwanese_model
    
    def transcribe_mandarin(self, audio_path: str) -> List[ASRSegment]:
        """Transcribe using WhisperX (Mandarin)"""
        import whisperx
        
        model = self._load_whisperx()
        
        # Load audio
        audio = whisperx.load_audio(audio_path)
        
        # Transcribe
        result = model.transcribe(audio, batch_size=16, language="zh")
        
        # Align
        model_a, metadata = whisperx.load_align_model(
            language_code="zh", 
            device="cuda"
        )
        result = whisperx.align(
            result["segments"], 
            model_a, 
            metadata, 
            audio, 
            "cuda",
            return_char_alignments=False
        )
        
        # Convert to ASRSegment
        segments = []
        for seg in result.get("segments", []):
            segments.append(ASRSegment(
                start=seg.get("start", 0),
                end=seg.get("end", 0),
                text=seg.get("text", ""),
                speaker=seg.get("speaker"),
                language="zh"
            ))
        
        return segments
    
    def transcribe_taiwanese(self, audio_path: str) -> List[ASRSegment]:
        """Transcribe using Taiwanese Whisper model"""
        pipe = self._load_taiwanese_model()
        
        # Transcribe with chunk settings
        result = pipe(
            audio_path,
            chunk_length_s=30,
            stride_length_s=5,
            return_timestamps=True
        )
        
        segments = []
        for chunk in result.get("chunks", []):
            timestamps = chunk.get("timestamp", (0, 0))
            segments.append(ASRSegment(
                start=timestamps[0] if timestamps[0] else 0,
                end=timestamps[1] if timestamps[1] else 0,
                text=chunk.get("text", ""),
                language="nan"
            ))
        
        return segments
    
    async def transcribe_parallel(self, audio_path: str) -> Tuple[List[ASRSegment], List[ASRSegment]]:
        """Run both ASR models in parallel"""
        loop = asyncio.get_event_loop()
        
        # Run both transcriptions in parallel using thread pool
        mandarin_future = loop.run_in_executor(
            self.executor, 
            self.transcribe_mandarin, 
            audio_path
        )
        taiwanese_future = loop.run_in_executor(
            self.executor, 
            self.transcribe_taiwanese, 
            audio_path
        )
        
        mandarin_result, taiwanese_result = await asyncio.gather(
            mandarin_future, 
            taiwanese_future,
            return_exceptions=True
        )
        
        # Handle exceptions
        if isinstance(mandarin_result, Exception):
            logger.error(f"Mandarin ASR failed: {mandarin_result}")
            mandarin_result = []
        if isinstance(taiwanese_result, Exception):
            logger.error(f"Taiwanese ASR failed: {taiwanese_result}")
            taiwanese_result = []
        
        return mandarin_result, taiwanese_result
    
    def align_segments(
        self, 
        mandarin: List[ASRSegment], 
        taiwanese: List[ASRSegment]
    ) -> List[Tuple[Optional[ASRSegment], Optional[ASRSegment]]]:
        """Align segments from both models by time overlap"""
        aligned = []
        
        # Simple alignment: match by time overlap
        for zh_seg in mandarin:
            best_match = None
            best_overlap = 0
            
            for nan_seg in taiwanese:
                # Calculate overlap
                overlap_start = max(zh_seg.start, nan_seg.start)
                overlap_end = min(zh_seg.end, nan_seg.end)
                overlap = max(0, overlap_end - overlap_start)
                
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_match = nan_seg
            
            aligned.append((zh_seg, best_match))
        
        return aligned
    
    async def select_best_transcription(
        self, 
        zh_text: str, 
        nan_text: str,
        context: List[str] = None
    ) -> str:
        """Use LLM to select the best transcription"""
        
        # If one is empty, return the other
        if not zh_text.strip():
            return nan_text
        if not nan_text.strip():
            return zh_text
        
        # If both are similar, return Mandarin version
        if zh_text.strip() == nan_text.strip():
            return zh_text
        
        # Use LLM to decide
        prompt = f"""你是一個語音辨識專家。以下是同一段音訊的兩種轉錄結果：

國語版本：{zh_text}
台語版本：{nan_text}

{"上下文：" + " ".join(context) if context else ""}

請選擇較正確、較通順的版本。如果是台語內容，保留台語版本；如果是國語，保留國語版本；如果是混合，請整合兩者。

請以 JSON 格式回覆，key 為 "text"，value 為最終選擇的文字。"""

        try:
            client = get_gemini_client()
            if not client:
                 logger.warning("Gemini client not available for selection, fallback to Mandarin")
                 return zh_text

            def _call_gemini():
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1,
                        "max_output_tokens": 200
                    }
                )
                return json.loads(response.text)

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(self.executor, _call_gemini)
            return result.get("text", zh_text).strip()
            
        except Exception as e:
            logger.error(f"LLM selection failed: {e}")
        
        # Fallback to Mandarin
        return zh_text
    
    async def transcribe_dual(self, audio_path: str) -> List[ASRSegment]:
        """
        Main method: Parallel transcription with LLM fusion
        """
        logger.info(f"Starting dual ASR for: {audio_path}")
        
        # Step 1: Parallel transcription
        mandarin_segs, taiwanese_segs = await self.transcribe_parallel(audio_path)
        logger.info(f"Mandarin segments: {len(mandarin_segs)}, Taiwanese: {len(taiwanese_segs)}")
        
        # Step 2: Align segments
        aligned = self.align_segments(mandarin_segs, taiwanese_segs)
        
        # Step 3: LLM fusion for each pair
        final_segments = []
        context = []
        
        for zh_seg, nan_seg in aligned:
            zh_text = zh_seg.text if zh_seg else ""
            nan_text = nan_seg.text if nan_seg else ""
            
            # Select best transcription
            best_text = await self.select_best_transcription(
                zh_text, 
                nan_text,
                context=context[-3:]  # Last 3 segments for context
            )
            
            # Create final segment
            final_seg = ASRSegment(
                start=zh_seg.start if zh_seg else (nan_seg.start if nan_seg else 0),
                end=zh_seg.end if zh_seg else (nan_seg.end if nan_seg else 0),
                text=best_text,
                speaker=zh_seg.speaker if zh_seg else None,
                language="mixed"
            )
            
            final_segments.append(final_seg)
            context.append(best_text)
        
        logger.info(f"Dual ASR complete: {len(final_segments)} segments")
        return final_segments


# ============================================
# Singleton instance
# ============================================

_dual_asr_engine = None

def get_dual_asr_engine() -> DualASREngine:
    """Get or create DualASREngine singleton"""
    global _dual_asr_engine
    if _dual_asr_engine is None:
        _dual_asr_engine = DualASREngine()
    return _dual_asr_engine

