"""
tests/test_exams.py — Tests for online exams, proctoring violations, and SPOC control room monitoring.
"""

def test_exam_requires_login(client):
    resp = client.get('/exams/evt_test_1', follow_redirects=False)
    assert resp.status_code in (302, 401)

def test_exam_page_loads_for_registered_student(auth_client, mock_db):
    # Setup mock event & registration
    mock_db.collection('events').document('evt_test_1').set({
        'title': 'CS101 Midterm Exam',
        'category': 'technical',
        'duration_minutes': 45
    })
    mock_db.collection('registrations').document('reg_evt_1').set({
        'event_id': 'evt_test_1',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999'
    })

    resp = auth_client.get('/exams/evt_test_1')
    assert resp.status_code == 200
    assert b'Online Assessment' in resp.data

def test_log_proctor_violation(auth_client, mock_db):
    mock_db.collection('events').document('evt_test_1').set({
        'title': 'CS101 Midterm Exam'
    })
    mock_db.collection('registrations').document('reg_evt_1').set({
        'event_id': 'evt_test_1',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999'
    })

    resp = auth_client.post('/api/proctor/log_violation', json={
        'event_id': 'evt_test_1',
        'violation_type': 'TAB_SWITCH',
        'detail': 'Candidate switched tab'
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['violations'] >= 1

def test_submit_exam(auth_client, mock_db):
    mock_db.collection('events').document('evt_test_1').set({
        'title': 'CS101 Midterm Exam'
    })
    resp = auth_client.post('/exams/submit/evt_test_1', data={
        'ans_q1': 'O(N)',
        'ans_q2': 'Repeatable Read'
    }, follow_redirects=False)
    assert resp.status_code in (301, 302)
