"""
tests/test_hackathon_ai_claude.py — UPG-326: Claude scores the submissions
when ANTHROPIC_API_KEY is set: the SPOC's criteria, 25 submissions per step
with their calls made at the same time, and a clear reason when a call fails.
The Claude call itself is checked against a stand-in client (no network).
"""
import datetime
import json
import threading
import time

import anthropic
import httpx2
import pytest

import services_hackathon_eval as ev
from tests.test_hackathon_phase2 import AFTER, p2, reply  # noqa: F401
from tests.test_hackathon_portal import _page, hack  # noqa: F401


@pytest.fixture
def claude(p2, monkeypatch):  # noqa: F811
    monkeypatch.setitem(p2['app'].config, 'ANTHROPIC_API_KEY', 'sk-ant-test')
    return p2


# 1. With a Claude key, Claude scores (and is named on the page); without one, Gemini as before
def test_the_claude_key_makes_claude_the_scorer_and_the_page_says_so(claude, monkeypatch):
    h = claude
    with h['app'].app_context():
        assert ev.provider() == 'claude' and ev.model_name() == 'claude-opus-5-5' and ev.batch_size() == 25
    eid, teams = h['setup'](names=('Alpha', 'Bravo'))
    h['after']()
    page = _page(h['owner'], f'/spoc/hackathon/{eid}')
    assert 'data-ai-criteria' in page and 'Start AI scoring' in page
    assert 'Scored by <strong>Claude (claude-opus-5-5)</strong>, 25 team(s) at a time' in page
    h['score_all'](eid)
    assert h['sub'](teams['Alpha'])['ai_eval']['model'] == 'claude-opus-5-5'

    monkeypatch.setitem(h['app'].config, 'ANTHROPIC_API_KEY', '')
    with h['app'].app_context():
        assert ev.provider() == 'gemini' and ev.batch_size() == ev.BATCH
    assert 'Scored by <strong>Gemini (gemini-2.5-flash)</strong>' in _page(h['owner'], f'/spoc/hackathon/{eid}')


# 2. 25 submissions per step, called at the same time, each scored once
def test_twenty_five_per_step_called_together_then_the_rest(claude):
    h = claude
    names = tuple(f'T{i:02d}' for i in range(27))
    eid, _teams = h['setup'](names=names)
    h['after']()
    h['script']['*'] = reply(8)
    running, peak, lock = [0], [0], threading.Lock()
    inner = ev._call_model

    def slow(system, data):
        with lock:
            running[0] += 1
            peak[0] = max(peak[0], running[0])
        time.sleep(0.05)
        try:
            return inner(system, data)
        finally:
            with lock:
                running[0] -= 1
    ev_call = pytest.MonkeyPatch()
    ev_call.setattr(ev, '_call_model', slow)
    try:
        h['owner'].post(f'/spoc/hackathon/{eid}/ai/start')
        first = h['owner'].post(f'/spoc/hackathon/{eid}/ai/next', json={},
                                headers={'Accept': 'application/json'}).get_json()
        assert first['scored'] == 25 and first['pending'] == 2 and not first['finished']
        assert peak[0] > 1, "the calls ran at the same time"
        second = h['owner'].post(f'/spoc/hackathon/{eid}/ai/next', json={},
                                 headers={'Accept': 'application/json'}).get_json()
        assert second['scored'] == 27 and second['finished'] and second['calls'] == 27
    finally:
        ev_call.undo()
    assert len(h['calls']) == 27
    assert len({json.loads(c['data'])['project_title'] for c in h['calls']}) == 27, "each team once"


# 3. The SPOC's criteria reach Claude; the calls stop at the event's cap
def test_the_spocs_criteria_are_used_and_the_cap_holds(claude, monkeypatch):
    h = claude
    eid, teams = h['setup'](names=('Alpha', 'Bravo', 'Charlie'))
    h['owner'].post(f'/spoc/hackathon/{eid}/ai/criteria', data={
        'criterion_0': 'Impact', 'description_0': 'Who it helps', 'marks_0': '60',
        'criterion_1': 'Code quality', 'marks_1': '40'})
    h['after']()
    h['script']['*'] = json.dumps({'scores': {'impact': 5, 'code_quality': 10}, 'reason': 'ok'})
    monkeypatch.setattr(ev, 'MAX_CALLS_PER_EVENT', 2)
    progress = h['score_all'](eid)
    assert progress['scored'] == 2 and progress['calls'] == 2 and progress['status'] == 'capped'
    assert '"impact": Impact (Who it helps) [worth 60 of 100 marks]' in h['calls'][0]['system']
    scored = [h['sub'](t)['ai_eval'] for t in teams.values() if h['sub'](t).get('ai_eval')]
    assert len(scored) == 2 and all(s['total'] == 70.0 for s in scored)


