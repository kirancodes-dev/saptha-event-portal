"""One active registration per person per event (UPG-115).

A partial unique index on registrations (event, lower(lead email)) for every
registration that isn't cancelled or waitlisted, so two forms sent at the same
instant can't both register the same person.

Before creating it, the upgrade looks for people who already hold two active
registrations for one event. If there are any it stops and lists them (it
never cancels or deletes a registration itself): cancel the extra ones, then
run the upgrade again (docs/DEPLOY.md, "Migrations").

Revision ID: 0007_one_active_registration
Revises: 0006_participant_types
Create Date: 2026-10-19
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007_one_active_registration'
down_revision: Union[str, Sequence[str], None] = '0006_participant_types'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = 'uq_registrations_active_lead'
ACTIVE = "status NOT IN ('cancelled', 'waitlisted')"


def upgrade() -> None:
    bind = op.get_bind()
    duplicates = bind.execute(sa.text(
        f'SELECT "eventId", lower("leadEmail") AS email, COUNT(*) AS n FROM registrations '
        f'WHERE {ACTIVE} GROUP BY "eventId", lower("leadEmail") HAVING COUNT(*) > 1')).fetchall()  # nosec B608 (constants)
    if duplicates:
        listed = '\n'.join(f'  event {row[0]}: {row[1]} ({row[2]} active registrations)' for row in duplicates[:50])
        raise RuntimeError(
            'Some people hold more than one active registration for the same event. Cancel the extra ones '
            '(keep one each), then run `alembic upgrade head` again:\n' + listed)
    op.create_index(INDEX, 'registrations', ['eventId', sa.text('lower("leadEmail")')], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))


def downgrade() -> None:
    op.drop_index(INDEX, table_name='registrations')
