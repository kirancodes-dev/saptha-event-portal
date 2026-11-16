"""
tests/test_product_story.py — UPG-275 on the real database layer: the About
page tells a university buyer who the portal is for, what it covers, how an
institution starts, what a demo can and cannot do and who to write to, with
nothing invented (no price, customer, figure, certification or integration
that isn't built); a demo copy says "Demo" on every page and an institution's
own deployment never does; the old platform pages no longer invent anything.
"""
import os
import re

import pytest

import services_institution
from tests.test_data_handling import _claims
from tests.test_integration_flow import _login, _unique, _user

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECTIONS = ('who', 'workflows', 'limits', 'start', 'demo', 'support')
INVENTED = ('₹', 'Rs.', '/year', '/month', 'per student', 'Free plan', 'Starter', 'Enterprise', 'Contact Sales',
            'testimonial', 'Trusted by', 'trusted by', 'Multi-Tenant', 'multi-tenant', 'LDAP', 'SAML', 'Microsoft',
            'support@sapthaevent.com', 'Get Started Free', 'Stripe', 'tenant account', 'Tenant Account',
            'across the world', 'worldwide', 'Industrial-grade')


def _text(html):
    html = re.sub(r'<(style|script)\b.*?</\1>', ' ', html, flags=re.S)
    return ' '.join(re.sub(r'<[^>]+>', ' ', html).split())


def _article(html):
    """The About page's own words, without the app bar and the footer."""
    return html[html.index('data-about'):html.index('</article>')]


@pytest.fixture
def site(real_app):
    flask_app, db = real_app
    services_institution.forget()
    before = {k: flask_app.config.get(k) for k in ('DEMO_ENVIRONMENT', 'DEMO_PAGES_ENABLED', 'FLASK_ENV')}
    yield {'app': flask_app, 'db': db, 'visitor': flask_app.test_client()}
    flask_app.config.update(before)
    db.collection(services_institution.COLLECTION).document(services_institution.DOCUMENT).delete()
    services_institution.forget()


# ── Criterion 1: the five things a buyer needs, and nothing invented ────────

def test_the_about_page_answers_the_buyers_five_questions_and_invents_nothing(site):
    d = site
    page = d['visitor'].get('/about')
    assert page.status_code == 200                                           # no login needed
    html = page.get_data(as_text=True)
    for section in SECTIONS:
        assert f'data-section="{section}"' in html and f'href="#{section}"' in html, section
    text = _text('<article ' + _article(html))
    for said in ('Who it is for', 'What it covers', 'What it does not do', 'How an institution gets started',
                 'What the demo can and cannot do', 'Support and more information'):
        assert said in text, said
    for invented in INVENTED:
        assert invented not in html, invented
    assert not re.search(r'\b\d+(\.\d+)?\s?[KkM]\+|\b\d[\d,]*\+?\s+(colleges|universities|institutions|students|customers)', text)
    assert not re.search(r'\d\s?%', text)                                     # no uptime or satisfaction figure
    assert _claims(text) == []
    # what it says it does not do
    for limit in ('One deployment serves one institution', 'no campus single sign-on', 'no price list',
                  'has not been independently audited', 'no uptime commitment',
                  'not been checked against the format of any accreditation'):
        assert limit in text, limit
    # the number of event kinds is the real one
    from services_event_types import TYPES
    assert f'{len(TYPES)} kinds of event' in text


def test_every_link_on_the_about_page_opens(site):
    d = site
    html = d['visitor'].get('/about').get_data(as_text=True)
    links = set(re.findall(r'href="(/[^"#]*)', _article(html)))
    assert {'/events', '/verify', '/privacy', '/terms', '/compliance/sla'} <= links
    for link in links:
        assert d['visitor'].get(link).status_code == 200, link


def test_the_page_carries_the_institutions_own_name_and_support_address(site):
    d = site
    html = d['visitor'].get('/about').get_data(as_text=True)
    assert 'Sapthagiri NPS University' in html                                # the built-in default
    if not services_institution.profile(d['db'])['support_email']:
        assert 'data-no-support' in html and 'mailto:' not in _article(html)

    admin = f"{_unique('aboutadmin')}@test.edu"
    clean, problems = services_institution.validate(dict(
        services_institution.profile(d['db']), name='Riverbend Institute of Technology', short_name='RIT',
        support_email='events@riverbend.example'))
    assert problems == {}
    services_institution.save(d['db'], clean, admin)
    services_institution.forget()
    html = d['visitor'].get('/about').get_data(as_text=True)
    assert 'SapthaEvent at Riverbend Institute of Technology' in _text(html)
    assert 'href="mailto:events@riverbend.example" data-support' in html and 'data-no-support' not in html
    assert "Riverbend Institute of Technology's own portal" not in html       # a test copy isn't anyone's portal


