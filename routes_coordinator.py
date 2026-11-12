import datetime
import random
from flask import (Blueprint, Response, flash, jsonify,
                   redirect, render_template, request, session)
# google-cloud-firestore is a pinned requirement: the database adapter uses its
# sentinels (Query, ArrayUnion, DELETE_FIELD) and FieldFilter on every backend.
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
class DynamicDBProxy:
    def __getattr__(self, name):
        try:
            import app as app_module
            if hasattr(app_module, 'db') and app_module.db is not None:
                return getattr(app_module.db, name)
        except Exception:
            pass
        try:
            from models import db as models_db
            return getattr(models_db, name)
        except Exception:
            raise AttributeError(f"No DB available for attribute '{name}'")

db = DynamicDBProxy()
from utils import (login_required, role_required, log_action, safe_int, create_registration, generate_reg_id,
                   AlreadyRegistered, venue_label)
from utils_email import (send_appointment_email, send_broadcast_email,
                         send_ticket_email, send_result_email)
from services_accounts import create_unverified_account, send_set_password_link
try:
    from utils_whatsapp import (send_room_assignment_whatsapp, send_result_whatsapp,
        send_elimination_whatsapp, send_broadcast_whatsapp,
        send_staff_appointment_whatsapp, send_ticket_whatsapp)
    _WA = True
except ImportError:
    _WA = False

coord_bp    = Blueprint('coordinator', __name__, url_prefix='/coordinator')
COORD_ROLES = ['ClubSPOC', 'UnitAdmin', 'EventOrganizer', 'EventCoordinator', 'Coordinator', 'SuperAdmin', 'Super Admin', 'UniversityAdmin']

def _wa(fn, *a, **kw):
    if _WA:
        try: return fn(*a, **kw)
        except Exception: pass
    return False

def _phone(reg):
    return (reg.get('lead_phone') or reg.get('phone') or
            (reg.get('members') or [{}])[0].get('phone', ''))

def _ff(f, op, v):
    return FieldFilter(f, op, v)


def _event_or_abort(event_id, permission):
    """Load an event and require `permission` on it for the session (BLK-04).

    Call outside the routes' try/except blocks so 403/404 aren't swallowed.
    """
    from flask import abort
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = doc.to_dict() or {}
    event['id'] = event_id
    if not can(session, permission, event, db=db):
        abort(403)
    return event


# Roles an organiser may give event staff. Anything else (e.g. SuperAdmin)
# would be a privilege escalation through the staff form (BLK-04).
STAFF_ROLES = ('Judge', 'EventCoordinator', 'Coordinator', 'Volunteer')


# 1. DASHBOARD
@coord_bp.route('/dashboard')
@login_required
@role_required(COORD_ROLES)
def dashboard():
    user_role = session.get('role', '')
    user_email = session.get('user_id')
    club_category = session.get('category', 'General')
    try:
        is_super = user_role in ('SuperAdmin', 'Super Admin') or club_category == 'All'
        all_events_ref = (db.collection('events')
                            .order_by('created_at', direction=firestore.Query.DESCENDING)
                            .stream())
        events = []; total_regs = 0; total_staff = 0
        from services_permission import can
        for e in all_events_ref:
            d = e.to_dict(); d['id'] = e.id
            # Scoped check: only events the user is authorized to manage or view
            if not can(session, 'manage_registrations', d, db=db) and not can(session, 'view_analytics', d, db=db):
                continue
            if not is_super:
                # Hide completed events
                current_date = datetime.date.today().strftime("%Y-%m-%d")
                event_date = d.get('date', '9999-99-99')
                if event_date < current_date:
                    continue
            total_staff += len(d.get('staff', []))
            regs = [r.to_dict() or {} for r in (db.collection('registrations')
                      .where(filter=_ff('event_id', '==', e.id)).stream())]
            # Count the registrations themselves: the cached counter on the event
            # can be stale (seeded or never reconciled) (UPG-80)
            d['registration_count'] = len(regs)
            total_regs += len(regs)
            d['scored_teams'] = sum(
                1 for r in regs
                if not r.get('is_eliminated') and r.get('scores'))
            # The form builder needs edit_event: show its button only to those who have it (UPG-68)
            d['can_edit_form'] = can(session, 'edit_event', d, db=db)
            events.append(d)
    except Exception as exc:
        flash(f"Dashboard error: {exc}", "danger")
        events = []; total_regs = 0; total_staff = 0
    from utils_pagination import paginate_events
    return render_template('coordinator/dashboard.html',
        events=events, page=paginate_events(events),   # cards: 25 a page (UPG-19)
        status_filter=(request.args.get('status') or '').strip().lower(),
        club_category=club_category,
        total_regs=total_regs, total_staff=total_staff,
        user_name=session.get('name'))


# 2. VIEW REGISTRATIONS (all students for an event)
@coord_bp.route('/registrations/<event_id>')
@login_required
@role_required(COORD_ROLES)
def view_registrations(event_id):
    from flask import abort
    from services_permission import can
    try:
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            flash("Event not found.", "danger")
            return redirect('/coordinator/dashboard')
        event = event_doc.to_dict(); event['id'] = event_id
        if not can(session, 'manage_registrations', event, db=db):
            abort(403)
        regs_raw = (db.collection('registrations')
                      .where(filter=_ff('event_id', '==', event_id)).stream())
        registrations = sorted(
            [dict(r.to_dict(), id=r.id) for r in regs_raw],
            key=lambda x: str(x.get('registered_at', '')), reverse=True)
        # The SPOC's entry list (UPG-214): counts over every team, then the filters
        import services_entry
        entry_counts = services_entry.counts(db, event_id, event, regs=[(r['id'], r) for r in registrations])
        listed = dict(event, **{services_entry.SWITCH: True})
        entry_filter = (request.args.get('entry') or '').strip()
        pay_filter = (request.args.get('pay') or '').strip()
        shown = registrations
        if entry_filter in ('selected', 'not_selected'):
            shown = [r for r in shown if not services_entry.inactive(r)
                     and services_entry.may_enter(listed, r) == (entry_filter == 'selected')]
        if pay_filter in ('paid', 'unpaid'):
            shown = [r for r in shown if (str(r.get('payment_status') or '').strip().lower()
                                          in ('paid', 'completed')) == (pay_filter == 'paid')]
        from utils_pagination import paginate_items
        # The lead's USN is saved as lead_usn (UPG-226); members are found by name, USN or email
        for reg in shown:
            reg['member_search'] = ' '.join(
                str(m.get(k) or '') for m in reg.get('members') or [] if isinstance(m, dict)
                for k in ('name', 'usn', 'email'))
        page = paginate_items(shown, search_fields=(
            'lead_name', 'name', 'lead_email', 'student_email', 'lead_usn', 'usn', 'team_name', 'lead_phone',
            'member_search'))
        # Each lead's login email, for helping someone told to contact the organizer (UPG-152)
        from services_accounts import login_status
        # Everything the form asked, labelled, under each row (UPG-231)
        import services_export
        form_details = services_export.FormDetails(db, event_id)
        for reg in page.items:
            lead = str(reg.get('lead_email') or reg.get('student_email') or '').strip().lower()
            doc = db.collection('users').document(lead).get() if lead else None
            profile = (doc.to_dict() or {}) if doc is not None and doc.exists else None
            reg['login'] = login_status(profile)
            reg['details'] = form_details.of(reg, profile)
        # Each member's confirmation (UPG-207), and how many still wait
        import services_team_confirm as confirm
        from routes_forms import team_limits
        member_confirm = confirm.enabled(event)
        team_event = team_limits(event)[1] > 1
        waiting = {'waiting': 0, 'unsent': 0, 'held': 0}
        if member_confirm:
            for reg in page.items:
                reg['member_status'] = confirm.summary(reg)
            for reg in registrations:
                for _, st in confirm.summary(reg) if confirm.active(reg) else []:
                    if st['key'] != 'confirmed':
                        waiting['waiting'] += 1
                        waiting['unsent'] += st['key'] != 'waiting'
                        waiting['held'] += st['key'] == 'held'
        # The hosting SPOC cancels a team until it is checked in (UPG-211)
        may_edit = can(session, 'edit_event', event, db=db)
        kept = kept_records(db, event_id) if may_edit else (set(), set())
        for reg in page.items:
            reg['checked_in'] = checked_in(reg)
            reg['cancelled'] = str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded')
            reg['on_list'] = services_entry.may_enter(listed, reg)
            # ...and deletes one that left no record elsewhere (UPG-229)
            reg['delete_block'] = delete_refusal(reg['id'], reg, *kept) if may_edit else ''
        # The people waiting for a seat, in line, with what they filled in (UPG-230)
        waitlist = waitlist_rows(db, event, form_details)
        from services_waitlist import auto_moves_up as services_waitlist_auto   # UPG-243
        import services_event_documents
        return render_template('coordinator/registrations.html',
            event=event, registrations=page.items, page=page, total=len(registrations),
            member_confirm=member_confirm, waiting=waiting, team_event=team_event,
            may_switch=may_edit, may_cancel=may_edit, may_select=may_edit, may_accept=may_edit,
            entry=entry_counts, entry_filter=entry_filter, pay_filter=pay_filter,
            waitlist=waitlist, seats=seats_left(event),
            waitlist_auto=services_waitlist_auto(event),
            # Documents for registered teams (UPG-239)
            documents=services_event_documents.documents(event), may_edit_documents=may_edit,
            # The summary at the top (UPG-234)
            cancelled=sum(1 for r in registrations
                          if str(r.get('status') or '').strip().lower() in ('cancelled', 'refunded')))
    except Exception as exc:
        if getattr(exc, 'code', None) == 403:
            abort(403)
        flash(f"Error loading registrations: {exc}", "danger")
        return redirect('/coordinator/dashboard')


