---
name: Google AI Media Generation
description: 使用 Google AI 生成高品質圖片和影片（Nano Banana + Veo + Flow + Whisk）
---

# Google AI 媒體生成 Skill

透過 Gemini 應用和 Labs.google 網頁介面使用 Google 的 AI 媒體生成工具。

> [!NOTE]
> 此 skill 使用瀏覽器自動化，適用於 Google AI Ultra/Pro 訂閱用戶。

---

## 支援的服務總覽

| 服務 | URL | 類型 | 說明 |
|------|-----|------|------|
| **Nano Banana** | gemini.google.com | 圖片 | AI 圖片生成與編輯 |
| **Nano Banana Pro** | gemini.google.com | 圖片 | 複雜場景與高解析度 |
| **Veo 3.1** | gemini.google.com | 影片 | AI 影片生成 |
| **Flow** | labs.google/fx/zh/tools/flow | 影片 | AI 影片製作工具 |
| **Whisk** | labs.google/fx/zh/tools/whisk/project | 圖片 | 圖片風格混合 |

---

## Nano Banana（圖片生成）

### 功能說明

Nano Banana 是 Google 的 AI 圖片生成和編輯工具：

| 版本 | 基礎模型 | 適用場景 |
|------|----------|----------|
| **Nano Banana** | Gemini 2.5 Flash | 快速生成、風格轉換、對話式編輯 |
| **Nano Banana Pro** | Gemini 3 Pro | 複雜場景、4K 高解析度、精確文字渲染 |

### 核心能力

- **圖片生成**：從文字描述生成圖片
- **對話式編輯**：透過對話修改現有圖片
- **風格轉換**：將照片轉換為不同藝術風格
- **角色一致性**：保持多張圖片中角色外觀一致
- **照片合成**：組合多張照片
- **局部編輯**：修改圖片特定區域
- **文字渲染**：生成包含精確文字的圖片（Pro）

### 操作流程

#### 步驟 1：開啟 Gemini

```
瀏覽器導航到 https://gemini.google.com
```

#### 步驟 2：選擇模型

- **Fast 模式**：使用 Nano Banana（快速）
- **Thinking 模式**：使用 Nano Banana Pro（精細）

#### 步驟 3：輸入 Prompt

圖片生成範例：
```
生成一張圖片：專業商務人士在現代辦公室，電影級打光，4K 品質
```

圖片編輯範例（先上傳圖片）：
```
把背景換成日落時的海灘
```

#### 步驟 4：下載

點擊生成的圖片，選擇下載。

---

## Veo 3.1（影片生成）

### 功能說明

Veo 是 Google 的 AI 影片生成模型：

| 版本 | 說明 | 訂閱需求 |
|------|------|----------|
| **Veo 3.1** | 完整功能，最高品質 | AI Ultra |
| **Veo 3.1 Fast** | 快速生成，較低點數消耗 | AI Pro/Ultra |

### 核心能力

- **文字生成影片**：從描述生成 8 秒影片
- **圖片生成影片**：從靜態圖片創建動畫
- **影片擴展**：延長現有影片
- **解析度**：720p / 1080p / 4K
- **原生音訊**：自動生成配合影片的音效

### 操作流程

#### 步驟 1：開啟 Gemini

```
瀏覽器導航到 https://gemini.google.com
```

#### 步驟 2：輸入影片生成 Prompt

```
生成一段影片：數位分身在會議室發表演說，電影級打光
```

英文 prompt（效果更佳）：
```
Generate a video: A digital human giving a speech in a conference room, cinematic lighting, 4K
```

#### 步驟 3：等待生成

- 生成時間約 1-5 分鐘
- 完成後會顯示影片預覽

#### 步驟 4：下載

點擊影片下載按鈕，格式為 MP4。

---

## Flow（專業影片製作）

### 功能說明

Flow 結合 Veo + Imagen 4，專為創意人士打造。

### URL

```
https://labs.google/fx/zh/tools/flow
```

### 核心功能

- **文字生成影片**：輸入描述生成片段
- **圖帧生影片**：從靜態圖片創建動畫
- **素材生影片**：使用現有素材重新生成
- **影片擴展**：延長現有影片
- **攝影機控制**：調整運鏡和視角
- **場景創建工坊**：組合多個片段成完整場景

### 點數消耗

| 方案 | 每月點數 | Veo 3.1 Fast |
|------|----------|--------------|
| 免費 | 180 | - |
| AI Pro | 更多 | - |
| AI Ultra | 最高 | 10 點/次 |

---

## Whisk（風格混合）

### 功能說明

混合多張圖片的主體、場景和風格。

### URL

```
https://labs.google/fx/zh/tools/whisk/project
```

### 操作流程

1. **上傳 Subject**：主體圖片（人物、物件）
2. **上傳 Scene**：場景圖片（背景、環境）
3. **上傳 Style**：風格圖片（藝術風格參考）
4. **點擊「Whisk it」**：生成混合結果
5. **下載**：儲存生成的圖片

---

## 瀏覽器自動化範例

### Nano Banana 圖片生成

```
Task: 使用 Nano Banana 生成圖片
1. 導航到 https://gemini.google.com
2. 確認已登入 AI Ultra/Pro 帳戶
3. 在對話框輸入圖片生成 prompt
4. 等待圖片生成完成
5. 點擊生成的圖片
6. 點擊下載按鈕
7. 回報下載位置
```

### Veo 影片生成

```
Task: 使用 Veo 生成影片
1. 導航到 https://gemini.google.com
2. 輸入：Generate a video: [用戶描述]
3. 等待 Veo 生成完成（1-5 分鐘）
4. 點擊下載按鈕
5. 回報影片下載位置
```

### Flow 專業製作

```
Task: 使用 Flow 生成影片
1. 導航到 https://labs.google/fx/zh/tools/flow
2. 登入並進入工作區
3. 選擇生成類型
4. 輸入 prompt
5. 配置解析度和時長
6. 點擊生成並等待完成
7. 匯出並下載
```

---

## 與 Digital Twin Pipeline 整合

生成的媒體可作為以下模組的輸入：

### 圖片（Nano Banana → 頭像/素材）

```python
# 使用生成的圖片作為數位分身頭像
from src.pipeline import DigitalTwinPipeline

pipeline = DigitalTwinPipeline()
result = pipeline.expression.generate_speech(
    source_image="outputs/nano_banana_avatar.png",
    audio_path="speech.wav"
)
```

### 影片（Veo → 驅動源）

```python
# 使用生成的影片作為驅動源
result = pipeline.expression.generate_speech(
    source_image="avatar.png",
    driving_video_path="outputs/veo_generated.mp4",
    audio_path="speech.wav"
)
```

---

## 錯誤處理

| 問題 | 解決方案 |
|------|----------|
| 未登入 | 確認已登入 AI Ultra/Pro 訂閱帳戶 |
| 點數不足 | 等待月初重置或購買充值點數 |
| 生成失敗 | 簡化 prompt 後重試 |
| 內容被拒絕 | 修改 prompt 避免違規內容 |

---

## 注意事項

> [!IMPORTANT]
> 需要 Google AI Pro 或 Ultra 訂閱才能使用完整功能。

> [!TIP]
> 使用英文 prompt 通常能獲得更好的生成效果。

> [!WARNING]
> 圖片生成約需 10-30 秒，影片生成約需 1-5 分鐘。
