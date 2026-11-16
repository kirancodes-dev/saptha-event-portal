# SapthaEvent REST API v1

This is the list of what the code serves under `/api/v1`. A test
(`tests/test_integration_docs.py`) fails when this list and the routes in
`routes_api_v1.py` stop matching, so an endpoint is never documented before it
exists or dropped from here while it still answers.

It is the API the mobile app uses. It is not a separate product: there are no
API keys, no per-client quotas and no sandbox. A caller signs in as a user
account and can do what that account can do.

## Base URL

`<the portal's address>/api/v1`, for example `https://events.example.edu/api/v1`.
`GET /api/v1/` returns the API's name and version.

## Signing in

`POST /api/v1/auth/login` with JSON `{"email", "password", "role"}` returns an
access token (15 minutes by default) and a refresh token (7 days by default).
Send the access token on later calls:

```http
Authorization: Bearer <access token>
```

`POST /api/v1/auth/refresh` exchanges a refresh token for new tokens;
`POST /api/v1/auth/logout` invalidates the access token. Failed sign-ins share
the web login's lockout counters. The lifetimes are the settings
`JWT_ACCESS_TOKEN_EXPIRES` and `JWT_REFRESH_TOKEN_EXPIRES` (seconds).

"Signed in" below means any valid access token. A role list means the token's
role must be one of those named in the code, or Super Admin.

## Versioning

Every path starts with `/api/v1`. A change that would break a caller goes
under a new prefix; fields may be added to a response under `v1`. There is no
deprecation schedule to quote, because there has been only one version.

## Answers and errors

Success: `{"status": "success", "data": ...}`; lists add paging fields.
Failure: `{"status": "error", "code": "...", "message": "..."}` with the HTTP
status `400` (bad input), `401` (missing, wrong or expired token), `403` (the
role may not do this), `404`, `429` (too many requests) or `503`.

## Endpoints

"Tested" means the automated tests call the endpoint. Endpoints marked "no"
exist and answer, and were not re-checked when this page was last rewritten
(2026-11-15).

### Accounts

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| POST | `/api/v1/auth/login` | anyone | yes | Sign in, get tokens |
| POST | `/api/v1/auth/register` | anyone | yes | Create a student account |
| POST | `/api/v1/auth/refresh` | anyone with a refresh token | no | New tokens |
| POST | `/api/v1/auth/logout` | signed in | no | Invalidate the access token |
| GET | `/api/v1/users/me` | signed in | yes | The caller's profile |
| PUT | `/api/v1/users/me` | signed in | yes | Update the caller's profile |
| GET | `/api/v1/achievements` | signed in | no | The caller's points and badges |
| GET | `/api/v1/notifications` | signed in | no | The caller's notifications |
| GET | `/api/v1/registrations` | signed in | no | The caller's registrations |

### Events

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| GET | `/api/v1/` | anyone | no | Name, version and a summary of endpoints |
| GET | `/api/v1/events` | anyone | yes | Listed events, paged; filters `q`, `category`, `type`, `mode`, `page`, `per_page` |
| GET | `/api/v1/events/<event_id>` | anyone | yes | One event |
| POST | `/api/v1/events` | ClubSPOC, Admin, Coordinator | yes | Create a draft event, with the web wizard's checks |
| PUT | `/api/v1/events/<event_id>` | ClubSPOC, Admin, Coordinator | no | Update an event |
| POST | `/api/v1/events/<event_id>/register` | signed in | no | Register the caller |
| GET | `/api/v1/templates` | anyone | yes | The event-type catalogue |
| GET | `/api/v1/templates/<template_id>` | anyone | yes | One event type |
| POST | `/api/v1/events/from-template` | SuperAdmin, Admin, SPOC, Organizer | yes | Create a draft from an event type |
| POST | `/api/v1/events/<event_id>/workflow-transition` | SuperAdmin, Admin, SPOC, Organizer | yes | Move an event to another stage |
| POST | `/api/v1/registrations/<reg_id>/workflow-transition` | SuperAdmin, Admin, SPOC, Organizer, Judge, Volunteer | no | Move a registration to another stage |
| GET | `/api/v1/workflow/history/<entity_type>/<entity_id>` | signed in | yes | The stage changes of an event or registration |

