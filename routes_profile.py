# =========================================================
# routes_profile.py
# =========================================================
from flask import Blueprint, flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash
from models import db
from utils import login_required, log_action, safe_int

profile_bp = Blueprint('profile', __name__, url_prefix='/profile')


@profile_bp.route('/')
@login_required
def view_profile():
    user_doc = db.collection('users').document(session['user_id']).get()
    user     = user_doc.to_dict() or {}
    my_teams = []
    stats    = {'total': 0, 'attended': 0, 'avg_score': None, 'top_rank': None}

    if session.get('role') == 'Student':
        all_scores = []
        ranks      = []
        for r in db.collection('registrations').where('lead_email', '==', session['user_id']).stream():
            d       = r.to_dict()
            d['id'] = r.id
            event_id = d.get('event_id')
            if event_id:
                event_doc = db.collection('events').document(event_id).get()
                if event_doc.exists:
                    evt = event_doc.to_dict()
                    d['event_title'] = evt.get('title', d.get('event_title', ''))
            my_teams.append(d)
            stats['total'] += 1
            if d.get('attendance') == 'Present':
                stats['attended'] += 1
            raw_scores = d.get('scores', {})
            if raw_scores:
                avgs = [safe_int(s.get('total', 0)) for s in raw_scores.values()]
                if avgs:
                    all_scores.append(round(sum(avgs) / len(avgs), 1))
            if d.get('final_rank'):
                ranks.append(d['final_rank'])

        if all_scores:
            stats['avg_score'] = round(sum(all_scores) / len(all_scores), 1)
        if ranks:
            stats['top_rank'] = min(ranks)

    # A pending account deletion, shown with a cancel button (UPG-22)
    deletion_due = ''
    try:
        for req in (db.collection('deletion_requests').where('email', '==', session['user_id'])
                      .where('status', '==', 'pending').limit(1).stream()):
            deletion_due = str((req.to_dict() or {}).get('scheduled_deletion_at', ''))[:10]
    except Exception:
        pass

    return render_template('profile/dashboard.html', user=user, teams=my_teams, stats=stats,
                           deletion_due=deletion_due,
                           avatar=avatar_value(user), avatar_presets=AVATAR_PRESETS)


@profile_bp.route('/update', methods=['POST'])
@login_required
def update_profile():
    try:
        name  = request.form.get('name', '').strip()
        phone = request.form.get('phone', '').strip()
        usn   = request.form.get('usn', '').strip().upper()

        update_data = {'name': name, 'phone': phone}
        if usn:
            update_data['usn'] = usn

        db.collection('users').document(session['user_id']).update(update_data)
        session['name'] = name
        log_action(db, "PROFILE_UPDATED", f"{session['user_id']} updated profile")
        flash("✅ Profile updated!", "success")
    except Exception as exc:
        flash(f"Error: {exc}", "danger")

    return redirect('/profile/')


@profile_bp.route('/security', methods=['POST'])
@login_required
def change_password():
    current_pw = request.form.get('current_password', '')
    new_pw     = request.form.get('new_password', '')
    confirm_pw = request.form.get('confirm_password', '')

    user_doc = db.collection('users').document(session['user_id']).get()
    user     = user_doc.to_dict() or {}

    if not check_password_hash(user.get('password', ''), current_pw):
        flash("❌ Current password is incorrect.", "danger")
        return redirect('/profile/')

    if new_pw != confirm_pw:
        flash("❌ New passwords do not match.", "danger")
        return redirect('/profile/')

    if len(new_pw) < 8:
        flash("❌ Password must be at least 8 characters.", "danger")
        return redirect('/profile/')

    db.collection('users').document(session['user_id']).update({
        'password': generate_password_hash(new_pw)
    })
    log_action(db, "PASSWORD_CHANGED", f"{session['user_id']} changed password")
    flash("🔒 Password changed successfully!", "success")
    return redirect('/profile/')


