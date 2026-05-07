"""
ASR helpers — Gemini multimodal ASR + optional local-ASR fallback shims.

Why a separate module?
  - main.py is being slimmed down; this code has clear single responsibility
    (ASR transcription helpers) and is shared between WebSocket route and
    main.py's startup hook (load_asr_model).
  - The conditional import of `scripts.transcribe_sprint0` is GPU-dependent
    and must fail gracefully on CPU-only Cloud Run instances.
"""

import io
import logging
import asyncio

logger = logging.getLogger(__name__)


# ============================================
# Local ASR (optional, GPU-dependent)
# ============================================
try:
    from scripts.transcribe_sprint0 import (
        get_transcription,
        load_asr_model,
        correct_keywords,
        logger as asr_logger,
    )
    LOCAL_ASR_AVAILABLE = True
except ImportError as e:
    asr_logger = logging.getLogger("asr_fallback")
    asr_logger.info(f"Local ASR not available: {e}. Using Gemini API for ASR.")
    LOCAL_ASR_AVAILABLE = False

    def get_transcription(*args, **kwargs):
        raise NotImplementedError("Local ASR not available. Use Gemini API.")

    def load_asr_model(*args, **kwargs):
        pass

    def correct_keywords(text):
        return text


# ============================================
# Gemini ASR (cloud, default)
# ============================================
async def get_transcription_gemini(audio_np, lang: str = "zh", prompt: str = "") -> str:
    """
    Transcribe audio using Gemini API (multimodal input).

    Args:
        audio_np: numpy float32 array of audio samples at 16kHz
        lang: source language code ('zh', 'en', etc.)
        prompt: context/initial prompt for better accuracy

    Returns:
        Transcribed text string (empty if no speech detected)
    """
    from app.llm_utils import get_gemini_client, GEMINI_MODEL

    client = get_gemini_client()
    if client is None:
        raise RuntimeError("Gemini client not initialized. Set GCP_PROJECT or GEMINI_API_KEY.")

    import soundfile as sf

    # Convert numpy array to WAV bytes in memory
    wav_buffer = io.BytesIO()
    sf.write(wav_buffer, audio_np, 16000, format='WAV')
    wav_bytes = wav_buffer.getvalue()

    lang_map = {"zh": "繁體中文", "en": "English", "ja": "日本語"}
    lang_name = lang_map.get(lang, lang)

    system_prompt = (
        f"你是語音轉文字引擎。請將音頻精確轉寫為{lang_name}文字。"
        "只輸出轉寫文字，不要添加任何額外說明、標點符號修飾或格式化。"
        "如果音頻中沒有語音或只有噪音，回傳空字串。"
    )

    user_content = []
    if prompt:
        user_content.append(f"上下文提示：{prompt}")
    user_content.append("請轉寫以下音頻：")

    from google.genai import types
    user_content.append(types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"))

    def _call_gemini_asr():
        return client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_content,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.1,
            )
        )

    # Run synchronous Gemini call in thread pool
    response = await asyncio.to_thread(_call_gemini_asr)

    result = response.text.strip() if response.text else ""
    return result