@coord_bp.route('/registrations/<event_id>/login_link', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def send_login_link(event_id):
    """The organizer emails a registrant's lead a new one-time set-password
    link (48 hours): the help behind "contact the hackathon organizer"
    (UPG-152). Counts against the daily email limit; participant accounts
    only."""
    from flask import abort
    from services_accounts import email_login_link, login_status
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'manage_registrations', event, db=db):
        abort(403)
    back = f'/coordinator/registrations/{event_id}'
    reg_doc = db.collection('registrations').document((request.form.get('reg_id') or '').strip()).get()
    reg = (reg_doc.to_dict() or {}) if reg_doc.exists else {}
    if str(reg.get('event_id') or '') != str(event_id):
        flash("That registration isn't for this event.", "danger")
        return redirect(back)
    lead = str(reg.get('lead_email') or reg.get('student_email') or '').strip().lower()
    user_doc = db.collection('users').document(lead).get() if lead else None
    user = (user_doc.to_dict() or {}) if user_doc is not None and user_doc.exists else None
    if not login_status(user)['can_send']:
        flash("A password link can be sent only to a participant's account.", "warning")
        return redirect(back)
    status = email_login_link(db, lead, (user or {}).get('name', ''), 'set_password',
                              reason="earlier, and the event's organizer has sent you a new link",
                              by=session.get('user_id', ''))
    if status == 'sent':
        flash(f"✅ A one-time password link (valid 48 hours) was emailed to {lead}.", "success")
    elif status == 'limit':
        flash("Today's email limit is reached, so nothing was sent. Try again tomorrow.", "danger")
    else:
        flash(f"The email to {lead} couldn't be sent. Check the mail settings and try again.", "danger")
    return redirect(back)


@coord_bp.route('/registrations/<event_id>/member_links', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def send_member_links(event_id):
    """Send confirmation links to waiting members (UPG-207): each member not
    yet sent one (teams registered before member confirmation, or held back
    by the daily email limit) gets one; a second press sends nothing more."""
    from flask import abort
    import services_team_confirm as confirm
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'manage_registrations', event, db=db):
        abort(403)
    back = f'/coordinator/registrations/{event_id}'
    if not confirm.enabled(event):
        flash("Member confirmation is off for this event.", "warning")
        return redirect(back)
    counts = confirm.send_waiting(db, event_id, event, by=session.get('user_id', ''))
    if not any(counts.values()):
        flash("Every waiting member has already been sent a link.", "info")
    else:
        flash(f"Links sent to {counts['sent']} member{'' if counts['sent'] == 1 else 's'}."
              + (f" {counts['limit']} held back by today's email limit: press again tomorrow." if counts['limit'] else '')
              + (f" {counts['failed']} couldn't be sent." if counts['failed'] else ''),
              "success" if not (counts['limit'] or counts['failed']) else "warning")
    return redirect(back)


@coord_bp.route('/registrations/<event_id>/member_confirm', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def switch_member_confirm(event_id):
    """Turn member confirmation on or off for this event (UPG-207); off,
    members the lead lists get no email, as before."""
    from flask import abort
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    on = request.form.get('on') == '1'
    db.collection('events').document(event_id).update({'member_confirm': on})
    log_action(db, "TEAM_CONFIRM_SWITCH", f"{session.get('user_id', '')} turned member confirmation "
               f"{'on' if on else 'off'} for event {event_id}")
    flash("Team members will get a link to confirm their email." if on else
          "Member confirmation is off: team members the lead lists get no email.", "success")
    return redirect(f'/coordinator/registrations/{event_id}')


def _registration_of(event_id):
    """The event, for an organiser's action on one of its registrations:
    404 for no event, 403 without manage_registrations."""
    from flask import abort
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'manage_registrations', event, db=db):
        abort(403)
    return event


@coord_bp.route('/registrations/<event_id>/edit/<reg_id>', methods=['GET', 'POST'])
@login_required
@role_required(COORD_ROLES)
def edit_registration(event_id, reg_id):
    """The event's organisers correct a registration's details (UPG-225), also
    after check-in; never a cancelled one."""
    import services_registration_edit as edit
    from routes_participant import registration_edit_page
    event = _registration_of(event_id)
    back = f'/coordinator/registrations/{event_id}'
    doc = db.collection('registrations').document(reg_id).get()
    reg = (doc.to_dict() or {}) if doc.exists else {}
    if str(reg.get('event_id') or '') != str(event_id):
        flash("That registration isn't for this event.", "danger")
        return redirect(back)
    if edit.cancelled(reg):
        flash("This registration is cancelled, so its details can't be changed.", "warning")
        return redirect(back)
    return registration_edit_page(reg_id, reg, event, organiser=True, back=back,
                                  member_email_action=f'/coordinator/registrations/{event_id}/member_email')


