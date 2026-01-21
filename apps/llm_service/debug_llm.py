import torch
from transformers import AutoModel, AutoTokenizer
import traceback
import os

# Force usage of the specific snapshot we inspected to be sure
# model_path = "MediaTek-Research/Llama-Breeze2-3B-Instruct"

# Or assume standard loading
model_path = "MediaTek-Research/Llama-Breeze2-3B-Instruct"

print(f"Attempting to load model from: {model_path}")
try:
    model = AutoModel.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        device_map="cuda" if torch.cuda.is_available() else "cpu"
    )
    print("Model loaded successfully!")
except Exception:
    print("!!! Failed to load model !!!")
    traceback.print_exc()
