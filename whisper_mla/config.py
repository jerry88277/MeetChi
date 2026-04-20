"""
Whisper-MLA Configuration

MLA hyperparameters for Whisper-large-v2 (Breeze ASR 25 base).
Derived from Whisper-MLA paper (arXiv:2603.00563) experimental setup
on Whisper-small, scaled proportionally to Whisper-large.

Paper (Whisper-small): d_model=768, d_kp=48 (6.25%), d_kv=96 (12.5%), r=2
Scaled (Whisper-large): d_model=1280, d_kp=80 (6.25%), d_kv=160 (12.5%), r=2
"""

from dataclasses import dataclass, field
from typing import Optional, List


@dataclass
class WhisperMLAConfig:
    """Configuration for MLA conversion of Whisper-large-v2."""

    # ── Model architecture (Whisper-large-v2 / Breeze ASR 25) ──
    d_model: int = 1280
    n_heads: int = 20
    head_dim: int = 64           # d_model / n_heads
    n_encoder_layers: int = 32
    n_decoder_layers: int = 32
    vocab_size: int = 51865

    # ── MLA hyperparameters ──
    # Preserved key dimensions: retain positional info
    # Paper: 6.25% of d_model → Whisper-large: 80
    d_kp: int = 80

    # Latent dimension: shared compressed space for K_c and V
    # Paper: 12.5% of d_model → Whisper-large: 160
    d_kv: int = 160

    # Number of frequency subspaces to preserve per head
    # Paper: r=2 for both small and large (universal)
    r: int = 2

    # Dimension selection strategy: "uniform" or "2norm"
    # Paper: uniform is better for decoder (learnable PE)
    dim_selection: str = "uniform"

    # ── DSO (Decoder Self-attention Only) ──
    # Only modify decoder self-attention; leave encoder & cross-attn unchanged
    apply_to_encoder: bool = False
    apply_to_cross_attn: bool = False

    # ── Source model ──
    source_model: str = "MediaTek-Research/Breeze-ASR-25"
    output_dir: str = "./breeze-asr-mla"

    # ── Training ──
    learning_rate: float = 1e-5
    num_epochs: int = 3
    per_device_batch_size: int = 4
    gradient_accumulation_steps: int = 8
    warmup_steps: int = 500
    max_audio_length: float = 30.0  # seconds
    fp16: bool = True

    @property
    def d_kc(self) -> int:
        """Compressible key dimensions = d_model - d_kp."""
        return self.d_model - self.d_kp

    @property
    def effective_batch_size(self) -> int:
        """Effective batch size with gradient accumulation."""
        return self.per_device_batch_size * self.gradient_accumulation_steps

    @property
    def kv_cache_compression_ratio(self) -> float:
        """KV cache size ratio vs original."""
        original = 2 * self.d_model       # K + V
        mla = self.d_kp + self.d_kv       # K_preserved + latent
        return mla / original

    def validate(self):
        """Validate configuration consistency."""
        assert self.d_model == self.n_heads * self.head_dim, \
            f"d_model ({self.d_model}) != n_heads ({self.n_heads}) * head_dim ({self.head_dim})"
        assert self.d_kp + self.d_kc == self.d_model, \
            f"d_kp ({self.d_kp}) + d_kc ({self.d_kc}) != d_model ({self.d_model})"
        assert self.d_kp == self.n_heads * self.r * 2, \
            f"d_kp ({self.d_kp}) != n_heads ({self.n_heads}) * r ({self.r}) * 2"
        assert self.dim_selection in ("uniform", "2norm"), \
            f"Invalid dim_selection: {self.dim_selection}"
        print(f"✅ Config valid. KV cache compression: {self.kv_cache_compression_ratio:.1%}")


@dataclass
class TrainingConfig:
    """Fine-tune configuration after SVD conversion."""

    # Datasets
    datasets: List[str] = field(default_factory=lambda: [
        "aishell1",                                          # 170hr 中文
        "librispeech_asr:train.clean.360",                   # 360hr 英文
        "librispeech_asr:train.clean.100",                   # 100hr 英文
        "mozilla-foundation/common_voice_17_0:zh-TW",        # 100hr 台灣
        "ky552/ML2021_ASR_ST",                                # ~9hr CS (NTU ML2021)
    ])

    # Code-switching oversampling factor
    cs_oversample_factor: int = 5

    # Validation
    val_datasets: List[str] = field(default_factory=lambda: [
        "mozilla-foundation/common_voice_17_0:zh-TW:test",  # 台灣口音
        "librispeech_asr:test.clean",                        # 英文
    ])

    # Acceptance criteria (max error rate increase vs Breeze baseline)
    max_cer_increase_zh: float = 0.01   # ≤ +1%
    max_wer_increase_en: float = 0.01   # ≤ +1%
    max_mer_increase_cs: float = 0.02   # ≤ +2%

    # Output
    output_dir: str = "./breeze-asr-mla-finetuned"
    logging_dir: str = "./logs"
    save_steps: int = 200
    eval_steps: int = 200
    logging_steps: int = 20
