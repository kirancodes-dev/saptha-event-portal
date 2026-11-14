"""
services_spoc_panel.py — what the SPOC's event panel on /spoc/dashboard puts
first (UPG-253).

The panel kept every tool, about 30 of them in five tabs, for every kind of
event; Registrations, the page used most, sat in "Judges & Certs". Now:

- a top row with the numbers that matter (registered of the limit, waiting,
  members not confirmed, checked in) and the three main buttons;
- a "What to do now" card for the event's stage (`stage`, `next_steps`);
- the other tools in labelled groups, with the hackathon, round, sports and
  placement tools only on those kinds of event (`kinds`);
- a one-line meaning under each "Advance to …" button (`MEANING`).
"""
import datetime

# What moving the event to each state does, under its button
MEANING = {
    'draft': "Back to editing; participants can't see it.",
    'pending_approval': "Sends it for approval; not public yet.",
    'published': "The event page goes up; registration stays shut.",
    'registration_open': "People can register.",
    'registration_closed': "No new registrations; registered teams stay.",
    'in_progress': "The event is on: check-in and judging.",
    'evaluation': "Judges finish scoring; results aren't out yet.",
    'completed': "The event is over: results and certificates.",
    'certified': "Certificates are done.",
    'archived': "Kept for records, off the lists.",
    'cancelled': "Calls the event off.",
    'active': "Live: open for registration.",
    'inactive': "Hidden from participants.",
}

STAGE_TITLE = {
    'draft': "Get it ready and publish",
    'open': "Registration is open",
    'closed': "Registration has closed",
    'day': "It's the event day",
    'after': "The event is over",
    'cancelled': "This event is cancelled",
}

_DRAFT = ('draft', 'pending', 'pending_approval', 'changes_requested', 'published', 'inactive')


def _today() -> datetime.date:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).date()


def _date(value):
    try:
        return datetime.date.fromisoformat(str(value or '')[:10])
    except ValueError:
        return None


def stage(event: dict) -> str:
    """'draft', 'open', 'closed', 'day', 'after' or 'cancelled'."""
    from routes_forms import registration_closed
    from services_certificates import event_ended
    status = str(event.get('status') or '').strip().lower()
    if status in ('cancelled', 'rejected'):
        return 'cancelled'
    if status in _DRAFT:
        return 'draft'
    if status in ('evaluation', 'certified') or event_ended(event):
        return 'after'
    first = _date(event.get('date'))
    last = max([d for d in (first, _date(event.get('end_date')), _date(event.get('end_datetime'))) if d],
               default=None)
    if status == 'in_progress' or (first and last and first <= _today() <= last):
        return 'day'
    if status == 'registration_closed' or registration_closed(event):
        return 'closed'
    return 'open'


def kinds(event: dict) -> dict:
    """Which kind-specific tools the panel shows. An event of no known type
    (made before types, or "custom") shows them all, as before."""
    from services_event_types import TYPES, get_type
    spec = get_type(str(event.get('event_type') or ''))
    unknown = spec is TYPES['custom']
    return {
        'hackathon': unknown or spec is TYPES['hackathon'],
        'rounds': unknown or bool(spec.get('competitive')) or spec.get('group') in ('competition', 'cultural'),
        'sports': spec.get('group') == 'sports' or event.get('category') == 'Sports' or bool(event.get('tournament')),
        'placement': bool(spec.get('placement')) or bool(event.get('is_placement')),
    }


def numbers(db, event_id: str, event: dict, regs: list) -> dict:
    """{'waiting': people on the waitlist, 'unconfirmed': team members who
    haven't confirmed, 'checked_in': registrations checked in}."""
    import services_team_confirm as confirm
    from services_waitlist import waiting
    unconfirmed = 0
    if confirm.enabled(event):
        unconfirmed = sum(1 for r in regs if confirm.active(r)
                          for _, st in confirm.summary(r) if st['key'] != 'confirmed')
    try:
        on_waitlist = len(waiting(db, event_id))
    except Exception:
        on_waitlist = 0
    return {'waiting': on_waitlist, 'unconfirmed': unconfirmed,
            'checked_in': sum(1 for r in regs if str(r.get('attendance') or '').strip().lower() == 'present')}


def next_steps(event_id: str, event: dict, current: str) -> list:
    """[(label, href, why)] for the "What to do now" card."""
    from routes_forms import team_limits
    regs = f"/coordinator/registrations/{event_id}"
    team = team_limits(event)[1] > 1
    status = str(event.get('status') or '').strip().lower()
    if current == 'draft':
        return [('Open registration' if status == 'published' else 'Review and publish',
                 f"/spoc/event/{event_id}/review", "Check every detail, then make it live."),
                ('Edit the details', f"/spoc/event/{event_id}/setup", "Date, venue, limits, fees."),
                ('Build the registration form', f"/forms/builder/{event_id}", "The questions people answer.")]
    if current == 'open':
        return [('Registrations', regs, "Who has registered, and their teams."),
                ('Waitlist', f"{regs}#waitlist", "People waiting for a seat."),
                ('Share the link', f"/spoc/event/{event_id}/share", "Links and QR codes to post.")]
    if current == 'closed':
        steps = []
        if team:
            steps.append(('Let teams add members', f"{regs}#add-members-window",
                          "Open a time window for registered teams."))
            steps.append(('Documents for teams', f"{regs}#documents", "An undertaking form, instructions."))
        steps.append(('Entry list', f"{regs}#entry-list", "Choose who may attend, if seats are short."))
        steps.append(('Registrations', regs, "Check details before the day."))
        return steps
    if current == 'day':
        return [('Scan tickets', f"/spoc/scan/{event_id}", "Check people in at the door."),
                ("Who's checked in", regs, "Attendance, team by team.")]
    if current == 'after':
        return [('Results', f"/spoc/results/{event_id}", "Scores and winners."),
                ('Certificates', f"/certificates/events/{event_id}", "Design and send them."),
                ('Event report', f"/spoc/event_report/{event_id}", "The Excel report."),
                ('Feedback', f"/feedback/analytics/{event_id}", "What people said.")]
    return []


def panel(db, event_id: str, event: dict, regs: list) -> dict:
    """Everything the template needs for one event."""
    current = stage(event)
    return {'stage': current, 'stage_title': STAGE_TITLE[current], 'steps': next_steps(event_id, event, current),
            'kinds': kinds(event), **numbers(db, event_id, event, regs)}
