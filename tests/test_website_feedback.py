"""
tests/test_website_feedback.py — UPG-304 on the real database layer.

The Super Admin makes website feedback rounds from two sample forms (or a
blank one), edits the questions, chooses who answers (everyone registered, or
the participants of chosen events) and turns a round on. While it is on, every
participant who must answer (lead or team member) is sent to the form from
every page, at every sign-in, until they submit; their ticket, signing out and
the privacy and help pages stay open; staff are never asked. Answers are
anonymous; written answers may be quoted only when the person allowed it.
"""
import csv
import io
import re
import uuid

import pytest

import services_site_feedback as sf
from tests.test_integration_flow import _create_event, _login, _unique, _user


@pytest.fixture
def fb(real_app, monkeypatch):
    import models
    import routes_site_feedback
    monkeypatch.setattr(routes_site_feedback, 'db', models.db)
    flask_app, db = real_app

    def all_off():
        for r in sf.rounds(db):
            if r.get('status') == sf.ON:
                db.collection(sf.ROUNDS).document(r['id']).update({'status': sf.OFF})
        sf.clear_cache()

    all_off()
    admin = f"{_unique('fbadmin')}@test.edu"
    _user(db, admin, 'SuperAdmin')
    spoc = f"{_unique('fbspoc')}@test.edu"
    _user(db, spoc, 'ClubSPOC')
    spoc_client = _login(flask_app, spoc, 'ClubSPOC')
    event_id = _create_event(spoc_client, db, _unique('Feedback Fest'), '2030-01-15')
    other_event = _create_event(spoc_client, db, _unique('Other Meet'), '2030-01-16')

    def team(event, status='Confirmed'):
        """A registration with a lead and a member, both with student logins."""
        lead, member = f"{_unique('fblead')}@test.edu", f"{_unique('fbmember')}@test.edu"
        for person in (lead, member):
            _user(db, person, 'Student')
        reg_id = str(uuid.uuid4())
        title = db.collection('events').document(event).get().to_dict().get('title')
        db.collection('registrations').document(reg_id).set({
            'event_id': event, 'event_title': title, 'team_name': _unique('Team'), 'lead_email': lead,
            'lead_name': 'Lead Person', 'status': status, 'payment_status': 'Free',
            'members': [{'name': 'Lead Person', 'email': lead, 'role': 'Lead'},
                        {'name': 'Member Person', 'email': member}]})
        reg = next(d for d in db.collection('registrations').where('lead_email', '==', lead).stream())
        return {'lead': lead, 'member': member, 'reg_id': reg.id}

    def student(email):
        return _login(flask_app, email, 'Student')

    def new_round(sample='now'):
        client = _login(flask_app, admin, 'SuperAdmin')
        resp = client.post('/admin/website-feedback/new', data={'sample': sample})
        assert resp.status_code == 302
        return client, resp.headers['Location'].rsplit('/', 1)[1]

    yield {'app': flask_app, 'db': db, 'admin': admin, 'spoc_client': spoc_client, 'event': event_id,
           'other_event': other_event, 'team': team, 'student': student, 'new_round': new_round,
           'admin_client': lambda: _login(flask_app, admin, 'SuperAdmin')}
    all_off()


def _form_of(r, **changes):
    """The edit form for a round as it is, with changes."""
    data = {'title': r['title'], 'intro': r.get('intro') or '', 'audience': r.get('audience') or 'all'}
    for i, q in enumerate(r['questions'], start=1):
        data.update({f'q_{i}_id': q['id'], f'q_{i}_kind': q['kind'], f'q_{i}_label': q['label'],
                     f'q_{i}_help': q.get('help') or '', f'q_{i}_options': '\n'.join(q.get('options') or []),
                     f'q_{i}_order': str(i)})
        if q.get('required'):
            data[f'q_{i}_required'] = '1'
    data.update(changes)
    return data


