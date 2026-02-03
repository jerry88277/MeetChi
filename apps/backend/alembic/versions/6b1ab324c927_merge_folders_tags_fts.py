"""merge_folders_tags_fts

Revision ID: 6b1ab324c927
Revises: 002_add_folders_tags_fts, 4876102672d1
Create Date: 2026-02-02 13:58:14.337118

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b1ab324c927'
down_revision: Union[str, None] = ('002_add_folders_tags_fts', '4876102672d1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
