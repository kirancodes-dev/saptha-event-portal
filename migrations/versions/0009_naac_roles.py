"""NAAC roles: IQAC coordinator and department admin (UPG-144).

Adds two values to the `userrole` type. On SQLite the role is a plain string
column, so there's nothing to change there. Values can't be removed from a
PostgreSQL enum, so the downgrade leaves them (unused values are harmless).

Revision ID: 0009_naac_roles
Revises: 0008_certificates
Create Date: 2026-10-20
"""
from typing import Sequence, Union

from alembic import op


revision: str = '0009_naac_roles'
down_revision: Union[str, Sequence[str], None] = '0008_certificates'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == 'postgresql':
        for value in ('IQACCoordinator', 'DepartmentAdmin'):
            op.execute(f"ALTER TYPE userrole ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    pass
