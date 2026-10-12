"""
services_leaderboard.py — one ranking for every leaderboard (UPG-84).

The projector board, the live board, the judges' board, the SPOC's results,
the AI report and results publishing all rank through `rank()`, so a team has
the same score and place everywhere:

- A judge's score is `total` (judge panel) or `final_score` (evaluation engine).
- A team's score is the average over the judges who scored it, to 2 decimals.
- Equal scores share a place (1, 2, 2, 4); within a tie the order follows the
  innovation, impact, clarity and presentation criteria, then the team name.
- Eliminated and cancelled registrations are left out.
"""
from typing import Optional

TIEBREAK_CRITERIA = ('innovation', 'impact', 'clarity', 'presentation')


def judge_score(entry) -> Optional[float]:
    """One judge's score for a team, whichever way it was stored."""
    if isinstance(entry, (int, float)) and not isinstance(entry, bool):
        return float(entry)
    if not isinstance(entry, dict):
        return None
    for key in ('total', 'final_score', 'score'):
        value = entry.get(key)
        if value in (None, ''):
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def score_of(reg: dict) -> tuple:
    """(average score or None, number of judges who scored)."""
    values = [v for v in (judge_score(e) for e in (reg.get('scores') or {}).values()) if v is not None]
    if not values:
        return None, 0
    return round(sum(values) / len(values), 2), len(values)


def _criteria(reg: dict) -> dict:
    """Average per criterion (lower-cased) across judges."""
    sums: dict = {}
    for entry in (reg.get('scores') or {}).values():
        if not isinstance(entry, dict):
            continue
        detail = entry.get('details') or entry.get('breakdown') or entry.get('raw_scores') or {}
        if not isinstance(detail, dict):
            continue
        for name, value in detail.items():
            if isinstance(value, dict):
                value = value.get('score', value.get('value'))
            try:
                sums.setdefault(str(name).lower(), []).append(float(value))
            except (TypeError, ValueError):
                continue
    return {k: sum(v) / len(v) for k, v in sums.items()}


def score_text(score) -> str:
    """How a score is shown on every board: up to 2 decimals, no trailing zeros."""
    if score is None:
        return '—'
    return f"{score:.2f}".rstrip('0').rstrip('.')


def _excluded(reg: dict) -> bool:
    return bool(reg.get('is_eliminated')) or str(reg.get('status') or '').lower() in ('cancelled', 'refunded')


def rank(regs, *, include_unscored: bool = False) -> list:
    """Ranked rows. `regs` are registration dicts carrying their `id`.
    Unscored teams come last with no rank when `include_unscored` is set."""
    rows = []
    for reg in regs:
        if _excluded(reg):
            continue
        score, judges = score_of(reg)
        if score is None and not include_unscored:
            continue
        team_name = (reg.get('team_name') or '').strip()
        lead_name = (reg.get('lead_name') or '').strip()
        rows.append({
            'id': str(reg.get('id') or ''),
            'team': team_name or lead_name or '—',
            'team_name': team_name or lead_name or '—',
            'lead_name': lead_name,
            'lead_email': reg.get('lead_email') or '',
            'members': len(reg.get('members') or []),
            'room': reg.get('assigned_room') or '',
            'round': int(reg.get('current_round') or 1),
            'attended': reg.get('attendance') == 'Present',
            'score': score,
            'judges': judges,
            'score_text': score_text(score),
            '_criteria': _criteria(reg),
        })
    rows.sort(key=lambda r: (
        r['score'] is None,
        -(r['score'] or 0),
        tuple(-r['_criteria'].get(c, 0) for c in TIEBREAK_CRITERIA),
        r['team'].lower(),
    ))
    place, previous = 0, None
    for i, row in enumerate(rows, 1):
        del row['_criteria']
        if row['score'] is None:
            row['rank'], row['tied'] = None, False
            continue
        if row['score'] != previous:
            place, previous = i, row['score']
        row['rank'] = place
    scored = [r for r in rows if r['rank'] is not None]
    counts: dict = {}
    for row in scored:
        counts[row['rank']] = counts.get(row['rank'], 0) + 1
    for row in scored:
        row['tied'] = counts[row['rank']] > 1
    return rows


def for_event(db, event_id: str, *, include_unscored: bool = False) -> list:
    """`rank()` over an event's registrations."""
    regs = []
    for doc in db.collection('registrations').where('event_id', '==', event_id).stream():
        d = doc.to_dict() or {}
        d['id'] = doc.id
        regs.append(d)
    return rank(regs, include_unscored=include_unscored)


def podium(rows: list) -> list:
    """Everyone placed 1st to 3rd (more than three when places are shared)."""
    return [r for r in rows if r['rank'] is not None and r['rank'] <= 3]
