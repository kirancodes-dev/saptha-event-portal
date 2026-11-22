"""
services_players.py — find a player and see their profile (UPG-424)

The players are the members of the teams in the public sports events: the
registrations of a tournament's teams. A player is the same person across
events by their email, which is never shown: the profile's address carries a
code made from it (an HMAC with the app's secret key), so the email can't be
read back from the link.

A profile shows the player's name, team and logo, jersey number, position and
age (from the date of birth, which is never shown, UPG-423), then each event:
the matches, raid and tackle points, successful raids, super raids, tackles,
super tackles, do-or-die points, Super 10s, High 5s and player of the match
awards, match by match, and the achievements. The numbers come from the
matches scored live (services_live_match): a match scored only as a result
has no player points.

Never shown: the date of birth, the email, the phone and the USN.
"""
import hashlib
import hmac
import time

import services_live_match as live
import services_sports as sports

CACHE_SECONDS = 60
HIDDEN_STATUSES = ('draft', 'cancelled', 'pending', 'pending_approval', 'rejected', 'deleted')
MAX_RESULTS = 50
MIN_QUERY = 2

_cache: dict = {}


def _secret() -> bytes:
    from flask import current_app
    return str(current_app.secret_key or '').encode()


def code(email: str) -> str:
    """The profile's code for an email: the same email gives the same code."""
    return hmac.new(_secret(), f'player:{str(email or "").strip().lower()}'.encode(), hashlib.sha256).hexdigest()[:16]


def _clean(name) -> str:
    return ' '.join(str(name or '').split())


def public_event(event: dict) -> bool:
    """A sports event with a tournament that anyone may see."""
    from services_team_confirm import is_sports
    if not (event.get('tournament') or {}).get('teams'):
        return False
    if str(event.get('status') or 'active').strip().lower() in HIDDEN_STATUSES:
        return False
    visibility = str(event.get('visibility') or 'Public').strip().lower()
    if visibility == 'private' or visibility in ('department', 'department_only') or event.get('department_only'):
        return False
    return is_sports(event)


def _members(reg: dict) -> list:
    """The team's players: the lead, then the members, each with an email."""
    rows = [m for m in reg.get('members') or [] if isinstance(m, dict)]
    lead = str(reg.get('lead_email') or reg.get('student_email') or '').strip().lower()
    if lead and not any(str(m.get('email') or '').strip().lower() == lead for m in rows):
        rows = [{'name': reg.get('lead_name'), 'email': lead, 'jersey': reg.get('lead_jersey')}] + rows
    return [m for m in rows if str(m.get('email') or '').strip() and _clean(m.get('name'))]


def _index(db) -> dict:
    """{code: {'name', 'entries': [one per event]}} over the public sports
    events, kept a minute."""
    hit = _cache.get('index')
    if hit and hit[0] > time.monotonic():
        return hit[1]
    people: dict = {}
    for snap in db.collection('events').stream():
        event = dict(snap.to_dict() or {}, id=snap.id)
        if not public_event(event):
            continue
        t = event['tournament']
        logos = sports.logos(t)
        for team in t.get('teams') or []:
            rdoc = db.collection('registrations').document(team['id']).get()
            reg = (rdoc.to_dict() or {}) if rdoc.exists else {}
            if str(reg.get('status') or '').lower() in ('cancelled', 'refunded'):
                continue
            for m in _members(reg):
                c = code(m['email'])
                person = people.setdefault(c, {'code': c, 'name': _clean(m.get('name')), 'entries': []})
                person['entries'].append({
                    'event_id': event['id'], 'event': event.get('title') or 'Event', 'date': str(event.get('date') or ''),
                    'sport': t.get('sport') or '', 'team_id': team['id'], 'team': team.get('name') or '',
                    'logo': logos.get(team['id'], ''), 'name': _clean(m.get('name')),
                    'jersey': str(m.get('jersey') or (reg.get('lead_jersey') if m.get('role') == 'Lead' else '') or ''),
                    'position': str(m.get('position') or ''), 'dob': str(m.get('dob') or '')})
    for person in people.values():
        person['entries'].sort(key=lambda e: e['date'], reverse=True)    # the latest event first
        person['name'] = person['entries'][0]['name']
    _cache['index'] = (time.monotonic() + CACHE_SECONDS, people)
    return people


