"""002 access control users and meeting participants

Revision ID: 002_access_control
Revises: 001_enable_pgvector
Create Date: 2026-04-10

新增資料表：
  - users                 (AD 帳號登錄表)
  - meeting_participants  (會議存取控制關聯表)
修改資料表：
  - meetings              (新增 owner_upn 欄位)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '002_access_control'
down_revision = '001_enable_pgvector'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ============================================================
    # 1. 建立 users 表 (必須在 meetings 前，因 meetings 會 FK 到它)
    # ============================================================
    op.create_table(
        'users',
        sa.Column('id',            sa.String(36),  primary_key=True),
        sa.Column('ad_upn',        sa.String(255), nullable=False),
        sa.Column('display_name',  sa.String(255), nullable=True),
        sa.Column('department',    sa.String(255), nullable=True),
        sa.Column('is_admin',      sa.Boolean,     nullable=False, server_default='false'),
        sa.Column('created_at',    sa.DateTime,    nullable=False, server_default=sa.func.now()),
        sa.Column('last_login_at', sa.DateTime,    nullable=True),
    )
    # 唯一索引（UPN 是查詢的主要 lookup key）
    op.create_index('idx_users_ad_upn', 'users', ['ad_upn'], unique=True)

    # ============================================================
    # 2. meetings 表新增 owner_upn 欄位
    # ============================================================
    op.add_column(
        'meetings',
        sa.Column('owner_upn', sa.String(255), sa.ForeignKey('users.ad_upn'), nullable=True, index=True)
    )
    op.create_index('idx_meetings_owner_upn', 'meetings', ['owner_upn'])

    # ============================================================
    # 3. 建立 meeting_participants 表
    # ============================================================
    op.create_table(
        'meeting_participants',
        sa.Column('id',             sa.String(36),  primary_key=True),
        sa.Column('meeting_id',     sa.String(36),  sa.ForeignKey('meetings.id',  ondelete='CASCADE'), nullable=False),
        sa.Column('user_upn',       sa.String(255), sa.ForeignKey('users.ad_upn', ondelete='CASCADE'), nullable=False),

        # MECE 存取角色
        sa.Column('role',           sa.Enum('owner', 'participant', 'viewer',      name='participantrole'), nullable=False, server_default='participant'),
        # 稽核用：存取來源
        sa.Column('access_source',  sa.Enum('upload', 'participant', 'granted',   name='accesssource'),    nullable=False, server_default='participant'),

        # 稽核欄位
        sa.Column('granted_at',     sa.DateTime,    nullable=False, server_default=sa.func.now()),
        sa.Column('granted_by_upn', sa.String(255), sa.ForeignKey('users.ad_upn'), nullable=True),
    )

    # 索引（存取控制查詢的效能關鍵）
    op.create_index('idx_mp_user_upn',    'meeting_participants', ['user_upn'])
    op.create_index('idx_mp_meeting_id',  'meeting_participants', ['meeting_id'])
    op.create_index('idx_mp_upn_meeting', 'meeting_participants', ['user_upn', 'meeting_id'])

    # 複合唯一：同一人對同一場會議只能有一筆記錄
    op.create_index(
        'uq_meeting_participant',
        'meeting_participants',
        ['meeting_id', 'user_upn'],
        unique=True
    )


def downgrade() -> None:
    # 逆序撤銷
    op.drop_index('uq_meeting_participant',  table_name='meeting_participants')
    op.drop_index('idx_mp_upn_meeting',      table_name='meeting_participants')
    op.drop_index('idx_mp_meeting_id',       table_name='meeting_participants')
    op.drop_index('idx_mp_user_upn',         table_name='meeting_participants')
    op.drop_table('meeting_participants')

    op.drop_index('idx_meetings_owner_upn',  table_name='meetings')
    op.drop_column('meetings', 'owner_upn')

    op.drop_index('idx_users_ad_upn', table_name='users')
    op.drop_table('users')

    # 清理 Enum types (PostgreSQL)
    sa.Enum(name='participantrole').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='accesssource').drop(op.get_bind(), checkfirst=True)
