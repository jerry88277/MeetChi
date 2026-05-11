"""Add is_confidential flag to meetings (Sprint 2e / Phase 1)

Revision ID: d7e3f9a2b8c1
Revises: c4d8a6b2f1e9
Create Date: 2026-05-11

Phase 1 of 機密會議 feature：先卡 schema + 上傳 UI；Phase 2 才在前端
做複製鎖、浮水印、右鍵攔截；Phase 3 才補後端 audio_url 短期 signed URL
與 admin-only restore 等保護。

設計：
  - is_confidential BOOLEAN NOT NULL DEFAULT FALSE
  - 既有資料預設為非機密（向後相容）
  - 索引：低基數欄位（只有 TRUE/FALSE）不建一般 btree，但 IT 若要快速
    撈出所有機密會議，partial index 比較有效率
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7e3f9a2b8c1"
down_revision: Union[str, None] = "c4d8a6b2f1e9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='meetings' AND column_name='is_confidential'
            ) THEN
                ALTER TABLE meetings
                ADD COLUMN is_confidential BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
        END $$;
    """)
    # Partial index — 只 index TRUE 那群 (低基數 + 偏頻查詢用)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meetings_confidential "
        "ON meetings (id) WHERE is_confidential = TRUE;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_meetings_confidential;")
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='meetings' AND column_name='is_confidential'
            ) THEN
                ALTER TABLE meetings DROP COLUMN is_confidential;
            END IF;
        END $$;
    """)
