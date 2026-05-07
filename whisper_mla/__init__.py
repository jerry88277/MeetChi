"""
Whisper-MLA: Multi-Head Latent Attention for Breeze ASR 25

Converts Breeze ASR 25 (Whisper-large-v2 based) to use MLA in decoder
self-attention, reducing KV cache by ~90% and enabling high concurrency.

Architecture: DSO (Decoder Self-attention Only)
Reference: arXiv:2603.00563 (Whisper-MLA), arXiv:2502.14837 (MHA2MLA)
"""
