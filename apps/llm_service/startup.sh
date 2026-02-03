#!/bin/bash
set -e

echo "=== MeetChi LLM Service Startup ==="

# Download models from GCS if path is specified
if [ -n "$GCS_MODELS_PATH" ]; then
    echo "Downloading models from $GCS_MODELS_PATH..."
    
    # Download WhisperX model
    if [ ! -d "/app/models/whisper-large-v3" ]; then
        echo "Downloading whisper-large-v3..."
        gsutil -m cp -r "$GCS_MODELS_PATH/whisper-large-v3" /app/models/ || echo "whisper-large-v3 not found in GCS"
    fi
    
    # Download Taiwanese ASR
    if [ ! -d "/app/models/taiwanese-asr" ]; then
        echo "Downloading taiwanese-asr..."
        gsutil -m cp -r "$GCS_MODELS_PATH/taiwanese-asr" /app/models/ || echo "taiwanese-asr not found in GCS"
    fi
    
    # Download Pyannote models
    if [ ! -d "/app/models/pyannote-diarization" ]; then
        echo "Downloading pyannote-diarization..."
        gsutil -m cp -r "$GCS_MODELS_PATH/pyannote-diarization" /app/models/ || echo "pyannote not found in GCS"
    fi
    
    echo "Models downloaded successfully!"
    ls -la /app/models/
else
    echo "GCS_MODELS_PATH not set, using HuggingFace Hub directly"
fi

echo "Starting Flask application..."
exec python app.py
