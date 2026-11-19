"""
services_hackathon_marks.py — a hackathon round marked outside the portal (UPG-308).

1. The SPOC downloads "the file for the evaluators": one row per team that
   submitted in this round, its team code first and an empty Score column
   second, then the team, the members and every answer.
2. The evaluators send back the team code and the score (out of 100). Two
   columns are enough; the whole file with Score filled in works too, because
   the columns are found by their headings.
3. The SPOC uploads it (CSV or Excel). The preview shows each team's score
   and rank, the top N with ties at the cut, and anything to fix; it saves
   nothing but the parsed file, kept on the event until Submit.
4. Submit saves each score as the team's round score (`file_score` on its
   submission) and sends the top N to the next round through the shortlist
   (services_hackathon_eval.confirm): notices, "Finalists announced", undo.

A team code is the 6-character code teams join with (`team_code`). A code a
lead replaced is kept in `team_code_history`, so a file made before still
matches; a team's current code always wins over someone's old one.
"""
import csv
import datetime
import io
import re
import secrets

import services_hackathon as hk
import services_hackathon_eval as ev

MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
DEFAULT_N = 10
CODE_HEADS = ('team code', 'team id', 'teamcode', 'teamid', 'code', 'team_code', 'team_id', 'id')
SCORE_HEADS = ('score', 'marks', 'mark', 'total', 'total score', 'total marks', 'final score', 'score (out of 100)')
UPLOAD = 'marks_upload'       # in the event's hackathon block, until Submit


class MarksError(ValueError):
    pass


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ── Reading the file ────────────────────────────────────────────────────────

