import logging
import traceback
import torch
from faster_whisper import WhisperModel
import os

# Configure logging to see download progress
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MODEL_NAME = "SoybeanMilk/faster-whisper-Breeze-ASR-25"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

print(f"--- ASR Model Debugger ---")
print(f"Target Model: {MODEL_NAME}")
print(f"Target Device: {DEVICE}")
print(f"--------------------------")

try:
    print(f"Starting to load/download model (this may take a few minutes)...")
    
    # Load the model
    # compute_type: float16 is recommended for NVIDIA GPUs, int8 for CPU
    model = WhisperModel(
        MODEL_NAME, 
        device=DEVICE, 
        compute_type="float16" if DEVICE == "cuda" else "int8"
    )
    
    print("\nSUCCESS: ASR model loaded successfully!")
    print(f"Model is ready for transcription on {DEVICE}.")

except Exception as e:
    print("\n!!! FAILED to load ASR model !!!")
    traceback.print_exc()
    
    # Check for common CTranslate2 / faster-whisper issues
    error_msg = str(e)
    if "CUDA" in error_msg and DEVICE == "cuda":
        print("\n[Suggestion] Possible CUDA incompatibility. Try ensuring cuDNN and cuBLAS are installed for CTranslate2.")
    elif "404" in error_msg:
        print("\n[Suggestion] Model name might be incorrect or Hugging Face is down.")
