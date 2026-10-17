"""
tests/test_readme.py — UPG-101: the README links the live site, says how to
run the app and its tests, and its test numbers agree with each other.
"""
import re

LIVE = 'https://saptha-967997581752.asia-south1.run.app'


def _readme():
    with open('README.md', encoding='utf-8') as fh:
        return fh.read()


def test_the_readme_links_the_live_site_and_says_how_to_run_it():
    readme = _readme()
    assert readme.count(LIVE) >= 3 and 'Live demo' in readme
    assert '## Run it locally' in readme and 'python app.py' in readme and 'pytest' in readme
    assert 'TESTS_' not in readme   # no unfilled numbers
    badge = re.search(r'badge/tests-(\d+)_passing', readme).group(1)
    assert f'**{badge} pass**' in readme   # the badge matches the Quality section
