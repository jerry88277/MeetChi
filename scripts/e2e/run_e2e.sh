#!/usr/bin/env bash
# run_e2e.sh — MeetChi E2E 整合測試執行器
#
# 自動取得 gcloud identity token 繞過 Cloud Run IAM，
# 無需申請 Org Policy 例外或設定 LB，開發者可直接對 Cloud Run 原生 URL 測試。
#
# 前提：jerry_tai@mail.chimei.com.tw 已有 meetchi-backend 的 run.invoker 權限
#       (參考 docs/process.md — cloudrun.tf IAM 設定)
#
# 用法：
#   bash scripts/e2e/run_e2e.sh                         # 使用預設測試音檔
#   bash scripts/e2e/run_e2e.sh path/to/audio.m4a       # 指定音檔
#   MEETCHI_BACKEND_URL=https://... bash scripts/e2e/run_e2e.sh   # 指定後端 URL
#
# Microsoft OAuth 串接完成後，改用 --token <ms_access_token> 參數
# （需後端 auth.py 支援 MS JWT 驗證）

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

BACKEND_URL="${MEETCHI_BACKEND_URL:-https://meetchi-backend-705495828555.asia-southeast1.run.app}"
AUDIO_FILE="${1:-}"

echo "============================================================"
echo "  MeetChi E2E Integration Test"
echo "  Backend: ${BACKEND_URL}"
echo "============================================================"
echo ""

# ── 1. 確認 gcloud 已登入 ─────────────────────────────────────────────────────
ACTIVE_ACCOUNT=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
if [[ -z "$ACTIVE_ACCOUNT" ]]; then
    echo "❌ gcloud 未登入。請先執行: gcloud auth login"
    exit 1
fi
echo "🔐 gcloud 帳號: ${ACTIVE_ACCOUNT}"

# ── 2. 取得 Identity Token ────────────────────────────────────────────────────
echo "🔑 取得 Identity Token..."
TOKEN=$(gcloud auth print-identity-token --audiences="${BACKEND_URL}" 2>/dev/null)
if [[ -z "$TOKEN" ]]; then
    echo "❌ Identity Token 取得失敗"
    echo "   確認 ${ACTIVE_ACCOUNT} 有 meetchi-backend run.invoker 權限"
    exit 1
fi
echo "   ✅ Token 取得成功 (${TOKEN:0:20}...)"
echo ""

# ── 3. Health Check ───────────────────────────────────────────────────────────
echo "🏥 Health check..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${TOKEN}" \
    "${BACKEND_URL}/health" --max-time 15)
if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "❌ Health check 失敗 (HTTP ${HTTP_STATUS})"
    echo "   若 Cloud Run 已 Scale to Zero，稍待 30 秒後重試（冷啟動）"
    exit 1
fi
echo "   ✅ Backend 健康 (HTTP ${HTTP_STATUS})"
echo ""

# ── 4. 執行 E2E 測試 ──────────────────────────────────────────────────────────
cd "${REPO_ROOT}"

PYTHON_CMD="python3"
if ! command -v python3 &>/dev/null; then
    PYTHON_CMD="python"
fi

ARGS=()
if [[ -n "$AUDIO_FILE" ]]; then
    ARGS+=("$AUDIO_FILE")
fi

MEETCHI_ID_TOKEN="${TOKEN}" \
MEETCHI_BACKEND_URL="${BACKEND_URL}" \
"${PYTHON_CMD}" scripts/e2e/test_upload.py "${ARGS[@]+"${ARGS[@]}"}"
