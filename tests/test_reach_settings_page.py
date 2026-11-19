"""
tests/test_reach_settings_page.py — UPG-320.

The Super Admin's "Public pages" switch (/reach/settings) answered 500: the
page named its on/off value `powered_by`, the same name as the footer's
function on every page, so the footer called a True or False. Now the page
opens, says whether the line is shown, and the footer works on it.
"""
from tests import test_reach
from tests.test_reach import reach

site = test_reach.site


def test_the_super_admin_opens_the_switch_page_and_turns_the_line_off_and_on(site):
    d = site
    reach._cache['at'] = 0
    resp = d['admin'].get('/reach/settings')
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert 'The line is <strong>shown</strong>' in html and 'Hide it' in html
    assert 'name="powered_by" value="off"' in html
    assert 'Powered by SapthaEvent' in html                          # the footer, on this page too
    d['admin'].post('/reach/settings', data={'powered_by': 'off'})
    try:
        html = d['admin'].get('/reach/settings').get_data(as_text=True)
        assert 'The line is <strong>hidden</strong>' in html and 'Show it' in html
        assert 'name="powered_by" value="on"' in html
        assert 'site-footer__powered' not in html
    finally:
        d['admin'].post('/reach/settings', data={'powered_by': 'on'})
    assert d['owner'].get('/reach/settings').status_code == 403      # only the Super Admin
