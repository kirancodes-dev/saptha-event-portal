"""
tests/test_hackathon_ai_gemini_model.py — UPG-328: Gemini scores with
gemini-3.8-flash by default (gemini-2.5-flash is closed to new keys), or the
model GEMINI_MODEL names; the request suits the model; a busy Gemini (429/503)
is tried again and then reads as busy, and a model the key can't use says so.
The Gemini call itself is checked against a stand-in client (no network).
"""
import datetime
import json
import os
import subprocess
import sys

import pytest
from google import genai
from google.genai import errors, types

import services_hackathon_eval as ev
from tests.test_hackathon_phase2 import AFTER, p2  # noqa: F401
from tests.test_hackathon_portal import _page, hack  # noqa: F401

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUSY = "The AI service was busy. Wait a minute, then score the rest again."


def _model_with(env_value):
    env = {k: v for k, v in os.environ.items() if k != 'GEMINI_MODEL'}
    if env_value is not None:
        env['GEMINI_MODEL'] = env_value
    out = subprocess.run([sys.executable, '-c', 'import services_hackathon_eval as ev; print(ev.MODEL)'],
                         cwd=ROOT, env=env, capture_output=True, text=True, check=True)
    return out.stdout.strip()


# 1. gemini-3.8-flash unless GEMINI_MODEL names another; the page names the model in use
def test_the_default_model_is_gemini_3_8_flash_and_gemini_model_sets_another(p2):  # noqa: F811
    assert _model_with(None) == 'gemini-3.8-flash'
    assert _model_with('') == 'gemini-3.8-flash'
    assert _model_with('   ') == 'gemini-3.8-flash'
    assert _model_with(' gemini-3.8-pro ') == 'gemini-3.8-pro'
    h = p2
    eid, teams = h['setup'](names=('Alpha',))
    h['after']()
    with h['app'].app_context():
        assert ev.provider() == 'gemini' and ev.model_name() == ev.MODEL
    assert f'Scored by <strong>Gemini ({ev.MODEL})</strong>' in _page(h['owner'], f'/spoc/hackathon/{eid}')
    h['score_all'](eid)
    assert h['sub'](teams['Alpha'])['ai_eval']['model'] == ev.MODEL


# 2. The request: the model, low thinking for Gemini 3; 2.5 keeps its old settings
def test_the_gemini_request_suits_the_model(monkeypatch):
    made, sent = {}, {}

    class FakeModels:
        def generate_content(self, **kwargs):
            sent.update(kwargs)
            return type('R', (), {'text': '{"scores": {}}'})()

    class FakeClient:
        def __init__(self, **kwargs):
            made.update(kwargs)
            self.models = FakeModels()
    monkeypatch.setattr(genai, 'Client', FakeClient)
    monkeypatch.setenv('GEMINI_API_KEY', 'gm-test')
    monkeypatch.setattr(ev, 'MODEL', 'gemini-3.8-flash')

    assert ev._call_gemini('the rules', '{"project_title": "X"}') == '{"scores": {}}'
    assert made['api_key'] == 'gm-test' and made['http_options'].timeout == ev.CALL_TIMEOUT_MS
    assert sent['model'] == 'gemini-3.8-flash' and sent['contents'] == '{"project_title": "X"}'
    config = sent['config']
    assert config.system_instruction == 'the rules' and config.response_mime_type == 'application/json'
    assert config.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert config.thinking_config.thinking_budget is None and config.temperature is None
    assert config.max_output_tokens == 4096

    monkeypatch.setattr(ev, 'MODEL', 'gemini-2.5-flash')
    old = ev.gemini_config('the rules')
    assert old.thinking_config.thinking_budget == 0 and old.thinking_config.thinking_level is None
    assert old.temperature == 0.2 and old.max_output_tokens == 1024


