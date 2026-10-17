"""
tests/test_upg66_csrf_forms.py — Tests for UPG-66: CSRF token on exam and hackathon submission forms.
"""
import os
import re
from flask_wtf.csrf import generate_csrf


def test_every_rendered_post_form_in_templates_has_csrf_token():
    """
    UPG-66 Criterion 2: Every <form method="POST"> in templates/ contains
    a csrf_token field (excluding the try-api client tool that hits the exempt /api/v1/auth/login).
    """
    root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'templates')
    exempt_templates = {'templates/developer/api_docs.html'}

    missing = []
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            if fn.endswith('.html'):
                full_path = os.path.join(dirpath, fn)
                rel_path = os.path.relpath(full_path, os.path.dirname(root))
                if rel_path in exempt_templates:
                    continue
                content = open(full_path).read()
                for m in re.finditer(r'<form\b[^>]*method=[\"\']?POST[\"\']?[^>]*>', content, re.IGNORECASE):
                    form_tag = m.group(0)
                    end_pos = content.find('</form>', m.end())
                    form_body = content[m.end():end_pos] if end_pos != -1 else content[m.end():m.end()+1000]
                    if 'csrf_token' not in form_body:
                        missing.append((rel_path, form_tag))

    assert missing == [], f"Found forms missing csrf_token: {missing}"


def test_exam_form_rendered_contains_csrf_token(auth_client, mock_db):
    """UPG-66: Rendering the exam interface outputs the hidden csrf_token input."""
    mock_db.collection('events').document('evt_csrf_exam').set({
        'title': 'CSRF Exam',
        'category': 'technical',
        'duration_minutes': 30,
    })
    mock_db.collection('registrations').document('reg_csrf_exam').set({
        'event_id': 'evt_csrf_exam',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999',
    })

    resp = auth_client.get('/exams/evt_csrf_exam')
    assert resp.status_code == 200
    assert b'name="csrf_token"' in resp.data


def test_hackathon_project_submission_rendered_contains_csrf_token(auth_client, mock_db):
    """UPG-66: Rendering the hackathon submit page outputs the hidden csrf_token input."""
    mock_db.collection('events').document('evt_csrf_hack').set({
        'title': 'CSRF Hackathon',
        'category': 'technical',
    })
    mock_db.collection('registrations').document('reg_csrf_hack').set({
        'event_id': 'evt_csrf_hack',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999',
        'team_name': 'Cyber Coders',
    })

    resp = auth_client.get('/hackathon/submit/evt_csrf_hack')
    assert resp.status_code == 200
    assert b'name="csrf_token"' in resp.data


def test_hackathon_submission_csrf_protection(app, auth_client, mock_db):
    """
    UPG-66 Criterion 1: Posting hackathon project submission with CSRF enabled:
    - Without token: rejected by CSRF (returns 400 for JSON request or flashes expired session on web post)
    - With token: accepted and saved
    """
    mock_db.collection('events').document('evt_csrf_hack_guard').set({
        'title': 'CSRF Hackathon Guard',
        'category': 'technical',
    })
    mock_db.collection('registrations').document('reg_csrf_hack_guard').set({
        'event_id': 'evt_csrf_hack_guard',
        'lead_name': 'Test Student',
        'lead_email': 'student@test.edu',
        'student_email': 'student@test.edu',
        'lead_phone': '9999999999',
        'team_name': 'Cyber Coders',
    })

    app.config['WTF_CSRF_ENABLED'] = True
    try:
        # 1. Posting without CSRF token fails CSRF check (refused with 400 for JSON request)
        refused_json = auth_client.post(
            '/hackathon/submit/evt_csrf_hack_guard',
            headers={'Accept': 'application/json'},
            data={'project_title': 'Smart AI'},
            follow_redirects=False,
        )
        assert refused_json.status_code == 400

        # Form post without token flashes session expired and does not save
        refused_html = auth_client.post(
            '/hackathon/submit/evt_csrf_hack_guard',
            data={'project_title': 'Smart AI'},
            follow_redirects=True,
        )
        assert b'Your session expired' in refused_html.data

        # 2. Posting with valid CSRF token succeeds
        with auth_client.session_transaction():
            token = generate_csrf()

        allowed = auth_client.post('/hackathon/submit/evt_csrf_hack_guard', data={
            'csrf_token': token,
            'project_title': 'Smart AI',
            'tagline': 'AI powered',
            'problem_statement': 'Problems',
            'solution_overview': 'Solutions',
            'tech_stack': 'Python',
            'github_url': 'https://github.com/test/smart',
        }, follow_redirects=False)
        assert allowed.status_code in (301, 302)
    finally:
        app.config['WTF_CSRF_ENABLED'] = False


def test_exam_submission_csrf_protection(app, auth_client, mock_db):
    """
    UPG-66 Criterion 1: Posting exam submission with CSRF enabled:
    - Without token: rejected by CSRF
    - With token: accepted
    """
    mock_db.collection('events').document('evt_csrf_exam_guard').set({
        'title': 'CSRF Exam Guard',
    })

    app.config['WTF_CSRF_ENABLED'] = True
    try:
        # 1. Posting without CSRF token fails CSRF check
        refused_json = auth_client.post(
            '/exams/submit/evt_csrf_exam_guard',
            headers={'Accept': 'application/json'},
            data={'ans_q1': 'A'},
            follow_redirects=False,
        )
        assert refused_json.status_code == 400

        refused_html = auth_client.post(
            '/exams/submit/evt_csrf_exam_guard',
            headers={'Referer': '/exams/evt_csrf_exam_guard'},
            data={'ans_q1': 'A'},
            follow_redirects=True,
        )
        assert b'Your session expired' in refused_html.data

        # 2. Posting with valid CSRF token succeeds
        with auth_client.session_transaction():
            token = generate_csrf()

        allowed = auth_client.post('/exams/submit/evt_csrf_exam_guard', data={
            'csrf_token': token,
            'ans_q1': 'A',
        }, follow_redirects=False)
        assert allowed.status_code in (301, 302)
    finally:
        app.config['WTF_CSRF_ENABLED'] = False
