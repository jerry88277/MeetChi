# quick_transcribe.py - 快速轉錄音檔
import sys
import os

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.transcribe_sprint0 import load_asr_model, correct_keywords

def transcribe_file(audio_path):
    """Quick transcription of an audio file."""
    model = load_asr_model()
    
    system_prompt = """
你是一個專業的 AI 即時聽寫專家。你的任務是將語音精準轉錄為流暢、易讀的【繁體中文】。

[核心原則]
1. 準確性優先：優先保留專有名詞、數字與關鍵術語的正確性。
2. 語意順暢：在不改變原意的前提下，自動修飾口語中的贅字。
3. 繁體中文：所有輸出必須使用台灣正體中文。
4. 標點符號：請根據語氣與停頓，自動加入正確的全形標點符號。
"""
    
    print(f"Transcribing: {audio_path}")
    
    segments, info = model.transcribe(
        audio_path,
        language="zh",
        initial_prompt=system_prompt.strip(),
        beam_size=5,
        temperature=0,
        vad_filter=True,
    )
    
    transcript_parts = []
    for segment in segments:
        if segment.no_speech_prob < 0.85:
            transcript_parts.append(segment.text.strip())
    
    transcript = "".join(transcript_parts)
    transcript = correct_keywords(transcript)
    
    return transcript

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python quick_transcribe.py <audio_file>")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    if not os.path.exists(audio_file):
        print(f"Error: File not found: {audio_file}")
        sys.exit(1)
    
    result = transcribe_file(audio_file)
    print("\n=== Transcription Result ===")
    print(result)
    print("============================")
