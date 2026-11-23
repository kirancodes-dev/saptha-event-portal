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
    """A team's logo for the sheet as PNG bytes: the local file, else the stored
    address (fetched once, 4 seconds at most). None when it can't be read.
    (UPG-472: before, a team with a logo made the sheet fail.)"""
    if not url:
        return None
    try:
        if url.startswith('/static/'):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), url.lstrip('/').split('?')[0])
            if not os.path.isfile(path):
                return None
            with open(path, 'rb') as fh:
                raw = fh.read(2_000_000)
        elif url.startswith('https://'):
            if url not in _logo_bytes:
                import urllib.request
                req = urllib.request.Request(url, headers={'User-Agent': 'SapthaEvent/1.0'})
                with urllib.request.urlopen(req, timeout=4) as resp:  # nosec B310 (our own storage's https address)
                    _logo_bytes[url] = resp.read(2_000_000)
            raw = _logo_bytes[url]
        else:
            return None
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(raw)) as im:          # WebP and the rest → PNG reportlab reads
            im = im.convert('RGBA')
            im.thumbnail((400, 400))
            buf = io.BytesIO()
            im.save(buf, 'PNG')
        return buf.getvalue()
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


COLLEGE_LOGO = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'snpsu-logo.jpg')   # for white paper
NAVY, LINE, SHADE, SOFT = '#1e293b', '#94a3b8', '#e2e8f0', '#f8fafc'


