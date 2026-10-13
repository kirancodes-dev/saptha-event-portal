"""Outbox for background tasks that failed or timed out inline (UPG-18).

Revision ID: 0002_outbox
Revises: 0001_baseline
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002_outbox'
down_revision: Union[str, Sequence[str], None] = '0001_baseline'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbox',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('task_name', sa.String(length=200), nullable=False),
        sa.Column('args_json', sa.Text(), nullable=False),
        sa.Column('kwargs_json', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_index('idx_outbox_status_next', 'outbox', ['status', 'next_attempt_at'], unique=False)


def downgrade() -> None:
    op.drop_index('idx_outbox_status_next', table_name='outbox')
    op.drop_table('outbox')