### Check-in, scores and certificates

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| GET | `/api/v1/events/<event_id>/ticket-manifest` | SuperAdmin, Admin, SPOC, Organizer, EventCoordinator | yes | The event's tickets, for the app's scanner |
| POST | `/api/v1/events/<event_id>/checkin-batch` | SuperAdmin, Admin, SPOC, Organizer, EventCoordinator | yes | Send check-ins the app kept while offline |
| POST | `/api/v1/events/<event_id>/scores` | SuperAdmin, Admin, SPOC, Organizer, Judge, EventCoordinator | yes | Submit a score |
| GET | `/api/v1/events/<event_id>/leaderboard` | anyone, once the organiser makes the leaderboard public | yes | The event's ranking; `403 not_public` until then |
| GET | `/api/v1/leaderboard/<event_id>` | anyone, once the organiser makes the leaderboard public | yes | The event's ranking (older path); `403 not_public` until then |
| POST | `/api/v1/events/<event_id>/issue-certificates` | SuperAdmin, Admin, SPOC, ClubSPOC, Organizer | yes | Issue certificates through the web's issuing |
| GET | `/api/v1/certificates/<cert_id>` | anyone | yes | Verify a certificate by its number |

The web scanner does not use `checkin-batch`; it sends each kept scan to
`POST /ticket/api/checkin` (see `docs/PWA.md`).

### Messages

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| POST | `/api/v1/events/<event_id>/broadcast` | SuperAdmin, Admin, SPOC, Organizer | yes | Send a notice to an event's participants |
| POST | `/api/v1/notifications/trigger` | SuperAdmin, Admin, SPOC, Organizer, EventCoordinator | yes | Send a notice to one participant |
| POST | `/api/v1/webhooks/email` | the email provider | no | Incoming delivery reports from the email provider (see "Webhooks") |

### Reports

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| GET | `/api/v1/analytics/events/<event_id>/funnel` | SuperAdmin, Admin, SPOC, Organizer | yes | Registered, confirmed, attended |
| GET | `/api/v1/analytics/events/<event_id>/throughput` | SuperAdmin, Admin, SPOC, Organizer, EventCoordinator | no | Check-ins by hour |
| GET | `/api/v1/analytics/events/<event_id>/demographics` | SuperAdmin, Admin, SPOC, Organizer | yes | Participants by department and institution |
| GET | `/api/v1/analytics/events/<event_id>/executive-summary` | SuperAdmin, Admin, SPOC, Organizer | yes | One event's summary |

### Platform administration

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| GET | `/api/v1/orgs` | SuperAdmin | no | Organisation records |
| POST | `/api/v1/orgs` | SuperAdmin | no | Create an organisation record |
| GET | `/api/v1/control-plane/overview` | SuperAdmin | yes | Counts across the deployment |
| POST | `/api/v1/control-plane/orgs/<org_id>/plan` | SuperAdmin | yes | Set an organisation record's plan |
| POST | `/api/v1/control-plane/orgs/<org_id>/status` | SuperAdmin | yes | Suspend or reactivate an organisation record |
| POST | `/api/v1/control-plane/impersonate` | SuperAdmin | yes | Record an audited support access |
| GET | `/api/v1/security/incidents` | SuperAdmin | yes | Recent security events |
| POST | `/api/v1/security/verify-nonce` | anyone | yes | Check a time-limited nonce |

Organisation records do not separate data: a deployment serves one institution
(`docs/MULTI_TENANCY.md`).

### AI event writer

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| POST | `/api/v1/ai/copilot/propose` | SuperAdmin, Admin, SPOC, Organizer | yes | Draft an event from a description |
| GET | `/api/v1/ai/copilot/proposals/<proposal_id>` | SuperAdmin, Admin, SPOC, Organizer | yes | Read a draft |
| POST | `/api/v1/ai/copilot/proposals/<proposal_id>/approve` | SuperAdmin, Admin, SPOC, Organizer | yes | Turn a draft into an event |

### Payments

These exist and are outside this page's review; see the payment code and its
tests before relying on them.

| Method | Path | Who | Tested | What it does |
|---|---|---|---|---|
| POST | `/api/v1/finance/checkout-preview` | anyone | yes | Price breakdown for a ticket |
| POST | `/api/v1/finance/convert` | anyone | yes | Currency conversion |
| GET | `/api/v1/events/<event_id>/payout-summary` | SuperAdmin, Admin, SPOC, Organizer | yes | An event's revenue summary |

## Webhooks

**Outgoing webhooks do not exist.** The portal does not call another system
when someone registers, checks in or receives a certificate (planned as
UPG-171, not built). To get data out, use the exports and feeds in
`docs/INTEGRATIONS.md`, or poll the endpoints above.

**Incoming:** `POST /api/v1/webhooks/email` takes delivery reports from the
email provider and records whether a registration's email was delivered.
