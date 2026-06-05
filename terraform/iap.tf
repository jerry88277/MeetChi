# ============================================
# IAP + Global Load Balancer
# 參考：docs/process.md Section III
#
# ⚠️  DEPLOYMENT ORDER（重要！違反順序會造成服務中斷）：
#
#   PHASE 1 — 建立 LB 基礎設施（可立即執行）
#     terraform apply -target=google_compute_global_address.lb_ip \
#                     -target=google_compute_region_network_endpoint_group.frontend_neg \
#                     -target=google_compute_region_network_endpoint_group.backend_neg
#     → 取得 Static IP，交給 IT 設定 DNS A record
#
#   PHASE 2 — 建立完整 LB + IAP（DNS 設定後執行）
#     terraform apply
#     → SSL 憑證自動申請（DNS 指向 IP 後 5–15 分鐘生效）
#
#   PHASE 3 — 收緊 Cloud Run Ingress（SSL 生效後執行，二擇一）
#     Option A: gcloud（立即生效，不等下次 terraform apply）
#       gcloud run services update meetchi-frontend \
#         --ingress internal-and-cloud-load-balancing \
#         --region asia-southeast1
#       gcloud run services update meetchi-backend \
#         --ingress internal-and-cloud-load-balancing \
#         --region asia-southeast1
#     Option B: 修改 cloudrun.tf 的 ingress 欄位後 terraform apply
#
#   ⚠️  Phase 3 執行後，直接訪問 *.run.app URL 會 403（預期行為）
#      必須透過 meetchi.chimei.com.tw 訪問
#
# IAP OAuth Brand 注意：
#   每個 GCP 專案只有一個 Brand。若已存在需先 import：
#     BRAND=$(gcloud iap oauth-brands list --project=PROJECT_ID \
#               --format="value(name)")
#     terraform import google_iap_brand.meetchi "$BRAND"
#   若尚未建立，terraform apply 會自動建立。
#
# OAuth consent screen 需在 GCP Console 設為 Internal：
#   https://console.cloud.google.com/apis/credentials/consent
# ============================================

# ── Enable Certificate Manager API ───────────────────────────────────────────

resource "google_project_service" "certificatemanager" {
  service            = "certificatemanager.googleapis.com"
  disable_on_destroy = false
}

# ── Global Static IP ─────────────────────────────────────────────────────────
# terraform output lb_static_ip 取得 IP，交給 IT 設定 DNS A record

resource "google_compute_global_address" "lb_ip" {
  name = "meetchi-lb-ip"
}

# ── IAP OAuth Brand + Client ──────────────────────────────────────────────────
# Brand = OAuth consent screen（每個專案只有一個）
# 建立後，到 GCP Console 將 consent screen 設為 "Internal"（只允許 chimei org）

resource "google_iap_brand" "meetchi" {
  support_email     = "jerry_tai@mail.chimei.com.tw"
  application_title = "MeetChi"
}

resource "google_iap_client" "meetchi" {
  display_name = "MeetChi IAP Client"
  brand        = google_iap_brand.meetchi.name
}

# ── Serverless NEGs ───────────────────────────────────────────────────────────
# Serverless NEG 走 Google 內部網路，不需 VPC / Private Service Connect

resource "google_compute_region_network_endpoint_group" "frontend_neg" {
  name                  = "meetchi-frontend-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = "meetchi-frontend"
  }
}

resource "google_compute_region_network_endpoint_group" "backend_neg" {
  name                  = "meetchi-backend-neg"
  network_endpoint_type = "SERVERLESS"
  region                = var.region

  cloud_run {
    service = "meetchi-backend"
  }
}

# ── Backend Services ──────────────────────────────────────────────────────────
# Frontend backend service：啟用 IAP（browser 自動 Google 登入）
# Backend API backend service：無 IAP（app 層 Bearer token 管控）
#   - Cloud Run ingress=internal-and-cloud-load-balancing 確保只有 LB 能呼叫

resource "google_compute_backend_service" "frontend" {
  name                  = "meetchi-frontend-backend"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  enable_cdn            = false

  backend {
    group = google_compute_region_network_endpoint_group.frontend_neg.id
  }

  iap {
    oauth2_client_id     = google_iap_client.meetchi.client_id
    oauth2_client_secret = google_iap_client.meetchi.secret
  }

  depends_on = [google_project_service.certificatemanager]
}

resource "google_compute_backend_service" "backend_api" {
  name                  = "meetchi-backend-api"
  protocol              = "HTTP"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  enable_cdn            = false

  backend {
    group = google_compute_region_network_endpoint_group.backend_neg.id
  }

  depends_on = [google_project_service.certificatemanager]
}

# ── URL Map ───────────────────────────────────────────────────────────────────
# /api/* → backend API（不帶 IAP，app 層控管）
# /*     → frontend（帶 IAP，Google 登入）

resource "google_compute_url_map" "meetchi" {
  name            = "meetchi-url-map"
  default_service = google_compute_backend_service.frontend.id

  host_rule {
    hosts        = [var.custom_domain]
    path_matcher = "meetchi-paths"
  }

  path_matcher {
    name            = "meetchi-paths"
    default_service = google_compute_backend_service.frontend.id

    path_rule {
      paths   = ["/api/*", "/api"]
      service = google_compute_backend_service.backend_api.id
    }
  }
}

# ── HTTP → HTTPS Redirect URL Map ────────────────────────────────────────────

resource "google_compute_url_map" "http_redirect" {
  name = "meetchi-http-redirect"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

# ── Google-Managed SSL Certificate ───────────────────────────────────────────
# 需要 DNS A record 指向 lb_ip 後，GCP 自動申請並更新（免費）
# 申請期間憑證狀態 PROVISIONING，約 5–15 分鐘後變 ACTIVE

resource "google_compute_managed_ssl_certificate" "meetchi" {
  name = "meetchi-ssl-cert"

  managed {
    domains = ["${var.custom_domain}."]
  }
}

# ── HTTPS Target Proxy ────────────────────────────────────────────────────────

resource "google_compute_target_https_proxy" "meetchi" {
  name             = "meetchi-https-proxy"
  url_map          = google_compute_url_map.meetchi.id
  ssl_certificates = [google_compute_managed_ssl_certificate.meetchi.id]
}

# ── HTTP Target Proxy（只做 redirect）────────────────────────────────────────

resource "google_compute_target_http_proxy" "http_redirect" {
  name    = "meetchi-http-redirect-proxy"
  url_map = google_compute_url_map.http_redirect.id
}

# ── Forwarding Rules ──────────────────────────────────────────────────────────

resource "google_compute_global_forwarding_rule" "https" {
  name                  = "meetchi-https-rule"
  target                = google_compute_target_https_proxy.meetchi.id
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "443"
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

resource "google_compute_global_forwarding_rule" "http_redirect" {
  name                  = "meetchi-http-redirect-rule"
  target                = google_compute_target_http_proxy.http_redirect.id
  ip_address            = google_compute_global_address.lb_ip.address
  port_range            = "80"
  load_balancing_scheme = "EXTERNAL_MANAGED"
}

# ── IAP Access Control ────────────────────────────────────────────────────────
# 所有 chimei.com.tw Google 帳號可通過 IAP

resource "google_iap_web_backend_service_iam_member" "chimei_domain_frontend" {
  project             = var.project_id
  web_backend_service = google_compute_backend_service.frontend.name
  role                = "roles/iap.httpsResourceAccessor"
  member              = "domain:chimei.com.tw"
}
