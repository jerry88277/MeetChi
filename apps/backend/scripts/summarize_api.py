from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from transformers import AutoModel, AutoTokenizer, GenerationConfig
import torch
import os
from huggingface_hub import login
import re
import unicodedata

# Import custom prompt engine
from mtkresearch.llm.prompt import MRPromptV3 # New import

app = FastAPI()

# --- Hugging Face Login (for models requiring authentication) ---
HF_TOKEN = os.getenv("HF_TOKEN")
if not HF_TOKEN:
    # Fallback or raise error. Ideally raise error in production.
    # For now, let's just log a warning if possible, or raise.
    # Given this is a script, raising is better.
    print("Warning: HF_TOKEN not set. Some features may not work.")
    HF_TOKEN = "" 

login(token=HF_TOKEN)

# --- Model and Tokenizer Initialization ---
model = None
tokenizer = None
device = "cpu"

try:
    model_id = "MediaTek-Research/Llama-Breeze2-8B-Instruct-v0_1" # Updated model ID
    device = "cuda" if torch.cuda.is_available() else "cpu"

    if device == "cpu":
        print("WARNING: CUDA is not available. Running on CPU will be very slow.")
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is not available. This service is optimized for GPU. Running on CPU will be extremely slow and might not work with current quantization settings.")

    # Load tokenizer with trust_remote_code and use_fast=False
    tokenizer = AutoTokenizer.from_pretrained(model_id, trust_remote_code=True, use_fast=False)
    
    # Load model with specific parameters from user's code
    model = AutoModel.from_pretrained(
        model_id,
        torch_dtype=torch.bfloat16, # Changed dtype
        low_cpu_mem_usage=True,
        trust_remote_code=True,
        device_map='auto',
        img_context_token_id=128212 # Specific parameter
    ).eval()

    print(f"Successfully loaded model: {model_id} on {device}.")

except Exception as e:
    print(f"FATAL: Failed to load LLM model on startup: {e}")
    model = None
    tokenizer = None

# --- Generation Configuration ---
generation_config = GenerationConfig(
  max_new_tokens=2048,
  do_sample=True,
  temperature=0.01,
  top_p=0.01,
  repetition_penalty=1.1,
  eos_token_id=128009
)

# --- Prompt Engine ---
prompt_engine = MRPromptV3()
sys_prompt = 'You are a helpful AI assistant built by MediaTek Research. The user you are helping speaks Traditional Chinese and comes from Taiwan.'

# --- API Request and Response Models ---
class SummarizeRequest(BaseModel):
    text: str
    model_id: str # For future flexibility, though we only have one model now

class SummarizeResponse(BaseModel):
    summary: str

# --- API Endpoint ---
@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest):
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model is not available. Service might be starting up or has failed to load the model.")

    try:
        # --- Sanitization of input text ---
        sanitized_text = unicodedata.normalize('NFKC', request.text)
        sanitized_text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', sanitized_text)
        sanitized_text = re.sub(r'\n+', '\n', sanitized_text).strip()

        # --- Chunking Strategy ---
        # For PoC, a simple fixed-size chunking with overlap
        max_chunk_length = 1000 # tokens, roughly 750 words for English, adjust for Chinese
        overlap_length = 100 # tokens

        # Tokenize the entire sanitized text to get token count
        tokens = tokenizer.encode(sanitized_text, add_special_tokens=False)
        total_tokens = len(tokens)

        summaries = []
        
        # Iterate through chunks
        for i in range(0, total_tokens, max_chunk_length - overlap_length):
            chunk_tokens = tokens[i : i + max_chunk_length]
            chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)

            # Construct conversations list for MRPromptV3
            conversations = [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": f"請提供以下中文文本的簡潔摘要，並保留說話者資訊：\n\n{chunk_text}"},
                ]},
            ]
            # Get prompt string from MRPromptV3
            prompt, pixel_values = prompt_engine.get_prompt(conversations)

            # --- DEBUGGING TextEncodeInput ERROR ---
            print(f"DEBUG: Type of prompt: {type(prompt)}")
            print(f"DEBUG: Length of prompt: {len(prompt)}")
            print(f"DEBUG: Repr of prompt (first 200 chars): {repr(prompt[:200])}")
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device) # Use model.device

            # Generate using model.generate with GenerationConfig
            output_tensors = model.generate(**inputs, generation_config=generation_config)

            # Decode the generated output
            full_generated_text = tokenizer.decode(output_tensors[0])
            
            # Post-process to remove the original prompt from the generated text
            # This might need adjustment based on actual model output and prompt_engine
            summary_text_chunk = full_generated_text.replace(prompt, "").strip()
            summaries.append(summary_text_chunk)

        # Combine summaries (simple concatenation for PoC)
        final_summary = " ".join(summaries).strip()

        return SummarizeResponse(summary=final_summary)

    except Exception as e:
        print(f"Error during summarization: {e}")
        raise HTTPException(status_code=500, detail=f"An error occurred during summarization: {e}")

@app.get("/health")
async def health_check():
    """Health check endpoint to verify if the service and model are ready."""
    if model is not None and tokenizer is not None:
        return {"status": "ok", "model_loaded": True, "device": device}
    else:
        return {"status": "error", "model_loaded": False, "reason": "LLM failed to load or CUDA not available.", "device": device}
