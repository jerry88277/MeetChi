# MeetChi 部署執行計劃 (MeetChi Deployment Execution Plan)

本計劃旨在安全解除目前的 Terraform 部署阻塞，接管既有衝突資源，並將 MeetChi 基礎設施及資料庫遷移完整部署至 GCP 專案 `prj-ai-meetchi-du`。

---

## ⚠️ 使用者審查與確認事項 (User Review Required)

> [!IMPORTANT]
> 1. **強制解除狀態鎖定 (Force Unlock)**:
>    我們將執行 `terraform force-unlock 1780045282626189`。請確認目前沒有其他人員或 CI/CD pipeline 正在對 `prj-ai-meetchi-du-terraform-state` 寫入。
> 2. **資源衝突接管 (Terraform Import)**:
>    由於 `meetchi-db-password` 等部分 GCP 資源先前已被手動或於舊部署中建立，我們會使用 `terraform import` 將既有資源導入狀態檔中，以避免 `terraform apply` 報錯或嘗試覆蓋。

---

## 📋 預計執行步驟 (Proposed Steps)

### 1. 解除鎖定與基礎清理
- 執行 `terraform force-unlock 1780045282626189` 釋放 stale lock。

### 2. 匯入既有衝突資源 (IaC 接管)
根據錯誤紀錄，以下資源需要先被導入或做相應處理：
- **Secret Manager Database Password**:
  ```bash
  terraform import google_secret_manager_secret.db_password projects/prj-ai-meetchi-du/secrets/meetchi-db-password
  ```
- **檢查其他潛在衝突資源**: 
  若 `terraform plan` 再次遇到 `Already exists` 報錯，將依法泡製匯入對應的資源（如其他的 Secrets 或 Service Account）。

### 3. 基礎設施部署 (Terraform Apply)
- 執行 `terraform apply -auto-approve` 完成所有基礎設施資源的建立與配置。

### 4. 資料庫遷移與服務啟動 (Phase 4)
- 執行 Alembic 資料庫遷移 Job：
  ```bash
  gcloud run jobs execute db-migrate-v19 --region=asia-southeast1
  ```
- 監控 Migration 執行狀態至成功。

---

## 🔬 驗證計劃 (Verification Plan)

### 自動與手動驗證
1. **IaC 狀態驗證**: 執行 `terraform plan` 確認顯示 `No changes. Your infrastructure matches the configuration.`。
2. **資料庫遷移驗證**: 檢查 `db-migrate-v19` 的執行日誌，確認資料庫結構升級至最新版本。
3. **服務狀態確認**: 確認 `meetchi-backend`、`meetchi-frontend` 與 `meetchi-gpu-asr` 服務均為綠燈可用狀態。
