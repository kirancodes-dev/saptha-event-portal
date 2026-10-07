"""
tests/html_sinks.py — find every place our JavaScript puts a value into HTML
(BLK-19). Used by tests/test_no_html_injection.py.

Two kinds of place are checked, in every tracked template's inline scripts
and every file in static/js:

  * a string that builds HTML — its fixed text contains a tag (`<div`,
    `</td`, …) — and the values put into it: `${value}` in a template
    literal, or `'<td>' + value + '</td>'`;
  * a direct write: `el.innerHTML = value`, `+=`, `outerHTML`,
    `insertAdjacentHTML(where, value)` and `document.write(value)`.

Each value must be one of:

  * escapeHtml(value)       text in an element or a quoted attribute;
  * escapeJsAttr(value)     a value inside an on…="…" handler attribute (the
                            browser decodes entities before running it);
  * safeUrl(value)          a value starting an href="…" or src="…";
  * a string literal, a number, or a ternary whose branches are literals;
  * list.map(x => `…`).join('') whose template is itself checked;
  * a name ending in Html/HTML (any case): HTML assembled from checked strings;
  * an entry in ALLOWED (file, expression), with the reason it's safe.

static/js/escape.js defines the three helpers. The JavaScript is read with a
small lexer (strings, template literals, comments, regex literals), which
is enough for the code in this repo.
"""
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HTML_TAG = re.compile(r'<\s*/?\s*[A-Za-z!]')
HANDLER_ATTR = re.compile(r'\bon[a-z]+\s*=\s*(?:"[^"]*|\'[^\']*)$', re.I)
URL_ATTR = re.compile(r'\b(href|src|action|formaction)\s*=\s*["\']?\s*$', re.I)
SINK = re.compile(r'\.(innerHTML|outerHTML)\s*\+?=(?!=)|\.insertAdjacentHTML\s*\(|\bdocument\.write(ln)?\s*\(')
HELPERS = ('escapeHtml', 'escapeJsAttr', 'safeUrl')
REGEX_KEYWORDS = ('return', 'typeof', 'case', 'do', 'else', 'in', 'of', 'new', 'delete', 'void', 'throw')

# Values that are safe without a helper, reviewed one by one:
# (file, expression) -> why.
ALLOWED = {
    ('static/js/i18n.js', 'dict[hk]'):
        'translations are a constant in i18n.py, served by /api/translations; only data-i18n-html elements use them',
}

# Templates nothing renders; UPG-15 deletes them.
NOT_RENDERED = {
    'templates/debug_modal.html': 'no route renders it (its /debug-modal route was removed in BLK-09)',
    'templates/public/home.html': 'only routes_public.py renders it, and that blueprint is not registered',
}


# ── Reading the JavaScript ─────────────────────────────────────────────────

def tracked_sources():
    """(path, line offset, JavaScript) for every first-party script."""
    out = subprocess.run(['git', '-C', ROOT, 'ls-files', 'templates', 'static/js'],
                         capture_output=True, text=True, check=True).stdout.split()
    for path in out:
        if not path.endswith(('.html', '.js')) or path in NOT_RENDERED:
            continue
        with open(os.path.join(ROOT, path), encoding='utf-8') as fh:
            text = fh.read()
        if path.endswith('.js'):
            yield path, 0, text
            continue
        for m in re.finditer(r'<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script>', text, re.S | re.I):
            yield path, text.count('\n', 0, m.start(1)), _without_jinja(m.group(1))


def _without_jinja(js):
    # {{ value }} becomes an opaque name; {% … %} disappears; newlines are kept.
    js = re.sub(r'\{\{.*?\}\}', lambda m: '__jinja__' + '\n' * m.group(0).count('\n'), js, flags=re.S)
    return re.sub(r'\{%.*?%\}', lambda m: '\n' * m.group(0).count('\n'), js, flags=re.S)


class Template:
    """A template literal: fixed text parts and ${…} expressions, alternating."""
    def __init__(self, start):
        self.start, self.end, self.parts, self.exprs = start, start, [''], []


