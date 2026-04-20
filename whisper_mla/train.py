"""
Whisper-MLA Fine-tuning Script

Fine-tunes the SVD-converted Whisper-MLA model to recover accuracy.
Uses HuggingFace Trainer with mixed-precision training.

Usage:
    python -m whisper_mla.train \
        --model_path ./breeze-asr-mla \
        --output_dir ./breeze-asr-mla-finetuned \
        --epochs 3

Hardware Requirements:
    - RTX 5090 (24GB): batch=4, grad_accum=8 → ~48-72hr
    - RTX 4090 (24GB): batch=4, grad_accum=8 → ~60-90hr
    - L4 (24GB):       batch=4, grad_accum=8 → ~80-120hr
"""

import os
import sys
import logging
import argparse
from typing import Dict, Optional

import torch
# Phase 2: 開啟 TensorFloat-32 (TF32) 支援 (RTX 5090 Blackwell 架構有巨幅加速)
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True

import evaluate
from transformers import (
    WhisperForConditionalGeneration,
    WhisperProcessor,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)
from datasets import load_dataset, concatenate_datasets, Audio, load_from_disk, Dataset
from dataclasses import dataclass

@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    processor: WhisperProcessor
    
    def __call__(self, features):
        input_features = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(
            input_features, return_tensors="pt"
        )
        
        label_features = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(
            label_features, return_tensors="pt"
        )
        
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )
        
        # Remove BOS token if present
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all():
            labels = labels[:, 1:]
        
        batch["labels"] = labels
        return batch

from .config import WhisperMLAConfig, TrainingConfig
from .modeling_whisper_mla import WhisperMLAModel

logger = logging.getLogger(__name__)


def load_training_datasets(config: TrainingConfig, processor: WhisperProcessor):
    """
    Load and prepare training datasets with proper mixing.
    
    Dataset mix:
    - AISHELL-1: 170hr Mandarin
    - LibriSpeech: 460hr English (clean.100 + clean.360)
    - CV17-zh-TW: 100hr Taiwanese Mandarin
    - NTUML2021 (ky552/ML2021_ASR_ST): ~9hr Code-switching (oversampled 5x)
    """
    all_datasets = []
    
    # ── AISHELL-1 (Mandarin) ──
    try:
        logger.info("Loading AISHELL-1 (Offline Parquets)...")
        aishell = load_dataset("parquet", data_dir="whisper_mla/data/aishell1/data", split="train")
        aishell = aishell.cast_column("audio", Audio(sampling_rate=16000))
        all_datasets.append(("aishell1", aishell))
        logger.info(f"  AISHELL-1: {len(aishell)} samples")
    except Exception as e:
        logger.warning(f"Failed to load AISHELL-1: {e}")
    
    # ── LibriSpeech (English) ──
    try:
        logger.info("Loading LibriSpeech (Offline Parquets)...")
        ls_100 = load_from_disk("whisper_mla/data/librispeech_train100")
        ls_360 = load_dataset("parquet", data_files="whisper_mla/data/librispeech_train360/clean/train.360/*.parquet", split="train")
        ls = concatenate_datasets([ls_100, ls_360])
        ls = ls.cast_column("audio", Audio(sampling_rate=16000))
        all_datasets.append(("librispeech", ls))
        logger.info(f"  LibriSpeech: {len(ls)} samples")
    except Exception as e:
        logger.warning(f"Failed to load LibriSpeech: {e}")
    
    # ── CommonVoice25 zh-TW (Taiwanese) ──
    try:
        logger.info("Loading CommonVoice25 zh-TW (Offline TSV)...")
        import pandas as pd
        cv_dir = os.path.join("whisper_mla", "data", "cv25_zhtw", "1774205381984-cv-corpus-25.0-2026-03-09-zh-TW", "cv-corpus-25.0-2026-03-09", "zh-TW")
        cv_df = pd.read_csv(os.path.join(cv_dir, "train.tsv"), sep="\t")
        cv_df["audio"] = cv_df["path"].apply(lambda x: os.path.join(cv_dir, "clips", x))
        cv_df = cv_df[["audio", "sentence"]].dropna()
        cv = Dataset.from_dict({"audio": cv_df["audio"].tolist(), "text": cv_df["sentence"].tolist()})
        cv = cv.cast_column("audio", Audio(sampling_rate=16000))
        all_datasets.append(("cv25_zhtw", cv))
        logger.info(f"  CV25-zh-TW: {len(cv)} samples")
    except Exception as e:
        logger.warning(f"Failed to load CV25-zh-TW: {e}")
    
    # ── NTUML2021 / ML2021_ASR_ST (Code-switching, oversampled) ──
    try:
        logger.info("Loading NTUML2021 (Offline Parquets)...")
        ntu = load_dataset("parquet", data_dir="whisper_mla/data/ntuml2021/data", split="train")
        ntu = ntu.cast_column("audio", Audio(sampling_rate=16000))
        # Rename 'transcription' → 'text' for consistency with other datasets
        if "transcription" in ntu.column_names and "text" not in ntu.column_names:
            ntu = ntu.rename_column("transcription", "text")
        # Oversample for balance
        ntu_repeated = concatenate_datasets([ntu] * config.cs_oversample_factor)
        all_datasets.append(("ntuml2021", ntu_repeated))
        logger.info(f"  NTUML2021: {len(ntu)} × {config.cs_oversample_factor} = {len(ntu_repeated)} samples")
    except Exception as e:
        logger.warning(f"Failed to load NTUML2021: {e}")
    
    if not all_datasets:
        raise RuntimeError("No datasets loaded successfully!")
    
    # Log dataset composition
    logger.info("Dataset composition:")
    total = sum(len(ds) for _, ds in all_datasets)
    for name, ds in all_datasets:
        logger.info(f"  {name}: {len(ds)} ({len(ds)/total:.1%})")
    
    return all_datasets


