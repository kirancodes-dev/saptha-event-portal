"""
tests/test_one_registration.py — UPG-115: one active registration per person
per event, kept by the database (a partial unique index, migration 0007), not
only by the form's check. Two forms for one person sent at the same instant
(two tabs) give one registration, and the other is told they're already
registered; a cancelled registration doesn't block registering again; a paid
order the database refuses is kept for a refund, not lost; the waitlist skips
someone already registered; the migration refuses to run over duplicates.
Run with TEST_DATABASE_URL to check it on PostgreSQL.
"""
import os
import subprocess
import sys
import threading

import pytest

from tests.test_forms_guard import _form, _free_event, _regs_for
from tests.test_integration_flow import _unique
from tests.test_paid_events import _checkout, _verify, paid, rzp  # noqa: F401  (fixtures)
from utils import AlreadyRegistered, create_registration

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _two_tabs(d, event_id, email):
    """Two different forms (two submission ids) for one person, sent at once."""
    start, answers = threading.Barrier(2), []

    def send():
        client = d['app'].test_client()
        start.wait()
        resp = client.post(f'/forms/submit/{event_id}', data=_form(email, _unique('tab')), follow_redirects=True)
        answers.append(resp.get_data(as_text=True))
    threads = [threading.Thread(target=send) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    return answers


@pytest.mark.parametrize('attempt', range(5))
def test_two_tabs_at_once_give_one_registration(paid, attempt):  # noqa: F811
    d = paid
    event_id = _free_event(d)
    email = f"{_unique('tabs')}@test.edu"
    answers = _two_tabs(d, event_id, email)
    assert len(_regs_for(d, event_id, email)) == 1
    told = [a for a in answers if "already registered for this event" in a]
    assert len(answers) == 2 and len(told) == 1, [a[:200] for a in answers]


def test_the_database_refuses_a_second_active_registration_in_any_case(paid):  # noqa: F811
    d = paid
    event_id = _free_event(d)
    email = f"{_unique('Case')}@test.edu"
    create_registration(d['db'], _unique('REG'), {'event_id': event_id, 'lead_email': email.lower(),
                                                  'lead_name': 'First', 'status': 'Confirmed'})
    with pytest.raises(AlreadyRegistered):
        create_registration(d['db'], _unique('REG'), {'event_id': event_id, 'lead_email': email.upper(),
                                                      'lead_name': 'Second', 'status': 'Confirmed'})
    assert len([r for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream()]) == 1


def test_registrations_without_an_email_dont_block_each_other(paid):  # noqa: F811
    """Old or imported rows with no lead email name nobody, so the rule doesn't apply."""
    d = paid
    event_id = _free_event(d)
    for _ in range(2):
        d['db'].collection('registrations').document(_unique('REG')).set({'event_id': event_id, 'status': 'Confirmed',
                                                                           'user_id': f"{_unique('anon')}@test.edu"})
    assert len(list(d['db'].collection('registrations').where('event_id', '==', event_id).stream())) == 2


def test_a_cancelled_registration_doesnt_block_registering_again(paid):  # noqa: F811
    d = paid
    event_id = _free_event(d)
    email = f"{_unique('again')}@test.edu"
    first = _unique('REG')
    create_registration(d['db'], first, {'event_id': event_id, 'lead_email': email, 'lead_name': 'A',
                                         'status': 'Confirmed'})
    d['db'].collection('registrations').document(first).update({'status': 'Cancelled'})
    create_registration(d['db'], _unique('REG'), {'event_id': event_id, 'lead_email': email, 'lead_name': 'A',
                                                  'status': 'Confirmed'})
    statuses = sorted(str(r.to_dict().get('status')).lower()
                      for r in d['db'].collection('registrations').where('event_id', '==', event_id).stream())
    assert statuses == ['cancelled', 'confirmed']


def test_a_paid_order_the_database_refuses_is_kept_for_a_refund(paid, monkeypatch):  # noqa: F811
    d = paid
    client, email, order = _checkout(d)
    # The other tab's registration landed between this payer's check and their write
    create_registration(d['db'], _unique('REG'), {'event_id': d['event_id'], 'lead_email': email,
                                                  'lead_name': 'Other Tab', 'status': 'Confirmed'})
    import routes_payment
    monkeypatch.setattr(routes_payment, '_existing_registration', lambda *a, **k: (None, None))
    resp = _verify(client, d, order['order_id'], f"pay_{_unique('x')}")
    assert resp.status_code == 202 and resp.get_json()['recorded'] is True
    from services_payments import get_order, unmatched_orders
    kept = get_order(order['order_id'])
    assert kept['status'] == 'paid' and not kept['reg_id'] and kept['failure_reason'] == 'already_registered'
    assert order['order_id'] in {o['id'] for o in unmatched_orders()}   # on the admin's payments page to refund
    assert len([r for r in d['db'].collection('registrations').where('event_id', '==', d['event_id']).stream()
                if r.to_dict().get('lead_email') == email]) == 1


def test_the_waitlist_skips_someone_already_registered(paid):  # noqa: F811
    d = paid
    event_id = _free_event(d)
    first, second = f"{_unique('wlfirst')}@test.edu", f"{_unique('wlsecond')}@test.edu"
    create_registration(d['db'], _unique('REG'), {'event_id': event_id, 'lead_email': first, 'lead_name': 'In',
                                                  'status': 'Confirmed'})
    for n, email in enumerate((first, second)):
        d['db'].collection('waitlists').document(_unique('WL')).set({
            'event_id': event_id, 'user_email': email, 'email': email, 'name': email.split('@')[0],
            'status': 'waiting', 'position': n + 1, 'joined_at': f'2026-10-0{n + 1}T10:00:00+00:00'})
    from routes_waitlist import auto_promote
    result = auto_promote(d['db'], event_id)
    assert result and result['user_email'] == second
    entries = {w.to_dict()['user_email']: w.to_dict()['status']
               for w in d['db'].collection('waitlists').where('event_id', '==', event_id).stream()}
    assert entries == {first: 'already_registered', second: 'promoted'}


# ── The migration ───────────────────────────────────────────────────────────

SEED_DUPLICATES = r'''
from db_adapter import SQLFirestoreAdapter
db = SQLFirestoreAdapter()
db.collection("events").document("evt-dup").set({"title": "Dup", "date": "2031-01-01", "status": "registration_open",
                                                 "category": "Technical"})
db.collection("registrations").document("reg-a").set({"event_id": "evt-dup", "lead_email": "twice@test.edu",
                                                    "lead_name": "Twice", "status": "Confirmed"})
print("SEEDED")
'''


def _run(args, url):
    env = dict(os.environ, DATABASE_URL=url, FLASK_ENV='development', CLOUD_SQL_INSTANCE='')
    env.pop('TEST_DATABASE_URL', None)
    return subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True, timeout=300)


