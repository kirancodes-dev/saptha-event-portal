# Security: what SapthaEvent does today

This page describes controls that exist in the code, with the file each one
lives in. It makes no claim of certification, independent audit, penetration
test or uptime commitment: none has been done or recorded in this repository.
What depends on how a deployment is set up is marked "deployment".

Related: [DATA_HANDLING.md](DATA_HANDLING.md) (what personal data is held and
who receives it), [PWA.md](PWA.md) (what is kept on a device),
[INSTITUTION_SETUP.md](INSTITUTION_SETUP.md), [DEPLOY.md](DEPLOY.md).

## Signing in

| Control | How it works | Where |
|---|---|---|
| Passwords | Stored as salted hashes (PBKDF2-SHA256 for new passwords; older scrypt hashes still verify). Never stored or logged in plain text. | `app.py` (hash default), `routes_auth.py` |
| Failed sign-ins | At most 5 a minute per IP address and per account, and 20 an hour per account (defaults; `LOGIN_THROTTLE_*`). The answer is the same whether or not the account exists. Counters are hashed keys, shared by every instance. | `services_login_throttle.py` |
| Super Admin sign-in | Also needs the deployment's master key (`MASTER_SECRET_KEY`). | `routes_auth.py` |
| Two-factor (TOTP) | Available for administrator accounts that turn it on. It is not forced. | `auth_2fa.py` |
| Sign in with Google | Optional; off unless the OAuth client is configured. Can be limited to the institution's email domains. | [INTEGRATIONS.md](INTEGRATIONS.md) |
| Sessions | Kept on the server (the database, or Redis when `REDIS_URL` is set). The cookie holds only the session ID and is `HttpOnly`, `SameSite=Lax`, and `Secure` in production. 30 days with "keep me signed in", otherwise 2 hours. Deactivating an account ends its open sessions at their next request. | `config.py`, `session_store.py`, `app.py` |
| API tokens | `/api/v1` uses JWT access tokens (15 minutes) and refresh tokens (7 days). | [API.md](API.md) |

## Who can do what

Every action on an event asks one function, `services_permission.can(user,
permission, event)`. An organiser acts only on events they own or hold a unit
grant for; coordinators, judges and volunteers only on events whose staff list
names them; Super Admins on everything. The roles an administrator can give
are listed at Admin → Users.

One deployment serves one institution; there is no tenant separation inside a
deployment ([MULTI_TENANCY.md](MULTI_TENANCY.md)).

## Requests

| Control | How it works | Where |
|---|---|---|
| CSRF | Every form post carries a token (Flask-WTF). `/api/v1` uses bearer tokens instead. | `app.py` |
| Content Security Policy | Scripts run only from this site and a short list of CDNs, or with a per-request nonce; no inline event handlers and no `eval`. Styles still allow inline (`'unsafe-inline'`). | `app.py` (`_csp`) |
| Other headers | `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, HSTS (one year) in production. | `app.py` (Talisman) |
| Rate limits | A general limit per client (10,000 an hour by default) and tighter ones on sensitive routes such as certificate verification. With no `REDIS_URL` the general limiter counts per instance, not across instances. | `config.py`, `app.py` |
| Secrets | Production refuses to start with a missing or weak `SECRET_KEY`, and names every other missing setting. Secrets come from the environment (deployment: Secret Manager). None is sent to the browser. | `config.py` |

## Tickets and check-in

A ticket's QR code holds a token signed with the server's secret
(`itsdangerous`, `routes_ticket.py`). The server checks the signature, the
event, payment and the entry list, and records the first check-in; a second
scan is answered "already checked in". Transferring a ticket makes the old
token stop working.

A scanner without a connection cannot verify a ticket: it keeps the scan on
the device and the server decides when the connection returns
([PWA.md](PWA.md)). No signing key is ever on a phone.

## Certificates

Each certificate has a number anyone can check at `/verify/<number>`. The PDF is kept
privately with its SHA-256, so a changed file is detectable. Download links in
emails are signed and expire.

## Records

Administrative and security-relevant actions (role changes, exports, roster
imports, audience changes, check-in overrides, deletions) are written to the
`audit_log` with the actor, the time and, for some entries, the IP address.
Super Admins read it at Admin → Audit log. The log is an ordinary table: it is
not hash-chained or write-once, so it is a record, not proof against someone
with database access.

## Deployment (not verifiable from this repository)

These are set where the service runs, and should be confirmed there:
HTTPS termination, database backups and their retention, who holds cloud
console access, log retention, and the region the data is stored in.
[DEPLOY.md](DEPLOY.md) records the setup used for the current deployment.

## Known limits

- No independent security review or penetration test is recorded.
- Two-factor sign-in is optional, including for administrators.
- Styles allow inline CSS in the Content Security Policy.
- The public `GET /api/v1/events/<id>` returns the whole event document,
  including the staff list's email addresses (logged as an open item in
  FEATURE_REVIEW.md).
- `services_ticket.py` falls back to a built-in signing key when `SECRET_KEY`
  is not in the environment. Production always sets it; a development machine
  without it would sign with a known key (open item).

## Reporting a problem

Tell the institution's portal administrator (the support address in the page
footer, set at Admin → Institution setup).