def prepare_dataset_fn(processor: WhisperProcessor, language: str = "zh"):
    """Create a preprocessing function for the dataset."""
    
    def prepare_dataset(batch):
        audio = batch["audio"]
        
        # Extract features
        input_features = processor.feature_extractor(
            audio["array"],
            sampling_rate=audio["sampling_rate"],
            return_tensors="pt",
        ).input_features[0]
        
        # Tokenize labels
        text_val = None
        for k in ["text", "sentence", "transcription"]:
            v = batch.get(k)
            if v is not None and isinstance(v, str) and len(v.strip()) > 0:
                text_val = v
                break
                
        if text_val is None:
            raise KeyError(f"Could not find valid text in batch. Available keys/values: {{k: batch[k] for k in ['text', 'sentence', 'transcription'] if k in batch}}")
            
        labels = processor.tokenizer(text_val).input_ids
        
        batch["input_features"] = input_features
        batch["labels"] = labels
        return batch
    
    return prepare_dataset


def compute_metrics_fn(processor: WhisperProcessor, metric_name: str = "cer"):
    """Create metrics computation function."""
    metric = evaluate.load(metric_name)
    
    def compute_metrics(pred):
        pred_ids = pred.predictions
        label_ids = pred.label_ids
        
        # Replace -100 with pad token id
        label_ids[label_ids == -100] = processor.tokenizer.pad_token_id
        
        pred_str = processor.tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
        label_str = processor.tokenizer.batch_decode(label_ids, skip_special_tokens=True)
        
        score = metric.compute(predictions=pred_str, references=label_str)
        return {metric_name: score}
    
    return compute_metrics


