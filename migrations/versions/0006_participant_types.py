"""Participant type, designation and institution on users and registrations (UPG-12).

Revision ID: 0006_participant_types
Revises: 0005_activity_points_hours
Create Date: 2026-10-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006_participant_types'
down_revision: Union[str, Sequence[str], None] = '0005_activity_points_hours'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = (('participant_type', 20), ('designation', 150), ('institution', 200))


def upgrade() -> None:
    for table in ('users', 'registrations'):
        for name, length in COLUMNS:
            op.add_column(table, sa.Column(name, sa.String(length=length), nullable=True))


def downgrade() -> None:
    for table in ('users', 'registrations'):
        for name, _ in reversed(COLUMNS):
            op.drop_column(table, name)