def render(data: dict) -> bytes:
    """The sheet as a one- or two-page A4 PDF (UPG-472): the college's logo and
    the event at the top, the score in a box with each team's logo, then the
    result, the points by half, the line-ups and each team's players side by
    side, the officials' signatures, and a footer on every page."""
    from datetime import datetime, timedelta, timezone

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    out = io.BytesIO()
    width = A4[0] - 28 * mm
    title = f"Score sheet {data['match_no']} · {data['event']}"
    page = SimpleDocTemplate(out, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=10 * mm,
                             bottomMargin=16 * mm, title=title)
    styles = getSampleStyleSheet()
    normal = ParagraphStyle('n', parent=styles['Normal'], fontSize=9.5, leading=13)
    small = ParagraphStyle('small', parent=normal, fontSize=8.5, leading=11)
    centre = ParagraphStyle('c', parent=small, alignment=1)
    head = ParagraphStyle('head', parent=styles['Heading3'], fontSize=11.5, leading=14, spaceBefore=8, spaceAfter=4,
                          textColor=colors.HexColor(NAVY))
    event_style = ParagraphStyle('ev', parent=normal, fontName='Helvetica-Bold', fontSize=14, leading=17, alignment=2)
    sub_style = ParagraphStyle('sub', parent=normal, fontSize=9, leading=12, alignment=2,
                               textColor=colors.HexColor('#475569'))
    team_style = ParagraphStyle('team', parent=normal, fontName='Helvetica-Bold', fontSize=13, leading=16, alignment=1)
    score_style = ParagraphStyle('score', parent=normal, fontName='Helvetica-Bold', fontSize=34, leading=40,
                                 alignment=1)
    home, away = data['teams']['home'], data['teams']['away']
    navy, line, shade = colors.HexColor(NAVY), colors.HexColor(LINE), colors.HexColor(SHADE)
    story = []

    # The top: the college's logo on the left, the event and the match on the right
    college = _college_logo()
    logo = Image(io.BytesIO(college[0]), width=52 * mm, height=52 * mm * college[1]) if college else ''
    where = ' · '.join(x for x in (data['match_no'], data['stage'], f"Pool {data['pool']}" if data['pool'] else '',
                                   f"{data['date']} {data['time']}".strip(), data['venue']) if x)
    top = Table([[logo, [Paragraph(f"{_x(data['event'])}", event_style),
                         Paragraph('<b>Score sheet</b>', ParagraphStyle('ss', parent=sub_style, fontSize=11,
                                                                       leading=14, textColor=navy)),
                         Paragraph(_x(where), sub_style)]]],
                colWidths=[58 * mm, width - 58 * mm])
    top.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (0, 0), 0),
                             ('RIGHTPADDING', (-1, 0), (-1, 0), 0), ('LINEBELOW', (0, 0), (-1, 0), 2, navy),
                             ('BOTTOMPADDING', (0, 0), (-1, 0), 6)]))
    story.append(top)
    story.append(Spacer(1, 3 * mm))
    if data['provisional']:
        banner = Table([[Paragraph(f"<font color='#b91c1c'><b>PROVISIONAL</b></font> · the match is not over "
                                   f"({_x(data['phase'])}). The final sheet comes at full time.", small)]],
                       colWidths=[width])
        banner.setStyle(TableStyle([('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fef2f2')),
                                    ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#b91c1c'))]))
        story += [banner, Spacer(1, 3 * mm)]

    # The score: each team's logo (or its initials), name and points; the result under it
    def badge(side):
        img = _logo(data['logos'][side])
        if img:
            return Image(io.BytesIO(img), width=20 * mm, height=20 * mm, kind='proportional')
        from reportlab.graphics.shapes import Circle, Drawing, String
        d = Drawing(20 * mm, 20 * mm)
        d.add(Circle(10 * mm, 10 * mm, 9.5 * mm, fillColor=navy, strokeColor=None))
        d.add(String(10 * mm, 7.6 * mm, _initials(data['teams'][side]), fontName='Helvetica-Bold', fontSize=18,
                     fillColor=colors.white, textAnchor='middle'))
        return d

    side_w, mid_w = (width - 24 * mm) / 2, 24 * mm
    won = {s: data['winner'] and data['teams'][s] == data['winner'] for s in ('home', 'away')}
    board = Table([
        [badge('home'), '', badge('away')],
        [Paragraph(_x(home), team_style), Paragraph('v', ParagraphStyle('v', parent=centre, fontSize=11)),
         Paragraph(_x(away), team_style)],
        [Paragraph(str(data['totals']['home']), score_style), Paragraph('–', score_style),
         Paragraph(str(data['totals']['away']), score_style)],
    ], colWidths=[side_w, mid_w, side_w])
    look = [('BOX', (0, 0), (-1, -1), 1, navy), ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(SOFT)),
            ('TOPPADDING', (0, 0), (-1, 0), 8), ('BOTTOMPADDING', (0, -1), (-1, -1), 8)]
    for col, s in ((0, 'home'), (2, 'away')):
        if won[s]:
            look.append(('BACKGROUND', (col, 0), (col, -1), colors.HexColor('#ecfdf5')))
    board.setStyle(TableStyle(look))
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
    if lines:
        facts = Table([[Paragraph(x, normal)] for x in lines], colWidths=[width])
        facts.setStyle(TableStyle([('BOX', (0, 0), (-1, -1), 0.5, line), ('LINEBELOW', (0, 0), (-1, -2), 0.25, line),
                                   ('TOPPADDING', (0, 0), (-1, -1), 4), ('BOTTOMPADDING', (0, 0), (-1, -1), 4)]))
        story += [Spacer(1, 3 * mm), facts]

    def grid(table, header_rows=1, bold_rows=()):
        look = [('GRID', (0, 0), (-1, -1), 0.5, line), ('BACKGROUND', (0, 0), (-1, header_rows - 1), shade),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3)]
        for r in range(header_rows, len(table._cellvalues)):
            if (r - header_rows) % 2:
                look.append(('BACKGROUND', (0, r), (-1, r), colors.HexColor(SOFT)))
        for r in bold_rows:
            look += [('BACKGROUND', (0, r), (-1, r), colors.HexColor('#dbeafe')),
                     ('LINEABOVE', (0, r), (-1, r), 1, navy)]
        table.setStyle(TableStyle(look))
        return table

    # Points by half: a team over its own three columns
    rows = [['', Paragraph(f'<b>{_x(home)}</b>', centre), '', '', Paragraph(f'<b>{_x(away)}</b>', centre), '', ''],
            [''] + [Paragraph(f'<b>{x}</b>', centre) for x in ('1st half', '2nd half', 'Total') * 2]]
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
    total_row = 6
    cells = [[c if not isinstance(c, (str, int)) else
              Paragraph((f'<b>{_x(str(c))}</b>' if r == total_row else _x(str(c))), small if j == 0 else centre)
              for j, c in enumerate(row)] for r, row in enumerate(rows)]
    table = Table(cells, colWidths=[40 * mm] + [(width - 40 * mm) / 6] * 6, repeatRows=2)
    grid(table, header_rows=2, bold_rows=(total_row,))
    table.setStyle(TableStyle([('SPAN', (1, 0), (3, 0)), ('SPAN', (4, 0), (6, 0)),
                               ('LINEAFTER', (3, 0), (3, -1), 1.2, navy)]))
    story.append(KeepTogether([Paragraph('Points by half', head), table]))

    if data['tiebreak']:
        sh = data['tiebreak']
        way = services_sports.TIEBREAK_WAYS.get(sh.get('decided'), 'tie-breaker')
        text = f"{_x(home)} {sh['home']} – {sh['away']} {_x(away)}"
        if sh.get('winner'):
            text += f" · {_x(data['teams'][sh['winner']])} won the {_x(way)}"
        story.append(Paragraph('Tie-breaker', head))
        story.append(Paragraph(text, normal))
        for line_text in sh.get('lines') or []:
            story.append(Paragraph(_x(line_text), small))

    half_w = (width - 4 * mm) / 2

    def two(left, right):
        t = Table([[left, '', right]], colWidths=[half_w, 4 * mm, half_w])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), 0),
                               ('RIGHTPADDING', (0, 0), (-1, -1), 0)]))
        return t

    if data['lineups']:
        boxes = []
        for side in ('home', 'away'):
            lu = data['lineups'][side]
            text = 'Starting seven: ' + ', '.join(_x(_tag(p)) for p in lu['start'])
            if lu['subs']:
                text += '<br/>Substitutes: ' + ', '.join(_x(_tag(p)) for p in lu['subs'])
            boxes.append(grid(Table([[Paragraph(f"<b>{_x(data['teams'][side])}</b>", small)],
                                     [Paragraph(text, small)]], colWidths=[half_w])))
        story.append(KeepTogether([Paragraph('Line-ups', head), two(*boxes)]))
    else:
        story += [Paragraph('Line-ups', head),
                  Paragraph('No line-ups were saved for this match (it was scored by count).', small)]

    if data['players']:
        boxes = []
        for side in ('home', 'away'):
            mine = [p for p in data['players'] if p['side'] == side]
            rows = [[Paragraph(f"<b>{_x(data['teams'][side])}</b>", small), '', '', '', ''],
                    [Paragraph(f'<b>{x}</b>', centre) for x in ('No.', 'Player', 'Raid', 'Tackle', 'Total')]]
            rows += [[Paragraph(_x(str(p['jersey'])), centre), Paragraph(_x(p['name']), small),
                      Paragraph(str(p['raid']), centre), Paragraph(str(p['tackle']), centre),
                      Paragraph(f"<b>{p['total']}</b>", centre)] for p in mine]
            if not mine:
                rows.append(['', Paragraph('No points', small), '', '', ''])
            t = Table(rows, colWidths=[11 * mm, half_w - 56 * mm, 15 * mm, 15 * mm, 15 * mm], repeatRows=2)
            grid(t, header_rows=2)
            t.setStyle(TableStyle([('SPAN', (0, 0), (-1, 0)), ('BACKGROUND', (0, 0), (-1, 0), navy),
                                   ('TEXTCOLOR', (0, 0), (-1, 0), colors.white)]))
            t._cellvalues[0][0] = Paragraph(f"<font color='white'><b>{_x(data['teams'][side])}</b></font>", small)
            boxes.append(t)
        story.append(Paragraph("Players' points", head))
        story.append(two(*boxes))
    else:
        story += [Paragraph("Players' points", head), Paragraph('No points were given to a named player.', small)]

    gap = 8 * mm
    each = (width - gap * (len(SIGNATURES) - 1)) / len(SIGNATURES)
    blank, names_row, widths = [], [], []
    for i, who in enumerate(SIGNATURES):
        if i:
            blank.append('')
            names_row.append('')
            widths.append(gap)
        blank.append('')
        names_row.append(who)
        widths.append(each)
    signs = Table([blank, names_row], colWidths=widths, rowHeights=[14 * mm, None])
    signs.setStyle(TableStyle([('FONTSIZE', (0, 0), (-1, -1), 9), ('ALIGN', (0, 0), (-1, -1), 'CENTER')] +
                              [('LINEBELOW', (c, 0), (c, 0), 0.8, colors.HexColor('#334155'))
                               for c in range(0, len(widths), 2)]))
    story.append(KeepTogether([Paragraph("Officials' signatures", head), signs]))

    printed = datetime.now(timezone(timedelta(hours=5, minutes=30))).strftime('%d %b %Y, %H:%M IST')

    def footer(canvas, doc_):
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.line(14 * mm, 11 * mm, A4[0] - 14 * mm, 11 * mm)
        canvas.setFont('Helvetica', 7.5)
        canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(14 * mm, 7 * mm, f"{data['match_no']} · {home} v {away} · printed {printed}")
        canvas.drawRightString(A4[0] - 14 * mm, 7 * mm, f"Page {doc_.page}")
        canvas.restoreState()

    page.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


