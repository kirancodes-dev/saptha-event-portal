"""
services_privacy.py — privacy notice consent, a person's own data, and account
deletion (UPG-22, DPDP Act 2023).

- `PRIVACY_NOTICE_VERSION`: the notice's version; change it whenever
  templates/public/privacy.html changes, so new consents record what was shown.
- `consent_record()` / `record_consent()`: stored with the time and version on
  each registration and in the person's `user_consent` document.
- `own_data(db, email)`: everything held about one person, with other people's
  details (a team's other members) left out.
- `anonymise_account(db, email)`: what a processed deletion request does. The
  account goes (no login), and the person's name, email, phone, USN and answers
  are removed from registrations, team entries, form submissions and feedback.
  Kept, without personal data: the registration rows themselves (attendance
  and payment amounts feed the event reports). Kept as they are: payment orders
  (finance records) and the audit log; see "Decisions needed" (D-7).
- `process_due_deletions(db)`: runs requests whose 30-day grace period has
  passed (the cron `cleanup` job).
"""
import datetime
import hashlib
import logging

logger = logging.getLogger(__name__)

PRIVACY_NOTICE_VERSION = '2026-10-10'
CONSENT_FIELD = 'privacy_consent'
DELETED_NAME = 'Deleted user'


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def consent_given(form) -> bool:
    return (form.get(CONSENT_FIELD) or '').strip().lower() in ('yes', 'on', 'true', '1')


def consent_record() -> dict:
    return {'at': _now().isoformat(), 'version': PRIVACY_NOTICE_VERSION}


def record_consent(db, email: str, record: dict = None) -> None:
    """Keep the person's latest consent to the privacy notice."""
    record = record or consent_record()
    try:
        db.collection('user_consent').document(email).set({
            'accepted_privacy_policy': True,
            'privacy_notice_version': record['version'],
            'privacy_consent_at': record['at'],
            'consent_updated_at': record['at'],
        }, merge=True)
    except Exception:
        logger.exception("Could not record privacy consent for %s", email)


def _member_email(member) -> str:
    return str((member or {}).get('email') or '').strip().lower()


# What a team member may see of a registration someone else leads: nothing
# about the lead or the other members (the SQL layer also returns aliases such
# as leadEmail and student_email, so this is an allow-list).
_MEMBER_VIEW_KEYS = ('reg_id', 'event_id', 'event_title', 'team_name', 'status', 'attendance',
                     'registered_at', 'current_round', 'checkin_time', 'ticket_id', 'certificate_id')


def _own_view(reg: dict, email: str) -> dict:
    """A registration as one person may see it: their own entry only."""
    members = [m for m in reg.get('members') or [] if _member_email(m) == email]
    if (reg.get('lead_email') or '').lower() == email:
        out = dict(reg)
    else:
        out = {k: reg[k] for k in _MEMBER_VIEW_KEYS if k in reg}
    out['members'] = members
    return out


def registrations_of(db, email: str):
    """(doc_id, data) for every registration the person leads or is a member of."""
    try:
        from google.cloud.firestore_v1.base_query import FieldFilter
    except ImportError:  # pragma: no cover
        FieldFilter = None
    seen = {}
    for doc in db.collection('registrations').where(filter=FieldFilter('lead_email', '==', email)).stream():
        seen[doc.id] = doc.to_dict() or {}
    # Members aren't a queryable column; scan registrations that list members.
    for doc in db.collection('registrations').stream():
        if doc.id in seen:
            continue
        data = doc.to_dict() or {}
        if any(_member_email(m) == email for m in data.get('members') or []):
            seen[doc.id] = data
    return list(seen.items())


