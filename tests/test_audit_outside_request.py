"""
tests/test_audit_outside_request.py — UPG-140 on the real database layer: an
audit row written with no request (as a background task or scheduled job
writes it) is kept, as "system"; inside a request it still names the user.
"""
from tests.test_integration_flow import _login, _unique, _user


def _rows(db, action):
    return [a.to_dict() for a in db.collection('audit_log').stream() if a.to_dict().get('action') == action]


def test_an_audit_row_with_no_request_is_written_as_system(real_app):
    import threading
    from flask import has_request_context
    from utils import log_action
    flask_app, db = real_app
    action = _unique('BACKGROUND_JOB').upper()
    seen = {}

    def job():                                   # a worker thread: no request, no app context
        seen['request'] = has_request_context()
        log_action(db, action, 'nightly clean-up ran')
    thread = threading.Thread(target=job)
    thread.start()
    thread.join()
    assert seen['request'] is False
    [row] = _rows(db, action)
    assert (row['user'], row['role'], row['details']) == ('system', 'system', 'nightly clean-up ran')


def test_inside_a_request_the_row_names_the_signed_in_user(real_app):
    from utils import log_action
    flask_app, db = real_app
    spoc = f"{_unique('auditspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _login(flask_app, spoc, 'ClubSPOC')
    action = _unique('IN_REQUEST').upper()
    with flask_app.test_request_context('/'):
        from flask import session
        session['user_id'], session['role'] = spoc, 'ClubSPOC'
        log_action(db, action, 'done by hand')
    [row] = _rows(db, action)
    assert (row['user'], row['role']) == (spoc, 'ClubSPOC')
