"""
tests/test_releases.py — the portal's versions and the What's new page (UPG-373).

The list (config/releases.json) must stay true and complete: newest first with
rising numbers, only finished items in it, and every item the changelog calls
finished listed in some version, so a future change can't be left off.
"""
import json
import re

import services_releases
from tests.test_integration_flow import _login, _unique, _user

REVIEW = 'docs/FEATURE_REVIEW.md'


def _status():
    text = open(REVIEW, encoding='utf-8').read()
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r'^\| ((?:UPG|BLK)-\d+) \|[^|]*\| ([^|]*) \|', text, re.M)}


def _expand(cell):
    """'UPG-308, UPG-310 to UPG-312; new UPG-314' → the finished ones, ranges opened."""
    done = cell.split(';')[0]
    ids = []
    for part in done.split(','):
        part = part.strip()
        m = re.match(r'(UPG|BLK)-(\d+)\s*(?:to|–|-)\s*(?:(?:UPG|BLK)-)?(\d+)$', part)
        if m:
            ids += [f"{m.group(1)}-{n}" for n in range(int(m.group(2)), int(m.group(3)) + 1)]
        elif re.match(r'(UPG|BLK)-\d+$', part):
            ids.append(part)
    return ids


def test_the_versions_are_newest_first_and_hold_only_finished_items():
    rel = services_releases.releases()
    assert rel and services_releases.version() == f"v{rel[0]['version']}"
    numbers = [tuple(int(x) for x in r['version'].split('.')) for r in rel]
    assert numbers == sorted(numbers, reverse=True) and len(set(numbers)) == len(numbers)
    assert [r['date'] for r in rel] == sorted((r['date'] for r in rel), reverse=True)
    status = _status()
    for r in rel:
        assert r['title'] and r['notes'], r['version']
        for item in r['items']:
            assert status.get(item, '').startswith('DONE'), f"{item} in v{r['version']} is {status.get(item)!r}"
    every = [i for r in rel for i in r['items']]
    assert len(every) == len(set(every)), "an item is listed in two versions"
    assert all(r['revision'] for r in rel[1:]), "only the newest version may be waiting for its deploy"


def test_every_item_the_changelog_finished_is_in_a_version():
    text = open(REVIEW, encoding='utf-8').read()
    log = text[text.index('## Changelog (last 20)'):]
    listed = {i for r in services_releases.releases() for i in r['items']}
    status = _status()
    missing = []
    for row in re.findall(r'^\| 20\d\d-\d\d-\d\d \|[^|]*\| ([^|]*) \|', log, re.M):
        missing += [i for i in _expand(row) if status.get(i, '').startswith('DONE') and i not in listed]
    assert not missing, f"Add these to config/releases.json's top version: {sorted(set(missing))}"


def test_the_whats_new_page_and_the_footer(real_app):
    app, db = real_app
    client = app.test_client()
    page = client.get('/whats-new')
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    top = services_releases.current()
    assert f"Version {top['version']}" in html and "You're using this version" in html
    assert html.count('data-release=') == len(services_releases.releases())
    assert 'Version 1.0' in html and '20 Oct 2026' in html and '2026-10-20' not in html
    assert html.index(f"Version {top['version']}") < html.index('Version 1.0')
    # The footer on any page names the version and links here, signed in or not
    footer = client.get('/about').get_data(as_text=True)
    assert f"What's new · v{top['version']}" in footer and 'href="/whats-new"' in footer
    email = f"{_unique('stud')}@test.edu"
    _user(db, email, 'Student')
    assert 'href="/whats-new"' in _login(app, email, 'Student').get('/participant/dashboard').get_data(as_text=True)


def test_an_unreadable_list_shows_no_version(monkeypatch, tmp_path):
    bad = tmp_path / 'releases.json'
    bad.write_text('{not json')
    monkeypatch.setattr(services_releases, 'PATH', str(bad))
    services_releases.releases.cache_clear()
    try:
        assert services_releases.releases() == [] and services_releases.version() == ''
    finally:
        services_releases.releases.cache_clear()
    assert json.load(open('config/releases.json'))['releases']