def own_data(db, email: str) -> dict:
    """Everything held about this person, as a download (DPDP right of access)."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    export = {'export_date': _now().isoformat(), 'user_email': email,
              'privacy_notice_version': PRIVACY_NOTICE_VERSION, 'sections': {}}

    user_doc = db.collection('users').document(email).get()
    if user_doc.exists:
        profile = dict(user_doc.to_dict() or {})
        for secret in ('password_hash', 'password', 'totp_secret', 'totp_backup_codes', 'calendar_token'):
            profile.pop(secret, None)
        export['sections']['profile'] = profile

    regs = []
    for doc_id, data in registrations_of(db, email):
        view = _own_view(data, email)
        view['id'] = doc_id
        regs.append(view)
    export['sections']['registrations'] = regs

    def by_email(collection, field='email'):
        try:
            return [dict(d.to_dict() or {}, id=d.id) for d in
                    db.collection(collection).where(filter=FieldFilter(field, '==', email)).stream()]
        except Exception:
            return []

    export['sections']['form_submissions'] = by_email('form_submissions')
    export['sections']['feedback'] = by_email('feedback')
    export['sections']['notifications'] = by_email('notifications_v2', 'user_email')
    consent = db.collection('user_consent').document(email).get()
    export['sections']['consent'] = (consent.to_dict() or {}) if consent.exists else {}
    return export


def _placeholder_email(email: str) -> str:
    return f"deleted-{hashlib.sha256(email.encode()).hexdigest()[:12]}@deleted.invalid"


def anonymise_account(db, email: str) -> dict:
    """Remove the person's account and personal data; returns what changed."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    email = email.strip().lower()
    gone = _placeholder_email(email)
    counts = {'registrations': 0, 'memberships': 0, 'submissions': 0, 'feedback': 0, 'notifications': 0}

    for doc_id, data in registrations_of(db, email):
        update = {}
        if (data.get('lead_email') or '').lower() == email:
            # student_email is the SQL layer's alias of lead_email: same value
            update.update({'lead_name': DELETED_NAME, 'lead_email': gone, 'student_email': gone,
                           'lead_phone': '', 'lead_usn': '', 'usn': '', 'form_answers': {}, 'feedback': {}})
            counts['registrations'] += 1
        members = data.get('members') or []
        if any(_member_email(m) == email for m in members):
            update['members'] = [
                {**m, 'name': DELETED_NAME, 'email': gone, 'phone': '', 'usn': ''} if _member_email(m) == email else m
                for m in members]
            counts['memberships'] += 1
        if update:
            db.collection('registrations').document(doc_id).update(update)

    for collection, field, key in (('form_submissions', 'email', 'submissions'),
                                   ('feedback', 'email', 'feedback')):
        try:
            for doc in db.collection(collection).where(filter=FieldFilter(field, '==', email)).stream():
                db.collection(collection).document(doc.id).update(
                    {'name': DELETED_NAME, 'email': gone, 'answers': {}, 'phone': ''})
                counts[key] += 1
        except Exception:
            logger.exception("Anonymising %s for a deletion failed", collection)
    try:
        for doc in db.collection('notifications_v2').where(filter=FieldFilter('user_email', '==', email)).stream():
            db.collection('notifications_v2').document(doc.id).delete()
            counts['notifications'] += 1
    except Exception:
        logger.exception("Deleting notifications for a deletion failed")

    db.collection('user_consent').document(email).delete()
    db.collection('users').document(email).delete()   # no account: no login, no reset link
    return counts


def process_due_deletions(db, now=None) -> int:
    """Carry out deletion requests whose grace period has ended."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    now = now or _now()
    done = 0
    for doc in db.collection('deletion_requests').where(filter=FieldFilter('status', '==', 'pending')).stream():
        req = doc.to_dict() or {}
        try:
            due = datetime.datetime.fromisoformat(str(req.get('scheduled_deletion_at')))
        except ValueError:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=datetime.timezone.utc)
        if due > now or not req.get('email'):
            continue
        counts = anonymise_account(db, req['email'])
        db.collection('deletion_requests').document(doc.id).update({
            'status': 'completed', 'completed_at': now.isoformat(),
            'email': _placeholder_email(req['email']), 'reason': '', 'result': counts})
        try:
            from utils import log_action
            log_action(db, "ACCOUNT_DELETED", f"Deletion request {doc.id} carried out: {counts}")
        except Exception:
            pass
        done += 1
    return done