def train(
    model_path: str,
    output_dir: str,
    mla_config: Optional[WhisperMLAConfig] = None,
    train_config: Optional[TrainingConfig] = None,
):
    """
    Fine-tune Whisper-MLA model.
    
    Args:
        model_path: Path to SVD-converted model
        output_dir: Where to save fine-tuned model
        mla_config: MLA hyperparameters
        train_config: Training configuration
    """
    if mla_config is None:
        mla_config = WhisperMLAConfig()
    if train_config is None:
        train_config = TrainingConfig()
    
    os.makedirs(output_dir, exist_ok=True)
    
    # ── Load model ──
    logger.info("Loading Whisper-MLA model for fine-tuning...")
    model, _, _ = WhisperMLAModel.from_pretrained(
        model_path,
        device="cuda" if torch.cuda.is_available() else "cpu",
        dtype=torch.float32,  # Full precision for training
    )
    
    processor = WhisperProcessor.from_pretrained(model_path)
    
    # ── Load datasets ──
    all_datasets = load_training_datasets(train_config, processor)
    
    # Combine and shuffle
    combined = concatenate_datasets([ds for _, ds in all_datasets])
    combined = combined.shuffle(seed=42)
    
    # Filter invalid/empty targets
    def has_valid_text(x):
        for k in ["text", "sentence", "transcription"]:
            v = x.get(k)
            if v is not None and isinstance(v, str) and len(v.strip()) > 0:
                return True
        return False
        
    combined = combined.filter(has_valid_text, num_proc=1)

    # Preprocess
    prepare_fn = prepare_dataset_fn(processor, language="zh")
    combined = combined.map(
        prepare_fn,
        remove_columns=combined.column_names,
        num_proc=1,
    )
    
    # ── Training arguments ──
    training_args = Seq2SeqTrainingArguments(
        output_dir=output_dir,
        num_train_epochs=mla_config.num_epochs,
        per_device_train_batch_size=mla_config.per_device_batch_size,
        gradient_accumulation_steps=mla_config.gradient_accumulation_steps,
        learning_rate=mla_config.learning_rate,
        warmup_steps=mla_config.warmup_steps,
        fp16=False,
        bf16=True,  # 使用 BF16 大幅減少記憶體用量且不溢位
        gradient_checkpointing=True,  # 開啟激勵檢查點：用計算換空間
        optim="adamw_bnb_8bit",  # 使用 8-bit 優化器：減少 optimizer states 空間
        logging_steps=train_config.logging_steps,
        save_steps=train_config.save_steps,
        eval_steps=train_config.eval_steps,
        logging_dir=train_config.logging_dir,
        save_total_limit=3,
        predict_with_generate=True,
        generation_max_length=448,
        report_to=["tensorboard"],
        dataloader_num_workers=4,  # Phase 2: 取樣多執行緒，確保資料不會餵不飽 GPU
        tf32=True,  # Phase 2: 啟用 TF32 計算
        torch_compile=False,  # Windows 無法支援原生 Triton 融合，因此必須關閉
        remove_unused_columns=False,
    )
    
    # ── Data collator ──
    data_collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)
    
    # ── Trainer ──
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=combined,
        data_collator=data_collator,
        compute_metrics=compute_metrics_fn(processor, "cer"),
        processing_class=processor.feature_extractor,
    )
    
    # ── Train ──
    logger.info(f"Starting fine-tuning: {mla_config.num_epochs} epochs")
    logger.info(f"  Effective batch size: {mla_config.effective_batch_size}")
    logger.info(f"  Total samples: {len(combined)}")
    
    # Auto-resume from latest checkpoint if one exists
    import glob
    checkpoints = glob.glob(os.path.join(output_dir, "checkpoint-*"))
    resume_from_ckpt = True if checkpoints else False
    if resume_from_ckpt:
        logger.info(f"Found checkpoints in {output_dir}, resuming from latest...")
    
    trainer.train(resume_from_checkpoint=resume_from_ckpt)
    
    # ── Save ──
    trainer.save_model(output_dir)
    processor.save_pretrained(output_dir)
    
    # Copy MLA config
    import shutil
    shutil.copy(
        os.path.join(model_path, "mla_config.json"),
        os.path.join(output_dir, "mla_config.json"),
    )
    
    logger.info(f"Fine-tuned model saved to: {output_dir}")


# ── CLI Entry Point ──
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    
    parser = argparse.ArgumentParser(description="Fine-tune Whisper-MLA")
    parser.add_argument("--model_path", required=True,
                        help="Path to SVD-converted model")
    parser.add_argument("--output_dir", default="./breeze-asr-mla-finetuned",
                        help="Output directory")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch_size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=1e-5)
    args = parser.parse_args()
    
    mla_config = WhisperMLAConfig(
        num_epochs=args.epochs,
        per_device_batch_size=args.batch_size,
        learning_rate=args.lr,
    )
    
    train(args.model_path, args.output_dir, mla_config)
