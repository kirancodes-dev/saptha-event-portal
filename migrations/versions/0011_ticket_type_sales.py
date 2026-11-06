"""Seats taken per ticket type (UPG-155).

One row per event and ticket type with the number of seats taken, so a
ticket type's seat limit holds when registrations arrive at the same time.

Revision ID: 0011_ticket_type_sales
Revises: 0010_email_quota
Create Date: 2026-11-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011_ticket_type_sales'
down_revision: Union[str, Sequence[str], None] = '0010_email_quota'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Development start-up (db_pg.init_db) may have created it already
    if sa.inspect(op.get_bind()).has_table('ticket_type_sales'):
        return
    op.create_table(
        'ticket_type_sales',
        sa.Column('key', sa.String(length=300), nullable=False),
        sa.Column('sold', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('key'),
    )


def downgrade() -> None:
    op.drop_table('ticket_type_sales')
