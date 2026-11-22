"""
services_score_sheet.py — a match's score sheet as a PDF (UPG-419), made from
its live log (services_live_match): the teams, who raided first, the line-ups,
each half's points, all outs, time-outs, reviews, the tie-breaker, the result,
the player of the match, every player's points, and lines for the officials'
signatures. "Provisional" until full time.
"""
import io
import logging
import os

import services_live_match as live
import services_sports

logger = logging.getLogger(__name__)

SIGNATURES = ('Scorer', 'Umpire 1', 'Umpire 2', 'Referee')
_logo_bytes = {}


def _logo(url: str):
    """A team's logo for the sheet: the local file, else the stored address
    (fetched once, 4 seconds at most). None when it can't be read."""
    from reportlab.lib.utils import ImageReader
    if not url:
        return None
    try:
        if url.startswith('/static/'):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), url.lstrip('/').split('?')[0])
            return ImageReader(path) if os.path.isfile(path) else None
        if not url.startswith('https://'):
            return None
        if url not in _logo_bytes:
            import urllib.request
            req = urllib.request.Request(url, headers={'User-Agent': 'SapthaEvent/1.0'})
            with urllib.request.urlopen(req, timeout=4) as resp:  # nosec B310 (our own storage's https address)
                _logo_bytes[url] = resp.read(2_000_000)
        return ImageReader(io.BytesIO(_logo_bytes[url]))
    except Exception as exc:                               # a missing logo never stops the sheet
        logger.warning("Score sheet logo not read (%s): %s", url, exc)
        return None


def sheet_data(event: dict, match: dict, doc: dict, names: dict, numbers: dict) -> dict:
    """Everything the sheet prints, worked out from the live log. `numbers`:
    {team id: {player: jersey}} for players without a line-up."""
    t = event.get('tournament') or {}
    pkl = live.is_pkl(doc)
    mat = (doc.get('mat') or live.replay(doc)) if pkl else None
    halves = {side: [{'raid': 0, 'tackle': 0, 'extra': 0, 'all_outs': 0, 'total': 0} for _ in (1, 2)]
              for side in ('home', 'away')}
    for e in doc.get('log') or []:
        h = halves[e['team']][min(2, max(1, int(e.get('half') or 1))) - 1]
        counts = e.get('counts') if e.get('counts') in ('raid', 'tackle') else 'extra'
        h[counts] += e['points']
        h['total'] += e['points']
        h['all_outs'] += e.get('kind') == 'all_out'
    timeouts = {side: [0, 0] for side in ('home', 'away')}
    reviews = {side: {'used': 0, 'upheld': 0} for side in ('home', 'away')}
    for ev in doc.get('events') or []:
        side = ev.get('team')
        if side not in ('home', 'away'):
            continue
        if ev.get('type') == 'timeout':
            timeouts[side][min(2, int(ev.get('half') or 1)) - 1] += 1
        elif ev.get('type') == 'review':
            reviews[side]['used'] += 1
            reviews[side]['upheld'] += bool(ev.get('upheld'))
    lineups = live.lineups(doc)
    players = []
    for (team_id, player), pts in sorted(live._match_players(doc).items(),
                                         key=lambda x: (x[0][0] != doc.get('home'), -(x[1]['raid'] + x[1]['tackle']),
                                                        x[0][1].lower())):
        side = 'home' if team_id == doc.get('home') else 'away'
        number = live.jersey_of(doc, side, player) or (numbers.get(team_id) or {}).get(player, '')
        players.append({'team': names.get(team_id, ''), 'side': side, 'name': player, 'jersey': number,
                        'raid': pts['raid'], 'tackle': pts['tackle'], 'total': pts['raid'] + pts['tackle']})
    totals = live.score(doc)
    result = doc.get('result') or {}
    sh = live.shootout_state(doc, names) if doc.get('shootout') or result.get('tiebreak') else None
    potm = live._potm(doc, names)
    if potm and not potm.get('jersey'):
        potm['jersey'] = (numbers.get(doc.get(potm['team'])) or {}).get(potm['name'], '')
    first = (mat or {}).get('first_raid') or doc.get('first_raid')
    return {
        'event': event.get('title') or '', 'match_no': services_sports.match_no(match),
        'stage': services_sports.stage_name(match), 'pool': match.get('pool') or '',
        'date': match.get('date') or event.get('date') or '', 'time': match.get('time') or '',
        'venue': match.get('venue') or event.get('venue') or '',
        'teams': {side: names.get(doc.get(side), 'TBD') for side in ('home', 'away')},
        'logos': {side: services_sports.logos(t).get(doc.get(side), '') for side in ('home', 'away')},
        'provisional': doc.get('phase') != 'full_time', 'phase': live.PHASE_NAMES.get(doc.get('phase'), ''),
        'pkl': pkl, 'first_raid': names.get(doc.get(first), '') if pkl and first in ('home', 'away') else '',
        'lineups': lineups, 'halves': halves, 'timeouts': timeouts, 'reviews': reviews,
        'totals': {side: totals[side]['total'] for side in ('home', 'away')},
        'all_outs': {side: sum(h['all_outs'] for h in halves[side]) for side in ('home', 'away')},
        'tiebreak': sh, 'winner': names.get(result.get('winner'), '') if result.get('winner') else '',
        'result': result, 'potm': potm, 'players': players,
    }


