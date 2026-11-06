"""
tests/test_pagination_lists.py — UPG-19 on the real database layer, for every
covered list: with 120 rows it shows 25 (the owner's page size) and page 5 the
last 20; a search by name, email or USN narrows it and combines with the page;
per_page=1000 is capped at 100; the users list pages in SQL (LIMIT). Also: the
three dashboards' ?status= filter, the audit log's role and action filters,
and that the dashboards' totals still count every event.

Rows carry a unique token, and each list is searched by it, so other tests'
data in the shared database doesn't change the counts.
"""
import datetime
import re

import pytest
from sqlalchemy import event as sa_event

from tests.test_integration_flow import PASSWORD, _login, _unique, _user

N = 120
FUTURE = (datetime.date.today() + datetime.timedelta(days=30)).isoformat()


def _showing(html):
    m = re.search(r'Showing (\d+)–(\d+) of (\d+)', html)
    assert m, 'no "Showing" line on the page'
    return tuple(int(x) for x in m.groups())


def _marked(html, tok):
    """The marked rows on the page. Chart data (<script>) and event pickers
    (<select>, e.g. "announce to which event") cover every event on purpose:
    they aren't the list, so they don't count."""
    html = re.sub(r'<(script|select)\b.*?</\1>', '', html, flags=re.S | re.I)
    return set(re.findall(rf'{tok}-(\d{{3}})', html))


@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    admin, spoc, coord = (f"{_unique(k)}@test.edu" for k in ('pgadmin', 'pgspoc', 'pgcoord'))
    _user(db, admin, 'SuperAdmin')
    _user(db, spoc, 'ClubSPOC')
    _user(db, coord, 'EventCoordinator')
    admin_client = flask_app.test_client()
    resp = admin_client.post('/login', data={'role': 'SuperAdmin', 'email': admin, 'password': PASSWORD,
                                             'secret_key': flask_app.config.get('MASTER_SECRET_KEY', '')})
    assert resp.status_code == 302 and resp.headers['Location'] != '/login'
    clients = {'admin': admin_client, 'spoc': _login(flask_app, spoc, 'ClubSPOC'),
               'coord': _login(flask_app, coord, 'EventCoordinator')}
    staff = [{'name': 'Cora', 'email': coord, 'role': 'EventCoordinator'}]

    def event(title, status='registration_open', **extra):
        event_id = _unique('EVT')
        db.collection('events').document(event_id).set(dict({
            'title': title, 'category': 'Technical', 'venue': 'Hall P', 'date': FUTURE, 'status': status,
            'spoc_id': spoc, 'staff': staff, 'created_at': datetime.datetime.now().isoformat()}, **extra))
        return event_id

    return {'app': flask_app, 'db': db, 'clients': clients, 'event': event, 'spoc': spoc}


# ── How each list's rows are made: (client, url, make(site, tok, i, ctx), searchable) ──
# `searchable` names the ways a row can be found besides its marked name or title.

def _user_row(d, tok, i, ctx):
    email = f'{tok}-{i:03d}@pages.test'
    d['db'].collection('users').document(email).set({
        'name': f'{tok}-{i:03d}', 'role': 'Student', 'usn': f'1PG{i:03d}{tok[-4:].upper()}',
        'email': email, 'password': 'x'})


def _reg(d, event_id, tok, i, **extra):
    d['db'].collection('registrations').document(_unique('REG')).set(dict({
        'event_id': event_id, 'lead_name': f'{tok}-{i:03d}', 'lead_email': f'{tok}-{i:03d}@pages.test',
        'usn': f'1PG{i:03d}{tok[-4:].upper()}', 'status': 'Confirmed',
        'registered_at': f'2026-10-01 10:{i // 60:02d}:{i % 60:02d}'}, **extra))


def _one_event(d, ctx):
    if 'event_id' not in ctx:
        ctx['event_id'] = d['event'](_unique('Paged Event'))
    return ctx['event_id']


