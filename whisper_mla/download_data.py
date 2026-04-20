"""
Download training datasets and Breeze ASR 25 model weights.
Run with whisper_mla venv:
  .venv\Scripts\python.exe whisper_mla\download_data.py

v4: Fixed torchcodec/FFmpeg DLL issue on Windows.
- Use Audio(decode=False) to skip audio decoding during download
- Audio will be decoded later during training (by soundfile/torchaudio)
- Added HF_TOKEN authentication for gated datasets (NTUML2021, CV17)
- Skip already-completed datasets (check dataset_info.json)
"""
import os
import sys
import time
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "download.log"),
            encoding="utf-8",
            mode="w",
        ),
    ],
)
logger = logging.getLogger(__name__)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")

# HuggingFace Token for gated datasets — supply via env var, do not hardcode.
HF_TOKEN = os.environ.get("HF_TOKEN")
if not HF_TOKEN:
    raise RuntimeError(
        "HF_TOKEN env var is required for downloading gated datasets. "
        "Get a token at https://huggingface.co/settings/tokens"
    )


def _is_saved(save_path):
    """Check if a dataset has already been saved (Arrow format)."""
    return os.path.exists(save_path) and os.path.exists(
        os.path.join(save_path, "dataset_info.json")
    )


def _save_streaming(ds_stream, save_path, name, log_interval=5000):
    """Stream a dataset and save to Arrow format."""
    from datasets import Dataset

    os.makedirs(save_path, exist_ok=True)
    records = []
    count = 0
    for example in ds_stream:
        records.append(example)
        count += 1
        if count % log_interval == 0:
            logger.info(f"  {name}: {count} samples streamed...")

    logger.info(f"  {name}: {count} samples loaded, converting to Arrow...")
    ds = Dataset.from_list(records)
    ds.save_to_disk(save_path)
    logger.info(f"  {name}: saved {count} samples → {save_path}")
    return count


def download_breeze_asr25():
    """Download Breeze ASR 25 model weights."""
    from transformers import WhisperForConditionalGeneration, WhisperProcessor

    save_path = os.path.join(MODEL_DIR, "breeze-asr-25")
    if os.path.exists(os.path.join(save_path, "model.safetensors")):
        logger.info(f"✅ Breeze ASR 25 already at {save_path}")
        return

    os.makedirs(save_path, exist_ok=True)
    logger.info("Downloading Breeze ASR 25 model...")
    start = time.time()
    model = WhisperForConditionalGeneration.from_pretrained(
        "MediaTek-Research/Breeze-ASR-25", torch_dtype="auto"
    )
    model.save_pretrained(save_path)
    processor = WhisperProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
    processor.save_pretrained(save_path)
    logger.info(f"✅ Breeze ASR 25 in {time.time() - start:.0f}s")


def download_librispeech():
    """Download LibriSpeech train.clean.100 + train.clean.360.
    
    Key fix: Use Audio(decode=False) to avoid torchcodec dependency.
    The raw audio bytes are stored and decoded during training.
    """
    from datasets import load_dataset, Audio

    # --- train.clean.100 ---
    save_100 = os.path.join(DATA_DIR, "librispeech_train100")
    if _is_saved(save_100):
        logger.info(f"✅ LibriSpeech train.100 already at {save_100}")
    else:
        logger.info("Downloading LibriSpeech train.clean.100 (100hr)...")
        start = time.time()
        try:
            # Try non-streaming first (faster if no decode needed)
            ds100 = load_dataset(
                "librispeech_asr", "clean", split="train.100",
            )
            # Disable audio decoding to avoid torchcodec
            ds100 = ds100.cast_column("audio", Audio(decode=False))
            os.makedirs(save_100, exist_ok=True)
            ds100.save_to_disk(save_100)
            logger.info(f"  train.100: {len(ds100)} samples → {save_100}")
        except Exception as e:
            logger.warning(f"  Non-streaming failed: {e}")
            logger.info("  Falling back to streaming mode...")
            ds100_stream = load_dataset(
                "librispeech_asr", "clean", split="train.100", streaming=True,
            )
            # cast_column works on IterableDataset too
            ds100_stream = ds100_stream.cast_column("audio", Audio(decode=False))
            _save_streaming(ds100_stream, save_100, "train.100")
        logger.info(f"  Completed in {time.time() - start:.0f}s")

    # --- train.clean.360 ---
    save_360 = os.path.join(DATA_DIR, "librispeech_train360")
    if _is_saved(save_360):
        logger.info(f"✅ LibriSpeech train.360 already at {save_360}")
    else:
        logger.info("Downloading LibriSpeech train.clean.360 (360hr) via streaming...")
        start = time.time()
        ds360_stream = load_dataset(
            "librispeech_asr", "clean", split="train.360", streaming=True,
        )
        ds360_stream = ds360_stream.cast_column("audio", Audio(decode=False))
        _save_streaming(ds360_stream, save_360, "train.360", log_interval=10000)
        logger.info(f"  Completed in {time.time() - start:.0f}s")


def download_aishell1():
    """Download AISHELL-1 (170hr Mandarin) from carlot/AIShell."""
    from datasets import load_dataset, Audio

    save_path = os.path.join(DATA_DIR, "aishell1")
    if _is_saved(save_path):
        logger.info(f"✅ AISHELL-1 already at {save_path}")
        return

    logger.info("Downloading AISHELL-1 (170hr) from carlot/AIShell...")
    start = time.time()

    # Use streaming + Audio(decode=False) to avoid torchcodec
    ds_stream = load_dataset(
        "carlot/AIShell", split="train", streaming=True, token=HF_TOKEN,
    )
    ds_stream = ds_stream.cast_column("audio", Audio(decode=False))
    count = _save_streaming(ds_stream, save_path, "AISHELL-1")
    logger.info(f"✅ AISHELL-1 completed: {count} samples in {time.time() - start:.0f}s")


