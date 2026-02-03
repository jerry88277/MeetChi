---
description: 影片生成任務專用工作流程（Video Generation）
---

# Video Generation 工作流程

當需要使用 Veo 或其他工具生成影片時，執行此流程。

// turbo-all

## 步驟 1：確認需求

理解影片生成需求：
- 內容描述（prompt）
- 目標格式（橫屏/直屏）
- 解析度需求
- 時長限制

## 步驟 2：檢查環境

驗證必要配置：
```bash
# 確認環境變數
echo $GOOGLE_CLOUD_PROJECT
echo $GOOGLE_GENAI_USE_VERTEXAI
```

驗證項目：
- [ ] `google-genai` 套件已安裝
- [ ] GCS bucket 已配置
- [ ] Vertex AI 權限已啟用

## 步驟 3：準備 Prompt

建立高品質 prompt：
- 描述場景和主體
- 指定打光和風格
- 包含解析度和品質關鍵字

**Prompt 模板**：
```
[主體描述]，[場景]，[打光風格]，[品質關鍵字]
例：高擬真數位人發表演說，現代會議室，電影級打光，4K ultra HD
```

## 步驟 4：執行生成

調用 Veo API：
1. 初始化 `genai.Client()`
2. 配置 `GenerateVideosConfig`
3. 啟動 Long Running Operation
4. 輪詢等待完成

## 步驟 5：驗證結果

確認生成結果：
- [ ] 影片成功存儲到 GCS
- [ ] 下載到本地並預覽
- [ ] 品質符合預期

## 步驟 6：後處理（可選）

如需進一步處理：
- 使用 LivePortrait 進行口型同步
- 使用 MimicMotion 精修動作
- 使用 FaceDetailer 優化臉部

## 步驟 7：整合到 Pipeline

將生成的影片整合到 Digital Twin pipeline：
```python
from src.pipeline import DigitalTwinPipeline
pipeline = DigitalTwinPipeline()
# 使用生成的影片作為驅動源
```

---

## 快速指令

| 指令 | 說明 |
|------|------|
| `/veo-video-gen prompt: "..."` | 快速生成影片 |
| `/veo-video-gen prompt: "..." ar: "9:16"` | 生成直屏影片 |
| `/veo-video-gen prompt: "..." res: "4k"` | 生成 4K 影片 |

---

## 相關資源

- **Skill 文件**：`.agent/skills/veo-video-gen/SKILL.md`
- **知識庫**：`video_generation_veo.md`