def _audit_row(d, tok, i, ctx):
    d['db'].collection('audit_log').document(_unique('LOG')).set({
        'action': 'PAGED_ACTION' if i % 2 else 'OTHER_ACTION', 'role': 'ClubSPOC' if i % 3 == 0 else 'Student',
        'user': f'{tok}-{i:03d}@pages.test', 'details': f'{tok}-{i:03d} did something',
        'timestamp': datetime.datetime.now().isoformat()})


def _submission(d, tok, i, ctx):
    event_id = _one_event(d, ctx)
    reg_id = _unique('REG')                                  # a submission belongs to a registration
    d['db'].collection('registrations').document(reg_id).set({'event_id': event_id, 'lead_name': 'Sub Mitter',
                                                              'lead_email': f'sub{i}@pages.test', 'status': 'Confirmed'})
    d['db'].collection('form_submissions').document(_unique('SUB')).set({
        'event_id': event_id, 'name': f'{tok}-{i:03d}', 'email': f'{tok}-{i:03d}@pages.test',
        'reg_id': reg_id, 'submitted_at': f'2026-10-01 10:{i // 60:02d}:{i % 60:02d}', 'answers': {}})


LISTS = {
    'admin users': ('admin', lambda ctx: '/admin/users', _user_row, ('email', 'usn')),
    'admin audit log': ('admin', lambda ctx: '/admin/audit_log', _audit_row, ('email',)),
    'admin payments': ('admin', lambda ctx: '/admin/payments',
                       lambda d, tok, i, ctx: _reg(d, _one_event(d, ctx), tok, i, payment_status='Paid',
                                                   amount_paid=100), ('email', 'usn')),
    'admin registrations': ('admin', lambda ctx: '/admin/registrations',
                            lambda d, tok, i, ctx: _reg(d, _one_event(d, ctx), tok, i), ('email', 'usn')),
    'admin dashboard': ('admin', lambda ctx: '/admin/dashboard',
                        lambda d, tok, i, ctx: d['event'](f'{tok}-{i:03d}'), ()),
    'admin events': ('admin', lambda ctx: '/admin/events',
                     lambda d, tok, i, ctx: d['event'](f'{tok}-{i:03d}'), ()),
    'spoc dashboard': ('spoc', lambda ctx: '/spoc/dashboard',
                       lambda d, tok, i, ctx: d['event'](f'{tok}-{i:03d}'), ()),
    'coordinator dashboard': ('coord', lambda ctx: '/coordinator/dashboard',
                              lambda d, tok, i, ctx: d['event'](f'{tok}-{i:03d}'), ()),
    'coordinator registrations': ('coord', lambda ctx: f"/coordinator/registrations/{ctx['event_id']}",
                                  lambda d, tok, i, ctx: _reg(d, _one_event(d, ctx), tok, i), ('email', 'usn')),
    'form responses': ('spoc', lambda ctx: f"/forms/responses/{ctx['event_id']}", _submission, ('email',)),
}


def _fill(d, name):
    tok = _unique('pg').replace('-', '')
    who, url, make, searchable = LISTS[name]
    ctx = {}
    for i in range(1, N + 1):
        make(d, tok, i, ctx)
    client = d['clients'][who]

    def get(**args):
        query = '&'.join(f'{k}={v}' for k, v in dict({'q': tok}, **args).items())
        resp = client.get(f'{url(ctx)}?{query}')
        assert resp.status_code == 200, (name, resp.status_code)
        return resp.get_data(as_text=True)
    return tok, get, searchable


@pytest.mark.parametrize('name', list(LISTS))
def test_each_list_shows_25_and_page_5_holds_the_last_20(site, name):
    tok, get, _ = _fill(site, name)
    first = get()
    assert _showing(first) == (1, 25, N) and len(_marked(first, tok)) == 25
    last = get(page=5)
    assert _showing(last) == (101, 120, N) and len(_marked(last, tok)) == 20
    assert _marked(first, tok).isdisjoint(_marked(last, tok))
    assert _showing(get(page=99))[:2] == (101, 120)          # past the end: the last page


