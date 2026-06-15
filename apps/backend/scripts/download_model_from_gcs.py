"""Download pyannote model from GCS at Docker build time."""
from google.cloud import storage
import os

BUCKET = "prj-ai-meetchi-du-meetchi-audio"
PREFIX = "models/pyannote/speaker-diarization-community-1/"
LOCAL_DIR = "/app/models/pyannote/speaker-diarization-community-1"

client = storage.Client()
bucket = client.bucket(BUCKET)
blobs = list(bucket.list_blobs(prefix=PREFIX))
print(f"Downloading {len(blobs)} files from gs://{BUCKET}/{PREFIX}")

for blob in blobs:
    rel = blob.name[len(PREFIX):]
    if not rel:
        continue
    local_path = os.path.join(LOCAL_DIR, rel)
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    blob.download_to_filename(local_path)
    print(f"  OK {rel} ({blob.size} bytes)")

print("Done - model baked into image")
