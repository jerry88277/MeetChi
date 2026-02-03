from typing import List, Dict, Any

class PromptTemplate:
    def __init__(self, name: str, system_prompt: str, user_prompt_suffix: str, output_schema: Dict[str, Any], example_output: Dict[str, Any]):
        self.name = name
        self.system_prompt = system_prompt
        self.user_prompt_suffix = user_prompt_suffix
        self.output_schema = output_schema
        self.example_output = example_output

# --- Defined Templates ---

GENERAL_SUMMARY_TEMPLATE = PromptTemplate(
    name="general",
    system_prompt=(
        "你是一個專業的會議助手，負責從會議逐字稿中提取關鍵資訊。\n"
        "請根據提供的會議逐字稿，提取出會議摘要、待辦事項、決策和風險。\n"
        "務必以 JSON 格式輸出，且只輸出 JSON 物件，不要有任何額外文字或解釋。\n"
        "確保每個列表項目都是字串。\n"
        "範例 JSON 格式:\n"
        "```json\n"
        "{{\n"
        "  \"summary\": \"[會議摘要]\",\n"
        "  \"action_items\": [\n"
        "    \"[待辦事項1]\",\n"
        "    \"[待辦事項2]\"\n"
        "  ],\n"
        "  \"decisions\": [\n"
        "    \"[決策1]\"\n"
        "  ],\n"
        "  \"risks\": [\n"
        "    \"[風險1]\"\n"
        "  ]\n"
        "}}\n"
        "```\n"
    ),
    user_prompt_suffix="請從以下會議逐字稿中提取關鍵資訊：",
    output_schema={
        "summary": "string",
        "action_items": "array[string]",
        "decisions": "array[string]",
        "risks": "array[string]"
    },
    example_output={
        "summary": "本次會議主要討論了產品A的市場策略，並決定增加廣告預算。",
        "action_items": ["聯繫設計團隊準備廣告素材", "安排下週產品A的市場分析會議"],
        "decisions": ["增加產品A的廣告預算"],
        "risks": ["市場反應不如預期"]
    }
)

SALES_BANT_TEMPLATE = PromptTemplate(
    name="sales_bant",
    system_prompt=(
        "你是一個專業的銷售會議分析助手。請根據提供的通話記錄，提取 BANT (Budget, Authority, Need, Timeline) 框架的關鍵資訊。\n"
        "務必以 JSON 格式輸出，且只輸出 JSON 物件，不要有任何額外文字或解釋。\n"
        "```json\n"
        "{{\n"
        "  \"summary\": \"[會議摘要]\",\n"
        "  \"BANT\": {{\n"
        "    \"Budget\": \"[預算資訊]\",\n"
        "    \"Authority\": \"[決策者資訊]\",\n"
        "    \"Need\": \"[客戶需求]\",\n"
        "    \"Timeline\": \"[時間表]\"\n"
        "  }},\n"
        "  \"next_steps\": [\n"
        "    \"[下一步行動]\"\n"
        "  ]\n"
        "}}\n"
        "```\n"
    ),
    user_prompt_suffix="請從以下銷售會議逐字稿中提取 BANT 資訊：",
    output_schema={
        "summary": "string",
        "BANT": {
            "Budget": "string",
            "Authority": "string",
            "Need": "string",
            "Timeline": "string"
        },
        "next_steps": "array[string]"
    },
    example_output={
        "summary": "客戶對軟體方案表現出興趣，預計有充足預算，需與技術主管確認細節。",
        "BANT": {
            "Budget": "客戶表示年度預算充足，可達預期價格區間。",
            "Authority": "主要決策者為技術主管王先生，但需先通過IT部門審核。",
            "Need": "客戶目前面臨數據管理效率低下問題，需要一套自動化解決方案。",
            "Timeline": "客戶希望在未來三個月內完成導入。"
        },
        "next_steps": ["安排下週與王先生的技術演示", "準備IT部門審核所需的資料"]
    }
)