class Lexed:
    """The literals of a script, and a mask: the script with every string,
    template literal, comment and regex blanked, a string or template
    leaving one 'S' where it starts. Positions match the script."""
    def __init__(self, js):
        self.js = js
        self.literals = []  # ('str', text, start, end) and ('tpl', Template, start, end)
        self._chars = list(js)
        self._lex(0, len(js), top=True)
        self.mask = ''.join(self._chars)

    def _blank(self, a, b, mark=''):
        for k in range(a, b):
            if self._chars[k] != '\n':
                self._chars[k] = ' '
        if mark and b > a:
            self._chars[a] = mark

    def _lex(self, i, end, top=False):
        """Lex js[i:end]; inside ${…} (top=False) stop at the closing brace."""
        js, depth = self.js, 0
        while i < end:
            c = js[i]
            if c in '"\'':
                j = _skip_quoted(js, i, c)
                self.literals.append(('str', js[i + 1:j - 1], i, j))
                self._blank(i, j, 'S')
                i = j
            elif c == '`':
                i = self._template(i)
            elif js.startswith('//', i):
                j = js.find('\n', i)
                j = end if j == -1 else j
                self._blank(i, j)
                i = j
            elif js.startswith('/*', i):
                j = js.find('*/', i + 2)
                j = end if j == -1 else j + 2
                self._blank(i, j)
                i = j
            elif c == '/' and self._regex_allowed(i):
                j = _skip_regex(js, i)
                if j:
                    self._blank(i, j, 'R')
                    i = j
                else:
                    i += 1
            else:
                if not top:
                    if c == '{':
                        depth += 1
                    elif c == '}':
                        if depth == 0:
                            return i
                        depth -= 1
                i += 1
        return i

    def _template(self, i):
        js = self.js
        tpl = Template(i)
        self.literals.append(('tpl', tpl, i, None))
        index = len(self.literals) - 1
        j = i + 1
        while j < len(js):
            c = js[j]
            if c == '\\':
                tpl.parts[-1] += js[j:j + 2]
                j += 2
            elif c == '`':
                j += 1
                break
            elif js.startswith('${', j):
                k = self._lex(j + 2, len(js))
                tpl.exprs.append(js[j + 2:k])
                tpl.parts.append('')
                j = k + 1
            else:
                tpl.parts[-1] += c
                j += 1
        tpl.end = j
        self.literals[index] = ('tpl', tpl, i, j)
        self._blank(i, j, 'S')
        return j

    def _regex_allowed(self, i):
        js = self.js
        if js.startswith('//', i) or js.startswith('/*', i):
            return False
        k = i - 1
        while k >= 0 and self._chars[k] in ' \t\r\n':
            k -= 1
        if k < 0:
            return True
        prev = self._chars[k]
        if prev.isalnum() or prev in '_$':
            word = re.search(r'([A-Za-z_$][\w$]*)$', ''.join(self._chars[max(0, k - 12):k + 1]))
            return bool(word) and word.group(1) in REGEX_KEYWORDS
        return prev in '(,=:[!&|?{};+-*%<>~^'


def _skip_quoted(js, i, quote):
    j = i + 1
    while j < len(js):
        if js[j] == '\\':
            j += 2
            continue
        if js[j] == quote or js[j] == '\n':
            return j + 1
        j += 1
    return j


def _skip_regex(js, i):
    j, in_class = i + 1, False
    while j < len(js) and js[j] != '\n':
        c = js[j]
        if c == '\\':
            j += 2
            continue
        if c == '[':
            in_class = True
        elif c == ']':
            in_class = False
        elif c == '/' and not in_class:
            j += 1
            while j < len(js) and js[j].isalpha():
                j += 1
            return j
        j += 1
    return None


# ── Judging a value ────────────────────────────────────────────────────────

def _call_of(expr, names):
    """expr is a single call to one of names: f(...) and nothing after it."""
    m = re.match(r'(%s)\s*\(' % '|'.join(names), expr)
    if not m:
        return False
    depth = 0
    masked = _masked(expr)
    for k, c in enumerate(masked):
        if c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
            if depth == 0:
                return masked[k + 1:].strip() == ''
    return False


def _masked(expr):
    """expr with string and template literals replaced by S."""
    return Lexed(expr).mask.replace('\n', ' ')


