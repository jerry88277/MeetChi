"""
check_meeting.py - Check meeting status and optionally trigger transcription
Usage: python scripts/e2e/check_meeting.py <meeting_id> [--trigger]
"""
import os, sys, time, json, requests, argparse

BASE_URL = os.getenv("MEETCHI_BACKEND_URL", "https://meetchi-backend-705495828555.asia-southeast1.run.app")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("meeting_id")
    parser.add_argument("--trigger", action="store_true", help="Trigger transcription if not already processing")
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args()

    mid = args.meeting_id

    # Check current status
    r = requests.get(f"{BASE_URL}/api/v1/meetings/{mid}", timeout=30)
    r.raise_for_status()
    d = r.json()
    status = d.get("status")
    segments = d.get("transcript_segments", [])
    summary = d.get("summary_json")

    print(f"Meeting ID : {mid}")
    print(f"Status     : {status}")
    print(f"Segments   : {len(segments)}")
    print(f"Summary    : {'Yes' if summary else 'No'}")
    print(f"Title      : {d.get('title', 'N/A')}")

    if status == "COMPLETED" and len(segments) > 0:
        print("\n[OK] Already COMPLETED - no action needed")
        return

    if status in ("PROCESSING", "PENDING") and not args.trigger:
        print(f"\n[INFO] Status is {status}. Use --trigger to re-trigger transcription.")
        return

    if args.trigger:
        print(f"\nTriggering transcription (timeout={args.timeout}s)...")
        start = time.time()
        try:
            res = requests.post(
                f"{BASE_URL}/api/v1/tasks/transcription",
                json={"meeting_id": mid},
                timeout=args.timeout
            )
            elapsed = time.time() - start
            print(f"HTTP {res.status_code} after {elapsed:.1f}s")
            print(f"Response: {res.text[:300]}")
        except requests.exceptions.Timeout:
            elapsed = time.time() - start
            print(f"[FAIL] TIMEOUT after {elapsed:.1f}s")
            sys.exit(1)
        except Exception as e:
            elapsed = time.time() - start
            print(f"[FAIL] ERROR after {elapsed:.1f}s: {e}")
            sys.exit(1)

        # Verify final status
        r2 = requests.get(f"{BASE_URL}/api/v1/meetings/{mid}", timeout=30)
        d2 = r2.json()
        status2 = d2.get("status")
        segs2 = d2.get("transcript_segments", [])
        sum2 = d2.get("summary_json")

        print(f"\nFinal Status  : {status2}")
        print(f"Final Segments: {len(segs2)}")
        print(f"Final Summary : {'Yes' if sum2 else 'No'}")

        if status2 == "COMPLETED" and len(segs2) > 0 and sum2:
            print(f"\n{'='*60}")
            print(f"[PASS] E2E PASSED -- Pipeline complete in {elapsed:.1f}s")
            print(f"   Meeting: {mid}")
            print(f"{'='*60}")
        elif status2 == "COMPLETED" and len(segs2) > 0:
            print("\n[PARTIAL] Transcript OK, summary missing")
        elif status2 == "FAILED":
            print("\n[FAIL] FAILED -- Check GPU ASR / Backend logs")
        else:
            print(f"\n[PENDING] STILL PROCESSING -- Status: {status2}")

if __name__ == "__main__":
    main()
