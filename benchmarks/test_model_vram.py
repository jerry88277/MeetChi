import os
import time
from whisper_mla.inference import WhisperMLAInference

def main():
    model_path = "whisper_mla/breeze-asr-mla-finetuned"
    audio_path = "GCP_app_test_audio/馬爾地夫屎蛋介紹.m4a"

    print("Converting M4A to WAV for libsndfile compatibility...")
    wav_path = audio_path.replace(".m4a", ".wav")
    if not os.path.exists(wav_path):
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", wav_path], check=True)
    audio_path = wav_path

    print("===== 本地端 WhisperMLA 推論與資源測試 =====")
    print(f"Model: {model_path}")
    print(f"Audio: {audio_path}")

    # Initialize Engine
    engine = WhisperMLAInference(model_path=model_path, device="cuda")
    
    # Run once to warm up (or just directly test)
    start_vram = engine.get_memory_stats()
    print(f"VRAM (Initial): {start_vram}")

    print("開始轉錄...")
    start_time = time.time()
    result = engine.transcribe(audio_path, language="zh")
    end_time = time.time()

    post_vram = engine.get_memory_stats()
    print(f"VRAM (Post-Transcription): {post_vram}")
    
    print("\n===== 推論結果 =====")
    print(f"Segments: {len(result.segments)}")
    total_text = "".join(s.text for s in result.segments)
    print(f"Transcript Preview: {total_text[:150]}...")
    
    print("\n===== 性能指標 =====")
    duration = result.duration
    proctime = result.processing_time
    print(f"Audio Duration: {duration:.2f}s")
    print(f"Processing Time: {proctime:.2f}s")
    if duration > 0:
        print(f"RTF (Real Time Factor): {proctime / duration:.4f}")
    
    alloc_gb = post_vram.get('allocated_gb', 0)
    print(f"Peak VRAM allocation: {alloc_gb:.2f} GB")

if __name__ == "__main__":
    main()