def test_the_migration_refuses_to_run_over_duplicates(tmp_path):
    url = f"sqlite:///{tmp_path / 'dups.db'}"
    assert _run([sys.executable, '-m', 'alembic', 'upgrade', '0006_participant_types'], url).returncode == 0
    seeded = _run([sys.executable, '-c', SEED_DUPLICATES], url)
    assert 'SEEDED' in seeded.stdout, seeded.stderr[-1500:]
    # A database from before 0007 could hold a duplicate: make one (development
    # start-up adds the index, so take it off first, as the old database didn't have it)
    import sqlite3
    with sqlite3.connect(tmp_path / 'dups.db') as conn:
        conn.execute('DROP INDEX IF EXISTS uq_registrations_active_lead')
        conn.execute('CREATE TEMP TABLE copy AS SELECT * FROM registrations')
        conn.execute("UPDATE copy SET id = 'ffffffffffffffffffffffffffffffff'")
        conn.execute('INSERT INTO registrations SELECT * FROM copy')
    refused = _run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], url)
    assert refused.returncode != 0 and 'more than one active registration' in refused.stderr
    assert 'twice@test.edu' in refused.stderr
    # Once the extra one is cancelled, it goes through
    with sqlite3.connect(tmp_path / 'dups.db') as conn:
        conn.execute("UPDATE registrations SET status = 'cancelled' WHERE id = 'ffffffffffffffffffffffffffffffff'")
    done = _run([sys.executable, '-m', 'alembic', 'upgrade', 'head'], url)
    assert done.returncode == 0, done.stderr[-1500:]
