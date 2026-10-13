"""
tests/test_profile_avatar.py — UPG-71: a profile photo for every role.

On the real SQL layer (temporary SQLite from conftest.py): a user picks one of
the brand avatars, uploads a photo (validated, cropped to a square WebP with no
metadata) or removes it, and the app bar shows it. Storage is replaced by a stub
that records the bytes, so nothing is written to disk or a bucket.
"""
import io

import pytest
from PIL import Image

from tests.test_integration_flow import _login, _unique, _user


@pytest.fixture
def stored(real_app, monkeypatch):
    import routes_profile
    import utils_storage
    monkeypatch.setattr(routes_profile, 'db', real_app[1])
    saved = []

    def fake_upload(data, path, content_type):
        saved.append({'data': data, 'path': path, 'type': content_type})
        return f'https://cdn.example/{path}'

    monkeypatch.setattr(utils_storage, 'upload_file', fake_upload)
    return saved


def _student(real_app, role='Student'):
    flask_app, db = real_app
    email = f"{_unique('avatar')}@test.edu"
    _user(db, email, role, name='Asha Rao')
    return _login(flask_app, email, role), email, db


def _jpeg(width=1600, height=1000, exif=True):
    img = Image.new('RGB', (width, height), (30, 80, 160))
    out = io.BytesIO()
    if exif:
        tags = Image.Exif()
        tags[0x010F] = 'TestCam'        # Make
        img.save(out, 'JPEG', exif=tags)
    else:
        img.save(out, 'JPEG')
    return out.getvalue()


def _avatar(db, email):
    return (db.collection('users').document(email).get().to_dict() or {}).get('avatar')


# ── Criterion 1: a preset avatar is saved and shown ─────────────────────────

def test_choosing_a_preset_saves_it_and_the_app_bar_shows_it(real_app, stored):
    client, email, db = _student(real_app)
    resp = client.post('/profile/avatar', data={'action': 'preset', 'preset': 'trophy'})
    assert resp.status_code == 302
    assert _avatar(db, email) == 'preset:trophy'
    page = client.get('/profile/').get_data(as_text=True)
    assert 'class="se-avatar app-bar__avatar"' in page
    assert '/static/img/avatars/trophy.svg' in page


def test_an_unknown_preset_is_refused(real_app, stored):
    client, email, db = _student(real_app)
    client.post('/profile/avatar', data={'action': 'preset', 'preset': '../../etc/passwd'})
    assert not _avatar(db, email)


# ── Criterion 2: an upload is validated, squared and stripped ───────────────

def test_an_uploaded_photo_is_stored_as_a_square_webp_without_metadata(real_app, stored):
    client, email, db = _student(real_app)
    resp = client.post('/profile/avatar', data={'action': 'upload', 'photo': (io.BytesIO(_jpeg()), 'me.jpg')},
                       content_type='multipart/form-data')
    assert resp.status_code == 302
    assert len(stored) == 1 and stored[0]['type'] == 'image/webp'
    assert stored[0]['path'].startswith('avatars/') and stored[0]['path'].endswith('.webp')
    assert email not in stored[0]['path']            # the address isn't in the public file name
    img = Image.open(io.BytesIO(stored[0]['data']))
    assert img.format == 'WEBP' and img.size == (512, 512)
    assert not dict(img.getexif())
    assert _avatar(db, email) == f"https://cdn.example/{stored[0]['path']}"
    assert f"https://cdn.example/{stored[0]['path']}" in client.get('/profile/').get_data(as_text=True)


@pytest.mark.parametrize('payload, name', [
    (b'not an image at all', 'fake.png'),
    (b'GIF89a' + b'\x00' * 64, 'anim.gif'),
])
def test_files_that_are_not_jpg_png_or_webp_are_refused(real_app, stored, payload, name):
    client, email, db = _student(real_app)
    client.post('/profile/avatar', data={'action': 'upload', 'photo': (io.BytesIO(payload), name)},
                content_type='multipart/form-data')
    assert stored == [] and not _avatar(db, email)


def test_a_photo_over_2_mb_is_refused(real_app, stored):
    client, email, db = _student(real_app)
    big = b'\xff\xd8' + b'0' * (2 * 1024 * 1024 + 10)
    client.post('/profile/avatar', data={'action': 'upload', 'photo': (io.BytesIO(big), 'big.jpg')},
                content_type='multipart/form-data')
    assert stored == [] and not _avatar(db, email)


# ── Criterion 3: removing falls back to initials ────────────────────────────

def test_removing_the_photo_shows_initials_again(real_app, stored):
    client, email, db = _student(real_app)
    client.post('/profile/avatar', data={'action': 'preset', 'preset': 'book'})
    client.post('/profile/avatar', data={'action': 'remove'})
    assert _avatar(db, email) == ''
    page = client.get('/profile/').get_data(as_text=True)
    assert 'se-avatar--initials app-bar__avatar' in page


def test_a_sign_in_provider_photo_is_used_when_nothing_was_chosen(real_app, stored):
    from routes_profile import avatar_value
    assert avatar_value({'avatar_url': 'https://lh3.example/photo.jpg'}) == 'https://lh3.example/photo.jpg'
    assert avatar_value({'avatar_url': 'javascript:alert(1)'}) == ''
    assert avatar_value({'avatar': 'preset:star', 'avatar_url': 'https://lh3.example/p.jpg'}) == 'preset:star'


# ── Criterion 4: every role, signed in only ─────────────────────────────────

@pytest.mark.parametrize('role', ['ClubSPOC', 'EventCoordinator', 'Judge'])
def test_every_role_can_set_a_photo(real_app, stored, role):
    client, email, db = _student(real_app, role)
    client.post('/profile/avatar', data={'action': 'preset', 'preset': 'campus'})
    assert _avatar(db, email) == 'preset:campus'
    assert '/static/img/avatars/campus.svg' in client.get('/profile/').get_data(as_text=True)


def test_signed_out_requests_change_nothing(real_app, stored):
    flask_app, _ = real_app
    resp = flask_app.test_client().post('/profile/avatar', data={'action': 'preset', 'preset': 'star'})
    assert resp.status_code == 302 and '/login' in resp.headers['Location']
    assert stored == []
