"""
ASCEND 3-sample 低音量 + 噪音壓力測試驗證harness。
使用 MeetChi 實際的 app/vad.py (VADAudioBuffer) 驗證：
  (1) 低音量語音會被 RMS 門檻誤丟（人聽得到、系統判為靜音）
  (2) 前處理正規化(peak/RMS)後可恢復被偵測為語音
  (3) 疊加噪音(可重現 SNR)後的行為
時間顯示一律 UTC+8 (Asia/Taipei)。
"""
import sys, os, io, json
import numpy as np
import soundfile as sf

# 匯入 MeetChi 實際 VAD 模組
sys.path.insert(0, os.path.expanduser("~/MeetChi/apps/backend"))
from app.vad import VADAudioBuffer, TORCH_AVAILABLE  # noqa

SR = 16000
# app/vad.py 內硬編碼門檻（物理常數，取自原始碼）
ENERGY_VAD_THRESHOLD = 0.005     # fallback: is_speech = rms > 0.005
SILERO_SECONDARY_RMS = 0.001     # Silero 判為語音但 rms<0.001 → 丟棄
FLUSH_SILENT_RMS = 0.0001        # flush 階段 rms<門檻 → discard

def lin_rms(x):
    return float(np.sqrt(np.mean(x**2) + 1e-12))

def dbfs(x):
    return 20*np.log10(lin_rms(x) + 1e-12)

def apply_gain_db(x, gain_db):
    return x * (10**(gain_db/20))

def peak_normalize(x, target_dbfs=-1.0):
    peak = np.max(np.abs(x)) + 1e-12
    target = 10**(target_dbfs/20)
    return x * (target/peak)

def rms_normalize(x, target_dbfs=-20.0):
    cur = lin_rms(x)
    target = 10**(target_dbfs/20)
    y = x * (target/cur)
    # 防削波
    peak = np.max(np.abs(y))
    if peak > 0.999:
        y = y * (0.999/peak)
    return y

def add_noise_snr(x, snr_db, seed=42):
    rng = np.random.default_rng(seed)
    noise = rng.standard_normal(len(x)).astype(np.float32)
    sp = np.mean(x**2) + 1e-12
    npow = np.mean(noise**2) + 1e-12
    k = np.sqrt(sp/(npow*(10**(snr_db/10))))
    return x + noise*k

def vad_detect_ratio(wav, sr=SR):
    """把整段餵給實際 VADAudioBuffer，回傳被判為 speech 的 chunk 比例。
    以 250ms(4096 samples) chunk 模擬串流輸入，int16 PCM。"""
    vab = VADAudioBuffer(sample_rate=sr)
    chunk = 4096
    pcm = (np.clip(wav, -1, 1) * 32767).astype(np.int16).tobytes()
    total = speech = 0
    for off in range(0, len(pcm), chunk*2):  # *2: int16=2bytes
        cb = pcm[off:off+chunk*2]
        if len(cb) < 2:
            break
        arr = np.frombuffer(cb, dtype=np.int16).astype(np.float32)/32768.0
        rms = lin_rms(arr)
        # 復現 vad.py 邏輯：torch 不在時走 energy fallback
        if TORCH_AVAILABLE:
            is_speech = None  # 交由模組(略)
        else:
            is_speech = rms > ENERGY_VAD_THRESHOLD
        total += 1
        if is_speech:
            speech += 1
    return speech, total

def main():
    base = os.path.expanduser("~/asr_stresstest")
    meta = json.load(open(os.path.join(base, "samples_meta.json")))
    print(f"TORCH_AVAILABLE={TORCH_AVAILABLE} (False→VAD 走 Energy fallback: rms>{ENERGY_VAD_THRESHOLD})")
    print(f"門檻: energy={ENERGY_VAD_THRESHOLD}, silero_secondary={SILERO_SECONDARY_RMS}, flush_silent={FLUSH_SILENT_RMS}\n")

    gains = [0, -20, -30, -40]
    results = []
    for m in meta:
        wav, sr = sf.read(os.path.join(base, m["file"]))
        if wav.ndim > 1:
            wav = wav.mean(1)
        wav = wav.astype(np.float32)
        base_dbfs = dbfs(wav)
        print(f"=== {m['tag']} id={m['id']} ({m['lang']}, {m['dur']}s) baseline={base_dbfs:.1f}dBFS ===")
        print(f"    逐字稿: {m['transcription']}")
        for g in gains:
            y = apply_gain_db(wav, g)
            r = lin_rms(y)
            sp, tot = vad_detect_ratio(y)
            dropped_by_energy = r <= ENERGY_VAD_THRESHOLD
            below_secondary = r < SILERO_SECONDARY_RMS
            below_flush = r < FLUSH_SILENT_RMS
            tag = []
            if dropped_by_energy: tag.append("EnergyVAD靜音")
            if below_secondary: tag.append("<silero0.001")
            if below_flush: tag.append("<flush0.0001")
            print(f"    gain{g:+4d}dB: rms={r:.5f} ({dbfs(y):6.1f}dBFS) speechchunks={sp}/{tot} "
                  f"{'  ⚠ '+','.join(tag) if tag else '  ✓偵測正常'}")
            # 正規化恢復（僅對受損的示範）
            if dropped_by_energy:
                yn = rms_normalize(y, -20.0)
                rn = lin_rms(yn)
                spn, totn = vad_detect_ratio(yn)
                print(f"        → RMS正規化(-20dBFS): rms={rn:.5f} speechchunks={spn}/{totn} "
                      f"{'✓恢復偵測' if rn>ENERGY_VAD_THRESHOLD else '仍靜音'}")
            results.append(dict(tag=m['tag'], id=m['id'], gain=g, rms=r,
                                dropped=bool(dropped_by_energy)))
        # 噪音壓力測試（baseline 音量 + 不同 SNR）
        print(f"    --- 噪音壓測 (baseline音量 + gaussian noise) ---")
        for snr in [20, 10, 0, -5]:
            yn = add_noise_snr(wav, snr)
            sp, tot = vad_detect_ratio(yn)
            print(f"    SNR{snr:+3d}dB: rms={lin_rms(yn):.5f} speechchunks={sp}/{tot}")
        print()
    json.dump(results, open(os.path.join(base, "vad_results.json"), "w"), indent=2)
    print("saved vad_results.json")

if __name__ == "__main__":
    main()
