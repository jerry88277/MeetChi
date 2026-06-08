# Home 目錄空間分類報告

> 盤點時間：2026-06-08  
> 清除後可用空間：**1.3 GB / 4.8 GB（使用率 72%，較前 85% 改善）**

---

## 一、清除執行紀錄

| 項目 | 清除前大小 | 結果 |
|------|-----------|------|
| `.npm/_npx/` | 330 MB | ✅ 已清除（`npm cache clean --force` 不清此目錄，需手動 rm）|
| `.cache/pip/` | 138 MB | ✅ 已清除（pip install 可重建）|
| `.cache/uv/` | 89 MB | ✅ 已清除（uv 可重建）|
| `.cache/jedi/` | 42 MB | ✅ 已清除（Python autocomplete，可重建）|
| `.gemini/tmp/` 2025 entries | ~54 MB | ✅ 已清除（2025 年 hash 快取）|
| **合計釋放** | **~653 MB** | |

---

## 二、/home/jerry_tai 完整分類

### 🔴 需立即處理 — 敏感文件（明文憑證）

| 文件 | 最後修改 | 說明 | 建議 |
|------|----------|------|------|
| `github_access_token.txt` | 2025-12-23 | **明文 GitHub PAT token（github_pat_...）** | ⚠️ 立即刪除並在 GitHub Settings → Developer settings → Tokens 撤銷 |
| `client_secret_854823695084-*.json` | 2026-01-07 | Google OAuth client secret | ⚠️ 確認是否仍在使用，移至安全位置 |
| `config.json` | 2026-01-05 | 含 API 設定（6KB）| 🟡 確認是否含 secret key |

---

### 🟢 活躍目錄（保留）

| 目錄 | 大小 | 最後修改 | 說明 |
|------|------|----------|------|
| `.local/lib/python3.12/site-packages/` | 971 MB | 活躍 | 已安裝的 Python 套件（不可刪）|
| `.cache/copilot/pkg/linux-x64/` | 690 MB | 2026-06-08 | GitHub Copilot CLI binary（不可刪）|
| `.gemini/extensions/` | 530 MB | 活躍 | Gemini CLI 擴充套件（不可刪）|
| `.cache/cloud-code/` | 145 MB | 2026-06-08 | Google Cloud Code extension cache |
| `.local/share/gh/` | 154 MB | 活躍 | `gh` CLI 資料 |
| `.codeoss/` | 80 MB | 2025-11-28 | Cloud Shell Editor 設定 |
| `.copilot/` | 30 MB | 2026-06-08 | Copilot session state（本工作階段）|
| **MeetChi/** | 419 MB | 2026-06-08 | ⭐ 主專案 |

---

### 🟡 近期使用，視需求保留

| 目錄 | 大小 | 最後修改 |
|------|------|----------|
| `2026-03-20/` | 12 MB | 2026-03-25 |
| `FinanceSummary/` | 7.0 MB | 2026-04-22 |
| `ExcelADK/` | 736 KB | 2026-05-08 |
| `TEMP/` | 380 KB | 2026-05-29 |
| `plan_reply/` | 40 KB | 2026-03-12 |
| `.docker/` | 804 KB | 2026-01-29 |

---

### 🔵 超過 3 個月未動（可評估清除，合計 ~63 MB）

| 目錄 | 大小 | 最後修改 |
|------|------|----------|
| `API_Test/` | 21 MB | 2025-11-06 |
| `Road_Risk_pro_Process/` | 11 MB | 2025-12-16 |
| `Statistic_and_Data_Cleaning/` | 6.4 MB | 2025-12-05 |
| `traffic/` | 6.1 MB | 2025-12-15 |
| `Apply_Letter/` | 5.5 MB | 2026-02-13 |
| `gopath/` | 3.9 MB | 2025-09-09 |
| `ConvertBase64/` | 3.4 MB | 2026-01-15 |
| `HTML_deployment/` | 2.8 MB | 2025-12-22 |
| `SAP_API/` | 1.8 MB | 2026-01-12 |
| `road-split-api/` | 284 KB | 2025-12-01 |
| `Brainstoming/` | 148 KB | 2025-12-16 |
| `Course_Report/` | 68 KB | 2025-11-07 |
| `Upload_HF_Model/` | 8.0 KB | 2025-12-24 |

---

### 🟠 MeetChi 內部可回收資源

| 項目 | 大小 | 建議 |
|------|------|------|
| `terraform/.terraform/` | 220 MB | 🟡 可 `rm -rf` 後 `terraform init` 重建 |
| `Material/` | 113 MB | 🟢 保留（品牌色分析用）|
| `test_data/ffmpeg-essentials.zip` | 36 MB | 🟡 ffmpeg 已安裝可刪除 zip |

---

## 三、空間現況（清除後）

```
/home  4.8GB 總計，已用 3.3GB，可用 1.3GB（72%）

工具 runtime（不可動）  ~2.7 GB
主專案 MeetChi/         ~419 MB（其中 terraform/.terraform 220MB 可選清除）
舊工作目錄（>3月）       ~63 MB  ← 待確認清除
可用空間                 1.3 GB
```

---

## 四、後續建議行動

| 優先度 | 行動 | 預計釋放 |
|--------|------|----------|
| 🔴 立即 | 刪除 `github_access_token.txt` + GitHub 撤銷 PAT | <1KB |
| 🟡 可選 | `rm -rf ~/MeetChi/terraform/.terraform/` | 220 MB |
| 🟡 可選 | `rm ~/MeetChi/test_data/ffmpeg-essentials.zip` | 36 MB |
| 🟡 評估 | 清除 13 個超過 3 個月的舊目錄 | 63 MB |
