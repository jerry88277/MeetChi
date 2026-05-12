"""Drop fk_meetings_deleted_by — keep deleted_by as audit-only VARCHAR

Revision ID: e8f4a2b9d6c3
Revises: d7e3f9a2b8c1
Create Date: 2026-05-12

Root cause (2026-05-12 feedback 617bb614)：
  c4d8a6b2f1e9 把 meetings.deleted_by 建 FK 指向 users.ad_upn。
  測試帳號 pjerry88277@gmail.com 不在 users 表 → INSERT/UPDATE 違反 FK →
  delete endpoint 回 500。使用者看到「不是給使用者觀看的紀錄」。

設計決策（第一性原理）：
  deleted_by 是 **audit metadata**，定位用途是「事後查誰刪的」。
  硬 FK 帶來兩個問題：
    1. 任何 deleted_by 寫入都要求對應 user 已存在；OAuth 首次登入前先操作
       就會失敗（不必要的耦合）
    2. ON DELETE SET NULL 意味使用者帳號被刪除時，過去的 audit trail 也被
       清空——audit 的意義就是「即使對應資料消失也要保留」

最佳實踐：audit log 欄位應為 **immutable plain VARCHAR**，不掛 FK。
  類比：syslog 不會 FK 到 process table，git commit author 不 FK 到 user db。

修法：
  - DROP CONSTRAINT fk_meetings_deleted_by IF EXISTS
  - 保留 meetings.deleted_by VARCHAR(255) NULL 不動
  - 既有資料不受影響（FK 是 ON DELETE SET NULL，drop FK 不改 row 內容）

Rollback (downgrade)：
  重新加回 FK；但若 deleted_by 已有不在 users 表的值，會失敗 →
  須先 UPDATE meetings SET deleted_by = NULL WHERE deleted_by NOT IN (SELECT ad_upn FROM users)
"""

from typing import Sequence, Union

from alembic import op


revision: str = "e8f4a2b9d6c3"
down_revision: Union[str, None] = "d7e3f9a2b8c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop the FK constraint, keep column."""
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_meetings_deleted_by'
                  AND table_name = 'meetings'
            ) THEN
                ALTER TABLE meetings DROP CONSTRAINT fk_meetings_deleted_by;
            END IF;
        END$$;
        """
    )


def downgrade() -> None:
    """Re-add FK; pre-cleans orphaned values to NULL first to avoid failure."""
    op.execute(
        """
        DO $$
        BEGIN
            -- 先 null 掉孤兒 deleted_by 值，避免重新加 FK 時 violation
            UPDATE meetings
            SET deleted_by = NULL
            WHERE deleted_by IS NOT NULL
              AND deleted_by NOT IN (SELECT ad_upn FROM users);

            IF NOT EXISTS (
                SELECT 1 FROM information_schema.table_constraints
                WHERE constraint_name = 'fk_meetings_deleted_by'
            ) THEN
                ALTER TABLE meetings
                    ADD CONSTRAINT fk_meetings_deleted_by
                    FOREIGN KEY (deleted_by) REFERENCES users(ad_upn)
                    ON DELETE SET NULL;
            END IF;
        END$$;
        """
    )