def _unwrap(expr):
    """Drop parentheses around the whole expression."""
    while expr.startswith('(') and expr.endswith(')'):
        masked, depth = _masked(expr), 0
        for k, c in enumerate(masked):
            depth += {'(': 1, ')': -1}.get(c, 0)
            if depth == 0 and k < len(masked) - 1:
                return expr
        expr = expr[1:-1].strip()
    return expr


def safe(expr, path, context=''):
    expr = _unwrap(expr.strip())
    if not expr or (path, expr) in ALLOWED:
        return True
    if HANDLER_ATTR.search(context):
        return _call_of(expr, ['escapeJsAttr'])
    if URL_ATTR.search(context):
        return _call_of(expr, ['safeUrl'])
    if _call_of(expr, HELPERS):
        return True
    if re.fullmatch(r'-?\d+(\.\d+)?', expr) or re.fullmatch(r'([A-Za-z_$][\w$.]*)?html', expr, re.I):
        return True
    masked = ' '.join(_masked(expr).split())
    if re.fullmatch(r'[S ()]+', masked) or _literal_ternary(masked):
        return True
    if re.fullmatch(r'[\w$.\[\]() ]*\.map\(\s*(\(?[\w$, ]*\)?\s*=>\s*S|function\s*\([\w$, ]*\)\s*\{\s*return\s+S\s*;?\s*\})\s*\)'
                    r'\.join\(\s*S?\s*\)', masked):
        return True
    return _map_returns_safe(expr, path)


def _map_returns_safe(expr, path):
    """list.map(function (x) { …; return …; }).join(''): every return gives a
    safe value, or a + chain with an HTML string (whose operands the chain
    check judges)."""
    mk = _masked(expr)
    m = re.fullmatch(r'\s*[\w$.\[\]() ]*\.map\(\s*(?:function\s*\([^)]*\)|\(?[\w$, ]*\)?\s*=>)\s*\{(?P<body>.*)\}\s*\)'
                     r'\.join\(\s*S?\s*\)\s*', mk, re.S)
    if not m:
        return False
    literals = Lexed(expr).literals
    returns = list(re.finditer(r'\breturn\b', mk[m.start('body'):m.end('body')]))
    if not returns:
        return False
    for r in returns:
        a = m.start('body') + r.end()
        b = a
        depth = 0
        while b < m.end('body') and not (depth == 0 and mk[b] == ';'):
            depth += {'(': 1, '[': 1, '{': 1, ')': -1, ']': -1, '}': -1}.get(mk[b], 0)
            if depth < 0:
                break
            b += 1
        value = expr[a:b].strip()
        chain = '+' in mk[a:b] and any(kind == 'str' and a <= start < b and HTML_TAG.search(text)
                                       for kind, text, start, end in literals)
        if not (chain or safe(value, path)):
            return False
    return True


def _literal_ternary(masked):
    """a ? S : b ? S : S — every result of a (nested) ternary is a literal."""
    depth, q = 0, None
    for k, c in enumerate(masked):
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == '?' and depth == 0:
            q = k
            break
    if q is None:
        return False
    depth, nested = 0, 0
    for k in range(q + 1, len(masked)):
        c = masked[k]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif depth == 0 and c == '?':
            nested += 1
        elif depth == 0 and c == ':':
            if nested:
                nested -= 1
                continue
            then, other = masked[q + 1:k].strip(), masked[k + 1:].strip()
            return all(re.fullmatch(r'[S ()]+', part) or _literal_ternary(part) for part in (then, other))
    return False


# ── Finding the places ─────────────────────────────────────────────────────

def findings():
    """Every value put into HTML without an accepted treatment:
    (path, line, expression, the HTML just before it)."""
    bad = []
    for path, offset, js in tracked_sources():
        bad += [(path, offset + js.count('\n', 0, pos) + 1, expr, ctx) for pos, expr, ctx in script_findings(js, path)]
    return bad


