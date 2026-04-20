from google import genai
import os
import sys

# Replace with the actual project / model setting if using vertex ai, but MeetChi uses gemini api key or vertex.
client = genai.Client()
q1 = '有提到專案進度或時程安排嗎？'
q2 = '會議中討論的最大的技術挑戰或瓶頸為何？'
resp1 = client.models.embed_content(model='text-embedding-004', contents=[q1])
resp2 = client.models.embed_content(model='text-embedding-004', contents=[q2])

v1 = resp1.embeddings[0].values
v2 = resp2.embeddings[0].values

print(f"v1 == v2: {v1 == v2}")
print(f"v1[:5] = {v1[:5]}")
print(f"v2[:5] = {v2[:5]}")