def search(db, query: str) -> list:
    """Players whose name has the words typed (any case), best match first."""
    words = str(query or '').strip().lower().split()
    if not words or len(''.join(words)) < MIN_QUERY:
        return []
    found = []
    for person in _index(db).values():
        names = {e['name'].lower() for e in person['entries']}
        if any(all(w in n for w in words) for n in names):
            latest = person['entries'][0]
            found.append({'code': person['code'], 'name': person['name'], 'team': latest['team'],
                          'logo': latest['logo'], 'jersey': latest['jersey'], 'position': latest['position'],
                          'events': len(person['entries']),
                          'starts': person['name'].lower().startswith(words[0])})
    found.sort(key=lambda r: (not r['starts'], r['name'].lower()))
    return found[:MAX_RESULTS]


# ── A player's numbers in one match ─────────────────────────────────────────

def _blank() -> dict:
    return {'raid': 0, 'tackle': 0, 'successful_raids': 0, 'super_raids': 0, 'tackles': 0, 'super_tackles': 0,
            'do_or_die': 0}


def _in_match(doc: dict, side: str, name: str) -> dict:
    """The player's numbers in a match scored live."""
    row, raids = _blank(), set()
    for e in doc.get('log') or []:
        if e.get('team') != side or _clean(e.get('player')) != name:
            continue
        if e.get('counts') == 'raid':
            row['raid'] += e['points']
            raids.add(e.get('event') or e.get('id'))
            row['super_raids'] += e.get('label') == 'Super raid'
            row['do_or_die'] += e['points'] if e.get('dod') else 0
        elif e.get('counts') == 'tackle':
            row['tackle'] += e['points']
            row['tackles'] += 1
            row['super_tackles'] += e.get('kind') == 'super_tackle'
    row['successful_raids'] = len(raids)
    return row


def _played(doc: dict, side: str, name: str, row: dict) -> bool:
    """In the seven, came on as a substitute, or scored."""
    lineup = (doc.get('lineup') or {}).get(side) or {}
    if name in [_clean(x) for x in lineup.get('start') or []]:
        return True
    if any(s.get('team') == side and _clean(s.get('on')) == name for s in (doc.get('mat') or {}).get('subs') or []):
        return True
    return bool(row['raid'] or row['tackle'] or row['tackles'])


def _result(m: dict, side_id: str, doc: dict) -> tuple:
    """('Won' / 'Lost' / 'Tied' / 'Playing', 'their score–the other's')."""
    home = m.get('home') == side_id
    if m.get('status') == 'played' and m.get('home_score') not in (None, ''):
        mine, theirs = (m['home_score'], m['away_score']) if home else (m['away_score'], m['home_score'])
        word = 'Won' if m.get('winner') == side_id else 'Tied' if not m.get('winner') else 'Lost'
        return word, f'{mine}–{theirs}'
    if doc and doc.get('phase') in live.IN_PLAY:
        sc = live.score(doc)
        mine, theirs = (sc['home']['total'], sc['away']['total']) if home else (sc['away']['total'], sc['home']['total'])
        return 'Playing', f'{mine}–{theirs}'
    return '', ''


# ── The profile ─────────────────────────────────────────────────────────────

TOTALS = ('matches', 'raid', 'tackle', 'total', 'successful_raids', 'super_raids', 'tackles', 'super_tackles',
          'do_or_die', 'super_10', 'high_5', 'potm')


