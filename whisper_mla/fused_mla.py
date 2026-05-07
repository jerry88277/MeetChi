import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Optional, Tuple, Dict
from transformers import WhisperForConditionalGeneration

class WhisperMLAFusedCache:
    """
    Paged / Storage-Optimized KV Cache for Fused Whisper MLA.
    Stores only k_preserved (dim=80) and c_kv (dim=160).
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
        if layer_idx in self._cache:
            past_kp, past_ckv = self._cache[layer_idx]
            k_preserved = torch.cat([past_kp, k_preserved], dim=1)
            c_kv = torch.cat([past_ckv, c_kv], dim=1)
        self._cache[layer_idx] = (k_preserved, c_kv)
        return k_preserved, c_kv


class WhisperMLAFusedAttention(nn.Module):
    """
    Fused Multi-Head Latent Attention for Inference.
    Absorbs uk_proj into q_proj and uv_proj into out_proj to avoid
    reconstructing full-dimension K and V.
    """
    def __init__(
        self,
        d_model: int,
        n_heads: int,
        d_kp: int,
        d_kv: int,
    ):
        super().__init__()
        self.d_model = d_model
        self.n_heads = n_heads
        self.head_dim = d_model // n_heads
        self.d_kp_per_head = d_kp // n_heads
        self.d_kv = d_kv
        
        # New fused attention head dimension: d_kp_per_head + d_kv (e.g. 4 + 160 = 164)
        self.fused_head_dim = self.d_kp_per_head + self.d_kv
        self.scale = self.head_dim ** -0.5
        
        # Fused Query Projection
        # Output shape is [n_heads, fused_head_dim] = [20, 164] -> total out_features = 3280
        self.fused_q_proj = nn.Linear(d_model, n_heads * self.fused_head_dim)
        
        # Preserved Key parameter extracting (for the standard token inputs, though usually stored in cache)
        self.kp_proj = nn.Linear(d_model, d_kp, bias=False)
        self.down_proj = nn.Linear(d_model, d_kv, bias=False)
        
        # Fused Output Projection
        # We compute n_heads * d_kv outputs from attention (20 * 160 = 3200)
        self.fused_out_proj = nn.Linear(n_heads * d_kv, d_model)
        
    def forward(
        self,
        hidden_states: torch.Tensor,
        key_value_states: Optional[torch.Tensor] = None,
        past_key_value: Optional[Tuple[torch.Tensor]] = None,
        attention_mask: Optional[torch.Tensor] = None,
        layer_head_mask: Optional[torch.Tensor] = None,
        output_attentions: bool = False,
        **kwargs,
    ) -> Tuple[torch.Tensor, Optional[torch.Tensor], Optional[Tuple[torch.Tensor]]]:
        
        bsz, tgt_len, _ = hidden_states.size()
        
        # 1. Compute Preserved Key and Latent KV
        k_preserved = self.kp_proj(hidden_states)  # [bsz, tgt_len, d_kp]
        c_kv = self.down_proj(hidden_states)       # [bsz, tgt_len, d_kv]
        
        # Reshape to HF cache shape format: [bsz, 1, seq_len, dim] so dim=2 is seq_len 
        k_preserved_st = k_preserved.unsqueeze(1)  # [bsz, 1, tgt_len, d_kp]
        c_kv_st = c_kv.unsqueeze(1)               # [bsz, 1, tgt_len, d_kv]
        
        if past_key_value is not None:
            past_kp, past_ckv = past_key_value
            k_preserved_st = torch.cat([past_kp, k_preserved_st], dim=2)
            c_kv_st = torch.cat([past_ckv, c_kv_st], dim=2)
            
        new_past_key_value = (k_preserved_st, c_kv_st)
        
        # Squeeze back for math
        k_preserved_full = k_preserved_st.squeeze(1) # [bsz, full_seq, d_kp]
        c_kv_full = c_kv_st.squeeze(1)               # [bsz, full_seq, d_kv]
        full_seq_len = k_preserved_full.size(1)
        
        # 2. Compute Fused Query
        Q = self.fused_q_proj(hidden_states)  # [bsz, tgt_len, n_heads * fused_head_dim]
        Q = Q.view(bsz, tgt_len, self.n_heads, self.fused_head_dim).transpose(1, 2)
        # Q is now [bsz, n_heads, tgt_len, fused_head_dim]
        
        # 3. Construct K on-the-fly for attention (broadcasting c_kv)
        # k_preserved: [bsz, full_seq, d_kp] -> [bsz, n_heads, full_seq, d_kp_per_head] -> transposes to [bsz, n_heads, full_seq, d_kp_per_head]
        k_pres_reshaped = k_preserved_full.view(bsz, full_seq_len, self.n_heads, self.d_kp_per_head).transpose(1, 2)
        
        # c_kv needs to be broadcast to all heads: [bsz, 1, full_seq, d_kv] expanded to [bsz, n_heads, full_seq, d_kv]
        c_kv_expanded = c_kv_full.unsqueeze(1).expand(bsz, self.n_heads, full_seq_len, self.d_kv)
        
        # K is now conceptually [bsz, n_heads, full_seq, fused_head_dim]
        K = torch.cat([k_pres_reshaped, c_kv_expanded], dim=-1)
        
        # 4. Attention
        attn_weights = torch.matmul(Q, K.transpose(-1, -2)) * self.scale
        if attention_mask is not None:
            # We assume attention mask supports broadcasting to [bsz, n_heads, tgt_len, seq_len]
            attn_weights = attn_weights + attention_mask
            
        attn_weights = F.softmax(attn_weights, dim=-1, dtype=torch.float32).to(Q.dtype)
        
        # 5. Multiply with Latent Value
        # V is conceptually c_kv for all heads! [bsz, n_heads, full_seq, d_kv]
        # output will be [bsz, n_heads, tgt_len, d_kv]
        attn_output = torch.matmul(attn_weights, c_kv_expanded)
        
        # 6. Fused Output Projection
        # Flatten back: [bsz, tgt_len, n_heads * d_kv]
        attn_output = attn_output.transpose(1, 2).contiguous().view(bsz, tgt_len, self.n_heads * self.d_kv)
        
        attn_output = self.fused_out_proj(attn_output)
        
        return attn_output, None, new_past_key_value


def convert_mla_to_fused(unfused_model_dict: dict, d_model=1280, n_heads=20, d_kp=80, d_kv=160, preserved_mask=None) -> dict:
    """
    Converts generic MLA weights to Fused MLA weights.
    Applies the mathematical folding offline.
    """
    fused_dict = {}
    head_dim = d_model // n_heads
    d_kp_per_head = d_kp // n_heads
    d_kc_per_head = head_dim - d_kp_per_head
    
    # We find all attention layers
    layers = set()
    for k in unfused_model_dict.keys():
        if "model.decoder.layers." in k and ".self_attn" in k:
            layer_idx = k.split(".")[3]
            layers.add(layer_idx)
            
    for l in layers:
        prefix = f"model.decoder.layers.{l}.self_attn"
        mla_prefix = f"{prefix}.mla"
        
        # Q_proj: [d_model, d_model]
        wq = unfused_model_dict[f"{prefix}.q_proj.weight"]
        bq_opt = unfused_model_dict.get(f"{prefix}.q_proj.bias", None)
        
        # UK_proj: [d_kc, d_kv] -> [1200, 160] (transposed locally in original code? No, in state dict it's [160, 1200] because of .t() trick! wait)
        # In original loaded state dict, uk_proj was shape [160, 1200], down_proj [160, 1280]
        # Let's assume unfused_model_dict is directly the raw checkpoint loaded from breeze-asr-mla!!
        w_uk = unfused_model_dict[f"{mla_prefix}.uk_proj.weight"] # Expected: [160, 1200]
        
        # In actual Linear, weight is [out_features, in_features]
        # Our `W_uk` in math was out=1200, in=160. So PyTorch linear shape is [1200, 160].
        # If the safetensors had [160, 1200], it must be transposed to [1200, 160] to represent out x in!
        if w_uk.shape == (160, 1200):
            w_uk = w_uk.t() # Now [1200, 160]
            
        w_uv = unfused_model_dict[f"{mla_prefix}.uv_proj.weight"] # Expected: [160, 1280]
        if w_uv.shape == (160, 1280):
            w_uv = w_uv.t() # Now [1280, 160]
            
        b_uv = unfused_model_dict.get(f"{mla_prefix}.uv_proj.bias", torch.zeros(1280))
        
        w_out = unfused_model_dict[f"{prefix}.out_proj.weight"] # [1280, 1280]
        b_out = unfused_model_dict.get(f"{prefix}.out_proj.bias", torch.zeros(1280))
        
        w_kp = unfused_model_dict[f"{mla_prefix}.kp_proj.weight"] # [80, 1280]
        w_down = unfused_model_dict[f"{mla_prefix}.down_proj.weight"] # [160, 1280]
        
        # 1. Fuse Q
        # wq: [1280, 1280]. Reshape to [20, 64, 1280]
        wq_heads = wq.view(n_heads, head_dim, d_model)
        # Split wq into preserved and compressible Parts using masks!
        # wait! In normal implementation, mask drops down to per-head level!
        # preserved_mask is 1D bool tensor of 1280 elements.
        pm_head = preserved_mask[:head_dim] # assume structural uniformity! [4 True, 60 False]
        wq_pres = wq_heads[:, pm_head, :] # [20, 4, 1280]
        wq_comp = wq_heads[:, ~pm_head, :] # [20, 60, 1280]
        
        # w_uk is [1200, 160]. Reshape to [20, 60, 160].
        # We need to project Q_comp using W_uk. 
        # w_uk_heads = w_uk.view(n_heads, d_kc_per_head, d_kv) -> [20, 60, 160]
        w_uk_heads = w_uk.view(n_heads, d_kc_per_head, d_kv)
        
        # w_fused_q_comp = w_uk^T @ w_q_comp
        # For each head: [160, 60] @ [60, 1280] -> [160, 1280]
        w_fused_q_comp = torch.bmm(w_uk_heads.transpose(1, 2), wq_comp) # [20, 160, 1280]
        
        # Concat wq_pres and w_fused_q_comp -> [20, 164, 1280]
        w_fused_q = torch.cat([wq_pres, w_fused_q_comp], dim=1) # [20, 164, 1280]
        fused_dict[f"model.decoder.layers.{l}.self_attn.fused_q_proj.weight"] = w_fused_q.view(n_heads * 164, d_model)
        
        if bq_opt is not None:
            bq_heads = bq_opt.view(n_heads, head_dim)
            bq_pres = bq_heads[:, pm_head] # [20, 4]
            bq_comp = bq_heads[:, ~pm_head] # [20, 60]
            # [20, 160, 60] @ [20, 60, 1] -> [20, 160, 1]
            b_fused_q_comp = torch.bmm(w_uk_heads.transpose(1, 2), bq_comp.unsqueeze(2)).squeeze(2) # [20, 160]
            b_fused_q = torch.cat([bq_pres, b_fused_q_comp], dim=1) # [20, 164]
            fused_dict[f"model.decoder.layers.{l}.self_attn.fused_q_proj.bias"] = b_fused_q.view(n_heads * 164)
            
        # 2. Key preservations
        fused_dict[f"model.decoder.layers.{l}.self_attn.kp_proj.weight"] = w_kp
        fused_dict[f"model.decoder.layers.{l}.self_attn.down_proj.weight"] = w_down
        
        # 3. Fuse Value & Output
        # output is \sum_h (A_h \cdot C_kv) \cdot W_{uv, h}^T \cdot W_{out, h}^T
        # w_uv: [1280, 160]. Reshape -> [20, 64, 160]
        w_uv_heads = w_uv.view(n_heads, head_dim, d_kv)
        
        # w_out: [1280, 1280]. It takes in 1280 from concatenated heads.
        # So w_out applies to [bsz, seq, 1280]. Let's view conceptually as block sum.
        # W_out * [V_1, V_2, ...]. The weight is [out_features, in_features] = [1280, 1280].
        # The input features are partitioned by head:
        w_out_heads = w_out.view(d_model, n_heads, head_dim).transpose(0, 1) # [20, 1280, 64]
        
        # We want W_fused_out_h = W_out_h @ W_uv_h
        # [1280, 64] @ [64, 160] -> [20, 1280, 160]
        w_fused_out_heads = torch.bmm(w_out_heads, w_uv_heads) 
        
        # Collapse back to linear weight shape [d_model, n_heads * d_kv]
        # We need [1280, 20, 160], then reshape to [1280, 3200]
        w_fused_out = w_fused_out_heads.transpose(0, 1).contiguous().view(d_model, n_heads * d_kv)
        
        fused_dict[f"model.decoder.layers.{l}.self_attn.fused_out_proj.weight"] = w_fused_out
        
        # Biases: b_out + W_out @ b_uv
        # b_uv: [1280].
        b_fused_out = b_out + (w_out @ b_uv)
        fused_dict[f"model.decoder.layers.{l}.self_attn.fused_out_proj.bias"] = b_fused_out

    return fused_dict