def _good_answers(r, **extra):
    data = {}
    for q in r['questions']:
        if q['kind'] == 'rating':
            data[f"a_{q['id']}"] = '4'
        elif q['kind'] == 'scale':
            data[f"a_{q['id']}"] = '9'
        elif q['kind'] == 'choice':
            data[f"a_{q['id']}"] = q['options'][0]
        elif q['kind'] == 'multi':
            data[f"a_{q['id']}"] = [q['options'][1]]
        else:
            data[f"a_{q['id']}"] = 'The team page is clear.'
    data.update(extra)
    return data


# ── Criterion 1: rounds from the two samples, Super Admin only ──────────────

def test_the_super_admin_starts_a_round_from_either_sample_and_nobody_else_can(fb):
    client = fb['admin_client']()
    page = client.get('/admin/website-feedback').get_data(as_text=True)
    assert 'data-sample="now"' in page and 'data-sample="during"' in page
    assert 'How easy was it to sign up and register for your event?' in page
    assert 'How did check-in with your QR ticket go?' in page
    for sample, first in (('now', 'signup'), ('during', 'find')):
        _, round_id = fb['new_round'](sample)
        r = sf.get(fb['db'], round_id)
        assert r['status'] == sf.DRAFT and r['questions'][0]['id'] == first and r['audience'] == 'all'
        # Ratings and ticks need an answer; writing is optional
        assert all(q['required'] for q in r['questions'] if q['kind'] != 'text')
        assert not any(q['required'] for q in r['questions'] if q['kind'] == 'text')
        assert any(q['id'] == 'recommend' for q in r['questions'])     # the same in both, to compare
    # A blank round
    resp = client.post('/admin/website-feedback/new', data={})
    assert sf.get(fb['db'], resp.headers['Location'].rsplit('/', 1)[1])['questions'] == []
    # Nobody else
    team = fb['team'](fb['event'])
    for c in (fb['spoc_client'], fb['student'](team['lead'])):
        assert c.get('/admin/website-feedback').status_code in (302, 403)
        assert c.post('/admin/website-feedback/new', data={'sample': 'now'}).status_code in (302, 403)
        assert c.get(f'/admin/website-feedback/{round_id}').status_code in (302, 403)
        assert c.post(f'/admin/website-feedback/{round_id}/on').status_code in (302, 403)
    assert sf.get(fb['db'], round_id)['status'] == sf.DRAFT


# ── Criterion 2: the Super Admin changes the questions ───────────────────────

def test_the_super_admin_adds_removes_reorders_and_rewords_questions(fb):
    client, round_id = fb['new_round']('now')
    r = sf.get(fb['db'], round_id)
    n = len(r['questions'])
    data = _form_of(r, title='Tell us about the website', q_1_label='How easy was registering?',
                    q_2_order='9', q_3_remove='1')
    data.update({f'q_{n + 1}_kind': 'choice', f'q_{n + 1}_label': 'Which device do you use most?',
                 f'q_{n + 1}_options': 'Phone\nLaptop\nPhone\n\nTablet', f'q_{n + 1}_required': '1',
                 f'q_{n + 1}_order': '2'})
    resp = client.post(f'/admin/website-feedback/{round_id}', data=data)
    assert resp.status_code == 302
    r = sf.get(fb['db'], round_id)
    labels = [q['label'] for q in r['questions']]
    assert r['title'] == 'Tell us about the website'
    assert labels[0] == 'How easy was registering?' and labels[1] == 'Which device do you use most?'
    assert labels[-1].startswith('How likely are you to recommend')           # moved to the end
    assert 'Which parts were hard or confusing?' not in labels                 # removed
    device = r['questions'][1]
    assert device['kind'] == 'choice' and device['options'] == ['Phone', 'Laptop', 'Tablet'] and device['required']
    assert r['questions'][0]['id'] == 'signup'                                 # ids kept


