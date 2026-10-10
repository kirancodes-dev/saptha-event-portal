"""The native document store's table (UPG-58).

Revision ID: 0003_native_document_store
Revises: 0002_outbox
Create Date: 2026-10-10

Databases created before migrations already have this table (the adapter
created it at runtime), so it's created only when missing.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003_native_document_store'
down_revision: Union[str, Sequence[str], None] = '0002_outbox'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if 'native_document_store' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'native_document_store',
        sa.Column('collection_name', sa.String(length=64), nullable=False),
        sa.Column('doc_id', sa.String(length=128), nullable=False),
        sa.Column('data_json', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('collection_name', 'doc_id'),
    )


def downgrade() -> None:
    op.drop_table('native_document_store')
