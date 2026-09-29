# SapthaEvent — Feature Review and Upgrade Plan

**Reviewed:** 2026-09-28 · **Code reviewed at commit:** `694c729` (branch `master`)
**Re-verified after merging BLK-09:** 2026-09-28 at `1f4cdc8` for every item touching `db_adapter.py`, `db_pg.py`, `config.py`, `routes_payment.py` or `tests/conftest.py` (marked "Last verified … `1f4cdc8`"). Other items still describe `694c729`; re-check them before building (see `AGENTS.md` rule 3).
**Scope:** whole repo; the goal is for this to be the one system Sapthagiri NPS University uses for every kind of event.

This file is the source of truth for planned work. Agents and developers work on one item ID at a time (see `AGENTS.md`).

### How to read the evidence

- `file:line` points at the code as of the item's "Last verified" commit: `1f4cdc8` for re-verified items, otherwise `694c729`.
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
   - anyone can log in as any student through the public registration form (BLK-02);
   - paid events can be confirmed for ₹0 or with a forged payment signature (BLK-03);
   - some endpoints leak registrations (BLK-04);
   - a user database and old credentials are in the public GitHub history (BLK-01).
5. Biggest gap 3 — **the event day still happens outside the app:** the camera scanners reject real ticket QRs and certificates fail to generate [R at `694c729`; not changed by BLK-09]. Departments still need paper sign-in and a separate certificate tool.
6. About 20 templates are never rendered, 3 blueprints are never registered, there are 2 parallel notification systems, 2 payment stacks, 13 seed scripts and a diverged copy of the whole app in `functions/saptha_app/` (UPG-14/15).

---

## 2. Feature inventory

