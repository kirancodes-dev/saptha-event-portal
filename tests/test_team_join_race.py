"""
tests/test_team_join_race.py — UPG-52 on the real database layer: two people
joining a team at the same moment can neither overwrite each other nor push it
past team_max. Two threads call the join's decision (`routes_teams._add_member`)
released together by a barrier, for several rounds. The row lock that settles
the race is PostgreSQL's (run with TEST_DATABASE_URL); on SQLite, writes are
serialised by the file and the one-free-place race is skipped.
"""
import threading

import pytest

import routes_teams
from tests import test_teams
from tests.test_integration_flow import _unique
from tests.test_teams import _reg, _register, _student, _team_regs

team_event = test_teams.team_event
ROUNDS = 5


def _dialect():
    from db_pg import get_engine
    return get_engine().dialect.name


def _team_with(d, mates_count):
    lead, client = _student(d, 'racelead')
    mates = [(f'Mate {i}', f"{_unique(f'rm{i}')}@test.edu", f'1SN22CS30{i}') for i in range(1, mates_count + 1)]
    before = {rid for rid, _ in _team_regs(d)}
    assert _register(d, client, lead, mates, team=_unique('Racers')).status_code == 302
    [(reg_id, reg)] = [(rid, r) for rid, r in _team_regs(d) if rid not in before]
    return reg_id, len(reg['members'])


def _join_together(reg_id, how_many):
    barrier, results = threading.Barrier(how_many), []

    def join(i):
        member = {'name': f'Joiner {i}', 'email': f"{_unique(f'join{i}')}@test.edu", 'role': 'Member'}
        barrier.wait()
        results.append(routes_teams._add_member(reg_id, member, 4))
    threads = [threading.Thread(target=join, args=(i,)) for i in range(how_many)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results


def test_two_joins_for_the_last_place_leave_exactly_one(team_event):
    if _dialect() != 'postgresql':
        pytest.skip('the race is settled by PostgreSQL row locks; run with TEST_DATABASE_URL')
    d = team_event
    for _ in range(ROUNDS):
        reg_id, members = _team_with(d, 2)          # lead + 2 of 4: one free place
        assert members == 3
        results = _join_together(reg_id, 2)
        assert sorted(results) == ['added', 'full']
        assert len(_reg(d, reg_id)['members']) == 4


def test_two_joins_with_two_free_places_keep_both(team_event):
    d = team_event
    for _ in range(ROUNDS if _dialect() == 'postgresql' else 1):
        reg_id, members = _team_with(d, 1)          # lead + 1 of 4: two free places
        assert members == 2
        results = _join_together(reg_id, 2) if _dialect() == 'postgresql' else [
            routes_teams._add_member(reg_id, {'name': f'J{i}', 'email': f"{_unique(f'sj{i}')}@test.edu"}, 4)
            for i in range(2)]
        assert results == ['added', 'added']
        assert len(_reg(d, reg_id)['members']) == 4