def render(data: dict) -> bytes:
    """The sheet as a one- or two-page A4 PDF."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    out = io.BytesIO()
    page = SimpleDocTemplate(out, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=12 * mm,
                             bottomMargin=12 * mm, title=f"Score sheet {data['match_no']} · {data['event']}")
    styles = getSampleStyleSheet()
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8.5, leading=11)
    head = ParagraphStyle('head', parent=styles['Heading3'], fontSize=11, spaceBefore=6, spaceAfter=3)
    grid = TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                       ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
                       ('FONTSIZE', (0, 0), (-1, -1), 8.5), ('VALIGN', (0, 0), (-1, -1), 'TOP')])
    home, away = data['teams']['home'], data['teams']['away']
    story = []
    if data['provisional']:
        story.append(Paragraph(f"<font color='#b91c1c'><b>PROVISIONAL</b></font> · the match is not over "
                               f"({data['phase']}). The final sheet comes at full time.", styles['Normal']))
    story.append(Paragraph(f"<b>{_x(data['event'])}</b> · Score sheet", styles['Title']))
    where = ' · '.join(x for x in (data['match_no'], data['stage'], f"Pool {data['pool']}" if data['pool'] else '',
                                   f"{data['date']} {data['time']}".strip(), data['venue']) if x)
    story.append(Paragraph(_x(where), styles['Normal']))
    story.append(Spacer(1, 4 * mm))

    def team_cell(side):
        logo = _logo(data['logos'][side])
        name = Paragraph(f"<para alignment='center'><b>{_x(data['teams'][side])}</b></para>", styles['Heading2'])
        score = Paragraph(f"<para alignment='center'><font size='26'><b>{data['totals'][side]}</b></font></para>",
                          styles['Normal'])
        rows = [[Image(logo, width=18 * mm, height=18 * mm)]] if logo else []
        return Table(rows + [[name], [Spacer(1, 5 * mm)], [score]], colWidths=[70 * mm])
    board = Table([[team_cell('home'), Paragraph("<para alignment='center'><b>v</b></para>", styles['Normal']),
                    team_cell('away')]], colWidths=[75 * mm, 30 * mm, 75 * mm])
    board.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE')]))
    story.append(board)
    lines = []
    if data['winner']:
        lines.append(f"<b>Result:</b> {_x(data['winner'])} won {data['totals']['home']}–{data['totals']['away']}")
    elif not data['provisional']:
        lines.append(f"<b>Result:</b> tied {data['totals']['home']}–{data['totals']['away']}")
    if data['first_raid']:
        lines.append(f"<b>Raided first:</b> {_x(data['first_raid'])} (won the toss)")
    if data['potm']:
        p = data['potm']
        lines.append(f"<b>Player of the match:</b> {_x(_tag(p))} ({_x(p['team_name'])}), {p['points']} points "
                     f"(raid {p['raid']}, tackle {p['tackle']})")
    for line in lines:
        story.append(Paragraph(line, styles['Normal']))

    story.append(Paragraph('Points by half', head))
    rows = [['', f'{home} 1st', f'{home} 2nd', f'{home} total', f'{away} 1st', f'{away} 2nd', f'{away} total']]
    for key, label in (('raid', 'Raid points'), ('tackle', 'Tackle points'), ('extra', 'All outs and extras'),
                       ('all_outs', 'All outs (times)'), ('total', 'Total')):
        row = [label]
        for side in ('home', 'away'):
            h = data['halves'][side]
            row += [h[0][key], h[1][key], h[0][key] + h[1][key]]
        rows.append(row)
    rows.append(['Time-outs'] + [x for side in ('home', 'away') for x in
                                 (data['timeouts'][side][0], data['timeouts'][side][1], sum(data['timeouts'][side]))])
    rows.append(['Reviews (upheld)'] + [x for side in ('home', 'away') for x in
                                        ('', '', f"{data['reviews'][side]['used']} ({data['reviews'][side]['upheld']})")])
    table = Table([[Paragraph(_x(str(c)), small) for c in r] for r in rows],
                  colWidths=[38 * mm] + [24 * mm] * 6, repeatRows=1)
    table.setStyle(grid)
    story.append(table)

    if data['tiebreak']:
        sh = data['tiebreak']
        story.append(Paragraph('Tie-breaker', head))
        way = services_sports.TIEBREAK_WAYS.get(sh.get('decided'), 'tie-breaker')
        text = f"{_x(home)} {sh['home']} – {sh['away']} {_x(away)}"
        if sh.get('winner'):
            text += f" · {_x(data['teams'][sh['winner']])} won the {_x(way)}"
        story.append(Paragraph(text, styles['Normal']))
        for line in sh.get('lines') or []:
            story.append(Paragraph(_x(line), small))

    story.append(Paragraph('Line-ups', head))
    if data['lineups']:
        cells = []
        for side in ('home', 'away'):
            lu = data['lineups'][side]
            text = f"<b>{_x(data['teams'][side])}</b><br/>Starting seven: " + ', '.join(_x(_tag(p)) for p in lu['start'])
            if lu['subs']:
                text += '<br/>Substitutes: ' + ', '.join(_x(_tag(p)) for p in lu['subs'])
            cells.append(Paragraph(text, small))
        lu_table = Table([cells], colWidths=[90 * mm, 90 * mm])
        lu_table.setStyle(TableStyle([('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#94a3b8')),
                                      ('VALIGN', (0, 0), (-1, -1), 'TOP')]))
        story.append(lu_table)
    else:
        story.append(Paragraph('No line-ups were saved for this match (it was scored by count).', small))

    story.append(Paragraph("Players' points", head))
    if data['players']:
        rows = [['Team', 'No.', 'Player', 'Raid', 'Tackle', 'Total']] + [
            [p['team'], p['jersey'], p['name'], p['raid'], p['tackle'], p['total']] for p in data['players']]
        table = Table([[Paragraph(_x(str(c)), small) for c in r] for r in rows],
                      colWidths=[48 * mm, 14 * mm, 58 * mm, 20 * mm, 20 * mm, 20 * mm], repeatRows=1)
        table.setStyle(grid)
        story.append(table)
    else:
        story.append(Paragraph('No points were given to a named player.', small))

    story.append(Spacer(1, 10 * mm))
    signs = Table([['_' * 26] * len(SIGNATURES), list(SIGNATURES)], colWidths=[45 * mm] * len(SIGNATURES))
    signs.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (0, 0), (-1, -1), 'CENTER')]))
    story.append(signs)
    page.build(story)
    return out.getvalue()


def _tag(p: dict) -> str:
    return f"#{p['jersey']} {p['name']}" if p.get('jersey') else p['name']


def _x(text: str) -> str:
    """Text for a reportlab paragraph: &, < and > escaped."""
    return str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