Status: WORKING · PARTLY BUILT (says where it breaks) · NOT CONNECTED (code exists, no UI uses it) · MISSING.

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| Home / event discovery / catalogue | WORKING [R] | `app.py:524`, `app.py:713`, crawl 200 | Home shows a hard-coded fake hackathon when no events exist (`app.py:683-694`). |
| University calendar + event `.ics` | WORKING [R] | `app.py:1066`, `app.py:768` | Department-only visibility filter at `app.py:984-987`. |
| Personal calendar feed | WORKING, **insecure** [R] | `app.py:1113` | `?user=<email>` returns anyone's registered events to anonymous callers (BLK-04). |
| Student sign-up / login | WORKING [R] | `routes_auth.py:195`, `routes_auth.py:36` | USN now persists (document shadow, `db_adapter.py` `extra_json`) [R at `1f4cdc8`]; it wasn't stored at `694c729`. |
| Google / Microsoft login | NOT CONNECTED [C] | `auth_oauth.py:32-135` | Login page has no link to `/auth/google` (`templates/login.html`). |
| 2FA (TOTP) | NOT CONNECTED [C] | `auth_2fa.py:42-155` | No template links to `/auth/2fa/*`. `totp_*` keys now persist [R round-trip at `1f4cdc8`]. |
| Event creation from template (SPOC) | WORKING [R at `1f4cdc8`] | `routes_spoc.py:96-274` | All settings now persist, e.g. a ₹500 fee and team 2–4 (`tests/test_integration_flow.py:75-102`) [R]. Presets only applied for seminar/workshop (`routes_spoc.py:131`). |
| Approval workflow (unit → admin) | WORKING [R] | `services_workflow.py:130-217`, `routes_admin.py:786` | Admin approval sets `published`; SPOC must still move it to `registration_open` (`routes_forms.py:309` treats `published` as closed). |
| Registration form (custom fields) | PARTLY BUILT [R] | `templates/public/registration_form.html:485`, `routes_spoc.py:252-256` | Works for SPOC-created seminar/workshop. Seeded and template-created forms store `field_name`; the template renders `name="{{ field.id }}"`, so inputs get `name=""` and there's no name/email field. |
| Form builder | WORKING (page load [R], save [C]) | `routes_forms.py:215-285` | No per-event ownership check (BLK-04). |
| Auto-account + auto-login on registration | **Security hole** [C at `1f4cdc8`] | `routes_forms.py:517`, `routes_forms.py:598`, `routes_payment.py:251` | Logs the visitor in as whatever email they type (BLK-02). Unchanged by BLK-09. |
| Waitlist | PARTLY BUILT [C] | `routes_forms.py:475-523`, `routes_waitlist.py:185-260` | Promotion confirms paid registrations as `unpaid` (`routes_waitlist.py:219`). No SPOC UI link to `/waitlist/list`. |
| Paid registration (Razorpay) | PARTLY BUILT, **insecure** [R at `1f4cdc8`] | `routes_payment.py:62-290` | Fee now persists and the Razorpay CSP block is fixed (`app.py:205-209`). Still insecure: `/payment/process` simulation; a forged signature on an empty key confirmed a ₹500 registration for ₹1 [R] (BLK-03). |
| Stripe payments | NOT CONNECTED [C] | `routes_payment_stripe.py` | No template or JS references `/payment/stripe`. |
| Coupons | NOT CONNECTED [C] | `routes_coupons.py` | No template or JS references `/coupons/*`. |
| Digital ticket page | PARTLY BUILT [R] | `routes_ticket.py:115-172` | New registrations open; the seeded registration shows "not your ticket" because `is_lead` reads `lead_email` (`routes_ticket.py:134`), which postgres mode returned as `leadEmail` at `694c729`. At `1f4cdc8` the key reads back correctly [R round-trip]; the page wasn't re-run. |
| Camera QR check-in (coordinator, SPOC, HUD) | PARTLY BUILT — **fails with real QRs** [R] | `templates/coordinator/scan.html:231-234`, `templates/spoc/scan.html:447-458`, `routes_ticket.py:270-271,479-481` | Coordinator/SPOC scanners pass the signed token as a reg ID → "INVALID TICKET" / 404 [R]. `/ticket/verify` and `/ticket/api/verify` said "Payment pending" for free tickets [R at `694c729`]. At `1f4cdc8` `payment_status` reads back as written (`Free`), so that gate likely passes; the token-as-reg-ID break is unchanged [C]. Not re-run (UPG-02). |
| Manual check-in (SPOC list) | WORKING on event day [R] | `routes_spoc.py:451-525` | Locked until event date (intended). Attendee name comes back blank in postgres mode. |
| Kiosk check-in | PARTLY BUILT [R] | `routes_checkin.py:256-400` | Coordinator gets 403, because they can't be assigned (see next rows). Name search reads `lead_name`. |
| Venue-QR self check-in | PARTLY BUILT [C] | `routes_checkin.py:65-172` | `public/checkin_closed.html` now exists and `/checkin/<id>` renders [R at `1f4cdc8`]; submit not run. |
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
- **Last verified:** 2026-09-28, commit `694c729`
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
- **Last verified:** 2026-09-28, commit `694c729`
- **Problem:** Three scanners, three broken paths [R]:
  - `templates/coordinator/scan.html:231-234` sends the signed token to `/coordinator/get_ticket/` → "INVALID TICKET".
  - `templates/spoc/scan.html:447-458` sends it to `/spoc/api/checkin/` → 404.
  - `scan_hud` → `/ticket/api/verify` blocks free tickets as "Payment pending" (`routes_ticket.py:479-481`; same gate at `:270-271`).
  - The offline queue replays to kiosk confirm (`static/js/offline-sync.js:83`), which returns 403 because coordinators can't be assigned.
- **Who benefits:** every coordinator and volunteer on event day; removes paper sign-in sheets.
- **What to build:** one check-in endpoint that accepts the signed token (`routes_ticket._parse_signed_token`), authorises with `can(session, 'check_in', event)`, applies a payment rule on the normalised status (free/waived/paid), is idempotent, and returns name and team. Point all three scanners and the offline queue at it. Make kiosk name search use the corrected keys.
- **Files touched:** `routes_ticket.py`, `routes_coordinator.py`, `routes_spoc.py`, `routes_checkin.py`, `templates/coordinator/scan.html`, `templates/spoc/scan.html`, `templates/coordinator/scan_hud.html`, `static/js/offline-sync.js`, tests.
- **Effort:** M · **Depends on:** BLK-04, BLK-06 · **Risk:** event-day critical path; ship behind a test that replays a real ticket token.
- **Acceptance criteria:**
  1. Test: token taken from the ticket page, scanned by the assigned coordinator → attendance `Present`; a second scan → "already checked in".
  2. Test: an unassigned coordinator and a student both get 403.
  3. Test: a free registration is never reported as unpaid; an unpaid paid registration is refused.
  4. Test: replaying an offline queue of 3 tokens marks 3 attendees present.