def _event_part(db, entry: dict) -> dict:
    """The player's numbers in one event, match by match, and the event's
    achievements for them."""
    edoc = db.collection('events').document(entry['event_id']).get()
    event = (edoc.to_dict() or {}) if edoc.exists else {}
    t = event.get('tournament') or {}
    names = sports.names(t)
    docs = {d.get('match_id'): d for d in (snap.to_dict() or {} for snap in
            db.collection(live.COLLECTION).where('event_id', '==', entry['event_id']).stream())}
    team, name = entry['team_id'], entry['name']
    totals = {k: 0 for k in TOTALS}
    matches = []
    for m in t.get('matches') or []:
        if team not in (m.get('home'), m.get('away')):
            continue
        side = 'home' if m.get('home') == team else 'away'
        doc = docs.get(m.get('id'))
        if not doc or doc.get('phase') == 'not_started':
            continue
        row = _in_match(doc, side, name)
        if not _played(doc, side, name, row):
            continue
        pm = doc.get('potm') or {}
        potm = pm.get('team') == side and _clean(pm.get('name')) == name
        word, scoreline = _result(m, team, doc)
        other = m.get('away') if side == 'home' else m.get('home')
        matches.append(dict(row, id=m['id'], no=sports.match_no(m), stage=sports.stage_name(m),
                            date=m.get('date') or '', opponent=names.get(other, 'TBD'), result=word,
                            score=scoreline, potm=potm, total=row['raid'] + row['tackle'],
                            url=f"/tournament/live/{entry['event_id']}/{m['id']}"))
        for k in _blank():
            totals[k] += row[k]
        totals['matches'] += 1
        totals['super_10'] += row['raid'] >= live.SUPER_10
        totals['high_5'] += row['tackle'] >= live.HIGH_5
        totals['potm'] += potm
    totals['total'] = totals['raid'] + totals['tackle']

    achievements = []
    places = sports.placings(t)
    if places.get(team) == 1:
        achievements.append({'kind': 'champion', 'text': f"Champion · {entry['event']}"})
    elif places.get(team) == 2:
        achievements.append({'kind': 'runner_up', 'text': f"Runner-up · {entry['event']}"})
    if places:   # the tournament is over: its top raider and defender
        stats = live.player_stats(list(docs.values()), names)
        for kind, label in (('raid', 'Top raider'), ('tackle', 'Top defender')):
            best = max((r[kind] for r in stats), default=0)
            if best and any(r[kind] == best and r['team_id'] == team and _clean(r['player']) == name for r in stats):
                achievements.append({'kind': f'top_{kind}', 'text': f"{label} · {entry['event']} · {best} points"})
    for mt in matches:
        if mt['potm']:
            achievements.append({'kind': 'potm', 'text': f"Player of the match · {mt['no']} v {mt['opponent']}"})
    for mt in matches:
        if mt['raid'] >= live.SUPER_10:
            achievements.append({'kind': 'super_10', 'text': f"Super 10 · {mt['raid']} raid points · {mt['no']}"})
        if mt['tackle'] >= live.HIGH_5:
            achievements.append({'kind': 'high_5', 'text': f"High 5 · {mt['tackle']} tackle points · {mt['no']}"})
    return {**entry, 'url': f"/tournament/fixtures/{entry['event_id']}", 'totals': totals, 'matches': matches,
            'achievements': achievements}


def profile(db, player_code: str):
    """The profile for a code, or None. Never the date of birth, email, phone or USN."""
    from routes_forms import age_on
    person = _index(db).get(str(player_code or '').strip().lower())
    if not person:
        return None
    latest = person['entries'][0]
    dob = next((e['dob'] for e in person['entries'] if e['dob']), '')
    events = [_event_part(db, e) for e in person['entries']]
    for e in events:
        e.pop('dob', None)
    career = {k: sum(e['totals'][k] for e in events) for k in TOTALS}
    return {'code': person['code'], 'name': person['name'], 'team': latest['team'], 'logo': latest['logo'],
            'jersey': latest['jersey'], 'sport': latest['sport'],
            'position': next((e['position'] for e in person['entries'] if e['position']), ''),
            'age': age_on(dob), 'events': events, 'career': career,
            'achievements': [a for e in events for a in e['achievements']]}


def links(db, event_id: str) -> dict:
    """{(team id, player's name): profile code} for an event's players, so its
    pages link the names to the profiles."""
    out = {}
    for person in _index(db).values():
        for e in person['entries']:
            if e['event_id'] == event_id:
                out[(e['team_id'], e['name'])] = person['code']
    return out