def test_the_footer_and_the_home_page_link_the_about_page(site):
    d = site
    student = f"{_unique('aboutstu')}@test.edu"
    _user(d['db'], student, 'Student')
    client = _login(d['app'], student, 'Student')
    assert 'href="/about"' in d['visitor'].get('/').get_data(as_text=True)
    for path in ('/events', '/privacy', '/participant/dashboard'):
        assert 'href="/about"' in client.get(path).get_data(as_text=True), path


# ── Criterion 2: a demo says so; an institution's own deployment doesn't ────

def test_the_three_environments_are_told_apart_from_the_settings():
    env = services_institution.environment
    assert env({'DEMO_ENVIRONMENT': True, 'FLASK_ENV': 'production'})['key'] == 'demo'      # demo wins
    assert env({'DEMO_ENVIRONMENT': False, 'FLASK_ENV': 'production'})['key'] == 'production'
    assert env({'FLASK_ENV': 'development'})['key'] == 'development' == env({})['key']
    assert 'sample data' in env({'DEMO_ENVIRONMENT': True})['explanation']
    assert 'real records' in env({'FLASK_ENV': 'production'})['explanation']
    import config
    assert config.Config.DEMO_ENVIRONMENT is False                             # off unless the deployment says so


def test_a_demo_says_demo_on_every_page_and_other_copies_never_do(site):
    d = site
    student = f"{_unique('demostu')}@test.edu"
    _user(d['db'], student, 'Student')
    client = _login(d['app'], student, 'Student')
    pages = ('/', '/events', '/about', '/privacy', '/login', '/verify', '/open-events')
    signed_in = ('/participant/dashboard', '/profile/')

    for path in pages:
        assert 'data-demo-banner' not in d['visitor'].get(path).get_data(as_text=True), path
    about = d['visitor'].get('/about').get_data(as_text=True)
    assert 'data-environment="development"' in about and 'This is a development copy' in _text(about)

    d['app'].config['DEMO_ENVIRONMENT'] = True
    for path in pages:
        html = d['visitor'].get(path).get_data(as_text=True)
        assert html.count('data-demo-banner') == 1 and 'href="/about#demo"' in html, path
        assert 'sample data, not real records' in html, path
    for path in signed_in:
        assert 'data-demo-banner' in client.get(path).get_data(as_text=True), path
    about = d['visitor'].get('/about').get_data(as_text=True)
    assert 'data-environment="demo"' in about and 'You are on a demo now.' in about

    d['app'].config.update(DEMO_ENVIRONMENT=False, FLASK_ENV='production')
    about = d['visitor'].get('/about').get_data(as_text=True)
    assert 'data-demo-banner' not in about and 'data-environment="production"' in about
    assert 'You are not on a demo.' in about and "a registration made here is a real registration" in _text(about)
    for path in ('/', '/events'):
        assert 'data-demo-banner' not in d['visitor'].get(path).get_data(as_text=True), path


def test_the_demo_section_says_what_a_demo_can_and_cannot_show(site):
    d = site
    html = d['visitor'].get('/about').get_data(as_text=True)
    can = _text(html[html.index('data-demo-can'):html.index('data-demo-cannot')])
    cannot = _text(html[html.index('data-demo-cannot'):html.index('id="support"')])
    for said in ('register for one as a visitor', 'demo accounts given to you', 'scan a ticket', 'reports'):
        assert said in can, said
    for said in ("your institution's name", 'do not put real personal details into a demo', 'not a load test',
                 'only when that copy has been given an account'):
        assert said in cannot, said


def test_scanners_and_printed_pages_have_no_banner_block():
    with open(os.path.join(ROOT, 'templates/layouts/fullscreen.html'), encoding='utf-8') as handle:
        assert '{% block environment_banner %}{% endblock %}' in handle.read()


# ── Criterion 3: the old platform pages invent nothing ──────────────────────

def test_the_old_platform_pages_stay_hidden_and_show_the_about_page_when_switched_on(site):
    d = site
    for path in ('/platform', '/features', '/pricing'):
        assert d['visitor'].get(path).status_code == 404, path
    d['app'].config['DEMO_PAGES_ENABLED'] = True
    about = _text(d['visitor'].get('/about').get_data(as_text=True))
    for path in ('/platform', '/features'):
        page = d['visitor'].get(path)
        assert page.status_code == 200 and _text(page.get_data(as_text=True)) == about, path
        for invented in INVENTED:
            assert invented not in page.get_data(as_text=True), (path, invented)
    for gone in ('templates/marketing/landing.html', 'templates/marketing/features.html'):
        assert not os.path.exists(os.path.join(ROOT, gone)), gone
    # nothing on the About page, the home page or the footer sends anyone to the price list
    for path in ('/about', '/'):
        assert 'href="/pricing"' not in d['visitor'].get(path).get_data(as_text=True), path


def test_the_setup_guide_says_how_to_mark_a_demo():
    with open(os.path.join(ROOT, 'docs/INSTITUTION_SETUP.md'), encoding='utf-8') as handle:
        guide = handle.read()
    assert 'DEMO_ENVIRONMENT' in guide and '/about' in guide