#### UPG-03 — Exports and an event report with real participant data
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `694c729`
- **Problem:** `/spoc/export_csv`, `/coordinator/export_registrations`, `/forms/responses/export` and `/admin/analytics/export/registrations` all downloaded files with empty name, email, phone and USN columns in postgres mode at `694c729` [R]. The cause (renamed keys) is fixed by BLK-09, so re-run the exports before building; the unified export service and event report are still needed. There is no deterministic post-event report; the AI report is blocked (`routes_spoc.py:816`).
- **Who benefits:** every organiser and HoD; replaces the Excel re-typing and hand-written IQAC/NAAC event reports.
- **What to build:** one export service used by SPOC, coordinator and admin, with columns for name, USN, department, year, email, phone, attendance, score, rank and certificate ID. Add a one-click event report (XLSX/PDF): registrations vs attendance by department/year, feedback averages, winners. No AI needed.
- **Files touched:** new `services_export.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_admin.py`, `routes_forms.py`, tests.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** PII in exports; keep behind `can(..., 'export_data', event)`.
- **Acceptance criteria:**
  1. Test: exporting an event with 2 registrations yields 2 rows with non-empty name and email.
  2. Test: a SPOC of another unit gets 403 on the export.
  3. Test: the event report's attendance count equals the number of `Present` registrations.
  4. An organiser can download the report from the SPOC dashboard.

#### UPG-04 — Judging works for rubric criteria from the create form and for new workflow states
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
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
- **Last verified:** 2026-09-28, commit `694c729`
- **Problem:** Students are told "Unauthorised access." on `/feedback/submit/<reg>` and `/participant/feedback/<reg>`, because both read `lead_email` (`routes_feedback.py:37`, `routes_participant.py:293`) [R]. At `1f4cdc8`, `/feedback/view` redirects to `/feedback/analytics`, which returns 200 [R] (it was 500 at `694c729`). The `lead_email` ownership key now reads back correctly, so the student routes may work; not re-run. There are still two parallel student feedback routes.
- **Who benefits:** every attendee and organiser; replaces Google Forms feedback.
- **What to build:** one student feedback route (keep `/participant/feedback`, redirect the other), the missing templates, an analytics page, and an option to require feedback before the certificate is issued.
- **Files touched:** `routes_feedback.py`, `routes_participant.py`, `templates/feedback/*`, tests.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the attendee `GET`s the feedback form → 200, `POST` → saved, read back on `/feedback/view/<event>` (200).
  2. Test: `/feedback/analytics/<event>` returns 200 with 0 and with 3 responses.
  3. Test: a non-owner student gets 403.
  4. Test: `/feedback/submit/<reg>` redirects to the single route.

#### UPG-06 — Certificates generate with the right name and can be issued in bulk
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `694c729`
- **Problem:** (the signature mismatch is re-checked unchanged at `1f4cdc8` [C]; the name and bulk-gate bullets were caused by BLK-06 and are likely fixed, not re-run)
  - `tasks/cert_tasks.py:44-50` calls `generate_certificate_pdf(reg_id=, name=, event_date=, venue=)`, but the signature is `(student_name, event_title, reg_id, cert_type, ...)` (`utils_certificate.py:145`). End-event certificate generation fails with a `TypeError` [R].
  - The certificate page reads `lead_name` (`routes_participant.py:233`) → "presented to None" [R].
  - Bulk send is blocked by `spoc_id` (`routes_spoc.py:1900`).
- **Who benefits:** every attendee; removes the separate certificate tool.
- **What to build:** fix the call signature; one issuing path (end event or button) producing a PDF per attendee with a stored certificate ID and verify URL; emailing on top.
- **Files touched:** `tasks/cert_tasks.py`, `utils_certificate.py`, `routes_spoc.py`, `routes_participant.py`, `routes_verification.py`, tests.
- **Effort:** M · **Depends on:** BLK-06, UPG-05 · **Risk:** PDF rendering on free-tier memory; generate lazily or in small batches.
- **Acceptance criteria:**
  1. Test: ending an event with 2 Present and 1 Absent attendee creates exactly 2 certificates without exceptions (eager Celery).
  2. Test: the certificate page shows the attendee's name.
  3. Test: `/verify/<certificate_id>` shows valid; a random ID shows invalid.
  4. The SPOC "bulk certificates" button succeeds for the event owner.

