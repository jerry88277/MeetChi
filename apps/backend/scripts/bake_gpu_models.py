import os
from faster_whisper import WhisperModel
import whisperx

def main():
    model_name = "SoybeanMilk/faster-whisper-Breeze-ASR-25"
    token = os.environ.get("HF_AUTH_TOKEN")
    
    print("=== Model Bake-in Started ===")
    
    print(f"1. Downloading Faster Whisper model: {model_name}")
    model = WhisperModel(model_name, device="cpu", compute_type="float32")
    print("Faster Whisper model cached successfully.\n")
    
    try:
        print("2. Downloading WhisperX alignment model (lang=zh)...")
        align_model, metadata = whisperx.load_align_model(language_code="zh", device="cpu")
        print("WhisperX alignment model cached successfully.\n")
    except Exception as e:
        print(f"WARNING: Skipping WhisperX alignment model caching due to: {e}\n")
    
    try:
        print("3. Downloading Pyannote Diarization (speaker-diarization-3.1)...")
        if token:
            from whisperx.diarize import DiarizationPipeline
            diar_model = DiarizationPipeline(use_auth_token=token, device="cpu")
            print("Pyannote Diarization cached successfully.\n")
        else:
            print("WARNING: No HF_AUTH_TOKEN found, skipping Diarization model download! Baking is incomplete!")
    except Exception as e:
        print(f"WARNING: Skipping Pyannote Diarization model caching due to: {e}\n")
        
    print("=== Model Bake-in Completed ===")

if __name__ == "__main__":
    main()
