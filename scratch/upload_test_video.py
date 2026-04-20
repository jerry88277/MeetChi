import json
import urllib.request
import os
import sys

BASE_URL = "https://meetchi-backend-705495828555.asia-southeast1.run.app"
VIDEO_PATH = r"d:\Side_project\MeetChi\GCP_app_test_audio\Hermes Agent 完整使用教程_1080p.mp4"

def post_json(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req) as res:
        return json.loads(res.read().decode())

def put_file(url, file_path, content_type):
    from urllib.request import Request, urlopen
    file_size = os.path.getsize(file_path)
    
    # We read file in chunks for urllib or just read entire file since memory is ok for small video?
    # Usually video might be 10MB-100MB, so it's okay.
    with open(file_path, 'rb') as f:
        data = f.read()
        
    req = Request(url, data=data, method='PUT', headers={'Content-Type': content_type})
    with urlopen(req) as res:
        return res.status

def main():
    if not os.path.exists(VIDEO_PATH):
        print(f"Error: file not found at {VIDEO_PATH}")
        sys.exit(1)
        
    print("1. Creating Meeting...")
    meeting_data = post_json(f"{BASE_URL}/api/v1/meetings", {
        "title": "Hermes Agent 完整使用教程_測試上傳",
        "language": "zh",
        "template_name": "general",
        "user_upn": "test@company.com"
    })
    meeting_id = meeting_data['id']
    print(f"Created meeting ID: {meeting_id}")
    
    print("2. Requesting Upload URL...")
    upload_info = post_json(f"{BASE_URL}/api/v1/meetings/{meeting_id}/upload-url", {
        "filename": os.path.basename(VIDEO_PATH),
        "contentType": "video/mp4"
    })
    upload_url = upload_info.get("upload_url") or upload_info.get("uploadUrl")
    print("Received Upload URL")
    
    print("3. Uploading Video (this may take a while)...")
    status = put_file(upload_url, VIDEO_PATH, "video/mp4")
    print(f"Upload complete with status {status}")
    
    print("4. Triggering transcription task...")
    try:
        # Note: this might block or throw 504 on Cloud Run if it takes > 60m, but 
        # usually Cloud Run returns 200 ok if it routes to background, or blocks.
        task_res = post_json(f"{BASE_URL}/api/v1/tasks/transcription", {
            "meeting_id": meeting_id,
            "template_type": "general"
        })
        print("Transcription task returned:", task_res)
    except Exception as e:
        print("Exception triggering transcription:", e)
        # Cloud Run might timeout the HTTP request if it takes > 1 hour, that's fine.

if __name__ == "__main__":
    main()
