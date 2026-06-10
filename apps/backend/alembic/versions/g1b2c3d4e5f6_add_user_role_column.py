"""Add role column to users table

Revision ID: g1b2c3d4e5f6
Revises: (latest)
Create Date: 2026-06-10
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = 'g1b2c3d4e5f6'
down_revision = None  # Will be set manually if needed
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('role', sa.String(20), nullable=False, server_default='user'))


def downgrade() -> None:
    op.drop_column('users', 'role')
