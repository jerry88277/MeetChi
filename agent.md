# Agent 備忘錄

本文件紀錄 Copilot Agent 在操作此專案時需要注意的事項。

---

## Git Push 規則

- **請使用 `enterprise` remote push：**
  ```bash
  git push enterprise main
  ```

- **原因：**  
  這台機器的 Git 認證身份是 `JERRY-TAI_chimei`（企業帳號），  
  `origin` remote 指向 `jerry88277/MeetChi`（個人帳號 repo），企業帳號無寫入權限。  
  `enterprise` remote 指向 `JERRY-TAI_chimei/MeetChi`，可正常 push。

- **Remote 設定：**
  | Remote | URL | 用途 |
  |--------|-----|------|
  | `origin` | `https://github.com/jerry88277/MeetChi` | ❌ 無法 push（403） |
  | `enterprise` | `https://github.com/JERRY-TAI_chimei/MeetChi` | ✅ 正確的 push 目標 |

---
