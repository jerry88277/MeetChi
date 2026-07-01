"""Add citations_json to rag_query_logs (R-A1)

Revision ID: h2c3d4e5f6a7
Revises: c6d7e8f9a0b1
Create Date: 2026-07-01

R-A1 (2026-07-01)：歷史對話載入時需還原可點擊的引用來源。
原本 rag_query_logs 只存 answer_preview + citation_count，無法還原 citations，
故載入歷史後引用全消失。此 migration 新增 citations_json TEXT 欄位存完整引用 JSON。

注意：Cloud Run 實際靠 app/main.py startup 的 ALTER TABLE ADD COLUMN IF NOT EXISTS
套用此變更（部署不自動跑 alembic）；此檔為正式記錄與本地/CI 用。
"""

from typing import Sequence, Union

from alembic import op


revision: str = "h2c3d4e5f6a7"
down_revision: Union[str, None] = "c6d7e8f9a0b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.tables WHERE table_name='rag_query_logs'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='rag_query_logs' AND column_name='citations_json'
            ) THEN
                ALTER TABLE rag_query_logs ADD COLUMN citations_json TEXT;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE rag_query_logs DROP COLUMN IF EXISTS citations_json;")