# 4. A failed call says why, never shows the key, and the next press retries only those
def test_failures_say_why_without_the_key_and_score_the_rest_again(claude):
    h = claude
    eid, teams = h['setup'](names=('Alpha', 'Bravo', 'Charlie', 'Delta'))
    h['after']()
    req = httpx2.Request('POST', 'https://api.anthropic.com/v1/messages')
    h['script'].update({
        'Bravo': anthropic.RateLimitError('busy sk-ant-test', response=httpx2.Response(429, request=req), body=None),
        'Charlie': anthropic.BadRequestError('Your credit balance is too low sk-ant-test',
                                             response=httpx2.Response(400, request=req), body=None),
        'Delta': anthropic.AuthenticationError('invalid x-api-key', response=httpx2.Response(401, request=req),
                                               body=None)})
    progress = h['score_all'](eid)
    assert progress['scored'] == 1 and progress['not_scored'] == 3
    errors = {n: h['sub'](t)['ai_eval'].get('error') for n, t in teams.items()}
    assert errors['Bravo'] == "The AI service was busy. Wait a minute, then score the rest again."
    assert errors['Charlie'] == "The Claude account has no credits left. Add credits, then score the rest again."
    assert errors['Delta'] == "The AI key was refused. Check the key set for the portal."
    assert 'sk-ant' not in json.dumps([h['sub'](t) for t in teams.values()], default=str)
    assert 'Score the rest again' in _page(h['owner'], f'/spoc/hackathon/{eid}')

    h['clock']['now'] = AFTER + datetime.timedelta(minutes=2)      # a minute or two later
    h['calls'].clear()
    for name in ('Bravo', 'Charlie', 'Delta'):
        h['script'].pop(name)
    progress = h['score_all'](eid)
    assert progress['scored'] == 4 and len(h['calls']) == 3, "only the three not scored are tried again"


# 5. The Claude request itself: model, criteria schema, low effort, fallbacks; refusals not scored
class _Block:
    def __init__(self, kind, text=''):
        self.type, self.text = kind, text


class _Reply:
    def __init__(self, text, stop='end_turn'):
        self.content = [_Block('thinking'), _Block('text', text)]
        self.stop_reason = stop


def test_the_claude_request_and_its_reply(monkeypatch):
    sent, made = {}, {}
    answer = {'value': _Reply(reply(9))}

    class FakeMessages:
        def create(self, **kwargs):
            sent.update(kwargs)
            return answer['value']

    class FakeClient:
        def __init__(self, **kwargs):
            made.update(kwargs)
            self.beta = type('B', (), {'messages': FakeMessages()})()
    monkeypatch.setattr(anthropic, 'Anthropic', FakeClient)
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')
    crits = ev.criteria({})
    system = ev.instructions(crits)

    raw = ev._call_claude(system, '{"project_title": "X"}')
    assert ev.parse_reply(raw, crits)[0] == {c['id']: 9.0 for c in crits}
    assert made['api_key'] == 'sk-ant-test' and made['timeout'] == ev.CLAUDE_TIMEOUT_S
    assert sent['model'] == 'claude-opus-5-5' and sent['system'] == system
    assert sent['messages'] == [{'role': 'user', 'content': '{"project_title": "X"}'}]
    assert sent['output_config']['effort'] == 'low'
    schema = sent['output_config']['format']['schema']
    assert sent['output_config']['format']['type'] == 'json_schema'
    assert schema['properties']['scores']['required'] == [c['id'] for c in crits]
    assert sent['fallbacks'] == 'default' and sent['betas'] == ['server-side-fallback-2026-07-01']
    assert 'temperature' not in sent and 'thinking' not in sent

    answer['value'] = _Reply('', stop='refusal')
    with pytest.raises(ev.ReplyError, match='declined'):
        ev._call_claude(system, '{}')
    answer['value'] = _Reply('{"scores": {', stop='max_tokens')
    with pytest.raises(ev.ReplyError, match='cut off'):
        ev._call_claude(system, '{}')
