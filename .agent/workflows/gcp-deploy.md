---
description: GCP 部署工作流程 - 自動執行 gcloud 和 terraform 指令
---

# GCP 部署工作流程

當用戶提及 `gcp-deploy` 時執行此流程。

// turbo-all

## 安全的 gcloud 指令（自動執行）

以下類型的指令會自動執行，無需手動核准：

### 查詢類指令
```bash
gcloud config list
gcloud projects list
gcloud services list
gcloud artifacts repositories list
gcloud run services list
gsutil ls
```

### 建立/啟用 API
```bash
gcloud services enable [API_NAME]
gcloud artifacts repositories create [NAME]
```

### Cloud Build
```bash
gcloud builds submit
gcloud builds list
```

### Terraform
```bash
terraform init
terraform plan
terraform apply -auto-approve
terraform output
terraform state list
```

## 部署步驟

1. 確認 gcloud 已認證
2. 啟用必要 API
3. 建立 Artifact Registry
4. 建置 Docker images
5. 執行 terraform apply
6. 驗證部署結果

## 注意事項

- `terraform destroy` 仍需手動核准
- 涉及刪除資源的指令需手動核准
- 涉及費用的操作會先顯示預估成本
