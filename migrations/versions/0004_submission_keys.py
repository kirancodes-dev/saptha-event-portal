"""Submission keys: a form sent twice registers once (UPG-26).

Revision ID: 0004_submission_keys
Revises: 0003_native_document_store
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004_submission_keys'
down_revision: Union[str, Sequence[str], None] = '0003_native_document_store'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'submission_keys',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('result', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )
    op.create_index(op.f('ix_submission_keys_created_at'), 'submission_keys', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_submission_keys_created_at'), table_name='submission_keys')
    op.drop_table('submission_keys')