def norm_code(value) -> str:
    """A team code as typed in any case, with spaces; Excel may give 123456 as a number."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return re.sub(r'\s+', '', str(value if value is not None else '')).upper()


def parse_score(value):
    """(score, None) or (None, what's wrong). A number from 0 to 100, up to 2 decimals."""
    if isinstance(value, bool):
        return None, "isn't a number"
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        text = str(value if value is not None else '').strip()
        if not text:
            return None, "is empty"
        if ',' in text and '.' not in text and text.count(',') == 1:
            text = text.replace(',', '.')        # 78,5
        try:
            number = float(text)
        except ValueError:
            return None, "isn't a number"
    if number != number or not 0 <= number <= 100:      # NaN, or out of range
        return None, "isn't from 0 to 100"
    number = round(number, 2)
    return (int(number) if number == int(number) else number), None


def _table(data: bytes, filename: str) -> list:
    """The file's rows as lists of cells."""
    name = str(filename or '').lower()
    if name.endswith('.xls'):
        raise MarksError("That's an old Excel file (.xls). Save it as .xlsx or .csv and upload it again.")
    if name.endswith('.xlsx') or data[:2] == b'PK':
        try:
            import openpyxl
            book = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            sheet = book.worksheets[0]
            rows = []
            for row in sheet.iter_rows(values_only=True):
                rows.append(list(row))
                if len(rows) > MAX_ROWS + 1:
                    break
            book.close()
            return rows
        except MarksError:
            raise
        except Exception:
            raise MarksError("That Excel file can't be read. Save it again as .xlsx or .csv.")
    for encoding in ('utf-8-sig', 'cp1252'):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise MarksError("That file can't be read. Upload a CSV or an Excel (.xlsx) file.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=',;\t')
    except csv.Error:
        dialect = csv.excel
    return [row for row in csv.reader(io.StringIO(text), dialect)][:MAX_ROWS + 1]


def _head(cell) -> str:
    return ' '.join(str(cell if cell is not None else '').strip().lower().replace('_', ' ').split())


def read(data: bytes, filename: str = '') -> list:
    """[{'line', 'code', 'score', 'error'}] from an uploaded file: columns by
    their headings, or the first two columns."""
    if not data:
        raise MarksError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise MarksError(f"The file is over {MAX_BYTES // (1024 * 1024)} MB. Send only the team code and score columns.")
    rows = [r for r in _table(data, filename) if any(str(c if c is not None else '').strip() for c in r)]
    if not rows:
        raise MarksError("The file has no rows.")
    if len(rows) > MAX_ROWS:
        raise MarksError(f"The file has more than {MAX_ROWS} rows.")
    heads = [_head(c) for c in rows[0]]
    code_at = next((i for i, h in enumerate(heads) if h in {_head(x) for x in CODE_HEADS}), None)
    score_at = next((i for i, h in enumerate(heads) if h in {_head(x) for x in SCORE_HEADS}), None)
    first = 1
    if code_at is None or score_at is None:
        code_at, score_at = 0, 1
        # A first row whose second cell is a score is data, not headings
        first = 0 if len(rows[0]) > 1 and parse_score(rows[0][1])[0] is not None else 1
    out = []
    for n, row in enumerate(rows[first:], start=first + 1):
        code = norm_code(row[code_at] if code_at < len(row) else '')
        raw = row[score_at] if score_at < len(row) else ''
        score, error = parse_score(raw)
        if not code and error == 'is empty':
            continue
        out.append({'line': n, 'code': code, 'score': score, 'raw': str(raw if raw is not None else '')[:20],
                    'error': error})
    if not out:
        raise MarksError("The file has headings but no marks.")
    return out


# ── Matching ────────────────────────────────────────────────────────────────

def _teams(db, event_id: str, event: dict) -> tuple:
    """(rows of this round from the ranking, {code: row}) with old codes after current ones."""
    rows = ev.ranking(db, event_id, event)
    by_code = {}
    for r in rows:
        code = norm_code(r['reg'].get('team_code'))
        if code:
            by_code[code] = r
    for r in rows:
        for old in r['reg'].get('team_code_history') or []:
            by_code.setdefault(norm_code(old), r)
    return rows, by_code


def check(db, event_id: str, event: dict, lines: list, n=DEFAULT_N) -> dict:
    """The preview: each matched team with its score and rank, the top N, and
    what to fix. Nothing is written.
    {'ok', 'fix', 'missing', 'matched', 'go', 'out', 'tie', 'mark', 'n', 'teams'}."""
    rows, by_code = _teams(db, event_id, event)
    fix, matched, seen = [], {}, {}
    for line in lines:
        where = f"Line {line['line']}"
        if not line['code']:
            fix.append(f"{where}: no team code.")
            continue
        if line['error']:
            fix.append(f"{where} ({line['code']}): the score “{line['raw']}” {line['error']}.")
            continue
        row = by_code.get(line['code'])
        if row is None:
            fix.append(f"{where}: no team in this round has the code {line['code']}.")
            continue
        if row['reg_id'] in seen:
            fix.append(f"{where}: {row['team']} ({line['code']}) is in the file twice "
                       f"(also line {seen[row['reg_id']]}).")
            continue
        seen[row['reg_id']] = line['line']
        if not row['submitted']:
            fix.append(f"{where}: {row['team']} ({line['code']}) didn't submit, so it can't have marks.")
            continue
        matched[row['reg_id']] = line['score']
    missing = [r for r in rows if r['submitted'] and r['reg_id'] not in matched]
    shaped = [{'reg_id': r['reg_id'], 'team': r['team'], 'code': norm_code(r['reg'].get('team_code')),
               'submitted': r['submitted'], 'key': matched.get(r['reg_id']), 'tied': False} for r in rows]
    keyed = sorted((r for r in shaped if r['key'] is not None), key=lambda r: (-r['key'], r['team'].lower()))
    for i, r in enumerate(keyed):
        r['rank'] = keyed[i - 1]['rank'] if i and keyed[i - 1]['key'] == r['key'] else i + 1
        r['tied'] = sum(1 for o in keyed if o['key'] == r['key']) > 1
    picked = ev.preview(shaped, 'top_n', n) if keyed else {'ok': False, 'go': [], 'out': shaped, 'tie': [],
                                                          'mark': None, 'n': 0}
    if not keyed and not fix:
        fix.append("No team in the file matches a team that submitted.")
    try:
        n = int(n)
    except (TypeError, ValueError):
        n = 0
    if n <= 0:
        fix.append("Enter how many teams go to the next round.")
    go = sorted(picked.get('go') or [], key=lambda r: (-r['key'], r['team'].lower()))
    return {'ok': not fix and bool(go), 'fix': fix, 'missing': missing, 'matched': keyed, 'go': go,
            'out': [r for r in shaped if r['reg_id'] not in {g['reg_id'] for g in go}],
            'tie': picked.get('tie') or [], 'mark': picked.get('mark'), 'n': n, 'teams': len(rows)}


# ── The upload kept until Submit ────────────────────────────────────────────

def _refusal(event: dict) -> str:
    if event.get('results_published'):
        return "Results are published."
    if ev.shortlist(event):
        return "The next round has already started. Undo the shortlist first to upload new marks."
    if hk.has_form(event) and hk.window(event) != 'closed':
        return "Submissions are still open. Upload the marks after the deadline."
    return ''


def upload_wait(event: dict) -> str:
    """Why step 3 (the upload) can't be used yet, for the page (UPG-324); ''
    when it can. The page shows the step either way, so the SPOC knows where."""
    if hk.has_form(event) and hk.window(event) != 'closed':
        return "Teams can still submit until then."
    return _refusal(event)


def keep(db, event_id: str, event: dict, lines: list, filename: str, by: str) -> dict:
    """Keep the parsed file on the event (not the file itself) for the preview and Submit."""
    why = _refusal(event)
    if why:
        raise MarksError(why)
    upload = {'id': secrets.token_hex(8), 'lines': lines, 'file': str(filename or '')[:120], 'at': _now(), 'by': by}
    h = hk.data(event)
    h[UPLOAD] = upload
    hk._save(db, event_id, h)
    event['hackathon'] = h
    return upload


def kept(event: dict) -> dict:
    upload = hk.data(event).get(UPLOAD)
    return dict(upload) if isinstance(upload, dict) and upload.get('lines') else {}


def submit(db, event_id: str, event: dict, upload_id: str, n, expected_round, by: str) -> tuple:
    """(ok, message): save the scores and send the top N to the next round."""
    why = _refusal(event)
    if why:
        return False, why
    upload = kept(event)
    if not upload or upload.get('id') != str(upload_id or ''):
        return False, "That upload was replaced. Check the latest preview and submit again."
    result = check(db, event_id, event, upload['lines'], n)
    if not result['ok']:
        return False, "Fix the file first: " + ' '.join(result['fix'][:5])
    if ev.mode(event) != ev.FILE:
        ok, message = ev.set_mode(db, event_id, event, ev.FILE, by=by)
        if not ok:
            return False, message
    scores = {r['reg_id']: r['key'] for r in result['matched']}
    stamp = {'at': _now(), 'by': by, 'file': upload.get('file', '')}
    for r in ev.ranking(db, event_id, event):
        if not r['sub_id']:
            continue
        if r['reg_id'] in scores:
            value = {'score': scores[r['reg_id']], **stamp}
        elif (r['sub'] or {}).get('file_score'):
            value = None                  # not in this file: an earlier upload's mark goes
        else:
            continue
        db.collection('project_submissions').document(r['sub_id']).set({'file_score': value}, merge=True)
    ok, message = ev.confirm(db, event_id, event, [r['reg_id'] for r in result['go']], expected_round, by)
    if not ok:
        return False, message
    h = hk.data(event)
    h[UPLOAD] = {}
    h['marks_submitted'] = {**stamp, 'teams': len(scores), 'n': result['n'], 'through': len(result['go'])}
    h['finale_open'] = True           # every judge sees every finalist (UPG-309)
    hk._save(db, event_id, h)
    event['hackathon'] = h
    return True, f"Marks saved for {len(scores)} team(s). " + message


# ── The file for the evaluators ─────────────────────────────────────────────

# Always in the file, whatever columns the SPOC picks (UPG-325): the marks
# come back on them.
EVALUATOR_KEEP = ('Team code', 'Score (out of 100)')

def evaluator_table(db, event_id: str, event: dict) -> tuple:
    """(columns, rows): one row per team that submitted in this round, team
    code first and an empty Score second."""
    from utils_email import _base_url
    base = _base_url().rstrip('/')
    fields = [f for f in (hk.form(event).get('fields') or []) if isinstance(f, dict)]
    titles = {p['id']: p['title'] for p in hk.problems(event)}
    columns = ['Team code', 'Score (out of 100)', 'Team', 'Lead', 'Lead email', 'Members', 'Problem', 'Last saved']
    used = set(columns)
    for f in fields:
        label = str(f.get('label') or f.get('id') or 'Answer')
        while label in used:
            label += ' '
        used.add(label)
        columns.append(label)
    out = []
    for r in ev.ranking(db, event_id, event):
        sub = r['sub']
        if not sub:
            continue
        reg = r['reg']
        answers = sub.get('answers') or {}
        cells = []
        for f in fields:
            a = answers.get(f.get('id'))
            if f.get('kind') == 'pdf' and isinstance(a, dict):
                a = f"{base}/hackathon/{event_id}/file/{r['reg_id']}/{f.get('id')}"
            elif f.get('kind') == 'problem':
                a = titles.get(a, a)
            cells.append('' if a in (None, '') else str(a) if not isinstance(a, (dict, list)) else str(a))
        members = '; '.join(str(m.get('name') or m.get('email') or '') for m in reg.get('members') or []
                            if isinstance(m, dict))
        out.append([reg.get('team_code') or '', '', r['team'], reg.get('lead_name') or '', reg.get('lead_email') or '',
                    members, titles.get(sub.get('problem_id'), '') if sub.get('problem_id') else '',
                    hk.show(sub.get('updated_at'), event) if sub.get('updated_at') else ''] + cells)
    out.sort(key=lambda row: (str(row[2]).lower(), row[0]))
    return columns, out