def script_findings(js, path='<script>'):
    """(position, expression, context) for one script."""
    lexed = Lexed(js)
    bad, seen = [], set()
    for kind, value, start, end in lexed.literals:
        if kind == 'tpl' and any(HTML_TAG.search(p) for p in value.parts):
            for k, expr in enumerate(value.exprs):
                if not safe(expr, path, value.parts[k]):
                    bad.append((start, expr.strip(), value.parts[k][-40:]))
        html = value if kind == 'str' else ''.join(value.parts)
        if HTML_TAG.search(html) and end is not None:
            region = _region(lexed.mask, start, end)
            if region not in seen:
                seen.add(region)
                bad += [(start, expr, ctx) for expr, ctx in _concat(lexed, *region, path)]
    for m in SINK.finditer(lexed.mask):
        a = m.end()
        if m.group(0).startswith('.insertAdjacentHTML'):
            comma = _top_level(lexed.mask, a, ',')
            if comma is None:
                continue
            a = comma + 1
        region = _region(lexed.mask, a, a, left=False, ternary=True)
        if region not in seen and not safe(lexed.js[region[0]:region[1]], path):
            seen.add(region)
            bad += [(m.start(), expr, ctx) for expr, ctx in _concat(lexed, *region, path, sink=True)]
    return bad


def _top_level(mask, i, char):
    depth = 0
    while i < len(mask):
        c = mask[i]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            if depth == 0:
                return None
            depth -= 1
        elif c == char and depth == 0:
            return i
        i += 1
    return None


def _region(mask, start, end, left=True, ternary=False):
    """The expression around mask[start:end], out to the operators that end
    it; with ternary=True, a ? b : c stays one expression."""
    a = start
    if left:
        depth, k = 0, start - 1
        while k >= 0:
            c = mask[k]
            if c in ')]' or (c == '}' and depth):
                depth += 1
            elif c in '([{}':
                if depth == 0:
                    break
                depth -= 1
            elif depth == 0:
                if c in ';,?:' or (c == '=' and mask[k + 1:k + 2] not in ('=', '>')
                                   and mask[k - 1:k] not in ('=', '!', '<', '>')):
                    break
                if c == '\n' and not _continues(mask, k):
                    break
                if mask[k:k + 6] == 'return' and (k == 0 or not (mask[k - 1].isalnum() or mask[k - 1] in '_$')):
                    k += 5
                    break
            k -= 1
        a = k + 1
    depth, k = 0, end
    while k < len(mask):
        c = mask[k]
        if c in '([' or (c == '{' and depth):
            depth += 1
        elif c in ')]}' or c == '{':
            if depth == 0:
                break
            depth -= 1
        elif depth == 0:
            if c in ';,' or (c in '?:' and not ternary):
                break
            if c == '\n' and not _continues(mask, k):
                break
            if c in '|&' and mask[k + 1:k + 2] == c and not ternary:
                break
        k += 1
    return a, k


def _continues(mask, newline):
    """A newline inside an expression: the line before ends with an operator or the next starts with one."""
    before = mask[:newline].rstrip()
    after = mask[newline:].lstrip()
    return (before.endswith(('+', '(', '[', '=', ',', '?', ':', '&&', '||'))
            or after.startswith(('+', '.', '?', ':', ')', ']')))


def _concat(lexed, a, b, path, sink=False):
    """The operands of a + chain in [a, b) that aren't literals, judged."""
    mask, js = lexed.mask, lexed.js
    bad, depth, start, operands = [], 0, a, []
    k = a
    while k < b:
        c = mask[k]
        if c in '([{':
            depth += 1
        elif c in ')]}':
            depth -= 1
        elif c == '+' and depth == 0 and mask[k + 1:k + 2] not in ('+', '=') and mask[k - 1:k] != '+':
            operands.append((start, k))
            start = k + 1
        k += 1
    operands.append((start, b))
    if len(operands) == 1 and not sink:
        return []
    context = ''
    for s, e in operands:
        text = js[s:e].strip()
        masked = mask[s:e].strip()
        if re.fullmatch(r'[S ()]*', masked):
            literal = [v for kind, v, ls, le in lexed.literals if s <= ls < e and kind == 'str']
            if literal:
                context = literal[-1]
            continue
        if not safe(text, path, context):
            bad.append((text, context[-40:]))
    return bad
