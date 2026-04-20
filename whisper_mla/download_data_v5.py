"""
Whisper-MLA Dataset Downloader v5
Strategy: Use huggingface_hub.snapshot_download for resume-capable downloads.
- Downloads parquet files directly to disk (not streaming into RAM)
- Supports resume on network interruption
- Skips already-downloaded datasets
"""
import os
import sys
import logging
from pathlib import Path

# ── Config ──────────────────────────────────────────────
DATA_DIR = Path(r"d:\Side_project\MeetChi\whisper_mla\data")
MODEL_DIR = Path(r"d:\Side_project\MeetChi\whisper_mla\models")
# HF token — must be supplied via env var, never hardcoded.
HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    raise RuntimeError(
        "HF_TOKEN env var is required. "
        "Get a token at https://huggingface.co/settings/tokens"
    )

# ── Logging ─────────────────────────────────────────────
LOG_FILE = Path(r"d:\Side_project\MeetChi\whisper_mla\download.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, mode="w", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── Imports ─────────────────────────────────────────────
from huggingface_hub import snapshot_download, hf_hub_download
from datasets import load_dataset, Audio

results = {}

# ══════════════════════════════════════════════════════════
# 1. Breeze ASR 25 Model
# ══════════════════════════════════════════════════════════
def download_breeze():
    dest = MODEL_DIR / "breeze-asr-25"
    if dest.exists() and any(dest.iterdir()):
        logger.info(f"[SKIP] Breeze ASR 25 already at {dest}")
        return "SKIP"
    logger.info("Downloading Breeze ASR 25 model...")
    snapshot_download(
        repo_id="MediaTek-Research/Breeze-ASR-25",
        local_dir=str(dest),
        token=HF_TOKEN,
        resume_download=True,
    )
    logger.info(f"[DONE] Breeze ASR 25 -> {dest}")
    return "OK"

# ══════════════════════════════════════════════════════════
# 2. LibriSpeech train.100
# ══════════════════════════════════════════════════════════
def download_librispeech_100():
    dest = DATA_DIR / "librispeech_train100"
    if dest.exists() and any(dest.iterdir()):
        logger.info(f"[SKIP] LibriSpeech train.100 already at {dest}")
        return "SKIP"
    logger.info("Downloading LibriSpeech train.100 parquets...")
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="openslr/librispeech_asr",
        repo_type="dataset",
        local_dir=str(dest),
        allow_patterns="clean/train.100/*.parquet",
        resume_download=True,
    )
    logger.info(f"[DONE] LibriSpeech train.100 -> {dest}")
    return "OK"

# ══════════════════════════════════════════════════════════
# 3. LibriSpeech train.360
# ══════════════════════════════════════════════════════════
def download_librispeech_360():
    dest = DATA_DIR / "librispeech_train360"
    # Check if parquets already exist
    if dest.exists():
        parquets = list(dest.rglob("*.parquet"))
        if len(parquets) >= 48:  # train.360 has 48 parquets (0000-0047)
            logger.info(f"[SKIP] LibriSpeech train.360 already has {len(parquets)} parquets at {dest}")
            return "SKIP"
    logger.info("Downloading LibriSpeech train.360 parquets (resume-capable)...")
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="openslr/librispeech_asr",
        repo_type="dataset",
        local_dir=str(dest),
        allow_patterns="clean/train.360/*.parquet",
        resume_download=True,
    )
    parquets = list(dest.rglob("*.parquet"))
    logger.info(f"[DONE] LibriSpeech train.360 -> {dest} ({len(parquets)} parquets)")
    return "OK"

# ══════════════════════════════════════════════════════════
# 4. AISHELL-1
# ══════════════════════════════════════════════════════════
def download_aishell1():
    dest = DATA_DIR / "aishell1"
    if dest.exists():
        parquets = list(dest.rglob("*.parquet"))
        if len(parquets) >= 30:  # aishell1 has 35 parquets
            logger.info(f"[SKIP] AISHELL-1 already has {len(parquets)} parquets at {dest}")
            return "SKIP"
    logger.info("Downloading AISHELL-1 parquets (resume-capable)...")
    dest.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id="carlot/AIShell",
        repo_type="dataset",
        local_dir=str(dest),
        allow_patterns="data/train-*.parquet",
        resume_download=True,
    )
    parquets = list(dest.rglob("*.parquet"))
    logger.info(f"[DONE] AISHELL-1 -> {dest} ({len(parquets)} parquets)")
    return "OK"

# ══════════════════════════════════════════════════════════
# 5. NTUML2021 (optional, code-switching)
# ══════════════════════════════════════════════════════════
def download_ntuml2021():
    dest = DATA_DIR / "ntuml2021"
    if dest.exists() and any(f for f in dest.iterdir() if f.suffix == '.parquet' or f.name == 'dataset_info.json'):
        logger.info(f"[SKIP] NTUML2021 already at {dest}")
        return "SKIP"
    dest.mkdir(parents=True, exist_ok=True)
    # Correct repo: ky552/ML2021_ASR_ST (public, MIT license, no auth needed)
    repo = "ky552/ML2021_ASR_ST"
    try:
        logger.info(f"  Downloading from {repo} (public, MIT license)...")
        snapshot_download(
            repo_id=repo,
            repo_type="dataset",
            local_dir=str(dest),
            resume_download=True,
        )
        logger.info(f"[DONE] NTUML2021 -> {dest}")
        return "OK"
    except Exception as e:
        logger.error(f"[FAIL] NTUML2021: {repo} -- {e}")
        return "FAIL"

# ══════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════
if __name__ == "__main__":
    import time
    start = time.time()

    tasks = [
        ("Breeze ASR 25", download_breeze),
        ("LibriSpeech train.100", download_librispeech_100),
        ("LibriSpeech train.360", download_librispeech_360),
        ("AISHELL-1", download_aishell1),
        ("NTUML2021", download_ntuml2021),
    ]

    logger.info(f"=== Whisper-MLA Dataset Downloader v5 ===")
    logger.info(f"  DATA_DIR: {DATA_DIR}")
    logger.info(f"  MODEL_DIR: {MODEL_DIR}")
    logger.info(f"  Resume-capable: YES")
    logger.info(f"  HF_TOKEN: set ({HF_TOKEN[:8]}...)")
    logger.info("")

    for name, fn in tasks:
        logger.info(f"{'='*50}")
        logger.info(f"Starting: {name}")
        logger.info(f"{'='*50}")
        try:
            results[name] = fn()
        except Exception as e:
            logger.error(f"[FAIL] {name}: {e}")
            results[name] = "FAIL"

    elapsed = (time.time() - start) / 60
    logger.info("")
    logger.info(f"{'='*50}")
    logger.info(f"Summary ({elapsed:.1f} minutes):")
    for name, status in results.items():
        icon = {"OK": "[OK]", "SKIP": "[SKIP]", "FAIL": "[FAIL]"}.get(status, "[??]")
        logger.info(f"  {icon} {name}")
    logger.info(f"{'='*50}")
