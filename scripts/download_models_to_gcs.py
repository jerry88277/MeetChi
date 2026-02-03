#!/usr/bin/env python3
"""
Download HuggingFace models to Google Cloud Storage.
Run this script ONCE before deploying Cloud Run services.

Usage:
    python scripts/download_models_to_gcs.py --bucket gs://PROJECT_ID-meetchi-audio

Models downloaded:
    - WhisperX large-v3 (Mandarin ASR)
    - gacky1601/whisper-small-taiwanese-asr-v2 (Taiwanese ASR)
    - MediaTek-Research/Breeze-7B-Instruct-v1_0 (LLM)
    - pyannote/speaker-diarization-3.1 (Speaker diarization)
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Models to download
MODELS = {
    # WhisperX large-v3 (via faster-whisper)
    "whisper-large-v3": {
        "type": "faster-whisper",
        "repo": "Systran/faster-whisper-large-v3",
        "gcs_path": "models/whisper-large-v3"
    },
    # Taiwanese ASR
    "taiwanese-asr": {
        "type": "transformers", 
        "repo": "gacky1601/whisper-small-taiwanese-asr-v2",
        "gcs_path": "models/taiwanese-asr"
    },
    # Breeze 7B LLM
    "breeze-7b": {
        "type": "transformers",
        "repo": "MediaTek-Research/Breeze-7B-Instruct-v1_0",
        "gcs_path": "models/breeze-7b"
    },
    # Pyannote diarization
    "pyannote-diarization": {
        "type": "pyannote",
        "repo": "pyannote/speaker-diarization-3.1",
        "gcs_path": "models/pyannote-diarization"
    },
    # Pyannote segmentation
    "pyannote-segmentation": {
        "type": "pyannote",
        "repo": "pyannote/segmentation-3.0",
        "gcs_path": "models/pyannote-segmentation"
    }
}

def download_transformers_model(repo: str, local_path: Path):
    """Download a HuggingFace transformers model."""
    from huggingface_hub import snapshot_download
    
    print(f"Downloading {repo} to {local_path}...")
    snapshot_download(
        repo_id=repo,
        local_dir=local_path,
        local_dir_use_symlinks=False
    )
    print(f"✓ Downloaded {repo}")

def download_faster_whisper_model(repo: str, local_path: Path):
    """Download a faster-whisper model."""
    from huggingface_hub import snapshot_download
    
    print(f"Downloading faster-whisper {repo} to {local_path}...")
    snapshot_download(
        repo_id=repo,
        local_dir=local_path,
        local_dir_use_symlinks=False,
        allow_patterns=["*.bin", "*.json", "*.txt", "*.model"]
    )
    print(f"✓ Downloaded {repo}")

def download_pyannote_model(repo: str, local_path: Path):
    """Download a pyannote model (requires HF_AUTH_TOKEN)."""
    from huggingface_hub import snapshot_download
    
    token = os.environ.get("HF_AUTH_TOKEN")
    if not token:
        print(f"⚠ Skipping {repo}: HF_AUTH_TOKEN required")
        return False
    
    print(f"Downloading {repo} to {local_path}...")
    snapshot_download(
        repo_id=repo,
        local_dir=local_path,
        local_dir_use_symlinks=False,
        token=token
    )
    print(f"✓ Downloaded {repo}")
    return True

def upload_to_gcs(local_path: Path, gcs_uri: str):
    """Upload local directory to GCS."""
    print(f"Uploading {local_path} to {gcs_uri}...")
    subprocess.run([
        "gsutil", "-m", "cp", "-r",
        str(local_path) + "/*",
        gcs_uri + "/"
    ], check=True)
    print(f"✓ Uploaded to {gcs_uri}")

def main():
    parser = argparse.ArgumentParser(description="Download HF models to GCS")
    parser.add_argument("--bucket", required=True, help="GCS bucket URI (gs://...)")
    parser.add_argument("--models", nargs="*", default=list(MODELS.keys()),
                        help="Specific models to download")
    parser.add_argument("--local-dir", default="./tmp_models",
                        help="Local temp directory for downloads")
    args = parser.parse_args()
    
    local_base = Path(args.local_dir)
    local_base.mkdir(exist_ok=True)
    
    for model_name in args.models:
        if model_name not in MODELS:
            print(f"Unknown model: {model_name}")
            continue
            
        config = MODELS[model_name]
        local_path = local_base / model_name
        gcs_uri = f"{args.bucket}/{config['gcs_path']}"
        
        # Download based on type
        if config["type"] == "transformers":
            download_transformers_model(config["repo"], local_path)
        elif config["type"] == "faster-whisper":
            download_faster_whisper_model(config["repo"], local_path)
        elif config["type"] == "pyannote":
            if not download_pyannote_model(config["repo"], local_path):
                continue
        
        # Upload to GCS
        upload_to_gcs(local_path, gcs_uri)
        
        # Cleanup local
        subprocess.run(["rm", "-rf", str(local_path)], check=True)
    
    print("\n✅ All models uploaded to GCS!")
    print(f"Bucket: {args.bucket}")
    print("\nModels available at:")
    for model_name in args.models:
        if model_name in MODELS:
            config = MODELS[model_name]
            print(f"  - {args.bucket}/{config['gcs_path']}")

if __name__ == "__main__":
    main()
