"""Add feedback_reports table (PR22 補正 / Sprint 2d backend)

Revision ID: b3e9f2a1c8d4
Revises: f7a9d3e1c5b2
Create Date: 2026-05-09

新增資料表：
  - feedback_reports  (使用者問題回報；對齊 app/models.py FeedbackReport)

設計原則：
  - 全部 CREATE ... IF NOT EXISTS，與 prod 既有 Base.metadata.create_all 路徑共存
    （該路徑在 PR22 已在 prod 自動建表前先 idempotent 寫過，這支 migration
    用來補審計足跡 + 讓未來 alembic chain 能引用 feedback_reports）
  - 索引含 user/status/created/issue_type+status 四道，對齊 admin backlog 查詢
  - meeting_id FK 用 ON DELETE SET NULL，讓會議刪除時不連帶丟 feedback
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3e9f2a1c8d4"
down_revision: Union[str, None] = "f7a9d3e1c5b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1. 建立 feedback_reports 表（idempotent — 與 create_all 共存）
    # ============================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS feedback_reports (
            id                VARCHAR(36)  PRIMARY KEY,

            -- 階段 1 必填
            user_upn          VARCHAR(255) NOT NULL,
            issue_type        VARCHAR(50)  NOT NULL,
            summary           TEXT         NOT NULL,
            severity          VARCHAR(20)  NOT NULL,

            -- 階段 2 可選
            expected          TEXT,
            actual            TEXT,
            repro_steps       TEXT,
            frequency         VARCHAR(20),
            attachment_url    TEXT,

            -- Auto-attached metadata
            meeting_id        VARCHAR(36)  REFERENCES meetings(id) ON DELETE SET NULL,
            page_url          TEXT,
            browser_info      TEXT,
            session_id        VARCHAR(64),
            frontend_version  VARCHAR(20),
            backend_version   VARCHAR(20),
            console_errors    JSON,

            -- 後續追蹤狀態
            status            VARCHAR(20)  NOT NULL DEFAULT 'open',
            assigned_to       VARCHAR(255),
            resolved_at       TIMESTAMP,
            notify_user       BOOLEAN      NOT NULL DEFAULT TRUE,
            admin_notes       TEXT,

            -- 時間軸
            created_at        TIMESTAMP    DEFAULT NOW(),
            updated_at        TIMESTAMP    DEFAULT NOW()
        );
    """)

    # ============================================================
    # 2. 索引 — 對齊 SQLAlchemy index= flag + __table_args__
    # ============================================================
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedback_reports_id            ON feedback_reports (id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedback_reports_user_upn      ON feedback_reports (user_upn);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedback_reports_issue_type    ON feedback_reports (issue_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedback_reports_meeting_id    ON feedback_reports (meeting_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedback_reports_status        ON feedback_reports (status);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_feedback_reports_created_at    ON feedback_reports (created_at);")
    # 複合索引：admin backlog 常見查詢「依 issue_type 篩 + 看 open 案」
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_user_upn             ON feedback_reports (user_upn);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_status               ON feedback_reports (status);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_created              ON feedback_reports (created_at);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_feedback_issue_type_status    ON feedback_reports (issue_type, status);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_feedback_issue_type_status;")
    op.execute("DROP INDEX IF EXISTS idx_feedback_created;")
    op.execute("DROP INDEX IF EXISTS idx_feedback_status;")
    op.execute("DROP INDEX IF EXISTS idx_feedback_user_upn;")
    op.execute("DROP INDEX IF EXISTS ix_feedback_reports_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_feedback_reports_status;")
    op.execute("DROP INDEX IF EXISTS ix_feedback_reports_meeting_id;")
    op.execute("DROP INDEX IF EXISTS ix_feedback_reports_issue_type;")
    op.execute("DROP INDEX IF EXISTS ix_feedback_reports_user_upn;")
    op.execute("DROP INDEX IF EXISTS ix_feedback_reports_id;")
    op.execute("DROP TABLE IF EXISTS feedback_reports;")
