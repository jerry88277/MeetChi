import os
import sys
import logging
import torch
from faster_whisper import WhisperModel # Import faster_whisper
import numpy as np
import ffmpeg # For audio processing utilities if needed for file input

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global model variable to cache the loaded model
MODEL = None
# MODEL_NAME = "large-v3" # Upgrade to large-v3 for better accuracy
MODEL_NAME = "SoybeanMilk/faster-whisper-Breeze-ASR-25" # Switch to Breeze-ASR-25 (CTranslate2)
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

def load_asr_model():
    """
    Loads the ASR model using faster-whisper.
    """
    global MODEL
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

def get_transcription(audio_input, language="zh", initial_prompt=None):
    """
    Transcribes the given audio input using faster-whisper.
    
    Args:
        audio_input: Path to an audio file (str) or numpy array (audio chunk).
        language: Language code (e.g., 'zh', 'en'). Defaults to 'zh'.
        initial_prompt: Text context from previous segments to guide the model.
    
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

[中英夾雜處理]
- 若講者使用英文術語，請保留英文原文，不要強行音譯（例如保留 "APP"，不要寫成 "欸屁屁"）。
- 英文與中文之間請自動加入半形空格（例如：使用 AI 技術）。

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
            language=language, 
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
            # Reduced threshold to 0.5 for more aggressive filtering of non-speech segments.
            if segment.no_speech_prob < 0.5: 
                valid_texts.append(segment.text.strip())
            else:
                logger.debug(f"Skipped high no_speech_prob segment ({segment.no_speech_prob:.2f}): {segment.text}")

        transcript_text = " ".join(valid_texts)
        
        # --- Hallucination Filter ---
        # Expanded list for more aggressive filtering of common Whisper hallucinations
        HALLUCINATIONS = [
            "謝謝你", "謝謝", "谢谢", "谢谢你", 
            "Thank you", "Thanks", "You're welcome",
            "字幕", "字幕提供", "字幕来源", "提供字幕", "本字幕", "自動產生",
            "MBC", "TVBS", "Go", "go", "Yeah", "Right", "Okay",
            "Amara", "amara", "Subtitles", "subtitles",
            "Copyright", "copyright", "©", 
            "MING PAO", "Ming Pao", "YouTube", "youtube", "Facebook", "facebook",
            "多謝您的觀看", "感謝您的觀看", "請不吝點贊訂閱", "歡迎訂閱",
            "大家好", "大家好", "Hello", "hello",
            "嗯", "啊", "哦", "喔", "哎", "呀", # Common interjections that are often noise
        ]
        
        cleaned_text = transcript_text.strip()
        
        # 1. Substring match filter (More aggressive)
        # Check if ANY part of the cleaned text contains a hallucination pattern
        if any(h.lower() in cleaned_text.lower() for h in HALLUCINATIONS):
            logger.warning(f"Filtered hallucination: {cleaned_text}")
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
        # Load audio using ffmpeg for faster-whisper (similar to how whisperx does)
        probe = ffmpeg.probe(audio_file)
        audio_stream = next((stream for stream in probe['streams'] if stream['codec_type'] == 'audio'), None)
        in_sr = int(audio_stream['sample_rate'])
        
        out, _ = (
            ffmpeg.input(audio_file)
            .output("-", format="s16le", acodec="pcm_s16le", ac=1, ar=16000)
            .run(cmd=["ffmpeg", "-nostdin"], capture_stdout=True, capture_stderr=True)
        )
        audio_np = np.frombuffer(out, np.int16).flatten().astype(np.float32) / 32768.0

        transcript = get_transcription(audio_np) # Pass numpy array
        print("\n--- Transcription Result ---")
        print(transcript)
        print("----------------------------")
    except Exception as e:
        logger.error(f"Error processing file {audio_file}: {e}")