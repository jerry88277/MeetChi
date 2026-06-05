"""
test_upload.py — MeetChi E2E Upload + Transcription Test

Usage:
    python scripts/e2e/test_upload.py <audio_file_path>
    python scripts/e2e/test_upload.py                    # uses default test file

Authentication (Cloud Run IAM bypass for developers):
    # Auto-fetches gcloud identity token if MEETCHI_ID_TOKEN not set:
    MEETCHI_ID_TOKEN=$(gcloud auth print-identity-token \
        --audiences=$MEETCHI_BACKEND_URL) \
    python scripts/e2e/test_upload.py

    # Or let the script auto-fetch (requires gcloud CLI installed + logged in):
    python scripts/e2e/test_upload.py

    # Or use the wrapper which handles token fetch automatically:
    bash scripts/e2e/run_e2e.sh [audio_file]

Steps:
    1. Create meeting
    2. Get Signed URL
    3. Upload to GCS
    4. Trigger transcription (SYNCHRONOUS — blocks until done)
    5. Verify results (status, segments, summary)
"""
import os
import sys
import time
import json
import argparse
import subprocess
import requests

# 705495828555 is the GCP project number for prj-ai-meetchi-du
BASE_URL = os.getenv("MEETCHI_BACKEND_URL", "https://meetchi-backend-705495828555.asia-southeast1.run.app")
DEFAULT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                            "GCP_app_test_audio", "馬爾地夫屎蛋介紹.m4a")


def _get_identity_token(audience: str) -> str | None:
    """Fetch gcloud identity token for Cloud Run IAM auth."""
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-identity-token", f"--audiences={audience}"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return result.stdout.strip()
        print(f"   ⚠️  gcloud token fetch failed: {result.stderr.strip()}")
    except FileNotFoundError:
        print("   ⚠️  gcloud not found. Set MEETCHI_ID_TOKEN env var manually.")
    except subprocess.TimeoutExpired:
        print("   ⚠️  gcloud token fetch timed out.")
    return None


def _auth_headers(token: str | None) -> dict:
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def main():
    parser = argparse.ArgumentParser(description="MeetChi E2E Upload Test")
    parser.add_argument("file", nargs="?", default=DEFAULT_FILE, help="Audio file path (default: GCP_app_test_audio/馬爾地夫屎蛋介紹.m4a)")
    parser.add_argument("--title", default="E2E Test", help="Meeting title")
    parser.add_argument("--language", default="zh", help="Language code")
    parser.add_argument("--template", default="general", help="Template type")
    parser.add_argument("--timeout", type=int, default=3600, help="Transcription timeout in seconds")
    parser.add_argument("--token", default=None, help="Identity token for Cloud Run IAM auth (auto-fetched from gcloud if omitted)")
    args = parser.parse_args()

    file_path = args.file
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        sys.exit(1)

    content_type = "audio/mp4" if file_path.endswith(".m4a") else "audio/wav"

    # ── Auth token ──────────────────────────────────────────────────────────
    token = args.token or os.getenv("MEETCHI_ID_TOKEN")
    if not token:
        print("🔑 Fetching gcloud identity token...")
        token = _get_identity_token(BASE_URL)
        if token:
            print(f"   ✅ Token obtained ({token[:20]}...)")
        else:
            print("   ℹ️  Proceeding without token (requires AUTH_REQUIRED=false on backend)")

    headers = _auth_headers(token)

    # ── Step 1: Create meeting ───────────────────────────────────────────
    print("1. Creating meeting...")
    res = requests.post(f"{BASE_URL}/api/v1/meetings", json={
        "title": f"{args.title} - {os.path.basename(file_path)}",
        "language": args.language,
        "template_name": args.template
    }, headers=headers, timeout=30)
    res.raise_for_status()
    meeting_id = res.json()["id"]
    print(f"   Meeting ID: {meeting_id}")

    # ── Step 2: Get Signed URL ───────────────────────────────────────────
    print("\n2. Getting GCS Signed URL...")
    res = requests.post(f"{BASE_URL}/api/v1/meetings/{meeting_id}/upload-url", json={
        "filename": os.path.basename(file_path),
        "contentType": content_type,
    }, headers=headers, timeout=30)
    res.raise_for_status()
    res_data = res.json()
    upload_url = res_data.get("uploadUrl") or res_data.get("upload_url") or res_data.get("url")
    print(f"   Signed URL obtained ({len(upload_url)} chars)")

    # ── Step 3: Upload to GCS ────────────────────────────────────────────
    file_size = os.path.getsize(file_path)
    print(f"\n3. Uploading {os.path.basename(file_path)} ({file_size/1024/1024:.1f} MB)...")
    with open(file_path, "rb") as f:
        upload_res = requests.put(
            upload_url,
            data=f,
            headers={"Content-Type": content_type},
            timeout=300,
        )

    if upload_res.status_code not in (200, 201):
        print(f"   ❌ Upload failed: HTTP {upload_res.status_code}")
        print(f"   {upload_res.text[:500]}")
        sys.exit(1)
    print(f"   ✅ GCS upload OK (HTTP {upload_res.status_code})")

    # ── Step 4: Trigger Transcription ────────────────────────────────────
    print(f"\n4. Triggering transcription (synchronous, timeout={args.timeout}s)...")
    start = time.time()
    try:
        res = requests.post(f"{BASE_URL}/api/v1/tasks/transcription", json={
            "meeting_id": meeting_id
        }, headers=headers, timeout=args.timeout)
        elapsed = time.time() - start
        print(f"   HTTP {res.status_code} after {elapsed:.1f}s")
        print(f"   Response: {res.text[:300]}")
    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        print(f"   ❌ TIMEOUT after {elapsed:.1f}s")
        sys.exit(1)
    except Exception as e:
        elapsed = time.time() - start
        print(f"   ❌ ERROR after {elapsed:.1f}s: {e}")
        sys.exit(1)

    # ── Step 5: Verify results ───────────────────────────────────────────
    print(f"\n5. Verifying meeting results...")
    res = requests.get(f"{BASE_URL}/api/v1/meetings/{meeting_id}", headers=headers, timeout=30)
    if res.status_code == 200:
        data = res.json()
        status = data.get("status")
        segments = data.get("transcript_segments", [])
        summary = data.get("summary_json")
        transcript_len = len(data.get("transcript_raw", "") or "")

        print(f"   Status: {status}")
        print(f"   Segments: {len(segments)}")
        print(f"   Transcript: {transcript_len} chars")
        print(f"   Summary: {'Yes' if summary else 'No'}")

        if summary:
            try:
                sj = json.loads(summary)
                preview = sj.get("summary", str(sj))[:200]
                print(f"   Preview: {preview}")
            except Exception:
                print(f"   Preview: {summary[:200]}")

        if status == "COMPLETED" and len(segments) > 0 and summary:
            print(f"\n{'='*60}")
            print(f"✅ E2E PASSED — Pipeline complete in {elapsed:.1f}s")
            print(f"   Meeting: {meeting_id}")
            print(f"{'='*60}")
        elif status == "COMPLETED" and len(segments) > 0:
            print(f"\n⚠️  PARTIAL — Transcript OK, summary missing")
        elif status == "FAILED":
            print(f"\n❌ FAILED — Check GPU ASR / Backend logs")
        else:
            print(f"\n⏳ STILL PROCESSING — Status: {status}")
    else:
        print(f"   ❌ Get meeting failed: HTTP {res.status_code}")


if __name__ == "__main__":
    main()

