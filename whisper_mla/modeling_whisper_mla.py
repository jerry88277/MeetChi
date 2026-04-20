"""
Whisper-MLA Model Architecture

Custom WhisperMLAAttention module that replaces standard MHA in
decoder self-attention with Multi-Head Latent Attention (MLA).

Only decoder self-attention is modified (DSO configuration).
Encoder self-attention and cross-attention remain unchanged.

KV Cache stores (K_preserved, c_kv) instead of full (K, V):
  Original: 2 × d_model = 2 × 1280 = 2560 per token
  MLA:      d_kp + d_kv  = 80 + 160 = 240 per token
  Compression: 90.6%

Reference: arXiv:2603.00563 Section 2.1-2.2
"""

import math
import json
import os
import logging
from typing import Optional, Tuple, Dict

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from safetensors.torch import load_file

from .config import WhisperMLAConfig

logger = logging.getLogger(__name__)


class WhisperMLACache:
    """
    Compressed KV Cache for Whisper-MLA.
    
    Instead of storing full K [bsz, n_heads, seq, head_dim] and V [same],
    we store:
      - K_preserved: [bsz, seq, d_kp]  (positional info)
      - c_kv:        [bsz, seq, d_kv]  (latent representation)
    
    Full K and V are reconstructed on-the-fly during attention computation.
    """
    
    def __init__(self, n_layers: int):
        self.n_layers = n_layers
        self._cache: Dict[int, Tuple[torch.Tensor, torch.Tensor]] = {}
    
    def get(self, layer_idx: int) -> Optional[Tuple[torch.Tensor, torch.Tensor]]:
        return self._cache.get(layer_idx, None)
    
    def update(
        self,
        layer_idx: int,
        k_preserved: torch.Tensor,
        c_kv: torch.Tensor,
    ) -> Tuple[torch.Tensor, torch.Tensor]:
        """Append new tokens to cache and return updated cache."""
        if layer_idx in self._cache:
            past_kp, past_ckv = self._cache[layer_idx]
            k_preserved = torch.cat([past_kp, k_preserved], dim=1)
            c_kv = torch.cat([past_ckv, c_kv], dim=1)
        
        self._cache[layer_idx] = (k_preserved, c_kv)
        return k_preserved, c_kv
    
    def clear(self):
        self._cache.clear()
    
    @property
    def seq_length(self) -> int:
        if not self._cache:
            return 0
        first = next(iter(self._cache.values()))
        return first[0].shape[1]
    
    def get_memory_bytes(self) -> int:
        total = 0
        for kp, ckv in self._cache.values():
            total += kp.nelement() * kp.element_size()
            total += ckv.nelement() * ckv.element_size()
        return total