@coord_bp.route('/registrations/<event_id>/member_email', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def correct_member_email(event_id):
    """The organiser corrects a waiting member's email (UPG-225), as the lead
    does on the team page (UPG-207): the new address gets a link."""
    import services_registration_edit as edit
    import services_team_confirm as confirm
    event = _registration_of(event_id)
    reg_id = (request.form.get('reg_id') or '').strip()
    doc = db.collection('registrations').document(reg_id).get() if reg_id else None
    reg = (doc.to_dict() or {}) if doc is not None and doc.exists else {}
    if str(reg.get('event_id') or '') != str(event_id) or edit.cancelled(reg):
        flash("That registration isn't an active one of this event.", "danger")
        return redirect(f'/coordinator/registrations/{event_id}')
    page = f'/coordinator/registrations/{event_id}/edit/{reg_id}'
    if not confirm.enabled(event):
        flash("Member confirmation is off for this event, so a member's email isn't corrected here.", "warning")
        return redirect(page)
    old = (request.form.get('email') or '').strip().lower()
    new = (request.form.get('new_email') or '').strip().lower()
    try:
        outcome = confirm.correct_email(db, reg_id, reg, event, old, new, by=session.get('user_id', ''))
    except confirm.ConfirmError as exc:
        flash(str(exc), 'warning')
        return redirect(page)
    flash(f"Email changed to {new}. " + ({'sent': "A link was sent there; the old one no longer works.",
                                         'limit': "Today's email limit is reached: send the link again tomorrow."}
                                        .get(outcome, "The email couldn't be sent: send the link again later.")),
          'success' if outcome == 'sent' else 'warning')
    return redirect(page)


def seats_left(event: dict) -> dict:
    """The event's seats as the form counts them (its registration count):
    limit (0 without one), taken, free, and how many over the limit the
    SPOC's accepts took it (UPG-235)."""
    limit = safe_int((event.get('limits') or {}).get('max_participants', 0)) or safe_int(event.get('capacity', 0))
    taken = safe_int(event.get('registration_count', 0))
    return {'limit': limit, 'taken': taken, 'free': max(limit - taken, 0) if limit else None,
            'over': max(taken - limit, 0) if limit else 0}


def seat_step(promoted: dict) -> str:
    """What's left for a person given a seat from the waitlist: pay, or
    nothing (their ticket is in the portal)."""
    from utils_email import _base_url
    base = _base_url()
    if promoted.get('status') == 'pending_payment':
        return ("One step is left: pay the fee to confirm your seat.\n"
                f"Pay here: {base}/payment/pay/{promoted['reg_id']}\n")
    return ("Your seat is confirmed. Your ticket (QR code) is in the portal:\n"
            f"{base}/participant/dashboard\n")


def accepted_message(event: dict, promoted: dict, how: str = 'accepted') -> tuple:
    """(subject, text) of the email and notice telling a person they're in
    from the waitlist: the organiser accepted them (UPG-235), or, with
    how='freed', a seat opened and they were first in line (UPG-240).
    Registered, and either confirmed or asked to pay to confirm."""
    reg = promoted.get('registration') or {}
    title = event.get('title') or 'the event'
    name = reg.get('lead_name') or 'there'
    team = reg.get('team_name') if reg.get('team_name') not in (None, '', 'Individual') else ''
    who = f"your team {team}'s" if team else 'your'
    paying = promoted.get('status') == 'pending_payment'
    if how == 'freed':
        subject = (f"A seat opened for {title}: pay to confirm" if paying
                   else f"You're in: a seat opened for {title}")
        news = (f"Good news: a seat opened for {title}, and {who} place on the waitlist was next, "
                "so you're registered.\n\n")
    else:
        subject = (f"Accepted from the waitlist: pay to confirm {title}" if paying
                   else f"Accepted: you're registered for {title}")
        news = f"Good news: the organiser of {title} accepted {who} request from the waitlist.\n\n"
    text = (f"Hi {name},\n\n"
            + news
            + f"{seat_step(promoted)}\n"
            f"Registration ID: {promoted['reg_id']}\n"
            + (f"Team: {team}\n" if team else '')
            + f"Date: {event.get('date') or 'to be announced'}\n"
            f"Venue: {venue_label(event) or 'to be announced'}\n\n"
            "See you there!")
    return subject, text


def waitlist_rows(db, event: dict, form_details=None) -> list:
    """The event's waitlist for the SPOC's page (UPG-230): each person still
    waiting, first in line first, with their place, the registration they
    filled in (a waitlist joined from the event page has only name, email and
    phone), whether accepting them asks a fee (as the promotion decides) and
    the details labelled as the registrations' are (UPG-231)."""
    from services_waitlist import waiting
    from routes_waitlist import promotion_terms
    import services_export
    event_id = event['id']
    form_details = form_details or services_export.FormDetails(db, event_id)
    rows = []
    for place, (wl_id, wl) in enumerate(waiting(db, event_id), start=1):
        reg = wl.get('reg_data') if isinstance(wl.get('reg_data'), dict) else {}
        reg = dict(reg) if reg else {'lead_name': wl.get('name') or '',
                                     'lead_email': wl.get('user_email') or wl.get('email') or '',
                                     'lead_phone': wl.get('phone') or ''}
        rows.append({'id': wl_id, 'place': place, 'joined_at': str(wl.get('joined_at') or ''),
                     'paid': promotion_terms(event, wl_id, reg)['is_paid'], 'reg': reg,
                     'members': [m for m in reg.get('members') or [] if isinstance(m, dict)],
                     'details': form_details.of(reg)})
    return rows


def _accept_entry(event: dict, wl_id: str, wl: dict, who: str, actor: str):
    """Register one waiting entry as accepted by the SPOC (UPG-230/235/240):
    a portal notice to each person on the team and ONE email to the lead.
    {'promoted', 'sent'}, or None when they were already registered."""
    from routes_waitlist import promote_entry
    event_id = event['id']
    promoted = promote_entry(db, event_id, wl_id, wl, announce=False)
    if not promoted:
        return None
    # They're told they were accepted (UPG-235): a portal notice to each person
    # on the team, and an email to the lead, also in a portal-mode hackathon,
    # because it's their registration email
    import services_hackathon as hk
    subject, text = accepted_message(event, promoted)
    reg = dict(promoted.get('registration') or {}, lead_email=promoted['user_email'])
    link = (f"/payment/pay/{promoted['reg_id']}" if promoted['status'] == 'pending_payment'
            else '/participant/dashboard')
    hk.notify(db, event, reg, subject, text, link=link, kind='waitlist_promoted')
    # One email: registered or pay, and a set-password link if they have no
    # password yet (UPG-240), also in a portal-mode hackathon
    import services_seat_email
    sent = services_seat_email.tell(db, event, promoted, how='accepted', by=actor)
    log_action(db, "WAITLIST_ACCEPTED",
               f"{actor} accepted {who} ({promoted['user_email']}) from the waitlist of event {event_id}"
               + ": "
               f"registration {promoted['reg_id']}, {promoted['status']}, "
               + ("emailed" if sent['status'] == 'sent' else "email not sent"))
    return {'promoted': promoted, 'sent': sent}


def _seat_count(event_id: str, event: dict) -> str:
    fresh = db.collection('events').document(event_id).get()
    seats = seats_left(dict(fresh.to_dict() or {}) if fresh.exists else event)
    return (f" The event now has {seats['taken']} registration{'' if seats['taken'] == 1 else 's'}"
            f" for {seats['limit']} seat{'' if seats['limit'] == 1 else 's'}"
            + (f" ({seats['over']} over the limit)." if seats['over'] else ".")) if seats['limit'] else ''


@coord_bp.route('/registrations/<event_id>/accept_waitlist', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def accept_waitlist(event_id):
    """The hosting SPOC accepts a person from the waitlist (UPG-230), whatever
    their place in line, also when no seat is free (the event then has more
    registrations than seats; the page says so before). They're registered as
    the automatic promotion registers the first in line: a paid event holds the
    seat for payment, a free one confirms it with a ticket; they're told."""
    from flask import abort
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    back = f'/coordinator/registrations/{event_id}#waitlist'
    wl_id = (request.form.get('wl_id') or '').strip()
    wl_doc = db.collection('waitlists').document(wl_id).get() if wl_id else None
    wl = (wl_doc.to_dict() or {}) if wl_doc is not None and wl_doc.exists else {}
    if str(wl.get('event_id') or '') != str(event_id):
        flash("That person isn't on this event's waitlist.", "danger")
        return redirect(back)
    who = ((wl.get('reg_data') or {}).get('team_name') if isinstance(wl.get('reg_data'), dict) else '') \
        or wl.get('name') or wl.get('user_email') or wl.get('email') or wl_id
    if str(wl.get('status') or '') != 'waiting':
        flash(f"{who} is no longer waiting, so nothing changed.", "info")
        return redirect(back)

    actor = session.get('user_id', '')
    done = _accept_entry(event, wl_id, wl, who, actor)
    if not done:
        flash(f"{who} is already registered for this event, so they were taken off the waitlist.", "info")
        return redirect(back)
    promoted, sent = done['promoted'], done['sent']
    emailed = sent['status'] == 'sent'
    paying = promoted['status'] == 'pending_payment'
    count = _seat_count(event_id, event)
    told = (f"An email telling them was sent to {promoted['user_email']}."
            + (" It has a link to set their password." if sent['password_link'] else '') if emailed
            else "They were told in the portal, but today's email limit is reached, so no email was sent; "
                 "please contact them." if sent['status'] == 'limit'
            else "They were told in the portal, but the email could not be sent; please contact them.")
    flash(f"{who} is accepted and registered"
          + (" and must pay the fee to confirm their seat. " if paying else ". ") + told + count, "success")
    return redirect(f'/coordinator/registrations/{event_id}')


def _hosted_event(event_id):
    """The event, for the SPOC who may edit it (404 or 403 otherwise)."""
    from flask import abort
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    return event


@coord_bp.route('/registrations/<event_id>/documents', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def add_document(event_id):
    """The hosting SPOC gives registered teams a document (UPG-239): a title,
    their own instructions and a PDF (an undertaking form, say), or one of the
    two. Each team lead is told in the portal."""
    import services_event_documents as docs
    event = _hosted_event(event_id)
    back = f'/coordinator/registrations/{event_id}#documents'
    upload = request.files.get('pdf')
    raw = upload.read(docs.PDF_MB * 1024 * 1024 + 1) if upload and upload.filename else b''
    actor = session.get('user_id', '')
    try:
        ok, message = docs.add(db, event_id, event, title=request.form.get('title') or '',
                               instructions=request.form.get('instructions') or '', pdf=raw,
                               pdf_name=(upload.filename or '') if upload else '', by=actor)
    except Exception:
        from flask import current_app
        current_app.logger.warning("Couldn't store a document for event %s", event_id, exc_info=True)
        ok, message = False, "The PDF couldn't be saved. Please try again."
    if ok:
        new = docs.documents(event)[-1]
        told = docs.notify_registered(db, event_id, event, new)
        log_action(db, "EVENT_DOCUMENT_ADDED",
                   f"{actor} added “{new['title']}” to event {event_id}"
                   + (f" with {new['pdf_name']}" if new.get('pdf_key') else '') + f"; {told} lead(s) told")
    flash(message, 'success' if ok else 'danger')
    return redirect(back)


@coord_bp.route('/registrations/<event_id>/documents/<doc_id>/remove', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def remove_document(event_id, doc_id):
    import services_event_documents as docs
    event = _hosted_event(event_id)
    ok, message = docs.remove(db, event_id, event, doc_id)
    if ok:
        log_action(db, "EVENT_DOCUMENT_REMOVED", f"{session.get('user_id', '')} removed document {doc_id} "
                                                 f"from event {event_id}")
    flash(message, 'success' if ok else 'warning')
    return redirect(f'/coordinator/registrations/{event_id}#documents')


@coord_bp.route('/registrations/<event_id>/waitlist_auto', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def waitlist_auto(event_id):
    """The hosting SPOC switches moving up from the waitlist on its own on or
    off for the event (UPG-243). Off: a freed seat stays free until the SPOC
    accepts someone, and new sign-ups join the waitlist while anyone waits."""
    import services_waitlist
    event = _hosted_event(event_id)
    on = request.form.get('auto') == 'on'
    db.collection('events').document(event_id).update({services_waitlist.AUTO: on})
    actor = session.get('user_id', '')
    log_action(db, "WAITLIST_AUTO_" + ("ON" if on else "OFF"), f"{actor}: event {event_id}")
    flash("Teams now move up from the waitlist on their own when a seat is freed." if on else
          "Teams now stay on the waitlist until you accept them; a freed seat waits for you. "
          "New sign-ups join the waitlist while anyone is waiting.", 'success')
    return redirect(f'/coordinator/registrations/{event_id}#waitlist')


def checked_in(reg: dict) -> bool:
    """Has this team (or anyone on it) been checked in at the event?"""
    if str(reg.get('attendance') or '').strip().lower() == 'present' or reg.get('attendance_days'):
        return True
    return any(str((m or {}).get('attendance') or '').strip().lower() == 'present'
               for m in reg.get('members') or [] if isinstance(m, dict))


@coord_bp.route('/registrations/<event_id>/cancel_team', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def cancel_team(event_id):
    """The SPOC who hosts the event cancels a team's registration, with a
    reason, until the team is checked in (UPG-211): the seat is freed and the
    waitlist moves up (the participant's own cancel), the ticket is refused
    at every scanner, each person on the team gets a portal notice and the
    lead an email (not in a portal-mode hackathon)."""
    from flask import abort
    import services_hackathon as hk
    from routes_participant import cancel_registration_record
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    back = f'/coordinator/registrations/{event_id}'
    reg_id = (request.form.get('reg_id') or '').strip()
    reg_doc = db.collection('registrations').document(reg_id).get() if reg_id else None
    reg = (reg_doc.to_dict() or {}) if reg_doc is not None and reg_doc.exists else {}
    if str(reg.get('event_id') or '') != str(event_id):
        flash("That registration isn't for this event.", "danger")
        return redirect(back)
    team = reg.get('team_name') or reg.get('lead_name') or reg_id
    if str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded'):
        flash(f"{team} is already cancelled.", "info")
        return redirect(back)
    if checked_in(reg):
        flash(f"{team} has already been checked in, so it can't be cancelled.", "warning")
        return redirect(back)
    reason = (request.form.get('reason') or '').strip()[:300]
    if not reason:
        flash("Give a reason for cancelling the team; the team sees it.", "warning")
        return redirect(back)

    actor = session.get('user_id', '')
    cancel_registration_record(reg_id, reg, actor, reason)
    db.collection('registrations').document(reg_id).update({
        'cancelled_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'cancelled_by': actor})

    title = event.get('title') or 'the event'
    message = (f"The organiser cancelled the registration of {team} for {title}. Reason: {reason}\n"
               "Your ticket no longer works at the entrance. Contact the organiser if you think this is a mistake.")
    hk.notify(db, event, reg, f"Registration cancelled: {title}", message, link='/participant/dashboard',
              kind='cancellation')
    lead = str(reg.get('lead_email') or reg.get('student_email') or '').strip().lower()
    if lead and hk.email_allowed(event, 'cancellation'):
        try:
            from utils_email import send_email_notification
            send_email_notification(lead, f"Registration cancelled: {title}", message, title)
        except Exception:
            from flask import current_app
            current_app.logger.warning("Cancellation email to %s failed", lead, exc_info=True)

    paid = str(reg.get('payment_status') or reg.get('paymentStatus') or '').strip().lower() in ('paid', 'completed')
    flash(f"{team} is cancelled; its seat is free and its ticket no longer works."
          + (" It had paid: ask the admin to refund it from Payments." if paid else ''), "success")
    return redirect(back)


PAID = ('paid', 'completed', 'refunded', 'refunding', 'refund_pending')


def kept_records(db, event_id: str):
    """(registrations with a certificate, registrations with hackathon work)
    for the event: records kept elsewhere that a delete would orphan."""
    certified, submitted = set(), set()
    try:
        import services_certificates
        certified = {str(c.get('reg_id')) for c in services_certificates.for_event(event_id, current_only=False)
                     if c.get('reg_id')}
    except Exception:
        pass
    try:
        submitted = {str((d.to_dict() or {}).get('registration_id') or '')
                     for d in db.collection('project_submissions').where('event_id', '==', event_id).stream()}
    except Exception:
        pass
    return certified, submitted


def delete_refusal(reg_id: str, reg: dict, certified=(), submitted=()) -> str:
    """Why this registration can't be deleted, or '' (UPG-229). Anything with a
    record elsewhere (a check-in, a payment, a certificate, hackathon work)
    is cancelled instead, so nothing points at a team that's gone."""
    if checked_in(reg):
        return "It was checked in, so it can't be deleted."
    if (str(reg.get('payment_status') or reg.get('paymentStatus') or '').strip().lower() in PAID
            or str(reg.get('status') or '').strip().lower() == 'refunded'):
        return "It has a payment, so it can't be deleted; cancel it instead."
    if reg_id in certified:
        return "It has a certificate, so it can't be deleted."
    if reg_id in submitted:
        return "It has submitted hackathon work, so it can't be deleted; cancel it instead."
    return ''


@coord_bp.route('/registrations/<event_id>/delete_team', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def delete_team(event_id):
    """The hosting SPOC erases a team's registration for good (UPG-229): its
    members, answers, form responses copy, ticket and scores go with it. A
    team that isn't cancelled is cancelled first, so its seat is freed as
    UPG-211's cancel frees it. The people's accounts stay."""
    from flask import abort
    import services_hackathon as hk
    from routes_participant import cancel_registration_record
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    back = f'/coordinator/registrations/{event_id}'
    reg_id = (request.form.get('reg_id') or '').strip()
    reg_doc = db.collection('registrations').document(reg_id).get() if reg_id else None
    reg = (reg_doc.to_dict() or {}) if reg_doc is not None and reg_doc.exists else {}
    if str(reg.get('event_id') or '') != str(event_id):
        flash("That registration isn't for this event.", "danger")
        return redirect(back)
    team = reg.get('team_name') or reg.get('lead_name') or reg_id
    if request.form.get('confirm') != 'yes':
        flash(f"Tick the box to confirm deleting {team}; nothing was deleted.", "warning")
        return redirect(back)
    refusal = delete_refusal(reg_id, reg, *kept_records(db, event_id))
    if refusal:
        flash(f"{team} wasn't deleted. {refusal}", "warning")
        return redirect(back)

    actor = session.get('user_id', '')
    was_cancelled = str(reg.get('status') or '').strip().lower() in ('cancelled', 'refunded')
    if not was_cancelled:
        cancel_registration_record(reg_id, reg, actor, 'Deleted by the organiser')
    for collection, field in (('form_submissions', 'reg_id'), ('tickets', 'registration_id')):
        try:
            for doc in db.collection(collection).where(field, '==', reg_id).stream():
                db.collection(collection).document(doc.id).delete()
        except Exception:
            from flask import current_app
            current_app.logger.warning("Could not remove %s of %s", collection, reg_id, exc_info=True)
    db.collection('registrations').document(reg_id).delete()

    lead = str(reg.get('lead_email') or reg.get('student_email') or '').strip().lower()
    # Gone from this event, not from the portal: the accounts stay, and the
    # waitlist entry it came from no longer says "accepted" (UPG-245)
    try:
        for doc in db.collection('waitlists').where('event_id', '==', event_id).stream():
            entry = doc.to_dict() or {}
            if str(entry.get('status') or '') == 'promoted' and lead and lead in (
                    str(entry.get('user_email') or '').strip().lower(), str(entry.get('email') or '').strip().lower()):
                db.collection('waitlists').document(doc.id).update({'status': 'removed'})
    except Exception:
        from flask import current_app
        current_app.logger.warning("Could not close the waitlist entry of %s", reg_id, exc_info=True)
    people = {lead} | {str(m.get('email') or '').strip().lower()
                       for m in reg.get('members') or [] if isinstance(m, dict)}
    people.discard('')
    if not was_cancelled:
        title = event.get('title') or 'the event'
        hk.notify(db, event, reg, f"Registration removed: {title}",
                  f"The organiser removed the registration of {team} for {title}. "
                  "Your ticket no longer works. Contact the organiser if you think this is a mistake.",
                  link='/participant/dashboard', kind='cancellation')
    log_action(db, "REGISTRATION_DELETED",
               f"{actor} deleted {team} ({reg_id}) of event {event_id}: lead {lead or '-'}, {len(people)} people"
               + (", already cancelled" if was_cancelled else ''))
    flash(f"{team} is deleted for good" + ("" if was_cancelled else "; its seat is free") + ".", "success")
    return redirect(back)


@coord_bp.route('/registrations/<event_id>/entry', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def entry_selection(event_id):
    """The SPOC's entry list (UPG-214): switch it on or off with an optional
    hall limit, tick or untick teams (chosen rows, all, a CSV, or the
    shortlist). Nobody is told; the door turns away teams not on it."""
    from flask import abort
    import services_entry as entry
    from services_permission import can
    event_doc = db.collection('events').document(event_id).get()
    if not event_doc.exists:
        abort(404)
    event = dict(event_doc.to_dict() or {}, id=event_id)
    if not can(session, 'edit_event', event, db=db):
        abort(403)
    actor = session.get('user_id', '')
    back = f'/coordinator/registrations/{event_id}'
    action = (request.form.get('action') or '').strip()

    if action == 'switch':
        on = request.form.get('on') == '1'
        try:
            limit = max(int(request.form.get('limit') or 0), 0)
        except ValueError:
            limit = 0
        db.collection('events').document(event_id).update({entry.SWITCH: on, entry.LIMIT: limit})
        log_action(db, "ENTRY_SELECTION", f"Event {event_id}: entry list {'on' if on else 'off'}"
                                          f"{f', hall limit {limit}' if limit else ''} by {actor}")
        flash("Only the teams you select may enter. Nobody is told." if on
              else "The entry list is off: every registered team may enter.", "success")
        return redirect(back)

    regs = [(d.id, d.to_dict() or {}) for d in
            db.collection('registrations').where(filter=_ff('event_id', '==', event_id)).stream()]
    missed = []
    if action in ('select', 'unselect'):
        ids = {str(i) for i in request.form.getlist('reg_id')}
        chosen, value = [(rid, r) for rid, r in regs if rid in ids], action == 'select'
    elif action in ('select_all', 'unselect_all'):
        chosen, value = regs, action == 'select_all'
    elif action == 'csv':
        upload = request.files.get('file')
        text = upload.read(512 * 1024).decode('utf-8-sig', errors='replace') if upload else ''
        chosen, missed = entry.match_csv(text, regs)
        value = True
    elif action == 'shortlist':
        # The teams still in the competition; those out of it come off the list
        chosen, value = [(rid, r) for rid, r in regs if not r.get('is_eliminated')], True
        entry.set_selected(db, [(rid, r) for rid, r in regs if r.get('is_eliminated')], False, actor)
    else:
        flash("Choose what to do.", "warning")
        return redirect(back)
    if not chosen:
        flash("No teams chosen." + (f" Not found: {', '.join(missed[:10])}." if missed else ''), "warning")
        return redirect(back)

    done = entry.set_selected(db, chosen, value, actor)
    log_action(db, "ENTRY_SELECTION", f"Event {event_id}: {done['changed']} team(s) "
                                      f"{'selected' if value else 'unselected'} ({action}) by {actor}")
    notes = [f"{done['changed']} team{'' if done['changed'] == 1 else 's'} "
             f"{'selected' if value else 'taken off the entry list'}."]
    if done['kept_in']:
        notes.append(f"{done['kept_in']} already checked in, so kept on.")
    if done['eliminated']:
        notes.append(f"{done['eliminated']} out of the competition, so not selected.")
    if missed:
        notes.append(f"Not found in this event: {', '.join(missed[:10])}{' …' if len(missed) > 10 else ''}.")
    if done['paid_out']:
        notes.append(f"{done['paid_out']} of them paid: ask the admin to refund from Payments.")
    fresh = dict(db.collection('events').document(event_id).get().to_dict() or {}, id=event_id)
    c = entry.counts(db, event_id, fresh)
    if c['over']:
        notes.append(f"{c['selected']} selected is more than the hall's {c['limit']} seats.")
    if not c['on']:
        notes.append("The entry list is off, so this has no effect until you turn it on.")
    flash(' '.join(notes), "warning" if (c['over'] or missed or done['paid_out'] or not c['on']) else "success")
    return redirect(back)


# 3. CREATE EVENT: retired (UPG-78). This used to save a live event straight
# from the coordinator dashboard's old modal, skipping the event types,
# validation, draft and review. Events are made in the wizard now.
@coord_bp.route('/create_event', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def create_event():
    if session.get('role') in ('ClubSPOC', 'SuperAdmin', 'Super Admin'):
        flash("Events are created in the event wizard: it saves a draft you can review before publishing.", "info")
        return redirect('/spoc/create_event')
    flash("Event coordinators don't create events. Ask your club SPOC to create it; "
          "they can then add you to its staff.", "warning")
    return redirect('/coordinator/dashboard')


# 4. EDIT EVENT
@coord_bp.route('/edit_event/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def edit_event(event_id):
    from flask import abort
    from services_permission import can
    try:
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists:
            abort(404)
        event_data = event_doc.to_dict() or {}
        event_data['id'] = event_id
        if not can(session, 'edit_event', event_data, db=db):
            abort(403)
        overview = request.form.get('overview', '').strip()
        criteria_list = [c.strip() for c in
            request.form.get('criteria', 'Overall Score').split(',') if c.strip()] or ['Overall Score']
        media_urls = [u.strip() for u in request.form.getlist('media_urls[]') if u.strip()]
        updates = {
            'title':            request.form.get('title', '').strip(),
            'date':             request.form.get('date'),
            'deadline':         request.form.get('deadline'),
            'venue':            request.form.get('venue', '').strip(),
            'overview':         overview,
            'description':      overview[:120] + '...' if len(overview) > 120 else overview,
            'rules':            request.form.get('rules', ''),
            'prizes':           request.form.get('prizes', ''),
            'judging_criteria': criteria_list,
            'media_urls':       media_urls,
            'banner_url':       media_urls[0] if media_urls else '',
            'entry_fee':        safe_int(request.form.get('entry_fee', 0)),
            'is_team_event':    request.form.get('is_team') == 'on',
        }
        db.collection('events').document(event_id).update(updates)
        # Registrants hear about a new date or venue, once (UPG-31)
        from services_venue import notify_event_details_changed
        notify_event_details_changed(db, event_id=event_id, previous_data=event_data,
                                     new_data={**event_data, **updates})
        log_action(db, "EVENT_EDITED", f"Event {event_id} by {session.get('user_id')}")
        flash("Event updated!", "success")
    except Exception as exc:
        flash(f"Update error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 5. DELETE EVENT
@coord_bp.route('/delete_event/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def delete_event(event_id):
    _event_or_abort(event_id, 'edit_event')
    try:
        db.collection('events').document(event_id).delete()
        for r in (db.collection('registrations')
                    .where(filter=_ff('event_id', '==', event_id)).stream()):
            r.reference.delete()
        for s in (db.collection('form_submissions')
                    .where(filter=_ff('event_id', '==', event_id)).stream()):
            s.reference.delete()
        db.collection('event_forms').document(event_id).delete()
        log_action(db, "EVENT_DELETED", f"Event {event_id} by {session.get('user_id')}")
        flash("Event deleted.", "warning")
    except Exception as exc:
        flash(f"Delete error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 6. ASSIGN STAFF
@coord_bp.route('/assign_staff/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def assign_staff(event_id):
    event = _event_or_abort(event_id, 'edit_event')
    try:
        name  = request.form.get('name', '').strip()
        email = request.form.get('email', '').lower().strip()
        role  = request.form.get('role', '')
        phone = request.form.get('phone', '').strip()
        if not name or not email or not role:
            flash("Name, email and role are required.", "warning")
            return redirect('/coordinator/dashboard')
        if role not in STAFF_ROLES:
            flash(f"Staff role must be one of: {', '.join(STAFF_ROLES)}.", "danger")
            return redirect('/coordinator/dashboard')
        event_title = event.get('title', 'Event')
        user_ref    = db.collection('users').document(email)
        if not user_ref.get().exists:
            # No password by email or WhatsApp: a one-time set-password link (UPG-33)
            create_unverified_account(db, email, name, phone, role=role,
                                      category=session.get('category', 'General'))
            send_set_password_link(db, email, name,
                                   reason=f"when you were appointed as {role} for {event_title}")
            _wa(send_staff_appointment_whatsapp, phone, name, role, event_title, email)
            flash(f"Account created for {name}. A link to set their password was emailed.", "success")
        else:
            if user_ref.get().to_dict().get('role') == 'Student':
                user_ref.update({'role': role})
            send_appointment_email(email, name, role, event_title)
            flash(f"{name} already had an account. Role updated.", "info")
        db.collection('events').document(event_id).update({
            'staff': firestore.ArrayUnion([{'name': name, 'email': email, 'role': role}])})
        log_action(db, "STAFF_ASSIGNED", f"{name} ({role}) to event {event_id}")
        flash(f"{name} appointed as {role}!", "success")
    except Exception as exc:
        flash(f"Assignment error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 7. ALLOCATE ROOMS
@coord_bp.route('/allocate_rooms/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def allocate_rooms(event_id):
    _event_or_abort(event_id, 'manage_registrations')
    try:
        room_names = request.form.getlist('room_name[]')
        capacities = [safe_int(c) for c in request.form.getlist('capacity[]')]
        event_data = db.collection('events').document(event_id).get().to_dict()
        judges     = [s for s in event_data.get('staff', []) if s.get('role') == 'Judge']
        if len(judges) < len(room_names):
            flash(f"Need {len(room_names)} judges but only {len(judges)} assigned.", "warning")
            return redirect('/coordinator/dashboard')
        random.shuffle(judges)
        regs = [r for r in (db.collection('registrations')
                              .where(filter=_ff('event_id', '==', event_id)).stream())
                if not r.to_dict().get('is_eliminated')]
        random.shuffle(regs)
        reg_index = 0
        for i, (room, cap) in enumerate(zip(room_names, capacities)):
            judge = judges[i]
            for _ in range(cap):
                if reg_index >= len(regs): break
                db.collection('registrations').document(regs[reg_index].id).update({
                    'assigned_room': room.strip(),
                    'assigned_judge_email': judge['email'],
                    'assigned_judge_name': judge['name']})
                reg_index += 1
        log_action(db, "ROOMS_ALLOCATED",
                   f"{reg_index} teams in {len(room_names)} rooms for event {event_id}")
        flash(f"{reg_index} teams allocated across {len(room_names)} rooms!", "success")
    except Exception as exc:
        flash(f"Allocation error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 8. TRIGGER REMINDERS
@coord_bp.route('/trigger_reminders/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def trigger_reminders(event_id):
    _event_or_abort(event_id, 'manage_registrations')
    try:
        event_data  = db.collection('events').document(event_id).get().to_dict()
        round_num   = event_data.get('active_round', 1)
        email_count = wa_count = 0
        for r in (db.collection('registrations')
                    .where(filter=_ff('event_id', '==', event_id)).stream()):
            d = r.to_dict()
            if d.get('is_eliminated') or not d.get('assigned_room'): continue
            import services_entry   # not on the SPOC's entry list (UPG-214)
            if services_entry.left_out(event_data, d): continue
            lead_email = d.get('lead_email', ''); lead_name = d.get('lead_name', 'Participant')
            room = d.get('assigned_room', 'TBD'); judge = d.get('assigned_judge_name', 'TBD')
            phone = _phone(d)
            body = (f"ROUND {round_num} ALERT\n\nHello {lead_name},\n\n"
                    f"You are in Round {round_num} of '{event_data['title']}'.\n"
                    f"Room: {room}\nJudge: {judge}\n\nBest of luck!")
            import services_hackathon
            if services_hackathon.email_allowed(event_data, 'room'):
                send_broadcast_email([lead_email], f"Round {round_num} Details",
                                      body, event_data['title'])
                email_count += 1
            else:   # a portal notice instead (UPG-195)
                services_hackathon.notify(db, {**event_data, 'id': event_id}, d, f"Round {round_num} details",
                                          body, link=f"/hackathon/{event_id}")
            if phone and _wa(send_room_assignment_whatsapp, phone, lead_name,
                             event_data['title'], round_num, room, judge):
                wa_count += 1
        flash(f"Round {round_num} alerts — {email_count} emails, {wa_count} WhatsApp.", "success")
    except Exception as exc:
        flash(f"Reminder error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 9. PROMOTE ROUND / ELIMINATION
@coord_bp.route('/promote_round/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def promote_round(event_id):
    event_d = _event_or_abort(event_id, 'publish_results')
    try:
        # The SPOC panel's rule: the average judge score, history kept (UPG-149)
        import services_rounds
        result = services_rounds.advance(
            db, event_id=event_id, event=event_d, mode='cutoff',
            cutoff=request.form.get('cutoff_score'), expected_round=request.form.get('round'),
            eliminate_unscored=request.form.get('eliminate_unscored') == 'yes',
            actor=session.get('user_id', ''))
        if not result['ok']:
            flash(result['message'], "warning")
            return redirect('/coordinator/dashboard')
        for t in result['eliminated']:
            rd = t['reg']
            _wa(send_elimination_whatsapp, _phone(rd), rd.get('lead_name', ''),
                event_d.get('title', 'Event'), result['round'] - 1)
        log_action(db, "ROUND_PROMOTED",
                   f"Event {event_id}: {len(result['advanced'])} promoted, {len(result['eliminated'])} "
                   f"eliminated. Cutoff={request.form.get('cutoff_score')}")
        flash(result['message'], "success")
    except Exception as exc:
        flash(f"Promotion error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 10. BROADCAST
@coord_bp.route('/broadcast/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def broadcast_message(event_id):
    _event_or_abort(event_id, 'manage_registrations')
    try:
        subject   = request.form.get('subject', '').strip()
        message   = request.form.get('message', '').strip()
        event_doc = db.collection('events').document(event_id).get()
        if not event_doc.exists: return redirect('/coordinator/dashboard')
        event_title = event_doc.to_dict().get('title', 'Event')
        import services_entry   # teams not on the SPOC's entry list hear nothing more (UPG-214)
        regs        = [r for r in db.collection('registrations')
                       .where(filter=_ff('event_id', '==', event_id)).stream()
                       if not services_entry.left_out(event_doc.to_dict() or {}, r.to_dict() or {})]
        email_list  = list({r.to_dict().get('lead_email') for r in regs
                            if r.to_dict().get('lead_email')})
        phone_list  = list({_phone(r.to_dict()) for r in regs if _phone(r.to_dict())})
        import services_hackathon
        event_data = event_doc.to_dict() or {}
        if services_hackathon.email_allowed(event_data, 'broadcast'):
            send_broadcast_email(email_list, subject, message, event_title)
        else:   # an update on the hackathon page instead (UPG-195)
            services_hackathon.post_update(db, event_id, event_data, subject, message, kind='announcement',
                                           by=session.get('user_id', ''))
        wa_sent = 0
        if _WA:
            try:
                res = send_broadcast_whatsapp(phone_list, event_title, subject, message)
                wa_sent = res.get('sent', 0)
            except Exception: pass
        flash(f"Sent to {len(email_list)} emails, {wa_sent} WhatsApp.", "success")
    except Exception as exc:
        flash(f"Broadcast error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 11. PUBLISH RESULTS
@coord_bp.route('/publish_results/<event_id>', methods=['POST'])
@login_required
@role_required(COORD_ROLES)
def publish_results(event_id):
    _event_or_abort(event_id, 'publish_results')
    try:
        event_ref   = db.collection('events').document(event_id)
        event_data  = event_ref.get().to_dict() or {}
        event_title = event_data.get('title', 'Event')
        # The shared ranking (UPG-84): the same scores and places as every board.
        # Scores keep their decimals; equal scores share a place.
        from services_leaderboard import for_event
        regs = {}
        for r in (db.collection('registrations')
                    .where(filter=_ff('event_id', '==', event_id)).stream()):
            regs[r.id] = r.to_dict() or {}
        ranked = for_event(db, event_id)
        leaderboard = [{'team_name': row['team_name'], 'lead_name': row['lead_name'],
                        'email': row['lead_email'], 'phone': _phone(regs.get(row['id'], {})),
                        'score': row['score'], 'rank': row['rank']} for row in ranked]

        # Write final_rank + final_score to every scored registration
        for row in ranked:
            db.collection('registrations').document(row['id']).update({
                'final_score': row['score'],
                'final_rank':  row['rank'],
            })

        winners = [w for w in leaderboard if w['rank'] <= 3]
        import services_hackathon
        portal = services_hackathon.portal_only(event_data)   # one result email per team lead (UPG-194)
        for winner in winners:
            if not portal:
                send_result_email(str(winner['email']), str(winner['lead_name']), event_title, winner['rank'], winner['score'])
            if winner.get('phone'):
                _wa(send_result_whatsapp, winner['phone'], winner['lead_name'],
                    event_title, winner['rank'], winner['score'])

        event_ref.update({'status': 'completed', 'winners': winners, 'results_published': True,   # as the SPOC's (UPG-139)
                          'completed_at': datetime.datetime.now(datetime.timezone.utc)})
        from routes_spoc import _push_results   # results by push too (UPG-157)
        _push_results(event_id)
        if portal:
            import services_hackathon_eval
            flash(services_hackathon_eval.publish_results(
                db, event_id, {**event_data, 'id': event_id}, session.get('user_id', ''))['message'], 'info')

        # Kick off AI summaries in background (best-effort — won't block publish)
        try:
            from flask import current_app
            import threading
            def _bg_summaries():
                with current_app.app_context():
                    from routes_ai_matching import generate_summaries as _gen
                    with current_app.test_request_context(
                            f'/ai/generate_summaries/{event_id}',
                            method='POST'):
                        from flask import session as _s
                        _s['user_id'] = session.get('user_id')
                        _s['role']    = session.get('role')
                        _s['name']    = session.get('name')
                        _s['category'] = session.get('category', 'General')
                        _gen(event_id)
            threading.Thread(target=_bg_summaries, daemon=True).start()
        except Exception as exc:
            import logging as _log
            _log.getLogger(__name__).warning('Background summary generation failed: %s', exc)

        log_action(db, "RESULTS_PUBLISHED", f"Event {event_id} by {session.get('user_id')}")
        flash("Results published! Top 3 notified. AI summaries generating in background.", "success")
        from services_certificate_runs import on_results_published   # position certificates (UPG-124)
        note = on_results_published(db, event_id, session.get('user_id', ''))
        if note:
            flash(note, 'info')
    except Exception as exc:
        flash(f"Publish error: {exc}", "danger")
    return redirect('/coordinator/dashboard')


# 12–13. EXPORTS: the shared export service (UPG-03); 403 without export_data
@coord_bp.route('/export_registrations/<event_id>')
@login_required
def export_registrations(event_id):
    import services_export
    from routes_spoc import _export_name
    event = _event_or_abort(event_id, 'export_data')
    columns, rows = services_export.registration_table(db, event_id)   # read once: columns follow the data (UPG-222)
    return Response(services_export.to_csv(rows, columns), mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment; filename={_export_name(event, 'Registrations.csv')}"})


@coord_bp.route('/export_excel/<event_id>')
@login_required
def export_excel(event_id):
    import services_export
    from routes_spoc import XLSX_MIMETYPE, _export_name
    event = _event_or_abort(event_id, 'export_data')
    return Response(services_export.registrations_xlsx(db, event_id), mimetype=XLSX_MIMETYPE,
                    headers={"Content-Disposition": f"attachment; filename={_export_name(event, 'Registrations.xlsx')}"})


# 14. WALK-IN / ON-SPOT
@coord_bp.route('/on_spot')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin'])
def on_spot_form():
    from services_workflow import EVENT_DAY_STATUSES
    events = [{'id': e.id, 'title': e.to_dict().get('title')}
              for e in (db.collection('events')
                          .where(filter=_ff('status', 'in', list(EVENT_DAY_STATUSES))).stream())]
    return render_template('coordinator/on_spot.html', events=events)


@coord_bp.route('/process_walkin', methods=['POST'])
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin'])
def process_walkin():
    try:
        event_id = request.form.get('event_id', '')
        email    = request.form.get('email', '').lower().strip()
        name     = request.form.get('name', '').strip()
        usn      = request.form.get('usn', '').upper().strip()
        phone    = request.form.get('phone', '').strip()
        if not event_id or not email or not name:
            flash("Event, name and email are required.", "warning")
            return redirect('/coordinator/on_spot')
        from services_permission import can
        walkin_event = db.collection('events').document(event_id).get()
        if not walkin_event.exists or not can(
                session, 'manage_registrations', dict(walkin_event.to_dict() or {}, id=event_id), db=db):
            flash("You can only register walk-ins for events you're assigned to.", "danger")
            return redirect('/coordinator/on_spot')
        # A new walk-in gets an account they open with an emailed one-time
        # set-password link; no password is ever sent (UPG-33)
        is_new = not db.collection('users').document(email).get().exists
        if is_new:
            create_unverified_account(db, email, name, phone, usn=usn)

        reg_id      = generate_reg_id()   # UPG-95
        event_doc   = db.collection('events').document(event_id).get().to_dict() or {}
        event_title = event_doc.get('title', 'Event')
        try:
            create_registration(db, reg_id, {
                'reg_id': reg_id, 'event_id': event_id, 'event_title': event_title,
                'lead_name': name, 'lead_email': email, 'lead_usn': usn, 'lead_phone': phone,
                'team_name': name, 'members': [],
                'status': 'Confirmed', 'payment_status': 'Paid',
                'amount_paid': event_doc.get('fees', {}).get('regular', 0),
                'payment_mode': request.form.get('payment_mode', 'Cash'),
                'registered_at': datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                'attendance': 'Present',
                'checkin_time': datetime.datetime.now().strftime("%H:%M:%S"),
                'is_eliminated': False, 'current_round': event_doc.get('active_round', 1),
                'source': 'walk_in'})   # a desk sign-up, not an online form (UPG-145)
        except AlreadyRegistered:   # the database keeps one active registration per person (UPG-115)
            flash(f"{email} is already registered for {event_title}; check them in from the scanner instead.", "info")
            return redirect('/coordinator/on_spot')

        # Generate QR code bytes so it can be attached to the ticket email
        try:
            import qrcode
            import io
            from qrcode.image.pil import PilImage
            qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,
                               box_size=8, border=2)
            qr.add_data(reg_id)
            qr.make(fit=True)
            buf = io.BytesIO()
            qr.make_image(fill_color="black", back_color="white",
                          image_factory=PilImage).save(buf, format="PNG")
            qr_bytes = buf.getvalue()
        except Exception:
            qr_bytes = None

        import services_hackathon   # no ticket email for a portal-only event (UPG-195)
        if services_hackathon.email_allowed(event_doc, 'ticket'):
            send_ticket_email(email, name, event_title, reg_id, qr_bytes=qr_bytes or b'')
        if is_new:
            send_set_password_link(db, email, name,
                                   reason=f"when you registered at the desk for {event_title}")
        _wa(send_ticket_whatsapp, phone, name, event_title, reg_id,
            event_doc.get('date', ''), event_doc.get('venue', ''))
        log_action(db, "WALKIN_REGISTERED", f"Walk-in {email} for event {event_id}")
        flash(f"Walk-in for {name} registered. Ticket sent to {email}"
              + (", with a link to set a password." if is_new else "."), "success")
    except Exception as exc:
        flash(f"Walk-in error: {exc}", "danger")
    return redirect('/coordinator/on_spot')


# 15. QR SCANNER
@coord_bp.route('/scanner')
@login_required
@role_required(['EventCoordinator', 'Volunteer', 'SuperAdmin', 'Super Admin'])   # volunteers scan where assigned (UPG-120)
def scanner_selector():
    user_email = session.get('user_id', '')
    user_name  = session.get('name', user_email.split('@')[0].title())
    is_super   = session.get('role', '') in ('SuperAdmin', 'Super Admin')

    today_str    = datetime.datetime.now().strftime('%Y-%m-%d')
    tomorrow_str = (datetime.datetime.now() + datetime.timedelta(days=1)).strftime('%Y-%m-%d')

    from services_workflow import EVENT_DAY_STATUSES
    events = []
    for e in db.collection('events').where(filter=_ff('status', 'in', list(EVENT_DAY_STATUSES))).stream():
        d = e.to_dict()
        in_staff  = any(s.get('email') == user_email for s in d.get('staff', []))
        in_coords = user_email in d.get('coordinators', [])
        if not (is_super or in_staff or in_coords):
            continue
        ev_date = d.get('date', '')
        if ev_date < today_str:
            continue
        events.append({
            'id':       e.id,
            'title':    d.get('title', 'Untitled'),
            'date':     ev_date,
            'time':     d.get('time', ''),
            'venue':    venue_label(d),   # UPG-111
            'category': d.get('category', 'General'),
            'reg_count': int(d.get('registration_count', 0) or 0),
            'max_cap':   int((d.get('limits') or {}).get('max_participants', 0) or 0),
            'is_today':    ev_date == today_str,
            'is_tomorrow': ev_date == tomorrow_str,
        })

    events.sort(key=lambda x: x['date'])
    today_events    = [e for e in events if e['is_today']]
    tomorrow_events = [e for e in events if e['is_tomorrow']]
    upcoming_events = [e for e in events if not e['is_today'] and not e['is_tomorrow']]

    return render_template('coordinator/scanner_selector.html',
        user_name=user_name,
        today_events=today_events,
        tomorrow_events=tomorrow_events,
        upcoming_events=upcoming_events,
        total_assigned=len(events),
    )


@coord_bp.route('/scan/<event_id>')
@login_required
@role_required(['EventCoordinator', 'Volunteer', 'SuperAdmin', 'Super Admin'])   # volunteers scan where assigned (UPG-120)
def scan_page(event_id):
    import services_sessions
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        return redirect('/coordinator/scanner')
    d = doc.to_dict()
    user_email = session.get('user_id', '')
    is_super   = session.get('role', '') in ('SuperAdmin', 'Super Admin')
    in_staff  = any(s.get('email') == user_email for s in d.get('staff', []))
    in_coords = user_email in d.get('coordinators', [])
    if not is_super and not in_staff and not in_coords:
        flash("You are not assigned to scan for this event.", "danger")
        return redirect('/coordinator/scanner')
    today_str      = datetime.datetime.now().strftime('%Y-%m-%d')
    event_date_str = str(d.get('date', ''))[:10]
    scanning_open  = event_date_str == today_str
    return render_template('coordinator/scan.html',
                            event_id=event_id,
                            event_title=d.get('title'),
                            event_date=event_date_str,
                            today=today_str,
                            scanning_open=scanning_open,
                            sessions=services_sessions.sessions_for(d))   # session mode (UPG-159)


@coord_bp.route('/scan-hud/<event_id>')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin', 'ClubSPOC'])
def scan_hud_page(event_id):
    """Full-screen Dedicated Coordinator Scan HUD with haptic/audio feedback and offline sync."""
    target_db = db
    try:
        from app import db as app_db
        if app_db is not None:
            target_db = app_db
    except Exception:
        pass

    doc = target_db.collection('events').document(event_id).get()
    if not doc.exists:
        flash("Event not found.", "warning")
        return redirect('/coordinator/scanner')
    d = doc.to_dict()
    d['id'] = event_id
    from services_permission import can
    if not can(session, 'check_in', d, db=target_db):
        flash("You're not assigned to check in at this event.", "warning")
        return redirect('/coordinator/scanner')
    import services_entry   # the SPOC's entry list (UPG-214)
    return render_template('coordinator/scan_hud.html', event=d, event_id=event_id,
                           entry=services_entry.counts(target_db, event_id, d))


@coord_bp.route('/scan-hud/<event_id>/entry.json')
@login_required
@role_required(['EventCoordinator', 'SuperAdmin', 'Super Admin', 'ClubSPOC'])
def scan_hud_entry(event_id):
    """The entry list for the scanner (UPG-214): the counts, and the tickets
    to turn away, kept on the phone for scans made without a connection."""
    from flask import abort
    import services_entry
    from services_permission import can
    doc = db.collection('events').document(event_id).get()
    if not doc.exists:
        abort(404)
    event = dict(doc.to_dict() or {}, id=event_id)
    if not can(session, 'check_in', event, db=db):
        abort(403)
    regs = [(r.id, r.to_dict() or {}) for r in
            db.collection('registrations').where(filter=_ff('event_id', '==', event_id)).stream()]
    return jsonify(dict(services_entry.counts(db, event_id, event, regs=regs),
                        blocked=services_entry.blocked_ids(db, event_id, event, regs=regs)))


def _registration_for_staff(reg_id, permission='check_in'):
    """Return (reg, event) if the session may act on this registration's event."""
    from services_permission import can
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists:
        return None, None
    reg = reg_doc.to_dict() or {}
    ev_doc = db.collection('events').document(str(reg.get('event_id', ''))).get()
    event = dict(ev_doc.to_dict() or {}, id=reg.get('event_id')) if ev_doc.exists else None
    if event is None or not can(session, permission, event, db=db):
        return reg, None
    return reg, event


@coord_bp.route('/get_ticket/<reg_id>')
@login_required
def get_ticket(reg_id):
    """What the coordinator scanner shows: names, team, room, attendance.

    Only staff who can check in at this event; never emails, phones or
    form answers (BLK-04).
    """
    reg, event = _registration_for_staff(reg_id)
    if reg is None:
        return jsonify({'status': 'error', 'message': 'INVALID TICKET'})
    if event is None:
        return jsonify({'status': 'error', 'message': 'Not authorised for this event'}), 403
    data = {k: reg.get(k) for k in ('reg_id', 'lead_name', 'lead_usn', 'team_name', 'assigned_room',
                                    'allocated_room', 'attendance', 'payment_status', 'event_title')}
    data['reg_id'] = data['reg_id'] or reg_id
    data['members'] = [{'name': m.get('name', ''), 'usn': m.get('usn', ''), 'attendance': m.get('attendance', '')}
                       for m in (reg.get('members') or [])]
    return jsonify({'status': 'success', 'data': data})


@coord_bp.route('/mark_attendance_granular', methods=['POST'])
@login_required
def mark_attendance_granular():
    try:
        data         = request.json or {}
        reg_id       = data.get('reg_id')
        present_usns = data.get('present_usns', [])
        if not reg_id:
            return jsonify({'status': 'error', 'message': 'Missing reg_id'})
        reg_data, event = _registration_for_staff(reg_id)
        if not reg_data:
            return jsonify({'status': 'error', 'message': 'Registration not found'})
        if event is None:
            return jsonify({'status': 'error', 'message': 'Not authorised for this event'}), 403
        reg_ref  = db.collection('registrations').document(reg_id)
        if reg_data.get('payment_status') == 'Pending':
            return jsonify({'status': 'error', 'message': 'PAYMENT PENDING!'})
        import services_entry   # the SPOC's entry list (UPG-214)
        if present_usns and not services_entry.may_enter(event, reg_data):
            return jsonify({'status': 'not_selected', 'message': services_entry.REFUSED}), 409
        members = reg_data.get('members', [])
        for m in members:
            m['attendance'] = 'Present' if m.get('usn') in present_usns else 'Absent'
        # Keep the first check-in time: the scan already recorded it (UPG-02)
        reg_ref.update({'members': members,
                        'attendance': 'Present' if present_usns else 'Absent',
                        'checkin_time': reg_data.get('checkin_time') or datetime.datetime.now().strftime("%H:%M:%S")})
        log_action(db, "ATTENDANCE_MARKED",
                   f"Reg {reg_id}: {len(present_usns)} members marked present")
        return jsonify({'status': 'success',
                        'message': f"{len(present_usns)} members marked present."})
    except Exception as exc:
        return jsonify({'status': 'error', 'message': str(exc)})


# 16. CERTIFICATE
@coord_bp.route('/certificate/<reg_id>/<usn>')
@login_required
def generate_certificate(reg_id, usn):
    reg_doc = db.collection('registrations').document(reg_id).get()
    if not reg_doc.exists: return "Registration not found.", 404
    data = reg_doc.to_dict()
    # BLK-04: the registrant (lead or a member) or staff who issue certificates
    viewer = (session.get('user_id') or '').lower()
    is_registrant = viewer and (
        (data.get('lead_email') or '').lower() == viewer or
        any((m.get('email') or '').lower() == viewer for m in data.get('members', [])))
    if not is_registrant and _registration_for_staff(reg_id, 'issue_certificates')[1] is None:
        return "Not authorised.", 403
    student_name = None
    if data.get('lead_usn') == usn:
        if data.get('attendance') != 'Present':
            return "Certificate denied: marked Absent.", 403
        student_name = data.get('lead_name')
    else:
        for m in data.get('members', []):
            if m.get('usn') == usn:
                if m.get('attendance') != 'Present':
                    return "Certificate denied: marked Absent.", 403
                student_name = m.get('name')
                break
    if not student_name:
        return "Student not found in this registration.", 404
    # Their certificate from the new store, if issued: its public page (UPG-126)
    import services_certificates
    from db_adapter import to_uuid
    ids = {str(reg_id), str(to_uuid(reg_id))}            # the SQL layer keys registrations by UUID
    issued = [c for c in services_certificates.for_event(data['event_id'])
              if str(c.get('reg_id')) in ids and c.get('name') == student_name]
    if issued:
        issued.sort(key=lambda c: c['cert_type'] not in services_certificates.ATTENDED_TYPES)
        return redirect(f"/verify/{issued[0]['number']}")
    event_data = db.collection('events').document(data['event_id']).get().to_dict()
    return render_template('participant/certificate.html',
                            student_name=student_name, event=event_data)
