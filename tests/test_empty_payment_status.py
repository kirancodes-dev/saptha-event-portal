"""
tests/test_empty_payment_status.py — UPG-44 on the real database layer (run it
on SQLite and, with TEST_DATABASE_URL, on PostgreSQL): an empty or missing
payment status reads back as written, not as the enum column's default
'unpaid'; an explicit 'unpaid' still reads 'unpaid', and filtering on it finds
only the explicit one.
"""
from tests.test_integration_flow import _create_event, _login, _unique, _user


def test_empty_and_missing_payment_status_read_back_as_written(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('paystat')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    event_id = _create_event(_login(flask_app, spoc, 'ClubSPOC'), db, _unique('Status Day'), '2030-06-01', team=False)
    base = {'event_id': event_id, 'lead_name': 'P S', 'status': 'Confirmed'}
    rows = {
        'empty': dict(base, lead_email=f"{_unique('empty')}@test.edu", payment_status=''),
        'missing': dict(base, lead_email=f"{_unique('missing')}@test.edu"),
        'unpaid': dict(base, lead_email=f"{_unique('unpaid')}@test.edu", payment_status='unpaid'),
        'paid': dict(base, lead_email=f"{_unique('paid')}@test.edu", payment_status='Paid'),
    }
    ids = {}
    for key, data in rows.items():
        ids[key] = _unique('REG')
        db.collection('registrations').document(ids[key]).set(data)
    read = {k: db.collection('registrations').document(v).get().to_dict() for k, v in ids.items()}

    assert read['empty']['payment_status'] == ''
    assert 'payment_status' not in read['missing'] or read['missing']['payment_status'] in (None, '')
    assert read['missing'].get('payment_status') != 'unpaid'
    assert read['unpaid']['payment_status'] == 'unpaid'
    assert read['paid']['payment_status'] == 'Paid'

    unpaid = [d.to_dict()['lead_email'] for d in db.collection('registrations')
              .where('event_id', '==', event_id).where('payment_status', '==', 'unpaid').stream()]
    assert unpaid == [rows['unpaid']['lead_email']]

    # Writing 'unpaid' over the empty one reads 'unpaid'
    db.collection('registrations').document(ids['empty']).update({'payment_status': 'unpaid'})
    assert db.collection('registrations').document(ids['empty']).get().to_dict()['payment_status'] == 'unpaid'
