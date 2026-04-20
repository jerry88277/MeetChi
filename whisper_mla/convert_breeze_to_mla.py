"""
SVD Conversion: Breeze ASR 25 → Whisper-MLA

Converts decoder self-attention layers from MHA to MLA using joint SVD.
No training data required — this is a pure mathematical transformation.

Reference: arXiv:2603.00563 Section 2.3
"""

import os
import math
import logging
from typing import Dict, Tuple, Optional

import torch
import numpy as np
from transformers import WhisperForConditionalGeneration, WhisperProcessor
from safetensors.torch import save_file

from .config import WhisperMLAConfig

logger = logging.getLogger(__name__)


def compute_preserved_mask(config: WhisperMLAConfig) -> torch.Tensor:
    """
    Compute the boolean mask indicating which key dimensions to preserve.
    
    Uses uniform sampling of frequency subspaces as per paper Section 2.1.
    Each head has head_dim/2 frequency subspaces (pairs of sin/cos).
    We select r subspaces per head with geometrically spaced intervals.
    
    Returns:
        Boolean tensor of shape [d_model] where True = preserved dimension
    """
    d_model = config.d_model
    n_heads = config.n_heads
    head_dim = config.head_dim
    r = config.r
    
    preserved_mask = torch.zeros(d_model, dtype=torch.bool)
    subspaces_per_head = head_dim // 2  # 32 for head_dim=64
    
    if config.dim_selection == "uniform":
        # Uniform sampling: geometrically spaced frequency subspaces
        # D_uniform = { floor(k * (d_h / 2r)) | 0 <= k < r }
        indices = []
        for k in range(r):
            idx = int(math.floor(k * subspaces_per_head / r))
            indices.append(idx)
    else:
        raise NotImplementedError(f"2-norm selection requires calibration data")
    
    # Apply to each head
    for h in range(n_heads):
        offset = h * head_dim
        for idx in indices:
            # Each subspace is a pair of consecutive dimensions
            preserved_mask[offset + 2 * idx] = True
            preserved_mask[offset + 2 * idx + 1] = True
    
    n_preserved = preserved_mask.sum().item()
    assert n_preserved == config.d_kp, \
        f"Preserved dims {n_preserved} != expected {config.d_kp}"
    
    logger.info(
        f"Preserved mask: {n_preserved}/{d_model} dims "
        f"({n_preserved/d_model:.1%}), "
        f"{r} subspaces/head, indices={indices}"
    )
    return preserved_mask


