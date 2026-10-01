"""
session_store.py — server-side sessions in the app's own database (BLK-08).

Cloud Run instances each have their own /tmp, wiped on every restart, so
file sessions logged everyone out on each deploy and bounced users between
instances. This stores sessions in a ``flask_sessions`` table on the same
engine as the rest of the app (Redis is used instead when REDIS_URL is set).

  * The cookie holds only a random session id; the data stays server-side.
  * An empty, unmodified session is never stored, so anonymous page views
    don't create sessions.
  * Expired rows are ignored and removed by ``purge_expired_sessions``.
"""
import datetime
import secrets
from contextlib import contextmanager

from flask.json.tag import TaggedJSONSerializer
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict

_serializer = TaggedJSONSerializer()


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def _aware(dt):
    # SQLite returns naive datetimes even for timezone-aware columns
    return dt.replace(tzinfo=datetime.timezone.utc) if dt is not None and dt.tzinfo is None else dt


@contextmanager
def _primary():
    """A transaction on the primary engine. Sessions are written during GET
    requests too, which db_pg.get_session would route to a read replica."""
    from sqlalchemy.orm import Session

    from db_pg import get_engine
    with Session(get_engine()) as s:
        with s.begin():
            yield s


class SQLSession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None, new=False):
        def on_update(self):
            self.modified = True
        super().__init__(initial, on_update)
        self.sid = sid
        self.new = new
        self.modified = False
        self.stored_expiry = None


class SQLSessionInterface(SessionInterface):
    """Flask session interface backed by models_pg.FlaskSession."""

    # Re-save an unmodified session only when its expiry has drifted this far,
    # so ordinary page views don't write to the database.
    REFRESH_AFTER = datetime.timedelta(hours=1)

    def _lifetime(self, app, session):
        if session.permanent:
            return app.permanent_session_lifetime
        return datetime.timedelta(seconds=app.config.get('SHORT_SESSION_LIFETIME', 7200))

    def open_session(self, app, request):
        from models_pg import FlaskSession

        sid = request.cookies.get(self.get_cookie_name(app))
        if sid:
            with _primary() as s:
                row = s.get(FlaskSession, sid)
                if row is not None and _aware(row.expiry) > _utcnow():
                    try:
                        data = _serializer.loads(row.data)
                    except Exception:
                        data = {}
                    session = SQLSession(data, sid=sid)
                    session.stored_expiry = _aware(row.expiry)
                    return session
        return SQLSession(sid=secrets.token_urlsafe(32), new=True)

    def save_session(self, app, session, response):
        from models_pg import FlaskSession

        name = self.get_cookie_name(app)
        domain = self.get_cookie_domain(app)
        path = self.get_cookie_path(app)

        if not session:
            # Logged out (or never used): drop the row and the cookie
            if session.modified and not session.new:
                with _primary() as s:
                    s.query(FlaskSession).filter_by(id=session.sid).delete()
                response.delete_cookie(name, domain=domain, path=path)
            return

        expiry = _utcnow() + self._lifetime(app, session)
        stale = session.stored_expiry is None or expiry - session.stored_expiry > self.REFRESH_AFTER
        if not (session.modified or session.new or stale):
            return

        payload = _serializer.dumps(dict(session))
        with _primary() as s:
            row = s.get(FlaskSession, session.sid)
            if row is None:
                s.add(FlaskSession(id=session.sid, data=payload, expiry=expiry))
            else:
                row.data = payload
                row.expiry = expiry

        response.set_cookie(
            name, session.sid,
            expires=self.get_expiration_time(app, session),
            httponly=self.get_cookie_httponly(app),
            domain=domain, path=path,
            secure=self.get_cookie_secure(app),
            samesite=self.get_cookie_samesite(app),
        )


def purge_expired_sessions() -> int:
    """Delete expired session rows; returns how many were removed."""
    from models_pg import FlaskSession
    with _primary() as s:
        return s.query(FlaskSession).filter(FlaskSession.expiry <= _utcnow()).delete()
