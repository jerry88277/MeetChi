"""Add access control tables: users, meeting_participants, owner_upn

Revision ID: f7a9d3e1c5b2
Revises: a1b2c3d4e5f6
Create Date: 2026-04-10

新增資料表：
  - users                 (AD 帳號登錄表，以 UPN 為主鍵)
  - meeting_participants  (會議存取控制關聯表 - MemPlace Isolation)
修改資料表：
  - meetings              (新增 owner_upn 欄位)

設計原則：
  - UPN (userPrincipalName) 為 AD/Entra ID 的標準身分識別鍵
  - 單一用戶查詢範圍由 meeting_participants JOIN 限制，非全庫掃描
  - idx_mp_user_upn 確保毫秒級 lookup 效能
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a9d3e1c5b2'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1. 啟用 pgvector（冪等，若已存在則跳過）
    # ============================================================
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ============================================================
    # 2. 建立 Enum 類型（PostgreSQL）
    # ============================================================
    participantrole = sa.Enum(
        'owner', 'participant', 'viewer',
        name='participantrole',
        create_type=False
    )
    accesssource = sa.Enum(
        'upload', 'participant', 'granted',
        name='accesssource',
        create_type=False
    )
    # 在 PG 中先建立 Enum 類型（若不存在）
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'participantrole') THEN
                CREATE TYPE participantrole AS ENUM ('owner', 'participant', 'viewer');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accesssource') THEN
                CREATE TYPE accesssource AS ENUM ('upload', 'participant', 'granted');
            END IF;
        END $$;
    """)

    # ============================================================
    # 3. 建立 users 表（必須在 meetings 之前，因為 meetings.owner_upn FK 指向它）
    # ============================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            VARCHAR(36)  PRIMARY KEY,
            ad_upn        VARCHAR(255) NOT NULL UNIQUE,
            display_name  VARCHAR(255),
            department    VARCHAR(255),
            is_admin      BOOLEAN      NOT NULL DEFAULT FALSE,
            created_at    TIMESTAMP    NOT NULL DEFAULT NOW(),
            last_login_at TIMESTAMP
        );
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_users_ad_upn ON users (ad_upn);
    """)

    # ============================================================
    # 4. meetings 表新增 owner_upn 欄位（Safe — 若已存在則跳過）
    # ============================================================
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'meetings' AND column_name = 'owner_upn'
            ) THEN
                ALTER TABLE meetings ADD COLUMN owner_upn VARCHAR(255);
                ALTER TABLE meetings ADD CONSTRAINT fk_meetings_owner_upn
                    FOREIGN KEY (owner_upn) REFERENCES users(ad_upn);
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_meetings_owner_upn ON meetings (owner_upn);
    """)

    # ============================================================
    # 5. 建立 meeting_participants 表（核心存取控制表）
    # ============================================================
    op.execute("""
        CREATE TABLE IF NOT EXISTS meeting_participants (
            id             VARCHAR(36)  PRIMARY KEY,
            meeting_id     VARCHAR(36)  NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
            user_upn       VARCHAR(255) NOT NULL REFERENCES users(ad_upn) ON DELETE CASCADE,
            role           participantrole NOT NULL DEFAULT 'participant',
            access_source  accesssource    NOT NULL DEFAULT 'participant',
            granted_at     TIMESTAMP    NOT NULL DEFAULT NOW(),
            granted_by_upn VARCHAR(255) REFERENCES users(ad_upn),
            CONSTRAINT uq_meeting_participant UNIQUE (meeting_id, user_upn)
        );
    """)

    # 效能關鍵索引（MemPlace 隔離查詢的依賴）
    op.execute("CREATE INDEX IF NOT EXISTS idx_mp_user_upn    ON meeting_participants (user_upn);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mp_meeting_id  ON meeting_participants (meeting_id);")
    op.execute("CREATE INDEX IF NOT EXISTS idx_mp_upn_meeting ON meeting_participants (user_upn, meeting_id);")


def downgrade() -> None:
    # 逆序撤銷所有變更
    op.execute("DROP INDEX IF EXISTS idx_mp_upn_meeting;")
    op.execute("DROP INDEX IF EXISTS idx_mp_meeting_id;")
    op.execute("DROP INDEX IF EXISTS idx_mp_user_upn;")
    op.execute("DROP TABLE IF EXISTS meeting_participants;")

    op.execute("DROP INDEX IF EXISTS idx_meetings_owner_upn;")
    op.execute("""
        ALTER TABLE meetings
        DROP CONSTRAINT IF EXISTS fk_meetings_owner_upn;
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'meetings' AND column_name = 'owner_upn'
            ) THEN
                ALTER TABLE meetings DROP COLUMN owner_upn;
            END IF;
        END $$;
    """)

    op.execute("DROP INDEX IF EXISTS idx_users_ad_upn;")
    op.execute("DROP TABLE IF EXISTS users;")

    op.execute("DROP TYPE IF EXISTS participantrole;")
    op.execute("DROP TYPE IF EXISTS accesssource;")
