import torch
from flask import Flask, request, jsonify
from transformers import AutoModel, AutoTokenizer, GenerationConfig
from mtkresearch.llm.prompt import MRPromptV3
import logging
import threading
import re # Import re for language validation
import os # Import os for env vars

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration ---
# MODEL_NAME = "MediaTek-Research/Llama-Breeze2-8B-Instruct"
MODEL_NAME = "MediaTek-Research/Llama-Breeze2-3B-Instruct"
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
MOCK_LLM = os.getenv("MOCK_LLM", "false").lower() == "true"

# Global model and tokenizer
model = None
tokenizer = None
prompt_engine = None
lock = threading.Lock()

def load_llm_model():
    global model, tokenizer, prompt_engine
    
    if MOCK_LLM:
        logger.info("MOCK_LLM is enabled. Skipping model loading.")
        return

    logger.info(f"Loading LLM model: {MODEL_NAME} on {DEVICE}...")
    try:
        # Use AutoModel as per documentation for this specific model
        model = AutoModel.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.bfloat16, # Recommended dtype
            low_cpu_mem_usage=True,
            trust_remote_code=True,
            device_map=DEVICE,
            img_context_token_id=128212 # Required parameter for Breeze2
        ).eval()
        
        tokenizer = AutoTokenizer.from_pretrained(
            MODEL_NAME, 
            trust_remote_code=True, 
            use_fast=False
        )
        
        # Initialize Prompt Engine
        prompt_engine = MRPromptV3()
        
        logger.info("LLM model loaded successfully.")
    except Exception as e:
        logger.error(f"Failed to load LLM model: {e}. Falling back to MOCK mode.")
        # Do NOT raise e here, allow app to start in degraded mode.
        # model remains None

# Pre-load model on startup
with app.app_context():
    load_llm_model()

@app.route('/health', methods=['GET'])
def health_check():
    if model is not None or MOCK_LLM or model is None: # Accept None (degraded) as healthy-ish for now
        return jsonify({"status": "ready", "device": DEVICE, "mock_mode": MOCK_LLM or model is None}), 200
    else:
        return jsonify({"status": "loading"}), 503

