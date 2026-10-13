"""
tests/test_event_journey_real_db.py — BLK-05 on the real SQL database layer:
one competitive event from registration to certificate, through the same
routes the screens use, plus the guard that keeps tests away from real
outbound services.
"""
import datetime
import os

from tests.conftest import OUTBOUND_CREDENTIALS
from tests.test_integration_flow import _create_event, _login, _unique, _user


def test_register_checkin_score_feedback_certificate(real_app):
    flask_app, db = real_app
    spoc = f"{_unique('spoc')}@test.edu"
    judge = f"{_unique('judge')}@test.edu"
    student = f"{_unique('stu')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    _user(db, judge, 'Judge')
    _user(db, student, 'Student')

    # SPOC creates an event happening today, with string criteria and the
    # "feedback before certificate" rule, and appoints a judge
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    title = _unique('Journey Hack')
    event_id = _create_event(spoc_client, db, title, datetime.date.today().isoformat(), fee=0, team=False)
    db.collection('events').document(event_id).update({
        'judging_criteria': ['Innovation', 'Execution'],
        'workflow_config': {'rules': {'require_feedback_for_certificate': True}},
    })
    assert spoc_client.post(f'/spoc/add_judge/{event_id}', data={
        'judge_name': 'Judge Judy', 'judge_email': judge, 'expertise': 'AI'}).status_code == 302

    # Register
    student_client = _login(flask_app, student, 'Student')
    assert student_client.post(f'/forms/submit/{event_id}', data={'privacy_consent': 'yes',
        'full_name': 'Stu Dent', 'email': student, 'phone': '9876543210', 'usn': '1SN20CS100',
    }).status_code == 302
    regs = list(db.collection('registrations').where('event_id', '==', event_id).stream())
    assert len(regs) == 1
    reg_id = regs[0].id

    def reg():
        return db.collection('registrations').document(reg_id).get().to_dict()

    # Check in at the gate
    checkin = spoc_client.post(f'/spoc/api/checkin/{event_id}/{reg_id}', json={'round': 1})
    assert checkin.status_code == 200, checkin.data
    assert reg()['attendance'] == 'Present'

    # Allocate rooms: each judge sees only the teams allocated to them
    assert spoc_client.post(f'/coordinator/allocate_rooms/{event_id}', data={
        'room_name[]': ['Hall 1'], 'capacity[]': ['10']}).status_code == 302
    assert reg()['assigned_judge_email'] == judge

    # Score
    judge_client = _login(flask_app, judge, 'Judge')
    teams = judge_client.get(f'/judge/event/{event_id}')
    assert teams.status_code == 200 and 'Stu Dent' in teams.get_data(as_text=True)
    assert judge_client.post(f'/judge/submit_score/{reg_id}', data={
        'score_innovation': '8', 'score_execution': '6', 'remarks': 'Solid'}).status_code == 302
    score = reg()['scores'][judge]
    assert score['details'] == {'Innovation': 8, 'Execution': 6}
    assert score['total'] == 7.0

    # The event ends; the certificate waits for feedback
    spoc_client.post(f'/spoc/event/{event_id}/transition', data={'target_state': 'completed'})
    assert db.collection('events').document(event_id).get().to_dict()['status'] == 'completed'
    early = student_client.get(f'/participant/certificate/{reg_id}')
    assert early.status_code == 302 and early.headers['Location'].endswith(f'/participant/feedback/{reg_id}')

    # Feedback
    assert student_client.get(f'/participant/feedback/{reg_id}').status_code == 200
    assert student_client.post(f'/participant/feedback/{reg_id}', data={
        'rating': '5', 'comments': 'Great event'}).status_code == 302
    assert reg()['feedback']['rating'] == 5

    # Certificate (the HTML certificate page; PDF generation is UPG-06)
    cert = student_client.get(f'/participant/certificate/{reg_id}')
    assert cert.status_code == 200
    body = cert.get_data(as_text=True)
    assert 'Stu Dent' in body and title in body
    assert '>None<' not in body


def test_tests_never_see_real_outbound_credentials_or_a_real_broker(real_app):
    # app.py has run load_dotenv() by now; a developer's .env must not have
    # filled any of these in
    for name in OUTBOUND_CREDENTIALS:
        assert os.environ.get(name) == '', name
    from celery_app import celery
    assert celery.conf.task_always_eager is True
    assert not str(celery.conf.broker_url).startswith('redis')
