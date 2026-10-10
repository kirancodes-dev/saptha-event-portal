"""Activity points and hours for events (UPG-11).

Revision ID: 0005_activity_points_hours
Revises: 0004_submission_keys
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005_activity_points_hours'
down_revision: Union[str, Sequence[str], None] = '0004_submission_keys'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('events', sa.Column('activity_points', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('events', sa.Column('activity_hours', sa.Float(), nullable=False, server_default='0.0'))


def downgrade() -> None:
    op.drop_column('events', 'activity_hours')
    op.drop_column('events', 'activity_points')