@app.route('/polish', methods=['POST'])
def polish_text():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({"error": "No text provided"}), 400
    
    raw_text = data['text']
    previous_context = data.get('previous_context', "")
    source_lang = data.get('source_lang', 'zh')
    target_lang = data.get('target_lang', 'en')

    # --- MOCK MODE HANDLING ---
    if MOCK_LLM or model is None:
        logger.info(f"[MOCK] Polishing: {raw_text}")
        return jsonify({
            "polished_text": raw_text, # No refinement in mock
            "refined": raw_text,
            "translated": f"[Mock Trans] {raw_text}" # Dummy translation
        })

    # Language descriptions for Prompt
    if source_lang == 'zh':
        source_desc = "中文（可包含中英夾雜）"
        refined_example = "產業鏈座落的城市之一。"
    else:
        source_desc = "英文"
        refined_example = "One of the cities where the industry chain is located."

    if target_lang == 'en':
        target_desc = "英文"
        trans_example = "one of the cities where the industrial chain is located."
    else:
        target_desc = "繁體中文"
        trans_example = "產業鏈座落的城市之一。"

    # Context/Prompt Engineering
    system_prompt = (
        "你是一個專業的即時口譯助手。你的任務是處理會議逐字稿片段。\n"
        "【參考資訊】：\n"
        "- 公司：奇美實業 (Chi Mei Corporation)\n"
        "- 高層：許春華(董事長)、趙令瑜(總經理)、林慶盛(總經理)、洪良義、徐全成、王耀慶、盛培華、蘇耀宗、郭銘洲(皆為副總)、陳連振、林丕淇(財務)、劉懷立(會計)。\n"
        "- 關鍵供應商：Formosa Plastics (台塑)、Nan Ya (南亞)、BASF (巴斯夫)、DuPont (杜邦)、Trinseo (盛禧奧)、LG Chem (樂金)、Mitsubishi Chemical (三菱化學)、Tosoh (東曹)、Celanese、Eastman、Evonik、Ineos Styrolution、Toray (東麗)。\n"
        "- 關鍵客戶：LCD面板廠(友達/群創)、全球前五大輪胎廠、LEGO積木。\n"
        "- 產品與技術：Ecologue永續材料、CCU碳捕捉再利用、LGP導光板、ABS樹脂、PMMA、PC、PCR塑膠、化學回收、機械回收。\n"
        "- 永續目標：2050淨零排放 (Net Zero)、SBTi科學基礎減量目標、Clean & Green、幸福(Xingfu)企業。\n\n"
        "輸入包含【上文】（僅供參考，用來理解語境，**嚴禁重複或引用**）與【當前片段】（需要處理）。\n"
        "請執行以下兩個任務，並務必嚴格遵守語言限制：\n"
        f"1. **refined** (潤飾)：修正錯字、去除贅字、**根據語氣加入或修正標點符號**。請利用【參考資訊】修正特定專有名詞。\n"
        "   - **標點符號重點**：請根據語句的停頓與語氣，適當加入逗號、句號或問號，使閱讀更流暢。\n"
        "   - **絕對禁止重複【上文】的內容**：你的輸出必須僅包含【當前片段】的資訊。\n"
        "   - **去重範例**：\n"
        "     上文：最具特色的產業\n"
        "     當前片段：產業鏈座落的城市\n"
        "     輸出 Refined：鏈座落的城市 (刪除重疊的'產業')\n"
        "   - **不要補全語意**：如果【當前片段】只有「就此展開」，請只輸出「就此展開」，**絕對不要**把上文的主詞（如「生態之旅」）補回來。\n"
        "   - **關鍵**：如果【當前片段】過短、語意不清或疑似噪音，請寧願返回非常簡短的內容，甚至空字符串，也**絕不能**進行任何形式的推測性補全，**更不能創造新的資訊**。\n"
        f"   - **必須保持原始語言（{source_desc}）**，絕對不要翻譯！\n"
        f"2. **translated** (翻譯)：將潤飾後的當前片段翻譯成流暢的**{target_desc}**。\n\n"
        "範例：\n"
        "上文：(Context)\n"
        "當前片段：(Input)\n"
        f"輸出：{{\"refined\": \"{refined_example}\", \"translated\": \"{trans_example}\"}}\n\n"
        "請只輸出合法的 JSON 物件，不要有任何解釋。"
    )
    
    user_content = f"當前片段：{raw_text}"
    if previous_context:
        user_content = f"上文：{previous_context}\n{user_content}"

    # Construct conversation for MRPromptV3
    conversations = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]
    
    try:
        with lock:
            # Generate Prompt
            prompt = prompt_engine.get_prompt(conversations)
            
            inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
            
            # Generation parameters
            generation_config = GenerationConfig(
                max_new_tokens=512,
                do_sample=True,
                temperature=0.1, # Keep low for JSON stability
                top_p=0.9,
                repetition_penalty=1.1,
                eos_token_id=128009 
            )

            # Inference
            output_tensors = model.generate(
                **inputs, 
                generation_config=generation_config,
                pixel_values=None
            )
            
            output_str = tokenizer.decode(output_tensors[0], skip_special_tokens=False)
            logger.info(f"Raw model output string: {output_str}") 
            
            # Parse result (MRPromptV3 returns a dictionary with 'role' and 'content')
            parsed_response = prompt_engine.parse_generated_str(output_str)
            
            content = ""
            if isinstance(parsed_response, dict) and 'content' in parsed_response:
                content = parsed_response['content']
            elif isinstance(parsed_response, str):
                content = parsed_response
            
            # --- Enhanced JSON Extraction ---
            import json
            import re
            
            # 1. Try to find JSON block using regex
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            # 2. Parse JSON
            refined_text = raw_text
            translated_text = ""
            
            try:
                result_json = json.loads(content)
                refined_text = result_json.get("refined", raw_text)
                translated_text = result_json.get("translated", "")
                
                # --- Post-processing / Sanitization ---
                
                # Recursive JSON check: if output contains nested JSON string
                if isinstance(refined_text, str) and (refined_text.strip().startswith('{') or '"refined":' in refined_text):
                     try:
                         nested = json.loads(refined_text)
                         if isinstance(nested, dict):
                             refined_text = nested.get('refined', refined_text)
                     except:
                         pass # Not valid JSON, keep as is (or could strip)

                # Type check
                if isinstance(refined_text, dict):
                     refined_text = refined_text.get('content', str(refined_text))
                if isinstance(translated_text, dict):
                     translated_text = translated_text.get('content', str(translated_text))
                     
                refined_text = str(refined_text)
                translated_text = str(translated_text)

                # --- Language Consistency Check ---
                # Prevent LLM from translating the 'refined' field into English when source is Chinese
                if source_lang == 'zh':
                    # Check if refined_text contains at least one Chinese character
                    # This heuristic assumes valid refined Chinese text must have Chinese characters.
                    # It handles cases where LLM outputs "In addition to..." instead of "除了..."
                    if not re.search(r'[\u4e00-\u9fff]', refined_text) and re.search(r'[a-zA-Z]', refined_text):
                         # If no Chinese AND contains English letters -> Likely flipped
                         # (Condition improved to allow numbers/punctuation only, but unlikely for ASR output)
                        logger.warning(f"Language Flip Detected! LLM output English in refined field: '{refined_text}'. Reverting to raw.")
                        refined_text = raw_text

            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON from LLM: {content}. Fallback to raw text.")
                refined_text = raw_text # Fallback to raw is safer than 'content' which might be garbage
                translated_text = ""

            logger.info(f"Polished: '{raw_text}' -> Refined: '{refined_text}', Translated: '{translated_text}'")
            
            return jsonify({
                "polished_text": refined_text, # Keep legacy field for compatibility if needed, but updated
                "refined": refined_text,
                "translated": translated_text
            })

    except Exception as e:
        logger.error(f"Inference error: {e}", exc_info=True)
        return jsonify({"error": str(e), "traceback": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)