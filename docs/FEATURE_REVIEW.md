# SapthaEvent — Feature Review and Upgrade Plan

**Reviewed:** 2026-09-28 · **Code reviewed at commit:** `694c729` (branch `master`)
**Re-verified after merging BLK-09:** 2026-09-28 at `1f4cdc8` for every item touching `db_adapter.py`, `db_pg.py`, `config.py`, `routes_payment.py` or `tests/conftest.py` (marked "Last verified … `1f4cdc8`"). Other items still describe `694c729`; re-check them before building (see `AGENTS.md` rule 3).
**Phase 0 re-verification (production-ready plan):** 2026-09-30 at `56a014d`, branch `production-ready`. Every item that isn't DONE was re-checked against the code at `56a014d` and now says "Last verified: 2026-09-30, commit `56a014d`". App code changed since `1f4cdc8` only in `db_adapter.py` (root units) and `routes_judge.py` (the `abort` import), so every `file:line` below still points at the right code unless the item says otherwise. New items BLK-12, BLK-13 and UPG-16 to UPG-32 were added, and section 7 lists the phases.
**Scope:** whole repo; the goal is for this to be the one system Sapthagiri NPS University uses for every kind of event.

This file is the source of truth for planned work. Agents and developers work on one item ID at a time (see `AGENTS.md`).

### How to read the evidence

- `file:line` points at the code as of the item's "Last verified" commit (`56a014d` for everything re-checked in Phase 0). Items built on `production-ready` cite their own commit by message and parent hash (e.g. "BLK-02: …", parent `07ad7b2`), because a commit can't contain its own hash; find it with `git log --grep '^BLK-02:'`.
- **How checks are run (from Phase 0):** Python 3.11 venv with `requirements-dev.txt`; full pytest on a temp SQLite database **and** on PostgreSQL 16 (an embedded server from the `pgserver` package, one empty database per run, passed as `TEST_DATABASE_URL`); `ruff check .`. Every key in the developer's `.env` is pre-set to a blank or dummy value first, because `app.py` calls `load_dotenv()` and python-dotenv never overrides a variable that's already set (BLK-05 removes the need for this). Baseline at `56a014d`: **414 passed, 1 xfailed** on both databases; ruff clean.
- **Python version:** since `1f4cdc8`, requirements are pinned and tested on Python 3.11 (as in CI and the Dockerfile). The repo's local `.venv` is Python 3.9 and fails 5 tests on `hashlib.scrypt` (the branch fails the same 5 on 3.9). Recreate `.venv` with 3.11.
- **[R]** means verified by running: a sandbox copy of the repo, no `.env`, no `serviceAccountKey.json`, `DATABASE_TYPE=postgres` code path through `db_adapter.py` on a throwaway SQLite file, seeded with `seed_all_roles_demo.py` + `seed_events_universal.py`, then driven over HTTP as each role.
- **[C]** means verified by reading the code only.
- The planning docs (`GAP_ANALYSIS.md`, `UNIVERSAL_EVENT_ENGINE_PLAN.md`, `PHASED_IMPLEMENTATION_PLAN.md`, `upgrade-log.md`, `reports/`) and commit messages were treated as claims, not facts. Example: commit `79c8e92` says "14 turnkey templates"; `services_templates.TEMPLATES_CATALOG` has 7 (hackathon, conference, workshop, seminar, sports, cultural, webinar).
- `pytest` (tests/ folder): **312 passed** at `694c729` [R], but those tests didn't exercise the SQL adapter the app uses by default (BLK-05). At `1f4cdc8`: **334 passed** on Python 3.11 with pinned requirements [R], including 7 HTTP integration tests and 15 document-fidelity tests that run on the real adapter.

**Important condition.** `models.py:31` makes `postgres` the default backend, and the local `.env` sets `DATABASE_TYPE=postgres`. Many breaks below come from the SQL adapter (`db_adapter.py`) and happen **only in postgres mode**. In Firestore mode, those fields persist. I could not confirm which backend production uses: the untracked `scratch/env-vars.yaml` says `firestore`, while `.env` says `postgres`. Items say "postgres mode" where this applies.

---

## 1. Summary

1. Today the app does this end to end: public event discovery and calendar, student sign-up and login, SPOC event creation from a template, admin approval, free registration via SPOC-created forms, a ticket page, manual check-in on the event day, judge scoring (with plain-text criteria), a results leaderboard, and admin analytics pages [R].
2. Almost everything after "register" breaks somewhere. Camera QR check-in, certificates, feedback, exports, coordinator assignment, team events and paid events all fail in postgres mode [R].
3. Biggest gap 1 — **data loss in the DB adapter:** at `694c729`, postgres mode silently dropped non-column fields, renamed others on read and ignored unknown filters (BLK-06). **Mostly fixed by merging BLK-09 (`1f4cdc8`)** [R]: fields round-trip, filters work, SPOCs can assign coordinators. Still open: enum columns keep lossy values, so SQL filters on role/category mismatch.
4. Biggest gap 2 — **security holes that make new features unsafe** (still open at `1f4cdc8` [R]):
   - anyone could log in as any student through the public registration form (BLK-02, **fixed** on `production-ready`);
   - paid events can be confirmed for ₹0 or with a forged payment signature (BLK-03);
   - some endpoints leak registrations (BLK-04);
   - any SPOC or coordinator can delete any event through a GET link, and `/api/v1` is open to cross-site requests from a logged-in browser (BLK-04, found in Phase 0);
   - login has no rate limiting (BLK-13);
   - a user database and old credentials are in the public GitHub history (BLK-01).
7. **Not production-ready yet (Phase 0, 2026-09-30):** sessions and uploads live on the container's disk (BLK-08, UPG-17), an empty database can't be built through migrations (UPG-16), background jobs need a broker that the Cloud Run target doesn't have (UPG-18, UPG-07), and 110 of 129 templates are standalone pages (UPG-23). Section 7 has the phased plan.
5. Biggest gap 3 — **the event day still happens outside the app:** the camera scanners reject real ticket QRs and certificates fail to generate [R at `694c729`; not changed by BLK-09]. Departments still need paper sign-in and a separate certificate tool.
6. About 20 templates are never rendered, 3 blueprints are never registered, there are 2 parallel notification systems, 2 payment stacks, 13 seed scripts and a diverged copy of the whole app in `functions/saptha_app/` (UPG-14/15).

---

## 2. Feature inventory