# 3. A busy answer (429/503) is tried again, 1 s then 2 s; not another error, nor once the call is old
def _busy(code=503):
    return errors.ServerError(code, {'error': {'code': code, 'message': 'high demand', 'status': 'UNAVAILABLE'}})


def test_a_busy_gemini_is_tried_again_and_nothing_else_is(monkeypatch):
    answers, tries, waits = [], [], []

    class FakeModels:
        def generate_content(self, **kwargs):
            tries.append(kwargs['model'])
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return type('R', (), {'text': answer})()

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs['http_options'].retry_options is None, "the SDK's own retry would retry timeouts too"
            self.models = FakeModels()
    monkeypatch.setattr(genai, 'Client', FakeClient)
    monkeypatch.setenv('GEMINI_API_KEY', 'gm-test')
    monkeypatch.setattr(ev, '_pause', waits.append)

    answers[:] = [_busy(503), _busy(429), '{"ok": 1}']
    assert ev._call_gemini('s', '{}') == '{"ok": 1}' and len(tries) == 3 and waits == [1, 2]

    tries.clear(), waits.clear()
    answers[:] = [_busy(), _busy(), _busy()]
    with pytest.raises(errors.ServerError):
        ev._call_gemini('s', '{}')
    assert len(tries) == ev.GEMINI_RETRIES == 3 and waits == [1, 2]

    tries.clear(), waits.clear()
    answers[:] = [errors.ClientError(404, {'error': {'code': 404, 'message': 'gone', 'status': 'NOT_FOUND'}})]
    with pytest.raises(errors.ClientError):
        ev._call_gemini('s', '{}')
    assert len(tries) == 1 and waits == []

    tries.clear(), waits.clear()
    clock = iter([100.0, 100.0 + ev.GEMINI_RETRY_WITHIN_S])     # the busy answer came late
    monkeypatch.setattr(ev.time, 'monotonic', lambda: next(clock))
    answers[:] = [_busy()]
    with pytest.raises(errors.ServerError):
        ev._call_gemini('s', '{}')
    assert len(tries) == 1 and waits == []


# 4. Busy (503/429) reads as busy, a closed model says so, anything else "didn't answer"
@pytest.mark.parametrize('exc, message', [
    (errors.ServerError(503, {'error': {'code': 503, 'message': 'high demand gm-test', 'status': 'UNAVAILABLE'}}),
     BUSY),
    (errors.ClientError(429, {'error': {'code': 429, 'message': 'quota gm-test', 'status': 'RESOURCE_EXHAUSTED'}}),
     BUSY),
    (errors.ClientError(404, {'error': {'code': 404, 'message': 'no longer available', 'status': 'NOT_FOUND'}}),
     "This AI model isn't available to the key set for the portal."),
    (errors.ServerError(500, {'error': {'code': 500, 'message': 'internal', 'status': 'INTERNAL'}}),
     "The AI service didn't answer."),
])
def test_gemini_errors_say_why(exc, message):
    assert ev._service_error(exc) == message


# 5. A team Gemini was busy for is "Not scored" with the reason, and the next press scores only it
def test_a_busy_gemini_is_not_scored_then_scored_on_the_next_press(p2):  # noqa: F811
    h = p2
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    h['after']()
    h['script']['Bravo'] = errors.ServerError(503, {'error': {'code': 503, 'message': 'high demand gm-test',
                                                              'status': 'UNAVAILABLE'}})
    progress = h['score_all'](eid)
    assert progress['scored'] == 1 and progress['not_scored'] == 1
    assert h['sub'](teams['Bravo'])['ai_eval']['error'] == BUSY
    assert 'gm-test' not in json.dumps([h['sub'](t) for t in teams.values()], default=str)

    h['clock']['now'] = AFTER + datetime.timedelta(minutes=2)
    h['script'].pop('Bravo')
    h['calls'].clear()
    progress = h['score_all'](eid)
    assert progress['scored'] == 2 and len(h['calls']) == 1
