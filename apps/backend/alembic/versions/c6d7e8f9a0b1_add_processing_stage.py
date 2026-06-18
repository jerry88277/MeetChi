"""Add processing_stage column to meetings

Revision ID: c6d7e8f9a0b1
Revises: b5c4d3e2f1a0
Create Date: 2026-06-18

新增 meetings.processing_stage (VARCHAR(20) nullable)，追蹤會議在處理 pipeline
中的精確階段：queued → transcribing → summarizing → NULL (完成)。
讓前端可以顯示「排隊中」「轉錄中」「生成摘要中」而非只有「處理中」。
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "b5c4d3e2f1a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'meetings' AND column_name = 'processing_stage'
            ) THEN
                ALTER TABLE meetings ADD COLUMN processing_stage VARCHAR(20) NULL;
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
                WHERE table_name = 'meetings' AND column_name = 'processing_stage'
            ) THEN
                ALTER TABLE meetings DROP COLUMN processing_stage;
            END IF;
        END$$;
        """
    )
