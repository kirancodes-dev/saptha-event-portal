"""Add campuses, buildings, rooms, and venue_bookings tables

Revision ID: 0002_campuses_buildings_rooms_bookings
Revises: 0001_org_units_scoped_roles
Create Date: 2026-09-27 21:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '0002_campuses_buildings_rooms_bookings'
down_revision: Union[str, Sequence[str], None] = '0001_org_units_scoped_roles'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create campuses table
    op.create_table(
        'campuses',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('organizationId', sa.String(length=128), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('address', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organizationId'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_campuses_organizationId', 'campuses', ['organizationId'], unique=False)
    op.create_index('ix_campuses_slug', 'campuses', ['slug'], unique=True)

    # 2. Create buildings table
    op.create_table(
        'buildings',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('campusId', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=50), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['campusId'], ['campuses.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_buildings_campusId', 'buildings', ['campusId'], unique=False)

    # 3. Create rooms table
    op.create_table(
        'rooms',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('buildingId', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('roomNumber', sa.String(length=100), nullable=True),
        sa.Column('capacity', sa.Integer(), nullable=False, server_default='50'),
        sa.Column('type', sa.String(length=50), nullable=False, server_default='classroom'),
        sa.Column('facilitiesJson', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['buildingId'], ['buildings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_rooms_buildingId', 'rooms', ['buildingId'], unique=False)

    # 4. Create venue_bookings table
    op.create_table(
        'venue_bookings',
        sa.Column('id', sa.String(length=128), nullable=False),
        sa.Column('roomId', sa.String(length=128), nullable=False),
        sa.Column('eventId', UUID(as_uuid=True), nullable=True),
        sa.Column('sessionId', sa.String(length=128), nullable=True),
        sa.Column('startTime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('endTime', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='confirmed'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updatedAt', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['roomId'], ['rooms.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['eventId'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sessionId'], ['event_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_venue_bookings_roomId', 'venue_bookings', ['roomId'], unique=False)
    op.create_index('ix_venue_bookings_eventId', 'venue_bookings', ['eventId'], unique=False)
    op.create_index('idx_venue_bookings_room_time', 'venue_bookings', ['roomId', 'startTime', 'endTime', 'status'], unique=False)

    # 5. Add roomId to events table
    with op.batch_alter_table('events') as batch_op:
        batch_op.add_column(sa.Column('roomId', sa.String(length=128), nullable=True))
        batch_op.create_foreign_key('fk_events_room_id', 'rooms', ['roomId'], ['id'], ondelete='SET NULL')
        batch_op.create_index('ix_events_roomId', ['roomId'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('events') as batch_op:
        batch_op.drop_index('ix_events_roomId')
        batch_op.drop_constraint('fk_events_room_id', type_='foreignkey')
        batch_op.drop_column('roomId')

    op.drop_index('idx_venue_bookings_room_time', table_name='venue_bookings')
    op.drop_index('ix_venue_bookings_eventId', table_name='venue_bookings')
    op.drop_index('ix_venue_bookings_roomId', table_name='venue_bookings')
    op.drop_table('venue_bookings')

    op.drop_index('ix_rooms_buildingId', table_name='rooms')
    op.drop_table('rooms')

    op.drop_index('ix_buildings_campusId', table_name='buildings')
    op.drop_table('buildings')

    op.drop_index('ix_campuses_slug', table_name='campuses')
    op.drop_index('ix_campuses_organizationId', table_name='campuses')
    op.drop_table('campuses')
