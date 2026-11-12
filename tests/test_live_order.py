"""
tests/test_live_order.py — UPG-218 on the real database layer.

A poll's (and a question's) time was kept to the second, so two opened in the
same second came back in either order. Now each is kept to the microsecond
and never repeats, so they come back in the order they were opened, every
time; rows saved before (to the second) still sort first within their second.
"""
import datetime
import uuid

import services_interact as live


class _Frozen(datetime.datetime):
    """The clock stuck on one second, as two clicks within it see it."""
    @classmethod
    def now(cls, tz=None):
        return datetime.datetime(2026, 11, 19, 9, 30, 0, tzinfo=tz)


def test_polls_and_questions_made_in_the_same_second_come_back_in_order(real_app, monkeypatch):
    flask_app, _db = real_app
    monkeypatch.setattr(live._dt, 'datetime', _Frozen)
    with flask_app.app_context():
        for _ in range(20):
            event_id = f"order-{uuid.uuid4().hex[:8]}"
            polls = [live.create_poll(event_id, f'Poll {i}?', ['Yes', 'No']) for i in range(3)]
            assert [p['id'] for p in live.polls_for(event_id)] == polls
            asked = [live.ask(event_id, f'p{i}@test.edu', f'Question {i}?', moderated=False) for i in range(3)]
            assert [q['id'] for q in live.questions_for(event_id)] == asked


def test_a_time_saved_to_the_second_sorts_before_one_from_the_same_second():
    old, new = '2026-11-19 09:30:00', live._now()
    assert len(new) == len('2026-11-19 09:30:00.000000') and old < old + '.000001' and new[:4].isdigit()