Status: WORKING · PARTLY BUILT (says where it breaks) · NOT CONNECTED (code exists, no UI uses it) · MISSING.

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| Home / event discovery / catalogue | WORKING [R] | `app.py:524`, `app.py:713`, crawl 200 | Home shows a hard-coded fake hackathon when no events exist (`app.py:683-694`). |
| University calendar + event `.ics` | WORKING [R] | `app.py:1066`, `app.py:768` | Department-only visibility filter at `app.py:984-987`. |
| Personal calendar feed | WORKING [R at BLK-04b] | `app.py:1109-1170`, `services_accounts.py:120-145` | Own events when logged in; calendar apps use a signed, resettable per-user token; `?user=` is ignored (BLK-04). |
| Student sign-up / login | WORKING [R] | `routes_auth.py:195`, `routes_auth.py:36` | USN now persists (document shadow, `db_adapter.py` `extra_json`) [R at `1f4cdc8`]; it wasn't stored at `694c729`. |
| Google / Microsoft login | NOT CONNECTED [C] | `auth_oauth.py:32-135` | Login page has no link to `/auth/google` (`templates/login.html`). |
| 2FA (TOTP) | NOT CONNECTED [C] | `auth_2fa.py:42-155` | No template links to `/auth/2fa/*`. `totp_*` keys now persist [R round-trip at `1f4cdc8`]. |
| Event creation from template (SPOC) | WORKING [R at `1f4cdc8`] | `routes_spoc.py:96-274` | All settings now persist, e.g. a ₹500 fee and team 2–4 (`tests/test_integration_flow.py:75-102`) [R]. Presets only applied for seminar/workshop (`routes_spoc.py:131`). |
| Approval workflow (unit → admin) | WORKING [R] | `services_workflow.py:130-217`, `routes_admin.py:786` | Admin approval sets `published`; SPOC must still move it to `registration_open` (`routes_forms.py:309` treats `published` as closed). |
| Registration form (custom fields) | PARTLY BUILT [R] | `templates/public/registration_form.html:485`, `routes_spoc.py:252-256` | Works for SPOC-created seminar/workshop. Seeded and template-created forms store `field_name`; the template renders `name="{{ field.id }}"`, so inputs get `name=""` and there's no name/email field. |
| Form builder | WORKING (page load and save [R at BLK-04b]) | `routes_forms.py:223-300` | Only the event's owner (or admins) can edit the form; assigned staff can see responses (BLK-04). |
| Auto-account on registration (no auto-login) | WORKING [R at BLK-02] | `services_accounts.py:37-106`, `routes_forms.py:387-426`, `routes_auth.py:203` | Fixed by BLK-02: no path logs anyone in; existing accounts log in first; new emails get an unverified account and a one-time set-password link; no password is shown or emailed. |
| Waitlist | PARTLY BUILT [R at BLK-03] | `routes_forms.py`, `routes_waitlist.py:186-300`, `tasks/waitlist_tasks.py` | Promotion on a paid event holds the seat as `pending_payment` with a pay link (BLK-03). Two promotion code paths remain (UPG-14). No SPOC UI link to `/waitlist/list`. |
| Paid registration (Razorpay) | WORKING in tests [R at BLK-03] | `routes_payment.py:66-400`, `services_payments.py` | Server-side price; orders recorded and checked on verify; payment IDs single-use; fails closed without keys; simulation only with `PAYMENT_SIMULATION=true` outside production (BLK-03). Not yet run against Razorpay test mode (UPG-30). No receipt email or refunds (UPG-30). |
| Stripe payments | NOT CONNECTED [C] | `routes_payment_stripe.py` | No template or JS references `/payment/stripe`. |
| Coupons | NOT CONNECTED in the UI [C] | `routes_coupons.py`, `services_payments.py:36-73` | `create_order` applies a coupon validated on the server if one is sent (BLK-03), but no template or JS sends one or calls `/coupons/*`. |
| Digital ticket page | PARTLY BUILT [R] | `routes_ticket.py:115-172` | New registrations open; the seeded registration shows "not your ticket" because `is_lead` reads `lead_email` (`routes_ticket.py:134`), which postgres mode returned as `leadEmail` at `694c729`. At `1f4cdc8` the key reads back correctly [R round-trip]; the page wasn't re-run. |
| Camera QR check-in (coordinator, SPOC, HUD) | PARTLY BUILT — **fails with real QRs** [R] | `templates/coordinator/scan.html:231-234`, `templates/spoc/scan.html:447-458`, `routes_ticket.py:270-271,479-481` | Coordinator/SPOC scanners pass the signed token as a reg ID → "INVALID TICKET" / 404 [R]. `/ticket/verify` and `/ticket/api/verify` said "Payment pending" for free tickets [R at `694c729`]. At `1f4cdc8` `payment_status` reads back as written (`Free`), so that gate likely passes; the token-as-reg-ID break is unchanged [C]. Not re-run (UPG-02). At `56a014d`: `/ticket/verify` accepts signed tokens only (`routes_ticket.py:56-84`), its GET is read-only, and only authorised staff can POST a check-in (`routes_ticket.py:318-327`) [C]; the lower-case `free` written by waitlist promotion would still read as unpaid (`routes_ticket.py:271,332,480,535`). |
| Manual check-in (SPOC list) | WORKING on event day [R] | `routes_spoc.py:451-525` | Locked until event date (intended). Attendee name comes back blank in postgres mode. |
| Kiosk check-in | PARTLY BUILT [C at `56a014d`] | `routes_checkin.py:236-400` | Secured in the root app: login + coordinator role + `can(…, 'check_in', event)`, searches only the chosen event, returns no email or phone (`routes_checkin.py:286-297`). Tests use the mock DB only (BLK-12). Coordinators can now be assigned (BLK-09). **The `functions/saptha_app` copy's kiosk has no login at all** (BLK-12). |
| Venue-QR self check-in | PARTLY BUILT [C at `56a014d`] | `routes_checkin.py:65-172` | Root app: needs the logged-in owner plus a signed venue code valid for 10 minutes (`routes_checkin.py:86-128`). Submit not run on the real DB (BLK-12). The `functions/` copy checks in by a typed email alone. |
| Offline check-in (PWA queue) | PARTLY BUILT [C] | `static/js/offline-sync.js:83` | Replays to kiosk confirm (same 403). `/api/v1/.../checkin-batch` is JWT-only with no UI. |
| Coordinator assignment | WORKING [R at `1f4cdc8`] | `routes_spoc.py:1171-1252` | `spoc_id` now persists, so "assign coordinator" adds the coordinator to `staff` [R], and the coordinator can then open registrations (`tests/test_integration_flow.py:166-186`). |
| Judge assignment | WORKING [R] | `routes_spoc.py:1379-1435` | Writes `staff`, which persists. |
| Judge dashboard | PARTLY BUILT [R] | `routes_judge.py:58-59` | Lists only events with status `active`; new workflow states never appear. |
| Judge scoring | PARTLY BUILT [R] | `routes_judge.py:158`, `templates/spoc/create_event.html:1116` | Criteria from the create form are objects; scoring crashes (`'dict' object has no attribute 'replace'` / 500) [R]. Works with string criteria [R]. |
| Rounds, lock scoring, advance round | not re-run [C at `1f4cdc8`] | `routes_spoc.py` round panel / lock / advance | The `spoc_id` gate is now satisfiable (the field persists), so these are likely unblocked; not re-run. |
| AI judge↔team matching | PARTLY BUILT [C] | `routes_ai_matching.py:87-116` | Reads `form_answers`/`team_name`, which are dropped or renamed in postgres mode. |
| Results + public leaderboard | WORKING [R] | `routes_spoc.py:786`, `routes_live.py:161` | Team/lead names blank in postgres mode. |
| Certificates | PARTLY BUILT [C at `1f4cdc8`] | `tasks/cert_tasks.py:44-50` vs `utils_certificate.py:145` | The PDF task signature mismatch (`TypeError ... 'name'`, [R] at `694c729`) is **unchanged**. Page name and bulk gate depend on fields that now persist, so they're likely fixed; not re-run (UPG-06). |
| Certificate public verification | not run [C] | `routes_verification.py:21-124` | Depends on certificates being issued. |
| Feedback | PARTLY BUILT [R at `1f4cdc8`] | `routes_feedback.py`, `routes_participant.py:286` | `/feedback/view` now redirects to `/feedback/analytics`, which returns 200 [R]. The student submit path wasn't re-run (UPG-05). |
| Hackathon submission + kanban | WORKING (page load) [R] | `routes_hackathon.py:20-215` | Pipeline and project pages are public (`routes_hackathon.py:107,137`). |
| Teams (create/join by code) | NOT CONNECTED [C] | `routes_teams.py:92` | Writes a separate `teams` collection; never linked to registrations, tickets or judging. |
| Agenda / sessions | WORKING (page load) [R] | `routes_spoc.py:759` | Session-level attendance not found. |
| Announcements | not run [C] | `routes_spoc.py:684-758` | — |
| Email (Brevo / Resend / Gmail) | PARTLY BUILT [C] | `utils_email.py`, `routes_auth.py:399-404` | SPOC blast email blocked by `spoc_id` (`routes_spoc.py:972`). |
| WhatsApp (Twilio) | not run [C] | `utils_whatsapp.py` | Needs a paid Twilio sender. |
| In-app notifications | PARTLY BUILT [C] | `routes_notifications.py:20` vs `routes_notifications_v2.py:70` | Student dashboard feed reads `notifications`, which nothing writes; every writer uses `notifications_v2`. |
| Scheduled reminders / lifecycle | NOT CONNECTED on free tier [C at `1f4cdc8`] | `celery_app.py:95-120`, `docker-compose.yml:27-37`, `Dockerfile:33` | `docker-compose.yml` now runs worker + beat for self-hosting; a single web service still runs only gunicorn (UPG-07). |
| Registration exports (CSV/Excel) | not re-run [C at `1f4cdc8`] | `routes_spoc.py:314`, `routes_coordinator.py`, `routes_admin.py:283` | Blank columns at `694c729` [R] came from renamed keys, which now read back correctly [R round-trip]; exports not re-run (UPG-03). |
| Admin dashboard / analytics / report | WORKING (page load) [R] | `routes_admin.py:39,124,563` | Figures built from the same lossy records. |
| Org units, scoped roles | PARTLY BUILT [R] | `routes_admin.py:629-785` | The first visit to `/admin/org_units` locks SuperAdmin and SPOC accounts out (BLK-07) [R]. |
| Venues, rooms, conflict check | PARTLY BUILT [C] | `routes_admin.py:825-1040`, `routes_spoc.py:1122-1128`, `services_workflow.py:190-218` | Admin CRUD page loads [R]; the create-event form has no room field, so conflicts are only checked on edit/publish. |
| Student portfolio `/u/<usn>` | WORKING [R at `1f4cdc8`] | `routes_portfolio.py:27` | Shows the right student; at `694c729` the ignored `usn` filter showed the Super Admin. |
| XP / gamification leaderboard | not re-run [C] | `routes_gamification.py` | `xp`/`badges` now persist [R round-trip at `1f4cdc8`]; leaderboard not re-run. |
| Referrals | not re-run [C] | `routes_referrals.py:38` | Filters on document-only fields now apply (`tests/test_db_documents.py:95`); referral page not re-run. |
| Teammate matchmaker | Demo only [C] | `routes_matchmaker.py:12,115` | Suggests hard-coded `MOCK_STUDENTS`. |
| Online exams / proctoring | PARTLY BUILT [R at `1f4cdc8`] | `templates/spoc/proctor_monitor.html:1` | SPOC proctor page now 200 [R]; exam flow not run. |
| Privacy (DPDP export/delete/consent) | not run [C] | `routes_compliance.py` | — |
| Audit log | PARTLY BUILT [R at `1f4cdc8`] | `utils.py` `log_action`, `templates/admin/audit_log.html` | The page shows the actor again (reads the document's `user` key, now preserved). The SQL `actorEmail` column still says `system` [R] (BLK-06). |
| REST API v1 (JWT) + multi-tenant control plane | NOT CONNECTED [C] | `routes_api_v1.py` | Only the AI copilot endpoints are called from a template. Finance, analytics, evaluation, certificate and control-plane services are used only here. |
| AI copilot (admin) | not run [C] | `routes_api_v1.py:1450-1520`, `auth_jwt.py:188-215` | Session fallback exists; no Gemini key in sandbox. |
| Android app | Webview wrapper [C] | `capacitor.config.json:5-6` | Loads `https://saptha-portal.railway.app`; no native or offline features. |
| Payment failure page | WORKING [R at `1f4cdc8`] | `templates/payment/failed.html:1` | Now extends `base_classic.html`; 200 [R]. |
| Login rate limiting | NOT CONNECTED [C at `56a014d`] | `security_middleware.py:49-110`, `config.py:114` | Per-IP and per-account helpers exist but nothing calls them; `/login` has no limit (BLK-13). |
| Sessions | PARTLY BUILT [C at `56a014d`] | `config.py:52-61` | Files in `/tmp/flask_session`: lost on restart, not shared between instances, pruned past 500 (BLK-08). |
| Database migrations | PARTLY BUILT [R at `56a014d`] | `migrations/versions/`, `db_adapter.py:201-310` | Two incremental migrations; `alembic upgrade head` on an empty DB fails. Schema comes from start-up `create_all` + `ALTER TABLE` (UPG-16). |
| File uploads (certificates, exports) | PARTLY BUILT [C at `56a014d`] | `utils_storage.py:10-94` | Local disk unless `STORAGE_TYPE=s3`/`gcs`; S3 errors silently fall back to local disk (UPG-17). |
| Background jobs | PARTLY BUILT [C at `56a014d`] | `celery_app.py:49-58` | Without a Redis broker, tasks run inline with no timeout or retry (UPG-18); scheduled jobs don't run (UPG-07). |
| Health check | PARTLY BUILT [C at `56a014d`] | `app.py:476-512` | Calls `.stream()` without reading it, so it may not reach the DB; returns exception text (UPG-20). |
| Error monitoring (Sentry) | PARTLY BUILT [C at `56a014d`] | `app.py:124-138` | Initialises when `SENTRY_DSN` is set; untested, not in `.env.example` docs (UPG-20). |
| Database backups | MISSING [C] | — | Nothing in the repo dumps or restores the database (UPG-21). |
| Pagination on web lists | MISSING [C at `56a014d`] | `routes_admin.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_forms.py` | Only `routes_api_v1.py` and `routes_notifications_v2.py` page results (UPG-19). |
| Shared page layout | PARTLY BUILT [C at `56a014d`] | `templates/base_classic.html` | 12 of 129 templates extend it; 110 are standalone pages (UPG-23). |

---

## 3. Journey breakdown per role

*(Traced at `694c729`. BLK-09 fixed several steps here: SPOC creation keeps all settings, coordinator assignment, feedback analytics, the payment failure page, the portfolio. See the inventory rows marked `1f4cdc8`; re-trace a journey before building on it.)*

Traced in code and, where marked, run in the sandbox against three SPOC-created events: **Review Seminar** (seminar template), **Review Hackathon** (team 2–4, judging criterion "Innovation"), **Review Cricket** (sports, ₹200). Seeded universal events were checked too.

### Student

| Step | Result | Where it breaks / leaves the app |
|---|---|---|
| Discover | OK [R] | — |
| Register (solo) | OK for SPOC-created seminar [R]; **broken** for seeded/template forms [R] | Inputs have `name=""` (`registration_form.html:485`). Student falls back to a Google Form. |
| Register (team) | **Broken** [R] | Hackathon form shows only name/email/phone/USN, because `is_team_event` and `limits` were dropped. `/teams/*` isn't linked to registration (`routes_teams.py:92`). Teams are formed on WhatsApp. |
| Pay | **Unsafe** [R] | Cricket fee saved as ₹0 [R]; with the fee restored, `/payment/process` confirmed it for ₹0 [R]. Organisers have to reconcile payments manually. |
| Ticket | OK for new registrations [R] | QR hidden until 1 day before (intended, `routes_ticket.py:143-152`). No payment reference stored. |
| Check-in | **Broken** for camera scans [R] | See Coordinator. |
| Attend sessions | Not found | No session-level attendance. |
| Submit work (hackathon) | Page loads [R] | — |
| See results | OK [R] | Names blank in postgres mode. |
| Feedback | **Broken** [R] | "Unauthorised access." on both routes (`routes_feedback.py:37`, `routes_participant.py:293`). Google Forms used instead. |
| Certificate | **Broken** [R] | Page shows "None"; PDF task TypeError; bulk send blocked. A separate certificate tool is used instead. |
| Portfolio | **Broken** [R] | `/u/<usn>` shows the wrong person. |

### SPOC / organiser

| Step | Result | Where it breaks |
|---|---|---|
| Create event (seminar / hackathon / sports) | Created [R] | Coordinators, team sizes, fee, deadline, ownership lost (postgres). Sports gets no fixtures (MISSING). |
| Build form | Page OK [R] | — |
| Publish (pending → approve → open) | OK [R] | Two steps after approval; not obvious from the UI copy. |
| Manage registrations / waitlist | Partly [R] | Exports have blank identity columns; no waitlist screen. Organisers rebuild the list in Excel. |
| Assign coordinators / judges / rooms | Judges OK [R]; coordinators **broken** [R]; rooms **broken** [R] | `spoc_id` checks at `routes_spoc.py:1186,1508,1546`. |
| Run the day | Manual list check-in only [R] | Camera scans fail; blast email blocked (`routes_spoc.py:972`). WhatsApp groups used instead. |
| Results | Publish OK [R]; lock/advance rounds **broken** [R] | `routes_spoc.py:1651,1672`. |
| Certificates | **Broken** [R] | `routes_spoc.py:1900`, `tasks/cert_tasks.py:44`. |
| Report | AI report blocked (`routes_spoc.py:816`); admin report page loads [R] | IQAC/NAAC report written by hand. |

### Coordinator / volunteer

| Step | Result | Where it breaks |
|---|---|---|
| Get assigned | **Broken** [R] | See SPOC row above. |
| Scan tickets | **Broken** [R] | Coordinator scanner sends the token to `/coordinator/get_ticket/` → "INVALID TICKET". HUD scanner → "Payment pending". |
| Walk-ins | not run [C] | `routes_coordinator.py:665-742`; restricted to `EventCoordinator` role. |
| Attendance (granular) | Works — **for anyone logged in** [R] | `routes_coordinator.py:848-876` has only `@login_required`; a student marked themselves present [R]. |
| Offline | Partly [C] | Queue replays to kiosk confirm, which returns 403 for unassigned coordinators. |

### Judge

| Step | Result | Where it breaks |
|---|---|---|
| See assigned events | **Broken** for new workflow states [R] | `routes_judge.py:59` filters `status == 'active'`. Judge needs a direct link. |
| Score with rubric | **Broken** with form criteria [R]; OK with string criteria [R] | `routes_judge.py:158`. Only attendees marked Present are listed (`routes_judge.py:104-105`), so this depends on check-in. |
| Locking | Blocked [R] | SPOC lock is gated on `spoc_id`. |
| Conflicts of interest | MISSING | No declaration or recusal found. |

### Super Admin

| Step | Result | Where it breaks |
|---|---|---|
| Departments / clubs (org units) | Works, but **first visit locks accounts out** [R] | BLK-07. |
| Approvals | OK [R] | — |
| Users / roles | Role assignment page OK [R]; nav links `/admin/users`, `/admin/events` → 404 [R] | `templates/base_classic.html:57-61`, `templates/admin/audit_log.html:74-75`. |
| Calendar | OK [R] | — |
| Analytics / exports | Pages OK [R]; exports have blank names [R] | BLK-06. |
| Bulk student import | MISSING | UPG-10. |

---

## 4. Event-type coverage

"Works today" is in postgres mode as verified at `694c729`. BLK-09 (`1f4cdc8`) removed most of the BLK-06 field loss these rows depended on; re-check a row before relying on it.

| Event type | Works today | Done outside the app | Needed |
|---|---|---|---|
| Seminar | Create from template, approval, free registration (SPOC-created form), ticket, manual check-in, calendar | Attendance sheet (exports blank), feedback (Google Forms), certificates (separate tool), IQAC report | BLK-06, UPG-01, UPG-02, UPG-03, UPG-05, UPG-06 |
| Workshop | Same as seminar; preset applied (`routes_spoc.py:131`) | Same; paid workshops can't collect fees safely | + BLK-03 |
| Guest lecture | Same as seminar (no own template) | Speaker invite and attendance list | Seminar items |
| Hackathon | Create, judges, project submission page, scoring with string criteria, leaderboard | Team formation (WhatsApp), check-in list, rubric scoring, round shortlists, certificates | UPG-08, UPG-04, UPG-02, UPG-06 |
| Sports | Create, registration (solo only), leaderboard page | Team rosters, fixtures, match results, standings (whiteboard/Excel) | UPG-08, UPG-13 |
| Cultural | Template exists (`services_templates.py:494`); judging as hackathon | Slots, judging sheets, certificates | UPG-04, UPG-06 |
| Club activities | Org units can be clubs (`routes_admin.py:688`) | Membership lists, recurring meetings, attendance across the year | UPG-11 (ledger); membership not yet listed |
| Placement drives | Generic registration only | Eligibility (branch / CGPA / backlogs), shortlists per round, company communication — all Excel | Eligibility rules + shortlist rounds (not in this list; add as next free ID when prioritised) |
| FDPs | Registration creates a **Student** account (`routes_forms.py:415`) | Faculty registration, multi-day attendance, hours on certificate | UPG-12, UPG-11 |
| NSS / NCC | Category collapses to `Technical` in postgres (`db_adapter.py:1233`) | Volunteer hours register, unit rolls, hours certificates | UPG-11, BLK-06 |
| Department events | Department-only visibility (`app.py:984-987`), unit approval [R] | Same as seminar | Seminar items |
| Conference / webinar | Templates exist; seeded forms render empty inputs [R] | External attendee registration | UPG-01, UPG-12 |

---

## 5. Upgrade recommendations

**Order of work:** all BLK items (section 6) come before any UPG item (see `AGENTS.md` rule 2). Within each group, items are ranked by manual work removed for the most people, then by lowest effort.

### A. Finish what's half-built

#### UPG-01 — Registration forms render every template field and always ask for identity
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Template and seeded forms store `field_name` (`services_templates.py` `form_config`; seeded `event_forms` rows), but `templates/public/registration_form.html:405,425,443,485` render `name="{{ field.id }}"`. Inputs get `name=""`, and there's no name or email field, so submissions fail [R]. The SPOC path patches `id` only for its own preset (`routes_spoc.py:252-256`).
- **Who benefits:** every student registering for a seeded or template-created event, plus organisers who otherwise fall back to Google Forms.
- **What to build:** normalise the schema in one place (`_get_form` in `routes_forms.py`) so every field has an `id`; always prepend the identity fields (full_name, email, phone, usn) once; add a check that fails form save if any field lacks an id.
- **Files touched:** `routes_forms.py`, `templates/public/registration_form.html`, `services_templates.py`, tests.
- **Effort:** S · **Depends on:** BLK-02, BLK-06 · **Risk:** low; existing SPOC forms already carry `id`.
- **Acceptance criteria:**
  1. Test: `GET /forms/register/<event from each of the 7 templates>` has no `name=""` input and contains `name="email"` exactly once.
  2. Test: submitting a template form stores the answers and they are read back from `form_submissions` for the responses page.
  3. Test: saving a form with a field that has neither `id` nor `field_name` returns 400.
  4. A student can register for the seeded conference event through the UI.

#### UPG-02 — QR check-in that works with real tickets, for assigned coordinators only
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Three scanners, three broken paths [R]:
  - `templates/coordinator/scan.html:231-234` sends the signed token to `/coordinator/get_ticket/` → "INVALID TICKET".
  - `templates/spoc/scan.html:447-458` sends it to `/spoc/api/checkin/` → 404.
  - `scan_hud` → `/ticket/api/verify` blocks free tickets as "Payment pending" (`routes_ticket.py:479-481`; same gate at `:270-271`).
  - The offline queue replays to kiosk confirm (`static/js/offline-sync.js:83`), which returns 403 because coordinators can't be assigned.
  - Found in BLK-12 [C]: the `/ticket/verify` POST skips the per-event check when the registration's event no longer exists (`if db_exists and event and not can_checkin`, `routes_ticket.py:325`), so any coordinator-level role could mark an orphaned registration present. Deleting an event removes its registrations, so this is rare; the unified endpoint must refuse when the event is missing.
- **Who benefits:** every coordinator and volunteer on event day; removes paper sign-in sheets.
- **What to build:** one check-in endpoint, shared by the coordinator, SPOC and kiosk screens, that accepts the signed token only (`routes_ticket._parse_signed_token`), authorises with `can(session, 'check_in', event)`, applies a payment rule on the normalised status (free/waived/paid, any case), is idempotent, and returns name, team and the first check-in time. Point all three scanners and the offline queue at it. Offline scans queue in the browser (IndexedDB, `static/js/offline-sync.js`, registered by `static/sw.js`) and sync later without duplicates. Make kiosk name search use the corrected keys.
- **Files touched:** `routes_ticket.py`, `routes_coordinator.py`, `routes_spoc.py`, `routes_checkin.py`, `templates/coordinator/scan.html`, `templates/spoc/scan.html`, `templates/coordinator/scan_hud.html`, `templates/public/kiosk.html`, `static/js/offline-sync.js`, `static/sw.js`, tests.
- **Effort:** M · **Depends on:** BLK-04, BLK-06, BLK-12 · **Risk:** event-day critical path; ship behind a test that replays a real ticket token.
- **Acceptance criteria:**
  1. Test: token taken from the ticket page, scanned by the assigned coordinator → attendance `Present`; a second scan → "already checked in at HH:MM" with the first scan's time.
  2. Test: an unassigned coordinator and a student both get 403.
  3. Test: a free registration (`Free` or `free`) is never reported as unpaid; an unpaid paid registration is refused.
  4. Test: replaying an offline queue of 3 tokens marks 3 attendees present; replaying the same queue again changes nothing and reports each as already checked in.
  5. Test: the coordinator, SPOC and kiosk scanner pages all call the same endpoint (template check), and a raw registration ID is refused there.

#### UPG-03 — Exports and an event report with real participant data
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** `/spoc/export_csv`, `/coordinator/export_registrations`, `/forms/responses/export` and `/admin/analytics/export/registrations` all downloaded files with empty name, email, phone and USN columns in postgres mode at `694c729` [R]. The cause (renamed keys) is fixed by BLK-09, so re-run the exports before building; the unified export service and event report are still needed. There is no deterministic post-event report; the AI report is blocked (`routes_spoc.py:816`).
- **Who benefits:** every organiser and HoD; replaces the Excel re-typing and hand-written IQAC/NAAC event reports.
- **What to build:** one export service (CSV and Excel) used by SPOC, coordinator and admin, with columns for name, USN, department, year, email, phone, team, attendance, payment status and amount, score, rank and certificate ID. Each person can export only the events they're allowed to see. Add a one-click event report (XLSX/PDF): registrations vs attendance by department/year, feedback averages, winners. No AI needed.
- **Files touched:** new `services_export.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_admin.py`, `routes_forms.py`, tests.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** PII in exports; keep behind `can(..., 'export_data', event)`.
- **Acceptance criteria:**
  1. Test: exporting an event with 2 registrations (one team, one paid) yields 2 rows with non-empty name, email, phone, team, attendance and payment columns, in both CSV and Excel.
  2. Test: a SPOC of another unit, an unassigned coordinator and a student each get 403 on every export route (SPOC, coordinator, forms, admin).
  3. Test: the event report's attendance count equals the number of `Present` registrations.
  4. An organiser can download the report from the SPOC dashboard.

#### UPG-04 — Judging works for rubric criteria from the create form and for new workflow states
- **Status:** IN PROGRESS (criterion 5 met in `4699478`; 1–4 open)
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** The create form saves criteria as `{name, description, max_score}` (`templates/spoc/create_event.html:1116`). `submit_score` calls `c.replace` (`routes_judge.py:158`) and `score_inline` uses the dict as a key → errors / 500 [R]. The judge dashboard lists only `status == 'active'` (`routes_judge.py:59`), so events in `registration_open`, `in_progress` or `evaluation` never show up [R]. There's no max-score validation. The missing `abort` import in `routes_judge.py` (a pre-existing `master` bug, where an unassigned judge got a swallowed `NameError` instead of a 403) was **fixed in `4699478`** at the owner's request, as part of finishing BLK-09. It's pinned by `tests/test_integration_flow.py::test_unassigned_judge_gets_403_and_nothing_is_saved`.
- **Who benefits:** judges and SPOCs of every competitive event (hackathon, cultural, quiz); removes paper score sheets.
- **What to build:** a single criteria normaliser (strings or objects → `{name, max_score}`) used by every judge route and template; validate `0 ≤ score ≤ max_score`; the dashboard lists assigned events in any judging-relevant state.
- **Files touched:** `routes_judge.py`, `templates/judge/teams.html`, `routes_spoc.py` (results), tests.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: criteria `[{"name":"Innovation","max_score":10}]` → `submit_score` stores 8 and the leaderboard shows 8.
  2. Test: a score of 11 on a max-10 criterion returns 400.
  3. Test: an assigned judge's dashboard lists an event in `in_progress` and in `evaluation`.
  4. Test: scoring after the SPOC locks it returns "locked".
  5. ✅ Test: an unassigned judge gets 403 on `submit_score` and `score_inline`, and nothing is saved (`tests/test_integration_flow.py::test_unassigned_judge_gets_403_and_nothing_is_saved`); `ruff check .` is clean (`4699478`).

#### UPG-05 — Feedback forms that load, save, and feed the report
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** At `694c729` students were told "Unauthorised access." on `/feedback/submit/<reg>` and `/participant/feedback/<reg>`, because both read `lead_email` [R]. Re-checked at `56a014d` [C]:
  - `/feedback/submit/<reg>` is already a 307 redirect to `/participant/feedback/<reg>` (`routes_feedback.py:30-33`, from the BLK-09 merge), so there's one student route. No test pins the redirect.
  - The student route still checks `lead_email` only (`routes_participant.py:293`), so team members can't give feedback. That key now reads back correctly; the route wasn't re-run.
  - It doesn't check that the student attended, and a second POST overwrites the stored `feedback` on the registration (`routes_participant.py:299-340`).
  - `/feedback/view` redirects to `/feedback/analytics`, which returns 200 [R at `1f4cdc8`].
- **Who benefits:** every attendee and organiser; replaces Google Forms feedback.
- **What to build:** feedback that opens only after check-in, one response per person (lead or team member), a SPOC summary page with a CSV export, and an option to require feedback before the certificate is issued.
- **Files touched:** `routes_feedback.py`, `routes_participant.py`, `templates/feedback/*`, tests.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the attendee `GET`s the feedback form → 200, `POST` → saved, read back on `/feedback/view/<event>` (200).
  2. Test: `/feedback/analytics/<event>` returns 200 with 0 and with 3 responses.
  3. Test: a non-owner student gets 403.
  4. Test: `/feedback/submit/<reg>` redirects to the single route (code exists at `routes_feedback.py:30-33`; the test is missing).
  5. Test: an attendee who isn't checked in can't submit; a second submission by the same person is refused and doesn't change the stored response.
  6. Test: the SPOC summary export returns one CSV row per response, for the event owner only.

#### UPG-06 — Certificates generate with the right name and can be issued in bulk
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** (the signature mismatch is re-checked unchanged at `1f4cdc8` [C]; the name and bulk-gate bullets were caused by BLK-06 and are likely fixed, not re-run)
  - `tasks/cert_tasks.py:44-50` calls `generate_certificate_pdf(reg_id=, name=, event_date=, venue=)`, but the signature is `(student_name, event_title, reg_id, cert_type, ...)` (`utils_certificate.py:145`). End-event certificate generation fails with a `TypeError` [R].
  - The certificate page reads `lead_name` (`routes_participant.py:233`) → "presented to None" [R].
  - Bulk send is blocked by `spoc_id` (`routes_spoc.py:1900`).
- **Who benefits:** every attendee; removes the separate certificate tool.
- **What to build:** fix the call signature; one issuing path (end event or button) producing a PDF per attendee with a stored certificate ID and verify URL; emailing on top.
- **Files touched:** `tasks/cert_tasks.py`, `utils_certificate.py`, `routes_spoc.py`, `routes_participant.py`, `routes_verification.py`, tests.
- **Effort:** M · **Depends on:** BLK-06 (was also UPG-05; the "require feedback first" option belongs to UPG-05, so certificates don't wait for it) · **Risk:** PDF rendering on free-tier memory; generate lazily or in small batches.
- **Acceptance criteria:**
  1. Test: ending an event with 2 Present and 1 Absent attendee creates exactly 2 certificates without exceptions (eager Celery).
  2. Test: the certificate page shows the attendee's name.
  3. Test: `/verify/<certificate_id>` shows valid; a random ID shows invalid.
  4. The SPOC "bulk certificates" button succeeds for the event owner.

#### UPG-07 — Reminders and lifecycle jobs run on free-tier hosting
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Reminders, the day-before QR email and lifecycle transitions are Celery beat jobs (`celery_app.py:95-120`). Since BLK-09, `docker-compose.yml:27-37` runs a Celery worker and beat for self-hosting. But the Dockerfile (what a single free-tier web service runs) starts only gunicorn (`Dockerfile:33`), and without Redis Celery runs eagerly (`celery_app.py:51-58`), so beat never runs there. The APScheduler files are unused (`scheduler_enhanced.py:284` has `start()` commented out; neither file is imported by the app).
- **Who benefits:** all registrants, and organisers who now send WhatsApp reminders by hand.
- **What to build:** a protected `POST /internal/cron/<job>` (shared secret header, compared in constant time; 503 when the secret isn't configured) that runs the existing task functions idempotently: reminders, lifecycle transitions, clean-up of expired sessions and old outbox rows, and outbox retries (UPG-18). An external scheduler calls it: Cloud Scheduler on Cloud Run, or a GitHub Actions `schedule` workflow. Document both. Delete the unused schedulers (see UPG-14).
- **Files touched:** new `routes_cron.py`, `app.py`, `tasks/scheduled_tasks.py`, `.github/workflows/cron.yml`, `docs/DEPLOY.md`, tests.
- **Effort:** S · **Depends on:** BLK-05 (tests), BLK-06 (`*_sent` flags persist) · **Risk:** double sends; rely on the existing `*_sent` flags.
- **Acceptance criteria:**
  1. Test: calling without the secret, or with a wrong one → 403; with no secret configured → 503.
  2. Test: `send_24h_reminders` with the secret, for an event tomorrow, sends once; a second call sends nothing.
  3. Test: the lifecycle job moves an event past its end date to `completed`.
  4. Test: the clean-up job deletes expired sessions (BLK-08) and nothing else.
  5. `.github/workflows/cron.yml` exists and targets the endpoint; `docs/DEPLOY.md` shows the Cloud Scheduler set-up.

#### UPG-08 — Team registration linked to tickets and judging
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** The SPOC-created team hackathon form shows only name/email/phone/USN [R], because `is_team_event` and `limits` are dropped and the fallback schema isn't team-aware (`routes_forms.py:328-330`). `/teams/*` writes a separate `teams` collection (`routes_teams.py:92`) that registrations, tickets and judges never read. Members are parsed only from `member_N_*` fields (`routes_forms.py:431-441`).
- **Who benefits:** hackathon, sports and cultural teams; removes WhatsApp team collection.
- **What to build:** team fields generated from `team_min`/`team_max`; create a team, then join by invite code, which adds the member to the same registration; team size limits enforced on the server; the lead manages the team (remove a member, regenerate the code); each member sees the ticket; team check-in marks the members who are present; judges see the team name.
- **Files touched:** `routes_forms.py`, `routes_teams.py`, `routes_ticket.py`, `templates/public/registration_form.html`, `templates/teams/*`, tests.
- **Effort:** M · **Depends on:** BLK-06, UPG-01 · **Risk:** medium; changes the registration record shape.
- **Acceptance criteria:**
  1. Test: a team event with limits 2–4 renders member fields and rejects a 1-member team.
  2. Test: joining by invite code adds the member to `members` and they can open the ticket.
  3. Test: the judge event page lists the team name.
  4. Test: a team at `team_max` rejects another join, even when the browser submits extra member fields.
  5. Test: only the lead can remove a member or regenerate the code; a removed member loses the ticket.
  6. Test: scanning the team ticket with 2 of 3 members marked present records exactly those 2.

#### UPG-09 — Book the venue while creating the event
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Room conflict detection exists (`services_venue.check_room_conflict`), but it runs only on edit (`routes_spoc.py:1122-1128`) and publish (`services_workflow.py:190-218`). The create form has no room field (no `room_id` in `templates/spoc/create_event.html`), so clashes surface late and rooms are booked by email or phone.
- **Who benefits:** SPOCs, the estates/admin office, and anyone who double-books halls.
- **What to build:** a room picker with availability on create; a booking created as tentative on submit and confirmed on approval.
- **Files touched:** `routes_spoc.py`, `templates/spoc/create_event.html`, `services_venue.py`, tests.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: creating an event in a room already booked for an overlapping time → error, no event created.
  2. Test: approval turns the tentative booking into confirmed.
  3. The calendar shows the room name for the event.

### B. New features the university needs

#### UPG-10 — Student roster import and university Google sign-in
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Accounts come only from self sign-up (`routes_auth.py:195-242`) or registration auto-create (`routes_forms.py:405-421`). There's no bulk import (not found). USN is now stored (fixed by BLK-09 [R round-trip at `1f4cdc8`]), but department and year are often blank, so department filters and reports are unreliable. OAuth routes exist, configured via `config.py:205-208`, but at `1f4cdc8` no template links to `/auth/google` or `/auth/microsoft`, and `auth_oauth.py` has no university-domain restriction [C].
- **Who benefits:** every student (one-click login) and every report that needs department/year.
- **What to build:** a SuperAdmin CSV upload (email, name, USN, department, year, section) that creates or updates users. Show a "Sign in with Google" button restricted to the university domain.
- **Files touched:** `routes_admin.py`, `templates/admin/*`, `auth_oauth.py`, `templates/login.html`, `config.py`, tests.
- **Effort:** M · **Depends on:** BLK-06, BLK-02 · **Risk:** account merging for existing emails.
- **Acceptance criteria:**
  1. Test: uploading 3 rows creates 3 users with USN and department read back.
  2. Test: re-uploading updates in place, with no duplicates.
  3. Test: a Google callback with a non-university domain is rejected.
  4. The login page shows the Google button when OAuth is configured.

#### UPG-11 — Participation ledger: activity points and NSS / NCC / FDP hours
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** MISSING. No points or hours fields exist anywhere (searched routes, services and templates for activity points, AICTE, NSS/volunteer/credit hours). Mentors and NSS/NCC officers keep these registers in Excel or on paper.
- **Who benefits:** every student (activity points), NSS/NCC units, faculty (FDP hours), IQAC.
- **What to build:** per-event points and/or hours set by the organiser; credited on attendance; a per-student ledger page; department/unit export; hours printed on certificates.
- **Files touched:** `models_pg.py` + migration, `routes_spoc.py`, `routes_participant.py`, `services_export.py`, `utils_certificate.py`, tests.
- **Effort:** M · **Depends on:** UPG-02, BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: an event worth 2 hours / 5 points credits a Present attendee and not an Absent one.
  2. Test: the ledger totals across 3 events are correct.
  3. Test: the department export lists every student in the department with totals.
  4. The certificate shows the hours when the event has them.

#### UPG-12 — Faculty and external participants (FDPs, guest lectures, conferences)
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Every registrant is created as `Student` (`routes_forms.py:415`, `routes_auth.py:226`). There's no faculty or external participant type (`utils.py:24-36`, `services_permission.py:53-80`), so FDPs and conferences can't be run for their real audience.
- **Who benefits:** HR/IQAC (FDP records), departments running FDPs and conferences, external delegates.
- **What to build:** `participant_type` (student / faculty / external) with designation and institution; the same participant dashboard; FDP certificate wording; analytics split by type.
- **Files touched:** `routes_forms.py`, `routes_auth.py`, `models_pg.py` + migration, `routes_participant.py`, `utils_certificate.py`, tests.
- **Effort:** M · **Depends on:** BLK-02, BLK-06 · **Risk:** role checks assume `Student`.
- **Acceptance criteria:**
  1. Test: a faculty registration creates a user with `participant_type = faculty` who can open their ticket.
  2. Test: the FDP certificate shows designation and institution.
  3. Test: the admin analytics split counts by participant type.

#### UPG-13 — Sports tournaments: fixtures, results, standings
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** The sports template promises "fixture brackets, live match score updates, point tables" (`services_templates.py:399-434`), but no model, route or template builds fixtures or standings. The only mention is a checklist label (`services_event.py:63`). Sports officers run tournaments on whiteboards and in Excel.
- **Who benefits:** Physical Education department, sports clubs, inter-department tournaments.
- **What to build:** a fixture generator (knockout and league) from confirmed teams; coordinator result entry; automatic advancement or points table; a public fixtures page.
- **Files touched:** new `routes_sports.py`, `services_sports.py`, `models_pg.py` + migration, templates, tests.
- **Effort:** L · **Depends on:** UPG-08, BLK-06 · **Risk:** scope creep; start with knockout and league only.
- **Acceptance criteria:**
  1. Test: 8 teams → a knockout with 7 matches; entering results advances the winners to a single champion.
  2. Test: a 4-team league points table is correct after 6 results.
  3. Test: only the assigned coordinator can enter results.
  4. The public fixtures page renders without login.

### C. Remove / merge

#### UPG-14 — Merge duplicate subsystems
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:**
  - **Notifications:** the v1 feed reads `notifications` (`routes_notifications.py:20`), but every writer uses `notifications_v2` (`routes_notifications_v2.py:70`, `services_automation.py:185`, `routes_waitlist.py:96`). The student dashboard feed (`templates/participant/dashboard.html:1758`) is always empty, while the header badge counts v2.
  - **Payments:** Stripe has no UI reference (`routes_payment_stripe.py`).
  - **Schedulers:** `scheduler.py` / `scheduler_enhanced.py` aren't used by the app.
  - **Matchmaker:** `routes_matchmaker.py` suggests mock people (`routes_matchmaker.py:12`). `routes_ai_matching.py` is a different feature (judge↔team) and stays.
  - **Tests:** `tests.py` fails at collection [R] and duplicates `tests/`.
  - **Waitlist promotion (found in BLK-03):** two implementations, `routes_waitlist.auto_promote` (ordered by `position`, no ticket) and `tasks/waitlist_tasks.promote_from_waitlist` (ordered by `joined_at`, issues a ticket, used by the cancel route). BLK-03 made both use `promotion_terms`; merge them into one.
  - **Not duplicates (checked 2026-09-30 at `56a014d`):** `models.py` (91 lines) is the `db` entry point imported by 70 modules, not a copy of `models_pg.py`; keep it. `routes_ai_matching.py` (judge↔team) is a different feature from the matchmaker; keep it.
- **Who benefits:** developers; students get a working notification feed.
- **What to build:** a v2-only notification API and dashboard feed; remove v1, Stripe, both scheduler files and `tests.py`; hide the matchmaker behind a flag until it uses real profiles.
- **Files touched:** `routes_notifications.py`, `templates/participant/dashboard.html`, `app.py`, `routes_payment_stripe.py`, `scheduler*.py`, `routes_matchmaker.py`, `tests.py`.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a notification created with `create_notification` appears in the dashboard feed endpoint.
  2. Test: `/payment/stripe/create_session` → 404.
  3. `grep -r "import scheduler" *.py` finds nothing and `pytest` passes.
  4. Test: `/participant/matchmaker/` → 404 unless the feature flag is on.

#### UPG-15 — Delete dead code and fix dead links
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:**
  - **Unregistered blueprints:** `routes_public.py`, `routes_head.py` and `routes_super.py` (not in `app.py:284-375`), yet live pages link to them: `/event_head/*` from `templates/coordinator/manage_event.html:50` and `/super_admin/*` from `templates/public/home.html:528`.
  - **Dead nav links:** `/admin/users` and `/admin/events` → 404 [R] (`templates/base_classic.html:57-61`); also `/dashboard` and `/settings` (`templates/base_classic.html:43,79`).
  - **Unused files:** about 20 templates are never rendered; `routes_api.py` is empty; `app.py:412` has a debug route.
  - **Broken or risky scripts:** `reset_system.py` imports a nonexistent `Participant` model; `wipe_data.py` deletes all events and registrations with no prompt.
  - **Seed scripts:** 13 `seed_*.py` scripts, 6 of which write directly to Firestore via `firestore.client()`.
  - **Copies:** `scratch/` (26 tracked files); untracked `saptha-event-portal-source*` folders and ~54 MB of zips; `functions/saptha_app/` is a tracked, diverged copy of the app (`app.py` differs by 522 lines) that `catalyst.json` deploys.
  - **Walk-in default password in the `functions/` copy (recorded 2026-09-29, not fixed):** `functions/saptha_app/routes_coordinator.py:645` still sets new walk-in accounts' password to `WALKIN_DEFAULT_PASSWORD` with a published default. The root app uses a random one-time password since BLK-09 (`routes_coordinator.py:688`). **Walk-in accounts created on the Zoho Catalyst deploy (which runs this copy, `catalyst.json`) may still have that password.** The copy does set `needs_password_reset` (`:652`), but its older `db_adapter.py` may drop that flag in postgres mode (as at `694c729`, BLK-06), so the forced reset may never have happened [C]. Owner: check walk-in accounts on that deploy and force resets.
  - **Stale gitlink:** `saptha-event-portal` is a gitlink (mode 160000) with no `.gitmodules`, pointing at a commit of this repo's own old history that no longer exists after the BLK-01 rewrite. It's inert; delete it.
- **Who benefits:** developers and agents (less wrong code to read); users (no 404s).
  - **The `functions/saptha_app` copy also keeps the kiosk and ticket holes the root app fixed** (BLK-12) and the bandit findings (BLK-11).
- **What to build:** remove or merge the above; move `scratch/` tools worth keeping into `scripts/` and delete the rest; fold the seed scripts into one seed command (with BLK-10's guard). For `functions/saptha_app/`: if Cloud Run is the only deploy target, remove it; otherwise generate the Catalyst bundle at deploy time instead of tracking a copy (decision D-1).
- **Files touched:** listed above, plus a new test.
- **Effort:** M · **Depends on:** none · **Risk:** the Zoho Catalyst deploy uses `functions/saptha_app/`; replace it with a build step before deleting.
- **Acceptance criteria:**
  1. Test: parse every template's internal `href`/`action`/`fetch` URL and assert each matches a rule in `app.url_map`.
  2. Test: `/debug-modal` → 404.
  3. `git ls-files` lists no `functions/saptha_app/*.py` and no `seed_*.py` beyond the kept one.
  4. The Catalyst deploy still works via the build step (manual check).
  5. Walk-in accounts created on the Zoho deploy with the old default password have been forced to reset (owner check), and no tracked file sets a default walk-in password (test).

### D. Production setup (added in Phase 0, 2026-09-30)

#### UPG-16 — Alembic baseline: build an empty database through migrations
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:**
  - `migrations/versions/` isn't empty (the plan's prompt said it was): it has two tracked incremental migrations, `0001_add_org_units_and_scoped_roles.py` and `0002_add_campuses_buildings_rooms_bookings.py`. They assume the core tables already exist: `alembic upgrade head` on an empty SQLite database fails with `NoSuchTableError: events` [R at `56a014d`].
  - The real schema comes from start-up code in every environment, production included: `Base.metadata.create_all` (`db_pg.py:171-184`) plus `ALTER TABLE … ADD COLUMN` in `db_pg.py:197` and `db_adapter.verify_and_align_schema` (`db_adapter.py:201-310`, called at `:1757`). Column changes are never recorded, can't be reviewed or rolled back, and race when several instances start together.
- **Who benefits:** whoever deploys and operates the app; every schema change after this.
- **What to build:** one baseline migration matching `models_pg.py` (0001/0002 folded in, or rebased onto the baseline); start-up `create_all`/`ALTER TABLE` only in development; `alembic upgrade head` as a deploy step (a Cloud Run job or the container entrypoint before gunicorn), documented in `docs/DEPLOY.md`. Existing databases get `alembic stamp` instructions.
- **Files touched:** `migrations/versions/*`, `migrations/env.py`, `db_pg.py`, `db_adapter.py`, `Dockerfile` or a deploy script, `docs/DEPLOY.md`, tests.
- **Effort:** M · **Depends on:** BLK-06 (its column changes go into or on top of the baseline) · **Risk:** a baseline that differs from a database created by `create_all`; the comparison test guards it.
- **Acceptance criteria:**
  1. Test: `alembic upgrade head` on an empty SQLite and an empty PostgreSQL database succeeds, and Alembic's `compare_metadata` against `models_pg.Base.metadata` reports no differences.
  2. Test: `alembic downgrade base` then `upgrade head` works on PostgreSQL.
  3. Test: with `FLASK_ENV=production`, app start-up issues no `CREATE TABLE` or `ALTER TABLE` (engine event listener), and refuses to start with a clear message if the database isn't at head.
  4. `docs/DEPLOY.md` shows the migration step and how to stamp an existing database.

#### UPG-17 — Uploads go to object storage and survive restarts
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`]
  - `utils_storage.upload_file` (used for certificates, `tasks/cert_tasks.py:124`, and exports, `tasks/export_tasks.py:187`) writes to `static/uploads/` unless `STORAGE_TYPE` is `s3` or `gcs` (`utils_storage.py:19,74-92`). On Cloud Run the container disk is wiped on restart and not shared between instances, so those files disappear.
  - The S3 branch can't target an S3-compatible service such as Supabase Storage: there's no endpoint setting (`utils_storage.py:29-34`). It uploads with `ACL='public-read'` (`:44`), which would make exported registration lists (names, emails, phones) public.
  - Any S3 or GCS error silently falls back to local disk (`:54-55`, `:71-72`).
- **Who benefits:** every attendee (certificates) and organiser (exports).
- **What to build:** an `S3_ENDPOINT_URL` setting (for Supabase Storage) on the existing S3 path; private objects with short-lived signed URLs for exports (certificates may stay public-readable so the verify page works, or be served through the app); local disk only in development; in production an upload error is an error, never a local write.
- **Files touched:** `utils_storage.py`, `tasks/cert_tasks.py`, `tasks/export_tasks.py`, `config.py`, `.env.example`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low; needs a Supabase Storage bucket and S3 keys for a manual check.
- **Acceptance criteria:**
  1. Test (boto3 client stubbed): with `STORAGE_TYPE=s3` and `S3_ENDPOINT_URL` set, the client is created with that endpoint and the returned URL points at it.
  2. Test: with production config, an S3 failure raises and nothing is written under `static/uploads/`.
  3. Test: exports are uploaded without a public ACL and handed out as signed URLs that expire.
  4. Test: a certificate uploaded through one app instance is readable through a second instance (shared stubbed bucket), and after an app restart.

#### UPG-18 — Background tasks without a broker: inline with timeouts, plus an outbox for retries
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] Without `CELERY_BROKER_URL=redis://…`, Celery runs every task inline in the request (`celery_app.py:49-58`, `task_always_eager`), with no timeout: a slow mail or WhatsApp provider holds the request (and the gunicorn worker). A failed send is logged and lost; nothing retries it. The Cloud Run + Supabase target has no Redis or worker. (Scheduled jobs are UPG-07.)
- **Who benefits:** everyone who waits on a page that sends mail; attendees whose confirmation would otherwise be lost.
- **What to build:** an outbox table (task name, arguments, attempts, next attempt, status, last error); with no broker, tasks run inline under a per-task timeout, and failures or timeouts are stored in the outbox; UPG-07's cron endpoint retries due rows with backoff and a maximum number of attempts. With a broker, behaviour is unchanged. Document both modes.
- **Files touched:** `celery_app.py`, new `services_outbox.py`, `models_pg.py` + migration, `tasks/*`, `docs/DEPLOY.md`, tests.
- **Effort:** M · **Depends on:** UPG-07 (retry trigger), UPG-16 (migration) · **Risk:** sending twice; each task keeps an idempotency key.
- **Acceptance criteria:**
  1. Test: with no broker, a task that raises leaves one outbox row (attempts 1) and the request still succeeds.
  2. Test: a task that runs past its timeout returns control to the request within the limit and is stored for retry.
  3. Test: the retry job sends a stored task once; running it again sends nothing; after the maximum attempts the row is marked failed.
  4. `docs/DEPLOY.md` explains the inline + outbox mode and the broker mode.

#### UPG-19 — Pagination and search on every admin, SPOC and coordinator list
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] Only `routes_api_v1.py` and `routes_notifications_v2.py` read a page or limit parameter (the plan's prompt said 3 route files). The web lists stream whole collections into one page: `.stream()` appears 26 times in `routes_admin.py`, 29 in `routes_spoc.py`, 15 in `routes_coordinator.py` and 6 in `routes_forms.py` (for example users, registrations, form responses, audit log). With a whole university's data these pages will be slow or time out.
- **Who benefits:** admins, SPOCs and coordinators of large events.
- **What to build:** one pagination helper (page, per-page capped at 100, total, next/previous links) with SQL-side limit/offset where the adapter can push it down, and a search box (name, email, USN) on each list. The item lists every covered endpoint when done.
- **Files touched:** new helper, `routes_admin.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_forms.py`, list templates, `db_adapter.py` (offset), tests.
- **Effort:** M (split by area if it grows past ~800 lines) · **Depends on:** BLK-06 (indexed columns) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: each covered list with 120 rows shows 50 by default, and page 3 shows the last 20.
  2. Test: searching by name, email or USN narrows the list; search and page combine.
  3. Test: `per_page=1000` is capped at 100.
  4. Test: the users list issues a SQL `LIMIT` rather than loading every row (query count or compiled SQL check).

#### UPG-20 — Boot checks, health, logs, Sentry and security headers for production
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`]
  - `validate_production_config` collects problems into one error (`config.py:235-249`) but checks only `SECRET_KEY`, `MASTER_SECRET_KEY` and the default admin password. `JWT_SECRET_KEY` silently falls back to `SECRET_KEY` (`config.py:198`); `RAZORPAY_*`, `BASE_URL`, the mail provider and storage settings aren't checked; `DATABASE_URL` is checked separately with its own error (`db_pg.py:104-150`).
  - `.env.example` lists 40 of the 86 environment variables the app code reads; missing ones include `SENTRY_TRACES_SAMPLE_RATE`, `SESSION_TYPE`, `RATELIMIT_STORAGE_URL`, `WTF_CSRF_SECRET_KEY`, `MAIL_*` SMTP settings and `PORT`.
  - `/health` and `/health/ready` call `.stream()` without reading it, so they may not reach the database, and they return the exception text (`app.py:476-512`).
  - Logs are plain text; Cloud Run needs one JSON object per line for severity and request grouping.
  - Sentry is initialised when `SENTRY_DSN` is set (`app.py:124-138`, `send_default_pii=False`), but nothing tests it (the plan's prompt said it wasn't set up).
  - HSTS is sent only when `FORCE_HTTPS` is true (`app.py:215`); on Cloud Run TLS ends at Google's front end, so this needs to be on in production and to trust the proxy's scheme.
- **Who benefits:** whoever deploys and runs the app.
- **What to build:** one production boot check reporting **all** missing or weak settings together (merging the database check); a complete `.env.example`; `/health` running `SELECT 1` and returning no error details; JSON logs in production; a Sentry test; HSTS, `X-Content-Type-Options`, `Referrer-Policy` and frame options in production behind the proxy (`ProxyFix`).
- **Files touched:** `config.py`, `db_pg.py`, `app.py`, `.env.example`, new logging config, tests.
- **Effort:** M · **Depends on:** none · **Risk:** a stricter boot check refuses to start a misconfigured deploy (intended).
- **Acceptance criteria:**
  1. Test: production boot with two required settings missing raises one error naming both; with strong dummy values it starts.
  2. Test: every environment variable read by app code (AST scan) appears in `.env.example`, or in a short allow-list of test-only names.
  3. Test: `/health` returns 503 when the database is unreachable and 200 otherwise; neither body contains exception text.
  4. Test: with production config, a log call produces one JSON object with `severity` and `message`.
  5. Test: with `SENTRY_DSN` set, `sentry_sdk.init` is called with `send_default_pii=False`; without it, it isn't called.
  6. Test: production responses carry HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy` and a frame policy.

#### UPG-21 — Daily database backups and a tested restore
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** MISSING [C]. Nothing in the repo dumps or restores the database (searched for `pg_dump` and backup scripts; the only "backup" hits are 2FA backup codes). Whether the Supabase plan in use keeps its own backups isn't known; don't rely on it.
- **Who benefits:** the university (every record of every event).
- **What to build:** `scripts/backup_db.sh` (`pg_dump -Fc` to a private bucket, dated names, retention), run daily by the external scheduler (Cloud Scheduler + a Cloud Run job, or GitHub Actions); `scripts/restore_db.sh`; a documented restore drill. Dumps are never committed.
- **Files touched:** `scripts/backup_db.sh`, `scripts/restore_db.sh`, `.gitignore`, `tests/test_repo_hygiene.py`, `docs/DEPLOY.md`, tests.
- **Effort:** S · **Depends on:** UPG-17 (bucket settings) · **Risk:** a dump holds all personal data; the bucket must be private and access-limited.
- **Acceptance criteria:**
  1. Test: the backup script against a test PostgreSQL produces a dump; restoring it into an empty database gives the same row counts per table.
  2. Test: the hygiene test fails if a `*.dump`, `*.sql`, `*.sql.gz` or `*.backup` file is tracked.
  3. `docs/DEPLOY.md` documents the schedule, retention, bucket permissions and the restore drill.

#### UPG-22 — Privacy notice, consent at registration, working data export and deletion
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] `routes_compliance.py` has data export (`:50`), deletion request (`:126`), cancel deletion (`:188`) and consent (`:211`, `:250`) endpoints, never run end to end. The registration form has no consent checkbox (no "consent" in `templates/public/registration_form.html`). The privacy page is linked from only 5 templates, because pages don't share a footer (UPG-23).
- **Who benefits:** every student and external participant; the university's DPDP obligations.
- **What to build:** a privacy notice linked from the shared footer; a required consent checkbox at registration and sign-up, stored with the time and notice version; a working export (the user's own data as a download) and deletion (account removed, registrations anonymised, kept only where records must be retained).
- **Files touched:** `routes_compliance.py`, `routes_forms.py`, `routes_auth.py`, `templates/public/registration_form.html`, the shared layout, tests.
- **Effort:** M · **Depends on:** BLK-02, UPG-23 (footer) · **Risk:** what must be kept (e.g. certificates, finance records) is a policy question; record it under "Decisions needed" if it blocks.
- **Acceptance criteria:**
  1. Test: registration without consent → refused with a clear message; with consent → stored with time and notice version.
  2. Test: export returns the user's profile and registrations and nothing about anyone else.
  3. Test: after deletion is processed, the user can't log in and their registrations hold no name, email or phone.
  4. Test: every page on the shared layout links the privacy notice.

### E. Frontend (added in Phase 0, 2026-09-30)

#### UPG-23 — Every page on one shared layout (split by area: UPG-23a–h)
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`, counted with a script] Of 129 templates, 12 extend `base_classic.html`, 1 extends `coordinator/base.html`, which doesn't exist (`templates/coordinator/view_scores.html`; nothing renders it, UPG-15), 5 are partials, and **110 are standalone pages** with their own `<head>`, CDN tags and navigation (the plan's prompt said 108 of 126 and ~13). So fixes to navigation, CSP, fonts, footer or loading states have to be made 110 times.
- **Who benefits:** every user (consistent navigation, mobile layout); every later frontend item.
- **What to build:** a role-aware shared layout (extend `base_classic.html`, with blocks for per-role navigation, and a minimal child layout for full-screen pages such as the kiosk, scanners and printable certificate). Move pages one area at a time, one commit each: 23a public, 23b participant, 23c teams/profile/payment, 23d SPOC, 23e coordinator, 23f judge, 23g admin, 23h marketing. Keep the existing design tokens in `static/css/global.css`; no redesign. Where a headless browser is available, screenshot each area's key pages at 375px and 1280px before and after.
- **Files touched:** `templates/**`, `templates/base_classic.html`, tests.
- **Effort:** L (8 sub-items) · **Depends on:** none (UPG-24/25 get easier after it) · **Risk:** lost page-specific CSS or scripts; the screenshot comparison and page tests guard it.
- **Acceptance criteria (per sub-item, for its area):**
  1. Test: every template in the area that is rendered by a route extends the shared layout (or its minimal child).
  2. Test: each key page returns 200 for its role and contains the shared navigation and footer landmarks.
  3. At 375px no key page scrolls horizontally, and no content is lost compared with the before-screenshot (headless check, when available).
  4. No URL changes.

#### UPG-24 — One Bootstrap version and one font set, loaded once, with SRI
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] Bootstrap 5.3.0 is loaded by 50 templates and 5.3.3 by 34. Google Fonts families: Inter (29 templates), Poppins (27), Plus Jakarta Sans (4), Cinzel (3), Orbitron (1), Outfit (1), while `static/css/global.css` uses Inter, Plus Jakarta Sans and Outfit (`global.css:189,201,897`). Of 261 CDN `<script>`/`<link>` tags, 2 have an `integrity` hash.
- **Who benefits:** every user (one download, consistent look); security (SRI).
- **What to build:** Bootstrap 5.3.3 and the font set `global.css` uses, loaded once in the layout, with `integrity` and `crossorigin` on every CDN file.
- **Files touched:** `templates/base_classic.html`, templates still carrying their own tags, tests.
- **Effort:** S (after UPG-23) · **Depends on:** UPG-23 · **Risk:** pages relying on 5.3.0 quirks or on Poppins; check in screenshots.
- **Acceptance criteria:**
  1. Test: no template references `bootstrap@5.3.0`; Bootstrap CSS and JS appear only in the layout files.
  2. Test: every CDN `<script>` and stylesheet `<link>` has `integrity` and `crossorigin`.
  3. Test: only the font families used by `global.css` are requested.

#### UPG-25 — Move inline scripts into static files; remove `'unsafe-inline'` from `script-src`
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] 72 templates contain inline `<script>` blocks, and 77 templates contain 489 inline event handlers (`onclick=` and similar). So the CSP's `script-src` allows `'unsafe-inline'` (`app.py:203`), which removes most of its protection against injected scripts; `content_security_policy_nonce_in=[]` (`app.py:218`).
- **Who benefits:** every user (XSS protection).
- **What to build:** page scripts in `static/js/`; event handlers bound with `addEventListener`; a per-request nonce (`content_security_policy_nonce_in=['script-src']`) for anything that must stay inline (e.g. a small JSON bootstrap); then remove `'unsafe-inline'` from `script-src`.
- **Files touched:** `templates/**`, `static/js/**`, `app.py`, tests.
- **Effort:** L (split by area like UPG-23) · **Depends on:** UPG-23 · **Risk:** a missed handler breaks a button; a headless click-through catches CSP violations.
- **Acceptance criteria:**
  1. Test: the CSP header's `script-src` has no `'unsafe-inline'`.
  2. Test: no template has an inline `<script>` without the nonce, and no inline `on*=` handler.
  3. Key pages load with no CSP violation in the browser console (headless check, when available).

#### UPG-26 — Forms: visible labels, clear errors, a loading state and one submit per click
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] The only double-submit guard is the "button loading state" in `static/js/global.js:208-225`, and only 25 of 129 templates load `global.js`; the payment pages `payment/checkout.html` and `public/payment_gateway.html` don't. The guard also re-enables the button after 15 seconds. Labels and error messages haven't been checked across forms.
- **Who benefits:** every user, especially on slow mobile networks (double registrations, double payments).
- **What to build:** the submit guard in the shared layout for every form (payment buttons stay disabled until the result arrives); a visible label for every input; field-level error messages from the server; server-side idempotency for registration submits.
- **Files touched:** `static/js/global.js`, the layout, form templates, `routes_forms.py`, tests.
- **Effort:** M · **Depends on:** UPG-23 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: every page with a `<form>` loads the submit guard (through the layout).
  2. Test: every visible input, select and textarea has a `<label for>` or `aria-label`.
  3. Test: posting the same registration twice quickly creates one registration.
  4. The payment button is disabled after one click until the payment result arrives (headless check, when available).

#### UPG-27 — Images: compress, lazy-load, alt text; visible keyboard focus
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] `static/img` is 4.5 MB in 7 files: `event_slide1–4.png` are 0.8–1.06 MB each, `feature-showcase.png` 0.6 MB, `hero-banner.png` 0.39 MB. Of 111 `<img>` tags in templates, 4 have no `alt` and 77 have no `loading` attribute. Keyboard focus styles haven't been checked.
- **Who benefits:** students on mobile data; keyboard and screen-reader users.
- **What to build:** compressed images (WebP where it helps, same dimensions and look); `loading="lazy"` below the fold; `alt` on every image; a visible `:focus-visible` style in `global.css` that uses the existing tokens.
- **Files touched:** `static/img/*`, templates, `static/css/global.css`, tests.
- **Effort:** S · **Depends on:** UPG-23 (fewer places to edit) · **Risk:** low.
- **Acceptance criteria:**
  1. `static/img` totals under 1.5 MB.
  2. Test: every `<img>` in templates has `alt`; every image outside the first screen has `loading="lazy"`.
  3. Test: `global.css` defines a `:focus-visible` style.

#### UPG-28 — The student journey and the scanner work on a 375px phone
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Not verified. Nobody has checked discover → register → pay → ticket → check-in → feedback → certificate, or the scanner pages, at phone width. `MOBILE_UX_PLAN.md` exists, but its claims weren't checked. No headless browser is set up in the repo.
- **Who benefits:** students (most use phones) and coordinators scanning on phones.
- **What to build:** a Playwright (Chromium) check, as a dev dependency, that walks the student journey and opens the scanner at 375×812 and 1280×800 with seed data, checks for horizontal scroll, and saves screenshots outside git; fix what it finds.
- **Files touched:** `tests/e2e/` (or `scripts/`), `requirements-dev.txt`, templates/CSS as needed.
- **Effort:** M · **Depends on:** UPG-23, UPG-26 · **Risk:** the browser download needs network access in CI.
- **Acceptance criteria:**
  1. Headless check: every journey page at 375px has `document.documentElement.scrollWidth <= innerWidth`.
  2. Headless check: the scanner page loads at 375px with the camera mocked and a token can be submitted.
  3. The phase report includes the 375px and 1280px screenshots.

### F. Event-day flows and release (added in Phase 0, 2026-09-30)

Phase 2 flows that existing items already cover: check-in (UPG-02), certificates (UPG-06), exports (UPG-03), team events (UPG-08), feedback (UPG-05). The items below cover the rest.

#### UPG-29 — Coordinator and judge assignment by a SPOC, end to end
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Assignment works since BLK-09 (`routes_spoc.py:1171-1252` coordinators, `:1379-1435` judges), and one test covers the SPOC assigning a coordinator (`tests/test_integration_flow.py:166-186`). Not tested: judge assignment, unassigning, a SPOC trying to assign on someone else's event, and the assigned person seeing the event on their dashboard.
- **Who benefits:** SPOCs, coordinators and judges.
- **What to build:** tests first; fix whatever they find (e.g. unassign doesn't remove access).
- **Files touched:** `routes_spoc.py`, tests.
- **Effort:** S · **Depends on:** BLK-04 · **Risk:** low.
- **Acceptance criteria:**
  1. Test (real DB): the SPOC assigns a coordinator and a judge on their own event; each sees it on their dashboard.
  2. Test: another SPOC gets 403 and nothing changes.
  3. Test: unassigning removes access to the event's registrations and scoring.

#### UPG-30 — Paid events end to end: receipt email, refunds and cancellations
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] After a verified payment only a WhatsApp receipt task is queued (`routes_payment.py:241`); there's no email receipt. There's no admin action to mark a payment refunded or a paid registration cancelled; `services_finance.py:249-264` only counts `refunded` in reports. BLK-03 makes verification safe; this item makes the whole flow work.
- **Who benefits:** the finance office, organisers and paying participants.
- **What to build:** a receipt email (Brevo) after a verified payment; admin actions to mark a registration refunded or cancelled (with reason, audit-logged), which also stop its ticket from checking in; a finance export row per payment.
- **Files touched:** `routes_payment.py`, `routes_admin.py`, `utils_email.py`, templates, tests.
- **Effort:** M · **Depends on:** BLK-03, BLK-05 · **Risk:** needs Razorpay test keys for the manual check.
- **Acceptance criteria:**
  1. Test (Razorpay client mocked): register → order → verify gives `Confirmed / Paid` with the server amount and queues exactly one receipt email.
  2. Test: an admin marks the registration refunded, then another cancelled; each is audit-logged, and the ticket is refused at check-in.
  3. Test: a non-admin gets 403 on both actions.
  4. Manual (owner, with Razorpay test keys): the full checkout in test mode.

#### UPG-31 — Notifications: confirmation, day-before reminder, change and cancellation notices through Brevo
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** [C at `56a014d`] Confirmation (`utils_email.send_registration_confirmed_email`, `utils_email.py:439`) and cancellation notices (`services_workflow.py:287-322`, idempotent per email) exist. The day-before reminder is a Celery beat job that doesn't run (UPG-07). There's no notice when an event's date, time or venue changes. In-app notifications are split between v1 and v2 (UPG-14).
- **Who benefits:** every registrant.
- **What to build:** a notice to all registrants when date, time or venue changes; the reminder through UPG-07's cron; every email through `utils_email` (Brevo first), each sent once (idempotency key), and never sent from tests.
- **Files touched:** `routes_spoc.py` (edit event), `services_workflow.py`, `tasks/scheduled_tasks.py`, `utils_email.py`, tests.
- **Effort:** S · **Depends on:** UPG-07, BLK-05 (UPG-18's outbox adds retries later but isn't required) · **Risk:** double sends; idempotency keys guard it.
- **Acceptance criteria:**
  1. Test: a registration sends one confirmation through the Brevo client (HTTP mocked) with the event's details.
  2. Test: the day-before reminder, run twice through the cron endpoint, sends once per registrant.
  3. Test: changing an event's venue notifies every registrant once; cancelling notifies once.
  4. Test: with no mail keys configured (tests), nothing is sent over the network.

#### UPG-32 — Release check and `docs/DEPLOY.md`
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** There's no deploy guide for Cloud Run + Supabase, and no end-to-end release check from a fresh clone. `README.md` describes Railway/Render deploys.
- **Who benefits:** whoever deploys and runs the app.
- **What to build:** the Phase 6 release check (fresh clone → `docker-compose up` → `alembic upgrade head` on an empty PostgreSQL → non-production seed → every role end to end at 375px and 1280px; production boot with strong dummy settings, then with one missing; restart mid-session and two instances; full pytest on SQLite and PostgreSQL, ruff, bandit, pip-audit, full-history gitleaks) and `docs/DEPLOY.md`: Cloud Run + Supabase set-up, every setting and how to generate it, the migration step, first Super Admin creation, rollback (redeploy the previous revision), backups and restore, monitoring.
- **Files touched:** `docs/DEPLOY.md`, `README.md` (link), this review (final report).
- **Effort:** M · **Depends on:** every other item in phases 1–5 · **Risk:** none.
- **Acceptance criteria:**
  1. Each release-check step above passes, with its output recorded in the changelog.
  2. `docs/DEPLOY.md` covers every topic listed.
  3. The final report lists every item's status, anything not DONE and why, and a go-live checklist.

---

## 6. Blockers — fix before building new features

Ranked by exposure and urgency. Kept short; a separate security pass will go deeper.

### Before the next deploy (checklist)

There's **no production deployment today** (owner, 2026-09-30: the Cloud Run free tier ended). Set every value below in the host's secret settings **before the first deploy**. Use new values, never ones used before (the old admin password and master key are public), and never put them in git (`tests/test_repo_hygiene.py` and the CI secret scan block that).

Generate each secret with: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.

| Setting | Requirement | Checked by the app at start-up? |
|---|---|---|
| `FLASK_ENV` | `production` | This is what turns the production checks on |
| `SECRET_KEY` | New random value, 32+ characters | Yes: start-up is refused otherwise (`config.py:35-39`, `validate_production_config`) |
| `MASTER_SECRET_KEY` | New random value, 12+ characters, not a published value | Yes (`validate_production_config`) |
| `JWT_SECRET_KEY` | New random value, different from `SECRET_KEY` | **No**: it silently falls back to `SECRET_KEY` (`config.py:198`) |
| `SUPER_ADMIN_PASS` (with `SUPER_ADMIN_EMAIL`) | New strong password, used to create the first SuperAdmin | Only against the list of published passwords (`validate_production_config`) |
| `RAZORPAY_KEY_SECRET` (with `RAZORPAY_KEY_ID`) | Set before any paid event is opened | **No**, but without them online payment refuses with 503 (fails closed since BLK-03). Never set `PAYMENT_SIMULATION` in production (it's ignored there anyway). |
| `DATABASE_URL` | PostgreSQL (`postgresql://…`) | Yes: production refuses SQLite or no database (`db_pg.py:104-150`) |

- **Use a fresh database.** If an old one is reused (the earlier Cloud SQL or Supabase database), first reset every account's password (the SuperAdmin's was the published demo password) and delete the demo accounts (BLK-10) and walk-in accounts created with the default password (UPG-15).
- **Check:** start the app once with these values and `FLASK_ENV=production`. It must start, and it must refuse to start if any start-up-checked value above is missing or weak (`tests/test_integration_flow.py::test_production_config_requires_real_secrets`).


#### BLK-01 — Admin credentials and a user database are in the public GitHub history
- **Status:** IN PROGRESS
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:**
  - The repo is public (the GitHub API returns 200 unauthenticated; 0 forks).
  - **Removed from all local history on 2026-09-29 (not pushed yet):**
    - `saptha_fallback.db`: 42 users, 41 password hashes, phones, 70 registrations; the unpushed commits had added one more real user.
    - `.env`: added `1db93ca`, changed `bb19dae`, deleted `04df1c0`.
    - `dataconnect/.dataconnect/`: a full PGlite/PostgreSQL data folder of 1,023 files with real email addresses, plus generated schema; added `328fb0b`, changed `7f4e6c3`, and tracked at HEAD until now.
    - `instance/event_portal.db`: a SQLite DB with 1 super-admin and 2 SPOC accounts (`45c24cc`, `04df1c0`).
    - 69 `__pycache__/*.pyc` files; the compiled config held today's SuperAdmin password and master key.
    - Every commit's tree was checked to equal its old tree minus exactly these paths. See the changelog for 2026-09-29.
  - **Variable names in the removed `.env` versions** (2 versions, the same 7 names, all set): `BASE_URL`, `GEMINI_API_KEY`, `MAIL_PASS`, `MAIL_USER`, `MASTER_SECRET_KEY`, `SUPER_ADMIN_EMAIL`, `SUPER_ADMIN_PASS`. Secrets among them:
    - `MAIL_PASS`: **two different values** (app passwords of the old `MAIL_USER` account, which differs from today's).
    - `GEMINI_API_KEY`: one old key, not today's.
    - `SUPER_ADMIN_PASS` and `MASTER_SECRET_KEY`: the same as today's values.
    - `SUPER_ADMIN_EMAIL`, `MAIL_USER` and `BASE_URL` are identifiers, not secrets.
  - **Still in history, not removable without `--replace-text`** (which the owner chose not to use; rotating instead), from a full-history gitleaks scan [R] plus a value match [R]:
    - **Two different Google API keys** hard-coded in `chatbot_routes.py`, in commits `2ffe545` (2026-03-12) and `477cec4` (2026-03-08). The first is the old `.env` `GEMINI_API_KEY`; **the second matches no `.env` value, so it's a separate key to revoke.** Neither is at HEAD.
    - The Supabase publishable (public-by-design) key and project URL in an old `.env.example` (`38068e4`).
    - Today's `SUPER_ADMIN_PASS` / `MASTER_SECRET_KEY` as literals in older `.env.example`, `README.md`, `fix_admin.py`, `routes_auth.py`, `init_superadmin.py` and `config.py` versions. The password is **also at HEAD**: it's the demo password in `seed_all_roles_demo.py`, `seed_demo.py`, `init_zoho_db.py` and `scratch/set_admin_password.py` (BLK-10). The master key is at HEAD in `config.py` (blocklist) and a test.
    - The walk-in default password in `functions/saptha_app/routes_coordinator.py:645` at HEAD (recorded under UPG-15).
    - Not a problem: a CI step's dummy service-account JSON (`sapthagiri_app/static/uploads/.github/workflows/pipeline.yml`); fake `98765…` phone numbers in seed scripts; test-only secrets and one report-table false positive (baselined in `.gitleaksignore`). There are no CSV/XLSX/SQL exports, private keys, real service-account JSON or other API keys anywhere.
  - **GitHub pull-request refs keep removed files after the force-push**, and repo owners can't delete them (only GitHub Support can). By PR number, all **47** PR refs contain at least one removed file [R, read-only fetch of GitHub's refs]:
    - PRs **#1–#5**: `instance/event_portal.db`, `__pycache__/*.pyc`.
    - PRs **#6–#47**: `.env`, `instance/event_portal.db`, `__pycache__/*.pyc`.
    - None contains `saptha_fallback.db` or `dataconnect/.dataconnect/`.
    - The remote branches `master` (all five paths), `main` (`.env`, `instance/`, `.pyc`) and `claude/busy-davinci-6nkabi` (all five) contain them too; the force-push and branch deletion fix those.
    - There are 0 commits reachable only from PR refs, so the PR refs add no content beyond the scanned branch history.
  - **Mitigation from BLK-09:** `config.validate_production_config` (`app.py:145`) refuses to start production with a published default. Both leaked values are on its blocklist [C]. A SuperAdmin account already created with the leaked password keeps it in the database.
- **Who benefits:** everyone whose account or data is exposed.
- **What to build:**
  - **Done locally:** backups; history rewrite; `.gitignore` rules; `tests/test_repo_hygiene.py`; CI job "Repo hygiene & secret scan" (the hygiene test plus a pinned gitleaks 8.30.1 full-history scan, with accepted findings in `.gitleaksignore`). **The two Google API keys are deliberately not accepted, so the secret-scan step fails until they're revoked**; their fingerprints are commented out in `.gitleaksignore`, ready to un-comment.
  - **No deployment exists** (owner, 2026-09-30), so pushing can't trigger a production start. The first deploy must follow **"Before the next deploy"** at the top of this section.
  - **Owner, now:** force-push and delete the remote branches (commands in the 2026-09-29 changelog entry).
  - **Owner, now:** ask GitHub Support to remove the PR refs' copies and cached views of old commits, sending the PR numbers above and `.git/commit-map-github-to-final.txt` (original → new hashes).
  - **Owner, done 2026-09-30:** changed the old mail account's password (which also revokes its app passwords, so both leaked `MAIL_PASS` values are dead) and revoked both Google API keys (the old `GEMINI_API_KEY` and the second key).
  - **Owner, replaced by the checklist:** `SUPER_ADMIN_PASS` and `MASTER_SECRET_KEY` aren't in use anywhere, since there's no production. The next deploy must use new values ("Before the next deploy").
  - **Owner, still open:** the Supabase publishable key (only if that project is still used); collaborators re-clone after the push.
- **Files touched:** `.gitignore`, `.github/workflows/ci.yml`, `.gitleaksignore`, `tests/test_repo_hygiene.py`; history rewrite; operational steps outside the code.
- **Effort:** S · **Depends on:** none · **Risk:** the force-push breaks existing clones; old objects stay on GitHub (PR refs, cached views) until Support removes them.
- **Local artifacts (never push or commit):**
  - `~/saptha-event-portal-backup-2026-09-29.git`: the original history.
  - `~/saptha-event-portal-backup-2026-09-29-before-purge2.git`: after the first rewrite.
  - `~/saptha-local-data/saptha_fallback.db` and `~/saptha-local-data/dataconnect-.dataconnect/`: local dev data, owner-only permissions.
  - `.git/commit-map-github-to-final.txt`.
  - Delete the backups and data copies once the push is confirmed; prefer the seed scripts for local data.
- **Acceptance criteria:**
  0. ✅ **Met locally:** no local commit contains `saptha_fallback.db` or the other removed paths. ⬜ **Not yet on GitHub:** as of 2026-09-30, `git ls-remote` still shows `master` at the old `c6080f5` and the old branches `main` and `claude/busy-davinci-6nkabi`; the last push was 2026-09-26. Completes after the force-push, branch deletion and GitHub Support's PR-ref clean-up. Re-checked in Phase 0 (2026-09-30, read-only `git ls-remote`): unchanged. **Waits on the owner; doesn't block other items.**
  1. ✅ **Met:** `tests/test_repo_hygiene.py::test_no_forbidden_files_are_tracked` fails if any `*.db`, `*.sqlite*`, `.env*` (other than `.env.example`), service-account key, `*.pyc` / `__pycache__/`, `dataconnect/.dataconnect/` or `instance/` file is tracked. It passes at `08eabf5`.
  2. ✅ **Met:** the CI job "Repo hygiene & secret scan" runs that test and the gitleaks scan. Demonstrated on a throwaway branch in a scratch clone: a commit adding `.env`, `local.db`, a `.pyc` and a fake AWS-style key made the test fail (1 failed, naming the 3 files) and gitleaks exit 1 [R].
  3. ✅ **Met for now: there's no production deployment** (owner, 2026-09-30), so nothing accepts the old SuperAdmin password or master key. The next deploy must pass **"Before the next deploy"** (new `SECRET_KEY`, `MASTER_SECRET_KEY`, `JWT_SECRET_KEY`, `SUPER_ADMIN_PASS`, `RAZORPAY_KEY_SECRET`, and a PostgreSQL `DATABASE_URL`, all set first). The start-up refusal for published values exists (`tests/test_integration_flow.py:221`).
  4. ✅ **Met locally:** both Google API keys are revoked (owner, 2026-09-30) and accepted in `.gitleaksignore`. The full-history gitleaks scan finds **no leaks in 212 commits** [R]. ⬜ **CI not yet confirmed green on GitHub**, because the commits haven't been pushed (criterion 0). Once pushed, the secret-scan step should pass; the separate bandit job will still fail until BLK-11 is fixed. The old password and master key remain as literals in history (gitleaks doesn't flag them); they're unused and must not be reused (criterion 3).

#### BLK-02 — The public registration form logs the visitor in as any email they type
- **Status:** DONE
- **Last verified:** 2026-09-30, commit "BLK-02: …" on `production-ready` (parent `07ad7b2`)
- **Problem (as found):** `submit_form` set `session['user_id']` to the submitted email (`routes_forms.py:598` at `56a014d`; waitlist branch `:517`), and so did payment completion (`routes_payment.py:251`) and the legacy public registration route (`routes_participant.py:518`, found while building). There was no password check for existing accounts. At `694c729`, an anonymous visitor submitted the hackathon form as `student@demo.com` and landed on that student's profile and dashboard [R]. The generated password was kept in the session (`routes_forms.py:610`) and emailed (`routes_forms.py:580`, `routes_participant.py:517`).
- **Who benefits:** every student account.
- **What was built:**
  - `services_accounts.py`: `resolve_registrant` (`:37`) returns the session email for a logged-in visitor, or a login redirect back to the form when an anonymous visitor types an existing account's email; `create_unverified_account` (`:56`) makes a Student account with a random, never-shown password hash and `email_verified: False`; one-time set-password tokens (`:71-90`, 3 days, bound to the current password hash so they stop working once used); `send_set_password_link` (`:93`); `is_safe_next` (`:108`).
  - `routes_forms.submit_form`: a logged-in visitor's email replaces the form's (`routes_forms.py:373-378`); the closed check runs first, then an existing account is sent to log in (`:387-407`); a new email gets an unverified account and a set-password email (`:421-426`); both auto-logins and the stored/emailed password are gone; the waitlist redirect no longer assumes a login (`:512`).
  - `routes_payment`: completion never logs in (`routes_payment.py:250`); `_after_payment_url` (`:263`) sends the logged-in owner to the ticket and anyone else to the confirmation page.
  - `routes_participant.public_register` follows the same rules (`routes_participant.py:371-386,454,457-461`).
  - `/set_password/<token>` (`routes_auth.py:203`) sets the password once, marks the email verified and logs in; login honours a same-site `next` (`routes_auth.py:30-34,149`) so "log in first" returns to the form; `templates/login.html` carries `next`.
  - `utils_email.send_set_password_email` (`utils_email.py:659`); the confirmation page shows where the link went and never a password (`templates/participant/registration_confirmed.html`, `app.py:932`).
  - Tests: the `real_app` fixture moved from `tests/test_integration_flow.py` into `tests/conftest.py` unchanged, except that it now also stubs `utils_email._send` so no test sends mail. Two tests in `tests/test_seminar_e2e.py` submitted students' forms from the SPOC's logged-in session, relying on this hole; they now submit from each student's own session (`_as_student`), with every assertion unchanged.
- **Files touched:** `services_accounts.py` (new), `routes_forms.py`, `routes_payment.py`, `routes_participant.py`, `routes_auth.py`, `utils_email.py`, `app.py`, `templates/login.html`, `templates/participant/registration_confirmed.html`, `tests/test_registration_no_auto_login.py` (new), `tests/conftest.py`, `tests/test_integration_flow.py`, `tests/test_seminar_e2e.py`.
- **Effort:** S · **Depends on:** none · **Risk:** existing students must now log in before registering; new students must use the emailed link before they can see their dashboard or ticket.
- **Acceptance criteria** (all in `tests/test_registration_no_auto_login.py`, on the real SQL adapter; each fails on the old code except the off-site `next` check):
  1. ✅ An anonymous submit with an existing student's email → no `user_id` in the session, a redirect to `/login?next=/forms/register/<event>`, no registration and no email; logging in returns to the form; an off-site `next` is ignored (`test_anonymous_submit_with_existing_email_must_log_in_first`, `test_login_ignores_an_off_site_next`).
  2. ✅ A logged-in student submitting a different email → the registration and its answers use the session email, and no account is created for the other email (`test_logged_in_student_registers_under_the_session_email`).
  3. ✅ The waitlist branch, `/payment/process` and `/payment/verify` (Razorpay client faked, correctly signed) never set the session (`test_waitlist_branch_never_logs_in`, `test_simulated_payment_completion_never_logs_in`, `test_verified_razorpay_payment_never_logs_in`).
  4. ✅ `/registration/confirmed`, the session and every email contain no password (`test_no_password_is_shown_stored_in_the_session_or_emailed`).
  5. ✅ A new email gets an unverified account and exactly one set-password link; nobody can log in before it's used; the link sets the password once and logs in; a reused, expired (4 days old) or tampered link is refused (`test_new_email_gets_an_account_and_a_one_time_set_password_link`, `test_expired_or_tampered_set_password_link_is_refused`). The legacy route passes the same checks (`test_legacy_public_register_route_never_logs_in`).
  - Full pytest: **424 passed, 1 xfailed** on SQLite and on PostgreSQL 16; `ruff check .` clean.

#### BLK-03 — Paid events can be completed without paying
- **Status:** DONE (manual check with Razorpay test keys waits on the owner; see UPG-30 criterion 4)
- **Last verified:** 2026-10-01, commit "BLK-03: …" on `production-ready` (parent `5c8c044`)
- **Problem (as found at `56a014d`):** BLK-09 fixed two prerequisites: the event fee now persists (₹500 stored as `entry_fee` 500 and `fees.regular` 500 [R]), and the CSP no longer blocks Razorpay checkout (`app.py:205-209`). The checks themselves are unchanged (`git diff 694c729 1f4cdc8 -- routes_payment.py` only adds form-answer recording).
  1. **Simulation endpoint always on.** `/payment/process` (`routes_payment.py:269-290`) completes any pending registration with a client-supplied amount; a ₹200 registration was confirmed for ₹0 [R at `694c729`].
  2. **Empty-key signature accepted.** When `RAZORPAY_KEY_SECRET` is unset, `/payment/verify` computes `HMAC('', order_id|payment_id)` (`routes_payment.py:34,112-118`), so anyone can produce a valid signature. On `1f4cdc8`, a forged signature with fake order/payment IDs confirmed a ₹500 registration as `Confirmed / Paid / ₹1` with payment ID `pay_FAKE456` [R].
  3. **Order not tied to the event or its fee.** The signature covers only `order_id|payment_id`. `verify_payment` never fetches the order from Razorpay, takes `event_id` from the request body (`routes_payment.py:110`) and records `amount_inr` from the browser (`routes_payment.py:125`). So even with a real secret, one genuine low-value payment (e.g. an order for a cheaper event, or a replayed payment) confirms any event at any claimed amount [C]. `create_order` writes `event_id` into the order notes (`routes_payment.py:88`), but nothing reads them back.
  4. **Waitlist promotion confirms paid registrations** (`routes_waitlist.py:219`) [C].
  5. **`create_order` falls back to simulation when keys are missing** (`routes_payment.py:80-82`): it tells the browser `simulate: true`, which then posts to `/payment/process` [C at `56a014d`].
  - The price is already computed on the server in `create_order` (`entry_fee` through `calculate_surge_price`, `routes_payment.py:76-78`); coupons aren't connected to checkout (`routes_coupons.py`, inventory). `verify` and `process` ignore that price.
  6. Found while building: the cancel route promotes through a second path, `tasks/waitlist_tasks.promote_from_waitlist`, which also confirmed paid registrations (with the waitlist entry's `Pending` status) and issued a ticket.
- **Who benefits:** the finance office and organisers of paid events.
- **What was built:**
  - `services_payments.py`: one server-side price (`server_price`, `:76`): event fee, then a coupon validated on the server (`find_valid_coupon`, `:36`, now also used by `/coupons/validate`, `routes_coupons.py:111`), then dynamic pricing. `simulation_enabled` (`:28`): `PAYMENT_SIMULATION=true` and never `FLASK_ENV=production`.
  - `payment_orders` table (`models_pg.PaymentOrder`): Razorpay order ID ↔ event ↔ payer ↔ amount, status, and a **unique** `paymentId`. `record_order` (`services_payments.py:108`) writes it in `create_order`; `claim_order` (`:116`) accepts only a recorded order for the session's pending event and payer, marks it paid once with an atomic update, and turns a reused payment ID into 409.
  - `create_order` (`routes_payment.py:66`): the event comes from the pending registration (a different `event_id` in the body → 400); 503 without keys unless simulation is on.
  - `verify` (`routes_payment.py:120`): 503 without keys; signature **and** `claim_order`; records the stored amount; marks a used coupon.
  - `/payment/process` (`routes_payment.py:342`): 403 unless simulation is on; the amount is the server's.
  - Waitlist promotion on a paid event, in both paths: the seat is held as `pending_payment` / `Pending` with no ticket, and the email and notification carry a pay link (`routes_waitlist.promotion_terms`, `routes_waitlist.py:186`, used at `:247` and `tasks/waitlist_tasks.py:75`). `/payment/pay/<reg_id>` (`routes_payment.py:380`) lets only the owner pay; completion confirms the same registration without counting the seat twice (`_existing_registration`, `routes_payment.py:231`).
  - The checkout page no longer sends `amount_inr` and shows the server's price.
  - Existing tests `test_global_scale.py::test_xp_triggers_registration_and_checkin` and `test_next_gen.py::test_checkout_applies_surge_pricing_to_order_amount` use the simulated checkout, so they now set `PAYMENT_SIMULATION=true`; assertions unchanged.
- **Files touched:** `services_payments.py` (new), `models_pg.py`, `routes_payment.py`, `routes_coupons.py`, `routes_waitlist.py`, `tasks/waitlist_tasks.py`, `templates/payment/checkout.html`, `tests/test_payments_secure.py` (new), `tests/test_global_scale.py`, `tests/test_next_gen.py`.
- **Effort:** M (was S) · **Depends on:** none · **Risk:** the new `payment_orders` table is created by start-up `create_all` until UPG-16's migrations exist.
- **Acceptance criteria** (all in `tests/test_payments_secure.py`, on the real SQL adapter with a fake Razorpay client; all 6 fail on the old code):
  1. ✅ `POST /payment/process` → 403 without `PAYMENT_SIMULATION=true`, and 403 with it when `FLASK_ENV=production`; with it in development, the stored amount is the server's (₹250) whatever the form says (`test_simulated_checkout_needs_the_flag_and_never_runs_in_production`).
  2. ✅ With no Razorpay keys, a forged empty-key signature → 503 and no registration; `create_order` → 503, never `simulate: true` unless simulation is on (`test_payment_fails_closed_without_razorpay_keys`).
  3. ✅ A correctly signed payment for an order this server didn't create, for another payer's order, or for the payer's own order made for a cheaper event → 400 and no registration; the genuine order then works (`test_verify_accepts_only_this_servers_order_for_the_same_event_and_payer`).
  4. ✅ `amount_inr` in the body is ignored; with 8 of 10 seats taken the order is ₹300 (₹200 × 1.5) and the registration records ₹300 and the order ID (`test_amount_comes_from_the_server_never_the_request`).
  5. ✅ A payment ID already used → 409; the same order can't be completed twice (`test_a_payment_id_can_be_used_once`). A paid event's waitlist promotion gives `pending_payment` with a pay link; only the owner can use the link; paying confirms the same registration at the server's price without double-counting the seat (`test_waitlist_promotion_on_a_paid_event_holds_the_seat_until_paid`).
  - Full pytest: **432 passed, 1 xfailed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-04 — Endpoints missing authorization
- **Status:** DONE, in two sub-items: **BLK-04a** (coordinator routes, scanner lookup, attendance, certificate, staff roles) and **BLK-04b** (form builder, calendar feed, `/api/v1` CSRF).
- **Last verified:** 2026-10-01, commit "BLK-04b: …" on `production-ready` (parent `35316bb`; BLK-04a is `35316bb`)
- **Problem:**
  - **Fixed by BLK-09** [R]:
    - `/diag/email` now requires SuperAdmin (`routes_auth.py:394-395`; `tests/test_integration_flow.py:189`).
    - `/debug-modal` is gone (`tests/test_integration_flow.py:197`).
    - SPOCs no longer "own" other SPOCs' events just by sharing a category (`services_permission.py:273-282`; `tests/test_integration_flow.py:75-102`).
  - **Still open:**
    - `/coordinator/get_ticket/<reg_id>` returns the full registration (email, phone, answers) to any logged-in user (`routes_coordinator.py:838-844`) [R at `694c729`]. IDs are `uuid5` of `REG-<milliseconds>` (`db_adapter.py` `to_uuid`), so they're guessable.
    - `/coordinator/mark_attendance_granular` needs only login; a student marked themselves present (`routes_coordinator.py:847-872`) [R at `694c729`].
    - `/calendar/feed.ics?user=<email>` leaks anyone's events to anonymous callers (`app.py:1114`) [C at `1f4cdc8`].
    - `/coordinator/certificate/<reg>/<usn>` has no guard [C].
    - Form builder, save, responses and responses export have only a role check, no per-event check (`routes_forms.py:215-240,623-660`) [C at `56a014d`].
  - **Found in Phase 0 (2026-09-30, `56a014d`)** [C]:
    - **`GET /coordinator/delete_event/<event_id>` deletes any event with all its registrations, form submissions and form** for any user with a coordinator-level role (`COORD_ROLES`, `routes_coordinator.py:58`), with no per-event check (`routes_coordinator.py:232-249`). Because it's a GET, an `<img>` tag on any page can trigger it for a logged-in SPOC or coordinator.
    - Other coordinator write routes with only a role check and no per-event check: `assign_staff` (`:253`), `allocate_rooms` (`:294`), `trigger_reminders` (a GET, `:330`), `promote_round` (`:361`), `broadcast` (`:399`), `publish_results` (`:428`), `process_walkin` (`:673`), and the `scan-hud` page (`:816`).
    - **Found in BLK-04a (2026-10-01):** `assign_staff` took the role straight from the form, so an organiser or coordinator could make any student (or a new account) a `SuperAdmin` (`routes_coordinator.py:258-283` at `8ab5005`). `/spoc/delete_event` checked ownership but was also a GET (`routes_spoc.py:1145`).
    - **`/api/v1` accepts the session cookie while being CSRF-exempt.** `api_v1_bp` is exempted from CSRF (`app.py:397-401`) on the grounds that it uses Bearer tokens, but `jwt_required` and `jwt_roles_required` fall back to the session cookie when no token is sent (`auth_jwt.py:167-176,204-214`). A third-party page can therefore make a logged-in user's browser call any `/api/v1` write endpoint.
- **Decision (owner, 2026-09-29):** SPOC isolation **within a category is intended**. A SPOC sees and manages only events they own (`spoc_id` / `created_by` / `spoc_email` / `created_by_email`), plus anything granted through `role_assignments` (unit scope). Sharing a category such as `Technical` grants nothing. Category `All` stays a global override. Implemented in the BLK-09 merge (`services_permission.py:273-282`), pinned by `tests/test_integration_flow.py:75-102`. Don't reintroduce category-based ownership.
- **Who benefits:** all students (privacy) and organisers (attendance integrity).
- **What to build:** `can(session, <perm>, event)` on every open endpoint above; state-changing routes become POST (keeping the old URL as a 405, with the dashboard buttons turned into forms); `get_ticket` returns only what the scanner needs (name, team, attendance), to authorised staff; a tokenised personal calendar feed URL (a per-user secret token, rotatable), with `?user=` ignored. CSRF: session-cookie requests to `/api/v1` must carry the CSRF token (or the session fallback is limited to read-only methods); Bearer-token requests stay exempt, so the Flutter and Capacitor apps keep working.
- **Built in BLK-04a:**
  - `_event_or_abort` (`routes_coordinator.py:74`) loads the event and requires a permission on it, before each route's `try` so a 403 isn't swallowed: `delete_event` and `assign_staff` need `edit_event` (`:258`, `:280`); `allocate_rooms`, `trigger_reminders` and `broadcast` need `manage_registrations` (`:324`, `:361`, `:432`); `promote_round` and `publish_results` need `publish_results` (`:393`, `:462`); walk-ins need `manage_registrations` on the chosen event (`:719`); the HUD scanner page needs `check_in` (`:873`).
  - `delete_event` and `trigger_reminders` are POST only (GET → 405), and so is `/spoc/delete_event` (`routes_spoc.py:1145`); the admin, coordinator and SPOC dashboards use small POST forms with the CSRF token instead of links.
  - Staff roles are limited to `STAFF_ROLES` (`routes_coordinator.py:93`: Judge, EventCoordinator, Coordinator, Volunteer).
  - `get_ticket` (`:895`) answers only staff who can check in at that event, with name, USN, team, room, attendance, payment status and members' names/USNs; never emails, phones or form answers. `mark_attendance_granular` (`:916`) needs the same (`_registration_for_staff`, `:879`). The coordinator certificate (`:948`) needs login plus being the registrant or holding `issue_certificates` on the event.
  - `tests/test_mobile_and_offline.py::TestCoordinatorScanHUD` opened the HUD as an unassigned coordinator; its event now lists that coordinator as staff (assertions unchanged).
- **Built in BLK-04b:**
  - Form builder and save need `edit_event` on the event, responses need `manage_registrations`, and the responses export needs `export_data` (`routes_forms.py:73`, used at `:231`, `:253`, `:630`, `:660`).
  - Personal calendar feed: `?user=` is ignored; the logged-in user gets their own events, and calendar apps use a signed per-user token (`services_accounts.py:120-145`, `app.py:1140-1152`). Pages link the token URL (`calendar_feed_url`, `app.py:1109`); `POST /calendar/feed/rotate` (`app.py:1127`, a "Reset link" button on My Events) bumps `calendar_feed_version` so every older link stops working.
  - `/api/v1`: when a call authenticates with the session cookie instead of a Bearer token, writes must carry the CSRF token (`auth_jwt._session_csrf_failure`, `auth_jwt.py:159`, used by both decorators at `:191`, `:232`); Bearer-token calls are unchanged, so the Flutter and Capacitor apps keep working. The admin AI-copilot modal now sends `X-CSRFToken`.
- **Files touched:** `routes_coordinator.py`, `routes_spoc.py`, `templates/coordinator/dashboard.html`, `templates/admin/dashboard.html`, `templates/spoc/dashboard.html`, `tests/test_coordinator_authz.py` (new), `tests/test_mobile_and_offline.py` (04a); `app.py`, `auth_jwt.py`, `routes_forms.py` and tests (04b).
- **Effort:** M (was S) · **Depends on:** none · **Risk:** the admin AI-copilot modal calls `/api/v1` with the session, so it must send the CSRF header; test it (04b).
- **Acceptance criteria:**
  1. ✅ A student, another student and an unassigned coordinator get 403 on `get_ticket` and `mark_attendance_granular`, and attendance stays `Pending`; assigned staff get only scanner fields (no email, phone or answers) and can mark attendance (`tests/test_coordinator_authz.py::test_students_and_outsiders_get_403_on_ticket_lookup_and_attendance`, `::test_assigned_staff_see_only_what_the_scanner_needs`).
  2. ✅ Anonymous `/calendar/feed.ics?user=<student>` returns an empty calendar (`tests/test_forms_feed_api_authz.py::test_calendar_feed_ignores_user_param_and_works_with_a_rotatable_token`).
  3. ✅ Test: anonymous and SPOC `/diag/email` → 403 (`tests/test_integration_flow.py:189-194`).
  4. ✅ Another SPOC gets 403 on the builder, save, responses and export of an event that isn't theirs, and the form is unchanged; the owner can do all four; assigned staff see responses but can't edit the form (`::test_form_builder_and_responses_are_per_event`). ✅ `/debug-modal` → 404 (`tests/test_integration_flow.py:197-200`); ✅ SPOC B's event is hidden from and 403 for SPOC A (`tests/test_integration_flow.py:96-102`).
  5. ✅ An unassigned coordinator and another SPOC get 403 on all 7 coordinator write routes and are turned away from the HUD, and nothing changes; GET on the delete and reminder routes (coordinator and SPOC) → 405 and the event still exists; an assigned coordinator can't delete; the owner deletes by POST; the staff form refuses `SuperAdmin`; walk-ins only for assigned events (`tests/test_coordinator_authz.py`, 8 tests on the real adapter, all failing on the old code).
  6. ✅ A session-cookie write to `/api/v1` without the CSRF token → 400 and nothing changes; with the token it works; a session read still works; a Bearer-token write needs no CSRF token (`::test_session_cookie_api_writes_need_csrf_but_bearer_tokens_dont`). The copilot modal sends the header (template change; its endpoint needs a Gemini key, not run).
  7. ✅ `/coordinator/certificate/<reg>/<usn>` needs login plus being the registrant or holding `issue_certificates` (`::test_coordinator_certificate_needs_the_registrant_or_certificate_staff`). ✅ The personal feed ignores `?user=`, works with the user's token, refuses a tampered token, and a reset kills the old link (`::test_calendar_feed_ignores_user_param_and_works_with_a_rotatable_token`).
  - All three BLK-04b tests fail on the old code. Full pytest: **443 passed, 1 xfailed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-05 — Route tests never run against the SQL adapter the app uses
- **Status:** IN PROGRESS (criterion 2's first half and criterion 3 met by BLK-09)
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:**
  - **Done by BLK-09:**
    - `tests/conftest.py:18-26` points `DATABASE_URL` at a fresh temp SQLite before any import (or `TEST_DATABASE_URL` for PostgreSQL), and `db_pg.py:110-121` gives `DATABASE_URL` precedence over `CLOUD_SQL_INSTANCE`. So tests can no longer reach a developer's Cloud SQL from `.env` [C].
    - `tests/test_integration_flow.py` (7 HTTP tests, `real_app` fixture) and `tests/test_db_documents.py` (15 tests) run on the real adapter [R].
  - **Still open:**
    - The shared `app` fixture still swaps in `MockFirestore` (`tests/conftest.py:252`), so most route tests don't use the adapter.
    - No SQL-backed journey covers scoring, certificates or feedback.
    - `app.py` still calls `load_dotenv()` (`app.py:51-52`), so a developer's `.env` mail/WhatsApp/Gemini credentials are live during tests. Only `real_app` stubs outbound email (`tests/test_integration_flow.py:30-32`). Confirmed in Phase 0: the local `.env` sets mail, Twilio and Gemini keys, and the Phase 0 runs had to pre-set every one of its keys to keep them out.
- **Who benefits:** everyone building later items; every acceptance criterion needs this.
- **What to build:** run the seminar/hackathon journey (register → check-in → score → certificate → feedback) on `real_app`; a conftest guard that clears or stubs outbound credentials (`MAIL_*`, `TWILIO_*`, `GEMINI_API_KEY`, `RAZORPAY_*`, `BREVO_API_KEY`, `RESEND_API_KEY`).
- **Files touched:** `tests/conftest.py`, `tests/test_integration_flow.py`.
- **Effort:** S (was M) · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ⬜ A `real_app` test runs register → check-in → score → certificate → feedback against the adapter. Register and check-in ✅ covered (`tests/test_integration_flow.py:105-146`).
  2. ✅ Tests can't touch a developer database: `DATABASE_URL` is forced to a temp DB before import (`tests/conftest.py:18-26`) and wins over `CLOUD_SQL_INSTANCE` (`db_pg.py:110-121`). ⬜ Test: outbound-credential env vars are empty inside the test session.
  3. ✅ All earlier tests still pass: 334 passed at `1f4cdc8` on Python 3.11 [R].

#### BLK-06 — The SQL adapter loses, renames and ignores fields (postgres mode)
- **Status:** IN PROGRESS (criteria 1, 2 and 4 partly met by BLK-09)
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Re-ran the original round-trip on `1f4cdc8` [R].
  - **Done by BLK-09:**
    - Events, users and registrations lose no fields: every key route code writes reads back identically, stored in an `extra_json` document shadow (`models_pg.py:114,147,357,430,536,588,608,643`; `db_adapter.py` `_merge_shadow`).
    - Keys read back under the names they were written with (`lead_email`, `payment_status`, `current_round`, …).
    - Workflow states, role names like `UniversityAdmin` and categories like `NSS` round-trip as document values.
    - Filters on document-only fields and `array_contains` now apply in Python instead of being dropped (`db_adapter.py` `SQLQuery.stream`, `_py_match`): `where('usn', …)` and `where('spoc_id', …)` return only matches [R].
    - The audit page shows the actor again.
  - **Still open:**
    1. **Enum columns keep lossy values, so SQL-side filters mismatch** [R]. `users.role` stores `SPOC` / `Participant` for `ClubSPOC` / `UniversityAdmin` (`db_adapter.py` `ROLE_ALIASES`), and `events.category` stores `Technical` for `NSS`. So `where('role','==','UniversityAdmin')` returns nobody, `where('role','==','Participant')` also returns that admin, and `where('category','==','Technical')` also returns the NSS event.
    1b. **Workflow states outside the status enums fall back in the SQL column** [R, `4699478`]. `EventStatus` lacks `evaluation` (used by `services_workflow.EVENT_STATE_TRANSITIONS`), and `RegistrationStatus` lacks most participant states (`pending_payment`, `round_1`, `shortlisted`, …). The document keeps the real value and `where('status','==',state)` matches it exactly, but the column holds `active` / `confirmed`. So `where('status','==','active')`, used by the judge dashboard (`routes_judge.py:59`), also returns events in `evaluation`. Pinned by a strict `xfail`: `tests/test_db_adapter_merge.py::test_active_filter_excludes_states_outside_the_enum`, which should flip to passing when this is fixed.
    2. **No document shadow on master's newer tables**: `OrgUnit`, `RoleAssignment`, `Campus`, `Building`, `Room`, `VenueBooking` (plus `TeamMember`, `Score`, `PushSubscription`, `Announcement`). Unmapped fields written there are still dropped [C].
    3. **The audit `actorEmail` column is still `system`**, because `log_action` writes `user` (`utils.py` `log_action`); SQL-level audit queries can't filter by actor [R].
    4. Rows written before `1f4cdc8` can't recover fields lost earlier (only legacy fallbacks via `_derive_legacy_event_fields`).
    5. **Hot filter fields live only in the JSON shadow** [C at `56a014d`]. `spoc_id` (referenced 23 times in `routes_spoc.py`, and by `services_permission`) has no column on `events` (`models_pg.py` has `coordinatorId` on `events` at `:342` and `spoc_email` only on announcements at `:558`), so `where('spoc_id', …)` loads every event and filters in Python (`db_adapter.py` `_py_match`). The same goes for other document-only keys routes filter on.
    6. **An organisation written without an API key is stored with `''`** (`db_adapter.py:1212`), and `organizations.apiKey` is unique (`models_pg.py:139`), so a second such organisation fails with a unique-constraint error. Found in BLK-14 [R]; the root organisation (`db_adapter.py:1782-1783`) and tenant sign-up (`routes_onboarding.py:66`) work around it by always setting a key.
- **Who benefits:** every user; this is the root cause of most PARTLY BUILT rows at `694c729`.
- **What to build:** store role and category as plain strings (or complete the enums with every value the app writes) plus an Alembic migration; workflow states the enum doesn't know (e.g. `evaluation`) are stored as themselves, never as `active`; add `extra_json` to the remaining tables; write `actor_email` from `log_action`; add real indexed columns for hot filter fields (at least `events.spoc_id`), filled from the shadow for existing rows.
- **Files touched:** `db_adapter.py`, `models_pg.py`, `migrations/`, `utils.py`, tests.
- **Effort:** M (was L) · **Depends on:** BLK-05 · **Risk:** schema migration on existing PostgreSQL data.
- **Acceptance criteria:**
  1. ✅ Round-trip of every key used by `routes_*` for events, registrations and users returns identical values (`tests/test_db_documents.py:56`; re-run [R]). ⬜ The same for tickets, org units, rooms and venue bookings.
  2. ✅ `where('usn','==',x)` returns only that user and `/u/<usn>` shows the right student [R].
  3. ⬜ Test: `where('role','==','UniversityAdmin')` returns exactly the UniversityAdmin users and `where('category','==','Technical')` excludes NSS events.
  4. ✅ The SPOC owner can assign a coordinator (`tests/test_integration_flow.py:177-181`) [R]. ⬜ Bulk certificates on `real_app`.
  5. ⬜ Test: the audit log `actor_email` column holds the acting user's email.
  6. ⬜ Test: `where('status','==','active')` excludes an event in `evaluation` (the strict xfail `tests/test_db_adapter_merge.py::test_active_filter_excludes_states_outside_the_enum` flips to a pass, and its `xfail` marker is removed).
  7. ⬜ Test: `events.spoc_id` is an indexed column; `where('spoc_id','==',x)` is answered by SQL (the compiled query has a `WHERE` on that column), and an event written with `spoc_id` in the document fills the column.
  8. ⬜ Test: two organisations written without an `api_key` can both be saved (an empty key is stored as `NULL`).

#### BLK-07 — Role migration locks out SuperAdmin and SPOC accounts
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Re-run on `1f4cdc8` [R].
  - `GET /admin/org_units` no longer rewrites roles on a fresh database. That's **incidental**: the adapter now creates the root `central` org unit at start-up (`db_adapter.py` `SQLFirestoreAdapter._ensure_root_units`, added in the BLK-09 merge), so the `if not units:` auto-migration (`routes_admin.py:642-644`) doesn't fire.
  - The "Migrate roles" action (`POST /admin/migrate_roles`) still rewrites the SuperAdmin to `UniversityAdmin` (`services_permission.py:422`) and mapped SPOCs to `UnitAdmin` (`:454`). Login maps only legacy names (`routes_auth.py:94-101`), so the SuperAdmin was **locked out** after pressing it [R].
- **Who benefits:** SuperAdmin and every SPOC.
- **What to build:** make migration an explicit POST with a dry-run preview and a confirm step; keep `users.role` compatible with login (or map `UniversityAdmin` → SuperAdmin and `UnitAdmin` → ClubSPOC at login); delete the GET-time trigger.
- **Files touched:** `routes_admin.py`, `services_permission.py`, `routes_auth.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** production may already contain migrated roles; include a repair step.
- **Acceptance criteria:**
  1. ✅ (incidental) `GET /admin/org_units` on a fresh DB leaves every `users.role` unchanged [R]. ⬜ Test that pins this, and the trigger removed.
  2. ⬜ Test: a user stored as `UniversityAdmin` logs in as SuperAdmin; `UnitAdmin` logs in as ClubSPOC.
  3. ⬜ Test: `POST /admin/migrate_roles` without `confirm=1` returns a preview and changes nothing.

#### BLK-08 — Users are logged out at random once ~500 sessions exist; sessions don't survive restarts or span instances
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Unchanged by BLK-09 [C at `56a014d`].
  - Without `REDIS_URL`, sessions are files under `/tmp/flask_session` (`config.py:52-61`). Flask-Session's default file threshold is 500; past it, sessions are pruned.
  - Every anonymous page view creates a session (1 → 11 files after 10 views [R at `694c729`]). At 502 files, logged-in users were logged out mid-flow [R at `694c729`].
  - **Merged in Phase 0 (the "sessions in /tmp" item):** on Cloud Run each instance has its own `/tmp`, which is wiped on restart and redeploy. So every restart logs everyone out, and with two instances a user bounces between "logged in" and "logged out" depending on which instance answers.
  - `docker-compose.yml` provides Redis for self-hosting; the Cloud Run + Supabase target has no Redis.
  - Production cookies: `SESSION_COOKIE_SECURE` and `SameSite=Strict` are set in production (`config.py:45-46`); `HttpOnly` relies on Flask's default. `Strict` drops the cookie when a user arrives from an email link or a payment redirect, so they look logged out on that first page.
- **Who benefits:** everyone on busy days, and after every deploy.
- **What to build:** server-side sessions through Flask-Session's SQLAlchemy backend, in the app database (Redis when `REDIS_URL` is set). This adds a `Flask-SQLAlchemy` dependency, or a small custom session interface on the existing engine; pick the smaller change. Expired rows are cleaned up (UPG-07's clean-up job). Secure, HttpOnly, SameSite=Lax cookies in production. Don't create sessions for anonymous GETs that don't need CSRF.
- **Files touched:** `config.py`, `app.py`, `requirements.txt`, `models_pg.py` or a session table migration, templates that call `csrf_token()` unnecessarily, tests.
- **Effort:** M (was S) · **Depends on:** none · **Risk:** everyone is logged out once when the backend switches.
- **Acceptance criteria:**
  1. Test: after 600 anonymous requests, a previously logged-in test client is still logged in.
  2. Test: with `SESSION_TYPE=filesystem` (development only), `SESSION_FILE_THRESHOLD` is at least 50000.
  3. Test: an anonymous `GET /events` doesn't create a session (no row, no file, no cookie).
  4. Test: a session created through one app instance is accepted by a second, separately created app instance on the same database.
  5. Test: a session survives an app restart (a new app object on the same database keeps the user logged in).
  6. Test: with production config, the session cookie is `Secure`, `HttpOnly` and `SameSite=Lax`.

#### BLK-09 — Merge the `claude/busy-davinci-6nkabi` branch from GitHub
- **Status:** DONE
- **Last verified:** 2026-09-29, commit `4699478`
- **Problem:** `origin/claude/busy-davinci-6nkabi` (3 commits, 2026-09-26: `348aceb`, `6d5bec0`, `c49291b`, forked from `89af3d3`) fixed several items in this list but wasn't on `master`. `master` had 2 unpushed commits since the fork (`efc668a`, `694c729`) touching the same files.
- **Who benefits:** everyone; it was a prerequisite for re-verifying BLK-05/06.
- **What was built:** merge commit `1f4cdc8` on local `master` (not pushed). 9 files conflicted. Resolutions (full list in the commit message):
  - **`config.py`:** master's production `SECRET_KEY` strength check stays; the dev fallback uses the branch's stable `instance/` key, not a random per-process key (which broke sessions/CSRF across gunicorn workers).
  - **`tests/conftest.py`:** both kept (master's `FLASK_ENV`/`FORCE_HTTPS`, the branch's temp database and `SECRET_KEY`).
  - **`db_adapter.py`:** the branch's transform/shadow machinery, corrected for master's schema:
    - `_find_record` uses `STRING_PK_COLLECTIONS`, so venue/org-unit rows are still found by string ID.
    - Status alias tables are built from the enums, so `draft`, `pending_approval`, `published`, `registration_open`, … and `checked_in` aren't collapsed to `active` / `confirmed`.
    - Only `users.role` uses the role enum.
    - Integer conversion kept; the `Base` import restored for `verify_and_align_schema`.
    - DELETE_FIELD on a NOT NULL column resets it to its default.
    - The `default` organization and `central` unit are created at start-up, because `events.orgUnitId` is an enforced foreign key.
  - **Semantic conflicts found only by tests** [R]: SPOC ownership by shared category removed (`services_permission.py`) so the branch's SPOC-isolation test holds; branch tests updated to master's scoped 403s, and to delete a document-only field now that `visibility` is a column.
  - **Lint:** ruff safe fixes so CI lint passes, except the pre-existing `routes_judge.py` `abort` import, recorded in UPG-04.
- **Follow-up (`4699478`, 2026-09-29), requested before pushing:**
  - Root rows are now created with `INSERT … ON CONFLICT DO NOTHING` in one transaction (`db_adapter.py` `SQLFirestoreAdapter._ensure_root_units`), so several processes starting together, or restarts, create them exactly once and never overwrite admin edits. The earlier check-then-insert **lost the race on PostgreSQL 16** in the new 8-process test, with no artificial delay [R].
  - `routes_judge.py` imports `abort` (UPG-04).
  - New `tests/test_db_adapter_merge.py` pins each adapter adjustment. Each test was confirmed to fail when its bug is re-introduced [R].
- **Files touched:** 173 files (the branch's 167 plus resolutions); follow-up: `db_adapter.py`, `routes_judge.py`, `tests/test_db_adapter_merge.py`, `tests/test_integration_flow.py`.
- **Effort:** M · **Depends on:** none · **Risk:** realised as silent merge interactions (listed above), each caught by the tests.
- **Acceptance criteria:**
  1. ✅ `master` contains `c49291b` via merge commit `1f4cdc8` (local only; `master` is 6 ahead of `origin/master`).
  2. ✅ Full pytest passes on the merged code: 334 passed on Python 3.11 with pinned requirements, using the repo's `pytest.ini` options [R]. On the old Python 3.9 `.venv`, 5 tests fail on `hashlib.scrypt`, the same as the branch alone on 3.9.
  3. ✅ Master-side tests from `efc668a`/`694c729` still exist and pass: `tests/test_venues_and_calendar_e2e.py` (18), the `firestore.Increment` test in `tests/test_db_adapter.py`, `tests/test_ticketing_and_forms.py` (17). No assertion in an existing master test was removed; 3 were rewritten by the branch to expect exact round-trips.
  4. ✅ `tests/test_db_documents.py` passes (15 tests).
  5. ✅ Each `db_adapter.py` merge adjustment has a test that fails without it (`tests/test_db_adapter_merge.py`):
     - string-ID lookup: rooms, venue bookings, org units, role assignments, campuses, buildings;
     - every event and participant workflow status round-trips, and enum-backed ones are stored in the column;
     - `role_assignments.role` is stored verbatim while `users.role` still uses the enum;
     - schema alignment upgrades a pre-venues database (needs `Base`).
  6. ✅ Root organization and `central` unit: created once across restarts, never overwritten, and exactly one of each after 8 processes start together, on SQLite and on PostgreSQL 16 [R].
  7. ✅ Full suite at `4699478`: **377 passed, 1 xfailed** on SQLite and on PostgreSQL 16 (Python 3.11, pinned requirements, repo `pytest.ini`); `ruff check .` clean [R].

#### BLK-10 — Seed scripts write known passwords and don't refuse production databases
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:**
  - **19 of the 29** seed/setup scripts hard-code account passwords as literals [R, AST scan for string literals under password-named keys/arguments/variables and in `generate_password_hash(...)`, covering `seed_*.py`, `saptha_full_seed.py`, `demo_reset.py`, `setup_*.py`, `init_*.py`, `fix_superadmin.py`, `scripts/*.py`, `scratch/seed_*.py`, `scratch/set_*password*.py`]. Examples: `seed_all_roles_demo.py:47`, `seed_demo.py:56`, `saptha_full_seed.py:123`, `demo_reset.py:59`, `setup_db.py:27`, `scratch/set_admin_password.py:21`.
  - The current SuperAdmin password equals the demo SuperAdmin password in these scripts (BLK-01), so a seed was apparently run against the database in use.
  - **Only one script has a production guard** (`seed_all_roles_demo.py:28`), and it checks only `FLASK_ENV`. It doesn't stop the risky case: a developer machine with `FLASK_ENV=development` whose `.env` points `DATABASE_URL` / `CLOUD_SQL_INSTANCE` at the real database. The local `.env` does set `CLOUD_SQL_INSTANCE` (review of `694c729`). Scripts that `from app import app` or use `models.db` connect wherever `.env` points.
  - 6 scripts write straight to the real Firebase project with `firestore.client()` and `serviceAccountKey.json` (UPG-15).
- **Decision (owner, 2026-09-30):** keep this as a **blocker**, because the live SuperAdmin password is one of these seed passwords.
- **Who benefits:** everyone with an account; stops known-password accounts appearing in production.
- **What to build:**
  - A shared `seed_safety.py` guard called first by every seed/setup script. It exits non-zero unless the target is local: SQLite, `localhost`/`127.0.0.1`, or a Docker `db` host; no `CLOUD_SQL_INSTANCE`; and `FLASK_ENV != production`. The only override is the command-line flag `--i-know-this-is-production` (owner, 2026-09-30, production-ready plan), which also covers staging.
  - Passwords come from `SEED_<ROLE>_PASSWORD` env vars or are generated with `secrets`, and are printed once at the end.
  - Scripts that talk to Firestore directly also require an explicit project confirmation.
  - Fold the scripts into one seed (with UPG-15).
- **Files touched:** all seed/setup scripts listed above, new `seed_safety.py`, tests.
- **Effort:** S · **Depends on:** none (merging scripts overlaps UPG-15) · **Risk:** low; breaks anyone relying on the published demo logins (they're printed instead).
- **Acceptance criteria:**
  1. Test: an AST scan of every seed/setup script finds no string literal used as a password (dict keys or arguments named like `password`, `password_raw`, `*_PASS`).
  2. Test: running each seed entry point with `DATABASE_URL=postgresql://user@prod-host/db`, with `CLOUD_SQL_INSTANCE` set, or with `FLASK_ENV=production` exits non-zero **before** any database connection (the engine is patched to fail if created).
  3. Test: with a local SQLite `DATABASE_URL`, the seed creates accounts whose passwords come from `SEED_*_PASSWORD` when set, and are random (different across two runs) when not.
  4. Test: with a production-looking target, the script runs only when `--i-know-this-is-production` is passed; an environment variable can't stand in for the flag.

#### BLK-11 — CI's bandit job fails on 5 pre-existing issues, so CI can't go green
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** The CI job "Security scan (bandit)" (`bandit -r . -x tests/,__pycache__/ -ll -q`, `.github/workflows/ci.yml`) exits 1 on 5 Medium-severity findings [R, fresh clone of `f956456`]:
  - `functions/saptha_app/audit_logger.py:111`, `:162` (B104, binding to all interfaces).
  - `functions/saptha_app/db_adapter.py:98`, `:108` (B608, SQL built from strings).
  - `scripts/seed_emulator.py:26` (B113, `requests` call without a timeout).
  - These **predate this work**: the branch alone fails with the same 5, and the old `master` (`89af3d3`) had 9. The merge fixed the root copies of `audit_logger.py` and `db_adapter.py`.
  - GitHub's CI on `master` has failed on every run since at least 2026-08-25. So even after the force-push, CI stays red until this is fixed, which undermines "every acceptance criterion has a passing test" for later items.
- **Who benefits:** everyone building later items; CI becomes a trustworthy gate.
  - Re-run in Phase 0 at `56a014d` (same command, local): exactly the same 5 findings.
- **What to build:** add a timeout to the `scripts/seed_emulator.py` request. For the `functions/saptha_app/` copy, either delete or regenerate it (UPG-15), or fix the two files as the root copies were fixed. Until decision D-1 is made, fix the two files in place (it's the smaller, reversible change). Don't blanket-exclude directories or add `# nosec` without a reason.
- **Files touched:** `functions/saptha_app/audit_logger.py`, `functions/saptha_app/db_adapter.py`, `scripts/seed_emulator.py` (or the UPG-15 removal).
- **Effort:** S · **Depends on:** none · **Risk:** low; the Zoho deploy uses `functions/saptha_app/`, so test it if it's kept.
- **Acceptance criteria:**
  1. `bandit -r . -x tests/,__pycache__/ -ll -q` exits 0 on a fresh clone.
  2. Every job in the CI workflow is green on GitHub for the pushed commit. (Waits on the owner's push, BLK-01.)
  3. `ruff check .` and the full pytest still pass.

#### BLK-12 — Kiosk and ticket-verify holes (and tests for them on the real database)
- **Status:** DONE for the root app (criterion 4, the `functions/` copy, waits on D-1)
- **Last verified:** 2026-10-01, commit "BLK-12: …" on `production-ready` (parent `f2ce15b`)
- **Problem:** Added in Phase 0 from the production-ready plan's list: unauthenticated kiosk search and confirm, a raw registration ID accepted by ticket verify, a GET that marks attendance, and self check-in by email alone.
  - **Already fixed in the root app** (by the BLK-09 merge, branch commit `348aceb`) [C at `56a014d`]:
    - Kiosk search and confirm need login, a coordinator-level role and `can(…, 'check_in', event)`; search queries only that event and returns no emails or phones (`routes_checkin.py:236-400`).
    - `/ticket/verify` and `/ticket/api/verify` accept signed tokens only and refuse raw IDs (`routes_ticket.py:56-84`); the GET is read-only; the check-in POST needs a coordinator-level role with access to the event (`routes_ticket.py:318-327`).
    - Self check-in needs the logged-in owner (lead or team member) plus a signed venue code valid for 10 minutes (`routes_checkin.py:86-128`).
  - **But the tests pinning this run on the in-memory mock**, not the SQL adapter: `tests/test_checkin_security.py` (7 tests, `client`/`mock_db` fixtures).
  - **The `functions/saptha_app` copy (run by the Zoho Catalyst deploy, `catalyst.json`) still has all four holes** [C]: kiosk search/confirm have no login (`functions/saptha_app/routes_checkin.py:143-224`); self check-in takes a typed email (`:45-60`); `/ticket/verify/<reg_id_or_token>` accepts raw registration IDs and marks attendance on a GET (`functions/saptha_app/routes_ticket.py:164-231`), and so does `/ticket/api/verify` (`:279-325`).
- **Who benefits:** every attendee (privacy) and organiser (attendance integrity).
- **What to build:** `real_app` tests for each fixed behaviour. For the `functions/` copy: remove it if Cloud Run is the only deploy target (UPG-15), otherwise port the root fixes (decision D-1).
- **What was built:** `tests/test_checkin_security_real_db.py`, 3 tests on the real SQL adapter. No app code changed: the root fixes predate this branch. To show the tests catch the holes, each was briefly reintroduced and the matching test failed: kiosk search without login (kiosk test fails), a venue code that doesn't expire in 10 minutes (self check-in test fails), raw registration IDs accepted by verify (ticket test fails).
- **Files touched:** `tests/`, and `functions/saptha_app/` (by D-1).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Anonymous kiosk search and confirm are sent to log in and change nothing; an unassigned coordinator gets 403; an assigned one gets only that event's match (not a same-named registrant of another event), with no email or phone in the JSON, and can confirm (`tests/test_checkin_security_real_db.py::test_kiosk_needs_staff_of_the_event_and_never_leaks_contact_details`).
  2. ✅ A raw registration ID on `/ticket/verify` and `/ticket/api/verify` (GET and POST) → 400; GETs with a valid token, anonymous or staff, never change attendance; POSTs by a student or an unassigned coordinator → 403; a POST by assigned staff marks `Present` (`::test_ticket_verify_takes_signed_tokens_only_and_only_staff_mark_attendance`).
  3. ✅ Self check-in sends anonymous users to log in, does nothing for a logged-in user without a registration, and refuses the owner with a missing, malformed, 11-minute-old or other-event code; the owner with a fresh code is marked `Present` (`::test_self_checkin_needs_the_owner_and_a_fresh_code_for_this_event`).
  - Full pytest: **446 passed, 1 xfailed** on SQLite and PostgreSQL 16; ruff clean.
  4. The `functions/saptha_app` copy is no longer tracked, or its kiosk, ticket-verify and self check-in routes pass the same tests (D-1).

#### BLK-13 — Login has no rate limiting
- **Status:** TODO
- **Last verified:** 2026-09-30, commit `56a014d`
- **Problem:** Added in Phase 0 [C at `56a014d`].
  - `/login` (`routes_auth.py`) and `/api/v1/auth/login` (`routes_api_v1.py:45`) have no rate limit. The global default is 100000/day and 10000/hour (`config.py:114`); only the form and chatbot routes set their own limits (`routes_forms.py:292,345`, `chatbot_routes.py:42`).
  - `security_middleware.py:49-110` has per-IP and per-account throttling helpers (`record_login_attempt`, `is_account_locked`), but **nothing calls them**, and they keep state in process memory, so it's lost on restart and not shared across instances or gunicorn workers.
  - The limiter's storage is `memory://` unless `REDIS_URL` is set (`config.py:115`), which has the same per-process problem.
- **Who benefits:** every account (password guessing).
- **What to build:** about 5 failed attempts per minute per IP and per account on `/login`, `/api/v1/auth/login` and the password-reset request, with a clear "try again in N seconds" message (429 for the API). Counters are shared across instances: Redis when `REDIS_URL` is set, otherwise a small database table. A successful login resets the account counter. Don't reveal whether the account exists.
- **Files touched:** `routes_auth.py`, `routes_api_v1.py`, `security_middleware.py` (or a new `services_login_throttle.py`), `models_pg.py`, `config.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** locking out a whole lab behind one NAT IP; keep the per-IP limit looser than per-account if that shows up.
- **Acceptance criteria:**
  1. Test: the 6th failed login within a minute from one IP → 429 (web shows the message), even across different accounts.
  2. Test: the 6th failed attempt on one account from different IPs is refused; after the window, the correct password works.
  3. Test: counters are shared: failures recorded through one app instance count in a second app instance on the same database.
  4. Test: `/api/v1/auth/login` is limited the same way, and the message is identical for existing and unknown accounts.


#### BLK-14 — Anyone can create a SuperAdmin account through the public tenant sign-up
- **Status:** DONE (criterion 3 waits on D-1)
- **Last verified:** 2026-09-30, commit "BLK-14: …" on `production-ready` (parent `ee74fae`)
- **Problem (as found):** Found while working on BLK-02 [R]. `POST /onboarding/signup` (`routes_onboarding.py:17-84` at `dc8ea5a`, registered unconditionally at `app.py:377`) took an organisation name, an email and a password from anyone, created an `organizations` row and a user with role `SuperAdmin`, and logged the visitor in as `SuperAdmin`, with no master key and no invitation. `SuperAdmin` is a wildcard in `utils.role_required` (`utils.py:61-63`), so the fresh session got 200 on `/admin/dashboard`, `/admin/org_units` and `/admin/audit_log`. `MULTI_TENANT_ENABLED` existed (`config.py:218`, default `false`) but the route didn't check it. The `functions/saptha_app` copy has the same route (`functions/saptha_app/routes_onboarding.py:69`).
- **Who benefits:** the whole university (full admin takeover by anyone).
- **What was built:**
  - Every `/onboarding/*` route returns 404 unless `MULTI_TENANT_ENABLED` is on (`routes_onboarding.py:23-27`, a blueprint `before_request`).
  - With the flag on, the sign-up creates a `TenantAdmin` (`routes_onboarding.py:20,74,84`), never `SuperAdmin`; the wizard accepts `TenantAdmin` (`:104`). Tenant-scoped admin powers remain future work, so the flag stays off for this deployment. The first SuperAdmin is created only through the `SUPER_ADMIN_EMAIL` / `SUPER_ADMIN_PASS` first-boot path.
  - Each new tenant gets its own API key (`routes_onboarding.py:66`), because the adapter stores a missing key as `''` and `organizations.apiKey` is unique, so a second tenant couldn't be created (the adapter bug is recorded under BLK-06).
  - `tests/test_global_scale.py`: the two onboarding tests now switch the flag on, and the sign-up test expects `TenantAdmin` instead of `SuperAdmin`, the exact behaviour this item removes (same strictness: an exact role match).
- **Files touched:** `routes_onboarding.py`, `tests/test_tenant_signup_disabled.py` (new), `tests/test_global_scale.py`.
- **Effort:** S · **Depends on:** none · **Risk:** low; nothing in this deployment uses tenant sign-up.
- **Acceptance criteria:**
  1. ✅ Test (real DB): with `MULTI_TENANT_ENABLED` off, `GET`/`POST /onboarding/signup` and `/onboarding/wizard` → 404, and no user, organisation or session is created (`tests/test_tenant_signup_disabled.py::test_tenant_signup_is_404_unless_multi_tenancy_is_on`).
  2. ✅ Test (real DB): with the flag on, the created account's role isn't `SuperAdmin`/`UniversityAdmin`, and its session is refused (redirect to `/login`) on `/admin/dashboard`, `/admin/org_units` and `/admin/audit_log` (`::test_tenant_signup_with_the_flag_on_never_grants_superadmin`). Both tests fail on the old code.
  3. ⬜ The `functions/saptha_app` copy is removed or fixed the same way (D-1).
  - Full pytest: **426 passed, 1 xfailed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-33 — Account emails: walk-in passwords by email, reusable reset links
- **Status:** TODO
- **Last verified:** 2026-09-30, commit "BLK-02: …" (parent `07ad7b2`)
- **Problem:** Found while building BLK-02 [C].
  - Walk-in accounts created by a coordinator get their one-time password in the ticket email (`routes_coordinator.py:728-731`, "Ticket + login details sent"). BLK-02 removed emailed passwords from self-registration only.
  - Staff accounts created through `assign_staff` get a generated password by email and WhatsApp (`send_credentials_email`, `send_staff_credentials_whatsapp`, `routes_coordinator.py:302-303` at BLK-04a).
  - Password-reset links (`/reset_token/<token>`, `routes_auth.py:372`) can be used any number of times within their hour, because the token isn't bound to the current password.
- **Who benefits:** walk-in participants and anyone who resets a password.
- **What to build:** walk-in accounts use BLK-02's unverified account + one-time set-password link; reset tokens are bound to the current password hash like the set-password tokens (`services_accounts.py:71-90`).
- **Files touched:** `routes_coordinator.py`, `routes_auth.py`, tests.
- **Effort:** S · **Depends on:** BLK-02 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a walk-in or a new staff member gets a set-password link and no password, by email or WhatsApp.
  2. Test: a reset link works once; the second use is refused.

#### UPG-34 — The legacy public registration route skips the "registration closed" check
- **Status:** TODO
- **Last verified:** 2026-09-30, commit "BLK-02: …" (parent `07ad7b2`)
- **Problem:** Found while building BLK-02 [C]. `POST /participant/public_register/<event_id>` (`routes_participant.py:358`), still used by the form on `templates/public/event_details.html:737`, never checks the event status or deadline, so it accepts registrations for draft, closed, completed or cancelled events. `/forms/submit` does check (`routes_forms.py:399-402`).
- **Who benefits:** organisers (no registrations after closing).
- **What to build:** point the event page's form at `/forms/register/<event_id>` and make the legacy route apply the same status check (or redirect to the form), keeping the URL.
- **Files touched:** `routes_participant.py`, `templates/public/event_details.html`, tests.
- **Effort:** S · **Depends on:** BLK-02 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the legacy route refuses a draft, closed or cancelled event and creates nothing.
  2. Test: the event page's registration form posts to the checked route.
---

## 7. Production-ready plan (phases)

*(Replaces "Recommended next 3 builds"; set in Phase 0, 2026-09-30.)* Work happens on the `production-ready` branch, one commit per item ("<ID>: <summary>"), in this order. Each phase ends with full checks, a phase summary in the changelog and a stop for the owner's "continue".

| Phase | Items, in order | Notes |
|---|---|---|
| 0. Sync the plan | — | Done 2026-09-30: every item re-verified; BLK-12, BLK-13, UPG-16 to UPG-32 added; sessions merged into BLK-08. |
| 1. Blockers | BLK-02 → BLK-14 → BLK-03 → BLK-04 + BLK-12 → BLK-05 → BLK-06 → BLK-07 → BLK-08 → BLK-10 → BLK-13 → BLK-11 | BLK-01's remaining criteria wait on the owner (D-2) and don't block anything. |
| 2. Event day | UPG-33 account emails → UPG-02 check-in → UPG-06 certificates → UPG-03 exports → UPG-29 assignment → UPG-01 forms → UPG-34 legacy registration route → UPG-08 teams → UPG-30 paid events → UPG-05 feedback → UPG-07 scheduled jobs → UPG-31 notifications | UPG-01 comes before UPG-08 (team fields need it); UPG-07 comes before UPG-31 (the reminder needs it). Each flow gets an end-to-end test on the real database layer. |
| 3. Production setup | UPG-16 migrations → UPG-17 uploads → UPG-18 background jobs → UPG-19 pagination → UPG-20 boot checks/health/logs → UPG-21 backups → UPG-22 privacy | |
| 4. Frontend | UPG-23a–h layout → UPG-24 Bootstrap/fonts → UPG-25 inline scripts/CSP → UPG-26 forms → UPG-27 images → UPG-28 375px check | One commit per UPG-23 area. |
| 5. Clean-up | UPG-14 → UPG-15 | The `functions/saptha_app` copy depends on D-1. |
| 6. Release check | UPG-32 | Fresh clone, production boot, restart/two instances, all scans, `docs/DEPLOY.md`, final report. |

Outside these phases (after Phase 6 unless the owner says otherwise): UPG-04 judging rubrics, UPG-09 venue booking on create, UPG-10 roster import and Google sign-in, UPG-11 participation ledger, UPG-12 faculty/external participants, UPG-13 sports fixtures.

### Decisions needed

| ID | Decision | Blocks | Until decided |
|---|---|---|---|
| D-1 | **Is Cloud Run the only deploy target?** If yes, `functions/saptha_app/` (the Zoho Catalyst copy) and `catalyst.json` are removed in Phase 5. That copy still has the kiosk/ticket holes (BLK-12), the public SuperAdmin sign-up (BLK-14), the bandit findings (BLK-11) and the walk-in default password (UPG-15). If Catalyst stays, it needs a build step instead of a tracked copy. | BLK-12 criterion 4; BLK-14 criterion 3; UPG-15 criteria 3–4 | BLK-11 fixes the two flagged files in place; everything else goes ahead. |
| D-2 | **BLK-01 owner actions:** force-push the rewritten `master`, delete the remote `main` and `claude/busy-davinci-6nkabi`, and ask GitHub Support to purge the 47 PR refs (commands in the 2026-09-29 changelog). The agent never pushes. | BLK-01 criteria 0 and 4 (CI green on GitHub); BLK-11 criterion 2 | Nothing else waits on it. |

---

## 8. Self-check results

The five most important claims, re-verified as if someone else wrote them, following template → route → service → database.

| # | Claim | Result | What changed |
|---|---|---|---|
| 1 | The public registration form logs the visitor in as any email (BLK-02) | **Confirmed** | Traced `registration_form.html` → `routes_forms.submit_form`. No password check at `routes_forms.py:405-421`; session set at `:606` [R]. Found the same pattern in the waitlist branch (`:517`) and payment completion (`routes_payment.py:247`); added both to BLK-02. |
| 2 | QR check-in fails because of the payment gate | **Partly right** — corrected | First written only for `/ticket/verify`. Following each scanner template to its endpoint showed the coordinator and SPOC scanners call different routes (`/coordinator/get_ticket`, `/spoc/api/checkin`), which fail for another reason: the signed token is passed as a registration ID [R]. The coordinator route also has no authorization [R]. UPG-02, BLK-04 and the inventory now say all three camera paths fail and manual SPOC check-in works on event day. |
| 3 | The SQL adapter drops and renames fields (BLK-06) | **Confirmed, with a condition** | Re-ran the round-trip on a clean DB [R] and re-read `db_adapter.py:603-609,1058,1352-1354`. It applies only when `DATABASE_TYPE` is postgres (the default at `models.py:31`); in Firestore mode the fields persist. Which backend production uses couldn't be verified. The summary and item text now state this condition. |
| 4 | Visiting Org Units locks out admins (BLK-07) | **Partly right** — broadened | First attributed to the adapter's enum fallback (postgres only). Re-reading `routes_auth.py:95-102` showed login has no mapping for `UniversityAdmin` / `UnitAdmin`, so the lockout happens in **both** backends. BLK-07 updated. |
| 5 | 12 SPOC actions always refuse because `spoc_id` isn't stored | **Confirmed (postgres mode)** | Traced the dashboard forms (e.g. `templates/spoc/dashboard.html:2033` → `routes_spoc.py:1186`) and the stored event row (no `spoc_id`; the value lands in `coordinatorId`, which no check reads) [R]. SuperAdmin is refused too: crawl redirects on `room_allocation` / `round_panel` [R]. Noted in BLK-06. |

---

## 9. What I couldn't verify, and why

- **Production behaviour and backend.** I didn't access the live site or any real database; I deliberately avoided the Cloud SQL instance and the Firebase project in `.env` / `serviceAccountKey.json`. Which of postgres/Firestore production uses is unknown.
- **Firestore mode end to end.** Not run, to avoid touching the real Firebase project. Items marked "postgres mode" may behave differently there.
- **SQLite vs real PostgreSQL.** The sandbox ran the adapter on SQLite. Field loss is in adapter Python code, so it's backend-independent, but UUID/enum/JSON column behaviour on real Postgres wasn't exercised.
- **Anything needing credentials:** Razorpay live orders (BLK-03 hole 3, order not tied to the event, is from reading the code; hole 2 was run with no key set), email delivery (Brevo/Resend/Gmail), WhatsApp (Twilio), web push, Gemini/AI features (AI copilot, AI form generation, AI matching, summaries), Google/Microsoft OAuth.
- **Celery with Redis, and celery-beat.** Only eager mode was exercised.
- **Android.** Did not build the APK; judged from `capacitor.config.json` and `android/` config only.
- **Not run at all [C]:** walk-in flow, venue-QR self check-in, exams beyond the proctor page, compliance export/delete, announcements, i18n, certificate verification page, form-builder save, performance/concurrency.
- **Repo visibility** was inferred from an unauthenticated GitHub API call returning 200 (`gh` isn't logged in).
- **Planning docs and `reports/` PDFs** were not reviewed page by page; their claims were checked only where they overlapped a feature above.
- **Phase 0 (2026-09-30):** re-verification was by reading the code at `56a014d` [C], plus the Alembic empty-database run [R] and the baseline test/ruff/bandit runs [R]. No flow was re-driven over HTTP. Some counts in the production-ready plan's prompt didn't match the code and were corrected in the items: `migrations/versions/` isn't empty (UPG-16); 2 route files paginate, not 3 (UPG-19); 110 of 129 templates are standalone, not 108 of 126 (UPG-23); Sentry is initialised in code, just untested (UPG-20); the kiosk/ticket holes exist only in the `functions/` copy (BLK-12).

---

## 10. Changelog

| Date | Commit | Item ID | What changed |
|---|---|---|---|
| 2026-09-28 | `694c729` | ALL | Initial full review and baseline re-verification. Created BLK-01..08 and UPG-01..15; inventory and event-type tables. |
| 2026-09-28 | `1f4cdc8` | BLK-09 | Added BLK-09, then merged `origin/claude/busy-davinci-6nkabi` into local `master` (not pushed). 9 conflicting files resolved; semantic merge fixes in `db_adapter.py`, `services_permission.py` and branch tests; pytest 334 passed (Python 3.11). Status → DONE. |
| 2026-09-28 | `1f4cdc8` | BLK-01..08, UPG-03..07, UPG-10 | Re-verified against the merged code. BLK-05 and BLK-06 mostly done (remaining scope narrowed). BLK-04 partly done (`/diag/email`, `/debug-modal`, category ownership). BLK-03 gains two confirmed holes: empty-key signature accepted [R], and order not tied to the event or fee (`amount_inr` / `event_id` from the browser) [C]. BLK-07's GET trigger is dormant but the migrate button still locks out the SuperAdmin [R]. UPG-04 gains the pre-existing `routes_judge.py` `abort` NameError. Inventory rows updated. Not a full re-verification: items outside these files still reflect `694c729`. |
| 2026-09-29 | `4699478` | BLK-09, UPG-04 | BLK-09 follow-up: conflict-safe creation of the root organization and `central` unit (the old check-then-insert raced on PostgreSQL); tests for each `db_adapter.py` merge adjustment, plus an 8-process start-up test on SQLite and PostgreSQL 16. `routes_judge.py` `abort` import added with a 403 test (UPG-04 criterion 5 ✅). Full suite 377 passed, 1 xfailed on both backends; ruff clean. |
| 2026-09-29 | `4699478` | BLK-04, BLK-06, BLK-01 | BLK-04: recorded the owner decision that SPOC isolation within a category is intended. BLK-06: new finding, workflow states outside the enums fall back in the status column (strict xfail). BLK-01: secrets scan of the 6 unpushed commits; no new keys, but current admin credentials are public in pushed files, and unpushed `efc668a`/`694c729` add a real user's personal data to `saptha_fallback.db`. New criterion 0: resolve that before pushing. |
| 2026-09-29 | `c874c04` | BLK-01 | **History rewrite (local; not pushed yet).** Backup first: `git clone --mirror` to `~/saptha-event-portal-backup-2026-09-29.git`, with the remote removed and the old remote branches kept as `refs/backup-remotes/origin/*`. Local DB copy saved to `~/saptha-local-data/saptha_fallback.db`. Ran `git filter-repo --path saptha_fallback.db --invert-paths --refs master ^a1f45b4 --force`: only the 13 commits from `a7baca8` (was `a7baca8`, where the file was added) onward are rewritten, so the other 250 commits keep their hashes and all 49 signatures. (A first unrestricted run changed 245 hashes and stripped the signatures of the GitHub-merged PR commits; it was discarded and redone from the backup.) *(This first local rewrite was superseded before any push by the second one below, which also removed more paths; its commit hashes no longer exist.)* Reflogs expired and objects pruned; the file's 4 blobs are gone. **Verified [R]:** `git log --all -- saptha_fallback.db` is empty; the `master` tree matches the old one except for that file (1,972 vs 1,973 files, identical blobs); pytest 377 passed, 1 xfailed; ruff clean. `origin` re-added without fetching. An editor's background Git fetch then pulled GitHub's old refs back in at 16:23; those refs and objects were deleted and pruned again. `remote.origin.fetch` is **unset** until after the force-push, so background fetches can't store the old history; restore it with `git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'`. **GitHub state (read-only checks):** 0 forks; the file is on the remote `master` and `claude/busy-davinci-6nkabi` only; none of the 47 `refs/pull/*` refs contains it; remote `main` doesn't either. **Owner push commands:** `git push --force-with-lease=master:c6080f56823d0d55268b8170ac9f6c73afeafa43 -u origin master`, then `git push origin --delete main claude/busy-davinci-6nkabi`. Criteria: 0 met locally; 1–4 not met (3 waits for rotation). |
| 2026-09-29 | `08eabf5` | BLK-01, BLK-10, UPG-15 | **Second (final) local history rewrite; still one force-push.** A second mirror backup was taken first (`~/saptha-event-portal-backup-2026-09-29-before-purge2.git`), and `dataconnect/.dataconnect/` was copied to `~/saptha-local-data/`. Then `git filter-repo --force --invert-paths --path dataconnect/.dataconnect/ --path .env --path instance/event_portal.db --path saptha_fallback.db --path-glob '*.pyc' --path-glob '*__pycache__/*'` ran over all 264 commits: most hashes changed and commit signatures were stripped (owner-approved). The first rewrite's hashes no longer exist; `.git/commit-map-github-to-final.txt` maps GitHub's original hashes to the final ones. **Verified [R]:** `git log --all` is empty for every removed path; each of the 264 commits' trees equals its old tree minus exactly the removed paths (0 mismatches, 0 commits dropped); the removed paths' objects are pruned (only the shared empty blob remains); `.env.example` is kept. Nothing in the app or Data Connect config needs `.dataconnect/` (emulator output). Added `.gitignore` rules, `tests/test_repo_hygiene.py`, the CI job "Repo hygiene & secret scan" (gitleaks 8.30.1, sha256-pinned) and `.gitleaksignore`. Gitleaks full history: 8 findings, all baselined (5 false positives or test dummies; 2 real Google API keys to revoke; 1 Supabase publishable key). Recorded the `functions/` walk-in default password (UPG-15) and added BLK-10 (seed scripts). All 47 PR refs still contain removed files (listed in BLK-01) and need GitHub Support. Full pytest 414 passed, 1 xfailed; ruff clean. `remote.origin.fetch` stays unset until the push. **Owner push commands:** `git ls-remote origin refs/heads/master` (must still be `c6080f56823d0d55268b8170ac9f6c73afeafa43`); `git push --force-with-lease=master:c6080f56823d0d55268b8170ac9f6c73afeafa43 origin master`; `git push origin --delete main claude/busy-davinci-6nkabi`; then `git config remote.origin.fetch '+refs/heads/*:refs/remotes/origin/*'`, `git fetch --prune origin` and `git branch --set-upstream-to=origin/master master`. |
| 2026-09-30 | `3ae5665` | BLK-01, BLK-10 | Owner decision: BLK-10 stays a blocker. `.gitleaksignore` no longer accepts the two Google API keys, so CI's secret scan fails on purpose until they're revoked (verified: exactly those 2 findings, exit 1). Recorded the production start-up requirements the push can trigger via auto-deploy (BLK-01 "Owner, before pushing"). |
| 2026-09-30 | `075734f` | BLK-01 | Owner: there's no production deployment (the Cloud Run free tier ended); changed the old mail account's password; revoked both Google API keys. Re-accepted the two revoked keys in `.gitleaksignore` (full-history scan: no leaks in 212 commits [R]). Criterion 3 met for now (no production); criterion 4 met locally. Added **"Before the next deploy"** (new `SECRET_KEY`, `MASTER_SECRET_KEY`, `JWT_SECRET_KEY`, `SUPER_ADMIN_PASS`, `RAZORPAY_KEY_SECRET`, PostgreSQL `DATABASE_URL`). **The force-push has not reached GitHub yet** (`master` still `c6080f5`, old branches present), so CI can't be confirmed green. |
| 2026-09-30 | `f956456` | BLK-11 | New: CI's bandit job fails on 5 pre-existing Medium findings (`functions/saptha_app/` copy and `scripts/seed_emulator.py`; the branch alone and the old `master` fail too). Recorded, not fixed. CI can't be fully green until it's fixed. Local equivalents of the other jobs pass: ruff, hygiene test, full-history gitleaks, pytest (414 passed at `3ae5665`; only docs and `.gitleaksignore` changed since). |
| 2026-09-30 | `56a014d` | ALL (Phase 0) | **Full re-verification of every item not DONE** against the code at `56a014d` on the new branch `production-ready` (from `master`). All citations still hold; corrections: UPG-05's single route already exists (`routes_feedback.py:30-33`), untested; BLK-04 gains the GET `delete_event` (any SPOC/coordinator can delete any event), 8 other coordinator write routes without a per-event check, and `/api/v1` accepting the session cookie while CSRF-exempt; BLK-06 gains the missing `events.spoc_id` column. Status corrections: BLK-04, BLK-05, BLK-06 and UPG-04 → IN PROGRESS (criteria already met by BLK-09); BLK-12 starts IN PROGRESS (root code fixed, tests open). **New items:** BLK-12 kiosk/ticket holes (fixed in the root app, still open in `functions/saptha_app`), BLK-13 login rate limiting, UPG-16 Alembic baseline, UPG-17 object storage, UPG-18 inline tasks + outbox, UPG-19 pagination, UPG-20 boot checks/health/logs/Sentry/headers, UPG-21 backups, UPG-22 privacy, UPG-23 shared layout (a–h), UPG-24 Bootstrap/fonts/SRI, UPG-25 inline scripts/CSP, UPG-26 forms, UPG-27 images, UPG-28 375px check, UPG-29 assignment E2E, UPG-30 paid events E2E, UPG-31 notifications, UPG-32 release check + DEPLOY.md. **Merged:** "sessions in /tmp" into BLK-08; "Celery needs Redis" split between UPG-07 (cron) and UPG-18 (outbox). Owner-directed changes: BLK-10's override is now `--i-know-this-is-production`; BLK-03 stores orders server-side and gates simulation on `PAYMENT_SIMULATION=true`. Inventory rows added for sessions, migrations, uploads, jobs, health, Sentry, backups, pagination, layout, login throttling. Section 7 is now the phase plan, with "Decisions needed" (D-1 deploy targets, D-2 BLK-01 push). |
| 2026-09-30 | `56a014d` | Phase 0 summary | **Done:** branch created; every open item re-verified; 19 items added; statuses and dependencies fixed (UPG-06 no longer waits on UPG-05, UPG-31 not on UPG-18; UPG-01 and UPG-07 pulled into Phase 2 for dependencies). **Checks** (docs-only change): full pytest **414 passed, 1 xfailed** on SQLite and on PostgreSQL 16; `ruff check .` clean; bandit shows the 5 known BLK-11 findings; `alembic upgrade head` on an empty DB fails (UPG-16). **Skipped:** nothing. **Waiting on the owner:** D-1 (is Cloud Run the only deploy target?), D-2 (BLK-01 force-push and GitHub Support). No item marked DONE in this phase. Next: Phase 1, starting with BLK-02. |
| 2026-09-30 | `dc8ea5a` | BLK-14 | New blocker found while starting BLK-02: the public `/onboarding/signup` creates a global `SuperAdmin` and logs the visitor in; confirmed on the real adapter (200 on `/admin/dashboard`, `/admin/org_units`, `/admin/audit_log`). Recorded, not fixed; scheduled right after BLK-02. |
| 2026-09-30 | "BLK-02: …" (parent `07ad7b2`) | BLK-02, UPG-33, UPG-34 | **BLK-02 DONE.** Registration, waitlist and payment completion never log anyone in (both registration routes and both payment endpoints); existing accounts log in first and return to the form; new emails get an unverified account and a one-time set-password link (`services_accounts.py`, `/set_password/<token>`); no password is shown, kept in the session or emailed. 10 new tests on the real adapter (`tests/test_registration_no_auto_login.py`), 9 of which fail on the old code. `real_app` moved to `tests/conftest.py` and now stubs all outbound mail; two `test_seminar_e2e.py` tests that registered students from the SPOC's session now use each student's own session (assertions unchanged). Full pytest 424 passed, 1 xfailed on SQLite and PostgreSQL 16; ruff clean. New: UPG-33 (walk-in passwords by email, reusable reset links), UPG-34 (legacy registration route skips the closed check). |
| 2026-09-30 | "BLK-14: …" (parent `ee74fae`) | BLK-14, BLK-06 | **BLK-14 DONE** (criterion 3 waits on D-1). `/onboarding/*` returns 404 unless `MULTI_TENANT_ENABLED`; with the flag on the sign-up creates a `TenantAdmin`, never `SuperAdmin`; each tenant gets its own API key. 2 new real-DB tests (both fail on the old code). `tests/test_global_scale.py`'s two onboarding tests now enable the flag, and the sign-up test expects `TenantAdmin` instead of `SuperAdmin`. BLK-06 gains the adapter's `''` API key (unique clash). Full pytest 426 passed, 1 xfailed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-03: …" (parent `5c8c044`) | BLK-03, UPG-14 | **BLK-03 DONE.** Server-side price (fee → coupon → dynamic pricing); `payment_orders` records order ↔ event ↔ payer ↔ amount with a unique payment ID; `/payment/verify` checks signature and order, records the stored amount, and fails closed (503) without keys; `create_order` likewise; `/payment/process` only with `PAYMENT_SIMULATION=true` outside production; paid waitlist promotions (both code paths) are held as `pending_payment` with an owner-only pay link. 6 new real-DB tests (all fail on the old code); two existing simulation tests now set the flag. UPG-14 gains the duplicate promotion paths. Full pytest 432 passed, 1 xfailed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-04a: …" (parent `8ab5005`) | BLK-04, UPG-33 | **BLK-04a done** (BLK-04 stays IN PROGRESS for 04b). Every coordinator write route checks the user's permission on that event; delete and reminder routes (and `/spoc/delete_event`) are POST only; staff roles are limited to Judge/EventCoordinator/Coordinator/Volunteer (the form could hand out `SuperAdmin`, found here); the scanner lookup returns no email, phone or answers and, like attendance marking, needs `check_in` on the event; the coordinator certificate needs the registrant or certificate staff. 8 new real-DB tests (all fail on the old code); one HUD test now assigns its coordinator. UPG-33 gains staff credentials by email/WhatsApp. Full pytest 440 passed, 1 xfailed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-04b: …" (parent `35316bb`) | BLK-04 | **BLK-04 DONE** (04a + 04b). 04b: form builder/save need `edit_event`, responses `manage_registrations`, export `export_data`; the personal calendar feed ignores `?user=` and serves calendar apps through a signed per-user token with a "Reset link" that invalidates old links; session-cookie writes to `/api/v1` need the CSRF token while Bearer-token calls are unchanged (copilot modal sends the header). 3 new real-DB tests (all fail on the old code). Full pytest 443 passed, 1 xfailed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-12: …" (parent `f2ce15b`) | BLK-12, UPG-02 | **BLK-12 DONE for the root app** (the `functions/` copy waits on D-1). 3 real-DB tests pin kiosk access and privacy, signed-token-only ticket verify with staff-only check-in, and owner + fresh-code self check-in; each was shown to fail when its hole was briefly reintroduced. No app code changed. UPG-02 gains the verify POST's missing-event gap. Full pytest 446 passed, 1 xfailed on SQLite and PostgreSQL 16; ruff clean. **Five items marked DONE since the Phase 0 re-verification** (BLK-02, BLK-14, BLK-03, BLK-04, BLK-12): AGENTS.md rule 8 suggests a re-verification pass; it's scheduled for the end of Phase 1. |