def test_a_round_that_doesnt_make_sense_is_refused_and_nothing_is_saved(fb):
    client, round_id = fb['new_round']('now')
    r = sf.get(fb['db'], round_id)
    cases = [
        (_form_of(r, title=''), 'Give the round a title'),
        (_form_of(r, q_3_options='Only one'), 'give at least two choices'),
        (dict(_form_of(r), audience='events'), 'Choose at least one event'),
        ({'title': 'Empty', 'audience': 'all'}, 'Add at least one question'),
    ]
    big = _form_of(r)
    for i in range(len(r['questions']) + 1, sf.MAX_QUESTIONS + 2):
        big.update({f'q_{i}_kind': 'text', f'q_{i}_label': f'Extra question {i}'})
    cases.append((big, f'At most {sf.MAX_QUESTIONS} questions'))
    for data, message in cases:
        resp = client.post(f'/admin/website-feedback/{round_id}', data=data)
        assert resp.status_code == 400 and message in resp.get_data(as_text=True), message
    assert sf.get(fb['db'], round_id)['questions'] == r['questions']


# ── Criterion 3: on and off, one at a time, chosen events ───────────────────

def test_one_round_is_on_at_a_time_and_chosen_events_need_events(fb):
    client, first = fb['new_round']('now')
    _, second = fb['new_round']('during')
    assert client.post(f'/admin/website-feedback/{first}/on').status_code == 302
    assert sf.get(fb['db'], first)['status'] == sf.ON
    page = client.get(f'/admin/website-feedback/{second}/on', follow_redirects=False)
    assert page.status_code == 405
    resp = client.post(f'/admin/website-feedback/{second}/on', follow_redirects=True)
    assert 'one round is asked at a time' in resp.get_data(as_text=True)
    assert sf.get(fb['db'], second)['status'] == sf.DRAFT
    # While on, the questions can't change
    r = sf.get(fb['db'], first)
    resp = client.post(f'/admin/website-feedback/{first}', data=_form_of(r, title='Changed'), follow_redirects=True)
    assert "can't change" in resp.get_data(as_text=True) and sf.get(fb['db'], first)['title'] == r['title']
    assert client.post(f'/admin/website-feedback/{first}/off').status_code == 302
    assert sf.get(fb['db'], first)['status'] == sf.OFF
    # The second round for one event only
    r2 = sf.get(fb['db'], second)
    resp = client.post(f'/admin/website-feedback/{second}', data=dict(_form_of(r2), audience='events',
                                                                         event_ids=[fb['event']]))
    assert resp.status_code == 302
    assert sf.get(fb['db'], second)['event_ids'] == [fb['event']]
    assert client.post(f'/admin/website-feedback/{second}/on').status_code == 302
    assert sf.get(fb['db'], second)['status'] == sf.ON


# ── Criterion 4: every participant is sent to the form until they answer ────

def test_every_member_of_a_team_is_sent_to_the_form_from_every_page_until_they_answer(fb):
    team = fb['team'](fb['event'])
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    for person in (team['lead'], team['member']):
        c = fb['student'](person)
        for path in ('/participant/dashboard', '/participant/my_events', '/participant/waitlist_status',
                     f'/participant/registration/{team["reg_id"]}/edit', '/events', '/'):
            resp = c.get(path)
            if path == '/' and resp.status_code == 200:
                continue   # the public home page is public
            assert resp.status_code == 302, path
            assert resp.headers['Location'].startswith('/website-feedback?next='), path
        form = c.get('/website-feedback?next=/participant/dashboard')
        html = form.get_data(as_text=True)
        assert form.status_code == 200 and 'How easy was it to sign up and register for your event?' in html
        assert 'data-honest' in html and 'anonymous' in html and 'data-quote-ok' in html
        # A JSON call or a form sent from an old tab is refused, not run
        resp = c.post('/participant/dashboard', data={})
        assert resp.status_code == 403 and resp.get_json()['error'] == 'feedback_required'
        # At every sign-in, until they answer
        again = fb['student'](person)
        assert again.get('/participant/dashboard').headers['Location'].startswith('/website-feedback')


