"""Soft delete + audit logs (Sprint 2e)

Revision ID: c4d8a6b2f1e9
Revises: b3e9f2a1c8d4
Create Date: 2026-05-11

新增：
  - meetings.deleted_at  (TIMESTAMP, nullable, indexed)
  - meetings.deleted_by  (VARCHAR 255, nullable; FK to users.ad_upn SET NULL)
  - audit_logs           (新表，記錄使用者敏感行為，給 IT debug + 合規 audit)

設計原則：
  - Hard delete 改 soft delete：delete_at IS NULL 才視為「存在」
    list/get 自動 filter，DB row 保留 30 天，IT 可用 admin 端點看
  - audit_logs 記錄
      meeting.deleted / meeting.restored / meeting.regenerate_summary /
      meeting.regenerate_transcript / meeting.viewed (optional, opt-in via FE)
    每筆含：user_upn, action_type, target_type, target_id, metadata (JSON),
            ip_address, user_agent, created_at
  - 不寫 cascade purge job 進這次 migration — 由 cron job / cloud scheduler
    在 audit_logs 穩定後再加（30 天硬刪政策）

Migration idempotent：欄位/表用 IF NOT EXISTS（PG 14+）；alembic_version
更新後即使重跑 upgrade 也不會壞。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d8a6b2f1e9"
down_revision: Union[str, None] = "b3e9f2a1c8d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1. meetings 加 soft-delete 兩欄
    # ============================================================
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='meetings' AND column_name='deleted_at'
            ) THEN
                ALTER TABLE meetings ADD COLUMN deleted_at TIMESTAMP NULL;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='meetings' AND column_name='deleted_by'
            ) THEN
                ALTER TABLE meetings ADD COLUMN deleted_by VARCHAR(255) NULL;
                BEGIN
                    ALTER TABLE meetings
                        ADD CONSTRAINT fk_meetings_deleted_by
                        FOREIGN KEY (deleted_by) REFERENCES users(ad_upn)
                        ON DELETE SET NULL;
                EXCEPTION WHEN duplicate_object THEN
                    -- already exists, skip
                    NULL;
                END;
            END IF;
        END $$;
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_meetings_deleted_at ON meetings (deleted_at);")
    # 複合索引：list 端常用 (deleted_at IS NULL) + ORDER BY created_at DESC
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_active_created "
        "ON meetings (deleted_at, created_at DESC);"
    )

    # ============================================================
    # 2. audit_logs 新表
    # ============================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id              VARCHAR(36)  PRIMARY KEY,
            user_upn        VARCHAR(255) NOT NULL,
            action_type     VARCHAR(64)  NOT NULL,
            target_type     VARCHAR(32)  NOT NULL,
            target_id       VARCHAR(36),
            metadata        JSON,
            ip_address      VARCHAR(64),
            user_agent      TEXT,
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        );
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_user_upn      ON audit_logs (user_upn);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_action_type   ON audit_logs (action_type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_target_id     ON audit_logs (target_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_audit_logs_created_at    ON audit_logs (created_at);")
    # 複合：IT 常見「某 user 最近的所有刪除動作」
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_user_action_created "
        "ON audit_logs (user_upn, action_type, created_at DESC);"
    )


def downgrade() -> None:
    # audit_logs 整桌移除（rollback 用）
    op.execute("DROP INDEX IF EXISTS idx_audit_user_action_created;")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_created_at;")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_target_id;")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_action_type;")
    op.execute("DROP INDEX IF EXISTS ix_audit_logs_user_upn;")
    op.execute("DROP TABLE IF EXISTS audit_logs;")

    # meetings 撤銷 soft-delete 欄位
    op.execute("DROP INDEX IF EXISTS idx_meetings_active_created;")
    op.execute("DROP INDEX IF EXISTS ix_meetings_deleted_at;")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='meetings' AND column_name='deleted_by'
            ) THEN
                ALTER TABLE meetings DROP CONSTRAINT IF EXISTS fk_meetings_deleted_by;
                ALTER TABLE meetings DROP COLUMN deleted_by;
            END IF;
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='meetings' AND column_name='deleted_at'
            ) THEN
                ALTER TABLE meetings DROP COLUMN deleted_at;
            END IF;
        END $$;
    """)
