import urllib.request
import json
import codecs
import sys

# Ensure UTF-8 output
sys.stdout = codecs.getwriter("utf-8")(sys.stdout.detach())

try:
    url = "https://meetchi-backend-705495828555.asia-southeast1.run.app/api/v1/meetings"
    response = urllib.request.urlopen(url)
    data = json.loads(response.read().decode('utf-8'))
    for m in data:
        print(f"ID: {m['id']} | Status: {m['status']}")
except Exception as e:
    print("Error:", e)