def svd_convert_layer(
    W_k: torch.Tensor,
    W_v: torch.Tensor,
    preserved_mask: torch.Tensor,
    d_kv: int,
    b_k: Optional[torch.Tensor] = None,
    b_v: Optional[torch.Tensor] = None,
) -> Dict[str, torch.Tensor]:
    """
    Convert a single attention layer's K/V projections via joint SVD.
    
    Args:
        W_k: Key projection weight [d_model, d_model]
        W_v: Value projection weight [d_model, d_model]
        preserved_mask: Boolean mask [d_model] for preserved key dims
        d_kv: Latent dimension for SVD
        b_k: Optional key bias [d_model]
        b_v: Optional value bias [d_model]
    
    Returns:
        Dict with converted weight matrices:
        - W_kp: Preserved key projection [d_kp, d_model]
        - W_DKV: Down-projection to latent [d_kv, d_model]
        - W_UK: Up-project latent → compressible key [d_kc, d_kv]
        - W_UV: Up-project latent → value [d_model, d_kv]
        - preserved_mask: Boolean mask [d_model]
        - reconstruction_error: Frobenius norm of approximation error
    """
    compressible_mask = ~preserved_mask
    d_model = W_k.shape[0]
    d_kp = preserved_mask.sum().item()
    d_kc = compressible_mask.sum().item()
    
    # Step 1: Split key projection
    # W_k is [out_features, in_features] in nn.Linear convention
    # For Whisper: W_k.weight is [d_model, d_model]
    W_kp = W_k[preserved_mask, :]       # [d_kp, d_model]
    W_kc = W_k[compressible_mask, :]    # [d_kc, d_model]
    
    # Step 2: Concatenate compressible K and V
    # M = [W_kc; W_v] → [d_kc + d_model, d_model]
    M = torch.cat([W_kc, W_v], dim=0).float()  # Use float64 for SVD precision
    
    # Step 3: Joint SVD
    U, S, Vh = torch.linalg.svd(M, full_matrices=False)
    
    # Step 4: Truncate to d_kv
    U_kv = U[:, :d_kv]              # [d_kc + d_model, d_kv]
    S_kv = S[:d_kv]                 # [d_kv]
    Vh_kv = Vh[:d_kv, :]            # [d_kv, d_model]
    
    # Step 5: Compute reconstruction error
    M_approx = U_kv @ torch.diag(S_kv) @ Vh_kv
    error = torch.norm(M - M_approx).item() / torch.norm(M).item()
    
    # Step 6: Construct down/up projection matrices
    S_sqrt = torch.sqrt(S_kv)       # [d_kv]
    
    # Down-projection: input → latent
    # W_DKV = Vh_kv^T @ diag(sqrt(S))  → [d_model, d_kv]
    W_DKV = (Vh_kv.T * S_sqrt.unsqueeze(0))  # [d_model, d_kv]
    
    # Up-projection: latent → outputs
    # Scale U by sqrt(S)
    U_scaled = U_kv * S_sqrt.unsqueeze(0)    # [d_kc + d_model, d_kv]
    
    W_UK = U_scaled[:d_kc, :].T              # [d_kv, d_kc] → for key reconstruction
    W_UV = U_scaled[d_kc:, :].T              # [d_kv, d_model] → for value reconstruction
    
    # Convert back to model precision
    result = {
        "W_kp": W_kp.to(W_k.dtype),                # [d_kp, d_model]
        "W_DKV": W_DKV.to(W_k.dtype).T,            # [d_kv, d_model] → stored as [d_model, d_kv] for nn.Linear
        "W_UK": W_UK.to(W_k.dtype),                 # [d_kv, d_kc]
        "W_UV": W_UV.to(W_k.dtype),                 # [d_kv, d_model]
        "preserved_mask": preserved_mask,
        "reconstruction_error": error,
    }
    
    # Handle biases
    if b_k is not None:
        result["b_kp"] = b_k[preserved_mask]
        # Bias for compressible part is absorbed into up-projection
    if b_v is not None:
        result["b_v"] = b_v
    
    return result


