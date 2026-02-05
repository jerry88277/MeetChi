import os
import sys
import logging
import string  # For string manipulation in Hallucination Filter
import json

# Lazy imports - GPU dependencies loaded only when needed
# This allows Cloud Run CPU environment to import this module without crashing
torch = None
WhisperModel = None
np = None
ffmpeg = None

def _ensure_gpu_deps():
    """Lazily load GPU dependencies (torch, faster_whisper, numpy, ffmpeg)."""
    global torch, WhisperModel, np, ffmpeg
    if torch is None:
        import torch as _torch
        torch = _torch
    if WhisperModel is None:
        from faster_whisper import WhisperModel as _WhisperModel
        WhisperModel = _WhisperModel
    if np is None:
        import numpy as _np
        np = _np
    if ffmpeg is None:
        import ffmpeg as _ffmpeg
        ffmpeg = _ffmpeg

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global model variable to cache the loaded model
MODEL = None
MODEL_NAME = "SoybeanMilk/faster-whisper-Breeze-ASR-25"  # Switch to Breeze-ASR-25 (CTranslate2)
DEVICE = None  # Set lazily when GPU deps are loaded


def load_asr_model():
    """
    Loads the ASR model using faster-whisper.
    """
    global MODEL, DEVICE
    _ensure_gpu_deps()  # Load GPU dependencies
    
    if DEVICE is None:
        DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
    
    if MODEL is None:
        logger.info(f"Loading faster-whisper model: {MODEL_NAME} on {DEVICE}...")
        try:
            # Load the model. It will automatically download if not present.
            # compute_type can be specified. "float16" for GPU, "int8" for CPU is common.
            MODEL = WhisperModel(MODEL_NAME, device=DEVICE, compute_type="float16" if DEVICE == "cuda" else "int8")
            logger.info("Faster-whisper model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load faster-whisper model: {e}")
            raise e
    return MODEL


def correct_keywords(text):
    """
    Performs specific keyword corrections.
    Loads from apps/backend/config/corrections.json if available.
    """
    corrections = {}
    config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "corrections.json")
    
    try:
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                corrections = json.load(f)
        else:
            # Fallback defaults if file missing
            corrections = {
                "剩副總": "盛副總",
                "勝負總": "盛副總",
                "黃學禮": "黃協理",
                "陳廉政": "陳連振",
                "陳連震": "陳連振",
                "徐全誠": "徐全成",
                "郭明珠": "郭銘洲",
                "趙令羽": "趙令瑜",
                "陳蓮妮": "陳連振",
                "公務": "工務",
                "齊美": "奇美",
                "旗美": "奇美",
                "刑美": "奇美",
                "邢美": "奇美",
                "體美": "奇美",
                "其美": "奇美",
                "A Step Up": "Step Up",
                "a step up": "Step Up",
                "step up": "Step Up",
            }
    except Exception as e:
        logger.error(f"Error reading corrections config: {e}")
        # Use minimal fallback to avoid crash
        corrections = {"齊美": "奇美"}

    for wrong, correct in corrections.items():
        # Use regex to replace only whole words or specific phrases if needed
        # For simplicity, using simple replace for now.
        text = text.replace(wrong, correct)
    return text