#### UPG-07 — Reminders and lifecycle jobs run on free-tier hosting
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
- **Problem:** Reminders, the day-before QR email and lifecycle transitions are Celery beat jobs (`celery_app.py:95-120`). Since BLK-09, `docker-compose.yml:27-37` runs a Celery worker and beat for self-hosting. But the Dockerfile (what a single free-tier web service runs) starts only gunicorn (`Dockerfile:33`), and without Redis Celery runs eagerly (`celery_app.py:51-58`), so beat never runs there. The APScheduler files are unused (`scheduler_enhanced.py:284` has `start()` commented out; neither file is imported by the app).
- **Who benefits:** all registrants, and organisers who now send WhatsApp reminders by hand.
- **What to build:** a protected `POST /internal/cron/<job>` (shared secret header) that runs the existing task functions idempotently, plus a GitHub Actions `schedule` workflow (free) that calls it hourly. Delete the unused schedulers (see UPG-14).
- **Files touched:** new `routes_cron.py`, `app.py`, `tasks/scheduled_tasks.py`, `.github/workflows/cron.yml`, tests.
- **Effort:** S · **Depends on:** none (tests need BLK-05) · **Risk:** double sends; rely on the existing `*_sent` flags, which need BLK-06 to persist.
- **Acceptance criteria:**
  1. Test: calling without the secret → 403.
  2. Test: `send_24h_reminders` with the secret, for an event tomorrow, sends once; a second call sends nothing.
  3. Test: the lifecycle job moves an event past its end date to `completed`.
  4. `.github/workflows/cron.yml` exists and targets the endpoint.

#### UPG-08 — Team registration linked to tickets and judging
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `694c729`
- **Problem:** The SPOC-created team hackathon form shows only name/email/phone/USN [R], because `is_team_event` and `limits` are dropped and the fallback schema isn't team-aware (`routes_forms.py:328-330`). `/teams/*` writes a separate `teams` collection (`routes_teams.py:92`) that registrations, tickets and judges never read. Members are parsed only from `member_N_*` fields (`routes_forms.py:431-441`).
- **Who benefits:** hackathon, sports and cultural teams; removes WhatsApp team collection.
- **What to build:** team fields generated from `team_min`/`team_max`; invite-code join that adds the member to the same registration; each member sees the ticket; judges see the team name.
- **Files touched:** `routes_forms.py`, `routes_teams.py`, `templates/public/registration_form.html`, `templates/teams/*`, tests.
- **Effort:** M · **Depends on:** BLK-06, UPG-01 · **Risk:** medium; changes the registration record shape.
- **Acceptance criteria:**
  1. Test: a team event with limits 2–4 renders member fields and rejects a 1-member team.
  2. Test: joining by invite code adds the member to `members` and they can open the ticket.
  3. Test: the judge event page lists the team name.
  4. Test: a team at `team_max` rejects another join.

#### UPG-09 — Book the venue while creating the event
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `694c729`
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
- **Last verified:** 2026-09-28, commit `1f4cdc8`
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
- **Last verified:** 2026-09-28, commit `694c729`
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
- **Last verified:** 2026-09-28, commit `694c729`
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
- **Last verified:** 2026-09-28, commit `694c729`
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
- **Last verified:** 2026-09-28, commit `694c729`
- **Problem:**
  - **Notifications:** the v1 feed reads `notifications` (`routes_notifications.py:20`), but every writer uses `notifications_v2` (`routes_notifications_v2.py:70`, `services_automation.py:185`, `routes_waitlist.py:96`). The student dashboard feed (`templates/participant/dashboard.html:1758`) is always empty, while the header badge counts v2.
  - **Payments:** Stripe has no UI reference (`routes_payment_stripe.py`).
  - **Schedulers:** `scheduler.py` / `scheduler_enhanced.py` aren't used by the app.
  - **Matchmaker:** `routes_matchmaker.py` suggests mock people (`routes_matchmaker.py:12`). `routes_ai_matching.py` is a different feature (judge↔team) and stays.
  - **Tests:** `tests.py` fails at collection [R] and duplicates `tests/`.
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
- **Last verified:** 2026-09-28, commit `694c729`
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
- **What to build:** remove or merge the above; generate the Catalyst bundle at deploy time instead of tracking a copy (confirm with the owner first); keep one seed script (`seed_all_roles_demo.py` + `seed_events_universal.py` merged).
- **Files touched:** listed above, plus a new test.
- **Effort:** M · **Depends on:** none · **Risk:** the Zoho Catalyst deploy uses `functions/saptha_app/`; replace it with a build step before deleting.
- **Acceptance criteria:**
  1. Test: parse every template's internal `href`/`action`/`fetch` URL and assert each matches a rule in `app.url_map`.
  2. Test: `/debug-modal` → 404.
  3. `git ls-files` lists no `functions/saptha_app/*.py` and no `seed_*.py` beyond the kept one.
  4. The Catalyst deploy still works via the build step (manual check).
  5. Walk-in accounts created on the Zoho deploy with the old default password have been forced to reset (owner check), and no tracked file sets a default walk-in password (test).

---

## 6. Blockers — fix before building new features