_college = []


def _college_logo():
    """The college's logo, its empty margin cut off: (PNG bytes, height / width), or None."""
    if not _college:
        try:
            from PIL import Image as PILImage
            from PIL import ImageChops
            with PILImage.open(COLLEGE_LOGO) as im:
                im = im.convert('RGB')
                ink = ImageChops.difference(im, PILImage.new('RGB', im.size, (255, 255, 255))).convert('L')
                im = im.crop(ink.point(lambda v: 255 if v > 24 else 0).getbbox() or (0, 0, im.width, im.height))
                im.thumbnail((900, 900))
                buf = io.BytesIO()
                im.save(buf, 'PNG')
            _college.append((buf.getvalue(), im.height / im.width))
        except Exception as exc:                           # no logo never stops the sheet
            logger.warning("Score sheet college logo not read: %s", exc)
            _college.append(None)
    return _college[0]


def _initials(name: str) -> str:
    words = [w for w in str(name or '').split() if w[:1].isalnum()]
    return ''.join(w[0] for w in words[:2]).upper() or '?'


def _tag(p: dict) -> str:
    return f"#{p['jersey']} {p['name']}" if p.get('jersey') else p['name']


def _x(text: str) -> str:
    """Text for a reportlab paragraph: &, < and > escaped."""
    return str(text or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
