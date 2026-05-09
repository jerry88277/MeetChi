"""
Integration tests for /api/v1/feedback (Sprint 2d / PR22).

用 FastAPI TestClient + SQLite in-memory，全程不依賴外部 Gemini / Cloud SQL。

Run:
  cd apps/backend
  pytest tests/test_feedback.py -v
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """SQLite 檔案 DB（避免 :memory: per-connection 看不到 table 的坑）。
    每個 module 跑前建獨立檔，跑完 fixture cleanup 自動由 pytest 刪 tmp 目錄。"""
    db_path = tmp_path_factory.mktemp("feedback") / "test.db"
    os.environ["DATABASE_URL"] = f"sqlite:///{db_path.as_posix()}"

    from app.main import app
    from app.database import engine
    from app.models import Base

    # 確保 feedback_reports 表已建（main.py startup hook 在 lifespan event 才跑，
    # TestClient 不一定觸發；明確 create_all 一次保險）
    Base.metadata.create_all(bind=engine)

    return TestClient(app)


@pytest.fixture
def admin_upn(client) -> str:
    """確保 DB 內有一個 admin user 給 admin endpoints 用。"""
    from app.database import SessionLocal
    from app.models import User

    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.ad_upn == "admin@meetchi.test").first()
        if not admin:
            admin = User(
                id=str(uuid.uuid4()),
                ad_upn="admin@meetchi.test",
                display_name="Admin Test",
                is_admin=True,
            )
            db.add(admin)
            db.commit()
        return admin.ad_upn
    finally:
        db.close()


def _new_payload(**overrides):
    base = {
        "user_upn": "user1@company.com",
        "issue_type": "summary_wrong",
        "summary": "摘要把預算金額抓錯了，應該是 50 萬不是 5 萬",
        "severity": "workaround",
    }
    base.update(overrides)
    return base


# ============================================
# POST /api/v1/feedback
# ============================================
class TestCreateFeedback:
    def test_minimal_payload_succeeds(self, client):
        r = client.post("/api/v1/feedback", json=_new_payload())
        assert r.status_code == 201
        data = r.json()
        assert data["issue_type"] == "summary_wrong"
        assert data["status"] == "open"
        assert data["resolved_at"] is None
        assert data["created_at"] is not None

    def test_full_payload_with_metadata(self, client):
        payload = _new_payload(
            expected="預算應該抓 50 萬",
            actual="摘要寫成 5 萬",
            repro_steps="1. 上傳檔案\n2. 等摘要\n3. 看 BANT.Budget 欄",
            frequency="rare",
            attachment_url="gs://test/abc.png",
            meeting_id=None,
            page_url="https://meetchi.../dashboard/abc",
            browser_info="Chrome 130 / Windows 11",
            session_id="sess_xxx",
            frontend_version="v1.3.2",
            backend_version="v49",
            console_errors=[{"msg": "test", "stack": "..."}],
        )
        r = client.post("/api/v1/feedback", json=payload)
        assert r.status_code == 201
        d = r.json()
        assert d["expected"] == "預算應該抓 50 萬"
        assert d["page_url"] == "https://meetchi.../dashboard/abc"

    def test_missing_required_fields_422(self, client):
        # 缺 issue_type
        r = client.post("/api/v1/feedback", json={
            "user_upn": "x@y.com",
            "summary": "abcde",
            "severity": "minor",
        })
        assert r.status_code == 422

    def test_invalid_issue_type_422(self, client):
        r = client.post("/api/v1/feedback", json=_new_payload(issue_type="not_a_type"))
        assert r.status_code == 422

    def test_invalid_severity_422(self, client):
        r = client.post("/api/v1/feedback", json=_new_payload(severity="critical"))
        assert r.status_code == 422

    def test_summary_too_short_422(self, client):
        r = client.post("/api/v1/feedback", json=_new_payload(summary="abc"))
        assert r.status_code == 422


# ============================================
# GET /api/v1/feedback (user 看自己)
# ============================================
class TestListMyFeedback:
    def test_returns_only_user_own(self, client):
        # 兩個 user 各送一筆
        client.post("/api/v1/feedback", json=_new_payload(
            user_upn="alice@company.com", summary="Alice 的回報，內容超過五字",
        ))
        client.post("/api/v1/feedback", json=_new_payload(
            user_upn="bob@company.com", summary="Bob 的回報，內容超過五字",
        ))

        r = client.get("/api/v1/feedback?user_upn=alice@company.com")
        assert r.status_code == 200
        data = r.json()
        assert all(item["user_upn"] == "alice@company.com" for item in data)

    def test_pagination(self, client):
        upn = "page-test@company.com"
        for i in range(15):
            client.post("/api/v1/feedback", json=_new_payload(
                user_upn=upn, summary=f"第 {i} 筆回報，超過五字測試",
            ))
        r = client.get(f"/api/v1/feedback?user_upn={upn}&skip=0&limit=10")
        assert len(r.json()) == 10
        r2 = client.get(f"/api/v1/feedback?user_upn={upn}&skip=10&limit=10")
        assert len(r2.json()) == 5


# ============================================
# GET /api/v1/feedback/admin
# ============================================
class TestAdminListFeedback:
    def test_non_admin_403(self, client):
        r = client.get("/api/v1/feedback/admin?requester_upn=random@user.com")
        assert r.status_code == 403

    def test_admin_sees_all(self, client, admin_upn):
        # 確保有資料
        client.post("/api/v1/feedback", json=_new_payload(
            user_upn="some-user@x.com",
            summary="任意一筆，超過五字測試",
        ))
        r = client.get(f"/api/v1/feedback/admin?requester_upn={admin_upn}")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_admin_filter_by_status(self, client, admin_upn):
        r = client.get(
            f"/api/v1/feedback/admin?requester_upn={admin_upn}&status=open"
        )
        assert r.status_code == 200
        assert all(item["status"] == "open" for item in r.json())

    def test_admin_filter_by_issue_type(self, client, admin_upn):
        # 加一筆 transcript_inaccurate
        client.post("/api/v1/feedback", json=_new_payload(
            issue_type="transcript_inaccurate",
            summary="逐字稿全部跳過第二個說話者，有問題",
        ))
        r = client.get(
            f"/api/v1/feedback/admin?requester_upn={admin_upn}"
            f"&issue_type=transcript_inaccurate"
        )
        assert r.status_code == 200
        assert all(item["issue_type"] == "transcript_inaccurate" for item in r.json())


# ============================================
# GET /api/v1/feedback/{id}
# ============================================
class TestGetFeedback:
    def test_owner_can_see(self, client):
        owner = "owner@company.com"
        r = client.post("/api/v1/feedback", json=_new_payload(
            user_upn=owner, summary="owner own feedback test",
        ))
        fid = r.json()["id"]

        r2 = client.get(f"/api/v1/feedback/{fid}?requester_upn={owner}")
        assert r2.status_code == 200
        assert r2.json()["id"] == fid

    def test_other_user_403(self, client):
        owner = "private@company.com"
        r = client.post("/api/v1/feedback", json=_new_payload(
            user_upn=owner, summary="private feedback don't peek pleeeease",
        ))
        fid = r.json()["id"]
        r2 = client.get(f"/api/v1/feedback/{fid}?requester_upn=stranger@x.com")
        assert r2.status_code == 403

    def test_admin_can_see_anything(self, client, admin_upn):
        owner = "anyone@company.com"
        r = client.post("/api/v1/feedback", json=_new_payload(
            user_upn=owner, summary="admin peek allowed test entry",
        ))
        fid = r.json()["id"]
        r2 = client.get(f"/api/v1/feedback/{fid}?requester_upn={admin_upn}")
        assert r2.status_code == 200

    def test_not_found_404(self, client):
        r = client.get("/api/v1/feedback/non-existent-id?requester_upn=anyone@x.com")
        assert r.status_code == 404


# ============================================
# PATCH /api/v1/feedback/{id}
# ============================================
class TestPatchFeedback:
    def test_admin_change_status_sets_resolved_at(self, client, admin_upn):
        r = client.post("/api/v1/feedback", json=_new_payload(
            summary="will be marked fixed in test patch",
        ))
        fid = r.json()["id"]
        assert r.json()["resolved_at"] is None

        r2 = client.patch(
            f"/api/v1/feedback/{fid}?requester_upn={admin_upn}",
            json={"status": "fixed"},
        )
        assert r2.status_code == 200
        d = r2.json()
        assert d["status"] == "fixed"
        assert d["resolved_at"] is not None  # 自動填入

    def test_admin_assign_and_notes(self, client, admin_upn):
        r = client.post("/api/v1/feedback", json=_new_payload(
            summary="assignee test feedback content",
        ))
        fid = r.json()["id"]

        r2 = client.patch(
            f"/api/v1/feedback/{fid}?requester_upn={admin_upn}",
            json={
                "status": "in_progress",
                "assigned_to": "engineer@meetchi.test",
                "admin_notes": "已交給 backend team，預計本週修",
            },
        )
        assert r2.status_code == 200
        d = r2.json()
        assert d["status"] == "in_progress"
        assert d["resolved_at"] is None  # in_progress 不該觸發 resolved_at
        assert d["assigned_to"] == "engineer@meetchi.test"
        assert "backend team" in d["admin_notes"]

    def test_non_admin_forbidden(self, client):
        r = client.post("/api/v1/feedback", json=_new_payload(
            summary="cannot be patched by non admin user role",
        ))
        fid = r.json()["id"]
        r2 = client.patch(
            f"/api/v1/feedback/{fid}?requester_upn=random@user.com",
            json={"status": "wontfix"},
        )
        assert r2.status_code == 403

    def test_invalid_status_422(self, client, admin_upn):
        r = client.post("/api/v1/feedback", json=_new_payload(
            summary="invalid status patch attempt 422 test",
        ))
        fid = r.json()["id"]
        r2 = client.patch(
            f"/api/v1/feedback/{fid}?requester_upn={admin_upn}",
            json={"status": "totally_not_valid"},
        )
        assert r2.status_code == 422