def test_the_ticket_signing_out_and_the_privacy_and_help_pages_stay_open(fb):
    team = fb['team'](fb['event'])
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    c = fb['student'](team['lead'])
    html = c.get('/website-feedback').get_data(as_text=True)
    assert f'href="/ticket/{team["reg_id"]}"' in html and 'href="/logout"' in html and 'href="/privacy"' in html
    for path in (f'/ticket/{team["reg_id"]}', f'/ticket/qr/{team["reg_id"]}', '/privacy', '/terms', '/about'):
        resp = c.get(path)
        assert not (resp.status_code == 302 and resp.headers['Location'].startswith('/website-feedback')), path
    resp = c.get('/logout')
    assert resp.status_code == 302 and not resp.headers['Location'].startswith('/website-feedback')
    with c.session_transaction() as sess:
        assert not sess.get('user_id')


def test_staff_people_not_registered_and_other_events_participants_are_not_asked(fb):
    team = fb['team'](fb['event'])
    elsewhere = fb['team'](fb['other_event'])
    cancelled = fb['team'](fb['event'], status='cancelled')
    loner = f"{_unique('fbloner')}@test.edu"
    _user(fb['db'], loner, 'Student')
    client, round_id = fb['new_round']('during')
    r = sf.get(fb['db'], round_id)
    client.post(f'/admin/website-feedback/{round_id}', data=dict(_form_of(r), audience='events',
                                                                   event_ids=[fb['event']]))
    client.post(f'/admin/website-feedback/{round_id}/on')
    assert fb['student'](team['member']).get('/participant/dashboard').status_code == 302
    for person in (elsewhere['lead'], cancelled['lead'], loner):
        assert fb['student'](person).get('/participant/dashboard').status_code == 200, person
    # The SPOC and the Super Admin are never asked
    assert fb['spoc_client'].get('/spoc/dashboard').status_code == 200
    assert fb['admin_client']().get('/admin/website-feedback').status_code == 200
    # The page says how many are asked: the lead and the member of the one team
    page = client.get(f'/admin/website-feedback/{round_id}').get_data(as_text=True)
    assert re.search(r'<strong>0</strong> of <strong>2</strong>', page)


# ── Criterion 5: answering, once ─────────────────────────────────────────────

def test_a_missing_answer_is_marked_and_a_sent_form_is_never_asked_again(fb):
    team = fb['team'](fb['event'])
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    r = sf.get(fb['db'], round_id)
    c = fb['student'](team['lead'])
    resp = c.post('/website-feedback', data={'next': '/participant/dashboard', 'a_change': 'Bigger buttons'})
    html = resp.get_data(as_text=True)
    assert resp.status_code == 400 and 'data-problems' in html and 'Choose an answer.' in html
    assert 'Tick at least one.' in html and 'Bigger buttons' in html            # what they wrote stays
    assert not sf.answered(fb['db'], round_id, team['lead'])
    resp = c.post('/website-feedback', data=_good_answers(r, next='/participant/dashboard'))
    assert resp.status_code == 302 and resp.headers['Location'].endswith('/participant/dashboard')
    assert c.get('/participant/dashboard').status_code == 200
    # Never again, also after signing in again; the member is still asked
    assert fb['student'](team['lead']).get('/participant/dashboard').status_code == 200
    assert fb['student'](team['member']).get('/participant/dashboard').status_code == 302
    # A second send (an old tab) saves nothing twice
    c.post('/website-feedback', data=_good_answers(r))
    assert len(sf.answers_of(fb['db'], round_id)) == 1
    # An outside "next" is not followed
    other = fb['student'](team['member'])
    resp = other.post('/website-feedback', data=_good_answers(r, next='https://example.com/x'))
    assert resp.headers['Location'].endswith('/participant/dashboard')


