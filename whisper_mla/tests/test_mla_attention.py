"""Tests for MLA Attention module."""

import sys
import os
import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from whisper_mla.config import WhisperMLAConfig
from whisper_mla.convert_breeze_to_mla import compute_preserved_mask
from whisper_mla.modeling_whisper_mla import WhisperMLAAttention, WhisperMLACache


class TestWhisperMLAAttention:
    """Test MLA attention forward pass."""
    
    @pytest.fixture
    def mla_attention(self):
        config = WhisperMLAConfig()
        mask = compute_preserved_mask(config)
        attn = WhisperMLAAttention(
            d_model=config.d_model,
            n_heads=config.n_heads,
            d_kp=config.d_kp,
            d_kv=config.d_kv,
            preserved_mask=mask,
        )
        return attn
    
    def test_forward_shape(self, mla_attention):
        """Output shape should match input."""
        bsz, seq_len = 2, 10
        x = torch.randn(bsz, seq_len, 1280)
        
        output, _ = mla_attention(x)
        assert output.shape == (bsz, seq_len, 1280)
    
    def test_forward_with_cache(self, mla_attention):
        """Test autoregressive generation with cache."""
        bsz = 1
        cache = WhisperMLACache(n_layers=32)
        
        # First token
        x1 = torch.randn(bsz, 1, 1280)
        out1, cache = mla_attention(x1, layer_idx=0, cache=cache)
        assert out1.shape == (bsz, 1, 1280)
        assert cache.seq_length == 1
        
        # Second token
        x2 = torch.randn(bsz, 1, 1280)
        out2, cache = mla_attention(x2, layer_idx=0, cache=cache)
        assert out2.shape == (bsz, 1, 1280)
        assert cache.seq_length == 2
    
    def test_cache_memory_reduction(self, mla_attention):
        """Cache should use significantly less memory than full K/V."""
        bsz = 4
        seq_len = 100
        cache = WhisperMLACache(n_layers=32)
        
        x = torch.randn(bsz, seq_len, 1280)
        _, cache = mla_attention(x, layer_idx=0, cache=cache)
        
        # MLA cache for 1 layer
        mla_bytes = cache.get_memory_bytes()
        
        # Original KV cache: 2 * bsz * seq_len * d_model * sizeof(float32)
        original_bytes = 2 * bsz * seq_len * 1280 * 4
        
        ratio = mla_bytes / original_bytes
        assert ratio < 0.15  # Should be ~9.375%


class TestWhisperMLACache:
    """Test compressed KV cache behavior."""
    
    def test_empty_cache(self):
        cache = WhisperMLACache(n_layers=32)
        assert cache.seq_length == 0
        assert cache.get(0) is None
    
    def test_cache_update(self):
        cache = WhisperMLACache(n_layers=32)
        
        kp = torch.randn(1, 5, 80)
        ckv = torch.randn(1, 5, 160)
        
        kp_out, ckv_out = cache.update(0, kp, ckv)
        assert kp_out.shape == (1, 5, 80)
        assert ckv_out.shape == (1, 5, 160)
        assert cache.seq_length == 5
    
    def test_cache_accumulation(self):
        cache = WhisperMLACache(n_layers=32)
        
        # Add 3 tokens
        for i in range(3):
            kp = torch.randn(1, 1, 80)
            ckv = torch.randn(1, 1, 160)
            cache.update(0, kp, ckv)
        
        assert cache.seq_length == 3
    
    def test_cache_clear(self):
        cache = WhisperMLACache(n_layers=32)
        cache.update(0, torch.randn(1, 5, 80), torch.randn(1, 5, 160))
        cache.clear()
        assert cache.seq_length == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
