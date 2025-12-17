# transcribe_breeze_hf.py
# This script uses the official Hugging Face AutomaticSpeechRecognitionPipeline for transcription.
# It retains the logging, file I/O, and configuration framework from exec_whisperx_task_v1.2.py.
# NOTE: This version does NOT support speaker diarization.

import ffmpeg
import torch
import json
import sys
import io
import os
import re
import logging
from datetime import datetime
from opencc import OpenCC
import librosa
from transformers import WhisperProcessor, WhisperForConditionalGeneration, AutomaticSpeechRecognitionPipeline

# Initialize Simplified to Traditional Chinese conversion
cc = OpenCC('s2twp')

# Force all stdout and stderr outputs to be encoded in UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# --------------------------- 
# Setup config and logging
# --------------------------- 
try:
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    
    as_dir_path = config["as_dir_path"]
    aslc_dir_path = config["aslc_dir_path"]
    tr_dir_path = config["tr_dir_path"]
    log_path = config["log_path"]
    
    os.makedirs(log_path, exist_ok=True)
    
    log_files = sorted(
        [f for f in os.listdir(log_path) if re.match(r"sparrow-\d{4}-\d{2}-\d{2}\.plog$", f)],
        reverse=True
    )
    
    if log_files:
        latest_log_file = os.path.join(log_path, log_files[0])
    else:
        latest_log_file = os.path.join(log_path, f"sparrow-{datetime.now().strftime('%Y-%m-%d')}.plog")
except Exception as e:
    print(f"Error reading config or setting up log directory: {e}")
    raise

