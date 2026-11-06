"""
tests/test_bandit_clean.py — UPG-113: CI's security step
(`bandit -r . -x tests/,__pycache__/ -ll -q`, .github/workflows/ci.yml) passes:
no Medium or High finding in any tracked file outside tests/. Run over the
tracked files, so local untracked copies of the repo don't count.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_bandit_finds_nothing_medium_or_high():
    bandit = shutil.which('bandit', path=os.path.dirname(sys.executable)) or shutil.which('bandit')
    if not bandit:
        pytest.fail('bandit is a dev dependency (requirements-dev.txt); install it to run this check')
    tracked = subprocess.run(['git', 'ls-files', '*.py'], cwd=ROOT, capture_output=True, text=True,
                             check=True).stdout.split()
    files = [f for f in tracked if not f.startswith('tests/')]
    out = subprocess.run([bandit, '-ll', '-q', '-f', 'json', *files], cwd=ROOT, capture_output=True, text=True)
    results = json.loads(out.stdout)['results']
    assert [(r['filename'], r['line_number'], r['test_id'], r['issue_text']) for r in results] == []