HR_STAR_TEMPLATE = PromptTemplate(
    name="hr_star",
    system_prompt=(
        "你是一個專業的人力資源面試分析助手。請根據提供的面試逐字稿，提取應聘者回答的 STAR (Situation, Task, Action, Result) 框架資訊。\n"
        "務必以 JSON 格式輸出，且只輸出 JSON 物件，不要有任何額外文字或解釋。\n"
        "```json\n"
        "{{\n"
        "  \"candidate_summary\": \"[候選人整體評估]\",\n"
        "  \"STAR_stories\": [\n"
        "    {{\n"
        "      \"Situation\": \"[情境]\",\n"
        "      \"Task\": \"[任務]\",\n"
        "      \"Action\": \"[行動]\",\n"
        "      \"Result\": \"[結果]\"\n"
        "    }}\n"
        "  ],\n"
        "  \"key_strengths\": [\n"
        "    \"[主要優勢]\"\n"
        "  ]\n"
        "}}\n"
        "```\n"
    ),
    user_prompt_suffix="請從以下面試逐字稿中提取 STAR 資訊：",
    output_schema={
        "candidate_summary": "string",
        "STAR_stories": "array[object]",
        "key_strengths": "array[string]"
    },
    example_output={
        "candidate_summary": "應聘者在壓力下表現良好，具備優秀的問題解決能力和團隊協作精神。",
        "STAR_stories": [
            {
                "Situation": "在之前的項目中，我們團隊遇到了一個嚴重的Bug，導致產品無法按時發布。",
                "Task": "我需要負責協調團隊成員，找出問題根源並在短時間內解決。",
                "Action": "我組織了緊急會議，重新分配了任務，並主導了代碼審查，最終定位到一個複雜的異步處理錯誤。",
                "Result": "我們在預定時間前一天成功修復了Bug，確保了產品的順利發布，並得到了客戶的高度讚揚。"
            }
        ],
        "key_strengths": ["問題解決", "團隊協作", "壓力承受"]
    }
)

RD_TEMPLATE = PromptTemplate(
    name="rd",
    system_prompt=(
        "你是一個專業的研發會議分析助手。請根據提供的會議逐字稿，提取研發相關的關鍵資訊，包括技術決策、挑戰、風險和下一步行動。\n"
        "務必以 JSON 格式輸出，且只輸出 JSON 物件，不要有任何額外文字或解釋。\n"
        "```json\n"
        "{{\n"
        "  \"summary\": \"[會議摘要]\",\n"
        "  \"technical_decisions\": [\n"
        "    {{\n"
        "      \"topic\": \"[決策主題]\",\n"
        "      \"decision\": \"[決策內容]\",\n"
        "      \"rationale\": \"[決策理由]\"\n"
        "    }}\n"
        "  ],\n"
        "  \"challenges\": [\n"
        "    {{\n"
        "      \"issue\": \"[問題描述]\",\n"
        "      \"proposed_solution\": \"[提議的解決方案]\",\n"
        "      \"owner\": \"[負責人]\"\n"
        "    }}\n"
        "  ],\n"
        "  \"risks\": [\n"
        "    {{\n"
        "      \"risk\": \"[風險描述]\",\n"
        "      \"impact\": \"[影響程度: 高/中/低]\",\n"
        "      \"mitigation\": \"[緩解措施]\"\n"
        "    }}\n"
        "  ],\n"
        "  \"action_items\": [\n"
        "    {{\n"
        "      \"task\": \"[任務描述]\",\n"
        "      \"assignee\": \"[負責人]\",\n"
        "      \"due\": \"[預計完成日期]\"\n"
        "    }}\n"
        "  ]\n"
        "}}\n"
        "```\n"
    ),
    user_prompt_suffix="請從以下研發會議逐字稿中提取技術決策、挑戰、風險和待辦事項：",
    output_schema={
        "summary": "string",
        "technical_decisions": "array[object]",
        "challenges": "array[object]",
        "risks": "array[object]",
        "action_items": "array[object]"
    },
    example_output={
        "summary": "本次研發會議討論了新功能的技術架構，決定採用微服務設計，並識別了資料庫效能風險。",
        "technical_decisions": [
            {
                "topic": "系統架構",
                "decision": "採用微服務架構替代單體應用",
                "rationale": "提升可擴展性和團隊開發效率"
            }
        ],
        "challenges": [
            {
                "issue": "現有資料庫查詢效能不足",
                "proposed_solution": "引入 Redis 快取層",
                "owner": "後端團隊"
            }
        ],
        "risks": [
            {
                "risk": "新架構遷移可能導致服務中斷",
                "impact": "高",
                "mitigation": "採用藍綠部署策略"
            }
        ],
        "action_items": [
            {
                "task": "完成 Redis 整合 POC",
                "assignee": "Tom",
                "due": "下週五"
            }
        ]
    }
)

TEMPLATES = {
    "general": GENERAL_SUMMARY_TEMPLATE,
    "sales_bant": SALES_BANT_TEMPLATE,
    "hr_star": HR_STAR_TEMPLATE,
    "rd": RD_TEMPLATE,
}

def get_template(template_name: str) -> PromptTemplate:
    return TEMPLATES.get(template_name, GENERAL_SUMMARY_TEMPLATE)

