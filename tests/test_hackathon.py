"""
tests/test_hackathon.py — Unit tests for Hackathon Project Submission, Kanban Pipeline, and Rubric Scoring.
"""

def test_submit_project_requires_login(client):
    resp = client.get('/hackathon/submit/evt_hack_1', follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_submit_project_page_loads(auth_client, mock_db):
    mock_db.collection('events').document('evt_hack_1').set({
        'title': 'AI Global Hackathon 2026',
        'category': 'technical'
    })
    mock_db.collection('registrations').document('reg_hack_1').set({
        'event_id': 'evt_hack_1',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999',
        'team_name': 'Quantum Coders'
    })

    resp = auth_client.get('/hackathon/submit/evt_hack_1')
    assert resp.status_code == 200
    assert b'Project Submission' in resp.data


def test_post_project_submission(auth_client, mock_db):
    mock_db.collection('events').document('evt_hack_1').set({
        'title': 'AI Global Hackathon 2026'
    })
    mock_db.collection('registrations').document('reg_hack_1').set({
        'event_id': 'evt_hack_1',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999',
        'team_name': 'Quantum Coders'
    })

    resp = auth_client.post('/hackathon/submit/evt_hack_1', data={
        'project_title': 'Smart Campus AI',
        'tagline': 'AI powered campus navigation',
        'problem_statement': 'Students get lost on day 1',
        'solution_overview': 'Map layout with AR features',
        'tech_stack': 'Python, Flask, Google Maps API',
        'github_url': 'https://github.com/test/smart-campus'
    }, follow_redirects=False)

    assert resp.status_code in (301, 302)


def test_kanban_pipeline_loads(client, mock_db):
    mock_db.collection('events').document('evt_hack_1').set({
        'title': 'AI Global Hackathon 2026'
    })

    resp = client.get('/hackathon/pipeline/evt_hack_1')
    assert resp.status_code == 200
    assert b'Hackathon Innovation Pipeline' in resp.data


def test_score_project_rubric_api(admin_client, mock_db):
    mock_db.collection('project_submissions').document('sub_101').set({
        'event_id': 'evt_hack_1',
        'project_title': 'Smart Campus AI',
        'score_impact': 0.0,
        'total_score': 0.0
    })

    resp = admin_client.post('/api/hackathon/score/sub_101', json={
        'impact': 9.0,
        'tech': 8.5,
        'ux': 9.0,
        'pitch': 9.5
    })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'
    assert data['total_score'] == 9.0
