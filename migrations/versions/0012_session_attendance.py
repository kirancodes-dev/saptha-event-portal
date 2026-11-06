"""Session attendance and starred sessions (UPG-159).

One row per registration and agenda session it was scanned into, and one row
per session someone added to their own agenda.

Revision ID: 0012_session_attendance
Revises: 0011_ticket_type_sales
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012_session_attendance'
down_revision: Union[str, Sequence[str], None] = '0011_ticket_type_sales'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Development start-up (db_pg.init_db) may have created them already
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'session_attendance' not in tables:
        op.create_table(
            'session_attendance',
            sa.Column('key', sa.String(length=300), nullable=False),
            sa.Column('event_id', sa.String(length=128), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('reg_id', sa.String(length=128), nullable=False),
            sa.Column('scanned_at', sa.String(length=40), nullable=False),
            sa.Column('scanned_by', sa.String(length=255), nullable=False),
            sa.Column('over_capacity', sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint('key'),
        )
        op.create_index('ix_session_attendance_event_id', 'session_attendance', ['event_id'])
        op.create_index('ix_session_attendance_reg_id', 'session_attendance', ['reg_id'])
    if 'session_stars' not in tables:
        op.create_table(
            'session_stars',
            sa.Column('key', sa.String(length=400), nullable=False),
            sa.Column('email', sa.String(length=255), nullable=False),
            sa.Column('event_id', sa.String(length=128), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.PrimaryKeyConstraint('key'),
        )
        op.create_index('ix_session_stars_email', 'session_stars', ['email'])


def downgrade() -> None:
    op.drop_table('session_stars')
    op.drop_index('ix_session_attendance_reg_id', table_name='session_attendance')
    op.drop_index('ix_session_attendance_event_id', table_name='session_attendance')
    op.drop_table('session_attendance')
