"""
test_community1.py — E2E Test for Community-1 Diarization Path

Tests the community-1 revision directly:
  1. Create a new meeting in backend
  2. Verify GCS audio file exists (reuse existing meeting's audio)
  3. Call community-1 GPU ASR endpoint directly
  4. Verify segments have speaker labels

Usage:
  python scripts/e2e/test_community1.py
  python scripts/e2e/test_community1.py --reuse-meeting <meeting_id>
  python scripts/e2e/test_community1.py --audio-meeting <meeting_id_with_audio>
"""
import os, sys, time, json, requests, argparse

BASE_URL = os.getenv("MEETCHI_BACKEND_URL", "https://meetchi-backend-705495828555.asia-southeast1.run.app")
COMMUNITY1_URL = "https://meetchi-gpu-asr-wfqjx2j42q-as.a.run.app"
GCS_BUCKET = "gs://project-51769b5e-7f0f-4a2f-80c-meetchi-audio"

def main():
    parser = argparse.ArgumentParser(description="Test community-1 diarization")
    parser.add_argument("--reuse-meeting", default=None, help="Reuse an existing meeting ID (skip upload)")
    parser.add_argument("--audio-meeting", default="cf75462b-dd01-468b-a2ba-ad746ad0e90d",
                        help="Meeting ID whose GCS audio to reuse (default: AI 2026 test file)")
    parser.add_argument("--language", default="zh")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    print("=" * 60)
    print("MeetChi Community-1 Diarization E2E Test")
    print("=" * 60)

    # Step 1: Health check community-1
    print("\n[1/4] Health check community-1 endpoint...")
    print(f"  URL: {COMMUNITY1_URL}/health")
    try:
        r = requests.get(f"{COMMUNITY1_URL}/health", timeout=300)
        print(f"  HTTP {r.status_code}: {r.text[:200]}")
        if r.status_code != 200:
            print("  [WARN] Health check non-200, proceeding anyway...")
    except requests.exceptions.Timeout:
        print("  [WARN] Health check timeout (cold start may still be in progress)")
    except Exception as e:
        print(f"  [WARN] Health check error: {e}")

    # Step 2: Determine which meeting/audio to use
    if args.reuse_meeting:
        meeting_id = args.reuse_meeting
        print(f"\n[2/4] Reusing existing meeting: {meeting_id}")
        r = requests.get(f"{BASE_URL}/api/v1/meetings/{meeting_id}", timeout=30)
        r.raise_for_status()
        d = r.json()
        audio_gcs = f"{GCS_BUCKET}/audio/{meeting_id}.mp4"
        print(f"  Title: {d.get('title', 'N/A')}")
        print(f"  Status: {d.get('status')}")
        print(f"  GCS audio: {audio_gcs}")
    else:
        # Create a new meeting, but reuse the GCS audio from another meeting
        source_meeting_id = args.audio_meeting
        print(f"\n[2/4] Creating new meeting (reusing audio from {source_meeting_id})...")

        # Create new meeting record
        r = requests.post(f"{BASE_URL}/api/v1/meetings", json={
            "title": f"Community-1 Test - {time.strftime('%Y%m%d-%H%M%S')}",
            "language": args.language,
            "template_name": "general"
        })
        r.raise_for_status()
        meeting_id = r.json()["id"]
        print(f"  New meeting ID: {meeting_id}")

        # Copy GCS audio from source meeting to new meeting using gcloud
        src_gcs = f"{GCS_BUCKET}/audio/{source_meeting_id}.mp4"
        dst_gcs = f"{GCS_BUCKET}/audio/{meeting_id}.mp4"
        print(f"  Copying GCS audio: {src_gcs} -> {dst_gcs}")
        import subprocess
        cp_result = subprocess.run(
            ["gcloud", "storage", "cp", src_gcs, dst_gcs],
            capture_output=True, text=True, timeout=60, shell=True
        )
        if cp_result.returncode != 0:
            print(f"  [FAIL] GCS copy failed: {cp_result.stderr}")
            sys.exit(1)
        print(f"  [OK] GCS copy complete")
        audio_gcs = dst_gcs

    # Step 3: Call community-1 endpoint directly
    print(f"\n[3/4] Calling community-1 /asr/refine (timeout={args.timeout}s)...")
    print(f"  Meeting ID: {meeting_id}")
    print(f"  Audio: {audio_gcs}")
    print(f"  Language: {args.language}")

    # Build callback URL so backend DB gets updated automatically
    callback_url = f"{BASE_URL}/api/v1/callbacks/asr-done"

    start = time.time()
    try:
        res = requests.post(
            f"{COMMUNITY1_URL}/asr/refine",
            json={
                "meeting_id": meeting_id,
                "audio_url": audio_gcs,
                "language": args.language,
                "callback_url": callback_url
            },
            timeout=args.timeout
        )
        elapsed = time.time() - start
        print(f"\n  HTTP {res.status_code} after {elapsed:.1f}s")

        if res.status_code == 200:
            data = res.json()
            status = data.get("status")
            segments = data.get("segments", [])
            speakers = data.get("speakers_count", 0)
            duration = data.get("duration", 0)
            error = data.get("error")

            print(f"  ASR Status    : {status}")
            print(f"  Segments      : {len(segments)}")
            print(f"  Speakers      : {speakers}")
            print(f"  Duration      : {duration:.1f}s")
            if error:
                print(f"  Error         : {error}")

            # Show first few segments with speaker labels
            if segments:
                print(f"\n  --- First 5 segments ---")
                for seg in segments[:5]:
                    spk = seg.get("speaker", "?")
                    txt = seg.get("text", "")[:80]
                    t_start = seg.get("start", 0)
                    print(f"  [{spk}] {t_start:.1f}s: {txt}")

                # Check speaker diversity
                speakers_seen = set(s.get("speaker") for s in segments if s.get("speaker"))
                print(f"\n  Unique speakers in segments: {speakers_seen}")
        else:
            print(f"  Response: {res.text[:500]}")

    except requests.exceptions.Timeout:
        elapsed = time.time() - start
        print(f"  [FAIL] TIMEOUT after {elapsed:.1f}s")
        sys.exit(1)
    except Exception as e:
        elapsed = time.time() - start
        print(f"  [FAIL] ERROR after {elapsed:.1f}s: {e}")
        sys.exit(1)

    # Step 4: Verify backend DB
    print(f"\n[4/4] Verifying backend DB for meeting {meeting_id}...")
    time.sleep(3)  # Give callback a moment
    r2 = requests.get(f"{BASE_URL}/api/v1/meetings/{meeting_id}", timeout=30)
    if r2.status_code == 200:
        d2 = r2.json()
        db_status = d2.get("status")
        db_segs = d2.get("transcript_segments", [])
        db_summary = d2.get("summary_json")

        print(f"  DB Status   : {db_status}")
        print(f"  DB Segments : {len(db_segs)}")
        print(f"  DB Summary  : {'Yes' if db_summary else 'No'}")

        if db_segs:
            # Check speaker labels in DB
            speakers_in_db = set(s.get("speaker") for s in db_segs if s.get("speaker"))
            print(f"  DB Speakers : {speakers_in_db}")

        # Final verdict
        print(f"\n{'='*60}")
        if len(segments) > 0 and len(speakers_seen) > 1:
            print(f"[PASS] Community-1 diarization PASSED")
            print(f"  Meeting  : {meeting_id}")
            print(f"  Segments : {len(segments)}")
            print(f"  Speakers : {speakers_seen}")
            print(f"  Time     : {elapsed:.1f}s")
        elif len(segments) > 0:
            print(f"[PARTIAL] Transcription OK but only 1 speaker detected")
            print(f"  Meeting  : {meeting_id}")
            print(f"  Segments : {len(segments)}")
        else:
            print(f"[FAIL] No segments returned - check community-1 logs")
        print(f"{'='*60}")
    else:
        print(f"  [FAIL] Backend query failed: HTTP {r2.status_code}")


if __name__ == "__main__":
    main()
