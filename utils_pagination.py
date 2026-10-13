"""
utils_pagination.py — one pagination and search helper for every staff list (UPG-19)

Lists read `?page=`, `?per_page=` (25 by default, at most 100) and `?q=` from
the URL, so a filtered page can be bookmarked or shared. Templates render
`partials/pagination.html` with the `Page` this returns.

    page = paginate_items(rows, search_fields=('name', 'email', 'usn'))
    page = paginate_query(db.collection('users').order_by('email'))   # SQL LIMIT/OFFSET
"""
import math
from dataclasses import dataclass, field
from typing import Any, Iterable, List, Sequence

from flask import request

PER_PAGE = 25
MAX_PER_PAGE = 100


def _int_arg(name, default):
    try:
        return int(request.args.get(name, default))
    except (TypeError, ValueError):
        return default


def page_args():
    """(page, per_page, q) from the request; page ≥ 1, 1 ≤ per_page ≤ 100."""
    page = max(_int_arg('page', 1), 1)
    per_page = min(max(_int_arg('per_page', PER_PAGE), 1), MAX_PER_PAGE)
    q = (request.args.get('q') or '').strip()
    return page, per_page, q


@dataclass
class Page:
    items: List[Any]
    page: int
    per_page: int
    total: int
    q: str = ''
    args: dict = field(default_factory=dict)   # the request's other query args, kept in links

    @property
    def pages(self) -> int:
        return max(math.ceil(self.total / self.per_page), 1) if self.per_page else 1

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def first_index(self) -> int:
        return 0 if not self.total else (self.page - 1) * self.per_page + 1

    @property
    def last_index(self) -> int:
        return min(self.page * self.per_page, self.total)

    def url(self, page: int) -> str:
        """This list's URL at another page, keeping the search and filters."""
        from urllib.parse import urlencode
        args = dict(self.args)
        args['page'] = page
        if self.per_page != PER_PAGE:
            args['per_page'] = self.per_page
        if self.q:
            args['q'] = self.q
        return request.path + '?' + urlencode(args)


def _other_args():
    return {k: v for k, v in request.args.items() if k not in ('page', 'per_page', 'q')}


def matches(item, q: str, fields: Sequence[str]) -> bool:
    """Case-insensitive substring match of q on any of the item's fields."""
    if not q:
        return True
    needle = q.lower()
    get = item.get if isinstance(item, dict) else (lambda f: getattr(item, f, ''))
    return any(needle in str(get(f) or '').lower() for f in fields)


def paginate_items(items: Iterable[Any], search_fields: Sequence[str] = ()) -> Page:
    """Search and page a list already loaded in memory."""
    page, per_page, q = page_args()
    rows = [i for i in items if matches(i, q, search_fields)] if q and search_fields else list(items)
    total = len(rows)
    last_page = max(math.ceil(total / per_page), 1)
    page = min(page, last_page)
    start = (page - 1) * per_page
    return Page(rows[start:start + per_page], page, per_page, total, q, _other_args())


def paginate_query(query, transform=lambda doc: doc) -> Page:
    """Page a database query with LIMIT/OFFSET (the SQL adapter pushes both
    into SQL). Use when there is no search; with one, load and use
    paginate_items, because the adapter has no substring filter."""
    page, per_page, q = page_args()
    total = query.count()
    last_page = max(math.ceil(total / per_page), 1)
    page = min(page, last_page)
    docs = query.offset((page - 1) * per_page).limit(per_page).stream()
    return Page([transform(d) for d in docs], page, per_page, total, q, _other_args())


ENDED_STATUSES = ('completed', 'certified', 'archived')


def filter_events(events, q: str = '', status: str = ''):
    """Dashboard event lists: search title, venue and category; `status` is
    'active' (not ended or cancelled), 'completed' (ended), or an exact status."""
    def keep(e):
        st = str((e.get('status') if isinstance(e, dict) else getattr(e, 'status', '')) or '').lower()
        if status == 'active' and (st in ENDED_STATUSES or st == 'cancelled'):
            return False
        if status == 'completed' and st not in ENDED_STATUSES:
            return False
        if status not in ('', 'active', 'completed') and st != status:
            return False
        return matches(e, q, ('title', 'venue', 'category'))
    return [e for e in events if keep(e)]


def paginate_events(events) -> Page:
    """Search (?q=), status filter (?status=) and page a dashboard's events."""
    status = (request.args.get('status') or '').strip().lower()
    q = page_args()[2]
    return paginate_items(filter_events(events, q, status))
