import torch
import time
import os
import sys
from transformers import AutoProcessor
sys.path.append(".")
from modeling_whisper_mla import WhisperMLAModel

def run_test():
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}")
    
    # Check if checkpoint exists
    ckpt_path = "./breeze-asr-mla-finetuned"
    if not os.path.exists(ckpt_path):
        print(f"Error: Could not find fine-tuned model at {ckpt_path}")
        return

    processor = AutoProcessor.from_pretrained("MediaTek-Research/Breeze-ASR-25")
    
    print("Loading Standard MHA / Unfused MLA model...")
    # NOTE: To test actual memory, we need to generate on a long sequence
    dummy_audio = torch.randn(1, 128, 3000).to(device, dtype=torch.float16)
    
    # 1. Test Fused MLA
    print("====== Loading FUSED MLA MODEL ======")
    model_fused, config_fused, _ = WhisperMLAModel.from_pretrained(
        ckpt_path,
        device=device,
        dtype=torch.float16,
        use_fused_inference=True
    )
    
    start_time = time.time()
    with torch.no_grad():
        out_fused = model_fused.generate(
            dummy_audio,
            max_new_tokens=50,
            language="zh",
            task="transcribe"
        )
    fused_time = time.time() - start_time
    print(f"Fused Generation Time: {fused_time:.2f}s")
    
    # Free memory
    del model_fused
    torch.cuda.empty_cache()
    
    # 2. Test Unfused MLA
    print("====== Loading UNFUSED MLA MODEL ======")
    model_unfused, config_unfused, _ = WhisperMLAModel.from_pretrained(
        ckpt_path,
        device=device,
        dtype=torch.float16,
        use_fused_inference=False
    )
    
    start_time = time.time()
    with torch.no_grad():
        out_unfused = model_unfused.generate(
            dummy_audio,
            max_new_tokens=50,
            language="zh",
            task="transcribe"
        )
    unfused_time = time.time() - start_time
    print(f"Unfused Generation Time: {unfused_time:.2f}s")

    print("\n====== RESULTS ======")
    print("Fused Output vs Unfused Output Identical?:", torch.equal(out_fused, out_unfused))
    print(f"Unfused time: {unfused_time:.2f}s")
    print(f"Fused time:   {fused_time:.2f}s")

if __name__ == "__main__":
    run_test()
