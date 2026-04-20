import subprocess
import json
import os
import sys

AUDIO_FILES = [
    "Hermes.wav",
    "Maldives.wav"
]
MODELS = ["faster-whisper", "mla"]
VADS = ["on", "off"]
OUTPUT_JSON = "benchmark_results_{}_{}_{}.json"

def run_worker(model, vad, audio):
    output_file = OUTPUT_JSON.format(model, vad, os.path.basename(audio))
    print(f"\n=======================================================", flush=True)
    print(f"[*] Running Benchmark Worker: [{model}] | VAD: [{vad}] | Audio: [{os.path.basename(audio)}]", flush=True)
    print(f"=======================================================", flush=True)
    
    if model == "faster-whisper":
        executor = r"d:\Side_project\MeetChi\apps\backend\.venv\Scripts\python.exe"
    else:
        executor = r"d:\Side_project\MeetChi\whisper_mla\.venv\Scripts\python.exe"
        
    cmd = [
        executor,
        "benchmark_worker.py",
        "--model", model,
        "--vad", vad,
        "--audio", audio,
        "--output", output_file
    ]
    
    try:
        subprocess.run(cmd, check=True)
        with open(output_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[X] Worker failed: {e}", flush=True)
        return None

def main():
    results = []
    for audio in AUDIO_FILES:
        for model in MODELS:
            for vad in VADS:
                res = run_worker(model, vad, audio)
                if res:
                    results.append(res)
    
    print("\n\n" + "="*80)
    print("[*] BENCHMARK RESULTS (Markdown Table Format)")
    print("="*80 + "\n")
    
    # Generate Markdown Table
    print("| Audio File | Model | VAD | Duration (s) | Load Time (s) | Infer Time (s) | RTF | Peak VRAM (MB) | Delta VRAM (MB) |")
    print("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        audio_name = os.path.basename(r['audio'])
        # Shorten audio name for display if needed
        audio_name_disp = audio_name[:15] + "..." if len(audio_name)>15 else audio_name
        print(f"| {audio_name_disp} | **{r['model']}** | {r['vad']} | {r['duration_sec']:.1f} | {r['load_time_sec']:.2f} | {r['infer_time_sec']:.2f} | **{r['rtf']:.4f}** | {r['peak_vram_mb']} | {r['vram_delta_mb']} |")

    # Save to a final json
    with open("benchmark_final_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)
        
    print("\n[*] Saved detailed report to benchmark_final_report.json")

if __name__ == '__main__':
    main()