def download_ntuml2021():
    """Download NTUML2021 (11hr Code-switching).
    
    This dataset is gated — requires HF_TOKEN.
    """
    from datasets import load_dataset, Audio

    save_path = os.path.join(DATA_DIR, "ntuml2021")
    if _is_saved(save_path):
        logger.info(f"✅ NTUML2021 already at {save_path}")
        return

    logger.info("Downloading NTUML2021 (11hr code-switching)...")

    repos = [
        "NTU-corpus/NTUML2021",
        "Mediatek-Research/NTUML2021",
    ]

    for repo in repos:
        try:
            logger.info(f"  Trying: {repo}...")
            ds_stream = load_dataset(
                repo, split="train", streaming=True, token=HF_TOKEN,
            )
            # Try to read one sample to verify access
            sample = next(iter(ds_stream))
            logger.info(f"  Connected to {repo}, keys={list(sample.keys())}")

            # Check if 'audio' column exists
            if "audio" in sample:
                ds_stream = load_dataset(
                    repo, split="train", streaming=True, token=HF_TOKEN,
                )
                ds_stream = ds_stream.cast_column("audio", Audio(decode=False))

            count = _save_streaming(ds_stream, save_path, "NTUML2021", log_interval=1000)
            logger.info(f"✅ NTUML2021 completed: {count} samples")
            return
        except Exception as e:
            logger.warning(f"  Failed: {repo} — {e}")

    logger.error(
        "⚠️ NTUML2021: All repos failed. "
        "Fine-tuning can proceed with AISHELL-1 + LibriSpeech; "
        "NTUML2021 is optional (CS oversampling)."
    )


def download_cv17_zhtw():
    """Download CommonVoice17 zh-TW (test split for validation).
    
    This is a gated dataset requiring:
    1. HF account with accepted license
    2. HF_TOKEN for authentication
    
    Full name: mozilla-foundation/common_voice_17_0
    """
    from datasets import load_dataset, Audio

    save_path = os.path.join(DATA_DIR, "cv17_zhtw")
    if _is_saved(save_path):
        logger.info(f"✅ CV17-zh-TW already at {save_path}")
        return

    logger.info("Downloading CommonVoice17 zh-TW (test split)...")
    logger.info("  Dataset: mozilla-foundation/common_voice_17_0, config=zh-TW")

    try:
        ds = load_dataset(
            "mozilla-foundation/common_voice_17_0", "zh-TW",
            split="test", token=HF_TOKEN,
        )
        ds = ds.cast_column("audio", Audio(decode=False))
        os.makedirs(save_path, exist_ok=True)
        ds.save_to_disk(save_path)
        logger.info(f"✅ CV17-zh-TW: {len(ds)} samples → {save_path}")
        return
    except Exception as e:
        logger.warning(f"  Direct download failed: {e}")

    # Fallback: streaming
    try:
        logger.info("  Trying streaming mode...")
        ds_stream = load_dataset(
            "mozilla-foundation/common_voice_17_0", "zh-TW",
            split="test", streaming=True, token=HF_TOKEN,
        )
        ds_stream = ds_stream.cast_column("audio", Audio(decode=False))
        count = _save_streaming(ds_stream, save_path, "CV17-zh-TW")
        logger.info(f"✅ CV17-zh-TW completed ({count} samples)")
        return
    except Exception as e:
        logger.error(f"  CV17-zh-TW streaming also failed: {e}")

    logger.error(
        "⚠️ CV17-zh-TW: Download failed. "
        "Please accept the license at "
        "https://huggingface.co/datasets/mozilla-foundation/common_voice_17_0 "
        "and ensure your HF_TOKEN has access. "
        "Validation can use LibriSpeech test split as alternative."
    )


if __name__ == "__main__":
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(MODEL_DIR, exist_ok=True)

    logger.info(f"HF_TOKEN: {'set (' + HF_TOKEN[:8] + '...)' if HF_TOKEN else 'NOT SET'}")

    steps = [
        ("Breeze ASR 25 Model", download_breeze_asr25),
        ("LibriSpeech", download_librispeech),
        ("AISHELL-1", download_aishell1),
        ("NTUML2021 (CS)", download_ntuml2021),
        ("CV17-zh-TW", download_cv17_zhtw),
    ]

    logger.info(f"=== Downloading {len(steps)} items ===")
    logger.info(f"  DATA_DIR: {DATA_DIR}")
    logger.info(f"  MODEL_DIR: {MODEL_DIR}")
    total_start = time.time()

    results = {}
    for name, fn in steps:
        logger.info(f"\n{'='*50}")
        logger.info(f"Starting: {name}")
        logger.info(f"{'='*50}")
        try:
            fn()
            results[name] = "✅"
        except Exception as e:
            logger.error(f"FAILED: {name} — {type(e).__name__}: {e}")
            results[name] = f"❌ {type(e).__name__}"

    total_elapsed = time.time() - total_start
    logger.info(f"\n{'='*50}")
    logger.info(f"Summary ({total_elapsed/60:.1f} minutes):")
    for name, status in results.items():
        logger.info(f"  {status} {name}")
    logger.info(f"{'='*50}")