# ── Profile photo (UPG-71) ────────────────────────────────────────────────────
# A user's photo is `users.avatar`: '' (initials), 'preset:<key>' (one of the
# brand avatars under static/img/avatars/) or the URL of an uploaded photo. A
# Google/Microsoft sign-in's `avatar_url` is used when nothing was chosen.
AVATAR_PRESETS = ('campus', 'cap', 'book', 'code', 'trophy', 'music', 'sport', 'star')
AVATAR_MAX_BYTES = 2 * 1024 * 1024
AVATAR_SIZE = 512


def avatar_value(user: dict) -> str:
    """The avatar to show for a user record: a preset key, a URL, or ''."""
    chosen = (user or {}).get('avatar') or ''
    if chosen.startswith('preset:') and chosen[7:] in AVATAR_PRESETS:
        return chosen
    if chosen.startswith(('https://', 'http://', '/static/uploads/')):
        return chosen
    oauth = (user or {}).get('avatar_url') or ''
    return oauth if oauth.startswith('https://') else ''


def _square_webp(data: bytes) -> bytes:
    """Validate an uploaded image and return it as a square WebP without metadata."""
    import io
    from PIL import Image, ImageOps, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            probe.verify()
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("That file isn't an image we can read. Use a JPG, PNG or WebP photo.")
    if fmt not in ('JPEG', 'PNG', 'WEBP'):
        raise ValueError("Use a JPG, PNG or WebP photo.")
    with Image.open(io.BytesIO(data)) as img:
        if img.width > 6000 or img.height > 6000:
            raise ValueError("That photo is too large (at most 6000 pixels on a side).")
        img = ImageOps.exif_transpose(img).convert('RGB')
        img = ImageOps.fit(img, (AVATAR_SIZE, AVATAR_SIZE), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, 'WEBP', quality=85)   # re-encoding drops EXIF (location, camera)
        return out.getvalue()


@profile_bp.route('/avatar', methods=['POST'])
@login_required
def update_avatar():
    import hashlib
    import secrets
    from utils_storage import upload_file

    email = session['user_id']
    action = request.form.get('action', '')
    try:
        if action == 'remove':
            value = ''
        elif action == 'preset':
            key = request.form.get('preset', '')
            if key not in AVATAR_PRESETS:
                flash("Choose one of the avatars shown.", "danger")
                return redirect('/profile/#photo')
            value = f'preset:{key}'
        elif action == 'upload':
            upload = request.files.get('photo')
            if not upload or not upload.filename:
                flash("Choose a photo to upload.", "danger")
                return redirect('/profile/#photo')
            data = upload.read(AVATAR_MAX_BYTES + 1)
            if len(data) > AVATAR_MAX_BYTES:
                flash("That photo is larger than 2 MB.", "danger")
                return redirect('/profile/#photo')
            webp = _square_webp(data)
            owner = hashlib.sha256(email.lower().encode()).hexdigest()[:16]
            url = upload_file(webp, f'avatars/{owner}-{secrets.token_hex(4)}.webp', 'image/webp')
            if not url:
                flash("The photo couldn't be saved. Please try again.", "danger")
                return redirect('/profile/#photo')
            # Local development returns an absolute URL on BASE_URL; keep the path only
            value = url[url.index('/static/uploads/'):] if '/static/uploads/' in url else url
        else:
            flash("Nothing to change.", "warning")
            return redirect('/profile/#photo')

        db.collection('users').document(email).update({'avatar': value})
        session['avatar'] = avatar_value({'avatar': value} if value else
                                         (db.collection('users').document(email).get().to_dict() or {}))
        log_action(db, "PROFILE_PHOTO_UPDATED", f"{email} set profile photo ({action})")
        flash("Profile photo updated." if action != 'remove' else "Profile photo removed.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    except Exception:
        flash("The photo couldn't be saved. Please try again.", "danger")
    return redirect('/profile/#photo')


@profile_bp.app_context_processor
def inject_current_avatar():
    """`current_avatar` for the app bar: read once per session, then cached in it."""
    if not session.get('user_id'):
        return {'current_avatar': ''}
    if 'avatar' not in session:
        try:
            user = db.collection('users').document(session['user_id']).get().to_dict() or {}
            session['avatar'] = avatar_value(user)
        except Exception:
            return {'current_avatar': ''}
    return {'current_avatar': session.get('avatar') or ''}
