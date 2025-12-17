import argparse
import whisperx
import torch
import os
import sys
import logging

# Suppress logging from whisperx and pyannote
logging.getLogger("whisperx").setLevel(logging.CRITICAL)
logging.getLogger("pyannote.audio").setLevel(logging.CRITICAL)
logging.getLogger("pyannote.core").setLevel(logging.CRITICAL)
logging.getLogger("httpx").setLevel(logging.CRITICAL)

# Story 2: Transcription Service Development
# This script receives an audio file path, transcribes it using WhisperX, and prints the transcript to stdout.

def transcribe_audio(file_path):
    """
    Transcribes the audio file at the given path.
    """
    if not os.path.exists(file_path):
        print(f"Error: File not found at {file_path}", file=sys.stderr)
        return

    try:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        compute_type = "float16" if torch.cuda.is_available() else "int8"
        
        # 1. Load model
        model = whisperx.load_model("base", device, compute_type=compute_type)

        # 2. Transcribe
        audio = whisperx.load_audio(file_path)
        result = model.transcribe(audio, batch_size=16)

        # 3. Print result
        transcript_text = " ".join([segment['text'].strip() for segment in result["segments"]])
        print(transcript_text)

    except Exception as e:
        print(f"An error occurred during transcription: {e}", file=sys.stderr)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Transcribe an audio file using WhisperX.')
    parser.add_argument('--audio-file', type=str, required=True, help='The absolute path to the audio file.')
    
    args = parser.parse_args()
    
    transcribe_audio(args.audio_file)
