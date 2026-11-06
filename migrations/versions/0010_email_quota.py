"""The daily email counter (UPG-152).

One row per UTC day with the number of emails sent, so every instance stops
at EMAIL_DAILY_LIMIT and the app stays under the mail provider's free quota.

Revision ID: 0010_email_quota
Revises: 0009_naac_roles
Create Date: 2026-10-31
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010_email_quota'
down_revision: Union[str, Sequence[str], None] = '0009_naac_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Development start-up (db_pg.init_db) may have created it already
    if sa.inspect(op.get_bind()).has_table('email_quota'):
        return
    op.create_table(
        'email_quota',
        sa.Column('day', sa.String(length=10), nullable=False),
        sa.Column('sent', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('day'),
    )


def downgrade() -> None:
    op.drop_table('email_quota')