script_name = os.path.basename(__file__)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
formatter = logging.Formatter(
    f"%(asctime)s - %(levelname)s - [{script_name}] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

file_handler = logging.FileHandler(latest_log_file, encoding="utf-8", mode="a")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

# --------------------------- 
# Receive command-line parameters
# --------------------------- 
try:
    as_filename = sys.argv[1]
    # Diarize toggle is kept for argument compatibility but is not used in this script.
    diarize_toggle = sys.argv[2]
except IndexError as e:
    logger.critical("Not enough command line arguments provided.", exc_info=True)
    raise

if diarize_toggle == "1":
    logger.warning("Speaker diarization is not supported in this script and will be ignored.")

sys.stdout.flush()
logger.info(f"Received arguments: {as_filename}")

# --------------------------- 
# Setup output file paths
# --------------------------- 
try:
    tr_txt_dir_path = os.path.join(tr_dir_path, "txt")
    tr_txt_filename = os.path.splitext(as_filename)[0] + '.txt'
    tr_txt_path = os.path.join(tr_txt_dir_path, tr_txt_filename)

    tr_srt_dir_path = os.path.join(tr_dir_path, "srt")
    tr_srt_filename = os.path.splitext(as_filename)[0] + '.srt'
    tr_srt_path = os.path.join(tr_srt_dir_path, tr_srt_filename)

    tr_vtt_dir_path = os.path.join(tr_dir_path, "vtt")
    tr_vtt_filename = os.path.splitext(as_filename)[0] + '.vtt'
    tr_vtt_path = os.path.join(tr_vtt_dir_path, tr_vtt_filename)

    tr_json_dir_path = os.path.join(tr_dir_path, "json")
    tr_json_filename = os.path.splitext(as_filename)[0] + '.json'
    tr_json_path = os.path.join(tr_json_dir_path, tr_json_filename)
    
    for path in [tr_txt_dir_path, tr_srt_dir_path, tr_vtt_dir_path, tr_json_dir_path]:
        os.makedirs(path, exist_ok=True)
except Exception as e:
    logger.critical(f"Error setting up output directories: {e}", exc_info=True)
    raise

# --------------------------- 
# Main parameters setup
# --------------------------- 
try:
    AUDIO_FILE = os.path.join(as_dir_path, as_filename)
    AUDIOLC_FILE = os.path.join(aslc_dir_path, as_filename)

    DEVICE = config["device"]
    MODEL_PATH = config["model_size"] # Using model_size to specify path to local model
    BATCH_SIZE = config.get("batch_size", 16)
    
    torch_dtype = torch.float16 if DEVICE == "cuda" else torch.float32
    
    logger.info(f"Transcription parameters: DEVICE:{DEVICE}, MODEL_PATH:{MODEL_PATH}")
except Exception as e:
    logger.critical(f"Error setting main parameters: {e}", exc_info=True)
    raise

# --------------------------- 
# Convert audio to mono (left channel)
# --------------------------- 
try:
    logger.info(f"Converting audio to mono: {AUDIO_FILE} -> {AUDIOLC_FILE}")
    (ffmpeg.input(AUDIO_FILE).output(AUDIOLC_FILE, ac=1, map="0:a:0").run(overwrite_output=True))
except Exception as e:
    logger.error(f"Error in audio conversion: {e}", exc_info=True)
    raise

# --------------------------- 
# Core Transcription using Transformers Pipeline
# --------------------------- 
try:
    logger.info(f"Loading model from path: {MODEL_PATH}")
    processor = WhisperProcessor.from_pretrained(MODEL_PATH)
    model = WhisperForConditionalGeneration.from_pretrained(MODEL_PATH, torch_dtype=torch_dtype).to(DEVICE).eval()

    logger.info("Building ASR Pipeline...")
    asr_pipeline = AutomaticSpeechRecognitionPipeline(
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        device=0 if DEVICE == "cuda" else -1,
        torch_dtype=torch_dtype
    )

    logger.info(f"Loading audio from the source file: {AUDIOLC_FILE}")
    audio_input, sample_rate = librosa.load(AUDIOLC_FILE, sr=16000)

    logger.info(f"Transcribing audio with ASR Pipeline...")
    transcription_result = asr_pipeline(audio_input, chunk_length_s=30, batch_size=BATCH_SIZE, return_timestamps=True)
    
    # Convert all text to Traditional Chinese
    transcription_result['text'] = cc.convert(transcription_result['text'])
    for chunk in transcription_result['chunks']:
        chunk['text'] = cc.convert(chunk['text'])

except Exception as e:
    logger.error(f"Error during transcription pipeline: {e}", exc_info=True)
    raise

# --------------------------- 
# Save transcription results
# --------------------------- 

def format_time(seconds):
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    seconds = s % 60
    return f"{hours:02}:{minutes:02}:{seconds:02},{ms:03}"

# Save as TXT file
try:
    logger.info(f"Saving result as a TXT file: {tr_txt_path}")
    with open(tr_txt_path, 'w', encoding='utf-8') as txt_file:
        for chunk in transcription_result['chunks']:
            start, end = chunk['timestamp']
            txt_file.write(f"[{format_time(start)} --> {format_time(end)}] {chunk['text']}\n")
except Exception as e:
    logger.error(f"Error saving TXT file: {e}", exc_info=True)
    raise

# Save as SRT file
try:
    logger.info(f"Saving result as an SRT file: {tr_srt_path}")
    with open(tr_srt_path, "w", encoding="utf-8") as srt_file:
        for idx, chunk in enumerate(transcription_result['chunks'], start=1):
            start, end = chunk['timestamp']
            start_time = format_time(start)
            end_time = format_time(end)
            text = chunk['text']
            srt_file.write(f"{idx}\n")
            srt_file.write(f"{start_time} --> {end_time}\n")
            srt_file.write(f"{text}\n\n")
except Exception as e:
    logger.error(f"Error saving SRT file: {e}", exc_info=True)
    raise

# Save as VTT file
def format_time_vtt(seconds):
    ms = int((seconds - int(seconds)) * 1000)
    s = int(seconds)
    hours = s // 3600
    minutes = (s % 3600) // 60
    seconds = s % 60
    return f"{hours:02}:{minutes:02}:{seconds:02}.{ms:03}"

try:
    logger.info(f"Saving result as a VTT file: {tr_vtt_path}")
    with open(tr_vtt_path, "w", encoding="utf-8") as vtt_file:
        vtt_file.write("WEBVTT\n\n")
        for chunk in transcription_result['chunks']:
            start, end = chunk['timestamp']
            start_time = format_time_vtt(start)
            end_time = format_time_vtt(end)
            text = chunk['text']
            vtt_file.write(f"{start_time} --> {end_time}\n")
            vtt_file.write(f"{text}\n\n")
except Exception as e:
    logger.error(f"Error saving VTT file: {e}", exc_info=True)
    raise

# Save as JSON file
try:
    logger.info(f"Saving result as a JSON file: {tr_json_path}")
    with open(tr_json_path, "w", encoding="utf-8") as json_file:
        json.dump(transcription_result, json_file, ensure_ascii=False, indent=4)
except Exception as e:
    logger.error(f"Error saving JSON file: {e}", exc_info=True)
    raise

logger.info("Process completed successfully")

# Print the content of the generated TXT file to stdout
try:
    with open(tr_txt_path, 'r', encoding='utf-8') as txt_file:
        print(txt_file.read())
except Exception as e:
    logger.error(f"Error reading generated TXT file for stdout: {e}", exc_info=True)

logging.shutdown()
sys.exit(0)
