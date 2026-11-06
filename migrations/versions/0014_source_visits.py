"""Visits per share link (UPG-162).

One row per event and share-link code, holding only a count.

Revision ID: 0014_source_visits
Revises: 0013_live_polls
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0014_source_visits'
down_revision: Union[str, Sequence[str], None] = '0013_live_polls'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Development start-up (db_pg.init_db) may have created it already
    if 'source_visits' not in set(sa.inspect(op.get_bind()).get_table_names()):
        op.create_table(
            'source_visits',
            sa.Column('key', sa.String(length=200), nullable=False),
            sa.Column('event_id', sa.String(length=128), nullable=False),
            sa.Column('code', sa.String(length=40), nullable=False),
            sa.Column('visits', sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint('key'),
        )
        op.create_index('ix_source_visits_event_id', 'source_visits', ['event_id'])


def downgrade() -> None:
    op.drop_index('ix_source_visits_event_id', table_name='source_visits')
    op.drop_table('source_visits')
