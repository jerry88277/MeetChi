"""Add failure_reason column to meetings

Revision ID: b5c4d3e2f1a0
Revises: a9b8c7d6e5f4
Create Date: 2026-05-25

新增 meetings.failure_reason (TEXT nullable)，給 FAILED status 補上人類可讀
的失敗原因，讓前端可以告訴使用者「為什麼失敗」+「下一步怎麼做」。

對既有 FAILED 紀錄不回填（值為 NULL → 前端顯示 generic message）。
"""

from typing import Sequence, Union

from alembic import op


revision: str = "b5c4d3e2f1a0"
down_revision: Union[str, None] = "a9b8c7d6e5f4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'meetings' AND column_name = 'failure_reason'
            ) THEN
                ALTER TABLE meetings ADD COLUMN failure_reason TEXT NULL;
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'meetings' AND column_name = 'failure_reason'
            ) THEN
                ALTER TABLE meetings DROP COLUMN failure_reason;
            END IF;
        END$$;
        """
    )
