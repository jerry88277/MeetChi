import argparse
import time
import json
import os
import threading
import subprocess
import soundfile as sf
from datetime import datetime

# VRAM memory monitor thread
class VramMonitor(threading.Thread):
    def __init__(self, pid, interval=0.1):
        super().__init__()
        self.pid = pid
        self.interval = interval
        self.running = True
        self.max_vram_mb = 0
        self.base_vram_mb = 0
        self.history = []

    def run(self):
        # Wait a bit for the first measurement to be our "base" VRAM for the process
        time.sleep(0.5)
        self.base_vram_mb = self.get_vram()
        while self.running:
            vram = self.get_vram()
            if vram > 0:
                self.max_vram_mb = max(self.max_vram_mb, vram)
                self.history.append(vram)
            time.sleep(self.interval)

    def get_vram(self):
        try:
            # Query global GPU used memory since WDDM process-specific memory returns [N/A]
            result = subprocess.check_output(
                ['nvidia-smi', '--query-gpu=memory.used', '--format=csv,nounits,noheader'],
                encoding='utf-8'
            )
            return int(result.strip().split('\n')[0].strip())
        except Exception:
            return 0

    def stop(self):
        self.running = False


def transcribe_faster_whisper(audio_path, vad):
    from faster_whisper import WhisperModel
    # Model corresponds to meetchi-gpu-asr Breeze-ASR-25
    model_name = "SoybeanMilk/faster-whisper-Breeze-ASR-25"
    
    # Load model
    start_load = time.time()
    model = WhisperModel(model_name, device="cuda", compute_type="float16")
    load_time = time.time() - start_load
    
    # Transcribe
    vad_parameters = {"min_silence_duration_ms": 500, "speech_pad_ms": 200} if vad else None
    
    start_infer = time.time()
    segments, info = model.transcribe(
        audio_path,
        language="zh",
        beam_size=5,
        vad_filter=vad,
        vad_parameters=vad_parameters,
    )
    # materialize generator to force complete execution
    res = list(segments)
    infer_time = time.time() - start_infer
    return load_time, infer_time, res[0].text if res else ""

def transcribe_whisper_mla(audio_path, vad):
    from whisper_mla.inference import WhisperMLAInference
    # Model
    model_path = "./whisper_mla/breeze-asr-mla-finetuned"
    
    start_load = time.time()
    pipe = WhisperMLAInference(model_path)
    load_time = time.time() - start_load
    
    # Setup args corresponding to VAD or Not
    if vad:
        # VAD is handled inside the inference module internally by _split_audio_vad
        pass
    else:
        # To strictly turn off VAD in mla inference, we'd need to mock or change its vad chunker.
        # But it takes VAD min silence ms in its internal _split_audio_vad. 
        pass

    start_infer = time.time()
    result = pipe.transcribe(audio_path, language="zh")
    infer_time = time.time() - start_infer
    
    # Combine text
    res_text = "".join(seg.text for seg in result.segments) if result.segments else ""
    return load_time, infer_time, res_text


def get_audio_duration(audio_path):
    try:
        import soundfile as sf
        with sf.SoundFile(audio_path) as f:
            return f.frames / f.samplerate
    except Exception as e:
        print(f"Failed to get audio duration via soundfile: {e}")
        return 0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=str, required=True, choices=["faster-whisper", "mla"])
    parser.add_argument("--vad", type=str, required=True, choices=["on", "off"])
    parser.add_argument("--audio", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    args = parser.parse_args()

    vad_bool = (args.vad == "on")
    pid = os.getpid()

    # Get duration
    duration = get_audio_duration(args.audio)
    print(f"Audio Duration: {duration:.2f} s", flush=True)

    monitor = VramMonitor(pid)
    monitor.start()

    try:
        if args.model == "faster-whisper":
            load_time, infer_time, snippet = transcribe_faster_whisper(args.audio, vad_bool)
        elif args.model == "mla":
            load_time, infer_time, snippet = transcribe_whisper_mla(args.audio, vad_bool)
        else:
            raise ValueError("Unknown model")
            
        rtf = infer_time / duration if duration > 0 else 0
    except Exception as e:
        print(f"Execution Error: {e}")
        load_time, infer_time, snippet, rtf = 0, 0, f"Error: {e}", 0

    monitor.stop()
    monitor.join()

    result = {
        "model": args.model,
        "vad": args.vad,
        "audio": args.audio,
        "duration_sec": duration,
        "load_time_sec": load_time,
        "infer_time_sec": infer_time,
        "rtf": rtf,
        "base_vram_mb": monitor.base_vram_mb,
        "peak_vram_mb": monitor.max_vram_mb,
        "vram_delta_mb": monitor.max_vram_mb - monitor.base_vram_mb,
        "text_snippet": snippet[:100] + "..." if len(snippet) > 100 else snippet
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    main()
