# 空間盤點報告

> 盤點時間：2026-06-08  
> 執行環境：Google Cloud Shell

---

## 磁碟空間現況

| 分區 | 總容量 | 已用 | 可用 | 使用率 |
|------|--------|------|------|--------|
| `/home`（Cloud Shell 個人儲存）| 4.8 GB | 3.9 GB | **702 MB** | 85% ⚠️ |
| `/`（容器主磁碟）| 95 GB | 48 GB | 47 GB | 51% ✅ |

> ⚠️ `/home` 空間不足是 `npm ci` 出現 `ENOSPC` 的根本原因（非主磁碟問題）。  
> 部署流程走 Cloud Build，不影響 GCP 上的建置作業。

---

## /home/jerry_tai 各目錄清單

### 超過 3 個月未修改的目錄（截止 2026-03-08）

| 最後修改 | 大小 | 目錄 | 建議 |
|----------|------|------|------|
| 2025-09-09 | 3.9 MB | `gopath/` | 🔴 可清除（Go 暫存）|
| 2025-11-06 | 21 MB | `API_Test/` | 🟡 確認後清除 |
| 2025-11-07 | 68 KB | `Course_Report/` | 🟡 確認後清除 |
| 2025-12-01 | 284 KB | `road-split-api/` | 🟡 確認後清除 |
| 2025-12-05 | 6.4 MB | `Statistic_and_Data_Cleaning/` | 🟡 確認後清除 |
| 2025-12-15 | 6.1 MB | `traffic/` | 🟡 確認後清除 |
| 2025-12-16 | 11 MB | `Road_Risk_pro_Process/` | 🟡 確認後清除 |
| 2025-12-16 | 148 KB | `Brainstoming/` | 🟡 確認後清除 |
| 2025-12-22 | 2.8 MB | `HTML_deployment/` | 🟡 確認後清除 |
| 2025-12-24 | 8.0 KB | `Upload_HF_Model/` | 🔴 可清除 |
| 2026-01-12 | 1.8 MB | `SAP_API/` | 🟡 確認後清除 |
| 2026-01-15 | 3.4 MB | `ConvertBase64/` | 🟡 確認後清除 |
| 2026-02-13 | 5.5 MB | `Apply_Letter/` | 🟡 確認後清除 |

**合計可回收**：~ 63 MB（舊目錄）

---

### 近期活躍目錄

| 最後修改 | 大小 | 目錄 | 說明 |
|----------|------|------|------|
| 2026-06-08 | 419 MB | `MeetChi/` | ⭐ 主專案，保留 |
| 2026-05-29 | 21 MB | `TEMP/` | 暫存，可評估清除 |
| 2026-05-08 | 736 KB | `ExcelADK/` | 近期使用，保留 |
| 2026-04-22 | 7.0 MB | `FinanceSummary/` | 近期使用，保留 |
| 2026-03-25 | 12 MB | `2026-03-20/` | 近期使用，保留 |

---

## MeetChi 內部大型資源

| 大小 | 目錄 | 說明 | 建議 |
|------|------|------|------|
| 220 MB | `terraform/.terraform/` | Terraform provider binaries（google, google-beta, random v5.45.2）| 🟡 可執行 `terraform init` 重建；**確認不需要後可清除** |
| 113 MB | `Material/` | CHIMEI 品牌素材（PDF + PNG）| 🟢 保留（已用於品牌分析）|
| 36 MB | `test_data/` | `ffmpeg-essentials.zip`（37MB）| 🟡 若 ffmpeg 已安裝可清除 zip |
| 3.7 MB | `apps/` | 原始碼 | 🟢 保留 |
| 1.3 MB | `docs/` | 設計文件 + devlog | 🟢 保留 |

---

## npm 快取

| 大小 | 路徑 | 說明 |
|------|------|------|
| 330 MB | `~/.npm/_npx/` | npx 執行緩存 |
| 212 KB | `~/.npm/_logs/` | npm 日誌 |

> 💡 `npm cache clean --force` 可清除 `_npx/`，預計釋放 ~330 MB。  
> 執行後 `/home` 可用空間從 702 MB → ~1 GB。

---

## 建議行動

| 優先度 | 行動 | 預計釋放 |
|--------|------|----------|
| 🔴 立即 | `npm cache clean --force` | ~330 MB |
| 🟡 確認後 | 清除 `terraform/.terraform/`（重新 `terraform init` 可還原）| 220 MB |
| 🟡 確認後 | 清除 `MeetChi/test_data/ffmpeg-essentials.zip` | 36 MB |
| 🟡 評估 | 清除超過 3 個月未用的舊目錄（13 個）| 63 MB |
| 🟢 可選 | 清除 `TEMP/` | 21 MB |

**若執行 🔴 + 🟡 建議，/home 可用空間可從 702 MB → ~1.3 GB**（使用率降至 ~73%）