def test_turning_a_round_off_lets_everyone_in_and_a_new_round_asks_again(fb):
    team = fb['team'](fb['event'])
    client, first = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{first}/on')
    c = fb['student'](team['lead'])
    c.post('/website-feedback', data=_good_answers(sf.get(fb['db'], first)))
    member = fb['student'](team['member'])
    assert member.get('/participant/dashboard').status_code == 302
    client.post(f'/admin/website-feedback/{first}/off')
    assert member.get('/participant/dashboard').status_code == 200
    # The mid-event round: the lead who answered the first is asked again
    _, second = fb['new_round']('during')
    client.post(f'/admin/website-feedback/{second}/on')
    resp = fb['student'](team['lead']).get('/participant/dashboard')
    assert resp.status_code == 302 and resp.headers['Location'].startswith('/website-feedback')
    assert 'How is the website helping you at the event?' in c.get('/website-feedback').get_data(as_text=True)


# ── Criterion 6: anonymous answers, quotes only when allowed ────────────────

def test_answers_are_not_linked_to_the_person_and_quotes_need_their_tick(fb):
    first, second = fb['team'](fb['event']), fb['team'](fb['event'])
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    r = sf.get(fb['db'], round_id)
    fb['student'](first['lead']).post('/website-feedback', data=_good_answers(
        r, a_change='Show the venue map', a_liked='The QR ticket was QUICK', quote_ok='1'))
    fb['student'](second['lead']).post('/website-feedback', data=_good_answers(
        r, a_change='Dark mode please', a_liked='Simple registration'))
    stored = [d.to_dict() for d in fb['db'].collection(sf.ANSWERS).stream() if d.to_dict().get('round_id') == round_id]
    assert len(stored) == 2
    for a in stored:
        text = repr(a)
        assert first['lead'] not in text and second['lead'] not in text and 'Lead Person' not in text
        assert set(a) == {'round_id', 'answers', 'quote_ok', 'day', 'device', 'events'}
        assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', a['day'])                     # a day, not a time
    done = [d.to_dict() for d in fb['db'].collection(sf.DONE).stream() if d.to_dict().get('round_id') == round_id]
    assert sorted(d['email'] for d in done) == sorted([first['lead'], second['lead']])
    assert all(set(d) == {'round_id', 'email', 'day'} for d in done)
    page = client.get(f'/admin/website-feedback/{round_id}').get_data(as_text=True)
    assert first['lead'] not in page and second['lead'] not in page
    quotes = page[page.index('data-quotes'):]
    assert 'The QR ticket was QUICK' in quotes and 'Show the venue map' in quotes
    assert 'Dark mode please' not in quotes and 'Simple registration' not in quotes


# ── Criterion 7: results, search and the CSV ─────────────────────────────────

