"""Add rag_query_logs table for query history

Revision ID: a9b8c7d6e5f4
Revises: e8f4a2b9d6c3
Create Date: 2026-05-25

新增 rag_query_logs：使用者跨會議 RAG 查詢歷史。
  - frontend 顯示近 90 天供 user re-fire
  - backend 保留可稽核期（policy 10 年；可由 cron 清理 > 10 年的）

設計：
  - user_upn / query / answer_preview / citation_count / confidence
  - response_time_ms 供日後優化分析
  - 索引 (user_upn, created_at DESC) 為主查詢路徑
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a9b8c7d6e5f4"
down_revision: Union[str, None] = "e8f4a2b9d6c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS rag_query_logs (
            id              VARCHAR(36)  PRIMARY KEY,
            user_upn        VARCHAR(255) NOT NULL,
            query           TEXT         NOT NULL,
            answer_preview  TEXT,
            citation_count  INTEGER      DEFAULT 0,
            confidence      VARCHAR(20),
            response_time_ms INTEGER,
            created_at      TIMESTAMP    NOT NULL DEFAULT NOW()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_rag_logs_user_created "
        "ON rag_query_logs (user_upn, created_at DESC);"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_rag_logs_user_created;")
    op.execute("DROP TABLE IF EXISTS rag_query_logs;")