Ranked by exposure and urgency. Kept short; a separate security pass will go deeper.

#### BLK-01 — Admin credentials and a user database are in the public GitHub history
- **Status:** IN PROGRESS
- **Last verified:** 2026-09-29, commit `08eabf5`
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
  - **Done locally:** backups; history rewrite; `.gitignore` rules; `tests/test_repo_hygiene.py`; CI job "Repo hygiene & secret scan" (the hygiene test plus a pinned gitleaks 8.30.1 full-history scan, with accepted findings in `.gitleaksignore`).
  - **Owner, now:** force-push and delete the remote branches (commands in the 2026-09-29 changelog entry).
  - **Owner, now:** ask GitHub Support to remove the PR refs' copies and cached views of old commits, sending the PR numbers above and `.git/commit-map-github-to-final.txt` (original → new hashes).
  - **Owner:** rotate or revoke `SUPER_ADMIN_PASS` (including the stored account hash), `MASTER_SECRET_KEY`, both old `MAIL_PASS` app passwords, the old `GEMINI_API_KEY`, the second Google API key, and (if the project is still used) the Supabase publishable key. Force password resets for accounts that were in the removed databases. Have collaborators re-clone.
- **Files touched:** `.gitignore`, `.github/workflows/ci.yml`, `.gitleaksignore`, `tests/test_repo_hygiene.py`; history rewrite; operational steps outside the code.
- **Effort:** S · **Depends on:** none · **Risk:** the force-push breaks existing clones; old objects stay on GitHub (PR refs, cached views) until Support removes them.
- **Local artifacts (never push or commit):**
  - `~/saptha-event-portal-backup-2026-09-29.git`: the original history.
  - `~/saptha-event-portal-backup-2026-09-29-before-purge2.git`: after the first rewrite.
  - `~/saptha-local-data/saptha_fallback.db` and `~/saptha-local-data/dataconnect-.dataconnect/`: local dev data, owner-only permissions.
  - `.git/commit-map-github-to-final.txt`.
  - Delete the backups and data copies once the push is confirmed; prefer the seed scripts for local data.
