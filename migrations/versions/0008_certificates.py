"""Certificates: one table for every certificate issued (UPG-122).

One current certificate per person, event and type (a partial unique index),
a random public number with a version for corrections, and the stored PDF's
key and SHA-256. Replaces the `verified_certificates` documents and API v1's
`certificates` documents; the verification page still reads the old ones.

Revision ID: 0008_certificates
Revises: 0007_one_active_registration
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008_certificates'
down_revision: Union[str, Sequence[str], None] = '0007_one_active_registration'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'certificates',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('number', sa.String(length=32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('is_current', sa.Boolean(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('eventId', sa.String(length=128), nullable=False),
        sa.Column('personKey', sa.String(length=320), nullable=False),
        sa.Column('recipientEmail', sa.String(length=255), nullable=True),
        sa.Column('recipientName', sa.String(length=300), nullable=False),
        sa.Column('regId', sa.String(length=128), nullable=True),
        sa.Column('certType', sa.String(length=30), nullable=False),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('dataJson', sa.Text(), nullable=False),
        sa.Column('pdfKey', sa.String(length=500), nullable=True),
        sa.Column('pdfSha256', sa.String(length=64), nullable=True),
        sa.Column('issuedAt', sa.DateTime(timezone=True), nullable=False),
        sa.Column('issuedBy', sa.String(length=255), nullable=True),
        sa.Column('emailedAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revokedAt', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revokedBy', sa.String(length=255), nullable=True),
        sa.Column('revokedReason', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_certificates_number', 'certificates', ['number'])
    op.create_index('ix_certificates_eventId', 'certificates', ['eventId'])
    op.create_index('ix_certificates_personKey', 'certificates', ['personKey'])
    op.create_index('ix_certificates_recipientEmail', 'certificates', ['recipientEmail'])
    op.create_index('uq_certificates_number_version', 'certificates', ['number', 'version'], unique=True)
    op.create_index('uq_certificates_current', 'certificates', ['eventId', 'personKey', 'certType'], unique=True,
                    postgresql_where=sa.text('is_current'), sqlite_where=sa.text('is_current'))


def downgrade() -> None:
    op.drop_table('certificates')
