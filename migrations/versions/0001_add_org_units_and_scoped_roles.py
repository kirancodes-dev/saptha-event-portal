"""Add org_units and scoped roles

Revision ID: 0001_org_units_scoped_roles
Revises: None
Create Date: 2026-09-27 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001_org_units_scoped_roles'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create org_units table
    op.create_table(
        'org_units',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('organizationId', sa.String(length=128), nullable=False),
        sa.Column('parentId', sa.String(length=128), nullable=True),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organizationId'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parentId'], ['org_units.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_org_units_organizationId', 'org_units', ['organizationId'], unique=False)
    op.create_index('ix_org_units_parentId', 'org_units', ['parentId'], unique=False)
    op.create_index('ix_org_units_slug', 'org_units', ['slug'], unique=False)

    # 2. Create role_assignments table
    op.create_table(
        'role_assignments',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('userId', sa.String(length=255), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column('scopeType', sa.String(length=50), nullable=False),
        sa.Column('scopeId', sa.String(length=128), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_role_assignments_userId', 'role_assignments', ['userId'], unique=False)
    op.create_index('ix_role_assignments_scopeId', 'role_assignments', ['scopeId'], unique=False)
    op.create_index('idx_role_user_scope', 'role_assignments', ['userId', 'scopeType', 'scopeId'], unique=False)

    # 3. Add orgUnitId to events table
    with op.batch_alter_table('events') as batch_op:
        batch_op.add_column(sa.Column('orgUnitId', sa.String(length=128), nullable=True))
        batch_op.create_foreign_key('fk_events_org_unit_id', 'org_units', ['orgUnitId'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_events_orgUnitId', ['orgUnitId'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('events') as batch_op:
        batch_op.drop_index('ix_events_orgUnitId')
        batch_op.drop_constraint('fk_events_org_unit_id', type_='foreignkey')
        batch_op.drop_column('orgUnitId')

    op.drop_index('idx_role_user_scope', table_name='role_assignments')
    op.drop_index('ix_role_assignments_scopeId', table_name='role_assignments')
    op.drop_index('ix_role_assignments_userId', table_name='role_assignments')
    op.drop_table('role_assignments')

    op.drop_index('ix_org_units_slug', table_name='org_units')
    op.drop_index('ix_org_units_parentId', table_name='org_units')
    op.drop_index('ix_org_units_organizationId', table_name='org_units')
    op.drop_table('org_units')