def test_the_results_count_average_and_search_the_answers(fb):
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    r = sf.get(fb['db'], round_id)
    scores = [(5, 10, 'Faster check-in'), (3, 8, ''), (1, 2, 'The password email came LATE')]
    for signup, recommend, change in scores:
        team = fb['team'](fb['event'])
        fb['student'](team['lead']).post('/website-feedback', data=_good_answers(
            r, a_signup=str(signup), a_recommend=str(recommend), a_change=change, a_hard_parts=[
                'Using it on my phone', 'Emails and notices']),
            headers={'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile/15E148'})
    result = sf.results(fb['db'], r)
    by = {item['q']['id']: item for item in result['questions']}
    assert result['total'] == 3 and by['signup']['average'] == 3.0
    assert by['recommend']['recommend_score'] == 0                             # 1 promoter, 1 detractor of 3
    assert (by['recommend']['promoters'], by['recommend']['passives'], by['recommend']['detractors']) == (1, 1, 1)
    counts = {o: n for o, n, _ in by['hard_parts']['counts']}
    assert counts['Using it on my phone'] == 3 and counts['Nothing was hard'] == 0
    assert [t['text'] for t in by['change']['texts']] and result['devices'] == [('Phone', 3)]
    page = client.get(f'/admin/website-feedback/{round_id}?q=password email came late').get_data(as_text=True)
    texts = page[page.index('data-result="change"'):]
    texts = texts[:texts.index('data-result="liked"')]
    assert 'The password email came LATE' in texts and 'Faster check-in' not in texts
    assert 'data-recommend-score' in page and 'Average: <strong>3.0</strong>' in page
    resp = client.get(f'/admin/website-feedback/{round_id}/answers.csv')
    assert resp.status_code == 200 and resp.mimetype == 'text/csv'
    rows = list(csv.reader(io.StringIO(resp.get_data(as_text=True))))
    assert rows[0][:3] == ['Day', 'Device', 'Events'] and rows[0][-1] == 'May be quoted (no name)'
    assert len(rows) == 4 and '@' not in resp.get_data(as_text=True)


def test_questions_lock_once_answered_and_a_copy_can_change(fb):
    team = fb['team'](fb['event'])
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    r = sf.get(fb['db'], round_id)
    fb['student'](team['lead']).post('/website-feedback', data=_good_answers(r))
    client.post(f'/admin/website-feedback/{round_id}/off')
    resp = client.post(f'/admin/website-feedback/{round_id}', data=_form_of(r, title='Changed'), follow_redirects=True)
    assert 'Copy it into a new round' in resp.get_data(as_text=True)
    assert sf.get(fb['db'], round_id)['title'] == r['title']
    assert 'data-locked' in client.get(f'/admin/website-feedback/{round_id}').get_data(as_text=True)
    assert client.post(f'/admin/website-feedback/{round_id}/delete').status_code == 302
    assert sf.get(fb['db'], round_id)                                           # answered: kept
    resp = client.post(f'/admin/website-feedback/{round_id}/copy')
    copy_id = resp.headers['Location'].rsplit('/', 1)[1]
    copied = sf.get(fb['db'], copy_id)
    assert copied['questions'] == r['questions'] and copied['status'] == sf.DRAFT
    assert client.post(f'/admin/website-feedback/{copy_id}', data=_form_of(copied, title='Changed')).status_code == 302
    assert sf.get(fb['db'], copy_id)['title'] == 'Changed'
    assert client.post(f'/admin/website-feedback/{copy_id}/delete').status_code == 302
    assert sf.get(fb['db'], copy_id) is None


def test_the_super_admin_sees_the_form_as_participants_do(fb):
    client, round_id = fb['new_round']('during')
    html = client.get(f'/admin/website-feedback/{round_id}/preview').get_data(as_text=True)
    assert 'data-preview-note' in html and 'How did check-in with your QR ticket go?' in html
    assert re.search(r'<button type="submit" class="btn btn-primary w-100" disabled>', html)
    assert 'action="#"' in html


# ── Criterion 8: privacy ─────────────────────────────────────────────────────

def test_the_persons_data_lists_the_rounds_answered_and_deletion_removes_it(fb):
    import services_privacy
    team = fb['team'](fb['event'])
    client, round_id = fb['new_round']('now')
    client.post(f'/admin/website-feedback/{round_id}/on')
    fb['student'](team['lead']).post('/website-feedback', data=_good_answers(sf.get(fb['db'], round_id)))
    export = services_privacy.own_data(fb['db'], team['lead'])
    assert [x['round_id'] for x in export['sections']['website_feedback_answered']] == [round_id]
    counts = services_privacy.anonymise_account(fb['db'], team['lead'])
    assert counts['website_feedback'] == 1 and not sf.answered(fb['db'], round_id, team['lead'])
    assert len(sf.answers_of(fb['db'], round_id)) == 1                         # the anonymous answer stays
