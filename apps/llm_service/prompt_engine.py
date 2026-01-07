import re
import json

class MRPromptV3:
    def get_prompt(self, conversations):
        """
        Constructs a prompt string from conversation history, typically for Llama-like models.
        Returns the formatted prompt and None for pixel_values (as this is a text-only model).
        """
        system_prompt = ""
        user_message = ""
        
        for msg in conversations:
            if msg["role"] == "system":
                system_prompt = msg["content"]
            elif msg["role"] == "user":
                # User content can be a string or a list of dicts (for multimodal)
                if isinstance(msg["content"], list):
                    user_message = "\n".join([item["text"] for item in msg["content"] if item["type"] == "text"])
                else:
                    user_message = msg["content"]

        if system_prompt:
            # Llama 3 style prompt
            return f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n{system_prompt}<|eot_id|><|start_header_id|>user<|end_header_id|>\n{user_message}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n", None
        else:
            return f"<|begin_of_text|><|start_header_id|>user<|end_header_id|>\n{user_message}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n", None

    def parse_generated_str(self, generated_text):
        """
        Parses the raw model output string to extract the assistant's response.
        For Llama 3 style, it's often the text after the last assistant header.
        """
        # Fix: Escape pipe characters '|' in regex
        match = re.search(r'<\|start_header_id\|>assistant<\|end_header_id\|>\s*(.*)', generated_text, re.DOTALL)
        if match:
            # Further strip any <|eot_id|> or trailing system/user turns
            content = match.group(1).strip()
            content = re.sub(r'<\|eot_id\|>.*', '', content, flags=re.DOTALL).strip()
            return {"content": content}
        
        # Fallback: If no header found, assume the whole text is the content (minus eot)
        content = re.sub(r'<\|eot_id\|>.*', '', generated_text, flags=re.DOTALL).strip()
        return {"content": content}