- **Acceptance criteria:**
  0. ✅ **Met locally:** no local commit contains `saptha_fallback.db` or the other removed paths. Completes on GitHub after the force-push, branch deletion and GitHub Support's PR-ref clean-up.
  1. ✅ **Met:** `tests/test_repo_hygiene.py::test_no_forbidden_files_are_tracked` fails if any `*.db`, `*.sqlite*`, `.env*` (other than `.env.example`), service-account key, `*.pyc` / `__pycache__/`, `dataconnect/.dataconnect/` or `instance/` file is tracked. It passes at `08eabf5`.
  2. ✅ **Met:** the CI job "Repo hygiene & secret scan" runs that test and the gitleaks scan. Demonstrated on a throwaway branch in a scratch clone: a commit adding `.env`, `local.db`, a `.pyc` and a fake AWS-style key made the test fail (1 failed, naming the 3 files) and gitleaks exit 1 [R].
  3. ⬜ **Not met (open until the owner confirms rotation):** the old SuperAdmin password no longer works on production. The start-up refusal ✅ exists (`tests/test_integration_flow.py:204`).
  4. ⬜ **Not met:** the full-history gitleaks scan passes (0 findings with the `.gitleaksignore` baseline [R]), but the baseline accepts **two real Google API keys**, justified only once they're revoked. Today's password and master key also remain as literals in history (gitleaks doesn't flag them; found by value match). Becomes ✅ when the owner confirms revocation.

#### BLK-02 — The public registration form logs the visitor in as any email they type
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
- **Problem:** Unchanged by BLK-09 [C]. `submit_form` sets `session['user_id']` to the submitted email (`routes_forms.py:598`; waitlist branch `routes_forms.py:517`), and so does payment completion (`routes_payment.py:251`). There's no password check for existing accounts. At `694c729`, an anonymous visitor submitted the hackathon form as `student@demo.com` and landed on that student's profile and dashboard [R]. The generated password is still kept in the session (`routes_forms.py:610`).
- **Who benefits:** every student account.
- **What to build:** never log in from the form. If the visitor is logged in, the email is the session email. If an account exists for the email, require login and return. New accounts are created unverified and log in only via an emailed link. Don't store passwords in the session.
- **Files touched:** `routes_forms.py`, `routes_payment.py`, `templates/public/registration_form.html`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** a small UX change (existing students must log in first).
- **Acceptance criteria:**
  1. Test: an anonymous submit with an existing student's email → no `user_id` in the session and a redirect to `/login`.
  2. Test: a logged-in student submitting a different email → the registration is saved under the session email.
  3. Test: the waitlist branch, `/payment/process` and `/payment/verify` never set the session.
  4. Test: `/registration/confirmed` never contains a password.

#### BLK-03 — Paid events can be completed without paying
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
- **Problem:** BLK-09 fixed two prerequisites: the event fee now persists (₹500 stored as `entry_fee` 500 and `fees.regular` 500 [R]), and the CSP no longer blocks Razorpay checkout (`app.py:205-209`). The checks themselves are unchanged (`git diff 694c729 1f4cdc8 -- routes_payment.py` only adds form-answer recording).
  1. **Simulation endpoint always on.** `/payment/process` (`routes_payment.py:269-290`) completes any pending registration with a client-supplied amount; a ₹200 registration was confirmed for ₹0 [R at `694c729`].
  2. **Empty-key signature accepted.** When `RAZORPAY_KEY_SECRET` is unset, `/payment/verify` computes `HMAC('', order_id|payment_id)` (`routes_payment.py:34,112-118`), so anyone can produce a valid signature. On `1f4cdc8`, a forged signature with fake order/payment IDs confirmed a ₹500 registration as `Confirmed / Paid / ₹1` with payment ID `pay_FAKE456` [R].
  3. **Order not tied to the event or its fee.** The signature covers only `order_id|payment_id`. `verify_payment` never fetches the order from Razorpay, takes `event_id` from the request body (`routes_payment.py:110`) and records `amount_inr` from the browser (`routes_payment.py:125`). So even with a real secret, one genuine low-value payment (e.g. an order for a cheaper event, or a replayed payment) confirms any event at any claimed amount [C]. `create_order` writes `event_id` into the order notes (`routes_payment.py:88`), but nothing reads them back.
  4. **Waitlist promotion confirms paid registrations** (`routes_waitlist.py:219`) [C].
- **Who benefits:** the finance office and organisers of paid events.
- **What to build:**
  - Simulation only when `PAYMENT_SIMULATION=1` and not production.
  - `/payment/verify` returns 503 when the key ID or secret is empty.
  - Fetch the order (`razorpay.Client.order.fetch`) and require `status == 'paid'`, `amount == server-side fee × 100` and `notes.event_id == event_id` from the session's pending registration, not the request body.
  - Store `payment_id` and reject reuse.
  - Promoted paid registrations become `pending_payment` with a pay link.
- **Files touched:** `routes_payment.py`, `routes_waitlist.py`, `config.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low; needs Razorpay test keys for a manual end-to-end check.
- **Acceptance criteria:**
  1. Test: `POST /payment/process` → 403 unless `PAYMENT_SIMULATION=1` (and always 403 in production).
  2. Test: with `RAZORPAY_KEY_SECRET` unset, `POST /payment/verify` with an HMAC made from an empty key → 503, and no registration is created.
  3. Test (order fetch mocked): an order whose amount is below the fee, whose `notes.event_id` differs, or whose status isn't `paid` → 400, no registration.
  4. Test: `amount_inr` in the request body is ignored; the stored `amount_paid` equals the fetched order amount.
  5. Test: a payment ID already used by another registration → 409; promoting from the waitlist on a paid event gives `pending_payment`, not confirmed.

#### BLK-04 — Endpoints missing authorization
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
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
    - Form builder and responses have no per-event check (`routes_forms.py`) [C].
- **Decision (owner, 2026-09-29):** SPOC isolation **within a category is intended**. A SPOC sees and manages only events they own (`spoc_id` / `created_by` / `spoc_email` / `created_by_email`), plus anything granted through `role_assignments` (unit scope). Sharing a category such as `Technical` grants nothing. Category `All` stays a global override. Implemented in the BLK-09 merge (`services_permission.py:273-282`), pinned by `tests/test_integration_flow.py:75-102`. Don't reintroduce category-based ownership.
- **Who benefits:** all students (privacy) and organisers (attendance integrity).
- **What to build:** `can(session, <perm>, event)` on the open endpoints; a tokenised calendar feed URL.
- **Files touched:** `routes_coordinator.py`, `app.py`, `routes_forms.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ⬜ Test: a student gets 403 on `get_ticket` and `mark_attendance_granular` for any registration.
  2. ⬜ Test: anonymous `/calendar/feed.ics?user=x` returns an empty calendar.
  3. ✅ Test: anonymous and SPOC `/diag/email` → 403 (`tests/test_integration_flow.py:189-194`).
  4. ⬜ SPOC of unit A gets 403 on `/forms/responses/<unit B event>`. ✅ `/debug-modal` → 404 (`tests/test_integration_flow.py:197-200`); ✅ SPOC B's event is hidden from and 403 for SPOC A (`tests/test_integration_flow.py:96-102`).

#### BLK-05 — Route tests never run against the SQL adapter the app uses
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
- **Problem:**
  - **Done by BLK-09:**
    - `tests/conftest.py:18-26` points `DATABASE_URL` at a fresh temp SQLite before any import (or `TEST_DATABASE_URL` for PostgreSQL), and `db_pg.py:110-121` gives `DATABASE_URL` precedence over `CLOUD_SQL_INSTANCE`. So tests can no longer reach a developer's Cloud SQL from `.env` [C].
    - `tests/test_integration_flow.py` (7 HTTP tests, `real_app` fixture) and `tests/test_db_documents.py` (15 tests) run on the real adapter [R].
  - **Still open:**
    - The shared `app` fixture still swaps in `MockFirestore` (`tests/conftest.py:252`), so most route tests don't use the adapter.
    - No SQL-backed journey covers scoring, certificates or feedback.
    - `app.py` still calls `load_dotenv()`, so a developer's `.env` mail/WhatsApp/Gemini credentials are live during tests. Only `real_app` stubs outbound email (`tests/test_integration_flow.py:30-32`).
- **Who benefits:** everyone building later items; every acceptance criterion needs this.
- **What to build:** run the seminar/hackathon journey (register → check-in → score → certificate → feedback) on `real_app`; a conftest guard that clears or stubs outbound credentials (`MAIL_*`, `TWILIO_*`, `GEMINI_API_KEY`, `RAZORPAY_*`, `BREVO_API_KEY`, `RESEND_API_KEY`).
- **Files touched:** `tests/conftest.py`, `tests/test_integration_flow.py`.
- **Effort:** S (was M) · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ⬜ A `real_app` test runs register → check-in → score → certificate → feedback against the adapter. Register and check-in ✅ covered (`tests/test_integration_flow.py:105-146`).
  2. ✅ Tests can't touch a developer database: `DATABASE_URL` is forced to a temp DB before import (`tests/conftest.py:18-26`) and wins over `CLOUD_SQL_INSTANCE` (`db_pg.py:110-121`). ⬜ Test: outbound-credential env vars are empty inside the test session.
  3. ✅ All earlier tests still pass: 334 passed at `1f4cdc8` on Python 3.11 [R].

#### BLK-06 — The SQL adapter loses, renames and ignores fields (postgres mode)
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
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
- **Who benefits:** every user; this is the root cause of most PARTLY BUILT rows at `694c729`.
- **What to build:** store role and category as plain strings (or complete the enums with every value the app writes) plus an Alembic migration; add `extra_json` to the remaining tables; write `actor_email` from `log_action`.
- **Files touched:** `db_adapter.py`, `models_pg.py`, `migrations/`, `utils.py`, tests.
- **Effort:** M (was L) · **Depends on:** BLK-05 · **Risk:** schema migration on existing PostgreSQL data.
- **Acceptance criteria:**
  1. ✅ Round-trip of every key used by `routes_*` for events, registrations and users returns identical values (`tests/test_db_documents.py:56`; re-run [R]). ⬜ The same for tickets, org units, rooms and venue bookings.
  2. ✅ `where('usn','==',x)` returns only that user and `/u/<usn>` shows the right student [R].
  3. ⬜ Test: `where('role','==','UniversityAdmin')` returns exactly the UniversityAdmin users and `where('category','==','Technical')` excludes NSS events.
  4. ✅ The SPOC owner can assign a coordinator (`tests/test_integration_flow.py:177-181`) [R]. ⬜ Bulk certificates on `real_app`.
  5. ⬜ Test: the audit log `actor_email` column holds the acting user's email.

#### BLK-07 — Role migration locks out SuperAdmin and SPOC accounts
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
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

#### BLK-08 — Users are logged out at random once ~500 sessions exist
- **Status:** TODO
- **Last verified:** 2026-09-28, commit `1f4cdc8`
- **Problem:** Unchanged by BLK-09 [C].
  - Without `REDIS_URL`, sessions are files (`config.py:54-61`). Flask-Session's default file threshold is 500; past it, sessions are pruned.
  - Every anonymous page view creates a session (1 → 11 files after 10 views [R at `694c729`]). At 502 files, logged-in users were logged out mid-flow [R at `694c729`].
  - `docker-compose.yml` now provides Redis for self-hosting, but a free-tier single web service still has no Redis.
- **Who benefits:** everyone on busy days.
- **What to build:** set `SESSION_FILE_THRESHOLD` high plus a periodic cleanup of expired files, or use a free managed Redis; avoid creating sessions for anonymous GETs that don't need CSRF.
- **Files touched:** `config.py`, `app.py`, templates that call `csrf_token()` unnecessarily, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: after 600 anonymous requests, a previously logged-in test client is still logged in.
  2. Test: with `SESSION_TYPE=filesystem`, `SESSION_FILE_THRESHOLD` is at least 50000.
  3. Test: an anonymous `GET /events` doesn't create a session file.

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
- **Last verified:** 2026-09-29, commit `08eabf5`
- **Problem:**
  - **19 of the 29** seed/setup scripts hard-code account passwords as literals [R, AST scan for string literals under password-named keys/arguments/variables and in `generate_password_hash(...)`, covering `seed_*.py`, `saptha_full_seed.py`, `demo_reset.py`, `setup_*.py`, `init_*.py`, `fix_superadmin.py`, `scripts/*.py`, `scratch/seed_*.py`, `scratch/set_*password*.py`]. Examples: `seed_all_roles_demo.py:47`, `seed_demo.py:56`, `saptha_full_seed.py:123`, `demo_reset.py:59`, `setup_db.py:27`, `scratch/set_admin_password.py:21`.
  - The current SuperAdmin password equals the demo SuperAdmin password in these scripts (BLK-01), so a seed was apparently run against the database in use.
  - **Only one script has a production guard** (`seed_all_roles_demo.py:28`), and it checks only `FLASK_ENV`. It doesn't stop the risky case: a developer machine with `FLASK_ENV=development` whose `.env` points `DATABASE_URL` / `CLOUD_SQL_INSTANCE` at the real database. The local `.env` does set `CLOUD_SQL_INSTANCE` (review of `694c729`). Scripts that `from app import app` or use `models.db` connect wherever `.env` points.
  - 6 scripts write straight to the real Firebase project with `firestore.client()` and `serviceAccountKey.json` (UPG-15).
- **Who benefits:** everyone with an account; stops known-password accounts appearing in production.
- **What to build:**
  - A shared `seed_safety.py` guard called first by every seed/setup script. It exits non-zero unless the target is local: SQLite, `localhost`/`127.0.0.1`, or a Docker `db` host; no `CLOUD_SQL_INSTANCE`; and `FLASK_ENV != production`. An explicit `ALLOW_SEED_TARGET=<database name>` override covers staging.
  - Passwords come from `SEED_<ROLE>_PASSWORD` env vars or are generated with `secrets`, and are printed once at the end.
  - Scripts that talk to Firestore directly also require an explicit project confirmation.
  - Fold the scripts into one seed (with UPG-15).
- **Files touched:** all seed/setup scripts listed above, new `seed_safety.py`, tests.
- **Effort:** S · **Depends on:** none (merging scripts overlaps UPG-15) · **Risk:** low; breaks anyone relying on the published demo logins (they're printed instead).
- **Acceptance criteria:**
  1. Test: an AST scan of every seed/setup script finds no string literal used as a password (dict keys or arguments named like `password`, `password_raw`, `*_PASS`).
  2. Test: running each seed entry point with `DATABASE_URL=postgresql://user@prod-host/db`, with `CLOUD_SQL_INSTANCE` set, or with `FLASK_ENV=production` exits non-zero **before** any database connection (the engine is patched to fail if created).
  3. Test: with a local SQLite `DATABASE_URL`, the seed creates accounts whose passwords come from `SEED_*_PASSWORD` when set, and are random (different across two runs) when not.
  4. Test: `ALLOW_SEED_TARGET` must name the target database exactly; a mismatch still refuses.

---

## 7. Recommended next 3 builds

*(Updated after BLK-09.)*

1. **BLK-01** — The exposure is still live on a public repo (the tracked user DB, history, and current admin credentials in pushed files), and the fix is mostly rotation plus untracking one file. Decide on the unpushed `saptha_fallback.db` change (criterion 0) **before** pushing `master`.
2. **BLK-02** — A one-file fix that closes the easiest account takeover. Every student account is at risk until it lands.
3. **BLK-03** — Payment verification is now re-verified as forgeable on the merged code (empty-key signature, browser-supplied amount and event). Paid events can't go live until the order is fetched and checked server-side.

After these: BLK-04 (small), then the remaining BLK-05 journey coverage and BLK-06 enum columns, then BLK-07 and BLK-08. Then UPG-01 → UPG-02 → UPG-03.

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
