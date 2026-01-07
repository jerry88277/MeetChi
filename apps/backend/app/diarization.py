import os
import torch
import logging
import pyannote.audio.core.task # <-- Import this
from pyannote.audio import Pipeline
from typing import List, Dict, Any
import torchaudio 
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# --- Configuration ---
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

# --- PyTorch Security Fix for 2.6+ ---
try:
    # Allow specific globals required by pyannote/speechbrain models
    # This fixes "WeightsUnpickler error: Unsupported global"
    torch.serialization.add_safe_globals([
        torch.torch_version.TorchVersion,
        pyannote.audio.core.task.Specifications
    ])
    logger.info("Added safe globals for PyTorch serialization.")
except AttributeError:
    # Older torch versions don't have this function, and likely default to weights_only=False anyway
    pass
except Exception as e:
    logger.warning(f"Failed to add safe globals: {e}")
HF_AUTH_TOKEN = os.getenv("HF_AUTH_TOKEN")
if not HF_AUTH_TOKEN:
    logger.error(f"Hugging Face Access Token (HF_AUTH_TOKEN) not found in environment variables. Current env vars: {list(os.environ.keys())}")
    logger.error("Speaker Diarization will not work without it. Please set HF_AUTH_TOKEN in .env")

# Diarization Pipeline (lazy loading)
diarization_pipeline = None

def load_diarization_pipeline():
    global diarization_pipeline
    if diarization_pipeline is None:
        logger.info("Loading pyannote.audio speaker diarization pipeline...")
        if not HF_AUTH_TOKEN:
            logger.error("HF_AUTH_TOKEN is missing. Cannot load pyannote pipeline.")
            return None
        try:
            # Use pyannote/speaker-diarization-3.1
            # ensure your HF_AUTH_TOKEN has access to this model and you accepted the user conditions
            diarization_pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-3.1",
                use_auth_token=HF_AUTH_TOKEN
            )
            # Move pipeline to GPU if available
            if torch.cuda.is_available():
                diarization_pipeline = diarization_pipeline.to(torch.device("cuda"))
                logger.info("pyannote.audio pipeline loaded on GPU.")
            else:
                logger.info("pyannote.audio pipeline loaded on CPU.")
            return diarization_pipeline
        except Exception as e:
            logger.error(f"Failed to load pyannote.audio pipeline: {e}")
            logger.error("Please ensure your HF_AUTH_TOKEN is correct and you have accepted the user conditions on Hugging Face Hub.")
            return None
    return diarization_pipeline

def perform_diarization(audio_file_path: str) -> List[Dict[str, Any]]:
    """
    Performs speaker diarization on an audio file.

    Args:
        audio_file_path: Path to the input audio file (e.g., WAV, MP3).

    Returns:
        A list of dictionaries, each representing a speech segment with speaker label, start, and end time.
        Example: [{'speaker': 'SPEAKER_00', 'start': 0.0, 'end': 5.0}, ...]
    """
    pipeline = load_diarization_pipeline()
    if pipeline is None:
        logger.error("Diarization pipeline is not loaded. Skipping diarization.")
        return []

    logger.info(f"Performing diarization for audio: {audio_file_path}")
    try:
        # pyannote audio expects an audio file path, a pre-loaded waveform, or an URI
        # It handles resampling internally to 16kHz mono.
        diarization = pipeline(audio_file_path)
        
        diarized_segments = []
        for segment, track, speaker in diarization.itertracks(yield_label=True):
            diarized_segments.append({
                "speaker": speaker,
                "start": round(segment.start, 2),
                "end": round(segment.end, 2)
            })
        logger.info(f"Diarization complete. Found {len(set(s['speaker'] for s in diarized_segments))} speakers.")
        return diarized_segments
    except Exception as e:
        logger.error(f"Error during speaker diarization for {audio_file_path}: {e}")
        return []

# Example usage (for testing)
if __name__ == "__main__":
    # Ensure HF_AUTH_TOKEN is set in your environment or .env file
    # For testing, you might need a dummy audio file.
    # Example: create a dummy.wav or use an existing one.
    
    # Simple test with a dummy audio file (replace with your actual audio)
    # This requires 'pydub' for simple audio creation, which is not in requirements.txt
    # from pydub import AudioSegment
    # AudioSegment.silent(duration=5000).export("dummy.wav", format="wav")
    
    test_audio_path = "path/to/your/audio.wav" # <-- REPLACE THIS WITH A REAL AUDIO FILE PATH FOR TESTING
    if os.path.exists(test_audio_path):
        segments = perform_diarization(test_audio_path)
        for seg in segments:
            print(seg)
    else:
        print(f"Test audio file not found: {test_audio_path}. Cannot perform example diarization.")
        print("Please create an audio file and update 'test_audio_path' in diarization.py for testing.")