@pytest.mark.parametrize('name', list(LISTS))
def test_search_narrows_each_list_and_combines_with_the_page(site, name):
    tok, get, searchable = _fill(site, name)
    narrowed = get(q=f'{tok}-01')                            # names 010 to 019
    assert _showing(narrowed) == (1, 10, 10) and _marked(narrowed, tok) == {f'01{k}' for k in range(10)}
    paged = get(q=f'{tok}-01', per_page=4, page=3)
    assert _showing(paged) == (9, 10, 10) and len(_marked(paged, tok)) == 2
    if 'email' in searchable:
        by_email = get(q=f'{tok}-042@pages.test')
        assert _showing(by_email) == (1, 1, 1) and _marked(by_email, tok) == {'042'}
    if 'usn' in searchable:
        by_usn = get(q=f'1PG077{tok[-4:].upper()}')
        assert _showing(by_usn) == (1, 1, 1) and _marked(by_usn, tok) == {'077'}


@pytest.mark.parametrize('name', list(LISTS))
def test_per_page_is_capped_at_100(site, name):
    tok, get, _ = _fill(site, name)
    page = get(per_page=1000)
    assert _showing(page) == (1, 100, N) and len(_marked(page, tok)) == 100


def test_the_users_list_pages_in_sql(site):
    d = site
    for i in range(1, 31):
        _user_row(d, _unique('sqlpg').replace('-', ''), i, {})
    from db_pg import get_engine
    statements = []

    def record(conn, cursor, statement, params, context, many):
        statements.append(statement)
    sa_event.listen(get_engine(), 'before_cursor_execute', record)
    try:
        html = d['clients']['admin'].get('/admin/users').get_data(as_text=True)
    finally:
        sa_event.remove(get_engine(), 'before_cursor_execute', record)
    users_selects = [s for s in statements if re.search(r'\bFROM\s+"?users"?', s, re.I) and 'COUNT' not in s.upper()]
    assert users_selects and all(re.search(r'\bLIMIT\b', s, re.I) for s in users_selects), users_selects
    first, last, total = _showing(html)
    assert (first, last) == (1, 25) and total >= 30


@pytest.mark.parametrize('name, url', [('admin dashboard', '/admin/dashboard'), ('spoc dashboard', '/spoc/dashboard'),
                                       ('coordinator dashboard', '/coordinator/dashboard')])
def test_the_dashboards_status_filter(site, name, url):
    d = site
    tok = _unique('st').replace('-', '')
    for i in range(1, 31):
        d['event'](f'{tok}-{i:03d}', status='completed' if i <= 12 else 'registration_open')
    who = LISTS[name][0]
    client = d['clients'][who]
    done = client.get(f'{url}?q={tok}&status=completed').get_data(as_text=True)
    assert _showing(done)[2] == 12 and _marked(done, tok) == {f'{k:03d}' for k in range(1, 13)}
    live = client.get(f'{url}?q={tok}&status=active').get_data(as_text=True)
    assert _showing(live)[2] == 18


def test_the_dashboard_totals_count_every_event(site):
    d = site
    tok = _unique('tot').replace('-', '')
    for i in range(1, 41):
        d['event'](f'{tok}-{i:03d}')
    spoc_page = d['clients']['spoc'].get('/spoc/dashboard').get_data(as_text=True)
    assert re.search(r'id="stat-total-events">\s*40\s*<', spoc_page) and _showing(spoc_page) == (1, 25, 40)
    coord_page = d['clients']['coord'].get('/coordinator/dashboard').get_data(as_text=True)
    assert _showing(coord_page) == (1, 25, 40) and '>40<' in re.sub(r'\s+', '', coord_page)


def test_the_audit_log_role_and_action_filters(site):
    tok, get, _ = _fill(site, 'admin audit log')
    by_action = get(action='paged_action')                   # odd rows: 60
    assert _showing(by_action)[2] == 60
    by_role = get(role='ClubSPOC')                           # every third row: 40
    assert _showing(by_role)[2] == 40
    both = get(role='ClubSPOC', action='PAGED_ACTION')       # odd multiples of 3: 20
    assert _showing(both)[2] == 20