def convert_breeze_to_mla(
    config: Optional[WhisperMLAConfig] = None,
    save_path: Optional[str] = None,
) -> Tuple[Dict, WhisperMLAConfig]:
    """
    Full conversion pipeline: Breeze ASR 25 → Whisper-MLA.
    
    Steps:
    1. Load Breeze ASR 25 model
    2. Compute preserved dimension mask (uniform sampling)
    3. For each decoder self-attention layer: apply joint SVD
    4. Save converted weights + config
    
    Args:
        config: MLA configuration (default: WhisperMLAConfig)
        save_path: Where to save converted model (default: config.output_dir)
    
    Returns:
        Tuple of (converted_weights_dict, config)
    """
    if config is None:
        config = WhisperMLAConfig()
    config.validate()
    
    save_path = save_path or config.output_dir
    os.makedirs(save_path, exist_ok=True)
    
    # ── Step 1: Load source model ──
    logger.info(f"Loading source model: {config.source_model}")
    model = WhisperForConditionalGeneration.from_pretrained(
        config.source_model,
        torch_dtype=torch.float32,  # Full precision for SVD accuracy
    )
    
    # ── Step 2: Compute preserved mask ──
    preserved_mask = compute_preserved_mask(config)
    
    # ── Step 3: Convert each decoder self-attention layer ──
    converted_layers = {}
    errors = []
    
    for layer_idx in range(config.n_decoder_layers):
        attn = model.model.decoder.layers[layer_idx].self_attn
        
        logger.info(f"Converting decoder layer {layer_idx}/{config.n_decoder_layers}...")
        
        result = svd_convert_layer(
            W_k=attn.k_proj.weight.data,
            W_v=attn.v_proj.weight.data,
            preserved_mask=preserved_mask,
            d_kv=config.d_kv,
            b_k=attn.k_proj.bias.data if attn.k_proj.bias is not None else None,
            b_v=attn.v_proj.bias.data if attn.v_proj.bias is not None else None,
        )
        
        converted_layers[layer_idx] = result
        errors.append(result["reconstruction_error"])
        
        logger.info(
            f"  Layer {layer_idx}: reconstruction error = {result['reconstruction_error']:.4f}"
        )
    
    avg_error = sum(errors) / len(errors)
    max_error = max(errors)
    logger.info(
        f"\n{'='*60}\n"
        f"SVD Conversion Complete!\n"
        f"  Layers converted: {config.n_decoder_layers}\n"
        f"  Avg reconstruction error: {avg_error:.4f}\n"
        f"  Max reconstruction error: {max_error:.4f}\n"
        f"  KV cache compression: {config.kv_cache_compression_ratio:.1%}\n"
        f"{'='*60}"
    )
    
    # ── Step 4: Build state dict for saving ──
    state_dict = {}
    
    # Copy all weights from original model
    for name, param in model.state_dict().items():
        # Skip decoder self-attention k_proj and v_proj (replaced by MLA)
        if "decoder.layers" in name and "self_attn" in name:
            if "k_proj" in name or "v_proj" in name:
                continue
        state_dict[name] = param.clone().contiguous()
    
    # Add MLA weights
    for layer_idx, layer_data in converted_layers.items():
        prefix = f"model.decoder.layers.{layer_idx}.self_attn.mla"
        state_dict[f"{prefix}.kp_proj.weight"] = layer_data["W_kp"].contiguous()
        state_dict[f"{prefix}.down_proj.weight"] = layer_data["W_DKV"].contiguous()
        state_dict[f"{prefix}.uk_proj.weight"] = layer_data["W_UK"].contiguous()
        state_dict[f"{prefix}.uv_proj.weight"] = layer_data["W_UV"].contiguous()
        if "b_kp" in layer_data:
            state_dict[f"{prefix}.kp_proj.bias"] = layer_data["b_kp"].contiguous()
        if "b_v" in layer_data:
            state_dict[f"{prefix}.uv_proj.bias"] = layer_data["b_v"].contiguous()
    
    # Save preserved mask
    state_dict["mla_preserved_mask"] = preserved_mask
    
    # ── Step 5: Save ──
    save_file(state_dict, os.path.join(save_path, "model.safetensors"))
    
    # Save processor/tokenizer
    processor = WhisperProcessor.from_pretrained(config.source_model)
    processor.save_pretrained(save_path)
    
    # Save MLA config
    import json
    mla_config = {
        "d_model": config.d_model,
        "n_heads": config.n_heads,
        "head_dim": config.head_dim,
        "n_decoder_layers": config.n_decoder_layers,
        "d_kp": config.d_kp,
        "d_kv": config.d_kv,
        "r": config.r,
        "dim_selection": config.dim_selection,
        "source_model": config.source_model,
        "avg_reconstruction_error": avg_error,
        "max_reconstruction_error": max_error,
        "kv_cache_compression_ratio": config.kv_cache_compression_ratio,
    }
    with open(os.path.join(save_path, "mla_config.json"), "w") as f:
        json.dump(mla_config, f, indent=2)
    
    logger.info(f"Converted model saved to: {save_path}")
    
    return converted_layers, config


# ── CLI Entry Point ──
if __name__ == "__main__":
    import argparse
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    parser = argparse.ArgumentParser(description="Convert Breeze ASR 25 to Whisper-MLA")
    parser.add_argument("--source", default="MediaTek-Research/Breeze-ASR-25",
                        help="Source model name or path")
    parser.add_argument("--output", default="./breeze-asr-mla",
                        help="Output directory for converted model")
    parser.add_argument("--d_kv", type=int, default=160,
                        help="Latent dimension (default: 160)")
    parser.add_argument("--r", type=int, default=2,
                        help="Preserved subspaces per head (default: 2)")
    args = parser.parse_args()
    
    config = WhisperMLAConfig(
        source_model=args.source,
        output_dir=args.output,
        d_kv=args.d_kv,
        r=args.r,
    )
    
    convert_breeze_to_mla(config)
