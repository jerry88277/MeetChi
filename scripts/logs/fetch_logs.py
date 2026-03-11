"""
fetch_logs.py — Unified Cloud Run log viewer

Usage:
    python scripts/logs/fetch_logs.py                          # backend logs, last 10min
    python scripts/logs/fetch_logs.py --service meetchi-gpu-asr # GPU ASR logs
    python scripts/logs/fetch_logs.py --severity ERROR          # errors only
    python scripts/logs/fetch_logs.py --since 30m               # last 30 minutes
    python scripts/logs/fetch_logs.py --limit 50                # max 50 entries
"""
import subprocess
import json
import sys
import argparse
import os

PROJECT = os.getenv("GCP_PROJECT", "project-51769b5e-7f0f-4a2f-80c")

def main():
    parser = argparse.ArgumentParser(description="MeetChi Cloud Run Log Viewer")
    parser.add_argument("--service", default="meetchi-backend",
                        choices=["meetchi-backend", "meetchi-gpu-asr", "meetchi-frontend"],
                        help="Cloud Run service name")
    parser.add_argument("--severity", default=None,
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Minimum severity filter")
    parser.add_argument("--since", default="10m", help="Time window (e.g. 10m, 1h, 6h)")
    parser.add_argument("--limit", type=int, default=30, help="Max log entries")
    parser.add_argument("--no-health", action="store_true", default=True,
                        help="Exclude health check logs (default: True)")
    args = parser.parse_args()

    # Build filter
    filters = [
        f'resource.type="cloud_run_revision"',
        f'resource.labels.service_name="{args.service}"',
    ]
    if args.severity:
        filters.append(f'severity>={args.severity}')

    cmd = [
        "gcloud.cmd", "logging", "read",
        " AND ".join(filters),
        f"--limit={args.limit}",
        f"--freshness={args.since}",
        "--format=json",
        f"--project={PROJECT}"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding='utf-8')
        logs = json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"gcloud error: {e.stderr}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError:
        print("Failed to parse log output", file=sys.stderr)
        sys.exit(1)

    if not logs:
        print(f"No logs found for {args.service} in last {args.since}")
        return

    # Reverse to chronological order
    logs.reverse()

    count = 0
    for log in logs:
        ts = log.get('timestamp', '')[11:19]
        sev = log.get('severity', 'INFO')

        # Extract message
        msg = ''
        if 'textPayload' in log:
            msg = log['textPayload']
        elif 'jsonPayload' in log:
            jp = log['jsonPayload']
            msg = jp.get('message', '') if isinstance(jp, dict) else str(jp)
        elif 'httpRequest' in log:
            req = log['httpRequest']
            msg = f"{req.get('requestMethod')} {req.get('requestUrl', '').split('?')[0]} {req.get('status')}"

        # Skip health checks
        if args.no_health and '/health' in msg:
            continue

        count += 1
        # Color by severity
        prefix = {"ERROR": "❌", "WARNING": "⚠️", "INFO": "  ", "DEBUG": "🔍"}.get(sev, "  ")
        print(f"{prefix} [{ts}] {msg.strip()}")

    print(f"\n--- {count} log entries from {args.service} (last {args.since}) ---")

if __name__ == "__main__":
    main()
