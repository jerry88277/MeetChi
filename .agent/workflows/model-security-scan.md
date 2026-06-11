# Workflow: ML Model Security Scan

## 觸發條件
- 新增、更換、或升級 ML 模型（ASR、Diarization、Embedding、LLM）
- 將模型 bake 進 Docker Image
- 定期維護掃描（建議每月一次）

## 前置條件
- 可存取 HuggingFace Hub（需 `HF_TOKEN` 用於 gated models）
- 可存取 GCS bucket（`gs://{PROJECT_ID}-meetchi-audio/models/`）
- Cloud Build 環境可用

## 流程步驟

### Step 1: 確認模型來源與格式

```bash
# 列出目標模型
echo "待掃描模型清單："
echo "  - 模型名稱: [HuggingFace repo 或 URL]"
echo "  - 格式: [safetensors / pickle(.bin/.pt) / h5 / SavedModel]"
echo "  - 來源: [官方組織 / 社群 / 第三方]"
```

判斷標準：
- ✅ 官方組織 + safetensors = 低風險（仍需掃描）
- ⚠️ 官方組織 + pickle = 中風險
- ❌ 第三方 + pickle = 高風險（必須深度掃描）

### Step 2: 執行自動化 Pipeline

```bash
# 透過 Cloud Build 執行完整 download → scan → upload 流程
gcloud builds submit --no-source \
  --config=cloudbuild-models.yaml \
  --substitutions=_HF_TOKEN=${HF_TOKEN},_PROJECT_ID=${PROJECT_ID} \
  --region=asia-east1
```

### Step 3: 手動掃描（本地/非 CI 情境）

若需要在本地環境掃描（例如測試新模型）：

```bash
# 安裝掃描工具
pip install "modelscan>=0.8.8" "fickling[torch]>=0.1.11"

# ModelScan: 全格式掃描
modelscan --path ./path-to-model-directory

# Fickling: 針對 pickle 格式深度分析
find ./path-to-model-directory -name "*.bin" -o -name "*.pt" -o -name "*.pkl" | \
  xargs -I{} python -m fickling --check-safety {}
```

### Step 4: 結果判讀

| 工具 | 結果 | 動作 |
|------|------|------|
| ModelScan | No issues found | ✅ 通過 |
| ModelScan | LOW/MEDIUM | ⚠️ 記錄但可繼續 |
| ModelScan | HIGH/CRITICAL | ❌ 停止，不得部署 |
| Fickling | LIKELY_SAFE | ✅ 通過 |
| Fickling | POSSIBLY_UNSAFE | ⚠️ 人工審查 |
| Fickling | UNSAFE/OVERTLY_MALICIOUS | ❌ 停止，不得部署 |

### Step 5: 失敗處置

若掃描失敗：
1. **不得上傳至 GCS 或 bake 進 image**
2. 在 Issue Tracker 建立安全事件記錄
3. 聯繫模型維護者確認是否為 false positive
4. 若確認為 false positive，需在 commit message 記錄豁免理由

### Step 6: 驗證（掃描通過後）

```bash
# 確認模型已上傳至 GCS
gsutil ls gs://${PROJECT_ID}-meetchi-audio/models/

# 若 bake 進 image，確認 image 可正常啟動
gcloud run services describe meetchi-gpu-asr --region=asia-southeast1 \
  --format="value(status.latestReadyRevisionName)"
```

## 相關檔案
- `cloudbuild-models.yaml` — CI/CD pipeline 實作
- `agents.md` Section 4 — 規則定義
- `Dockerfile.gpu-service` — GPU ASR image（若 bake 模型）

## 工具版本要求
- ModelScan: `>=0.8.8`（Protect AI / Palo Alto Networks）
- Fickling: `>=0.1.11`（Trail of Bits，修補 CVE-2026-22608/09/12）

## 注意事項
- Fickling < 0.1.7 有已知繞過漏洞，絕對不可使用舊版
- safetensors 格式天然免疫 pickle 攻擊，但仍建議用 ModelScan 做完整掃描
- 定期更新掃描工具版本，追蹤新發現的 CVE
