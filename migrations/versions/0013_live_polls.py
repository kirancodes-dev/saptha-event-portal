"""Live polls and audience questions (UPG-160).

Polls with one answer per person, and questions with one upvote per person.

Revision ID: 0013_live_polls
Revises: 0012_session_attendance
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013_live_polls'
down_revision: Union[str, Sequence[str], None] = '0012_session_attendance'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Development start-up (db_pg.init_db) may have created them already
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if 'live_polls' not in tables:
        op.create_table(
            'live_polls',
            sa.Column('id', sa.String(length=32), nullable=False),
            sa.Column('event_id', sa.String(length=128), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('question', sa.String(length=300), nullable=False),
            sa.Column('options_json', sa.Text(), nullable=False),
            sa.Column('multiple', sa.Boolean(), nullable=False),
            sa.Column('status', sa.String(length=10), nullable=False),
            sa.Column('created_at', sa.String(length=40), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_live_polls_event_id', 'live_polls', ['event_id'])
    if 'live_poll_votes' not in tables:
        op.create_table(
            'live_poll_votes',
            sa.Column('key', sa.String(length=300), nullable=False),
            sa.Column('poll_id', sa.String(length=32), nullable=False),
            sa.Column('choices_json', sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint('key'),
        )
        op.create_index('ix_live_poll_votes_poll_id', 'live_poll_votes', ['poll_id'])
    if 'live_questions' not in tables:
        op.create_table(
            'live_questions',
            sa.Column('id', sa.String(length=32), nullable=False),
            sa.Column('event_id', sa.String(length=128), nullable=False),
            sa.Column('session_id', sa.String(length=64), nullable=False),
            sa.Column('text', sa.String(length=500), nullable=False),
            sa.Column('asked_by', sa.String(length=255), nullable=False),
            sa.Column('status', sa.String(length=10), nullable=False),
            sa.Column('created_at', sa.String(length=40), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_live_questions_event_id', 'live_questions', ['event_id'])
    if 'live_question_votes' not in tables:
        op.create_table(
            'live_question_votes',
            sa.Column('key', sa.String(length=300), nullable=False),
            sa.Column('question_id', sa.String(length=32), nullable=False),
            sa.PrimaryKeyConstraint('key'),
        )
        op.create_index('ix_live_question_votes_question_id', 'live_question_votes', ['question_id'])


def downgrade() -> None:
    for table, index in (('live_question_votes', 'ix_live_question_votes_question_id'),
                         ('live_questions', 'ix_live_questions_event_id'),
                         ('live_poll_votes', 'ix_live_poll_votes_poll_id'),
                         ('live_polls', 'ix_live_polls_event_id')):
        op.drop_index(index, table_name=table)
        op.drop_table(table)