class WhisperMLAAttention(nn.Module):
    """
    Multi-Head Latent Attention for Whisper decoder self-attention.
    
    Replaces standard MHA with compressed KV cache:
    1. Query projection: unchanged (W_q)
    2. Preserved key: W_kp extracts positional dimensions
    3. Down-projection: W_DKV compresses input to latent space
    4. Up-projections: W_UK (key) and W_UV (value) reconstruct from latent
    5. Output projection: unchanged (W_out)
    """
    
    def __init__(
        self,
        d_model: int,
        n_heads: int,
        d_kp: int,
        d_kv: int,
        preserved_mask: torch.Tensor,
    ):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.d_kp = d_kp
        self.d_kv = d_kv
        self.d_kc = d_model - d_kp
        self.scale = self.head_dim ** -0.5
        
        # Register preserved mask as buffer (not a parameter)
        self.register_buffer("preserved_mask", preserved_mask)
        self.register_buffer("compressible_mask", ~preserved_mask)
        
        # Query: unchanged from original Whisper
        self.q_proj = nn.Linear(d_model, d_model)
        
        # Preserved key: extracts position-critical dimensions
        self.kp_proj = nn.Linear(d_model, d_kp, bias=False)
        
        # Down-projection: input → shared latent space
        self.down_proj = nn.Linear(d_model, d_kv, bias=False)
        
        # Up-projections: latent → reconstructed key/value
        self.uk_proj = nn.Linear(d_kv, self.d_kc, bias=False)
        self.uv_proj = nn.Linear(d_kv, d_model, bias=True)  # bias for value
        
        # Output: unchanged from original Whisper
        self.out_proj = nn.Linear(d_model, d_model)
    
    def forward(
        self,
        hidden_states: torch.Tensor,
        key_value_states: Optional[torch.Tensor] = None,
        past_key_value: Optional[Tuple[torch.Tensor]] = None,
        attention_mask: Optional[torch.Tensor] = None,
        output_attentions: bool = False,
        cache: Optional[WhisperMLACache] = None,
        layer_idx: int = 0,
        **kwargs,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Forward pass with compressed KV cache.
        
        Args:
            hidden_states: [batch, seq_len, d_model]
            attention_mask: [batch, 1, seq_len, full_seq_len]
            layer_idx: Layer index for cache
            cache: WhisperMLACache
            
        Returns:
            (output, cache)
        """
        bsz, tgt_len, _ = hidden_states.size()
        
        # ── Query (unchanged) ──
        Q = self.q_proj(hidden_states)  # [bsz, tgt_len, d_model]
        
        # ── MLA: Compress K/V ──
        # Preserved key (position info)
        k_preserved = self.kp_proj(hidden_states)  # [bsz, tgt_len, d_kp]
        
        # Latent vector (shared representation)
        c_kv = self.down_proj(hidden_states)        # [bsz, tgt_len, d_kv]
        
        # ── Update cache ──
        if cache is not None:
            k_preserved, c_kv = cache.update(layer_idx, k_preserved, c_kv)
        
        full_seq_len = k_preserved.size(1)
        
        # ── On-the-fly reconstruction ──
        # Reconstruct compressible key from latent
        k_compressed = self.uk_proj(c_kv)  # [bsz, full_seq_len, d_kc]
        
        # Reconstruct value from latent
        V = self.uv_proj(c_kv)             # [bsz, full_seq_len, d_model]
        
        K = torch.zeros(
            bsz, full_seq_len, self.d_model,
            device=hidden_states.device, dtype=k_preserved.dtype,
        )
        K[:, :, self.preserved_mask] = k_preserved
        K[:, :, self.compressible_mask] = k_compressed
        
        # ── Standard multi-head attention (Using Flash Attention) ──
        Q = Q.view(bsz, tgt_len, self.n_heads, self.head_dim).transpose(1, 2).contiguous()
        K = K.view(bsz, full_seq_len, self.n_heads, self.head_dim).transpose(1, 2).contiguous()
        V = V.view(bsz, full_seq_len, self.n_heads, self.head_dim).transpose(1, 2).contiguous()
        
        # 使用 PyTorch 原生 SDPA 以觸發 Flash Attention 機制 (大幅節省長音檔的 VRAM)
        attn_output = F.scaled_dot_product_attention(
            Q, K, V,
            attn_mask=attention_mask,
            dropout_p=0.0,
            is_causal=False  # 因 Whisper 原本就會將因果遮罩 (Causal Mask) 傳入 attention_mask 中
        )
        
        attn_output = attn_output.transpose(1, 2).contiguous().view(bsz, tgt_len, self.d_model)
        
        # Output projection
        attn_output = self.out_proj(attn_output)
        
        return attn_output, None


class WhisperMLAModel:
    """
    Wrapper that loads a Whisper model and replaces decoder self-attention
    with MLA modules using pre-converted weights.
    """
    
    @staticmethod
    def from_pretrained(
        model_path: str,
        device: str = "cuda",
        dtype: torch.dtype = torch.float16,
        use_fused_inference: bool = False,
    ) -> Tuple[WhisperForConditionalGeneration, WhisperMLAConfig, torch.Tensor]:
        """
        Load a Whisper-MLA model from converted checkpoint.
        
        Args:
            model_path: Path to converted model directory
            device: Target device
            dtype: Model dtype
            use_fused_inference: If True, folds weights and applies Fused MLA operator.
            
        Returns:
            (model, config, preserved_mask)
        """
        # Load MLA config
        config_path = os.path.join(model_path, "mla_config.json")
        with open(config_path) as f:
            mla_config_dict = json.load(f)
        
        mla_config = WhisperMLAConfig(**{
            k: v for k, v in mla_config_dict.items()
            if k in WhisperMLAConfig.__dataclass_fields__
        })
        
        logger.info(f"Loading Whisper-MLA from {model_path}")
        logger.info(f"  d_kp={mla_config.d_kp}, d_kv={mla_config.d_kv}, "
                     f"compression={mla_config.kv_cache_compression_ratio:.1%}")
        
        # Load state dict
        state_dict = load_file(os.path.join(model_path, "model.safetensors"))
        preserved_mask = state_dict.pop("mla_preserved_mask", None)
        if preserved_mask is None:
            from .convert_breeze_to_mla import compute_preserved_mask
            preserved_mask = compute_preserved_mask(mla_config)
        
        # Load base Whisper model structure
        model = WhisperForConditionalGeneration.from_pretrained(
            mla_config.source_model,
            torch_dtype=dtype,
        )
        
        if use_fused_inference:
            from .fused_mla import convert_mla_to_fused, WhisperMLAFusedAttention
            logger.info("Converting MLA weights to Fused MLA weights on the fly for inference...")
            fused_state_dict = convert_mla_to_fused(
                state_dict, mla_config.d_model, mla_config.n_heads, 
                mla_config.d_kp, mla_config.d_kv, preserved_mask
            )
            
        # Replace decoder self-attention with MLA
        for layer_idx in range(mla_config.n_decoder_layers):
            layer = model.model.decoder.layers[layer_idx]
            
            if use_fused_inference:
                from .fused_mla import WhisperMLAFusedAttention
                mla_attn = WhisperMLAFusedAttention(
                    d_model=mla_config.d_model,
                    n_heads=mla_config.n_heads,
                    d_kp=mla_config.d_kp,
                    d_kv=mla_config.d_kv,
                ).to(dtype)
                
                prefix = f"model.decoder.layers.{layer_idx}.self_attn"
                mla_attn.fused_q_proj.weight.data = fused_state_dict[f"{prefix}.fused_q_proj.weight"].to(dtype)
                if f"{prefix}.fused_q_proj.bias" in fused_state_dict:
                    mla_attn.fused_q_proj.bias.data = fused_state_dict[f"{prefix}.fused_q_proj.bias"].to(dtype)
                    
                mla_attn.kp_proj.weight.data = fused_state_dict[f"{prefix}.kp_proj.weight"].to(dtype)
                if f"{prefix}.kp_proj.bias" in fused_state_dict:
                    mla_attn.kp_proj.bias.data = fused_state_dict[f"{prefix}.kp_proj.bias"].to(dtype)
                    
                mla_attn.down_proj.weight.data = fused_state_dict[f"{prefix}.down_proj.weight"].to(dtype)
                if f"{prefix}.down_proj.bias" in fused_state_dict:
                    mla_attn.down_proj.bias.data = fused_state_dict[f"{prefix}.down_proj.bias"].to(dtype)
                    
                mla_attn.fused_out_proj.weight.data = fused_state_dict[f"{prefix}.fused_out_proj.weight"].to(dtype)
                if f"{prefix}.fused_out_proj.bias" in fused_state_dict:
                    mla_attn.fused_out_proj.bias.data = fused_state_dict[f"{prefix}.fused_out_proj.bias"].to(dtype)
                
                layer.self_attn = mla_attn
            else:
                # Create Standard Unfused MLA attention module
                mla_attn = WhisperMLAAttention(
                    d_model=mla_config.d_model,
                    n_heads=mla_config.n_heads,
                    d_kp=mla_config.d_kp,
                    d_kv=mla_config.d_kv,
                    preserved_mask=preserved_mask,
                ).to(dtype)
                
                # Load converted weights
                prefix = f"model.decoder.layers.{layer_idx}.self_attn"
                if f"{prefix}.mla.kp_proj.weight" in state_dict:
                    prefix = f"{prefix}.mla"
                
                mla_attn.kp_proj.weight.data = state_dict[f"{prefix}.kp_proj.weight"].to(dtype)
                mla_attn.down_proj.weight.data = state_dict[f"{prefix}.down_proj.weight"].to(dtype)
                mla_attn.uk_proj.weight.data = state_dict[f"{prefix}.uk_proj.weight"].to(dtype)
                mla_attn.uv_proj.weight.data = state_dict[f"{prefix}.uv_proj.weight"].to(dtype)
                if f"{prefix}.kp_proj.bias" in state_dict:
                    mla_attn.kp_proj.bias = nn.Parameter(state_dict[f"{prefix}.kp_proj.bias"].to(dtype))
                if f"{prefix}.uv_proj.bias" in state_dict:
                    mla_attn.uv_proj.bias.data = state_dict[f"{prefix}.uv_proj.bias"].to(dtype)
                
                # Copy q_proj and out_proj from original state dict
                q_key = f"model.decoder.layers.{layer_idx}.self_attn.q_proj"
                out_key = f"model.decoder.layers.{layer_idx}.self_attn.out_proj"
                mla_attn.q_proj.weight.data = state_dict[f"{q_key}.weight"].to(dtype)
                if f"{q_key}.bias" in state_dict:
                    mla_attn.q_proj.bias.data = state_dict[f"{q_key}.bias"].to(dtype)
                mla_attn.out_proj.weight.data = state_dict[f"{out_key}.weight"].to(dtype)
                if f"{out_key}.bias" in state_dict:
                    mla_attn.out_proj.bias.data = state_dict[f"{out_key}.bias"].to(dtype)
                
                # Replace the self_attn module
                layer.self_attn = mla_attn
            
        model = model.to(device)
        logger.info(f"Whisper-MLA model loaded successfully ({device}, {dtype}, fused={use_fused_inference})")
        
        return model, mla_config, preserved_mask
