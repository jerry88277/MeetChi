"""add speaker_mappings to meetings

Revision ID: a1b2c3d4e5f6
Revises: 9fb3cc7a43bb
Create Date: 2026-03-12 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '9fb3cc7a43bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('meetings', sa.Column('speaker_mappings', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('meetings', 'speaker_mappings')
