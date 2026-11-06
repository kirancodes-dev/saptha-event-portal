"""
tests/test_every_template_rendered.py — UPG-64: every file under templates/ is
rendered by the code (named in a .py file) or extended, included or imported by
a template that is, so no stale page can be rendered by accident.
"""
import glob
import os
import re

ROOT = 'templates'


def test_every_template_is_rendered_or_included():
    templates = {os.path.relpath(p, ROOT) for p in glob.glob(f'{ROOT}/**/*.html', recursive=True)}
    code = ''.join(open(f, encoding='utf-8').read() for f in glob.glob('*.py') + glob.glob('tasks/*.py'))
    used = [t for t in templates if re.search(r"['\"]" + re.escape(t) + r"['\"]", code)]
    refs = {}
    for t in templates:
        with open(os.path.join(ROOT, t), encoding='utf-8') as fh:
            refs[t] = re.findall(r"{%-?\s*(?:extends|include|import|from)\s+['\"]([^'\"]+)['\"]", fh.read())
    seen, todo = set(), list(used)
    while todo:
        t = todo.pop()
        if t not in seen:
            seen.add(t)
            todo.extend(refs.get(t, ()))
    assert sorted(templates - seen) == []
