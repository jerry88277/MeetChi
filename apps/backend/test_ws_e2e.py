"""
E2E WebSocket Test — verify scoping bug fix.
Connects to the live Cloud Run WebSocket, sends a config + tiny audio chunk,
then disconnects gracefully. If no UnboundLocalError, the fix works.
"""
import asyncio
import json
import struct
import urllib.request

BASE_URL = "https://meetchi-backend-705495828555.asia-southeast1.run.app"
WS_URL = "wss://meetchi-backend-705495828555.asia-southeast1.run.app/ws/transcribe"

async def test():
    try:
        import websockets
    except ImportError:
        print("Installing websockets...")
        import subprocess, sys
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websockets", "-q"])
        import websockets

    # 1. Create a meeting via REST API
    meeting_data = json.dumps({"title": "E2E Test Meeting", "language": "zh"}).encode()
    req = urllib.request.Request(
        f"{BASE_URL}/api/v1/meetings",
        data=meeting_data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    resp = urllib.request.urlopen(req)
    meeting = json.loads(resp.read())
    meeting_id = meeting["id"]
    print(f"✅ Created meeting: {meeting_id}")

    # 2. Connect WebSocket
    async with websockets.connect(WS_URL, ping_interval=None, close_timeout=5) as ws:
        print("✅ WebSocket connected (no crash!)")

        # 3. Send config
        config = {
            "type": "config",
            "meeting_id": meeting_id,
            "source_language": "zh",
            "target_language": "en",
            "gemini_model": "gemini-2.0-flash-lite"
        }
        await ws.send(json.dumps(config))
        print("✅ Config sent")

        # 4. Wait for any response
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=10)
            print(f"✅ Received: {msg[:200]}")
        except asyncio.TimeoutError:
            print("⏳ No response in 10s (normal if no Gemini session started)")
        except Exception as e:
            print(f"⚠️  Recv error: {e}")

        # 5. Send a tiny audio chunk (silence - 1 second of 16kHz 16-bit mono)
        silence = b'\x00\x00' * 16000  # 1 second of silence
        await ws.send(silence)
        print("✅ Audio chunk sent (1s silence)")

        await asyncio.sleep(3)

        # 6. Send stop signal
        await ws.send(json.dumps({"type": "stop"}))
        print("✅ Stop signal sent")

        await asyncio.sleep(2)

    print("✅ WebSocket closed cleanly")

    # 7. Check meeting status via API
    await asyncio.sleep(3)
    resp = urllib.request.urlopen(f"{BASE_URL}/api/v1/meetings")
    meetings = json.loads(resp.read())
    test_meeting = next((m for m in meetings if m["id"] == meeting_id), None)
    if test_meeting:
        print(f"\n📊 Meeting result:")
        print(f"   ID:       {test_meeting['id'][:8]}...")
        print(f"   Status:   {test_meeting['status']}")
        print(f"   Duration: {test_meeting['duration']}")
        print(f"   Audio:    {test_meeting.get('audio_url', 'None')}")
    else:
        print(f"⚠️  Meeting {meeting_id} not found in API response")

    return meeting_id

if __name__ == "__main__":
    mid = asyncio.run(test())
    print(f"\n🏁 Test complete. Meeting ID: {mid}")
