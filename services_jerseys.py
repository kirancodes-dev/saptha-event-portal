"""
services_jerseys.py — the SPOC's Jersey numbers page (UPG-461)

Every team of a sports tournament and each of its players' jersey numbers on
one page: the SPOC changes any of them and saves once. Each number is written
the way the registration's Edit page writes it (UPG-225,
`services_registration_edit.apply`), so the registration, its form answers,
the form responses, the squads the scorer picks from, the public team details
and the line-ups of matches not yet over all show the new one. Two players of
a team may share a number (the owner, UPG-460): the page says so but saves.
"""
import re

import services_registration_edit as edit

NUMBER = re.compile(r'^\d{1,3}$')


def _teams(db, event_id: str, event: dict) -> list:
    """The tournament's teams in its order, else the confirmed registrations."""
    t = event.get('tournament') or {}
    if t.get('teams'):
        return [{'id': x['id'], 'name': x.get('name') or '', 'pool': x.get('pool') or '',
                 'logo': x.get('logo') or ''} for x in t['teams'] if x.get('id')]
    import services_sports
    return [{'id': x['id'], 'name': x.get('name') or '', 'pool': '', 'logo': ''}
            for x in services_sports.confirmed_teams(db, event_id)]


def _input(reg_id: str, who: str) -> str:
    return f"j|{reg_id}|{who}"


def sheet(db, event_id: str, event: dict) -> list:
    """[{'id', 'name', 'pool', 'logo', 'players': [{'input', 'who', 'name',
    'lead', 'number', 'shared'}]}]: `who` is 'lead' or the member's key
    (email, else 'name:' and the name); `shared` when a teammate has the
    same number."""
    out = []
    for team in _teams(db, event_id, event):
        snap = db.collection('registrations').document(team['id']).get()
        reg = (snap.to_dict() or {}) if snap.exists else {}
        if not reg or edit.cancelled(reg) or str(reg.get('event_id') or '') != event_id:
            continue
        page = edit.build(db, event_id, event, reg)
        values = page['values']
        players = [{'who': 'lead', 'name': values.get('lead_name') or 'The lead', 'lead': True,
                    'number': str(values.get(f['name']) or ''), 'field': f['name']}
                   for f in page['lead'] if f['key'] == 'jersey']
        for m in page['members']:
            for p in m['parts']:
                if p['key'] == 'jersey':
                    players.append({'who': m['key'], 'name': m['name'] or f"Member {m['n']}", 'lead': False,
                                    'number': str(values.get(p['name']) or ''), 'field': p['name']})
        counts: dict = {}
        for p in players:
            if p['number']:
                counts[p['number']] = counts.get(p['number'], 0) + 1
        for p in players:
            p['input'] = _input(team['id'], p['who'])
            p['shared'] = bool(p['number']) and counts[p['number']] > 1
        out.append(dict(team, players=players, page=page))
    return out


def save(db, event_id: str, event: dict, form, by: str) -> dict:
    """Save the numbers the page sent. All or nothing: a number that isn't
    0 to 999 stops the save and is shown beside its player. {'errors': {input:
    message}, 'values': {input: what was sent}, 'teams': [names saved],
    'players': how many numbers changed, 'shared': [notes], 'lineups': how many
    matches' line-ups took the new numbers}."""
    from routes_forms import JERSEY_FIELD, jersey_number
    teams = sheet(db, event_id, event)
    out = {'errors': {}, 'values': {}, 'teams': [], 'players': 0, 'shared': [], 'lineups': 0}
    plans = []
    for team in teams:
        sent = {}
        for p in team['players']:
            raw = form.get(p['input'])
            if raw is None:
                continue
            value = jersey_number(str(raw).strip())
            out['values'][p['input']] = str(raw).strip()
            if value and not NUMBER.match(value):
                out['errors'][p['input']] = JERSEY_FIELD['pattern_error']
                continue
            if value != p['number']:
                sent[p['field']] = value
        if sent:
            plans.append((team, sent))
    if out['errors'] or not plans:
        return out

    changed_ids = []
    for team, sent in plans:
        page = team['page']
        data = {f"m{m['index']}_key": m['key'] for m in page['members']}   # as the Edit page names them
        data.update(sent)
        only = {name for name in sent if not name.startswith('m')}
        result = edit.apply(db, team['id'], event_id, event, data, by, organiser=True, only=only)
        if result['errors']:   # not expected: the numbers were checked above
            for p in team['players']:
                if p['field'] in result['errors']:
                    out['errors'][p['input']] = result['errors'][p['field']]
            continue
        if result['changed']:
            out['teams'].append(team['name'])
            out['players'] += len(result['changed'])
            out['shared'] += [f"{team['name']}: {note}" for note in result['shared']]
            changed_ids.append(team['id'])
    if changed_ids:
        import services_live_match as live
        out['lineups'] = live.refresh_jerseys(db, event_id, changed_ids)
    return out
