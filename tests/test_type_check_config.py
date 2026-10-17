"""
tests/test_type_check_config.py — UPG-100: the editor's type checker
(Pyrefly) reads its configuration and the project's Python environment, and
routes_coordinator.py has no type errors.
"""
import os
import shutil
import subprocess
import sys
import tomllib

import pytest


def _pyrefly():
    here = os.path.join(os.path.dirname(sys.executable), 'pyrefly')
    return here if os.path.exists(here) else shutil.which('pyrefly')


def test_the_pyrefly_config_is_valid_toml_with_known_keys():
    with open('pyrefly.toml', 'rb') as fh:
        config = tomllib.load(fh)
    assert config['python-interpreter-path'] == '.venv/bin/python'
    assert 'saptha-event-portal-source*' in config['project-excludes']
    assert config['errors'] == {'parse-error': False, 'unknown-name': False, 'untyped-import': False}
    with open('pyrightconfig.json', encoding='utf-8') as fh:
        assert '"pythonVersion": "3.11"' in fh.read()


@pytest.mark.skipif(_pyrefly() is None, reason='pyrefly is a dev tool (requirements-dev.txt)')
def test_pyrefly_accepts_the_config_and_finds_no_errors_in_routes_coordinator():
    result = subprocess.run([_pyrefly(), 'check', 'routes_coordinator.py', '--output-format=min-text'],
                            capture_output=True, text=True, timeout=300)
    output = result.stdout + result.stderr
    assert 'configuration error' not in output.lower() and 'parse error' not in output.lower(), output[-500:]
    assert 'INFO 0 errors' in output, output[-500:]
