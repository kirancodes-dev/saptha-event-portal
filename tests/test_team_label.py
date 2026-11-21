"""
tests/test_team_label.py — UPG-377: a team named "Team Phoenix" reads "Team
Phoenix", not "Team Team Phoenix", in its result email (and wherever the
portal writes "Team <name>"); "Phoenix" still reads "Team Phoenix".
"""
import pytest

import services_registration_state as rs
import utils_email


@pytest.mark.parametrize('name, label', [
    ('Phoenix', 'Team Phoenix'), ('Team Phoenix', 'Team Phoenix'), ('TEAM X', 'TEAM X'), ('team-alpha', 'team-alpha'),
    ('Teamwork Heroes', 'Team Teamwork Heroes'), ('  Byte Busters ', 'Team Byte Busters'), ('', ''), (None, ''),
])
def test_team_is_written_once(name, label):
    assert rs.team_label(name) == label


@pytest.mark.parametrize('team, shown', [('Team Phoenix', 'Team Phoenix'), ('Phoenix', 'Team Phoenix')])
def test_the_result_email_writes_team_once(monkeypatch, team, shown):
    sent = []
    monkeypatch.setattr(utils_email, '_send', lambda to, subject, html: sent.append(html) or True)
    assert utils_email.send_hackathon_result_email('lead@example.edu', 'Asha', 'Hack 2026', team, 'Winner', 1, None, '')
    assert f'>{shown}</p>' in sent[0]
    assert 'Team Team' not in sent[0]


def test_the_templates_use_the_filter():
    for path in ('templates/participant/dashboard.html', 'templates/participant/_waitlist.html'):
        with open(path, encoding='utf-8') as fh:
            source = fh.read()
        assert '· Team {{' not in source and '| team }}' in source, path
