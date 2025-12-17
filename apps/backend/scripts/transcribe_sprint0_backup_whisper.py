import os
import sys
import logging
import torch
import whisperx
import numpy as np
import ffmpeg
import omegaconf.listconfig
import omegaconf.base
import omegaconf.nodes
import typing
import collections
import torch.torch_version
import pyannote.audio.core.model
import pyannote.audio.core.task

# Register safe globals for torch.load to fix PyTorch 2.6+ security restrictions
torch.serialization.add_safe_globals([
    omegaconf.listconfig.ListConfig, 
    omegaconf.base.ContainerMetadata, 
    typing.Any, 
    list, 
    collections.defaultdict, 
    dict, 
    int, 
    omegaconf.nodes.AnyNode, 
    omegaconf.base.Metadata, 
    torch.torch_version.TorchVersion, 
    pyannote.audio.core.model.Introspection, 
    pyannote.audio.core.task.Specifications, 
    pyannote.audio.core.task.Problem, 
    pyannote.audio.core.task.Resolution
])

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Global model variable to cache the loaded model
MODEL = None
MODEL_NAME = "adi-gov-tw/Taiwan-Tongues-ASR-CE" 
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if torch.cuda.is_available() else "int8"

def load_asr_model():
    """
    Loads the ASR model.
    """
    global MODEL
    if MODEL is None:
        logger.info(f"Loading model: {MODEL_NAME} on {DEVICE} with {COMPUTE_TYPE}")
        try:
            # whisperx.load_model can accept a HF repo ID if supported by underlying faster-whisper
            # If this fails, we might need to fallback to 'large-v2' or check model compatibility
            MODEL = whisperx.load_model(MODEL_NAME, DEVICE, compute_type=COMPUTE_TYPE)
            logger.info("Model loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise e
    return MODEL

def get_transcription(audio_input, language="zh", initial_prompt=None):
    """
    Transcribes the given audio input.
    
    Args:
        audio_input: Path to an audio file (str) or numpy array (audio chunk).
        language: Language code (e.g., 'zh', 'en'). Defaults to 'zh'.
        initial_prompt: Text context from previous segments to guide the model.
    
    Returns:
        str: The transcribed text.
    """
    model = load_asr_model()
    
    try:
        # If input is a file path, load it
        if isinstance(audio_input, str):
            if not os.path.exists(audio_input):
                logger.error(f"File not found: {audio_input}")
                return ""
            logger.info(f"Transcribing file: {audio_input}")
            audio = whisperx.load_audio(audio_input)
        elif isinstance(audio_input, np.ndarray):
             # Assuming input is already a float32 numpy array (16kHz mono)
            audio = audio_input
        else:
            logger.error("Invalid audio input format. Expected file path or numpy array.")
            return ""

        # Transcribe
        # batch_size can be adjusted. 
        # beam_size not supported by whisperx wrapper directly.
        options = {
            "batch_size": 16, 
            "language": language, 
            "task": "transcribe"
        }
        
        # WhisperX might accept **kwargs for some underlying args, or it might not.
        # If initial_prompt fails next, we will have to remove it too.
        if initial_prompt:
            options["initial_prompt"] = initial_prompt

        result = model.transcribe(audio, **options)
        
        # Extract text
        transcript_text = " ".join([segment['text'].strip() for segment in result["segments"]])
        
        # --- Hallucination Filter ---
        HALLUCINATIONS = [
            "謝謝你", "謝謝", "谢谢", "谢谢你", 
            "Thank you", "Thanks", 
            "字幕", "字幕提供", "字幕来源",
            "MBC", "TVBS", "Go", "go" # Added 'Go', 'go' as observed in previous logs
        ]
        
        cleaned_text = transcript_text.strip()
        
        # 1. Exact match filter
        if cleaned_text in HALLUCINATIONS:
            logger.warning(f"Filtered hallucination: {cleaned_text}")
            return ""
            
        return transcript_text

    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True) # Log full traceback
        return ""

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python transcribe_sprint0.py <audio_file_path>")
        sys.exit(1)
        
    audio_file = sys.argv[1]
    print(f"Testing transcription on: {audio_file}")
    
    transcript = get_transcription(audio_file)
    print("\n--- Transcription Result ---")
    print(transcript)
    print("----------------------------")