def get_transcription(audio_input, language="zh", initial_prompt=None, skip_hallucination_filter=False):
    """
    Transcribes the given audio input using faster-whisper.
    
    Args:
        audio_input: Path to an audio file (str) or numpy array (audio chunk).
        language: Language code (e.g., 'zh', 'en'). Defaults to 'zh'.
        initial_prompt: Text context from previous segments to guide the model.
        skip_hallucination_filter: If True, skip hallucination filtering (for alignment mode).
    
    Returns:
        str: The transcribed text.
    """
    model = load_asr_model()
    
    try:
        # Our websocket code only sends numpy arrays, so this branch is most used.
        if not isinstance(audio_input, np.ndarray):
             logger.error("Invalid audio input format for streaming. Expected numpy array.")
             return ""
        
        audio = audio_input # audio_input is already a float32 numpy array (16kHz mono)

        # Transcribe with faster-whisper
        # Use beam_size=5 for better accuracy, temperature=0 for determinism.
        
        # Optimize prompt for Traditional Chinese
        transcribe_prompt = initial_prompt
        if language == "zh":
            # Universal System Prompt (Hardcoded for quality, formatting, and disambiguation)
            # This forms the base context for ASR
            system_prompt_base = """
你是一個專業的 AI 即時聽寫專家。你的任務是將語音精準轉錄為流暢、易讀的【繁體中文】。

[核心原則]
1. 準確性優先：優先保留專有名詞、數字與關鍵術語的正確性。
2. 語意順暢：在不改變原意的前提下，自動修飾口語中的贅字（如「那個」、「呃」）與結巴。
3. 繁體中文：所有輸出必須使用台灣正體中文（Traditional Chinese, Taiwan）。絕對禁止出現簡體字。
4. 標點符號：請根據語氣與停頓，自動加入正確的全形標點符號（，。？！）。

[上下文參考]
以下是使用者提供的本次對話背景知識（專有名詞、主題、關鍵字），請利用這些資訊來消除歧義並修正同音異字：
"""
            
            # Combine system_prompt_base, custom_initial_prompt (from frontend), and previous_context
            # Order: System Prompt Base -> Custom Prompt (User-defined Knowledge) -> Previous ASR Context
            final_asr_prompt = system_prompt_base.strip()

            if initial_prompt: # initial_prompt here is from frontend's custom_initial_prompt + previous_context
                final_asr_prompt += f"\n{initial_prompt.strip()}"
            
            t_prompt = final_asr_prompt # Now t_prompt contains all context

            # The initial_prompt parameter in model.transcribe already handles the combination,
            # so we just need to pass the combined context here.
            # No need to further prepend "以下是繁體中文的內容。", as it's included in system_prompt_base
            # If there's already a previous context, it's combined in main.py before passing here.
            transcribe_prompt = t_prompt

        segments, info = model.transcribe(
            audio, 
            language=language,  # Keep language parameter for better accuracy
            initial_prompt=transcribe_prompt,
            beam_size=5, # Increased to 10 for better accuracy (trade-off with speed)
            temperature=0, # Enforce deterministic output
            # Other parameters like no_speech_threshold can be tuned.
            vad_filter=False, # Disabled faster-whisper's internal VAD filter
            # vad_parameters={"min_speech_duration_ms": 100, "max_speech_duration_s": 30, "min_silence_duration_ms": 500}
        )
        
        # Extract text with no_speech_prob filtering
        valid_texts = []
        for segment in segments:
            # Filter out segments that Whisper thinks are "no speech" (silence/noise)
            # Increased threshold to 0.85 to be more lenient and allow more partial/noisy speech to pass through.
            if segment.no_speech_prob < 0.85: 
                valid_texts.append(segment.text.strip())
            else:
                logger.debug(f"Skipped high no_speech_prob segment ({segment.no_speech_prob:.2f}): {segment.text}")

        transcript_text = " ".join(valid_texts)
        
        # --- Apply Keyword Corrections ---
        transcript_text = correct_keywords(transcript_text) # <--- ADDED HERE
        # --- End Keyword Corrections ---
        
        # --- Hallucination Filter (Relaxed) ---
        # Skip in alignment mode - the script already provides context
        if not skip_hallucination_filter:
            HALLUCINATIONS_SUBSTRING = [
                "字幕", "字幕提供", "字幕来源", "提供字幕", "本字幕", "自動產生",
                "MBC", "TVBS", "Amara", "subtitles", "Copyright", "©", 
                "MING PAO", "Ming Pao", "請不吝點贊訂閱", "歡迎訂閱",
                "多謝您的觀看", "感謝您的觀看"
            ]
            
            # Exact match blacklist (Filter ONLY if the text equals these, ignoring punctuation)
            # This prevents deleting sentences like "謝謝大家的參與"
            HALLUCINATIONS_EXACT = [
                "謝謝你", "謝謝", "谢谢", "谢谢你", 
                "Thank you", "Thanks", "You're welcome",
                "Go", "go", "Yeah", "Right", "Okay",
                "大家好", "Hello", "hello",
                "嗯", "啊", "哦", "喔", "哎", "呀"
            ]
            
            cleaned_text = transcript_text.strip()
            
            # 1. Substring match (Spam/Copyright)
            if any(h.lower() in cleaned_text.lower() for h in HALLUCINATIONS_SUBSTRING):
                logger.warning(f"Filtered hallucination (substring): {cleaned_text}")
                return ""

            # 2. Exact match (Interjections)
            # Remove punctuation for check
            import string
            text_no_punct = cleaned_text.translate(str.maketrans('', '', string.punctuation + "，。？！、"))
            
            if text_no_punct.strip() in HALLUCINATIONS_EXACT:
                 logger.warning(f"Filtered hallucination (exact): {cleaned_text}")
                 return ""
            
        return transcript_text

    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        return ""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe_sprint0.py <audio_file_path>")
        sys.exit(1)
        
    audio_file = sys.argv[1]
    print(f"Testing transcription on: {audio_file}")
    
    # Example for file input
    # Needs ffmpeg to load audio file correctly
    # You might want to create a separate helper for file-based transcription outside streaming
    
    try:
        # Use faster-whisper's built-in file transcription
        # It handles audio loading internally
        model = load_asr_model()
        
        # Optimize prompt for Traditional Chinese
        system_prompt_base = """
你是一個專業的 AI 即時聽寫專家。你的任務是將語音精準轉錄為流暢、易讀的【繁體中文】。

[核心原則]
1. 準確性優先：優先保留專有名詞、數字與關鍵術語的正確性。
2. 語意順暢：在不改變原意的前提下，自動修飾口語中的贅字。
3. 繁體中文：所有輸出必須使用台灣正體中文（Traditional Chinese, Taiwan）。
4. 標點符號：請根據語氣與停頓，自動加入正確的全形標點符號（，。？！）。
"""
        
        segments, info = model.transcribe(
            audio_file,  # Directly pass file path
            language="zh",
            initial_prompt=system_prompt_base.strip(),
            beam_size=5,
            temperature=0,
            vad_filter=True,
        )
        
        # Extract text
        transcript_parts = []
        for segment in segments:
            if segment.no_speech_prob < 0.85:
                transcript_parts.append(segment.text.strip())
        
        transcript = "".join(transcript_parts)
        transcript = correct_keywords(transcript)
        
        print("\n--- Transcription Result ---")
        print(transcript)
        print("----------------------------")
    except Exception as e:
        logger.error(f"Error processing file {audio_file}: {e}")
