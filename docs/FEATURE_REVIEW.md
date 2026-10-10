# SapthaEvent — Feature Review and Upgrade Plan

**Reviewed:** 2026-09-28 · **Code reviewed at commit:** `694c729` (branch `master`)
**Re-verified after merging BLK-09:** 2026-09-28 at `1f4cdc8` for every item touching `db_adapter.py`, `db_pg.py`, `config.py`, `routes_payment.py` or `tests/conftest.py` (marked "Last verified … `1f4cdc8`"). Other items still describe `694c729`; re-check them before building (see `AGENTS.md` rule 3).
**Phase 0 re-verification (production-ready plan):** 2026-09-30 at `56a014d`, branch `production-ready`. Every item that isn't DONE was re-checked against the code at `56a014d` and now says "Last verified: 2026-09-30, commit `56a014d`". App code changed since `1f4cdc8` only in `db_adapter.py` (root units) and `routes_judge.py` (the `abort` import), so every `file:line` below still points at the right code unless the item says otherwise. New items BLK-12, BLK-13 and UPG-16 to UPG-32 were added, and section 7 lists the phases.
**Re-verification after Phase 1:** 2026-10-02 at `986d108`, branch `production-ready` (rule 8: 13 items DONE since Phase 0). Every item that isn't DONE, plus the summary, feature inventory, journey and event-type tables, was re-checked against the code at `986d108`; those items now say "Last verified: 2026-10-02, commit `986d108`". Each `file:line` was mapped from the item's last-verified commit with an exact line alignment (`difflib`), and every citation that moved or changed was read. The counts behind UPG-19 to UPG-27 were re-run with one script on both `56a014d` and `986d108`, so only real code changes show as differences. Corrections are listed in the 2026-10-02 changelog entry.
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
2. Almost everything after "register" breaks somewhere. Camera QR check-in, certificates, feedback, exports, coordinator assignment, team events and paid events all fail in postgres mode [R]. *(At `986d108`: coordinator assignment works (BLK-09); paid events are verified safely (BLK-03; not yet run against Razorpay test mode, UPG-30); feedback and the certificate page work for the lead (BLK-05 journey test). Camera QR check-in, certificate PDFs, team events and exports are still open. Since UPG-02 (2026-10-07), every scanner checks real tickets in. At the end of Phase 2 (2026-10-08) all of these work on the real database layer: check-in (UPG-02), certificates (UPG-06), exports (UPG-03), teams (UPG-08), feedback (UPG-05), notices and reminders (UPG-31, UPG-07); paid events work in tests but haven't been run against Razorpay test mode (UPG-30).)*
3. Biggest gap 1 — **data loss in the DB adapter:** at `694c729`, postgres mode silently dropped non-column fields, renamed others on read and ignored unknown filters (BLK-06). **Mostly fixed by merging BLK-09 (`1f4cdc8`)** [R]: fields round-trip, filters work, SPOCs can assign coordinators. The rest (enum columns, workflow states, `spoc_id` column, audit actor, newer tables) was fixed by BLK-06 (DONE 2026-10-01).
4. Biggest gap 2 — **security holes that make new features unsafe** (found by `1f4cdc8` [R]; status at `986d108` per line):
   - anyone could log in as any student through the public registration form (BLK-02, **fixed** on `production-ready`);
   - paid events could be confirmed for ₹0 or with a forged payment signature (BLK-03, **fixed**);
   - some endpoints leaked registrations (BLK-04, **fixed**);
   - any SPOC or coordinator could delete any event through a GET link, and `/api/v1` was open to cross-site requests from a logged-in browser (BLK-04, found in Phase 0, **fixed**);
   - login had no rate limiting (BLK-13, **fixed** on `production-ready`);
   - a forged `Host`/`X-Forwarded-Host` made reset and set-password emails link to another site (BLK-16, found in the PR #48 review, **fixed**);
   - any SPOC could end, publish, staff or edit another SPOC's event (BLK-17, **fixed**);
   - any Volunteer account could mark attendance and open tickets at any event (BLK-18, found starting UPG-02, **fixed**);
   - names, titles and messages other people typed ran as script where page scripts built HTML: public leaderboard, calendar and landing page, staff and student pages (BLK-19, found in UPG-02, **fixed**);
   - a user database and old credentials were in the public GitHub history (BLK-01: branches rewritten and force-pushed 2026-10-01; the 47 PR refs wait on GitHub Support).
7. **Not production-ready yet (Phase 0, 2026-09-30):** uploads live on the container's disk (UPG-17; sessions moved to the database, BLK-08), an empty database can't be built through migrations (UPG-16), background jobs need a broker that the Cloud Run target doesn't have (UPG-18, UPG-07), and 111 of 129 templates are standalone pages (UPG-23). Section 7 has the phased plan. *(End of Phase 2, 2026-10-08: nothing live stores files any more (UPG-17 corrected, D-5); scheduled jobs run through the cron endpoint (UPG-07); migrations (UPG-16), inline background tasks (UPG-18) and 107 standalone templates (UPG-23) remain.)*
5. Biggest gap 3 — **the event day still happens outside the app:** the camera scanners reject real ticket QRs and certificates fail to generate [R at `694c729`; not changed by BLK-09]. Departments still need paper sign-in and a separate certificate tool. *(Since UPG-02, 2026-10-07: every scanner, the kiosk and the offline queue check real tickets in through one endpoint; since UPG-06, 2026-10-08, certificates are issued, emailed and verifiable.)*
6. About 20 templates are never rendered, 3 blueprints are never registered, there are 2 parallel notification systems, 2 payment stacks, 13 seed scripts and a diverged copy of the whole app in `functions/saptha_app/` (UPG-14/15).

---

## 2. Feature inventory

Status: WORKING · PARTLY BUILT (says where it breaks) · NOT CONNECTED (code exists, no UI uses it) · MISSING.

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| Home / event discovery / catalogue | WORKING [R] | `app.py:550`, `app.py:739`, crawl 200 | Home shows a hard-coded fake hackathon when no events exist (`app.py:709-720`). |
| University calendar + event `.ics` | WORKING [R] | `app.py:1093`, `app.py:794` | Department-only visibility filter at `app.py:1011-1014`. |
| Personal calendar feed | WORKING [R at BLK-04b] | `app.py:1135-1210`, `services_accounts.py:143,149` | Own events when logged in; calendar apps use a signed, resettable per-user token; `?user=` is ignored (BLK-04). |
| Student sign-up / login | WORKING [R at UPG-35] | `routes_auth.py:272`, `routes_auth.py:66` | USN now persists (document shadow, `db_adapter.py` `extra_json`) [R at `1f4cdc8`]; it wasn't stored at `694c729`. Failed logins and reset requests answer the same for every email (UPG-35); sign-up still tells an existing email to log in. |
| Google / Microsoft login | NOT CONNECTED [C] | `auth_oauth.py:32-135` | Login page has no link to `/auth/google` (`templates/login.html`). |
| 2FA (TOTP) | NOT CONNECTED [C] | `auth_2fa.py:42-155` | No template links to `/auth/2fa/*`. `totp_*` keys now persist [R round-trip at `1f4cdc8`]. |
| Event creation from template (SPOC) | WORKING [R at `1f4cdc8`] | `routes_spoc.py:119-297` | All settings now persist, e.g. a ₹500 fee and team 2–4 (`tests/test_integration_flow.py:56-83`) [R]. Presets only applied for seminar/workshop (`routes_spoc.py:154`). |
| Approval workflow (unit → admin) | WORKING [R] | `services_workflow.py:130-217`, `routes_admin.py:913` | Admin approval sets `published`; SPOC must still move it to `registration_open` (`published` is a closed status, `routes_forms.py:86`). |
| Registration form (custom fields) | WORKING [R at UPG-01] | `routes_forms.py:99-154` | Every form, template, seeded or SPOC-built, is normalised on read: each field has a name and the identity fields appear once. Answers are stored and shown on the responses page (UPG-45 fixed postgres mode). |
| Form builder | WORKING (page load and save [R at BLK-04b]) | `routes_forms.py:353-435` | Only the event's owner (or admins) can edit the form; assigned staff can see responses (BLK-04). |
| Auto-account on registration (no auto-login) | WORKING [R at BLK-02] | `services_accounts.py:37-106`, `routes_forms.py:526-572`, `routes_auth.py:236` | Fixed by BLK-02: no path logs anyone in; existing accounts log in first; new emails get an unverified account and a one-time set-password link; no password is shown or emailed. Since UPG-33 the same goes for walk-ins and for staff and SPOC accounts someone else creates, and reset links work once. |
| Waitlist | PARTLY BUILT [R at BLK-03] | `routes_forms.py`, `routes_waitlist.py:185-300`, `tasks/waitlist_tasks.py` | Promotion on a paid event holds the seat as `pending_payment` with a pay link (BLK-03). Two promotion code paths remain (UPG-14). No SPOC UI link to `/waitlist/list`. |
| Paid registration (Razorpay) | WORKING in tests [R at UPG-30] | `routes_payment.py`, `services_payments.py`, `routes_admin.py:486-560` | Server-side price, recorded orders, single-use payment IDs (BLK-03). A receipt email after payment. Capacity is re-checked at completion; a paid order that can't complete stays paid and is listed for the admin to complete or refund (Razorpay refund with confirmation). A signed `payment.captured` webhook completes registrations whose browser closed. Admins mark registrations refunded or cancelled, and those tickets stop checking in. Not yet run against Razorpay test mode (criterion 4). |
| Stripe payments | NOT CONNECTED [C] | `routes_payment_stripe.py` | No template or JS references `/payment/stripe`. |
| Coupons | NOT CONNECTED in the UI [C] | `routes_coupons.py`, `services_payments.py:36-73` | `create_order` applies a coupon validated on the server if one is sent (BLK-03), but no template or JS sends one or calls `/coupons/*`. Since UPG-36 each order holds a use when it's created (race-free), so `max_uses` holds even when payers check out together. |
| Digital ticket page | PARTLY BUILT [R] | `routes_ticket.py:224-281` | New registrations open; the seeded registration shows "not your ticket" because `is_lead` reads `lead_email` (`routes_ticket.py:243`), which postgres mode returned as `leadEmail` at `694c729`. At `1f4cdc8` the key reads back correctly [R round-trip]; the page wasn't re-run. |
| Camera QR check-in (coordinator, SPOC, HUD) | WORKING [R at UPG-02] | `routes_ticket.py:123-217`, `templates/coordinator/scan.html:238`, `templates/spoc/scan.html:454`, `templates/coordinator/scan_hud.html:340` | Every scanner posts the scanned ticket to `POST /ticket/api/checkin`: signed tokens only, assigned staff only (`can`, BLK-18), one payment rule (free/waived/paid in any case; a free event owes nothing), idempotent with the first check-in time, refuses another event's ticket and a ticket whose event is gone. Tested on the real database and against the page scripts; not yet driven with a phone camera. Scanner list shows events in every event-day status since UPG-43 (built, untested). |
| Manual check-in (SPOC list) | WORKING on event day [R at BLK-05] | `routes_spoc.py:481-555` | Locked until event date (intended). Names read back since BLK-09; BLK-05's journey test checks in through this route on the real database. |
| Kiosk check-in | WORKING in the root app [R at UPG-02] | `routes_checkin.py:236-349`, `templates/public/kiosk.html:700` | Login + coordinator role + `check_in` on the event; search returns no email or phone (BLK-12). Confirm after a name search uses the shared check-in (payment rule, "already checked in at HH:MM"); a USB scanner can scan tickets into the search box (UPG-02). Search results insert names with `innerHTML` (BLK-19). **The `functions/saptha_app` copy's kiosk has no login at all** (BLK-12); removed in Phase 5 (UPG-15, D-1). |
| Venue-QR self check-in | WORKING in the root app [R at BLK-12] | `routes_checkin.py:65-172` | Root app: needs the logged-in owner plus a signed venue code valid for 10 minutes (`routes_checkin.py:86-128`). Pinned on the real database by BLK-12. The `functions/` copy checks in by a typed email alone (removed in Phase 5, UPG-15, D-1). |
| Offline check-in (PWA queue) | WORKING in tests [R at UPG-02] | `static/js/offline-sync.js`, `templates/coordinator/scan_hud.html:13`, `static/sw.js:20` | The HUD queues scans in IndexedDB when offline (one entry per ticket) and replays them to the shared endpoint; repeats answer "already in". Run in Node against the live app, not yet in a phone browser. `/api/v1/.../checkin-batch` is JWT-only with no UI. |
| Coordinator assignment | WORKING [R at UPG-29] | `routes_spoc.py:1187-1250`, `:1253` (remove) | The owner assigns and removes coordinators from the dashboard; another SPOC gets 403. Removing ends access to registrations, exports and check-in (`tests/test_assignment.py`). |
| Judge assignment | WORKING [R at UPG-29] | `routes_spoc.py:1371-1430`, `:1253` (remove) | Writes `staff`; only on events the SPOC manages (BLK-17). Judges are listed and removable in the judges dialog; removing ends scoring. The judge dashboard shows only `active` events (UPG-04). |
| Judge dashboard | PARTLY BUILT [R] | `routes_judge.py:58-59` | Lists only events with status `active`; new workflow states never appear. |
| Judge scoring | PARTLY BUILT [R] | `routes_judge.py:158`, `templates/spoc/create_event.html:1117` | Criteria from the create form are objects; scoring crashes (`'dict' object has no attribute 'replace'` / 500) [R]. Works with string criteria [R]. |
| Rounds, lock scoring, advance round | not re-run [C at `1f4cdc8`] | `routes_spoc.py` round panel / lock / advance | The `spoc_id` gate is now satisfiable (the field persists), so these are likely unblocked; not re-run. |
| AI judge↔team matching | PARTLY BUILT [C] | `routes_ai_matching.py:87-116` | Reads `form_answers`/`team_name`, which persist since BLK-09/BLK-06 [R round-trip]; matching not re-run. |
| Results + public leaderboard | WORKING [R] | `routes_spoc.py:800`, `routes_live.py:161` | Team and lead names read back since BLK-09 [R round-trip]; leaderboard not re-run. |
| Certificates | WORKING [R at UPG-06] | `utils_certificate.py:778`, `tasks/cert_tasks.py:25`, `routes_spoc.py:579,1894` | One issuing path for end-event and the bulk button: a PDF per attendee marked Present (winner certificates for the top three scores), a certificate ID and verify URL on the registration, an emailed PDF; never issued twice. PDFs are drawn again on download, not stored (UPG-17). |
| Certificate public verification | WORKING [R at UPG-06] | `routes_verification.py:21-185` | `/verify/<certificate_id>` shows the issued certificate and offers the PDF; an unknown ID shows invalid (404). Certificates from API v1's `CertificateService` aren't found there (UPG-14). |
| Feedback | WORKING [R at UPG-05] | `routes_feedback.py`, `routes_participant.py:290-340` | Opens after check-in; each attendee (lead or team member) answers once; the event's staff see the summary and export it (others 403). An optional rule requires each person's feedback before their certificate. |
| Hackathon submission + kanban | WORKING (page load) [R] | `routes_hackathon.py:20-206` | Pipeline and project pages are public (`routes_hackathon.py:107,137`). |
| Teams (create/join by code) | WORKING [R at UPG-08] | `routes_teams.py`, `routes_forms.py:156-225` | A team is one registration: the form asks for members within the event's limits, others join with the lead's invite code, the lead removes members and replaces the code; tickets, judging and check-in read its members. |
| Agenda / sessions | WORKING (page load) [R] | `routes_spoc.py:772` | Session-level attendance not found. |
| Announcements | not run [C] | `routes_spoc.py:696-771` | — |
| Email (Brevo / Resend / Gmail) | WORKING in tests [R at UPG-31] | `utils_email.py`, `routes_auth.py:473-478` | Confirmation, day-before ticket with the entry QR, and change and cancellation notices go through Brevo once each (`tests/test_notices.py`, HTTP mocked); not yet sent through a real Brevo account. Notices reach only the registration's lead (UPG-48). Every link in an email comes from `BASE_URL`, never the request's host (BLK-16). No built-in sender or password: the sender is `MAIL_FROM`, else `MAIL_USER`; with neither, Brevo and Resend refuse to send (UPG-41). The SPOC blast email's `spoc_id` gate (`routes_spoc.py:972`) passes for the owner since BLK-09; not re-run. |
| WhatsApp (Twilio) | not run [C] | `utils_whatsapp.py` | Needs a paid Twilio sender. The day-before reminder and the payment receipt tasks call their functions correctly since UPG-31; the automation's WhatsApp channel still doesn't (UPG-49). |
| In-app notifications | PARTLY BUILT [C] | `routes_notifications.py:20` vs `routes_notifications_v2.py:70` | Student dashboard feed reads `notifications`, which nothing writes; every writer uses `notifications_v2`. |
| Scheduled reminders / lifecycle | BUILT [T at UPG-07] | `routes_cron.py:45`, `tasks/scheduled_tasks.py:534`, `.github/workflows/cron.yml`, `docs/DEPLOY.md` | Self-hosted, Celery beat runs them (`docker-compose.yml`); on a single web service, Cloud Scheduler or GitHub Actions calls `POST /internal/cron/<job>` with a shared secret. The lifecycle closes registration and completes past events, and no longer deletes anything. The reminders read every event-day status since UPG-43 (built, untested); the ticket-email signature was fixed in UPG-31. |
| Registration exports (CSV/Excel) | WORKING [R at UPG-03] | `services_export.py`, `routes_spoc.py:346,355`, `routes_coordinator.py:523,533`, `routes_admin.py:285` | One export for SPOC, coordinator and admin: lead name, USN, department, year, email, phone, team, members, attendance, payment, amount, score, rank, certificate ID. 403 without `export_data` on the event. Department and year are inferred from the profile, form or USN when not asked. |
| Admin dashboard / analytics / report | WORKING (page load) [R] | `routes_admin.py:38,123,690` | Figures come from records that keep every field since BLK-06; not re-run. |
| Users page (Super Admin) | WORKING [R at UPG-40] | `routes_admin.py:429-467`, `templates/admin/users.html` | Lists every account with its role and whether it has set a password; resends the set-password link to accounts still waiting (not to Super Admins or accounts with a password), audit-logged. Unpaginated (UPG-19). |
| Org units, scoped roles | WORKING [R at BLK-07] | `routes_admin.py:756-950` | Viewing never migrates; "Migrate roles" previews first, and migrated SuperAdmin and SPOC accounts keep access (BLK-07). |
| Venues, rooms, conflict check | PARTLY BUILT [C] | `routes_admin.py:957-1153`, `routes_spoc.py:1138-1144`, `services_workflow.py:190-218` | Admin CRUD page loads [R]; the create-event form has no room field, so conflicts are only checked on edit/publish. |
| Student portfolio `/u/<usn>` | WORKING [R at `1f4cdc8`] | `routes_portfolio.py:27` | Shows the right student; at `694c729` the ignored `usn` filter showed the Super Admin. |
| XP / gamification leaderboard | not re-run [C] | `routes_gamification.py` | `xp`/`badges` now persist [R round-trip at `1f4cdc8`]; leaderboard not re-run. |
| Referrals | not re-run [C] | `routes_referrals.py:39` | Filters on document-only fields now apply (`tests/test_db_documents.py:95`); referral page not re-run. |
| Teammate matchmaker | Demo only [C] | `routes_matchmaker.py:12,115` | Suggests hard-coded `MOCK_STUDENTS`. |
| Online exams / proctoring | PARTLY BUILT [R at `1f4cdc8`] | `templates/spoc/proctor_monitor.html:1` | SPOC proctor page now 200 [R]; exam flow not run. |
| Privacy (DPDP export/delete/consent) | not run [C] | `routes_compliance.py` | — |
| Audit log | WORKING [R at BLK-06a] | `utils.py` `log_action`, `templates/admin/audit_log.html` | The page shows the actor again (reads the document's `user` key, now preserved). The SQL `actorEmail` column holds the acting user since BLK-06a [R]. |
| REST API v1 (JWT) + multi-tenant control plane | NOT CONNECTED [C] | `routes_api_v1.py` | Only the AI copilot endpoints are called from a template. Finance, analytics, evaluation, certificate and control-plane services are used only here. |
| AI copilot (admin) | not run [C] | `routes_api_v1.py:1466-1507`, `auth_jwt.py:212-242` | Session fallback exists; no Gemini key in sandbox. |
| Android app | Webview wrapper [C] | `capacitor.config.json:5-6` | Loads `https://saptha-portal.railway.app`; no native or offline features. |
| Payment failure page | WORKING [R at `1f4cdc8`] | `templates/payment/failed.html:1` | Now extends `base_classic.html`; 200 [R]. |
| Login rate limiting | WORKING [R at BLK-13] | `services_login_throttle.py`, `routes_auth.py:83-86,337-341`, `routes_api_v1.py:62-88` | 5 failed logins (web + API, one counter) or reset requests per IP and per account per minute, and 20 failed logins per account per hour (UPG-37), then 429 "try again in N seconds"; counters in the database (Redis if `REDIS_URL`), shared by every instance (BLK-13). The old in-memory helpers in `security_middleware.py` are unused (UPG-14). |
| Sessions | WORKING [R at BLK-08] | `session_store.py`, `config.py:49-64` | In the database (Redis if `REDIS_URL`): survive restarts, shared by instances, none for plain anonymous page views (BLK-08). |
| Database migrations | PARTLY BUILT [R at `56a014d`] | `migrations/versions/`, `db_adapter.py:201-326` | Two incremental migrations; `alembic upgrade head` on an empty DB fails. Schema comes from start-up `create_all` + `ALTER TABLE` (UPG-16). |
| File uploads (certificates, exports) | NOT USED by the app [C at end of Phase 2] | `utils_storage.py:10-93` | Nothing live stores files: certificates are emailed and verified from the database (UPG-06), exports are streamed (UPG-03). The helper still writes to local disk unless `STORAGE_TYPE=s3`/`gcs`, and S3 errors silently fall back to it; that matters for UPG-21's backups (UPG-17, D-5). |
| Background jobs | PARTLY BUILT [C at `56a014d`] | `celery_app.py:49-58` | Without a Redis broker, tasks run inline with no timeout or retry (UPG-18). Scheduled jobs run through the cron endpoint since UPG-07. |
| Health check | PARTLY BUILT [C at `986d108`] | `app.py:502-538` | Calls `.stream()` without reading it, so it may not reach the DB; returns exception text (UPG-20). |
| Error monitoring (Sentry) | PARTLY BUILT [C at `56a014d`] | `app.py:124-138` | Initialises when `SENTRY_DSN` is set; untested, not in `.env.example` docs (UPG-20). |
| Database backups | MISSING [C] | — | Nothing in the repo dumps or restores the database (UPG-21). |
| Pagination on web lists | MISSING [C at `56a014d`] | `routes_admin.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_forms.py` | Only `routes_api_v1.py` and `routes_notifications_v2.py` page results (UPG-19). |
| Shared page layout | PARTLY BUILT [C at `56a014d`] | `templates/base_classic.html` | 12 of 129 templates extend it; 111 are standalone pages (UPG-23). |

---

## 3. Journey breakdown per role

*(Traced at `694c729`; steps fixed by Phase 1 were updated in the re-verification of 2026-10-02 at `986d108` and say which item fixed them. Earlier, BLK-09 fixed several steps here: SPOC creation keeps all settings, coordinator assignment, feedback analytics, the payment failure page, the portfolio. See the inventory rows marked `1f4cdc8`; re-trace a journey before building on it.)*

Traced in code and, where marked, run in the sandbox against three SPOC-created events: **Review Seminar** (seminar template), **Review Hackathon** (team 2–4, judging criterion "Innovation"), **Review Cricket** (sports, ₹200). Seeded universal events were checked too.

### Student

| Step | Result | Where it breaks / leaves the app |
|---|---|---|
| Discover | OK [R] | — |
| Register (solo) | **Works** [R at UPG-01] | Every template's form names its fields and asks for name, email, phone and USN once; the seeded conference registers end to end. |
| Register (team) | **Works** [R at UPG-08] | The form asks for the team name and members within the event's limits; teammates join with the lead's code (`tests/test_teams.py`). |
| Pay | **Works in tests** (BLK-03, UPG-30) | Charged at the server's price; a receipt email; a webhook completes payments whose browser closed; a paid order that can't complete stays paid for the admin to complete or refund. Not yet run against Razorpay test mode (UPG-30 criterion 4). |
| Ticket | OK for new registrations [R] | QR hidden until 1 day before (intended, `routes_ticket.py:143-152`). The day before, the ticket email brings the same QR, and a WhatsApp reminder goes out (UPG-31, through UPG-07's cron). Changes of date, time or venue, and cancellation, are emailed once. No payment reference stored. |
| Check-in | **Works** [R at UPG-02] | The ticket's QR is accepted by every scanner; see Coordinator. |
| Attend sessions | Not found | No session-level attendance. |
| Submit work (hackathon) | Page loads [R] | — |
| See results | OK [R] | Names read back since BLK-09 [R round-trip]. |
| Feedback | **Works** [R at UPG-05] | Every checked-in attendee, team members included, answers once; the SPOC dashboard links the summary and its CSV export. |
| Certificate | **Works** [R at UPG-06] | The page shows the name and links the official PDF; it's emailed when the event ends, and `/verify/<id>` confirms it. |
| Portfolio | **Fixed** [R at `1f4cdc8`] | `/u/<usn>` shows the right student. |

### SPOC / organiser

| Step | Result | Where it breaks |
|---|---|---|
| Create event (seminar / hackathon / sports) | Created [R] | All settings persist since BLK-09 [R]. Sports gets no fixtures (MISSING, UPG-13). |
| Build form | Page OK [R] | — |
| Publish (pending → approve → open) | OK [R] | Two steps after approval; not obvious from the UI copy. |
| Manage registrations / waitlist | Partly [R] | Exports work since UPG-03 (CSV and Excel with every column); no waitlist screen. |
| Assign coordinators / judges / rooms | Judges and coordinators: assign and remove [R at UPG-29]; rooms not re-run | Tested end to end (`tests/test_assignment.py`). |
| Run the day | QR scans and the manual list [R at UPG-02] | Scans go through the shared check-in; the manual list still uses its own route (UPG-14); the blast email's `spoc_id` gate (`routes_spoc.py:963`) passes for the owner since BLK-09 (not re-run). WhatsApp groups used instead. |
| Results | Publish OK [R]; lock/advance not re-run | Their `spoc_id` gates (`routes_spoc.py:1652,1673`) pass for the owner since BLK-09. |
| Certificates | **Works** [R at UPG-06] | Ending the event or the bulk button issues each attendee's certificate once, through one path. |
| Report | **Event report** [R at UPG-03] | One click on the SPOC dashboard: registered vs present by department and year, feedback average, winners (Excel). The AI report still needs a Gemini key. |

### Coordinator / volunteer

| Step | Result | Where it breaks |
|---|---|---|
| Get assigned | OK [R at UPG-29] | The event appears on the coordinator's dashboard; removal by the SPOC ends access (`tests/test_assignment.py`). |
| Scan tickets | **Works** [R at UPG-02] | Coordinator, SPOC and HUD scanners and the kiosk use `POST /ticket/api/checkin` (`tests/test_checkin_unified.py`). The scanner list and walk-in form show events in every event-day status since UPG-43 (built, untested). |
| Walk-ins | Works [R at UPG-33] | `routes_coordinator.py:549-632`; needs `manage_registrations` on the chosen event (BLK-04a). A new walk-in gets the ticket and a one-time set-password link, never a password (`tests/test_account_emails.py`). |
| Attendance (granular) | **Fixed** (BLK-04a) [R] | `routes_coordinator.py:759-761` needs `check_in` on the event; students and unassigned coordinators get 403 (`tests/test_coordinator_authz.py`). |
| Offline | **Works in tests** [R at UPG-02] | The HUD queues scans offline and replays them to the shared check-in without duplicates (run in Node against the live app). |

### Judge

| Step | Result | Where it breaks |
|---|---|---|
| See assigned events | **Broken** for new workflow states [R] | `routes_judge.py:59` filters `status == 'active'`. Judge needs a direct link. |
| Score with rubric | **Broken** with form criteria [R]; OK with string criteria [R] | `routes_judge.py:158`. Only attendees marked Present are listed (`routes_judge.py:104-105`), so this depends on check-in. |
| Locking | not re-run | The SPOC lock's `spoc_id` gate passes for the owner since BLK-09 (UPG-04 criterion 4). |
| Conflicts of interest | MISSING | No declaration or recusal found. |

### Super Admin

| Step | Result | Where it breaks |
|---|---|---|
| Departments / clubs (org units) | Works [R at BLK-07] | Viewing never migrates; migration previews first and keeps everyone's access (BLK-07). |
| Approvals | OK [R] | — |
| Users / roles | Role assignment page OK [R]; `/admin/users` lists accounts and resends set-password links (UPG-40) [R]; the dead `/admin/events` link is gone from every template [C at `986d108`] | Other dead links: UPG-15. |
| Calendar | OK [R] | — |
| Analytics / exports | Pages OK [R]; exports not re-run | Names read back since BLK-06 [R round-trip]; UPG-03. |
| Bulk student import | MISSING | UPG-10. |

---

## 4. Event-type coverage

"Works today" is in postgres mode as verified at `694c729`. BLK-09 (`1f4cdc8`) removed most of the BLK-06 field loss these rows depended on; re-check a row before relying on it. Re-checked 2026-10-02 at `986d108`: every BLK item named here is DONE, so "Needed" lists only UPG items.

| Event type | Works today | Done outside the app | Needed |
|---|---|---|---|
| Seminar | Create from template, approval, free registration (any form, UPG-01), ticket, QR and manual check-in (UPG-02), certificates (UPG-06), attendance export and event report (UPG-03), feedback (UPG-05), calendar | — | — |
| Workshop | Same as seminar; preset applied (`routes_spoc.py:154`) | Same; paid workshops: payments are verified safely since BLK-03, not yet run against Razorpay test mode | + UPG-30 |
| Guest lecture | Same as seminar (no own template) | Speaker invite and attendance list | Seminar items |
| Hackathon | Create, judges, project submission page, scoring with string criteria, leaderboard, QR check-in (UPG-02), winner and participation certificates (UPG-06), team registration with invite codes (UPG-08) | Rubric scoring, round shortlists | UPG-04 |
| Sports | Create, registration (teams since UPG-08), leaderboard page | Fixtures, match results, standings (whiteboard/Excel) | UPG-13 |
| Cultural | Template exists (`services_templates.py:494`); judging as hackathon; certificates (UPG-06) | Slots, judging sheets | UPG-04 |
| Club activities | Org units can be clubs (`routes_admin.py:812`) | Membership lists, recurring meetings, attendance across the year | UPG-11 (ledger); membership not yet listed |
| Placement drives | Generic registration only | Eligibility (branch / CGPA / backlogs), shortlists per round, company communication — all Excel | UPG-57 (eligibility rules + shortlist rounds) |
| FDPs | Registration creates a **Student** account (`services_accounts.py:59,66`, used at `routes_forms.py:571`) | Faculty registration, multi-day attendance, hours on certificate | UPG-12, UPG-11 |
| NSS / NCC | Category kept as `NSS` / `NCC` since BLK-06a | Volunteer hours register, unit rolls, hours certificates | UPG-11 |
| Department events | Department-only visibility (`app.py:1011-1014`), unit approval [R] | Same as seminar | Seminar items |
| Conference / webinar | Templates exist; their forms work since UPG-01 [R] | External attendee registration | UPG-12 |

---

## 5. Upgrade recommendations

**Order of work:** all BLK items (section 6) come before any UPG item (see `AGENTS.md` rule 2). Within each group, items are ranked by manual work removed for the most people, then by lowest effort.

### A. Finish what's half-built

#### UPG-01 — Registration forms render every template field and always ask for identity
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-01: …" on `production-ready` (parent `2a69b17`)
- **Problem:** Template and seeded forms store `field_name` (`services_templates.py` `form_config`; seeded `event_forms` rows), but `templates/public/registration_form.html:405,425,443,485` render `name="{{ field.id }}"`. Inputs get `name=""`, and there's no name or email field, so submissions fail [R]. The SPOC path patches `id` only for its own preset (`routes_spoc.py:252-256`).
- **Who benefits:** every student registering for a seeded or template-created event, plus organisers who otherwise fall back to Google Forms.
- **What to build:** normalise the schema in one place (`_get_form` in `routes_forms.py`) so every field has an `id`; always prepend the identity fields (full_name, email, phone, usn) once; add a check that fails form save if any field lacks an id.
- **Re-checked before building (2026-10-08, `b5afda8`; rule 3):** the form files were unchanged since `986d108` apart from UPG-03's one line. Two findings:
  - The broken forms come from `TemplateService.instantiate_event` (API v1's create-from-template) and the seeder, which store the template's `field_name` fields with no identity fields. The SPOC's own create path already adds both (`routes_spoc.py:267-282`).
  - Criterion 2 found that the SQL adapter dropped the answers' envelope; recorded and fixed first as **UPG-45**.
- **What was built:**
  - **One normaliser on read: `normalise_fields` (`routes_forms.py:103`), used by `_get_form` (`:129`).** Every field gets an `id` (else its `field_name`); layout fields without one get `layout_N`; duplicate ids are dropped. Full name, email, phone and USN (`IDENTITY_FIELDS`, `:87`) are prepended once unless the form already asks for them under that id or a known synonym (`name`, `email_address`, `mobile`, `roll_number`, …).
  - The registration page, submission, validation, builder and schema API all read through `_get_form`. So stored forms, old and seeded included, are fixed without rewriting them; the template and `services_templates.py` need no change.
  - **Saving refuses an input field with neither `id` nor `field_name`** (400 naming the field, `:312`) instead of inventing `field_N`. A `field_name` becomes its id.
- **Files touched:** `routes_forms.py`, `tests/test_registration_forms.py` (new). (`templates/public/registration_form.html` and `services_templates.py` needed no change.)
- **Effort:** S · **Depends on:** BLK-02, BLK-06, UPG-45 (found here) · **Risk:** low; existing SPOC forms already carry `id`.
- **Acceptance criteria** (`tests/test_registration_forms.py`, real database layer; all 10 cases fail on the old code):
  1. ✅ Test: `GET /forms/register/<event from each of the 7 templates>` has no `name=""` input and contains `name="email"` exactly once (`::test_every_template_form_names_its_fields_and_asks_for_email_once`, one case per template, made the way API v1 makes them; every template field and all four identity fields are named).
  2. ✅ Test: submitting a template form stores the answers and they are read back from `form_submissions` for the responses page (`::test_a_template_form_submission_is_stored_and_shown_on_the_responses_page`, hackathon template).
  3. ✅ Test: saving a form with a field that has neither `id` nor `field_name` returns 400 (`::test_saving_a_field_with_no_id_is_refused`; the stored form is unchanged, and a `field_name`-only field saves under that id).
  4. ✅ A student can register for the seeded conference event through the UI (`::test_a_student_registers_for_the_seeded_conference_through_the_ui`: `seed_universal_portal`, the student opens the form, submits it and pays through the simulated checkout).
  - Full pytest: **842 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-02 — QR check-in that works with real tickets, for assigned coordinators only
- **Status:** DONE
- **Last verified:** 2026-10-07, commit "UPG-02: …" on `production-ready` (parent `5c54cb8`)
- **Problem:** Three scanners, three broken paths [R]:
  - `templates/coordinator/scan.html:231-234` sends the signed token to `/coordinator/get_ticket/` → "INVALID TICKET".
  - `templates/spoc/scan.html:447-458` sends it to `/spoc/api/checkin/` → 404.
  - `scan_hud` → `/ticket/api/verify` blocks free tickets as "Payment pending" (`routes_ticket.py:479-481`; same gate at `:270-271`).
  - The offline queue replays to kiosk confirm (`static/js/offline-sync.js:83`), which answers 403 to coordinators not assigned to the event. Assigned ones can confirm: assignment works since BLK-09, and BLK-12 pins kiosk access. Re-checked at `986d108`: `/coordinator/get_ticket` now answers only staff who can check in at the event (BLK-04a, `routes_coordinator.py:895`), but it still looks the scanned token up as a registration ID, so real QRs still get "INVALID TICKET".
  - Found in BLK-12 [C]: the `/ticket/verify` POST skips the per-event check when the registration's event no longer exists (`if db_exists and event and not can_checkin`, `routes_ticket.py:325`), so any coordinator-level role could mark an orphaned registration present. Deleting an event removes its registrations, so this is rare; the unified endpoint must refuse when the event is missing.
- **Who benefits:** every coordinator and volunteer on event day; removes paper sign-in sheets.
- **What to build:** one check-in endpoint, shared by the coordinator, SPOC and kiosk screens, that accepts the signed token only (`routes_ticket._parse_signed_token`), authorises with `can(session, 'check_in', event)`, applies a payment rule on the normalised status (free/waived/paid, any case), is idempotent, and returns name, team and the first check-in time. Point all three scanners and the offline queue at it. Offline scans queue in the browser (IndexedDB, `static/js/offline-sync.js`, registered by `static/sw.js`) and sync later without duplicates. Make kiosk name search use the corrected keys.
- **Re-checked before building (2026-10-07, `2db0db1`; rule 3):** BLK-16 shortened `routes_ticket.py` above the cited code (the payment gates were at `:257,318,466,521` and the missing-event skip at `:311`); the claims hold. Also found:
  - `can()` gave every Volunteer `check_in` on every event. Recorded and fixed first as **BLK-18**, so the endpoint's `can()` check means assigned staff only.
  - The HUD scanner sent a read-only GET with the whole scanned link, so it never marked anyone present. Its offline queue was never loaded (`offline-sync.js` was included only by the shared layout).
  - The kiosk's search box was `readonly`, so a USB scanner couldn't type into it.
- **What was built:**
  - **One check-in, `routes_ticket.check_in` (`routes_ticket.py:123`).** It needs a logged-in user (401 otherwise) and the registration (404). Its event must exist (404: the BLK-12 gap is closed). The user needs `can(…, 'check_in', event)` (403). An `event_id` from the scanner must match the ticket's event (409 `wrong_event`).
    - A repeat changes nothing and answers `already_in`, "Already checked in at HH:MM.", with the first time.
    - Payment uses `payment_allows_entry` (`:100`): free, waived, exempt, completed and anything starting with "paid", in any case, may enter. On an event with a fee, anything else is refused (402 `unpaid`); on a free event nothing is owed.
    - It marks `Present` with the time and who scanned, updates the wallet ticket, awards the XP and audit-logs `CHECKIN`.
    - It returns name, team, room, first check-in time, registration ID and member names and USNs (no emails or phones).
  - **The endpoint: `POST /ticket/api/checkin` (`:200`).** It takes `{token, event_id}` in the body, so the token stays out of URLs and logs. It accepts the ticket-page link or either signed token format (`_token_from_scan`, `:113`, then `_parse_signed_token`), and refuses registration IDs with 400.
  - **Every scanner and desk uses it:**
    - the coordinator scanner (`templates/coordinator/scan.html:238`), which then shows the team so member attendance can be adjusted;
    - the SPOC scanner's QR path (`templates/spoc/scan.html:452`); its manual list still uses `/spoc/api/checkin`, see UPG-14;
    - the HUD (`templates/coordinator/scan_hud.html:340`), which now loads the offline queue (`:13`) and sends a CSRF token;
    - the kiosk, when a USB or camera scanner types a ticket into the search box (`templates/public/kiosk.html:699`; the box takes typing with `inputmode="none"`, `:509`).
  - **The other routes use the shared function.** `/ticket/verify` POST (`:426`), `/ticket/api/verify` POST for registrations (`:557`) and kiosk confirm after a name search (`routes_checkin.py:341`) all call it. Their GET checks use the same payment rule, and their response keys are kept.
  - **The offline queue (`static/js/offline-sync.js`).** It stores each ticket once in IndexedDB and replays to the endpoint with the CSRF token. An item leaves the queue on any final answer (checked in, already in, refused); it stays after a network error, an expired login or a 5xx. Old queued items are still read. `static/sw.js:20` precaches the script (cache `v4`).
  - **Small fixes in the same flows.** Saving member attendance keeps the first check-in time (`routes_coordinator.py:926`). The SPOC scanner's rows carry the ticket's ID, so a scan updates the right row (`routes_spoc.py:445`). The kiosk's search keys were already right since BLK-06/09; criterion tests pin them.
- **Files touched:** `routes_ticket.py`, `routes_checkin.py`, `routes_coordinator.py`, `routes_spoc.py`, `templates/coordinator/scan.html`, `templates/coordinator/scan_hud.html`, `templates/spoc/scan.html`, `templates/public/kiosk.html`, `static/js/offline-sync.js`, `static/sw.js`, `tests/test_checkin_unified.py` and `tests/js/offline_sync_harness.js` (new).
- **Effort:** M · **Depends on:** BLK-04, BLK-06, BLK-12 · **Risk:** event-day critical path. Two concurrent first scans of one ticket both answer "Entry granted" (no transaction in the adapter); attendance is still right. The scanner pages weren't driven in a real browser: their scripts were parsed with Node, and the endpoint, the routes and the offline queue were tested.
- **Acceptance criteria** (`tests/test_checkin_unified.py`, real database layer; all 20 cases fail on the old code):
  1. ✅ Test: token taken from the ticket page, scanned by the assigned coordinator → attendance `Present`; a second scan → "already checked in at HH:MM" with the first scan's time (`::test_the_ticket_page_qr_checks_in_once_and_a_rescan_reports_the_first_time`; the token is what the page's QR encodes; saving member attendance afterwards keeps the time).
  2. ✅ Test: an unassigned coordinator and a student both get 403 (`::test_unassigned_staff_students_and_visitors_cant_check_in`; a visitor gets 401).
  3. ✅ Test: a free registration (`Free` or `free`) is never reported as unpaid; an unpaid paid registration is refused (`::test_free_waived_and_paid_registrations_are_let_in_in_any_case` with 7 spellings, also on both GET checks; `::test_an_unpaid_registration_on_a_paid_event_is_refused` for Pending, unpaid, Refunded and none; `::test_no_status_on_a_free_event_is_free`).
  4. ✅ Test: replaying an offline queue of 3 tokens marks 3 attendees present; replaying the same queue again changes nothing and reports each as already checked in (`::test_replaying_an_offline_queue_twice_checks_each_in_once`). Also `::test_the_browser_queue_sends_each_scan_once_and_replays_safely`, which runs `offline-sync.js` itself in Node against a live copy of the app: 3 tickets, one scanned twice, are queued once, sent as 3 posts, then replayed as "already in"; a scan made while the server is unreachable stays queued. It's skipped where Node isn't installed; CI's test job has no Node.
  5. ✅ Test: the coordinator, SPOC and kiosk scanner pages all call the same endpoint (template check), and a raw registration ID is refused there (`::test_every_scanner_calls_the_one_endpoint_and_it_refuses_registration_ids`; the HUD and the offline queue too; none of the scan handlers calls an old by-ID route).
  - Also tested: a ticket whose event is gone is refused by all three POST routes (`::test_a_ticket_whose_event_is_gone_is_refused_everywhere`), another event's ticket is refused at this event's scanner, and kiosk name search finds by name, team, member and USN and confirms once.
  - Full pytest: **782 passed** on SQLite and PostgreSQL 16; ruff clean; bandit exit 0.

#### UPG-03 — Exports and an event report with real participant data
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-03: …" on `production-ready` (parent `f964a34`)
- **Problem:** `/spoc/export_csv`, `/coordinator/export_registrations`, `/forms/responses/export` and `/admin/analytics/export/registrations` all downloaded files with empty name, email, phone and USN columns in postgres mode at `694c729` [R]. The cause (renamed keys) is fixed by BLK-09, so re-run the exports before building; the unified export service and event report are still needed. There is no deterministic post-event report. The AI report's `spoc_id` gate (`routes_spoc.py:816`) passes for the event's owner since BLK-09, but the report needs a Gemini key.
  - Already in place [C at `986d108`]: `/spoc/export_csv` (`routes_spoc.py:325`), `/coordinator/export_registrations` (`routes_coordinator.py:548`) and `/coordinator/export_excel` (`:603`) check `export_data` on the event and re-raise the 403 from their `except` blocks. `/forms/responses/export` does the same since BLK-04b, and `/admin/analytics/export/<kind>` is SuperAdmin-only (`routes_admin.py:283-285`). Only the forms export's 403 is tested (`tests/test_forms_feed_api_authz.py:42`), so criterion 2 still needs tests for the other three.
- **Who benefits:** every organiser and HoD; replaces the Excel re-typing and hand-written IQAC/NAAC event reports.
- **What to build:** one export service (CSV and Excel) used by SPOC, coordinator and admin, with columns for name, USN, department, year, email, phone, team, attendance, payment status and amount, score, rank and certificate ID. Each person can export only the events they're allowed to see. Add a one-click event report (XLSX/PDF): registrations vs attendance by department/year, feedback averages, winners. No AI needed.
- **Re-checked before building (2026-10-08, `f964a34`; rule 3):** the routes moved (SPOC export at `routes_spoc.py:334`, coordinator at `routes_coordinator.py:531,586`). Two claims above were wrong:
  - `/coordinator/export_excel` didn't re-raise its 403: its `except` turned it into a flash and a redirect.
  - Every export route's role gate (`ClubSPOC`, coordinator roles, form-builder roles, Super Admin) sent other roles, students included, to the login page (302), so criterion 2's 403 needed the role gates replaced by the per-event check.
  - Department and year aren't stored on registrations. The export takes the user's profile department, else the form's answer, else the branch code in the USN, and the form's year answer, else the batch in the USN (`1SN22CS…` → 2022).
- **What was built:**
  - **`services_export.py` (new).** One row per registration in fixed columns: ticket ID, lead name, lead USN, department, year, lead email, lead phone, team, other members, attendance, check-in time, payment status, amount, score, rank, certificate ID, registered at (`COLUMNS`, `:15`). Lead columns keep the SPOC CSV's existing `Lead Email` header, which a test pins.
    - Score is the published final score, else the judges' average; rank is the published rank, else by average.
    - CSV and Excel writers quote a cell that a spreadsheet would run as a formula (a name starting with `=`), but leave numbers like `+91 98…` alone.
    - `event_report` and `event_report_xlsx` (`:147`, `:184`) build the report sheets: summary (registered, present, attendance %, feedback responses and average rating), by department, by year, winners (top three) and all registrations. No AI.
  - **Routes.** SPOC CSV, a new SPOC Excel and the new event report (`routes_spoc.py:346,355,364`), the coordinator's CSV and Excel (`routes_coordinator.py:518,528`) and the admin's all-events registrations CSV (`routes_admin.py:285`) all use the service.
  - **Permissions.** Each per-event route needs only a login and `export_data` on the event (`_event_or_abort`), so anyone else gets 403. The forms export drops its role gate the same way (`routes_forms.py:654`). The admin export answers 403 to anyone but a Super Admin (`routes_admin.py:289`).
  - **SPOC dashboard.** It links the report and both exports for each event (`templates/spoc/dashboard.html:1947`).
- **Files touched:** `services_export.py` (new), `routes_spoc.py`, `routes_coordinator.py`, `routes_admin.py`, `routes_forms.py`, `templates/spoc/dashboard.html`, `tests/test_exports.py` (new).
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** PII in exports; they stay behind `can(..., 'export_data', event)`. Department and year are inferred when the form doesn't ask; the student roster import (UPG-10) would make them exact.
- **Acceptance criteria** (`tests/test_exports.py`, real database layer; all 6 cases fail on the old code):
  1. ✅ Test: exporting an event with 2 registrations (one team, one paid) yields 2 rows with non-empty name, email, phone, team, attendance and payment columns, in both CSV and Excel (`::test_every_export_gives_both_registrations_with_real_columns`: SPOC and coordinator, CSV and Excel, plus the admin's all-events CSV. It also checks department, year, members, score, rank, certificate ID and amount, and the formula quoting).
  2. ✅ Test: a SPOC of another unit, an unassigned coordinator and a student each get 403 on every export route (SPOC, coordinator, forms, admin) (`::test_nobody_without_export_rights_gets_any_export`, 7 routes each, including the report).
  3. ✅ Test: the event report's attendance count equals the number of `Present` registrations (`::test_the_report_counts_attendance_by_department_and_year`; also the department, year, feedback and winners sheets).
  4. ✅ An organiser can download the report from the SPOC dashboard (`::test_the_organiser_downloads_the_report_from_the_dashboard`).
  - Full pytest: **826 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-04 — Judging works for rubric criteria from the create form and for new workflow states
- **Status:** IN PROGRESS (criterion 5 met in `4699478`; 1–4 open)
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** The create form saves criteria as `{name, description, max_score}` (`templates/spoc/create_event.html:1117`). `submit_score` calls `c.replace` (`routes_judge.py:158`) and `score_inline` uses the dict as a key → errors / 500 [R]. The judge dashboard lists only `status == 'active'` (`routes_judge.py:59`), so events in `registration_open`, `in_progress` or `evaluation` never show up [R]. There's no max-score validation. The missing `abort` import in `routes_judge.py` (a pre-existing `master` bug, where an unassigned judge got a swallowed `NameError` instead of a 403) was **fixed in `4699478`** at the owner's request, as part of finishing BLK-09. It's pinned by `tests/test_integration_flow.py::test_unassigned_judge_gets_403_and_nothing_is_saved`.
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
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-05: …" on `production-ready` (parent `c35bd09`)
- **Problem:** At `694c729` students were told "Unauthorised access." on `/feedback/submit/<reg>` and `/participant/feedback/<reg>`, because both read `lead_email` [R]. Re-checked at `56a014d` [C]:
  - `/feedback/submit/<reg>` is already a 307 redirect to `/participant/feedback/<reg>` (`routes_feedback.py:30-33`, from the BLK-09 merge), so there's one student route. No test pins the redirect.
  - The student route still checks `lead_email` only (`routes_participant.py:290`), so team members can't give feedback. For the lead it works on the real database: BLK-05's journey test opens and submits it (`tests/test_event_journey_real_db.py:74-77`), so criterion 1 is met except the read-back on `/feedback/view/<event>`.
  - It doesn't check that the student attended, and a second POST overwrites the stored `feedback` on the registration (`routes_participant.py:296-337`).
  - `/feedback/view` redirects to `/feedback/analytics`, which returns 200 [R at `1f4cdc8`].
- **Who benefits:** every attendee and organiser; replaces Google Forms feedback.
- **What to build:** feedback that opens only after check-in, one response per person (lead or team member), a SPOC summary page with a CSV export, and an option to require feedback before the certificate is issued.
- **Re-checked before building (2026-10-08, `c35bd09`; rule 3):** still as described. Also found:
  - `/feedback/analytics` and `/feedback/summary` checked only the role, so any SPOC or coordinator could read any event's feedback, comments and names included. The owner-only summary needed a per-event check anyway.
  - The single `feedback` field on a registration gave team members nowhere to answer.
- **What was built:**
  - **One response per person**, each its own document in `feedback_responses` (`routes_feedback.py:34`), keyed by event, registration and email. The lead's answer is also kept on the registration, where the certificate rule and older responses are read. `event_responses` (`:48`) gathers both, so responses from before still count once.
  - **The student route** (`routes_participant.py:290-340`) is open to the lead and the registration's team members; anyone else gets 403 (`:301`). It opens only once the registration is checked in, and not for a member marked absent at the door (`:303`). A second answer from the same person is refused and the first stays (`has_responded`, `routes_feedback.py:41`).
  - **The summary and export are for the event's staff only.** `/feedback/analytics` and `/feedback/summary` need `view_analytics` on the event (`:94`, `:139`). The new `/feedback/export/<event>` (`:162`) needs `export_data`: one CSV row per response (time, name, email, team, rating, sentiment, tags, comments), through UPG-03's CSV writer. The analytics page links the export; the SPOC dashboard links the summary.
  - **"Require feedback before the certificate"** (the event's workflow rule) now asks each person for their own answer (`routes_participant.py:225`).
- **Files touched:** `routes_feedback.py`, `routes_participant.py`, `templates/feedback/analytics.html`, `templates/spoc/dashboard.html`, `tests/test_feedback.py` (new).
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria** (`tests/test_feedback.py`, real database layer; 6 of 7 fail on the old code, and criterion 4's redirect already existed):
  1. ✅ Test: the attendee `GET`s the feedback form → 200, `POST` → saved, read back on `/feedback/view/<event>` (200) (`::test_an_attendee_sends_feedback_and_staff_read_it_back`).
  2. ✅ Test: `/feedback/analytics/<event>` returns 200 with 0 and with 3 responses (`::test_the_summary_works_with_no_responses_and_with_three`; the three are a team's lead and two members; the JSON summary averages them).
  3. ✅ Test: a non-owner student gets 403 (`::test_someone_not_on_the_registration_gets_403`).
  4. ✅ Test: `/feedback/submit/<reg>` redirects to the single route (`::test_the_old_submit_url_redirects_to_the_one_route`).
  5. ✅ Test: an attendee who isn't checked in can't submit; a second submission by the same person is refused and doesn't change the stored response (`::test_feedback_needs_check_in_and_each_person_answers_once`; also a member marked absent).
  6. ✅ Test: the SPOC summary export returns one CSV row per response, for the event owner only (`::test_the_export_has_one_row_per_response_for_the_events_staff_only`: another SPOC and a student are refused; another SPOC also gets 403 on the analytics and summary).
  - Also: `::test_the_certificate_rule_asks_each_member_for_their_own_feedback`.
  - Full pytest: **878 passed** on PostgreSQL 16, **877 passed and 1 skipped** on SQLite; ruff clean.

#### UPG-06 — Certificates generate with the right name and can be issued in bulk
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-06: …" on `production-ready` (parent `816808c`)
- **Problem:** (the signature mismatch is re-checked unchanged at `1f4cdc8` [C]; the name and bulk-gate bullets were caused by BLK-06 and are likely fixed, not re-run)
  - `tasks/cert_tasks.py:44-50` calls `generate_certificate_pdf(reg_id=, name=, event_date=, venue=)`, but the signature is `(student_name, event_title, reg_id, cert_type, ...)` (`utils_certificate.py:145`). End-event certificate generation fails with a `TypeError` [R].
  - The certificate page reads `lead_name` (`routes_participant.py:230`) → "presented to None" [R at `694c729`]. Fixed: the key persists since BLK-09, and BLK-05's journey test checks that the page shows the name.
  - Bulk send's `spoc_id` gate (`routes_spoc.py:1900`) passes for the owner since BLK-09; not re-run (criterion 4).
- **Who benefits:** every attendee; removes the separate certificate tool.
- **What to build:** fix the call signature; one issuing path (end event or button) producing a PDF per attendee with a stored certificate ID and verify URL; emailing on top.
- **Re-checked before building (2026-10-08, `816808c`; rule 3):** only `routes_spoc.py` changed since `986d108` (BLK-17's ownership checks). The signature mismatch was still there. Also found:
  - three certificate stores: the PDF generator wrote `verified_certificates/<hash>` as a side effect of drawing; `CertificateService` writes `certificates/<id>`, which `/verify` never reads (API v1 only; added to UPG-14);
  - end-event's fallback and the bulk button each re-sent every certificate on every run;
  - the email's verify link used the registration ID;
  - `/verify/<id>/download` re-drew the PDF with a recomputed hash, so its QR pointed at a record that didn't exist.
- **What was built:**
  - **One issuing path, `utils_certificate.issue_event_certificates` (`utils_certificate.py:778`).** For each registration marked Present that has no certificate yet, it renders the PDF (the event's uploaded template, else the built-in design) and records `verified_certificates/<certificate_id>`. It then stores `certificate_id`, `certificate_verify_url`, `certificate_type` and the time on the registration, and emails the PDF.
    - The top three scored attendees get a winner certificate instead of participation.
    - A rerun issues nothing twice.
    - It returns counts (issued, emailed, already issued, not present, failed).
    - The certificate ID is `certificate_id_for(...)` (`:145`), the hash the generator used before.
  - **End-event and the bulk button share it.** End-event queues `tasks.cert_tasks.bulk_generate_certificates` (`tasks/cert_tasks.py:25`, inline without a broker), which calls it, or calls it directly if queueing fails (`routes_spoc.py:570`). The bulk button calls it directly (`routes_spoc.py:1868`) and now uses BLK-17's `_event_or_abort(…, 'issue_certificates')`. The broken per-registration task and the two old send-all functions are gone.
  - **Drawing only draws.** `generate_certificate_pdf` takes `certificate_id` (`:164`) for the QR and footer and no longer writes records. The download route passes the stored ID (`routes_verification.py:177`), and the email links `/verify/<certificate_id>` (`utils_email.py:788`).
  - **The attendee's certificate page** links the official PDF and the verification page when one was issued (`routes_participant.py:232`).
- **Files touched:** `utils_certificate.py`, `tasks/cert_tasks.py`, `routes_spoc.py`, `routes_verification.py`, `routes_participant.py`, `utils_email.py`, `templates/participant/certificate.html`, `tests/test_certificates.py` (new).
- **Effort:** M · **Depends on:** BLK-06 (was also UPG-05; the "require feedback first" option belongs to UPG-05, so certificates don't wait for it) · **Risk:** PDF rendering on free-tier memory: about 0.1 s per certificate here, done inline when there's no broker (UPG-18 adds timeouts). PDFs aren't stored: `/verify/<id>/download` draws them again from the record (object storage is UPG-17).
- **Acceptance criteria** (`tests/test_certificates.py`, real database layer; all 3 fail on the old code):
  1. ✅ Test: ending an event with 2 Present and 1 Absent attendee creates exactly 2 certificates without exceptions (eager Celery) (`::test_ending_the_event_issues_exactly_one_certificate_per_attendee`). It also checks: the scored attendee gets a winner certificate; the records and registrations hold the ID and verify URL; each attendee gets one email with a PDF and the right verify link; the absent one gets nothing.
  2. ✅ Test: the certificate page shows the attendee's name (`tests/test_event_journey_real_db.py:80-84`, BLK-05; it also checks there's no ">None<").
  3. ✅ Test: `/verify/<certificate_id>` shows valid; a random ID shows invalid (`::test_verify_shows_an_issued_certificate_and_refuses_a_random_id`; the PDF downloads, and the attendee's page links it).
  4. ✅ The SPOC "bulk certificates" button succeeds for the event owner (`::test_the_bulk_button_issues_through_the_same_path_once`: 2 issued; pressing again or ending the event afterwards issues and emails nothing more; another SPOC gets 403).
  - Full pytest: **820 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-07 — Reminders and lifecycle jobs run on free-tier hosting
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-07: …" on `production-ready` (parent `125f7f7`)
- **Problem:** Reminders, the day-before QR email and lifecycle transitions are Celery beat jobs (`celery_app.py:95-120`). Since BLK-09, `docker-compose.yml:27-37` runs a Celery worker and beat for self-hosting. But the Dockerfile (what a single free-tier web service runs) starts only gunicorn (`Dockerfile:33`), and without Redis Celery runs eagerly (`celery_app.py:51-58`), so beat never runs there. The APScheduler files are unused (`scheduler_enhanced.py:284` has `start()` commented out; neither file is imported by the app).
- **Who benefits:** all registrants, and organisers who now send WhatsApp reminders by hand.
- **What to build:** a protected `POST /internal/cron/<job>` (shared secret header, compared in constant time; 503 when the secret isn't configured) that runs the existing task functions idempotently: reminders, lifecycle transitions, clean-up of expired sessions, old login attempts (`services_login_throttle.purge_expired`, BLK-13) and old outbox rows, and outbox retries (UPG-18). An external scheduler calls it: Cloud Scheduler on Cloud Run, or a GitHub Actions `schedule` workflow. Document both. Delete the unused schedulers (see UPG-14).
- **Re-checked before building (2026-10-08, `125f7f7`; rule 3):** still as described (only `services_login_throttle.py` changed since `986d108`, adding the hourly window). Also found:
  - **The lifecycle job deleted data.** `run_event_lifecycle` deleted every event 5 days after its date, with its registrations, and any registrations 30 days after. Under self-hosted beat this would have removed results, attendance and certificates' records. Criterion 3 asks it to complete events instead, so it was rewritten to change statuses only; how long data is kept is UPG-22.
  - **Events saved without times get the save time as `start_datetime`/`end_datetime`** on the SQL layer, so "end date" alone would complete any event created a day earlier: new item UPG-47.
  - The reminders (and the velocity alert) look only at the old `active` status: added to UPG-43. Scheduled emails link to a fixed `https://sapthaevent.in`: new item UPG-46.
- **What was built:**
  - **`POST /internal/cron/<job>`** (`routes_cron.py:45`): 503 while `CRON_SECRET` is unset (`:48`); the `X-Cron-Secret` header is compared with `hmac.compare_digest` (`:50`), missing or wrong → 403; unknown job → 404; a failing job → 500 and logged. Registered and CSRF-exempt in `app.py:359,427` (the scheduler sends a secret, not a session). Jobs (`:41`):
    - `reminders`: `send_24h_reminders` and `send_3day_reminders`, each skipping registrations already reminded (`ticket_sent`, `early_reminder_sent`);
    - `lifecycle`: `run_event_lifecycle`;
    - `cleanup`: `session_store.purge_expired_sessions` and `services_login_throttle.purge_expired` (`:34`).
  - **`run_event_lifecycle` changes statuses and deletes nothing** (`tasks/scheduled_tasks.py:533`). Registration closes after the deadline (`registration_open` or the old `active` → `registration_closed`). An event whose last day has passed and is still published, open, closed or in progress → `completed`; its last day is the later of `date` and `end_datetime` (`:569`, because of UPG-47). Each move goes through `WorkflowEngine.transition_event`, so it's in the audit trail; a second run moves nothing.
  - **`.github/workflows/cron.yml`**: hourly reminders, 6-hourly lifecycle, daily clean-up, and a manual run; it does nothing until the repository secrets `CRON_URL` and `CRON_SECRET` are set, and takes no permissions.
  - **`docs/DEPLOY.md`** (new; the rest of the guide is UPG-32): the endpoint, the jobs and their answers, Cloud Scheduler set-up with `gcloud`, the GitHub Actions alternative (use one, not both), and the request timeout needed while emails go out inline (UPG-18). `CRON_SECRET` is in `.env.example` and the deploy checklist (section 6).
  - **Not done here:** outbox clean-up and retries wait for UPG-18's outbox (a new job on this endpoint). The unused schedulers stay for UPG-14: `tests/test_event_maintenance.py:10` imports two jobs from `scheduler_enhanced.py`. The velocity alert and the daily analytics roll-up still run only under Celery beat (noted in `docs/DEPLOY.md`).
- **Files touched:** new `routes_cron.py`, `app.py`, `tasks/scheduled_tasks.py`, `celery_app.py` (a comment), `.env.example`, new `.github/workflows/cron.yml`, new `docs/DEPLOY.md`, new `tests/test_cron.py`.
- **Effort:** S · **Depends on:** BLK-05 (tests), BLK-06 (`*_sent` flags persist) · **Risk:** double sends; rely on the existing `*_sent` flags.
- **Acceptance criteria** (`tests/test_cron.py`, real database layer; criteria 1–4 fail on the old code):
  1. ✅ Test: calling without the secret, or with a wrong one → 403; with no secret configured → 503 (`::test_the_endpoint_needs_the_secret_and_is_off_without_one`; with CSRF protection on, a right secret → 200; GET → 405).
  2. ✅ Test: `send_24h_reminders` with the secret, for an event tomorrow, sends once; a second call sends nothing (`::test_the_day_before_reminder_goes_out_once`: two confirmed registrants get one ticket email each and the one with a phone one WhatsApp; a cancelled registrant and an event in 5 days get nothing; the event is `active` because of UPG-43).
  3. ✅ Test: the lifecycle job moves an event past its end date to `completed` (`::test_the_lifecycle_completes_past_events_and_deletes_nothing`: open, in-progress, closed and `active` events past their date → `completed`; a multi-day event still running, today's event, an event saved without times, a draft and a cancelled event stay; a passed deadline closes registration; a 40-day-old event and its registration still exist; the moves are in the audit trail; a second run moves nothing).
  4. ✅ Test: the clean-up job deletes expired sessions (BLK-08) and login attempts older than the throttle window (BLK-13), and nothing else (`::test_the_clean_up_deletes_only_expired_sessions_and_old_login_attempts`: a live session and a 30-minute-old attempt, still counted by the hourly cap, stay).
  5. ✅ `.github/workflows/cron.yml` exists and targets the endpoint; `docs/DEPLOY.md` shows the Cloud Scheduler set-up (`::test_the_github_workflow_and_the_deploy_guide_target_the_endpoint`).
  - Full pytest: **883 passed** on PostgreSQL 16, **882 passed and 1 skipped** on SQLite; ruff clean.

#### UPG-08 — Team registration linked to tickets and judging
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-08: …" on `production-ready` (parent `98c3556`)
- **Problem:** The SPOC-created team hackathon form showed only name/email/phone/USN [R at `694c729`], because `is_team_event` and `limits` were dropped. They persist since BLK-09, but the fallback schema adds only a team-name field, never member fields from `team_min`/`team_max` (`routes_forms.py:191-214`, used at `:340-342`). `/teams/*` writes a separate `teams` collection (`routes_teams.py:92`) that registrations, tickets and judges never read. Members are parsed only from `member_N_*` fields (`routes_forms.py:445-455`).
- **Who benefits:** hackathon, sports and cultural teams; removes WhatsApp team collection.
- **What to build:** team fields generated from `team_min`/`team_max`; create a team, then join by invite code, which adds the member to the same registration; team size limits enforced on the server; the lead manages the team (remove a member, regenerate the code); each member sees the ticket; team check-in marks the members who are present; judges see the team name.
- **Re-checked before building (2026-10-08, `98c3556`; rule 3):** still as described. Nothing links to `/teams/*`, and no test covered it. Tickets (`routes_ticket.view_ticket`), the scanner's member list (UPG-02) and per-member attendance already read the registration's `members`, so the team had to live there.
- **What was built:**
  - **The form asks for the team.** `team_limits` (`routes_forms.py:156`) reads the event's `limits`. `team_fields` (`:167`) adds the team name and one name / email / USN row per possible member (required up to the minimum); `registration_schema` (`:188`) is what the registration page and submit both use.
  - **Size is checked on the server** (`:540`), whatever the browser sends: `submitted_members` (`:196`) refuses a member number beyond the maximum and an email listed twice. The team must have between the minimum and maximum people, the lead included, and a name; the check runs before any account is created.
  - **Invite code.** A team registration gets a unique 6-character `team_code` (`new_team_code`, `:216`; set at `:600`).
  - **`routes_teams.py`, rewritten on the registration.** The separate `teams` collection is no longer used.
    - `/teams/join` adds the logged-in student to the registration's `members`. It refuses a full team, a closed event and anyone already registered for the event.
    - `/teams/<reg_id>` is the team page: members, the ticket link, and for the lead the code.
    - The lead can remove a member (not themselves) and replace the code; a member can leave.
    - `/teams/create/<event_id>` now opens the event's form.
    - Templates are on the shared layout; `templates/teams/create.html` is gone. The ticket page links to the team page.
  - **What already worked, now tested:** a member opens the team ticket; the judge sees the team name; scanning the team ticket then saving member attendance marks exactly who came (UPG-02).
- **Files touched:** `routes_forms.py`, `routes_teams.py`, `templates/teams/view.html`, `templates/teams/join.html` (rewritten), `templates/teams/create.html` (removed), `templates/participant/ticket.html`, `tests/test_teams.py` (new), `tests/test_integration_flow.py` (see below), `tests/html_sinks.py` (skips a tracked file deleted before commit). `routes_ticket.py` and the registration template needed no change.
- **Effort:** M · **Depends on:** BLK-06, UPG-01 · **Risk:** medium; the registration gains `team_code`, and team events now refuse registrations below the team minimum. `tests/test_integration_flow.py::test_student_registers_for_free_team_event_and_spoc_checks_in` registered one person for a 2–4 team event, which criterion 1 now refuses. Its form gained a second member; its assertions are unchanged.
- **Acceptance criteria** (`tests/test_teams.py`, real database layer; 5 of 6 fail on the old code, and criterion 3 already held):
  1. ✅ Test: a team event with limits 2–4 renders member fields and rejects a 1-member team (`::test_the_form_asks_for_members_and_refuses_a_one_person_team`; three member rows, a 2-person team is accepted with an invite code).
  2. ✅ Test: joining by invite code adds the member to `members` and they can open the ticket (`::test_joining_by_code_adds_the_member_and_they_can_open_the_ticket`; only the lead sees the code; someone registered with another team can't join).
  3. ✅ Test: the judge event page lists the team name (`::test_the_judge_sees_the_team_name`).
  4. ✅ Test: a team at `team_max` rejects another join, even when the browser submits extra member fields (`::test_a_full_team_takes_nobody_else`).
  5. ✅ Test: only the lead can remove a member or regenerate the code; a removed member loses the ticket (`::test_only_the_lead_manages_the_team_and_a_removed_member_loses_the_ticket`; the old code stops working).
  6. ✅ Test: scanning the team ticket with 2 of 3 members marked present records exactly those 2 (`::test_a_team_check_in_records_exactly_the_members_who_came`).
  - Full pytest: **855 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-09 — Book the venue while creating the event
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Room conflict detection exists (`services_venue.check_room_conflict`), but it runs only on edit (`routes_spoc.py:1138-1144`) and publish (`services_workflow.py:190-218`). The create form has no room field (no `room_id` in `templates/spoc/create_event.html`), so clashes surface late and rooms are booked by email or phone.
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Accounts come only from self sign-up (`routes_auth.py:276-323`) or registration, which creates an unverified account since BLK-02 (`routes_forms.py:570-572`, `services_accounts.py:58`). There's no bulk import (not found). USN is now stored (fixed by BLK-09 [R round-trip at `1f4cdc8`]), but department and year are often blank, so department filters and reports are unreliable. OAuth routes exist, configured via `config.py:227-230`, but at `986d108` no template links to `/auth/google` or `/auth/microsoft`, and `auth_oauth.py` has no university-domain restriction [C].
- **Who benefits:** every student (one-click login) and every report that needs department/year.
- **What to build:** a SuperAdmin CSV upload (email, name, USN, department, year, section) that creates or updates users. Show a "Sign in with Google" button restricted to the university domain.
- **Files touched:** `routes_admin.py`, `templates/admin/*`, `auth_oauth.py`, `templates/login.html`, `config.py`, tests.
- **Effort:** M · **Depends on:** BLK-06, BLK-02 · **Risk:** account merging for existing emails.
- **Acceptance criteria:**
  1. Test: uploading 3 rows creates 3 users with USN and department read back.
  2. Test: re-uploading updates in place, with no duplicates.
  3. Test: a Google callback with a non-university domain is rejected.
  4. The login page shows the Google button when OAuth is configured. *(2026-10-10: moved to UPG-55, which links Google sign-in and 2FA before launch; UPG-10 adds the domain rule.)*

#### UPG-11 — Participation ledger: activity points and NSS / NCC / FDP hours
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Every registrant is created as `Student`: registration through `services_accounts.create_unverified_account` (its role defaults to `Student`, `services_accounts.py:59,66`; used at `routes_forms.py:571`), and sign-up at `routes_auth.py:306`. There's no faculty or external participant type (`utils.py:24-36`, `services_permission.py:53-80`), so FDPs and conferences can't be run for their real audience.
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** The sports template promises "fixture brackets, live match score updates, point tables" (`services_templates.py:392-434`), but no model, route or template builds fixtures or standings. The only mentions are checklist labels (`services_event.py:63`, `services_copilot.py:180`; the second was missed before). Sports officers run tournaments on whiteboards and in Excel.
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:**
  - **Notifications:** the v1 feed reads `notifications` (`routes_notifications.py:20`), but every writer uses `notifications_v2` (`routes_notifications_v2.py:70`, `services_automation.py:185`, `routes_waitlist.py:96`). The student dashboard feed (`templates/participant/dashboard.html:1759`) is always empty, while the header badge counts v2.
  - **Payments:** Stripe has no UI reference (`routes_payment_stripe.py`).
  - **Schedulers:** `scheduler.py` / `scheduler_enhanced.py` aren't used by the app. Since UPG-07, scheduled jobs run through `/internal/cron/<job>` or Celery beat. `tests/test_event_maintenance.py:10` imports `_create_cleanup_job` and `_create_event_status_transition_job` from `scheduler_enhanced.py`; removing the file means deciding what happens to those two tests (rule 5), whose behaviour `tests/test_cron.py` now covers for the live job.
  - **Matchmaker:** `routes_matchmaker.py` suggests mock people (`routes_matchmaker.py:12`). `routes_ai_matching.py` is a different feature (judge↔team) and stays.
  - **Tests:** `tests.py` fails at collection [R] and duplicates `tests/`.
  - **Login throttling (found in BLK-13):** `security_middleware.py`'s in-memory `record_login_attempt`, `is_account_locked` and `get_remaining_lockout` were never called and are superseded by `services_login_throttle.py`. Nothing calls `block_ip` outside them, so the `is_ip_blocked` check in `init_security_middleware` never blocks anyone. Remove them, along with their unit tests in `tests/test_security.py`, which only test this dead code (keep the header and sanitiser tests).
  - **Waitlist promotion (found in BLK-03):** two implementations, `routes_waitlist.auto_promote` (ordered by `position`, no ticket) and `tasks/waitlist_tasks.promote_from_waitlist` (ordered by `joined_at`, issues a ticket, used by the cancel route). BLK-03 made both use `promotion_terms`; merge them into one.
  - **Not duplicates (checked 2026-09-30 at `56a014d`):** `models.py` (91 lines) is the `db` entry point imported by 70 modules, not a copy of `models_pg.py`; keep it. `routes_ai_matching.py` (judge↔team) is a different feature from the matchmaker; keep it.
  - **Check-in paths left beside the shared check-in (found building UPG-02):** the SPOC manual list (`/spoc/api/checkin`, with rounds and no payment check) and the coordinator's `get_ticket` and `mark_attendance_granular` still work by registration ID with their own rules; the scanners and desks now use `routes_ticket.check_in`. `/ticket/api/verify` POST's Bearer-token login imports `auth_jwt.decode_access_token`, which doesn't exist, so it only ever accepts the session (fails closed).
  - **Background tasks nothing queues (found in the end-of-Phase 2 re-verification):** `tasks/export_tasks.py` (Excel, score-sheet and QR-list exports uploaded through `utils_storage`; never called: exports are served directly by `services_export`, UPG-03) and `tasks/webhook_tasks.py` (`process_razorpay_payment`/`process_razorpay_refund`; never called since UPG-30's webhook in `routes_payment.py`). `tests/test_tasks.py:88-125` tests `process_razorpay_payment`, so removing it needs the same rule 5 decision as the scheduler tests.
  - **Two certificate stores (found building UPG-06):** the web path records `verified_certificates/<id>` (`utils_certificate.issue_event_certificates`), which `/verify` reads; API v1's `services_certificate.CertificateService` writes `certificates/<id>`, which `/verify` doesn't read, so API-issued certificates can't be verified there.
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
- **Status:** IN PROGRESS (criterion 2 met by BLK-09's test; the rest open)
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:**
  - **Unregistered blueprints:** `routes_public.py`, `routes_head.py` and `routes_super.py` (not in `app.py:302-395`), yet live pages link to them: `/event_head/*` from `templates/coordinator/manage_event.html:50` and `/super_admin/*` from `templates/public/home.html:528`.
  - **Dead nav links:** re-checked 2026-10-02 against the app's URL map [R]. `/admin/events` and `/settings` are no longer linked from any template, and `/dashboard` now resolves (`dashboard_redirect`). `/admin/users` is linked again and resolves since UPG-40. The links to the unregistered blueprints above still 404.
  - **Unused files:** about 20 templates are never rendered (`admin/users.html` is rendered since UPG-40); `routes_api.py` is empty. (The debug route is gone since BLK-09: `/debug-modal` → 404, `tests/test_integration_flow.py:198`.)
  - **Broken or risky scripts:** `reset_system.py` imports a nonexistent `Participant` model; `wipe_data.py` deletes all events and registrations with no prompt (since BLK-10 it refuses production-looking databases, but it still doesn't ask).
  - **Seed scripts:** 13 `seed_*.py` scripts, plus `seed_safety.py` (BLK-10's guard, not a seed). In all, 10 seed/setup scripts write straight to Firestore, and since BLK-10/BLK-15 only after the project is confirmed.
  - **Copies:** `scratch/` (26 tracked files); untracked `saptha-event-portal-source*` folders and ~54 MB of zips; `functions/saptha_app/` is a tracked, diverged copy of the app (`app.py` differs in 646 lines by `git diff --numstat`, 630 at `986d108`) that `catalyst.json` deploys.
  - **Walk-in default password in the `functions/` copy (recorded 2026-09-29, not fixed):** `functions/saptha_app/routes_coordinator.py:645` still sets new walk-in accounts' password to `WALKIN_DEFAULT_PASSWORD` with a published default. The root app gives new walk-ins no password at all since UPG-33, only a set-password link (`routes_coordinator.py:576,611`). **Walk-in accounts created on the Zoho Catalyst deploy (which runs this copy, `catalyst.json`) may still have that password.** The copy does set `needs_password_reset` (`:652`), but its older `db_adapter.py` may drop that flag in postgres mode (as at `694c729`, BLK-06), so the forced reset may never have happened [C]. Owner: check walk-in accounts on that deploy and force resets.
  - **Stale gitlink:** `saptha-event-portal` is a gitlink (mode 160000) with no `.gitmodules`, pointing at a commit of this repo's own old history that no longer exists after the BLK-01 rewrite. It's inert; delete it.
- **Who benefits:** developers and agents (less wrong code to read); users (no 404s).
  - **The `functions/saptha_app` copy also keeps the kiosk and ticket holes the root app fixed** (BLK-12) and the bandit findings (BLK-11).
- **What to build:** remove or merge the above; move `scratch/` tools worth keeping into `scripts/` and delete the rest; fold the seed scripts into one seed command (with BLK-10's guard). Remove `functions/saptha_app/` and `catalyst.json`: Cloud Run is the only deploy target (D-1, owner, 2026-10-01), so no Catalyst build step replaces them.
- **Files touched:** listed above, plus a new test.
- **Effort:** M · **Depends on:** none · **Risk:** low for deploys (nothing else deploys the copy, D-1).
- **Acceptance criteria:**
  1. Test: parse every template's internal `href`/`action`/`fetch` URL and assert each matches a rule in `app.url_map`.
  2. ✅ Test: `/debug-modal` → 404 (`tests/test_integration_flow.py:198`, `test_removed_debug_and_legacy_endpoints`, since BLK-09).
  3. `git ls-files` lists nothing under `functions/saptha_app/`, no `catalyst.json`, and no `seed_*.py` beyond the kept one. This also completes BLK-12 criterion 4 and BLK-14 criterion 3.
  4. ~~The Catalyst deploy still works via the build step (manual check).~~ Dropped: D-1 (owner, 2026-10-01) ends the Catalyst deploy, so there's no build step to check. Covered instead by criterion 3 (`catalyst.json` is gone).
  5. Walk-in accounts created on the Zoho deploy with the old default password have been forced to reset (owner check), and no tracked file sets a default walk-in password (test).

### D. Production setup (added in Phase 0, 2026-09-30)

#### UPG-16 — Alembic baseline: build an empty database through migrations
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:**
  - `migrations/versions/` isn't empty (the plan's prompt said it was): it has two tracked incremental migrations, `0001_add_org_units_and_scoped_roles.py` and `0002_add_campuses_buildings_rooms_bookings.py`. They assume the core tables already exist: `alembic upgrade head` on an empty SQLite database fails with `NoSuchTableError: events` [R at `56a014d`].
  - The real schema comes from start-up code in every environment, production included: `Base.metadata.create_all` (`db_pg.py:171-184`) plus `ALTER TABLE … ADD COLUMN` in `db_pg.py:197` and `db_adapter.verify_and_align_schema` (`db_adapter.py:201-326`, called at `:1856`). Column changes are never recorded, can't be reviewed or rolled back, and race when several instances start together.
  - **Added since Phase 0, which the baseline must include:** the tables `payment_orders` (BLK-03; with UPG-30's columns `regDataJson`, `failureReason`, `refundId`, `refundedAt`, `refundedBy`), `coupon_uses` (UPG-36), `flask_sessions` (BLK-08) and `login_attempts` (BLK-13); the column `events.spoc_id` and the new status enum members (BLK-06a); `extra_json` on eight more tables (BLK-06b). Re-run 2026-10-02 [R]: `alembic upgrade head` on an empty SQLite database still fails with `NoSuchTableError: events`.
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
- **Status:** MERGED into UPG-21 (D-5, owner, 2026-10-10). Criteria 1–2 are built and tested there; 3–4 have nothing live to test.
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`]
  - **Corrected in the end-of-Phase 2 re-verification (2026-10-08) [C]: no live path stores files today.** Certificates are generated, emailed and verified from their database record since UPG-06 (`tasks/cert_tasks.py` no longer uploads); certificate templates are stored in the database (`routes_spoc.py:1305`); exports are streamed by `services_export` (UPG-03). `utils_storage.upload_file` is called only by `tasks/export_tasks.py:187`, which nothing queues, and the unused `scheduler_enhanced.py:456` (both UPG-14). So nothing is lost on a restart today.
  - What remains matters for UPG-21's backups (and any future upload): `upload_file` writes to `static/uploads/` unless `STORAGE_TYPE` is `s3` or `gcs` (`utils_storage.py:19,74-92`), and on Cloud Run that disk is wiped on restart and not shared between instances.
  - The S3 branch can't target an S3-compatible service such as Supabase Storage: there's no endpoint setting (`utils_storage.py:29-34`). It uploads with `ACL='public-read'` (`:44`), which would make exported registration lists (names, emails, phones) public.
  - Any S3 or GCS error silently falls back to local disk (`:54-55`, `:71-72`).
- **Who benefits:** the university (UPG-21's backups land in a private bucket); any later feature that stores files.
- **What to build:** an `S3_ENDPOINT_URL` setting (for Supabase Storage) on the existing S3 path; private objects with short-lived signed URLs for exports (certificates may stay public-readable so the verify page works, or be served through the app); local disk only in development; in production an upload error is an error, never a local write.
- **Files touched:** `utils_storage.py`, `config.py`, `.env.example`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low; needs a Supabase Storage bucket and S3 keys for a manual check.
- **Acceptance criteria:**
  1. Test (boto3 client stubbed): with `STORAGE_TYPE=s3` and `S3_ENDPOINT_URL` set, the client is created with that endpoint and the returned URL points at it.
  2. Test: with production config, an S3 failure raises and nothing is written under `static/uploads/`.
  3. Test: exports are uploaded without a public ACL and handed out as signed URLs that expire.
  4. Test: a certificate uploaded through one app instance is readable through a second instance (shared stubbed bucket), and after an app restart. *(Re-verification 2026-10-08: nothing uploads certificates any more; this criterion and criterion 3 have nothing live to test. Proposed in D-5: keep criteria 1–2 and fold them into UPG-21.)*

#### UPG-18 — Background tasks without a broker: inline with timeouts, plus an outbox for retries
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] Without `CELERY_BROKER_URL=redis://…`, Celery runs every task inline in the request (`celery_app.py:49-58`, `task_always_eager`), with no timeout: a slow mail or WhatsApp provider holds the request (and the gunicorn worker). A failed send is logged and lost; nothing retries it. The Cloud Run + Supabase target has no Redis or worker. (Scheduled jobs are UPG-07.)
- **Who benefits:** everyone who waits on a page that sends mail; attendees whose confirmation would otherwise be lost.
- **What to build:** an outbox table (task name, arguments, attempts, next attempt, status, last error); with no broker, tasks run inline under a per-task timeout, and failures or timeouts are stored in the outbox; UPG-07's cron endpoint retries due rows with backoff and a maximum number of attempts. With a broker, behaviour is unchanged. Document both modes.
- **Files touched:** `celery_app.py`, new `services_outbox.py`, `models_pg.py` + migration, `tasks/*`, `docs/DEPLOY.md`, tests.
- **Effort:** M · **Depends on:** UPG-07 (retry trigger), UPG-16 (migration) · **Risk:** sending twice; each task keeps an idempotency key.
- **Noted in UPG-07 (2026-10-08):** the endpoint is built (`routes_cron.py`, jobs in `JOBS`). Add an `outbox` job there for due retries, and old outbox rows to the `cleanup` job, with a schedule line in `docs/DEPLOY.md` and `.github/workflows/cron.yml`. Until then, the day-before reminder's emails go out inline in the cron request, which `docs/DEPLOY.md` covers with a 30-minute deadline. **Noted in UPG-31:** the notice keys (`notification_dedup`, the reminders' `*_sent` flags) are read, then written, so two runs at the same instant could both send; the outbox's idempotency key should be a unique insert.
- **Acceptance criteria:**
  1. Test: with no broker, a task that raises leaves one outbox row (attempts 1) and the request still succeeds.
  2. Test: a task that runs past its timeout returns control to the request within the limit and is stored for retry.
  3. Test: the retry job sends a stored task once; running it again sends nothing; after the maximum attempts the row is marked failed.
  4. `docs/DEPLOY.md` explains the inline + outbox mode and the broker mode.

#### UPG-19 — Pagination and search on every admin, SPOC and coordinator list
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] Only `routes_api_v1.py` and `routes_notifications_v2.py` read a page or limit parameter (the plan's prompt said 3 route files). The web lists stream whole collections into one page: `.stream()` appears 27 times in `routes_admin.py`, 27 in `routes_spoc.py`, 13 in `routes_coordinator.py` and 7 in `routes_forms.py` (re-counted 2026-10-08; 25, 29, 15 and 6 at `986d108`) (for example users, registrations, form responses, audit log). With a whole university's data these pages will be slow or time out.
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`]
  - `validate_production_config` collects problems into one error (`config.py:257-275`) but checks only `SECRET_KEY`, `MASTER_SECRET_KEY` and the default admin password. `JWT_SECRET_KEY` silently falls back to `SECRET_KEY` (`config.py:220`); `RAZORPAY_*`, `BASE_URL`, the mail provider and storage settings aren't checked; `DATABASE_URL` is checked separately with its own error (`db_pg.py:104-150`).
  - `.env.example`'s Redis section still says sessions use the filesystem without Redis; since BLK-08 they use the database (found in BLK-13).
  - `COLLEGE_LOGO_URL` defaults to the retired Railway domain (`config.py:187-190`), so email and certificate logos break unless it's set (found in BLK-16): default it to `BASE_URL` + `/static/snpsu-logo.png` or require it.
  - `.env.example` lists 47 of the 99 environment variables the app code reads (re-counted 2026-10-08 with one script, which gives 43 of 93 at `986d108`; the earlier 43 of 91 used a narrower file set). Missing ones include `MAIL_FROM`, the sender production needs (UPG-41 and the deploy checklist), `SENTRY_TRACES_SAMPLE_RATE`, `SESSION_TYPE`, `RATELIMIT_STORAGE_URL`, `WTF_CSRF_SECRET_KEY`, `MAIL_*` SMTP settings and `PORT`.
  - `/health` and `/health/ready` call `.stream()` without reading it, so they may not reach the database, and they return the exception text (`app.py:502-538`).
  - Logs are plain text; Cloud Run needs one JSON object per line for severity and request grouping.
  - Sentry is initialised when `SENTRY_DSN` is set (`app.py:124-138`, `send_default_pii=False`), but nothing tests it (the plan's prompt said it wasn't set up).
  - HSTS is sent only when `FORCE_HTTPS` is true (`app.py:233`); on Cloud Run TLS ends at Google's front end, so this needs to be on in production and to trust the proxy's scheme.
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] `routes_compliance.py` has data export (`:50`), deletion request (`:126`), cancel deletion (`:188`) and consent (`:211`, `:250`) endpoints, never run end to end. The registration form has no consent checkbox (no "consent" in `templates/public/registration_form.html`). The privacy page is linked from only 5 templates, because pages don't share a footer (UPG-23).
- **Who benefits:** every student and external participant; the university's DPDP obligations.
- **What to build:** a privacy notice linked from the shared footer; a required consent checkbox at registration and sign-up, stored with the time and notice version; a working export (the user's own data as a download) and deletion (account removed, registrations anonymised, kept only where records must be retained).
- **Files touched:** `routes_compliance.py`, `routes_forms.py`, `routes_auth.py`, `templates/public/registration_form.html`, the shared layout, tests.
- **Effort:** M · **Depends on:** BLK-02, UPG-23 (footer) · **Risk:** what must be kept (e.g. certificates, finance records) is a policy question; record it under "Decisions needed" if it blocks.
- **Noted in UPG-07 (2026-10-08):** the scheduled lifecycle job used to delete events 5 days after their date and registrations after 30 days. It now only changes statuses, so nothing is deleted on a schedule. If old data should go after some time, that rule belongs here, with the policy above.
- **Acceptance criteria:**
  1. Test: registration without consent → refused with a clear message; with consent → stored with time and notice version.
  2. Test: export returns the user's profile and registrations and nothing about anyone else.
  3. Test: after deletion is processed, the user can't log in and their registrations hold no name, email or phone.
  4. Test: every page on the shared layout links the privacy notice.

### E. Frontend (added in Phase 0, 2026-09-30)

#### UPG-23 — Every page on one shared layout (split by area: UPG-23a–h)
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`, counted with a script] Of 129 templates, 16 extend `base_classic.html` (12 at `986d108`; Phase 2 added `admin/payments.html` and moved `admin/users.html`, `teams/join.html` and `teams/view.html` onto it), 1 extends `coordinator/base.html`, which doesn't exist (`templates/coordinator/view_scores.html`; nothing renders it, UPG-15), 5 are partials, and **107 are standalone pages** with their own `<head>`, CDN tags and navigation (111 at `986d108`; the plan's prompt said 108 of 126 and ~13). So fixes to navigation, CSP, fonts, footer or loading states have to be made 107 times. (Re-counted 2026-10-02: Phase 0 wrote 110, which left the four groups one short of 129.)
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] Bootstrap 5.3.0 is loaded by 46 templates and 5.3.3 by 34 (re-counted 2026-10-08; 50 and 34 at `986d108`, before four pages moved onto the shared layout). Google Fonts families: Inter (29 templates), Poppins (27), Plus Jakarta Sans (4), Cinzel (3), Orbitron (1), Outfit (1), while `static/css/global.css` uses Inter, Plus Jakarta Sans and Outfit (`global.css:189,201,897`). Of 261 CDN `<script>`/`<link>` tags, 2 have an `integrity` hash (still 2 on 2026-10-08; the font and tag counts fell slightly as pages moved onto the shared layout).
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] 70 templates contain inline `<script>` blocks, and 76 templates contain 483 inline event handlers (`onclick=` and similar; re-counted 2026-10-08: 72, 78 and 490 at `986d108`). So the CSP's `script-src` allows `'unsafe-inline'` (`app.py:221`), which removes most of its protection against injected scripts; `content_security_policy_nonce_in=[]` (`app.py:236`).
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] The only double-submit guard is the "button loading state" in `static/js/global.js:211-229`, and only 24 of 129 templates load `global.js` (25 at `986d108`); the payment pages `payment/checkout.html` and `public/payment_gateway.html` don't. The guard also re-enables the button after 15 seconds. Labels and error messages haven't been checked across forms.
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
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
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
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
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-29: …" on `production-ready` (parent `2f6262f`)
- **Problem:** Assignment works since BLK-09 (`routes_spoc.py:1171-1252` coordinators, `:1379-1435` judges), and one test covers the SPOC assigning a coordinator (`tests/test_integration_flow.py:164-185`). Not tested: judge assignment, unassigning, a SPOC trying to assign on someone else's event, and the assigned person seeing the event on their dashboard.
- **Who benefits:** SPOCs, coordinators and judges.
- **What to build:** tests first; fix whatever they find (e.g. unassign doesn't remove access).
- **Re-checked before building (2026-10-08, `2f6262f`; rule 3):** the routes moved (`assign_coordinator` at `routes_spoc.py:1187`, `add_judge` at `:1371`). What the tests found:
  - there was no way to unassign anyone (no route, no button);
  - `assign_coordinator` answered another SPOC with a flash and a redirect, not 403;
  - the judge dashboard lists only events whose status is `active`, so a judge doesn't see an event in a workflow state. That's UPG-04 criterion 3 (after Phase 6), so the judge-dashboard check here uses an `active` event.
  - A judge sees only teams allocated to them unless open hall is on; that's how judging works, not a fault.
- **What was built:**
  - `POST /spoc/remove_staff/<event_id>` (`routes_spoc.py:1253`): the owner (or anyone with `edit_event` on the event) removes an email from the event's `staff` and `coordinators`. Every permission on the event comes from those lists, so access to registrations, exports, check-in and scoring ends at once; the account stays.
  - The SPOC dashboard shows a remove button on each coordinator chip and lists the assigned judges, each with a Remove button, in the judges dialog (`templates/spoc/dashboard.html:1746,2098`). The dialog's stale "credentials emailed" line now says new judges get a set-password link (UPG-33).
  - `assign_coordinator` checks `edit_event` with BLK-17's helper first (`routes_spoc.py:1193`), so another SPOC gets 403 before anything is created.
- **Files touched:** `routes_spoc.py`, `templates/spoc/dashboard.html`, `tests/test_assignment.py` (new).
- **Effort:** S · **Depends on:** BLK-04 · **Risk:** low. Removing a judge leaves `assigned_judge_email` on the event's registrations, harmless since scoring needs the staff entry; the next allocation replaces it.
- **Acceptance criteria** (`tests/test_assignment.py`, real database layer; all 4 cases fail on the old code):
  1. ✅ Test (real DB): the SPOC assigns a coordinator and a judge on their own event; each sees it on their dashboard (`::test_the_owner_assigns_a_coordinator_and_a_judge_and_each_sees_the_event`; the coordinator opens the registrations, the judge the team list; the owner's dashboard offers removal). The judge's check uses an `active` event until UPG-04 criterion 3.
  2. ✅ Test: another SPOC gets 403 and nothing changes (`::test_another_spoc_cant_assign_or_remove_and_nothing_changes`: assign coordinator, add judge and remove; no account is created for a new email).
  3. ✅ Test: unassigning removes access to the event's registrations and scoring (`::test_removing_someone_ends_their_access`: the coordinator loses registrations, exports and attendance marking and the event leaves their dashboard; the judge loses the team list and scoring, nothing is saved, and the event leaves their dashboard). `::test_removing_someone_who_isnt_staff_changes_nothing` covers a wrong email.
  - Full pytest: **830 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-30 — Paid events end to end: receipt email, refunds and cancellations
- **Status:** IN PROGRESS (built 2026-10-08; criterion 4, the owner's checkout with Razorpay test keys, is left)
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] After a verified payment only a WhatsApp receipt task is queued (`routes_payment.py:356`); there's no email receipt. There's no admin action to mark a payment refunded or a paid registration cancelled; `services_finance.py:249-264` only counts `refunded` in reports. BLK-03 makes verification safe; this item makes the whole flow work.
  - **Added 2026-10-02 from the code review of PR #48 (owner)** [C at `7aac9ca`]:
    - (a) **Money taken, no registration.** `verify_payment` claims the order (marks it paid, `routes_payment.py:177`) before `_complete_registration` runs (`:197`). If completion fails (the payer is already registered, or any exception), the payer has paid but has no registration; the only trace is an audit line (`PAYMENT_UNMATCHED`, `:209`, or `PAYMENT_FAILED`, `:374`), and the browser gets a 400. Completion also doesn't re-check capacity (capacity is checked only at form submit, `routes_forms.py:605-606`), so a payment finished after the last seat went **overbooks** the event instead of failing.
    - (b) **No webhook.** Nothing receives Razorpay's server-to-server events (no webhook route in `routes_payment.py`). If the browser closes after paying, before `/payment/verify` runs, the payment is never matched to the order or a registration.
- **Who benefits:** the finance office, organisers and paying participants.
- **What to build:** a receipt email (Brevo) after a verified payment; admin actions to mark a registration refunded or cancelled (with reason, audit-logged), which also stop its ticket from checking in; a finance export row per payment.
  - Added 2026-10-02: a `payment.captured` webhook (`/payment/webhook/razorpay`), verified with `X-Razorpay-Signature` and a new `RAZORPAY_WEBHOOK_SECRET`, that completes the registration from the stored order (and the reg data kept with it), once, whichever of webhook and browser arrives first.
  - Completion re-checks capacity. When completion fails after the order is paid (full, already registered, error), the order is kept as paid with no registration, and the payer is told the payment is recorded and will be completed or refunded.
  - An admin list of paid orders with no registration, and a refund action that calls Razorpay's refund API for the order's payment and amount, records the refund on the order and audit-logs it.
  - `RAZORPAY_WEBHOOK_SECRET` joins "Before the next deploy".
- **Re-checked before building (2026-10-08, `f5ae29d`; rule 3):** `routes_payment.py` and `services_payments.py` were unchanged since `986d108`; the claims hold. Also found:
  - `payment_orders` had nowhere to keep the registration being paid for, so a webhook had nothing to complete from;
  - a registration's status enum has `cancelled` but no `refunded`;
  - after a payment, the ticket-email task calls `send_ticket_email` with arguments it doesn't take, so paid registrants never got their ticket email, and the WhatsApp receipt task has the same fault. Both are notifications; added to UPG-31, not fixed here.
- **What was built:**
  - **Orders keep what they pay for.** `payment_orders` gains `regDataJson`, `failureReason`, `refundId`, `refundedAt` and `refundedBy` (`models_pg.py`). Existing databases get them from the start-up schema check (`db_adapter.verify_and_align_schema`); UPG-16's baseline must include them. `create_order` stores the pending registration with its order (`services_payments.record_order`, `services_payments.py:188`).
  - **Receipt.** A completed payment with an amount queues one receipt email: amount, event, registration, payment ID (`routes_payment.py:351`, `utils_email.send_payment_receipt_email`, `utils_email.py:720`).
  - **Completion never overbooks or loses money** (`routes_payment.py:306`). It re-checks capacity; a held waitlist seat is already counted.
    - When completion fails after the order is claimed (full, already registered, an error), the order stays paid with its reason recorded (`:208`).
    - The payer gets 202 and `RECORDED_MESSAGE` (`:18`): the payment is recorded and will be completed or refunded. The checkout page shows it.
  - **Webhook: `POST /payment/webhook/razorpay` (`:397`).** It is CSRF-exempt and authenticated by `X-Razorpay-Signature` with `RAZORPAY_WEBHOOK_SECRET`; without the secret it answers 503.
    - On `payment.captured` it claims the order atomically, but only if Razorpay's amount is the order's (`claim_paid_order`, `services_payments.py:239`). It then completes the stored registration once.
    - If the browser's `/payment/verify` arrives after the webhook, it is sent to the ticket (`routes_payment.py:180`).
    - Replays, unknown orders and wrong amounts change nothing.
  - **The admin's payments page `/admin/payments`** (Super Admin only, 403 otherwise; `routes_admin.py:486`), linked from both admin navigations:
    - paid orders with no registration, each with a Razorpay refund that needs a ticked confirmation. The refund moves the order to `refunding` atomically, so only one request calls the API; it records refund ID, time and admin, audit-logs it, and undoes the claim if the API fails (`:527`, `start_refund` `services_payments.py:265`).
    - paid registrations, each markable refunded (money returned another way) or cancelled with a reason, audit-logged (`:501`). Both set the registration `cancelled`, refunded also sets the payment `Refunded`, and check-in refuses either (`routes_ticket.py:169`).
  - **Finance export.** `/admin/analytics/export/payments`: one row per order with payment, amount, status, registration and refund (`routes_admin.py:321`).
  - `RAZORPAY_WEBHOOK_SECRET` is documented in `.env.example` and the deploy checklist.
- **Files touched:** `routes_payment.py`, `services_payments.py`, `routes_admin.py`, `routes_ticket.py`, `models_pg.py`, `db_adapter.py` (schema check), `utils_email.py`, `tasks/email_tasks.py`, `app.py` (CSRF exemption), `templates/admin/payments.html` (new), `templates/payment/checkout.html`, `templates/base_classic.html`, `templates/admin/dashboard.html`, `.env.example`, `tests/test_paid_events.py` (new).
- **Effort:** L (was M) · **Depends on:** BLK-03, BLK-05 · **Risk:** needs Razorpay test keys for the manual check; refunds move real money, so the action needs a ticked confirmation. Two payments racing for the last seat can both pass the capacity check (no transaction in the adapter); the second would overbook by one.
- **Acceptance criteria** (`tests/test_paid_events.py`, real database layer, Razorpay client mocked; all 12 cases fail on the old code):
  1. ✅ Test (Razorpay client mocked): register → order → verify gives `Confirmed / Paid` with the server amount and queues exactly one receipt email (`::test_a_verified_payment_confirms_and_sends_one_receipt`).
  2. ✅ Test: an admin marks the registration refunded, then another cancelled; each is audit-logged, and the ticket is refused at check-in (`::test_admin_marks_registrations_refunded_and_cancelled_and_their_tickets_stop`).
  3. ✅ Test: a non-admin gets 403 on both actions (`::test_non_admins_cant_use_any_payment_action`: the owner SPOC and a student, also on the page, the refund and the export).
  4. Manual (owner, with Razorpay test keys): the full checkout in test mode. **Open**, as is BLK-03's matching check. **Deferred to UPG-32** (D-6, 2026-10-10): run on a public test deployment together with the webhook. Set the webhook (event `payment.captured`, URL `<BASE_URL>/payment/webhook/razorpay`) and its secret first.
  5. ✅ Test: when completion fails after the order is claimed (the event filled up, the payer is already registered, or an exception), no seat is over-allocated, the order stays paid with no registration, it appears in the admin list, and the payer sees that the payment is recorded (`::test_a_failed_completion_keeps_the_payment_and_overbooks_nobody`, one case per cause).
  6. ✅ Test: a `payment.captured` webhook with a valid signature for a recorded order whose browser never returned completes the registration once; replaying it, or the browser's `/payment/verify` arriving afterwards, changes nothing. A bad signature → 400 and nothing changes; an unknown order → 200 and nothing is created (`::test_the_webhook_completes_a_payment_whose_browser_never_returned_once`, `::test_the_webhook_refuses_bad_signatures_and_ignores_unknown_orders`, which also covers a wrong amount; `::test_the_webhook_fails_closed_without_its_secret`).
  7. ✅ Test: the admin list shows exactly the paid orders that have no registration; a non-admin gets 403 (`::test_the_admin_list_shows_exactly_the_paid_orders_without_a_registration`; the 403 is in criterion 3's test).
  8. ✅ Test (Razorpay client mocked): the refund action calls the refund API once with the order's payment ID and amount, marks the order refunded and audit-logs it; a second request does nothing; a non-admin gets 403 (`::test_the_refund_calls_razorpay_once_and_is_recorded`; without the confirmation nothing happens).
  - Also: `::test_the_finance_export_has_one_row_per_payment`.
  - Full pytest: **867 passed** on SQLite and PostgreSQL 16; ruff clean.
- **Rule 8 (early pass, `db_adapter.py` and `models_pg.py` changed):** the change only adds columns to `payment_orders`. Of the 32 open items, UPG-16 lists that table for its baseline; its line now names the new columns. The other items citing `models_pg.py` (UPG-11 to UPG-14, UPG-18) don't touch `payment_orders`, and their claims are unchanged.

#### UPG-31 — Notifications: confirmation, day-before reminder, change and cancellation notices through Brevo
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-31: …" on `production-ready` (parent `f570f07`)
- **Found while building UPG-30 (2026-10-08) [R]:** after a payment, `tasks.email_tasks.send_ticket_email_task` calls `utils_email.send_ticket_email(event_date=…, venue=…)`, which takes neither. So the task fails and retries five times, and a paid registrant never gets their ticket email. `send_payment_receipt_whatsapp_task` passes `reg_id` to `send_payment_receipt_whatsapp`, which expects `payment_id`.
- **Found while building UPG-07 (2026-10-08) [C]:** the day-before WhatsApp reminder task imports `utils_whatsapp.send_event_reminder_whatsapp` (`tasks/notification_tasks.py:53`), which doesn't exist, so every WhatsApp reminder fails and retries three times. The day-before email uses the same broken `send_ticket_email_task` call as above.
- **Problem:** [C at `56a014d`] Confirmation (`utils_email.send_registration_confirmed_email`, `utils_email.py:439`) and cancellation notices (`services_workflow.py:287-322`, idempotent per email) exist. The day-before reminder is a Celery beat job that doesn't run (UPG-07; since 2026-10-08 it runs through `/internal/cron/reminders`, but its sends fail, see above). There's no notice when an event's date, time or venue changes. In-app notifications are split between v1 and v2 (UPG-14).
- **Who benefits:** every registrant.
- **What to build:** a notice to all registrants when date, time or venue changes; the reminder through UPG-07's cron; every email through `utils_email` (Brevo first), each sent once (idempotency key), and never sent from tests.
- **Re-checked before building (2026-10-08, `f570f07`; rule 3):** the confirmation is as described. The rest is worse than the Problem says [R]:
  - **The change notice exists** (`services_venue.notify_event_details_changed`, called by the SPOC's edit, `routes_spoc.py:1152`), and **neither it nor the cancellation notice ever sent an email:** both go through `services_automation.dispatch_trigger`, whose email channel imports `utils_email.send_email_notification`, which didn't exist. The error was caught and recorded as `email_fallback`, so only the in-app notice was created.
  - The change notice's "once" key used Python's `hash()`, which differs between processes, so it held only within one worker.
  - The coordinator's edit form (`/coordinator/edit_event`) changes date and venue without any notice.
  - The confirmation email promises the entry QR the day before, but the reminder attached none. It also used the stream's internal ID, not the ticket ID.
- **What was built:**
  - **The missing and mismatched senders:** `utils_email.send_email_notification` (`utils_email.py:778`) sends a plain notice through `_send` (Brevo first) and escapes the text. `send_ticket_email` takes `event_date` and `venue` (`:534-538`), which the tasks already passed. `utils_whatsapp.send_event_reminder_whatsapp` (`utils_whatsapp.py:137`) is the day-before WhatsApp. The receipt WhatsApp task passes the payment ID (`tasks/notification_tasks.py:87`; callers `routes_payment.py`, `tasks/webhook_tasks.py`).
  - **The day-before ticket** (`tasks/scheduled_tasks.py:70,95`) uses the ticket's ID and attaches the entry QR: `tasks/email_tasks.ticket_qr_png` (`:112`) makes the same signed token the ticket page shows, which the scanners accept. Sent once per registration (`ticket_sent`), through `/internal/cron/reminders` (UPG-07).
  - **Change notices** use a stable key over the old and new venue, room, date, time and start (`services_venue.py:568-571`), so the same change is sent once on any instance. The coordinator's edit sends them too (`routes_coordinator.py:231`). **Cancellation** keeps its key `event_cancelled_<event>_<email>` (`services_workflow.py:321`), so cancelling again after a restore sends nothing.
  - Because the email channel now exists, API v1's automation triggers (`routes_api_v1.py:1100,1137`: payment success, round advanced, certificate issued, …) now send their emails too, under each user's email preference.
  - **Not done here:** notices go to the registration's lead only (UPG-48). The automation's WhatsApp channel calls a function that doesn't exist (UPG-49). Older email templates insert names and titles without escaping (UPG-50). The "once" checks read then write, so two runs at the same instant could both send; UPG-18's outbox should make the key a unique insert.
- **Files touched:** `utils_email.py`, `utils_whatsapp.py`, `tasks/email_tasks.py`, `tasks/notification_tasks.py`, `tasks/scheduled_tasks.py`, `tasks/webhook_tasks.py`, `routes_payment.py`, `routes_coordinator.py`, `services_venue.py`, new `tests/test_notices.py`. (`routes_spoc.py` and `services_workflow.py` already called the notices.)
- **Effort:** S · **Depends on:** UPG-07, BLK-05 (UPG-18's outbox adds retries later but isn't required) · **Risk:** double sends; idempotency keys guard it.
- **Acceptance criteria** (`tests/test_notices.py`, real database layer, Brevo's HTTP API mocked and any connection beyond localhost refused; 4 of 5 fail on the old code, and the confirmation already worked):
  1. ✅ Test: a registration sends one confirmation through the Brevo client (HTTP mocked) with the event's details (`::test_a_registration_sends_one_confirmation_through_brevo`: title, date, venue and calendar invite; registering again sends nothing).
  2. ✅ Test: the day-before reminder, run twice through the cron endpoint, sends once per registrant (`::test_the_day_before_ticket_goes_out_once_with_the_entry_qr`: one ticket email each with the signed entry QR, one WhatsApp each; the event is `active` because of UPG-43).
  3. ✅ Test: changing an event's venue notifies every registrant once; cancelling notifies once (`::test_a_venue_change_and_a_cancellation_each_notify_every_registrant_once`: saving the same change twice sends one notice; a cancelled registration gets none; the coordinator's date edit notifies; cancel, cancel, restore to draft, cancel sends one cancellation notice each).
  4. ✅ Test: with no mail keys configured (tests), nothing is sent over the network (`::test_with_no_mail_keys_nothing_leaves_the_machine`: registration, reminders, a venue change and a cancellation make no connection and no name lookup beyond localhost).
  - Also: `::test_notices_escape_what_people_type`.
  - Full pytest: **888 passed** on PostgreSQL 16, **887 passed and 1 skipped** on SQLite; ruff clean.

#### UPG-32 — Release check and `docs/DEPLOY.md`
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** There's no deploy guide for Cloud Run + Supabase, and no end-to-end release check from a fresh clone. `docs/DEPLOY.md` has only the scheduled-jobs section (UPG-07); `docs/DEPLOYMENT.md` covers the container and settings in general. *(Corrected 2026-10-08: `README.md` has no Railway/Render deploy guide; it names Cloud Run (`README.md:287,542`) and calls Brevo "Railway-safe" (`:211`).)*
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
| `SECRET_KEY` | New random value, 32+ characters | Yes: start-up is refused otherwise (`config.py:36-40`, `validate_production_config`) |
| `MASTER_SECRET_KEY` | New random value, 12+ characters, not a published value | Yes (`validate_production_config`) |
| `JWT_SECRET_KEY` | New random value, different from `SECRET_KEY` | **No**: it silently falls back to `SECRET_KEY` (`config.py:217`) |
| `SUPER_ADMIN_PASS` (with `SUPER_ADMIN_EMAIL`) | New strong password, used to create the first SuperAdmin | Only against the list of published passwords (`validate_production_config`) |
| `RAZORPAY_KEY_SECRET` (with `RAZORPAY_KEY_ID`) | Set before any paid event is opened | **No**, but without them online payment refuses with 503 (fails closed since BLK-03). Never set `PAYMENT_SIMULATION` in production (it's ignored there anyway). |
| `RAZORPAY_WEBHOOK_SECRET` | The secret set on the Razorpay webhook (Dashboard → Webhooks: event `payment.captured`, URL `<BASE_URL>/payment/webhook/razorpay`). It completes registrations whose browser closed after paying (UPG-30). | **No**, but without it the webhook answers 503 and such payments wait on the admin's payments page |
| `DATABASE_URL` | PostgreSQL (`postgresql://…`) | Yes: production refuses SQLite or no database (`db_pg.py:104-150`) |
| `BREVO_API_KEY` | A Brevo API key (Brevo → Settings → SMTP & API → API Keys). **Required in practice:** since UPG-33, new staff, SPOCs and walk-ins can get in only through the emailed set-password link. | **No** (UPG-20 adds a check) |
| `MAIL_FROM` | The sender, e.g. `SapthaEvent <events@your-domain>`, an address verified as a sender in Brevo. Unset, the sender is `MAIL_USER`; with neither, Brevo and Resend refuse to send and `/diag/email` says why (`utils_email.py:51-61`, UPG-41). | No |
| `BASE_URL` | The site's public `https://` address, e.g. the Cloud Run URL or the university domain. Every emailed, WhatsApp, QR and referral link is built from it. | Yes: production refuses a missing, `http://` or localhost value (`config.py:267-270`, BLK-16) |
| `CRON_SECRET` | New random value. Needed where Celery beat doesn't run (Cloud Run): Cloud Scheduler or GitHub Actions sends it to `/internal/cron/<job>` (`docs/DEPLOY.md`, UPG-07). | **No**, but without it the endpoint answers 503 and no reminders or lifecycle changes happen |
| `LOGIN_THROTTLE_IP_LIMIT` | **About 50** (owner, 2026-10-02). On campus Wi-Fi many students share one public IP, so the default of 5 failed logins a minute per IP would lock out a whole lab. Leave `LOGIN_THROTTLE_ACCOUNT_LIMIT` at 5. | No: it defaults to 5 (`config.py:131`, BLK-13) |

- **Use a fresh database.** If an old one is reused (the earlier Cloud SQL or Supabase database), first reset every account's password (the SuperAdmin's was the published demo password) and delete the demo accounts (BLK-10) and walk-in accounts created with the default password (UPG-15).
- **Test-send (owner, 2026-10-02).** After the first deploy, log in as the SuperAdmin and open `/diag/email?to=<your address>` (SuperAdmin-only, `routes_auth.py`). The message must arrive, not in spam, from `MAIL_FROM`. Then appoint a test judge on a test event and check that their set-password link arrives and works.
- **Proxy hops (owner, 2026-10-02).** `ProxyFix(x_for=1, x_proto=1)` (`app.py:151`) trusts exactly one proxy, which is right for Cloud Run alone; it never trusts `X-Forwarded-Host` (BLK-16). If Cloudflare or a load balancer is ever put in front, set `x_for` to the real number of proxies. Otherwise the app sees the proxy's address for every visitor, and BLK-13's per-IP limit counts everyone as one IP. Never set it higher than the real number: clients could then forge their IP in `X-Forwarded-For` and dodge the per-IP limit.
- **Check:** start the app once with these values and `FLASK_ENV=production`. It must start, and it must refuse to start if any start-up-checked value above is missing or weak (`tests/test_integration_flow.py::test_production_config_requires_real_secrets`).


#### BLK-01 — Admin credentials and a user database are in the public GitHub history
- **Status:** IN PROGRESS. Only GitHub Support's removal of the PR refs is left (criterion 0); nothing else waits on it.
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification), with read-only `git ls-remote`: `master` at `8b72203` (PR #49 merged), the remote `production-ready` at `37c2a5c` (Phase 2's local commits not pushed), and PR refs 1–49: the same 47 old ones, plus #48 and #49 on the rewritten history
- **Problem:**
  - The repo is public (the GitHub API returns 200 unauthenticated; 0 forks).
  - **Removed from all history on 2026-09-29, force-pushed by the owner on 2026-10-01:**
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
    - The remote branches `master` (all five paths), `main` (`.env`, `instance/`, `.pyc`) and `claude/busy-davinci-6nkabi` (all five) contained them too. **Fixed 2026-10-01** [R, `git ls-remote`]: GitHub's `master` is the rewritten `56a014d` (the same hash as local `master`), `production-ready` is `10207cd`, and `main` and `claude/busy-davinci-6nkabi` no longer exist. `git log origin/master origin/production-ready` finds none of the removed paths.
    - There are 0 commits reachable only from PR refs, so the PR refs add no content beyond the scanned branch history.
    - **Still on GitHub (2026-10-01):** all 47 `refs/pull/*` refs, unchanged. The owner has contacted GitHub Support.
  - **Mitigation from BLK-09:** `config.validate_production_config` (`app.py:145`) refuses to start production with a published default. Both leaked values are on its blocklist [C]. A SuperAdmin account already created with the leaked password keeps it in the database.
- **Who benefits:** everyone whose account or data is exposed.
- **What to build:**
  - **Done locally:** backups; history rewrite; `.gitignore` rules; `tests/test_repo_hygiene.py`; CI job "Repo hygiene & secret scan" (the hygiene test plus a pinned gitleaks 8.30.1 full-history scan, with accepted findings in `.gitleaksignore`). **The two Google API keys are deliberately not accepted, so the secret-scan step fails until they're revoked**; their fingerprints are commented out in `.gitleaksignore`, ready to un-comment.
  - **No deployment exists** (owner, 2026-09-30), so pushing can't trigger a production start. Cloud Run is the only deploy target (D-1). The first deploy must follow **"Before the next deploy"** at the top of this section.
  - **Owner, done 2026-10-01:** force-pushed the rewritten `master`, deleted the remote `main` and `claude/busy-davinci-6nkabi`, and pushed `production-ready` (verified with `git ls-remote`). The local `remote.origin.fetch` is restored and `master` tracks `origin/master`.
  - **Owner, done 2026-10-01:** contacted GitHub Support to remove the PR refs' copies and cached views of old commits (PR numbers above; `.git/commit-map-github-to-final.txt` maps original → new hashes). **Waiting on Support.**
  - **Owner, done 2026-09-30:** changed the old mail account's password (which also revokes its app passwords, so both leaked `MAIL_PASS` values are dead) and revoked both Google API keys (the old `GEMINI_API_KEY` and the second key).
  - **Owner, replaced by the checklist:** `SUPER_ADMIN_PASS` and `MASTER_SECRET_KEY` aren't in use anywhere, since there's no production. The next deploy must use new values ("Before the next deploy").
  - **Owner, still open:** the Supabase publishable key (only if that project is still used); collaborators re-clone, because their clones still hold the old history.
- **Files touched:** `.gitignore`, `.github/workflows/ci.yml`, `.gitleaksignore`, `tests/test_repo_hygiene.py`; history rewrite; operational steps outside the code.
- **Effort:** S · **Depends on:** none · **Risk:** the force-push breaks existing clones; old objects stay on GitHub (PR refs, cached views) until Support removes them.
- **Local artifacts (never push or commit):**
  - `~/saptha-event-portal-backup-2026-09-29.git`: the original history.
  - `~/saptha-event-portal-backup-2026-09-29-before-purge2.git`: after the first rewrite.
  - `~/saptha-local-data/saptha_fallback.db` and `~/saptha-local-data/dataconnect-.dataconnect/`: local dev data, owner-only permissions.
  - `.git/commit-map-github-to-final.txt`.
  - The push is confirmed (2026-10-01). Keep `.git/commit-map-github-to-final.txt` until GitHub Support has finished, in case they ask for it; then delete the backups and data copies (owner). Prefer the seed scripts for local data.
- **Acceptance criteria:**
  0. ✅ **Met locally and on GitHub's branches:** no local commit contains `saptha_fallback.db` or the other removed paths; on 2026-10-01 `git ls-remote` shows only `master` (`56a014d`, rewritten) and `production-ready` (`10207cd`), and neither branch's history contains a removed path [R]. ⬜ **PR refs:** all 47 still exist and still hold removed files; completes when GitHub Support removes them (owner contacted Support on 2026-10-01). **Doesn't block other items.**
  1. ✅ **Met:** `tests/test_repo_hygiene.py::test_no_forbidden_files_are_tracked` fails if any `*.db`, `*.sqlite*`, `.env*` (other than `.env.example`), service-account key, `*.pyc` / `__pycache__/`, `dataconnect/.dataconnect/` or `instance/` file is tracked. It passes at `08eabf5`.
  2. ✅ **Met:** the CI job "Repo hygiene & secret scan" runs that test and the gitleaks scan. Demonstrated on a throwaway branch in a scratch clone: a commit adding `.env`, `local.db`, a `.pyc` and a fake AWS-style key made the test fail (1 failed, naming the 3 files) and gitleaks exit 1 [R].
  3. ✅ **Met for now: there's no production deployment** (owner, 2026-09-30), so nothing accepts the old SuperAdmin password or master key. The next deploy must pass **"Before the next deploy"** (new `SECRET_KEY`, `MASTER_SECRET_KEY`, `JWT_SECRET_KEY`, `SUPER_ADMIN_PASS`, `RAZORPAY_KEY_SECRET`, and a PostgreSQL `DATABASE_URL`, all set first). The start-up refusal for published values exists (`tests/test_integration_flow.py:205`).
  4. ✅ **Met:** both Google API keys are revoked (owner, 2026-09-30) and accepted in `.gitleaksignore`. The full-history gitleaks scan finds **no leaks in 212 commits** [R]. ✅ **On GitHub:** CI run 36886209908 on the pushed `master` (`56a014d`, 2026-10-01) passed "Repo hygiene & secret scan" and "Lint (ruff)" [R, GitHub Actions API]. The bandit job failed on the known BLK-11 findings and pytest on BLK-15's causes. The old password and master key remain as literals in history (gitleaks doesn't flag them); they're unused and must not be reused (criterion 3).

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
- **Status:** DONE
- **Last verified:** 2026-10-01, commit "BLK-05: …" on `production-ready` (parent `7b394c0`)
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
- **What was built:**
  - `tests/conftest.py:18-38`: before any app import, every outbound credential and service setting in `OUTBOUND_CREDENTIALS` (mail, Brevo, Resend, Twilio, Gemini/Google, Razorpay, Stripe, VAPID, AWS/GCS storage, Supabase, Sentry, OAuth, Zoho, Cloud SQL, Firebase) is set to `''`, so `load_dotenv()` can't fill them from a developer's `.env`. Celery is forced inline with an in-memory broker: CI sets `CELERY_BROKER_URL=redis://…`, under which `.delay()` would queue tasks that never run in a test (and a developer's `.env` could point at a real broker).
  - Since BLK-02, `real_app` lives in `tests/conftest.py:398` and stubs `utils_email._send`, so no test sends mail.
  - `tests/test_event_journey_real_db.py`: one competitive event through the real routes: SPOC creates it and appoints a judge → the student registers → SPOC check-in → room/judge allocation → the judge scores (8 and 6 → 7.0) → the event completes → the certificate waits for feedback → feedback → the certificate page shows the name.
  - `tests/test_integration_flow.py::_login` now also fails when the login itself failed (both redirect with 302); no existing test relied on that.
- **Found while building:** submitted scores come back with renamed keys (BLK-06 criterion 9).
- **Files touched:** `tests/conftest.py`, `tests/test_integration_flow.py`.
- **Effort:** S (was M) · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ A `real_app` test runs register → check-in → score → feedback → certificate against the adapter (`tests/test_event_journey_real_db.py::test_register_checkin_score_feedback_certificate`). The certificate step is the HTML certificate page; PDF generation is UPG-06.
  2. ✅ Tests can't touch a developer database: `DATABASE_URL` is forced to a temp DB before import (`tests/conftest.py:40-47`) and wins over `CLOUD_SQL_INSTANCE` (`db_pg.py:110-121`). ✅ After the app (and `load_dotenv()`) has loaded, every outbound credential is empty and Celery is inline on a non-Redis broker (`::test_tests_never_see_real_outbound_credentials_or_a_real_broker`). With the blanking removed and a fake `MAIL_PASS` preset, this test fails.
  3. ✅ All earlier tests still pass: **448 passed, 1 xfailed** on SQLite, on PostgreSQL 16, and with CI's `CELERY_BROKER_URL=redis://…` set; ruff clean.

#### BLK-06 — The SQL adapter loses, renames and ignores fields (postgres mode)
- **Status:** DONE, in two sub-items: **BLK-06a** (filters on real values, workflow states, `spoc_id` column, audit actor, organisation keys) and **BLK-06b** (document shadow on the newer tables, team members and scores, ticket check-in time). Criterion 4's "bulk certificates on `real_app`" moved to UPG-06 criterion 4, which covers the same button.
- **Last verified:** 2026-10-01, commit "BLK-06b: …" on `production-ready` (parent `dda7716`; BLK-06a is `dda7716`)
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
    7. **Scores come back with renamed keys** [R, found in BLK-05]. `judge.submit_score` writes `scores[<judge>] = {details, total, raw_total, remarks, judge_name, submitted_at}` (`routes_judge.py:167-176`), but on the real adapter it reads back as `{criteria, total, feedback, judge_name, timestamp}`: `raw_total` is dropped and three keys are renamed (the `Score` table has no document shadow, item 2). Code reading `details` or `remarks` gets nothing.
- **Who benefits:** every user; this is the root cause of most PARTLY BUILT rows at `694c729`.
- **What to build:** store role and category as plain strings (or complete the enums with every value the app writes) plus an Alembic migration; workflow states the enum doesn't know (e.g. `evaluation`) are stored as themselves, never as `active`; add `extra_json` to the remaining tables; write `actor_email` from `log_action`; add real indexed columns for hot filter fields (at least `events.spoc_id`), filled from the shadow for existing rows.
- **Built in BLK-06a** (approach changed from "plain strings", see below):
  - **Filters compare the stored value.** For every enum-backed field (role, category, event and registration status, payment status, attendance), `SQLQuery.stream` narrows in SQL only where that can't drop a match and then compares the document value (`db_adapter.py:1589-1620`, `:1675`). Only explicit synonyms are equal (`Coordinator`/`EventCoordinator`, `Student`/`Participant`, `ClubSPOC`/`SPOC`, `SuperAdmin`/`Admin`, any case); everything else compares as text, so `UniversityAdmin` never matches the `Participant` fallback and `NSS` never matches `Technical`. `!=` on these fields is never pushed to SQL.
  - **Writes use the same mapping** (`_to_member`, `db_adapter.py:1501`): a value with a member (e.g. `UniversityAdmin`, `EventOrganizer`) is stored as that member instead of falling back.
  - **Workflow states are stored as themselves:** `EventStatus` gains `evaluation`; `RegistrationStatus` gains every participant workflow state (`applied`, `pending_payment`, `round_1`, `shortlisted`, …) (`models_pg.py:67,76-93`); `'Pending Payment'` is an alias of `pending_payment` (`db_adapter.py:174`); the old `applied → pending` alias is gone.
  - **`events.spoc_id`** is an indexed column (`models_pg.py:357`), written from the document (`db_adapter.py:1112`), so `where('spoc_id', …)` runs in SQL. No current code filters on it through the adapter, so existing rows with a NULL column hide nothing.
  - **Audit actor:** the `actorEmail` column takes `actor_email`, `actorEmail` or `log_action`'s `user` (`db_adapter.py:1169`).
  - **Organisation API key:** empty is stored as NULL (`db_adapter.py:1216`, and on update), so organisations without keys coexist.
  - **Why not plain strings:** `tests/test_db_adapter_merge.py::test_users_role_still_uses_the_role_enum` pins `users.role` as an enum column (a BLK-09 decision), and two status tests read the enum columns. Keeping the enum columns as a coarse index and comparing real values meets the same criteria without changing those tests or the column types.
  - **Existing databases:** rows written before BLK-06a can hold a stale coarse value (e.g. `confirmed` for `Pending Payment`), and an SQL-narrowed query can miss them. There's no production data; UPG-16's migration should recompute these columns from `extra_json` for any database that predates it. PostgreSQL databases created before this change also need the new enum members (`ALTER TYPE … ADD VALUE`), which UPG-16's baseline includes; fresh databases get them from `create_all`.
  - The strict xfail `test_active_filter_excludes_states_outside_the_enum` now passes; its marker is removed.
- **Built in BLK-06b:**
  - `extra_json` document shadow on `OrgUnit`, `RoleAssignment`, `Campus`, `Building`, `Room`, `VenueBooking`, `TeamMember` and `Score` (`models_pg.py`); the adapter's existing shadow logic now covers the first six, so fields without a column survive writes and merging updates.
  - Team members and judges' scores are child rows rebuilt on read, and the registration's own shadow is shallow (a second judge's score would replace the first). So each member and score row now stores the dict it was written from (`db_adapter.py:1461`, `:1483`, `:1491`) and returns it on read (`:964`, `:978`). Per-member attendance from granular check-in, member roles, and the judge route's `details`/`remarks`/`raw_total`/`submitted_at` now read back as written; older rows fall back to the columns.
  - **Found and fixed here:** `parse_datetime` turns an empty value into "now", so every new ticket was stored with `checkedInAt` set and read back as `checked_in: True`. A nullable date column now stays NULL when empty (`db_adapter.py:1367`), and new tickets start unchecked (`:1240`).
  - `tests/test_event_journey_real_db.py` asserts the per-criterion score values again (they read back correctly now).
- **Files touched:** `db_adapter.py`, `models_pg.py`, `migrations/`, `utils.py`, tests.
- **Effort:** M (was L) · **Depends on:** BLK-05 · **Risk:** schema migration on existing PostgreSQL data.
- **Acceptance criteria:**
  1. ✅ Round-trip of every key used by `routes_*` for events, registrations and users returns identical values (`tests/test_db_documents.py:56`; re-run [R]). ✅ The same for org units, role assignments, campuses, buildings, rooms, venue bookings and tickets, including nested values and merging updates; a new ticket reads back unchecked (`tests/test_db_documents_newer_tables.py::test_newer_tables_and_tickets_keep_every_field`); team members keep role, WhatsApp and per-member attendance (`::test_team_members_keep_their_role_and_attendance`).
  2. ✅ `where('usn','==',x)` returns only that user and `/u/<usn>` shows the right student [R].
  3. ✅ `where('role','==','UniversityAdmin')` returns exactly the UniversityAdmin user; `'Participant'` returns Student and Participant users but not the admin; legacy synonyms still match; `where('category','==','Technical')` excludes the NSS event (`tests/test_db_filters_real_values.py::test_role_filters_match_the_stored_role`, `::test_category_filters_match_the_stored_category`).
  4. ✅ The SPOC owner can assign a coordinator (`tests/test_integration_flow.py:177-181`) [R]. ➡ Bulk certificates on `real_app`: moved to UPG-06 criterion 4 (the PDF task still has a signature bug there).
  5. ✅ The `actorEmail` column holds the acting user's email, and `where('actor_email', …)` finds it (`::test_audit_log_records_the_real_actor`).
  6. ✅ `where('status','==','active')` excludes an event in `evaluation` (the former strict xfail passes and its marker is removed); `evaluation` and `pending_payment` are stored as themselves in the columns, and a `Pending Payment` registration doesn't match `confirmed` (`::test_workflow_states_are_stored_as_themselves`).
  7. ✅ `events.spoc_id` is indexed; `where('spoc_id','==',x)` returns only that event and the executed SQL has `spoc_id` in its `WHERE` (`::test_spoc_id_is_an_indexed_column_answered_by_sql`).
  8. ✅ Two organisations without an `api_key` both save with `NULL` keys, and updating one to `''` still works (`::test_organisations_without_api_keys_can_coexist`).
  - All six BLK-06a tests fail on the old adapter. Full pytest: **455 passed** on SQLite and PostgreSQL 16 (no xfail left); ruff clean.
  9. ✅ Scores submitted by two judges through `/judge/submit_score` both survive and each reads back with exactly `details`, `total`, `raw_total`, `remarks`, `judge_name`, `submitted_at` (`::test_scores_read_back_with_the_keys_the_judge_route_wrote`).
  - All three BLK-06b tests fail on the pre-06b adapter. Full pytest: **458 passed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-07 — Role migration locks out SuperAdmin and SPOC accounts
- **Status:** DONE
- **Last verified:** 2026-10-01, commit "BLK-07: …" on `production-ready` (parent `c05af5e`)
- **Problem:** Re-run on `1f4cdc8` [R].
  - `GET /admin/org_units` no longer rewrites roles on a fresh database. That's **incidental**: the adapter now creates the root `central` org unit at start-up (`db_adapter.py` `SQLFirestoreAdapter._ensure_root_units`, added in the BLK-09 merge), so the `if not units:` auto-migration (`routes_admin.py:642-644`) doesn't fire.
  - The "Migrate roles" action (`POST /admin/migrate_roles`) still rewrites the SuperAdmin to `UniversityAdmin` (`services_permission.py:422`) and mapped SPOCs to `UnitAdmin` (`:454`). Login maps only legacy names (`routes_auth.py:94-101`), so the SuperAdmin was **locked out** after pressing it [R].
- **Who benefits:** SuperAdmin and every SPOC.
- **What to build:** make migration an explicit POST with a dry-run preview and a confirm step; keep `users.role` compatible with login (or map `UniversityAdmin` → SuperAdmin and `UnitAdmin` → ClubSPOC at login); delete the GET-time trigger.
- **What was built:**
  - `GET /admin/org_units` never migrates (`routes_admin.py:641`).
  - `POST /admin/migrate_roles` (`routes_admin.py:806`) runs `migrate_roles_and_units(db, dry_run=True)` unless `confirm=1`: it flashes the summary ("Preview only, nothing changed") and the page then shows a **Confirm migration** button (`templates/admin/org_units.html`). `dry_run` guards every write (`services_permission.py:345`).
  - The migration still writes the scoped names into `users.role` (an existing test, `tests/test_scoped_roles_e2e.py::test_role_migration_maps_demo_users_and_backfills`, pins that), and **login maps them back**: one `_login_role` table (`routes_auth.py:33-45`) used by login (`:112`), forgot-password and reset-token, so `UniversityAdmin` logs in as SuperAdmin and `UnitAdmin` as ClubSPOC, and a migrated admin still can't reset by email. The API login maps the same two names, leaving every other role as before for the mobile apps (`routes_api_v1.py:81`). This is also the repair for any database already migrated.
- **Files touched:** `routes_admin.py`, `services_permission.py`, `routes_auth.py`, `routes_api_v1.py`, `templates/admin/org_units.html`, `tests/test_role_migration_keeps_access.py` (new).
- **Files touched:** `routes_admin.py`, `services_permission.py`, `routes_auth.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** production may already contain migrated roles; include a repair step.
- **Acceptance criteria:**
  1. ✅ `GET /admin/org_units` doesn't migrate even when it sees no org units (the old trigger's condition), and roles stay unchanged (`tests/test_role_migration_keeps_access.py::test_viewing_org_units_never_migrates`).
  2. ✅ A user stored as `UniversityAdmin` logs in as SuperAdmin and opens `/admin/dashboard`; `UnitAdmin` logs in as ClubSPOC and opens `/spoc/dashboard`; the migrated admin gets no reset email (`::test_already_migrated_accounts_log_in_with_their_old_roles`); the API login works for a migrated admin (`::test_api_login_works_for_migrated_accounts`).
  3. ✅ `POST /admin/migrate_roles` without `confirm=1` changes no role or grant and offers the confirm button; with it, grants are written, and **the SuperAdmin and the SPOC log straight back in and reach their dashboards** (`::test_migrate_previews_first_and_the_superadmin_keeps_access_after_confirming`).
  - All four tests fail on the old code. Full pytest: **462 passed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-08 — Users are logged out at random once ~500 sessions exist; sessions don't survive restarts or span instances
- **Status:** DONE
- **Last verified:** 2026-10-01, commit "BLK-08: …" on `production-ready` (parent `22598e7`)
- **Problem:** Unchanged by BLK-09 [C at `56a014d`].
  - Without `REDIS_URL`, sessions are files under `/tmp/flask_session` (`config.py:52-61`). Flask-Session's default file threshold is 500; past it, sessions are pruned.
  - Every anonymous page view creates a session (1 → 11 files after 10 views [R at `694c729`]). At 502 files, logged-in users were logged out mid-flow [R at `694c729`].
  - **Merged in Phase 0 (the "sessions in /tmp" item):** on Cloud Run each instance has its own `/tmp`, which is wiped on restart and redeploy. So every restart logs everyone out, and with two instances a user bounces between "logged in" and "logged out" depending on which instance answers.
  - `docker-compose.yml` provides Redis for self-hosting; the Cloud Run + Supabase target has no Redis.
  - Production cookies: `SESSION_COOKIE_SECURE` and `SameSite=Strict` are set in production (`config.py:45-46`); `HttpOnly` relies on Flask's default. `Strict` drops the cookie when a user arrives from an email link or a payment redirect, so they look logged out on that first page.
- **Who benefits:** everyone on busy days, and after every deploy.
- **What to build:** server-side sessions through Flask-Session's SQLAlchemy backend, in the app database (Redis when `REDIS_URL` is set). This adds a `Flask-SQLAlchemy` dependency, or a small custom session interface on the existing engine; pick the smaller change. Expired rows are cleaned up (UPG-07's clean-up job). Secure, HttpOnly, SameSite=Lax cookies in production. Don't create sessions for anonymous GETs that don't need CSRF.
- **What was built:**
  - `session_store.py`: a Flask session interface on the app's own database (the smaller change: no Flask-SQLAlchemy dependency). The cookie holds only a random id; the data (Flask's tagged-JSON format) lives in a `flask_sessions` table (`models_pg.FlaskSession`, `models_pg.py:579`). Reads and writes use the primary engine, because sessions are saved during GETs too (`session_store.py:35`). An empty, unmodified session is never stored; logout deletes the row and the cookie; an unmodified session is re-saved only when its expiry has drifted by more than an hour (`:86-122`). `purge_expired_sessions` (`:125`) is ready for UPG-07's clean-up job.
  - `config.py`: `SESSION_TYPE` defaults to `redis` when `REDIS_URL` is set, otherwise `sqlalchemy` (the database; `:60`); `filesystem` only if chosen explicitly, with `SESSION_FILE_THRESHOLD` 50000 (`:63`); cookies are `HttpOnly`, `Secure` in production and `SameSite=Lax` (`:48`). A Redis failure now falls back to the database, not files (`app.py:194-207`).
  - Anonymous page views: the shared layout's `<meta name="csrf-token">` used to mint a token, and so a session, for every visitor. It now uses `csrf_meta_token()` (`app.py:177`), which mints one only for logged-in users or when the session already has one; forms still call `csrf_token()`. The 110 standalone pages still mint one in their own meta tag (each anonymous visitor there gets a 2-hour session row, purged on expiry) until they move to the shared layout (UPG-23).
  - CI still sets `SESSION_TYPE=filesystem`; the session tests set the database store explicitly, so they test the production default either way.
- **Files touched:** `session_store.py` (new), `config.py`, `app.py`, `models_pg.py`, `templates/base_classic.html`, `tests/test_sessions_server_side.py` (new).
- **Effort:** M (was S) · **Depends on:** none · **Risk:** everyone is logged out once when the backend switches.
- **Acceptance criteria** (all in `tests/test_sessions_server_side.py`, on the real database; all fail on the old code):
  1. ✅ After 600 different anonymous visitors (600 session rows), a logged-in user is still logged in and opens their dashboard (`::test_anonymous_traffic_creates_no_sessions_and_logs_nobody_out`).
  2. ✅ `SESSION_FILE_THRESHOLD` is at least 50000 (`::test_file_sessions_if_chosen_keep_a_high_threshold`).
  3. ✅ An anonymous `GET /events` sets no session cookie and stores no row (same test as 1).
  4. ✅ A session created by the real app is accepted by a second, separately created app instance sharing only the database; logging out ends it there too (`::test_a_session_works_on_another_instance_and_after_a_restart`).
  5. ✅ After a "restart" (a brand-new session store, same database) the user is still logged in (same test). Expired sessions are ignored and purged (`::test_expired_sessions_are_ignored_and_purged`).
  6. ✅ Production config gives `Secure`, `HttpOnly`, `SameSite=Lax` and the database store by default, and the cookie the app sends carries those flags (`::test_production_cookies_are_secure_httponly_and_lax`).
  - Full pytest: **467 passed** on SQLite, PostgreSQL 16, and with CI's `SESSION_TYPE=filesystem`; ruff clean.

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
- **Status:** DONE (10a + 10b).
- **Last verified:** 2026-10-01, commit "BLK-10b: …" on `production-ready` (parent `8ecdc9e`)
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
- **Built in BLK-10a:**
  - `seed_safety.py`: `guard()` (`:84`) loads `.env` as the app would, then refuses with exit code 3 when `production_reasons()` (`:48`) finds `FLASK_ENV=production`, `CLOUD_SQL_INSTANCE`, a Cloud SQL socket URL, or a `DATABASE_URL` host other than SQLite, a local Unix socket, localhost/127.0.0.1/::1 or the docker-compose `db` service. Only `--i-know-this-is-production` on the command line overrides it. `guard(firestore=True)` also requires `--confirm-firestore-project=<id>` matching the service-account key's project (or a local emulator). The message names the host, never the URL. `seed_password()` (`:104`) is ready for BLK-10b.
  - All 31 seed, setup, wipe, delete and reset scripts (root, `scripts/`, `scratch/`) call `guard()` first, before any project import; the 10 that use the Firestore client call `guard(firestore=True)`.
- **Built in BLK-10b:**
  - `seed_safety.py`: `seed_password(role)` returns `SEED_<ROLE>_PASSWORD` from the environment if set, or generates a secure random password using `secrets.token_urlsafe(12)`. All generated passwords are recorded and printed in a single clear summary table at the end of execution.
  - All 19 seed, setup, and reset scripts updated to use `seed_password(...)` instead of hardcoded string literals.
- **Files touched:** all seed/setup scripts listed above, new `seed_safety.py`, tests.
- **Effort:** S · **Depends on:** none (merging scripts overlaps UPG-15) · **Risk:** low; breaks anyone relying on the published demo logins (they're printed instead).
- **Acceptance criteria:**
  1. ✅ Test: an AST scan of every seed/setup script finds no string literal used as a password (dict keys or arguments named like `password`, `password_raw`, `*_PASS`) (`tests/test_seed_safety.py::test_no_script_uses_a_string_literal_as_a_password`).
  2. ✅ Each of the 31 scripts, run with a remote `DATABASE_URL`, with `CLOUD_SQL_INSTANCE`, with `FLASK_ENV=production`, or with a Cloud SQL socket URL, exits 3 before any connection: SQLAlchemy engines, Firebase and HTTP are replaced by "exit 99" in the test runner; the URL is never echoed; every script calls `guard()` before any other import (`tests/test_seed_safety.py`, 124 parametrised cases plus the local-database check).
  3. ✅ Test: with a local SQLite `DATABASE_URL`, the seed creates accounts whose passwords come from `SEED_*_PASSWORD` when set, and are random (different across two runs) when not (`tests/test_seed_safety.py::test_seed_passwords_come_from_the_environment_or_are_random`).
  4. ✅ With a production-looking target, environment variables don't override the guard and the command-line flag does; Firestore scripts additionally need the right project named (a wrong one is refused) (`::test_only_the_command_line_flag_overrides_the_guard`, `::test_firestore_scripts_also_need_the_project_named`).
  - Full pytest: **658 passed** on SQLite and PostgreSQL 16; ruff clean.
  - **Found 2026-10-01 (BLK-15, now DONE):** criterion 4's Firestore check read a different key than the scripts used and accepted any project name when it found none; its test passed only where the untracked `serviceAccountKey.json` existed, so it failed in CI. Fixed by BLK-15.

#### BLK-11 — CI's bandit job fails on 5 pre-existing issues, so CI can't go green
- **Status:** DONE
- **Last verified:** 2026-10-01, commit "BLK-11: …" on `production-ready` (parent `affcab7`)
- **Problem:** The CI job "Security scan (bandit)" (`bandit -r . -x tests/,__pycache__/ -ll -q`, `.github/workflows/ci.yml`) exits 1 on 5 Medium-severity findings [R, fresh clone of `f956456`]:
  - `functions/saptha_app/audit_logger.py:111`, `:162` (B104, binding to all interfaces).
  - `functions/saptha_app/db_adapter.py:98`, `:108` (B608, SQL built from strings).
  - `scripts/seed_emulator.py:26` (B113, `requests` call without a timeout); `:33` since BLK-10a added the guard at the top (re-run 2026-10-01: the same 5 findings, nothing new).
  - These **predate this work**: the branch alone fails with the same 5, and the old `master` (`89af3d3`) had 9. The merge fixed the root copies of `audit_logger.py` and `db_adapter.py`.
  - GitHub's CI on `master` has failed on every run since at least 2026-08-25. So even after the force-push, CI stays red until this is fixed, which undermines "every acceptance criterion has a passing test" for later items.
- **Who benefits:** everyone building later items; CI becomes a trustworthy gate.
  - Re-run in Phase 0 at `56a014d` (same command, local): exactly the same 5 findings.
- **What to build:** add a timeout to the `scripts/seed_emulator.py` request. The `functions/saptha_app/` copy is removed in Phase 5 (UPG-15; D-1 decided 2026-10-01), so until then fix its two files in place, as the root copies were fixed, so CI can go green now. Don't blanket-exclude directories or add `# nosec` without a reason.
- **What was built** (the same fixes the root copies got, so the copy stays harmless until UPG-15 deletes it):
  - `functions/saptha_app/audit_logger.py:111,162`: `# nosec B104 — placeholder IP, not a bind address`, word for word as in the root `audit_logger.py:111,162`. `"0.0.0.0"` is only the logged IP when there's no request.
  - `functions/saptha_app/db_adapter.py` `verify_and_align_schema`: the two `information_schema` lookups use bound parameters (`:table`, `:col`) instead of f-strings, as in the root `db_adapter.py:289-303`.
  - `scripts/seed_emulator.py:33`: the emulator request has `timeout=30`.
  - No directory excluded; no `# nosec` without a reason.
- **Files touched:** `functions/saptha_app/audit_logger.py`, `functions/saptha_app/db_adapter.py`, `scripts/seed_emulator.py`.
- **Effort:** S · **Depends on:** none · **Risk:** low; nothing deploys the `functions/` copy (D-1).
- **CI on GitHub (2026-10-01, after the owner's push):** on `master` (`56a014d`) "Security scan (bandit)" failed as expected and "Test (pytest)" failed (cause reproduced; recorded in BLK-15), while "Repo hygiene & secret scan" and "Lint (ruff)" passed. CI runs only on pushes to `main`/`master`/`develop` and on pull requests into `main`/`master` (`.github/workflows/ci.yml:3-7`), so commits pushed to `production-ready` get no CI run until a pull request into `master` is opened.
- **Acceptance criteria:**
  1. ✅ `bandit -r . -x tests/,__pycache__/ -ll -q` exits 0 on a fresh clone [R]; it found the 5 issues before the fix. CI's "Security scan (bandit)" job runs this command on every push and pull request into `master`.
  2. ✅ Every job in the CI workflow is green on GitHub [R, GitHub Actions API]. On pull request #48: run 36958162992 (`9e28bf3`) and run 36958733560 (`7aac9ca`) passed hygiene and gitleaks, ruff, pytest and bandit; Docker build is skipped on pull requests. After the merge, on `master` (`86348fe`): run 36959323400 passed all five jobs, Docker build included.
  3. ✅ `ruff check .` is clean and the full pytest passes: **689 passed** on SQLite and PostgreSQL 16.

#### BLK-12 — Kiosk and ticket-verify holes (and tests for them on the real database)
- **Status:** DONE for the root app (criterion 4 is met when UPG-15 removes the `functions/` copy in Phase 5; D-1)
- **Last verified:** 2026-10-01, commit "BLK-12: …" on `production-ready` (parent `f2ce15b`)
- **Problem:** Added in Phase 0 from the production-ready plan's list: unauthenticated kiosk search and confirm, a raw registration ID accepted by ticket verify, a GET that marks attendance, and self check-in by email alone.
  - **Already fixed in the root app** (by the BLK-09 merge, branch commit `348aceb`) [C at `56a014d`]:
    - Kiosk search and confirm need login, a coordinator-level role and `can(…, 'check_in', event)`; search queries only that event and returns no emails or phones (`routes_checkin.py:236-400`).
    - `/ticket/verify` and `/ticket/api/verify` accept signed tokens only and refuse raw IDs (`routes_ticket.py:56-84`); the GET is read-only; the check-in POST needs a coordinator-level role with access to the event (`routes_ticket.py:318-327`).
    - Self check-in needs the logged-in owner (lead or team member) plus a signed venue code valid for 10 minutes (`routes_checkin.py:86-128`).
  - **But the tests pinning this run on the in-memory mock**, not the SQL adapter: `tests/test_checkin_security.py` (7 tests, `client`/`mock_db` fixtures).
  - **The `functions/saptha_app` copy (run by the Zoho Catalyst deploy, `catalyst.json`) still has all four holes** [C]: kiosk search/confirm have no login (`functions/saptha_app/routes_checkin.py:143-224`); self check-in takes a typed email (`:45-60`); `/ticket/verify/<reg_id_or_token>` accepts raw registration IDs and marks attendance on a GET (`functions/saptha_app/routes_ticket.py:164-231`), and so does `/ticket/api/verify` (`:279-325`).
- **Who benefits:** every attendee (privacy) and organiser (attendance integrity).
- **What to build:** `real_app` tests for each fixed behaviour. For the `functions/` copy: Cloud Run is the only deploy target (D-1, 2026-10-01), so UPG-15 removes it in Phase 5; no port of the root fixes.
- **What was built:** `tests/test_checkin_security_real_db.py`, 3 tests on the real SQL adapter. No app code changed: the root fixes predate this branch. To show the tests catch the holes, each was briefly reintroduced and the matching test failed: kiosk search without login (kiosk test fails), a venue code that doesn't expire in 10 minutes (self check-in test fails), raw registration IDs accepted by verify (ticket test fails).
- **Files touched:** `tests/`, and `functions/saptha_app/` (removed by UPG-15).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Anonymous kiosk search and confirm are sent to log in and change nothing; an unassigned coordinator gets 403; an assigned one gets only that event's match (not a same-named registrant of another event), with no email or phone in the JSON, and can confirm (`tests/test_checkin_security_real_db.py::test_kiosk_needs_staff_of_the_event_and_never_leaks_contact_details`).
  2. ✅ A raw registration ID on `/ticket/verify` and `/ticket/api/verify` (GET and POST) → 400; GETs with a valid token, anonymous or staff, never change attendance; POSTs by a student or an unassigned coordinator → 403; a POST by assigned staff marks `Present` (`::test_ticket_verify_takes_signed_tokens_only_and_only_staff_mark_attendance`).
  3. ✅ Self check-in sends anonymous users to log in, does nothing for a logged-in user without a registration, and refuses the owner with a missing, malformed, 11-minute-old or other-event code; the owner with a fresh code is marked `Present` (`::test_self_checkin_needs_the_owner_and_a_fresh_code_for_this_event`).
  - Full pytest: **446 passed, 1 xfailed** on SQLite and PostgreSQL 16; ruff clean.
  4. ⬜ The `functions/saptha_app` copy is no longer tracked (D-1: removed by UPG-15 in Phase 5).

#### BLK-13 — Login has no rate limiting
- **Status:** DONE
- **Last verified:** 2026-10-01, commit "BLK-13: …" on `production-ready` (parent `07cf145`)
- **Problem (as found at `56a014d`):** Added in Phase 0 [C]. Re-checked against the code at `07cf145` before building: `routes_auth.py`, `routes_api_v1.py`, `models_pg.py` and `config.py` had changed (BLK-02/03/06/07/08), but only the line numbers moved (the limiter settings are now `config.py:122-124`).
  - `/login` (`routes_auth.py`) and `/api/v1/auth/login` (`routes_api_v1.py:45`) have no rate limit. The global default is 100000/day and 10000/hour (`config.py:114`); only the form and chatbot routes set their own limits (`routes_forms.py:292,345`, `chatbot_routes.py:42`).
  - `security_middleware.py:49-110` has per-IP and per-account throttling helpers (`record_login_attempt`, `is_account_locked`), but **nothing calls them**, and they keep state in process memory, so it's lost on restart and not shared across instances or gunicorn workers.
  - The limiter's storage is `memory://` unless `REDIS_URL` is set (`config.py:115`), which has the same per-process problem.
- **Who benefits:** every account (password guessing).
- **What to build:** about 5 failed attempts per minute per IP and per account on `/login`, `/api/v1/auth/login` and the password-reset request, with a clear "try again in N seconds" message (429 for the API). Counters are shared across instances: Redis when `REDIS_URL` is set, otherwise a small database table. A successful login resets the account counter. Don't reveal whether the account exists.
- **What was built:**
  - `services_login_throttle.py`: a sliding window of at most `LOGIN_THROTTLE_IP_LIMIT` attempts per IP and `LOGIN_THROTTLE_ACCOUNT_LIMIT` per account in any `LOGIN_THROTTLE_WINDOW` seconds (defaults 5, 5, 60; `config.py:130-133`, documented in `.env.example`).
    - `retry_after` (`:148`) gives the wait; `record_failure` (`:161`) and `clear_account` (`:173`) update the counters.
    - Counters live in the new `login_attempts` table (`models_pg.LoginAttempt`, `models_pg.py:588`), or in Redis sorted sets when `REDIS_URL` is set (`LOGIN_THROTTLE_STORAGE`, `config.py:133`).
    - A Redis error falls back to the database. If the counters can't be read at all, the attempt is allowed and the error is logged.
    - Keys are SHA-256 hashes, so no email or IP is stored.
    - Old rows are deleted as new ones arrive; `purge_expired` (`:188`) is ready for UPG-07's clean-up job.
  - **Web login** (`routes_auth.py:83-86`): checked before the master key and before the account is looked up, so the answer doesn't depend on whether the account exists. A refusal returns 429 with the login page, the message "Too many attempts. Please try again in N seconds." and `Retry-After` (`_throttled`, `:54`).
    - Every failure is recorded: bad master key, unknown account, wrong password or role (`:91,126,148`).
    - A success clears only the account's counter (`:121,164`). The IP's counter stays, so one valid account can't buy more guesses at others.
  - **API login** (`routes_api_v1.py:62-88`): the same check and the same counters as the web, so alternating between web and API doesn't double the rate. A refusal returns `429 too_many_attempts` with `details.retry_after` and `Retry-After`. Unknown accounts and wrong passwords both record a failure and get the same 401.
  - **Password-reset request** (`routes_auth.py:337-341`): every request counts per IP and per requested email, known or not, under its own counter. Refused requests send no email.
  - A refused attempt isn't recorded, so a lockout ends one window after the failures that caused it.
  - `tests/conftest.py:248` (`_fresh_login_throttle`, autouse) clears the counters before each test, because every test client logs in from `127.0.0.1`. Without it, failed logins in one test would throttle the next one.
  - `requirements-dev.txt`: `fakeredis==2.39.0`, so the Redis path is tested.
- **Files touched:** `services_login_throttle.py` (new), `models_pg.py`, `config.py`, `routes_auth.py`, `routes_api_v1.py`, `.env.example`, `requirements-dev.txt`, `tests/conftest.py`, `tests/test_login_throttle.py` (new). `security_middleware.py`'s unused in-memory helpers are left for UPG-14.
- **Effort:** S · **Depends on:** none · **Risk:** a whole lab behind one NAT IP shares the per-IP limit; only failures count, and `LOGIN_THROTTLE_IP_LIMIT` can be raised without a code change. Production sets it to about 50, and the proxy-hop setting must match the real proxies (both in "Before the next deploy"). The new `login_attempts` table is created by start-up `create_all` until UPG-16's migrations exist.
- **Acceptance criteria** (all in `tests/test_login_throttle.py`, on the real database layer; the parametrised tests run on the database and on Redis (fakeredis); 13 of the 15 fail with the old route code, and the other 2 (API success resets the counter) fail when only that reset is removed):
  1. ✅ The 6th failed login within a minute from one IP gets 429 with "Please try again in 60 seconds." and `Retry-After: 60`, after failures on 5 different known and unknown accounts. While blocked, even the right password from that IP is refused and logs nobody in; other IPs aren't affected (`::test_sixth_failed_login_from_one_ip_is_refused_across_accounts`). Password-reset requests are limited per IP and per account, and a refused request sends no email (`::test_password_reset_requests_are_limited_per_ip_and_per_account`).
  2. ✅ The 6th failed attempt on one account from 6 different IPs is refused, and so is the right password. The wait counts down (15 s left after 45 s), and once the window passes the correct password works (`::test_sixth_failure_on_one_account_from_different_ips_is_refused_until_the_window_passes`). A success resets the account counter but not the IP's (`::test_success_resets_the_account_counter_but_not_the_ip_counter`).
  3. ✅ Failures recorded by a second app instance **in a separate Python process**, sharing only the database, count here: 3 + 2 on the account, 2 + 3 from the IP (`::test_failures_recorded_by_another_process_count_here`). With Redis, separate client connections share the counters (`::test_redis_counters_are_shared_by_separate_clients`), and a Redis outage falls back to the database and still throttles (`::test_a_redis_outage_falls_back_to_the_database`).
  4. ✅ `/api/v1/auth/login` is limited the same way: per account, per IP, and on one counter shared with the web login. The 429 body is identical for an existing and an unknown account (`{"error": "too_many_attempts", "message": "Too many attempts. Please try again in 60 seconds.", "details": {"retry_after": 60}}`), as are the 401s before it (`::test_api_login_is_limited_the_same_way_and_answers_alike_for_unknown_accounts`). An API success resets the account counter (`::test_api_success_resets_the_account_counter`).
  - Full pytest: **673 passed** on SQLite and on PostgreSQL 16; ruff clean; bandit shows only the 5 known BLK-11 findings. With CI's environment (fresh clone, `REDIS_URL` and the Celery broker on a Redis server, CI's command): 672 passed, 1 failed, the known BLK-15 test.

#### BLK-14 — Anyone can create a SuperAdmin account through the public tenant sign-up
- **Status:** DONE (criterion 3 is met when UPG-15 removes the `functions/` copy in Phase 5; D-1)
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
  3. ⬜ The `functions/saptha_app` copy is removed (D-1: by UPG-15 in Phase 5).
  - Full pytest: **426 passed, 1 xfailed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-15 — The Firestore seed guard checks a different key than the scripts use, and its test fails in CI
- **Status:** DONE
- **Last verified:** 2026-10-01, commit "BLK-15: …" on `production-ready` (parent `9135851`)
- **Problem (as found):** Found on 2026-10-01 while checking CI after the owner's push. Reproduced in fresh clones with CI's test-job environment (`.github/workflows/ci.yml:77-85`, a Redis server on port 6379, CI's exact pytest command) [R].
  - **CI's pytest fails on `production-ready`:** at `10207cd`, **657 passed, 1 failed**. The failure is `tests/test_seed_safety.py::test_firestore_scripts_also_need_the_project_named`.
    - The test points `GOOGLE_APPLICATION_CREDENTIALS` at a fake key. `seed_demo.py` ignores that variable and loads `FIREBASE_CREDENTIALS` or `./serviceAccountKey.json` (`seed_demo.py:37-45`).
    - `serviceAccountKey.json` is git-ignored (`.gitignore:4`), so a fresh clone doesn't have it. The script exits 1 before reaching the stubbed connection, and the test expects 99.
    - It passes in the developer's checkout only because the real key file is there; BLK-10's "658 passed" was run there.
  - **The same mismatch is a hole in the guard.** `seed_safety._firestore_project` (`seed_safety.py:69-76`) reads only `GOOGLE_APPLICATION_CREDENTIALS` or the repo-root `serviceAccountKey.json`. The 10 Firestore scripts load credentials from other places:
    - `FIREBASE_CREDENTIALS` (JSON in the environment): `seed_demo.py:37`, `saptha_full_seed.py:40`, `seed_presentation.py:35`;
    - `FIREBASE_KEY_PATH`: `seed_live_demo.py:48`, `setup_tomorrow_demo.py:42`, `scratch/seed_single_event.py:38`;
    - a `serviceAccountKey.json` relative to the current directory: `delete_data.py:17`, `setup_db.py:19` (and the fallbacks above).
    - So when the guard finds no key (for example, only `FIREBASE_CREDENTIALS` is set), it accepts **any** `--confirm-firestore-project` value (`seed_safety.py:94`, `expected and confirmed != expected`). When the guard's key and the script's key differ, it confirms one project and the script writes to the other.
  - **CI's pytest also fails on `master` (`56a014d`), for a reason already fixed on `production-ready`:** with CI's `CELERY_BROKER_URL=redis://…`, the waitlist promotion is queued and never runs, so `tests/test_seminar_e2e.py::test_capacity_waitlist_and_promotion_guard` fails with `'waiting' == 'promoted'`. Without the broker variables it passes. BLK-05's conftest forces Celery inline, and at `10207cd` that test passes under CI's environment.
- **Who benefits:** everyone building later items (CI becomes a gate that can go green); the Firebase project (no seed run against a project nobody confirmed).
- **What to build:** one credential resolver in `seed_safety.py`, used by both the guard and every Firestore script, covering `FIREBASE_CREDENTIALS`, `FIREBASE_KEY_PATH`, `GOOGLE_APPLICATION_CREDENTIALS` and `serviceAccountKey.json` in a fixed order. The guard confirms the project of exactly the credentials the script will use, and refuses when it can't read a project ID (unless the local emulator is used). The test supplies its own fake key through that resolver and doesn't depend on files outside git.
- **What was built:**
  - `seed_safety.firestore_credentials` (`seed_safety.py:74`) is the one place that finds a Firestore key. The first source that is set wins, even if it's broken, so a bad setting never falls through to another key:
    1. `FIREBASE_CREDENTIALS` (the JSON itself);
    2. `FIREBASE_KEY_PATH`;
    3. `serviceAccountKey.json` in the current directory;
    4. `serviceAccountKey.json` in the project root (`PROJECT_KEY`, `:71`);
    5. `GOOGLE_APPLICATION_CREDENTIALS`.
    - Each script finds the same key as before, except where it disagreed with the guard: `GOOGLE_APPLICATION_CREDENTIALS` is now consulted last instead of first.
  - `guard(firestore=True)` (`seed_safety.py:139-149`) reads the project ID from that key. It refuses when it can't read one (no key, unparseable, no `project_id`, missing file), and it refuses any name but that project. The emulator exception is unchanged.
  - `firestore_key()` (`seed_safety.py:112`) hands every script the same key. All 10 Firestore scripts now connect with `credentials.Certificate(firestore_key())` instead of their own lookups; their now-unused `os`/`sys`/`json` imports were removed (ruff).
  - `tests/test_seed_safety.py::test_firestore_scripts_also_need_the_project_named`: same assertions. It supplies its fake key through `FIREBASE_CREDENTIALS`, the first source, as a structurally valid key generated in the test (`fake_key`, `:153`), instead of `GOOGLE_APPLICATION_CREDENTIALS`, which the scripts never read.
- **Files touched:** `seed_safety.py`, `delete_data.py`, `saptha_full_seed.py`, `seed_demo.py`, `seed_live_demo.py`, `seed_presentation.py`, `setup_db.py`, `setup_tomorrow_demo.py`, `scripts/seed_events.py`, `scripts/wipe_firestore.py`, `scratch/seed_single_event.py`, `tests/test_seed_safety.py`.
- **Effort:** S · **Depends on:** BLK-10 (DONE) · **Risk:** low; a script that finds its key today keeps finding it, unless it was relying on `GOOGLE_APPLICATION_CREDENTIALS` over a local key file (none did).
- **Acceptance criteria** (in `tests/test_seed_safety.py`; a runner stubs `firebase_admin.initialize_app` to report the project the script connects with):
  1. ✅ In a fresh clone with no `serviceAccountKey.json`, no `.env`, CI's environment, a Redis server and CI's exact command: **689 passed** [R]. The old test failed there.
  2. ✅ With only `FIREBASE_CREDENTIALS` set (project A), each of the 10 Firestore scripts refuses `--confirm-firestore-project=project-b` and connects with project A when given `=project-a` (`::test_each_firestore_script_connects_with_the_project_the_guard_confirmed`, 10 cases; `::test_there_are_firestore_scripts_to_check` pins the count).
  3. ✅ Unparseable credentials, a key without `project_id` and a missing key file are refused whatever project is named, or none (`::test_unreadable_credentials_are_refused_whatever_project_is_named`); no key anywhere is refused too (`::test_no_key_anywhere_is_refused`).
  4. ✅ With two sources naming different projects, the guard confirms the one the script connects with and refuses the other: `FIREBASE_CREDENTIALS` over `FIREBASE_KEY_PATH`, and `FIREBASE_KEY_PATH` over `GOOGLE_APPLICATION_CREDENTIALS`. A key in the current directory beats `GOOGLE_APPLICATION_CREDENTIALS` (`::test_the_guard_checks_the_key_the_script_will_use`).
  - With the old guard and scripts, 13 of these tests fail in the developer's checkout. The other 3 (criterion 3) pass there only because the old guard fell back to the developer's real key; in a fresh clone they fail too. Full pytest: **689 passed** on SQLite and PostgreSQL 16; ruff clean; bandit shows only the 5 BLK-11 findings.

#### BLK-16 — Email, QR and referral links follow a forged Host header
- **Status:** DONE
- **Last verified:** 2026-10-02, commit "BLK-16: …" on `production-ready` (parent `0f22a5c`)
- **Problem (as found at `7aac9ca`):** From the code review of PR #48 (owner, 2026-10-02); confirmed in the code [C].
  - **Links built from the request's host:**
    - the password-reset link (`routes_auth.py:365`);
    - the set-password link sent on registration (`services_accounts.py:100`);
    - the venue check-in QR (`routes_checkin.py:226`);
    - the referral link (`routes_referrals.py:49`).
  - **Helpers that prefer the request's host:**
    - `utils_email._base_url` returns `request.url_root` first (`utils_email.py:50-67`). Every email template's links and logo use it (`utils_email.py:107,449,511,602,689,754`), as do the certificate logo (`utils_certificate.py:81`) and the certificate verification page (`routes_verification.py:172`).
    - `routes_ticket._base_url` uses `BASE_URL` but falls back to the request's host for the ticket QR (`routes_ticket.py:91-104`, used at `:158,216`).
  - **ProxyFix trusts `X-Forwarded-Host`** (`app.py:149`, `x_host=1`, plus `x_prefix=1`), so any client can set the host Flask sees.
  - **Attack:** `POST /forgot_password` with a victim's email and `X-Forwarded-Host: evil.example`. The real reset email reaches the victim with a link to `https://evil.example/reset_token/<token>`, and one click hands the attacker a valid one-hour token. Registering a new email the same way leaks a three-day set-password token.
  - **Hard-coded fallbacks:** `utils_email._base_url` falls back to the old Cloud Run URL (`utils_email.py:51`); `utils_whatsapp.py:116,154,210` fall back to an old Railway URL.
  - **`BASE_URL` isn't required in production:** it defaults to `http://127.0.0.1:5000` (`config.py:173`), and `validate_production_config` doesn't check it.
- **Who benefits:** every account (no takeover through a poisoned email link).
- **What to build:**
  - Build every link that goes into an email, a WhatsApp message, a QR code or a referral from `BASE_URL` only, through one helper, with no request host and no hard-coded URL.
  - `validate_production_config` requires `BASE_URL` to be an `https://` URL that isn't localhost.
  - `ProxyFix(x_for=1, x_proto=1)` only.
  - Add `BASE_URL` to "Before the next deploy".
  - Not in scope: Stripe's `success_url`/`cancel_url` (`routes_payment_stripe.py:71-72`) are redirects for the caller's own checkout, never sent to anyone else, and UPG-14 removes Stripe.
- **What was built:**
  - `utils_email._base_url` (`utils_email.py:50`) is the one helper. It returns the app's `BASE_URL`, or the environment variable outside an app context, or `http://127.0.0.1:5000` in development. It never uses the request's host and holds no hard-coded URL.
  - Every link that leaves the app now uses it:
    - the reset link (`routes_auth.py:367`) and the set-password link (`services_accounts.py:100`);
    - the ticket QR (`routes_ticket._base_url`, `routes_ticket.py:90`, used at `:144,202`) and the venue check-in QR (`routes_checkin.py:227`);
    - the referral link (`routes_referrals.py:50`);
    - WhatsApp messages (`utils_whatsapp._public_base_url`, `utils_whatsapp.py:36`, used at `:121,158,213`);
    - the waitlist pay link (`routes_waitlist.py:196`), the reminder email (`tasks/email_tasks.py:60`), and the certificate verify links (`routes_spoc.py:569,1920`), which were relative when `BASE_URL` was unset.
  - `validate_production_config` refuses a production start unless `BASE_URL` is an `https://` address that isn't localhost, in the same single error as the other problems (`config.py:267-270`).
  - `ProxyFix(x_for=1, x_proto=1)` (`app.py:151`): `X-Forwarded-Host` and `X-Forwarded-Prefix` are no longer trusted.
  - "Before the next deploy" gains `BASE_URL`.
  - `tests/test_integration_flow.py::test_production_config_requires_real_secrets` gives its valid production config a `BASE_URL`, the setting this item makes required; its assertions are unchanged.
- **Files touched:** `utils_email.py`, `routes_ticket.py`, `routes_checkin.py`, `routes_referrals.py`, `routes_auth.py`, `services_accounts.py`, `utils_whatsapp.py`, `routes_waitlist.py`, `tasks/email_tasks.py`, `routes_spoc.py`, `config.py`, `app.py`, `tests/test_public_links.py` (new), `tests/test_integration_flow.py`.
- **Effort:** S · **Depends on:** none · **Risk:** a deploy without a proper `BASE_URL` now refuses to start (intended); in development, links point at the `BASE_URL` default (`http://127.0.0.1:5000`).
- **Acceptance criteria** (all in `tests/test_public_links.py`, on the real database layer; each request goes to the forged host `evil.example` with `X-Forwarded-Host: attacker.example`; 11 of the 12 tests fail on the old code, and the 12th checks that a correct production config still starts):
  1. ✅ Test: a password-reset request and a registration with a new email, each sent with a forged `Host` and `X-Forwarded-Host`, email links that start with `BASE_URL` and contain neither forged host (`::test_password_reset_email_links_to_base_url_whatever_the_host`, `::test_set_password_email_on_registration_links_to_base_url`).
  2. ✅ Test: with the same forged headers, the ticket QR URL, the venue check-in QR, the referral link and `utils_email._base_url()` all use `BASE_URL` (`::test_qr_codes_and_referral_links_use_base_url`; the QR data is captured where the QR is drawn).
  3. ✅ Test: production boot without `BASE_URL`, or with an `http://` or localhost one, is refused in the same single error as the other problems; with an `https://` `BASE_URL` it starts (`::test_production_refuses_a_missing_or_unsafe_base_url`, 5 cases; `::test_production_starts_with_an_https_base_url`).
  4. ✅ Test: the app's ProxyFix trusts one hop of `X-Forwarded-For` and `X-Forwarded-Proto` only; a forged `X-Forwarded-Host` doesn't change the host the app sees, and the client IP and scheme still come through (`::test_proxy_fix_trusts_one_hop_of_for_and_proto_only`).
  5. ✅ Test: no app module builds a link from `request.host_url` or `request.url_root`. The allow-list covers `app.py`'s same-site referrer check and Stripe's own redirect URLs (until UPG-14). `utils_email.py`, `utils_whatsapp.py` and `routes_ticket.py` hold no hard-coded deploy URL (`::test_no_app_module_builds_links_from_the_request_host`, an AST scan of every tracked app module; `::test_outbound_message_modules_hold_no_hard_coded_deploy_url`). The tenant middleware's domain lookup is also allow-listed: multi-tenancy is off, and it builds no link.
  - Full pytest: **701 passed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-17 — Any SPOC can end, publish, staff and edit other SPOCs' events
- **Status:** DONE
- **Last verified:** 2026-10-02, commit "BLK-17: …" on `production-ready` (parent `a417e88`)
- **Problem (as found at `a417e88`):** Found while starting UPG-33 [C at `a417e88`, AST scan of `routes_spoc.py` plus reading each route]. These ClubSPOC routes take an `event_id` but never check that the user may act on that event (no `spoc_id` comparison, no `can(...)`):
  - **Writes:**
    - `end_event` (`routes_spoc.py:530`): marks any event `completed` and starts certificate generation;
    - `announce` (`:687`) and `agenda` (`:762`, GET and POST);
    - `publish_results` (`:789`): marks it `completed` with results published;
    - `toggle_openhall` (`:1081`) and `upload_cert_templates` (`:1256`);
    - `upload_judges_csv` (`:1322`) and `add_judge` (`:1382`): appoint judges, who can then score that event;
    - `setup_rooms` (`:1439`);
    - `reassign_room` (`:1529`), which also doesn't check that the registration belongs to the event.
  - **Reads:** `judging/audit` (`:1937`, every judge's scores), `schedule/optimize` (`:2049`), `ticket/nfc-verify` (`:2147`) and `judging/matchmaker` (`:2180`).
  - `announcements/public` (`:737`) is public by design.
  - BLK-04 fixed the coordinator routes, the form builder and the API; these SPOC routes weren't in its list. The SPOC isolation decision (BLK-04, owner 2026-09-29) says a SPOC manages only events they own or hold a unit grant for.
- **Who benefits:** every organiser (nobody else can end, publish or staff their event) and every participant (scores and attendee data stay with the event's staff).
- **What to build:** one helper that loads the event and requires a permission on it with `services_permission.can`, called before each route's `try` so the 403 isn't swallowed. The permissions are:
  - `edit_event`: end, announce, agenda, open hall, judges, optimizer, matchmaker;
  - `publish_results`: publish results;
  - `issue_certificates`: certificate templates;
  - `manage_registrations`: rooms and reassignment;
  - `view_analytics`: the judging audit;
  - `check_in`: NFC verify.
  - Room reassignment refuses a registration from another event.
- **What was built:**
  - `_event_or_abort(event_id, permission)` (`routes_spoc.py:29`) loads the event (404 if missing) and requires `can(session, permission, event)` (403 otherwise).
  - It's called first in each of the 14 routes (`routes_spoc.py:549,707,783,811,1104,1280,1347,1408,1466,1557,1969,2082,2181,2215`), with the permissions listed above.
  - `reassign_room` also answers 404 unless the registration belongs to the event (`routes_spoc.py:1557-1560`).
- **Files touched:** `routes_spoc.py`, `tests/test_spoc_event_authz.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** a page that some other role relied on now answers 403; the routes are ClubSPOC-only, so only other SPOCs lose access.
- **Acceptance criteria** (`tests/test_spoc_event_authz.py`, real database layer; criteria 1–2 and 4 fail on the old code, where another SPOC's `end_event` ended the event):
  1. ✅ Test (real DB): a SPOC who doesn't own the event gets 403 on each of the 10 write routes and nothing about the event, its staff, its registrations or its rooms changes, and no judge account is created (`::test_another_spoc_gets_403_on_every_route_and_nothing_changes`).
  2. ✅ Test: the same SPOC gets 403 on the 4 read pages, and on the agenda page (same test).
  3. ✅ Test: the owner can still add a judge, publish results, toggle open hall, open the agenda and the judging audit, and reassign their own registration's room (`::test_the_owner_still_manages_their_event`).
  4. ✅ Test: the owner can't reassign a registration that belongs to another event: 404, and its room is unchanged (`::test_the_owner_cant_reassign_another_events_registration`).
  - Full pytest: **704 passed** on SQLite and PostgreSQL 16; ruff clean.

#### BLK-18 — Any Volunteer can mark attendance and open tickets at any event
- **Status:** DONE
- **Last verified:** 2026-10-07, commit "BLK-18: …" on `production-ready` (parent `2db0db1`)
- **Problem (as found at `2db0db1`):** Found while starting UPG-02 [R]. `services_permission.can` gave the `Volunteer` session role `check_in` on every event, with no assignment check (`services_permission.py:311-312`: `return permission == 'check_in'`). Every other staff role checks the event's `staff` list. Organisers can appoint volunteers (`STAFF_ROLES`, BLK-04), so any volunteer for one event could, at every other event:
  - mark attendance (`/coordinator/mark_attendance_granular`, `routes_coordinator.py:908`); confirmed on the real database: an unassigned volunteer's request answered 200 and set the registration `Present`;
  - read the scanner view of any registration: names, USNs, room (`/coordinator/get_ticket`, `:887`);
  - open any registrant's ticket page and QR, so they got its signed check-in token (`routes_ticket.py:122,177`, through `routes_checkin._can_manage_event`).
  The kiosk, SPOC scanner and `/ticket/verify` POST weren't affected: they also require a coordinator-level role.
- **Who benefits:** every participant (their attendance and ticket stay with the event's own staff) and organisers.
- **What to build:** a Volunteer has `check_in` only on events where they're in `staff` or `coordinators`, like an EventCoordinator, and no other permission.
- **What was built:** the Volunteer branch of `can` (`services_permission.py:312-319`) requires the event's `staff` or `coordinators` to list them, the same rule EventCoordinators follow. Without an event it still answers the role-level question, as for the other staff roles.
- **Files touched:** `services_permission.py`, `tests/test_volunteer_scope.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** a volunteer who worked an event without being added to its staff list is now refused; the organiser adds them through "assign staff".
- **Acceptance criteria** (`tests/test_volunteer_scope.py`, real database layer; criteria 1 and 3 fail on the old code):
  1. ✅ Test: a volunteer not on the event's staff gets 403 on mark-attendance, the scanner lookup and the QR image, and is turned away from the ticket page; attendance is unchanged (`::test_an_unassigned_volunteer_cant_check_in_or_see_tickets`).
  2. ✅ Test: a volunteer on the event's staff can still look up and mark attendance (`::test_a_volunteer_on_the_events_staff_still_checks_in`).
  3. ✅ Test: `can` gives a volunteer `check_in` only at their event (by event or event ID) and no other permission even there (`::test_a_volunteer_has_check_in_only_and_only_where_assigned`).
  - Full pytest: **762 passed** on SQLite and PostgreSQL 16; ruff clean.
- **Rule 8 (early pass, `services_permission.py` changed):** every open item (37) was checked against this change. Three mention the permission layer: UPG-02 (built next; it wants check-in for assigned staff only, which this enforces), UPG-03 (`export_data`, which volunteers never had) and UPG-12 (cites `services_permission.py:53-80`, unchanged). No other open item's claims change. The full re-verification still runs at the end of Phase 2.

#### BLK-19 — Registrant names run as HTML on staff pages (stored XSS)
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "BLK-19: …" on `production-ready` (parent `0a68ce6`)
- **Problem:** Found while building UPG-02 [C]. Registration stores the lead's name, the team name and member names exactly as typed (`routes_forms.py:404,407,443-455`); nothing escapes or rejects markup on input. Pages Jinja renders escape them, but several staff pages build HTML in JavaScript with `innerHTML` and template strings:
  - the SPOC scanner's manual list, which runs as soon as the SPOC opens the scanner (`templates/spoc/scan.html:338`: name, team), and its scan log (`:543`);
  - the kiosk's search results (`templates/public/kiosk.html:747`: name, team, event title).
  - There are 180 `innerHTML` uses in 43 tracked templates and scripts; the rest haven't been checked.
  The Content-Security-Policy allows inline scripts (`app.py:221`, `'unsafe-inline'`; UPG-25), so a registrant named `<img src=x onerror=…>` runs script in the SPOC's or coordinator's session. That script can read the page's CSRF token and act as them. UPG-02's new code adds no `innerHTML` with data and didn't change these three places.
- **Who benefits:** every organiser, coordinator and admin who opens a page that lists registrants.
- **What to build:** every place a page's JavaScript inserts stored or server-supplied text uses `textContent`, DOM nodes, or one shared escaping helper; markup with values goes through that helper. Keep names as typed (no input mangling).
- **What was built:**
  - **The audit was wider than the three places first seen.** The first full scan found 241 values put into HTML without escaping, in 30 tracked templates and scripts. Other people's text could run as script in:
    - public pages: team and lead names on the live leaderboard, event titles, venues and categories on the calendar tooltip, the landing page's event modal (it reads the card's text and re-inserts it as HTML) and its chatbot (the AI's reply);
    - staff pages: names on the SPOC scanner and dashboard feeds, the judge's scoring form and leaderboard (criteria and team names), AI matching, the admin's AI event proposal, proctoring alerts;
    - the student dashboard: notification titles and links, waitlist event titles.
    Two pages that already escaped used helpers that missed single quotes, which matters inside attributes.
  - **One helper file, `static/js/escape.js`.** It has `escapeHtml` for text and quoted attributes, `escapeJsAttr` for values inside `on…="…"` handlers (where entities are decoded before the code runs) and `safeUrl` for `href`/`src` (refuses `javascript:`, `data:` and other schemes, including ones hidden with spaces or control characters). The shared layout loads it in `<head>` (`templates/base_classic.html:23`); each standalone page that uses it loads it before its scripts.
  - **Every value now goes through the helpers.** The page-local helpers (`escHtml`, `fb_esc`, `esc`, a second `escapeHtml`) are replaced by the shared one. Shared scripts (`global.js`, `analytics.js`, `pwa.js`, `command-palette.js`, `proctor.js`) build DOM nodes with `textContent` instead, since they load on pages that may not have the helper. Two ID-in-handler spots now find their element without an ID.
  - **The scan, `tests/html_sinks.py`.** It lexes the inline scripts of every tracked template and every `static/js` file. It checks each value in an HTML-building string or a direct `innerHTML`/`outerHTML`/`insertAdjacentHTML`/`document.write`, and needs the right helper for the context. Accepted without one: literals, numbers, ternaries of literals, `.map(…).join('')` whose returns are checked, names ending in `html`, and one reviewed exception (translations from `i18n.py`). It skips `templates/debug_modal.html` and `templates/public/home.html`, which nothing renders (UPG-15 deletes them).
  - Names stay stored as typed: no input mangling.
- **Files touched:** `static/js/escape.js` (new), `static/js/{global,analytics,pwa,command-palette,proctor}.js`, `templates/base_classic.html` and 25 other templates, `tests/html_sinks.py` and `tests/test_no_html_injection.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** the scan reads JavaScript with a small lexer, so code written in unusual ways could slip past it; UPG-25 (no `'unsafe-inline'`) is the second layer. A chatbot reply with formatting now shows as plain text.
- **Acceptance criteria** (`tests/test_no_html_injection.py`; criterion 1 fails on the old code with 241 findings, and the loader check fails too):
  1. ✅ Test: a scan of every tracked template and `static/js` file finds each `innerHTML`, `outerHTML`, `insertAdjacentHTML` and `document.write` that interpolates a value (`${…}` or `+ value`). Each value goes through the escaping helper, or the line is on a short reviewed list of trusted values (`::test_every_value_put_into_html_is_escaped`; the reviewed list has one entry). Also: every page that calls the helpers loads them first (`::test_every_page_that_escapes_loads_the_helpers`); shared scripts don't depend on them; 30 cases pin what the scan flags and accepts.
  2. ✅ Test (Node, as UPG-02's harness): the escaping helper turns `<img src=x onerror=alert(1)>`, quotes and `&` into text (`::test_the_helpers_turn_markup_into_text`, which also checks `escapeJsAttr` and 11 addresses through `safeUrl`). Skipped without Node.
  3. ✅ Test (real database): a registrant named `<img src=x onerror=alert(1)>` is stored unchanged and appears escaped on the server-rendered staff pages that list registrants (`::test_a_markup_name_is_stored_as_typed_and_shown_as_text`: the coordinator's registrations page and the SPOC scanner page; the kiosk search returns it as JSON data). This already held on the old code: Jinja escapes; the test pins it.
  - Full pytest: **817 passed** on SQLite and PostgreSQL 16; ruff clean; bandit exit 0.

#### UPG-33 — Account emails: walk-in passwords by email, reusable reset links
- **Status:** DONE
- **Last verified:** 2026-10-02, commit "UPG-33: …" on `production-ready` (parent `0b9463a`)
- **Problem (as found):** Found while building BLK-02 [C].
  - Walk-in accounts created by a coordinator get their one-time password in the ticket email (`routes_coordinator.py:765-768`, "Ticket + login details sent"). BLK-02 removed emailed passwords from self-registration only.
  - Staff accounts created through `assign_staff` get a generated password by email and WhatsApp (`send_credentials_email`, `send_staff_credentials_whatsapp`, `routes_coordinator.py:302-303` at BLK-04a).
  - Password-reset links (`/reset_token/<token>`, `routes_auth.py:396`) can be used any number of times within their hour, because the token isn't bound to the current password.
  - **Re-checked before building (2026-10-02, `0b9463a`; rule 3):** three more paths create someone else's account and email its password, all covered by criterion 1's "new staff member":
    - `routes_spoc.assign_coordinator` emails a generated password to a new coordinator;
    - `add_judge` and `upload_judges_csv` do the same for new judges;
    - `routes_admin.appoint_spoc` emails the password the admin typed into the form (`templates/admin/dashboard.html:668`).
    - (`routes_super.py` also takes a typed password, but its blueprint isn't registered; UPG-15.)
- **Who benefits:** walk-in participants, new staff and SPOCs, and anyone who resets a password.
- **What to build:** every account created for someone else (walk-in, coordinator staff, SPOC-appointed coordinator or judge, admin-appointed SPOC) is a BLK-02 unverified account plus a one-time set-password link, and the email says why the account exists. No password appears in any email or WhatsApp message, and the admin form loses its password field. Reset tokens are bound to the current password hash like the set-password tokens (`services_accounts.py:71-90`).
- **What was built:**
  - `services_accounts.create_unverified_account` (`services_accounts.py:58`) takes a role and extra fields, so every path uses BLK-02's unverified account. `send_set_password_link` (`:115`) passes a reason, and the set-password email (`utils_email.send_set_password_email`, `utils_email.py:656`) says why the account exists ("when you were appointed as Judge for …", "when you registered at the desk for …").
  - **Walk-in** (`routes_coordinator.py:723,758`): the ticket email no longer carries login details; a new walk-in gets the link.
  - **Coordinator `assign_staff`** (`:294-296`): the link by email, and a WhatsApp appointment notice without credentials (`utils_whatsapp.send_staff_appointment_whatsapp`, `utils_whatsapp.py:152`, replaces `send_staff_credentials_whatsapp`).
  - **SPOC `assign_coordinator`** (`routes_spoc.py:1225-1226`), **`upload_judges_csv`** (`:1370-1371`) and **`add_judge`** (`:1401-1402`): the link instead of a generated password.
  - **Admin `appoint_spoc`** (`routes_admin.py:390-391`): the form has no password field (`templates/admin/dashboard.html:668`), and a password sent anyway is ignored.
  - **Reset links:** `make_reset_token`/`load_reset_token` (`services_accounts.py:86-91`, shared checker `_load_bound_token`, `:96`) bind the token to the current password hash, one hour as before. `forgot_password` and `reset_token` use them (`routes_auth.py:360-361,393-394`). A used link, or one issued before the password changed, is refused with "already been used"; tokens in the old format are invalid.
  - `utils_email.send_credentials_email` is no longer called by app code; it stays only for `scratch/send_all_demo_mails.py` (UPG-15).
- **Files touched:** `services_accounts.py`, `utils_email.py`, `utils_whatsapp.py`, `routes_coordinator.py`, `routes_spoc.py`, `routes_admin.py`, `routes_auth.py`, `templates/admin/dashboard.html`, `tests/test_account_emails.py` (new).
- **Effort:** S · **Depends on:** BLK-02 · **Risk:** low.
- **Acceptance criteria** (`tests/test_account_emails.py`, real database layer; every plaintext handed to `generate_password_hash` during a request is recorded and must not appear in any email or WhatsApp message; all 8 tests fail on the old code):
  1. ✅ A walk-in (`::test_walk_in_gets_a_set_password_link_and_no_password`), a new staff member through each of the four staff paths (`::test_new_staff_get_a_set_password_link_and_no_password`, 4 cases) and an admin-appointed SPOC (`::test_appointed_spoc_gets_a_set_password_link_and_the_form_asks_no_password`) get exactly one set-password link and no password, by email or WhatsApp. The account can't be logged into until the link sets a password, which logs them in with the right role; the link then stops working. App code no longer calls the credential senders (`::test_no_app_module_sends_credentials`).
  2. ✅ A reset link works once; the same link again, and another link issued before the change, are refused and the password stays as first set (`::test_a_reset_link_works_once`).
  - Full pytest: **712 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-34 — The legacy public registration route skips the "registration closed" check
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-34: …" on `production-ready` (parent `2fb6e01`)
- **Problem:** Found while building BLK-02 [C]. `POST /participant/public_register/<event_id>` (`routes_participant.py:355`), still used by the form on `templates/public/event_details.html:737`, never checks the event status or deadline, so it accepts registrations for draft, closed, completed or cancelled events. `/forms/submit` does check (`routes_forms.py:413-416`).
- **Who benefits:** organisers (no registrations after closing).
- **What to build:** point the event page's form at `/forms/register/<event_id>` and make the legacy route apply the same status check (or redirect to the form), keeping the URL.
- **Re-checked before building (2026-10-08, `2fb6e01`; rule 3):** still true (the legacy route is at `routes_participant.py:355`, the modal form at `templates/public/event_details.html:738`). Also found:
  - `/forms/submit` checked the status but not the deadline or `pending_approval`, which the registration page refuses, so a past-deadline event still took registrations by POST;
  - the event page's modal posted team members as `member_name[]`, a format `/forms/submit` doesn't read.
- **What was built:**
  - **One check, `routes_forms.registration_closed` (`routes_forms.py:90`).** Registration is closed for a draft, pending, published-but-not-open, closed, completed, certified, cancelled or archived event, and after its deadline. The registration page (`:375`), `/forms/submit` (`:467`) and the legacy route (`routes_participant.py:367`) all use it. The legacy route refuses before anything is created and sends the visitor back to the event page; its URL stays.
  - **The event page's Register buttons link to the event's own form** (`/forms/register/<id>`, which UPG-01 made work for every form). Its separate modal form and member script, which bypassed the form, are removed.
- **Files touched:** `routes_forms.py`, `routes_participant.py`, `templates/public/event_details.html`, `tests/test_registration_closed.py` (new).
- **Effort:** S · **Depends on:** BLK-02 · **Risk:** low; no existing test registered after a deadline.
- **Acceptance criteria** (`tests/test_registration_closed.py`, real database layer; 6 of 7 cases fail on the old code, the seventh guards an open event):
  1. ✅ Test: the legacy route refuses a draft, closed or cancelled event and creates nothing (`::test_the_legacy_route_refuses_a_closed_event_and_creates_nothing`, also pending approval and past the deadline: no registration, no account; `/forms/submit` refuses the same; `::test_the_legacy_route_still_registers_for_an_open_event`).
  2. ✅ Test: the event page's registration form posts to the checked route (`::test_the_event_page_sends_registrants_to_the_checked_form`: no form posts to the legacy route; Register links to `/forms/register/<id>`, whose form posts to `/forms/submit/<id>`).
  - Full pytest: **849 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-35 — Login and password-reset messages reveal whether an account exists
- **Status:** DONE
- **Last verified:** 2026-10-02, commit "UPG-35: …" on `production-ready` (parent `032e7c3`)
- **Problem (as found at `986d108`):** Found while building BLK-13 [C]. BLK-13's throttle answers the same for known and unknown accounts, but other messages don't:
  - The web login says "Account not found. Please register or contact admin." for an unknown email and "Incorrect password or wrong role selected." for a known one (`routes_auth.py:127` vs `:149`).
  - The API login answers `403 account_locked` for an existing account that still has a legacy unhashed password, before checking the password (`routes_api_v1.py:83`); unknown accounts get `401 invalid_credentials` (`:76`).
  - The password-reset request already answers alike for known, unknown and SuperAdmin emails (`routes_auth.py:344-379`), in wording the owner wants changed.
  - Sign-up says so when an email is already registered (web `routes_auth.py:295`, API `routes_api_v1.py:142`), and so does registration (`routes_forms.py:419`, BLK-02).
- **Decision (owner, 2026-10-02):** make the **login and password-reset** messages uniform: "Email or password is incorrect" and "If an account exists for this email, we've sent a reset link". **Keep sign-up and registration as they are:** an existing email is told to log in first.
- **Who benefits:** students and staff (login and reset no longer confirm who has an account).
- **What to build:**
  - Web login: an unknown email, a wrong password and an account with a legacy unhashed password all flash "Email or password is incorrect", with the same redirect, and each counts as a BLK-13 failure.
  - A correct password with the wrong role selected may keep a role hint: only someone who already has the password can see it. Change this if the owner wants the uniform message there too.
  - API login: the same three cases return the same `401 invalid_credentials` with the message "Email or password is incorrect". The legacy-hash account no longer gets its own `403`. Keep the error code, because the mobile apps may read it.
  - Password reset: every request (known, unknown or SuperAdmin email) flashes "If an account exists for this email, we've sent a reset link".
  - Sign-up and registration: unchanged.
- **What was built:**
  - `routes_auth.LOGIN_FAILED_MESSAGE` and `RESET_REQUESTED_MESSAGE` (`routes_auth.py:18-19`) hold the two answers.
  - **Web login:** an unknown email (`:127`), a wrong password and an old unhashed password (`:152`) flash "Email or password is incorrect." and redirect to `/login`. A correct password with the wrong role gets "Wrong role selected for this account…", which only someone who has the password can see.
  - **API login:** the same three cases return `401 invalid_credentials` with the same message (`routes_api_v1.py:77` and the combined hash check below it); the old-password account no longer gets its own `403 account_locked`. Each counts as a BLK-13 failure.
  - **Password reset:** every request flashes "If an account exists for this email, we've sent a reset link." (`routes_auth.py:348`); only an existing non-SuperAdmin account is emailed.
  - **Sign-up and registration:** unchanged.
  - `tests/test_login_throttle.py`'s API test expected the old 401 message word for word; it now expects the new one, still an exact match.
- **Files touched:** `routes_auth.py`, `routes_api_v1.py`, `tests/test_uniform_auth_messages.py` (new), `tests/test_login_throttle.py`.
- **Effort:** S · **Depends on:** BLK-13 · **Risk:** a user who mistypes their email no longer sees "Account not found"; the message says email *or* password.
- **Acceptance criteria** (`tests/test_uniform_auth_messages.py`, real database layer; criteria 1–3 fail on the old code, and criterion 4 pins behaviour that stays the same):
  1. ✅ Test: a web login with an unknown email, a wrong password for an existing account, and an existing account with a legacy unhashed password all get the same status, redirect and "Email or password is incorrect"; the wrong-role hint appears only with the right password (`::test_web_login_answers_alike_for_unknown_emails_wrong_and_old_passwords`).
  2. ✅ Test: the API gives the same status and JSON body for those three cases (`::test_api_login_answers_alike_for_the_same_three_cases`).
  3. ✅ Test: a password-reset request for an unknown, an existing and a SuperAdmin email shows the same page and "If an account exists for this email, we've sent a reset link"; only the existing non-SuperAdmin email is sent a link (`::test_reset_requests_answer_alike_and_only_the_real_account_gets_a_link`).
  4. ✅ Test: sign-up (web and API) and registration with an existing email still tell the user to log in first (unchanged behaviour, now pinned: `::test_sign_up_and_registration_still_tell_an_existing_email_to_log_in`).
  - Full pytest: **716 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-36 — Coupons can be used more than `max_uses` times
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-36: …" on `production-ready` (parent `caaa317`)
- **Problem:** From the code review of PR #48 (owner, 2026-10-02) [C]. `find_valid_coupon` refuses a coupon only when `current_uses >= max_uses` at the moment the price is computed (`services_payments.py:58`, called when the order is created). `current_uses` is incremented only after a verified payment (`_use_coupon`, `routes_payment.py:177-184`). So payers who create orders before any of them pays all get the discount: with `max_uses` 1, two simultaneous checkouts both pay the discounted price, and `current_uses` ends at 2.
- **Who benefits:** organisers and the finance office (discount budgets hold).
- **What to build:** reserve a use atomically when the order is created (a conditional update that increments `current_uses` only while it's below `max_uses`), and release the reservation when the order expires or isn't paid. Or refuse at claim time when the coupon is exhausted and fall back to the full price. Choose whichever is smaller and race-free on PostgreSQL.
- **Re-checked before building (2026-10-08, `caaa317`; rule 3):** UPG-30 changed the payment files; the race is unchanged. Coupons are schemaless documents (`native_document_store` JSON, or Redis), so a conditional update on `current_uses` isn't possible there; the reservation needed a small table of its own.
- **What was built (reservation at order creation):**
  - **New table `coupon_uses`** (`CouponUse`, `models_pg.py:630`): one row per event and coupon, `used` = uses paid or held. Start-up creates it (`db_pg.init_db`).
  - **`take_coupon_use`** (`services_payments.py:116`) takes a use with one conditional `UPDATE … SET used = used + 1 WHERE used < max_uses`, race-free on SQLite and PostgreSQL. The row starts at the coupon's recorded `current_uses`. `create_order` takes it before asking Razorpay (`routes_payment.py:112`): no use left means 400 "Coupon usage limit reached" (the payer can pay full price), and a Razorpay error gives it back.
  - **Holds end.** An unpaid order holds its use for `COUPON_HOLD_MINUTES` (default 30, `coupon_hold`, `:108`); after that, the next checkout marks it `expired` and gives the use back, once, by conditional update (`release_expired_holds`, `:160`). A payer who starts checkout again gives back their earlier unpaid order's use first, so retries don't hold two (`release_payer_holds`, `:143`).
  - **A late payment is never lost.** An expired order can still be paid (browser or webhook) and takes a use again; if none is free (`_late_coupon_over_limit`, `:331`), the payment is kept as recorded with no registration, reason `COUPON_GONE`, for the admin to complete or refund (UPG-30).
  - `COUPON_HOLD_MINUTES` is documented in `.env.example`. `routes_coupons.py` needed no change: its validation stays a pre-check, and the hold is what limits uses.
- **Files touched:** `services_payments.py`, `routes_payment.py`, `models_pg.py`, `.env.example`, `tests/test_coupon_limits.py` (new).
- **Effort:** S · **Depends on:** BLK-03 · **Risk:** a hold blocks a use for up to 30 minutes after a payer walks away; expiry ends it.
- **Acceptance criteria** (`tests/test_coupon_limits.py`, real database layer; all 4 cases fail on the old code):
  1. ✅ Test: a coupon with `max_uses` 1 and two payers who both create orders before either pays: only one order gets the discount, and `current_uses` never exceeds 1 (`::test_two_checkouts_before_anyone_pays_get_one_discount`; `::test_a_payer_starting_checkout_again_holds_one_use`).
  2. ✅ Test: an order created with a coupon and never paid releases the use after it expires, and the next payer can use the coupon (`::test_an_unpaid_order_gives_its_use_back_when_the_hold_expires`; paying the expired order afterwards is kept as recorded, not lost).
  3. ✅ Test (PostgreSQL): 10 concurrent order creations for a coupon with `max_uses` 3 discount exactly 3 orders (`::test_ten_concurrent_checkouts_get_exactly_the_coupons_three_uses`; skipped on SQLite).
  - Full pytest: **871 passed** on PostgreSQL 16, **870 passed and 1 skipped** on SQLite; ruff clean.

#### UPG-37 — Hourly per-account login cap on top of the per-minute limit
- **Status:** DONE
- **Last verified:** 2026-10-02, commit "UPG-37: …" on `production-ready` (parent `06f4b02`)
- **Problem:** From the code review of PR #48 (owner, 2026-10-02). BLK-13 allows 5 failed logins per account per minute (`services_login_throttle.py`). A slow attacker can keep trying 4 passwords a minute, 240 an hour, without ever being refused.
- **Who benefits:** every account.
- **What to build:** a second window per account: at most about 20 failed logins per hour (`LOGIN_THROTTLE_ACCOUNT_HOURLY_LIMIT`, default 20), on the same counters and with the same "try again in N seconds" answer. The per-IP limit is unchanged, and a successful login clears both account windows. Document the setting in `.env.example`.
- **What was built:**
  - Each counter now has its own window: `_counters` (`services_login_throttle.py:59`) returns `(key, limit, window)`. For logins, the account key is checked twice: per minute (5) and per hour (`LOGIN_THROTTLE_ACCOUNT_HOURLY_LIMIT`, default 20, `config.py:136`).
  - Attempts are kept as long as the longest window needs (`_keep_for`, `:50`); the database purge and Redis expiry used the one-minute window before. Still one stored row per failure.
  - A success clears the account key, so both windows reset. The IP and password-reset counters have no hourly window.
  - The setting is documented in `.env.example`.
  - `tests/test_login_throttle.py::test_redis_counters_are_shared_by_separate_clients` handed out new Redis connections from a fixed list of 20, which runs out now that each check reads three counters (it then fell back to the database). It now makes a new connection on every call; same intent, same assertions.
- **Files touched:** `services_login_throttle.py`, `config.py`, `.env.example`, `tests/test_login_throttle.py`.
- **Effort:** S · **Depends on:** BLK-13 · **Risk:** a forgetful user locked out for up to an hour; the password-reset link still works.
- **Acceptance criteria** (in `tests/test_login_throttle.py`, on the database and on Redis; criteria 1–2 fail on the old code, and criterion 3 guards against over-blocking):
  1. ✅ Test: 20 failed logins on one account spread over 50 minutes (never more than 4 a minute) are all answered normally; the 21st within the hour is refused with 429 and the wait until the oldest failure leaves the hour; after it does, the right password works (`::test_hourly_cap_stops_a_slow_guesser`).
  2. ✅ Test: the same holds for `/api/v1/auth/login`, on the shared counter, with web and API failures mixed (`::test_hourly_cap_applies_to_the_api_on_the_shared_counter`).
  3. ✅ Test: a successful login clears the hourly count; the per-IP limit is unaffected: one IP's 25 failures on different accounts over the hour are never refused (`::test_success_clears_the_hourly_count_and_ips_have_no_hourly_cap`).
  - Full pytest: **722 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-38 — Delete the sample Jekyll workflow
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** From the code review of PR #48 (owner, 2026-10-02). `.github/workflows/jekyll-docker.yml` is GitHub's "Jekyll site CI" sample: it builds a Jekyll site in Docker on every push and pull request to `master`. The repo has no Jekyll site (no `_config.yml` or `Gemfile`), so the check means nothing and costs CI time.
- **Who benefits:** developers (CI shows only real checks).
- **What to build:** delete the file.
- **Files touched:** `.github/workflows/jekyll-docker.yml`, `tests/test_repo_hygiene.py`.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. Test: no tracked workflow file runs Jekyll (`tests/test_repo_hygiene.py`).
  2. The next CI run on GitHub shows no "Jekyll site CI" check.

#### UPG-39 — In development, log set-password and reset links when no mail provider is set
- **Status:** DONE
- **Last verified:** 2026-10-02, commit "UPG-39: …" on `production-ready` (parent `1b04a80`)
- **Problem:** Owner, 2026-10-02. Since BLK-02 and UPG-33 the emailed set-password link is the only way into a new account, and the reset link the only way back in. With no mail provider configured (no `BREVO_API_KEY`, `RESEND_API_KEY` or Gmail login), `utils_email._send` falls back to Gmail SMTP and fails (`utils_email.py:408-420`), so a developer can't follow these flows locally.
- **Who benefits:** developers and testers.
- **What to build:** when no provider is configured and `FLASK_ENV` isn't `production`, the set-password and reset emails also write their link to the log at WARNING, marked as development-only. In production the link is never logged: a missing provider is logged as an error without the link.
- **What was built:**
  - `utils_email.mail_provider()` (`utils_email.py:75`) names the provider `_send` will use, or `''`.
  - `_log_link_without_mail` (`:96`) is called by the reset email (`:686`) and the set-password email (`:717`). With no provider outside production, it logs the link at WARNING, marked "DEVELOPMENT ONLY". In production (app config or environment, `_is_production`, `:86`) it logs an ERROR naming the recipient and the missing provider, never the link.
  - With a provider configured, nothing is logged.
- **Files touched:** `utils_email.py`, `tests/test_dev_mail_links.py` (new).
- **Effort:** S · **Depends on:** UPG-33 · **Risk:** a link in a production log would be a credential; the production test guards it.
- **Acceptance criteria** (`tests/test_dev_mail_links.py`, real database layer; criteria 1–2 fail on the old code):
  1. ✅ Test: in development with no provider, registering a new email and requesting a reset each log the full link (`::test_development_logs_both_links`).
  2. ✅ Test: with production config and no provider, neither link appears in any log record (an error about the missing provider is logged instead) (`::test_production_never_logs_a_link`).
  3. ✅ Test: with a provider configured (HTTP stubbed), the links aren't logged (`::test_with_a_provider_the_links_are_not_logged`).
  - Full pytest: **725 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-40 — The Super Admin can resend a set-password link from a users page
- **Status:** DONE
- **Last verified:** 2026-10-07, commit "UPG-40: …" on `production-ready` (parent `118dbf3`)
- **Problem:** Owner, 2026-10-02. Since UPG-33, staff, SPOCs and walk-ins can get in only through the emailed set-password link, which expires after 3 days. There's no way to send a new one:
  - no routed users page exists (`/admin/users` is a 404);
  - `templates/admin/users.html` is never rendered (UPG-15) and links to delete with a GET;
  - the admin report lists staff without actions (`routes_admin.py:583-598`).
  - "Forgot password" works for the person themselves, but an organiser can't help someone whose link expired.
- **Who benefits:** SuperAdmins and the staff and SPOCs they appoint.
- **What to build:**
  - A SuperAdmin-only users page at `/admin/users` (on the shared layout, linked from the admin navigation) listing each account's name, email, role and whether they've set a password.
  - For accounts still waiting for their first password, a POST "Resend set-password link" button (CSRF) that emails a fresh link and audit-logs it.
  - SuperAdmin accounts and accounts that already have a password are refused. Pagination is UPG-19's job.
- **Re-checked before building (2026-10-07, `118dbf3`; rule 3):** `routes_admin.py`, `templates/admin/users.html` and `templates/base_classic.html` are unchanged since `37c2a5c`; `/admin/users` is still a 404.
- **What was built:**
  - `GET /admin/users` (`routes_admin.py:438`, SuperAdmin only) lists every account's name, email, role and password state, waiting accounts first. "Waiting for first password" means `needs_password_reset` is set (`_waiting_for_password`, `:429`): accounts someone else creates keep it until the set-password link or a reset is used.
  - `POST /admin/users/resend_set_password` (`:458`, CSRF token in the form) emails a fresh link through UPG-33's `send_set_password_link`, explaining that an administrator sent it, and audit-logs `SET_PASSWORD_LINK_RESENT`. It refuses Super Admin roles (`SUPER_ROLE_NAMES`, `:421`), accounts that already have a password and unknown emails, and sends nothing for them.
  - `templates/admin/users.html` is rewritten on the shared layout. The old standalone page, never rendered, is gone, along with its GET delete link and its form posting to a non-existent `/admin/add_user`.
  - Linked from the layout's Management section (`templates/base_classic.html:61`) and from the admin dashboard's own sidebar (`templates/admin/dashboard.html:395`), where Super Admins land; that page doesn't use the layout yet (UPG-23).
- **Files touched:** `routes_admin.py`, `templates/admin/users.html`, `templates/base_classic.html`, `templates/admin/dashboard.html` (nav links), `tests/test_admin_users.py` (new).
- **Effort:** S · **Depends on:** UPG-33 · **Risk:** a long unpaginated list until UPG-19.
- **Acceptance criteria** (`tests/test_admin_users.py`, real database layer; all 6 cases fail on the old code):
  1. ✅ Test: a SuperAdmin opens `/admin/users` and sees an account waiting for its password with a resend button, and an account with a password without one (`::test_the_super_admin_sees_who_is_waiting_and_a_resend_button_only_for_them`).
  2. ✅ Test: the resend sends exactly one set-password email whose link opens the account with its role, and the action is audit-logged (`::test_a_resend_emails_one_working_link_and_is_audit_logged`).
  3. ✅ Test: a SPOC and a student get 403 or a login redirect on the page and the action; resending for an account that has a password, or for a SuperAdmin, is refused and nothing is sent (`::test_only_the_super_admin_can_open_the_page_or_resend`, with an anonymous visitor too, and `::test_accounts_with_a_password_and_super_admins_are_refused`).
  - Full pytest: **731 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-41 — Remove the leftover Gmail app password from `utils_email.py`
- **Status:** DONE
- **Last verified:** 2026-10-07, commit "UPG-41: …" on `production-ready` (parent `dee2135`)
- **Problem:** Found 2026-10-02 while recording UPG-39 [C]. The module docstring of `utils_email.py` (`:26-27`, also in `functions/saptha_app/utils_email.py`) shows a Gmail app password next to the old `MAIL_USER` account. It has been in the public repo since `45c24cc` (2026-04-19). It isn't one of BLK-01's two leaked `MAIL_PASS` values, but it belongs to the same old account. The owner changed that account's password on 2026-09-30, which revokes all its app passwords, so it should already be dead. Gitleaks doesn't flag this format. The same docstring and `_from_address` (`:68-72`) also hard-code that account as the default sender.
- **Who benefits:** everyone (no credential-shaped text left in the code).
- **What to build:** remove the value and the account from the docstring (document the settings by name only), and drop the hard-coded default sender (use `MAIL_FROM`, and fall back to `MAIL_USER` only when that is set). Add a hygiene test that fails on a `MAIL_PASS` assignment with a value in tracked app code. The `functions/` copy goes in Phase 5 (UPG-15).
- **Re-checked before building (2026-10-07, `dee2135`; rule 3):** UPG-39 added code to `utils_email.py` after `37c2a5c`, so `_from_address` had moved to `:68-72`; the docstring lines (`:26-27`) were unchanged. Also found: `config.py`'s `MAIL_PASSWORD` fell back to the literal `'SET_THIS_IN_ENV'` (unused, but it fails criterion 1), and the privacy, terms and payment-failed pages give the old account as the contact address (recorded as UPG-42; not part of this item).
- **What was built:**
  - The module docstring (`utils_email.py:1-16`) documents the settings by name only: no account, no password.
  - `_from_address` (`:51`) returns `MAIL_FROM`, else `SapthaEvent <MAIL_USER>` when `MAIL_USER` is set, else `''`. With no sender, Brevo and Resend refuse before any request and say so in `LAST_EMAIL_ERROR`, which `/diag/email` shows (`NO_SENDER_ERROR`, `:61`, used at `:262` and `:324`). Before, an unverified or wrong sender failed inside the provider. The SMTP path already needs `MAIL_USER`.
  - `config.py:113-114`: `MAIL_USERNAME` and `MAIL_PASSWORD` default to `''`; neither is read anywhere else.
  - Criterion 1's scan (`tests/test_repo_hygiene.py:162-215`) parses every tracked `.py` file outside `functions/` and `scratch/`. It flags `MAIL_PASS`/`MAIL_PASSWORD` given a string by assignment, a dict entry, a keyword or a lookup default, and any string, docstrings included, that spells out such an assignment. Other tracked text files are checked line by line, with `$VAR`, `${{ … }}`, `<…>` and empty values allowed. It needs only the standard library, so CI's hygiene job (which installs only pytest) runs it.
- **Files touched:** `utils_email.py`, `config.py`, `tests/test_repo_hygiene.py`, `tests/test_mail_sender.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** a deploy with Brevo or Resend but no `MAIL_FROM` now fails to send with a clear error instead of sending as the old account. The deploy checklist already sets `MAIL_FROM` (row updated).
- **Acceptance criteria:**
  1. ✅ Test: no tracked file outside `functions/` and `scratch/` assigns a literal value to `MAIL_PASS` (or `MAIL_PASSWORD`) in code or docstrings (`tests/test_repo_hygiene.py::test_no_mail_password_in_tracked_files`, plus 24 cases pinning what the scan flags and allows). Fails on the old code (the docstring and `config.py`'s placeholder).
  2. ✅ Test: with neither `MAIL_FROM` nor `MAIL_USER` set, the sender address contains no hard-coded personal account: the sender is empty, Brevo and Resend send nothing, and `Config` has no built-in account (`tests/test_mail_sender.py::test_with_neither_setting_there_is_no_sender_and_nothing_is_sent`, `::test_config_has_no_built_in_mail_account`; both fail on the old code). `::test_the_sender_is_mail_from_else_the_mail_user_login` pins the order.
  3. ✅ Owner: confirm the old Gmail account lists no app passwords. **Confirmed by the owner on 2026-10-07.**
  - Full pytest: **759 passed** on SQLite and PostgreSQL 16; ruff clean.

#### UPG-42 — The privacy, terms and payment-failed pages give the old Gmail account as the contact address
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found 2026-10-07 while building UPG-41 [C]. Three public pages tell people to write to the old mail account, the one whose password was changed on 2026-09-30 (BLK-01, UPG-41):
  - `templates/public/privacy.html:60` (exercising data rights) and `:77`;
  - `templates/public/terms.html:68`;
  - `templates/payment/failed.html:43`.
  If nobody reads that inbox, privacy requests and payment problems go unanswered. The privacy notice's grievance contact is also part of the university's DPDP obligations (UPG-22).
- **Who benefits:** students and external participants who need help; the university (privacy requests reach someone).
- **What to build:** one contact address from a setting (e.g. `SUPPORT_EMAIL`, documented in `.env.example`), used by all three pages. When it's unset, the pages show no address rather than a personal one.
- **Needs from the owner:** ~~the contact address (D-4).~~ Decided 2026-10-10: `events@your-university-domain` (D-4).
- **Files touched:** `config.py` or a context processor in `app.py`, the three templates, `.env.example`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. Test: with `SUPPORT_EMAIL` set, the privacy, terms and payment-failed pages show it, and no tracked template outside `functions/` and `scratch/` contains the old account's address.
  2. Test: with it unset, those pages render without a `mailto:` link.

#### UPG-43 — Event-day lists show only events whose status is the old `active`
- **Status:** BUILT (untested)
- **Last verified:** 2026-10-10, commit "UPG-43: …" on `production-ready` (parent `932afdd`)
- **Problem:** Found while building UPG-02 [C]. Events created by SPOCs move through workflow states (`services_workflow.py:25-40`: published, registration_open, in_progress, …) and never become `active`, but:
  - the coordinator's scanner list shows only `active` events (`routes_coordinator.py:636`), so an assigned coordinator doesn't see today's event and needs the direct link `/coordinator/scan/<event>`;
  - the walk-in form lists only `active` events (`routes_coordinator.py:548`);
  - venue-QR self check-in refuses any other status (`routes_checkin.py:77,102`).
  - The judge dashboard has the same filter (`routes_judge.py:59`), covered by UPG-04.
  - **Found while building UPG-07:** the scheduled day-before reminder, the 3-day reminder and the SPOC's velocity alert also look only at `active` events (`tasks/scheduled_tasks.py:47,245,378`), so no SPOC-created event gets them. UPG-07's test uses an `active` event.
  The kiosk's own `active` check went away in UPG-02 (it now uses the shared check-in, which has no status rule).
- **Who benefits:** coordinators and volunteers on event day; participants using self check-in.
- **What to build:** one helper that says whether an event is running for event-day purposes (published, registration open or closed, in progress, and the old `active`; not draft, pending, cancelled or completed), used by these three places.
- **Files touched:** `routes_coordinator.py`, `routes_checkin.py`, `services_workflow.py` (the helper), `tasks/scheduled_tasks.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **What was built (2026-10-10, development-only run):**
  - One helper: `services_workflow.EVENT_DAY_STATUSES` (published, registration open or closed, in progress, and the old `active`) and `is_event_day_status` (`services_workflow.py:63-71`), plus `REGISTRATION_OPEN_STATUSES`.
  - The coordinator's scanner list and walk-in form query those statuses (`routes_coordinator.py:549,638`); venue-QR self check-in accepts them and refuses the rest (`routes_checkin.py:78,103`).
  - The day-before and 3-day reminders read every event-day status, and the velocity alert reads events still taking registrations (`tasks/scheduled_tasks.py:21,48,246,379`); the lifecycle job's `RUNNING`/`REGISTRATION_OPEN` are now these constants.
  - The judge dashboard is left for UPG-04 (Phase 6), as the item says.
- **To test later:** criteria 1–4 below (real database): the scanner list and walk-in form list a `registration_open` event today and not a `cancelled` one; venue self check-in for `in_progress` vs `cancelled`; the day-before reminder through `/internal/cron/reminders` for a `registration_closed` event tomorrow and not a `cancelled` one. Existing `tests/test_cron.py` and `tests/test_notices.py` use `active` events and still pass.
- **Acceptance criteria:**
  1. Test (real DB): an assigned coordinator's scanner list shows today's `registration_open` event; a `cancelled` one isn't listed.
  2. Test: the walk-in form lists the same event.
  3. Test: venue self check-in works for an `in_progress` event and refuses a `cancelled` one.
  4. Test: the day-before reminder, through `/internal/cron/reminders`, reaches registrants of a `registration_closed` event tomorrow, and not of a `cancelled` one.
- **Not scheduled yet:** it fits Phase 2 next to UPG-29 (owner's call).

#### UPG-44 — An empty payment status reads back as `unpaid` (postgres mode)
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found while building UPG-02 [R]. A registration written with `payment_status: ''` reads back as `'unpaid'` on the SQL adapter: the enum column gets its default and the read returns it. Every live registration path sets a status (form, waitlist, walk-in, payment), so this affects old, seeded or imported rows. Reports then count them as unpaid. Before UPG-02's rule (a free event owes nothing), such an attendee would have been refused at the gate.
- **Who benefits:** organisers reading payment figures.
- **What to build:** an empty or missing payment status reads back as written, as other fields do since BLK-06b; an explicit `unpaid` still reads `unpaid`.
- **Files touched:** `db_adapter.py`, tests. Touches a shared file: run rule 8's early pass.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test (SQLite and PostgreSQL): `''` and a missing `payment_status` read back as `''` and missing; `'unpaid'` reads back `'unpaid'`; filters on `payment_status == 'unpaid'` find only the explicit one.

#### UPG-45 — Form submissions lose who sent them, and read back flattened (postgres mode)
- **Status:** DONE
- **Last verified:** 2026-10-08, commit "UPG-45: …" on `production-ready` (parent `b5afda8`)
- **Problem (as found at `b5afda8`):** Found while building UPG-01 [R]. `utils.record_form_submission` writes `{event_id, reg_id, email, name, answers, submitted_at}` (`utils.py:216-229`).
  - The SQL adapter maps `answers` onto the `answers_json` column (`FIELD_MAP`, `db_adapter.py:77`), so it overwrote the full document the insert had stored there (`:1166`). Only the answers were kept; `name`, `email` and `reg_id` were dropped.
  - On read the answers came back flattened at the top level, with no `answers` key (`:1018-1024`).
  - The responses page and the forms export read `s.get('answers')` (`routes_forms.py:684,715`), so in postgres mode they listed submissions with every answer empty.
  - Firestore mode is unaffected.
- **Who benefits:** organisers reading form responses and exports.
- **What to build:** the adapter keeps the whole submission in its JSON column and reads it back as written; rows stored before the fix (answers only) read back as `{'answers': …}`.
- **What was built:** `_submission_document` (`db_adapter.py:420`) reads the stored JSON, and wraps an answers-only row from before the fix. Writes merge the document into the column and keep the generic loop from overwriting it with the answers (`:1396-1401`). Reads return the document with `event_id`, `registration_id` and, if missing, `submitted_at` from its column (`:1030-1036`). No schema change.
- **Files touched:** `db_adapter.py`, `tests/test_form_submission_documents.py` (new).
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low; only the `form_submissions` branch of the adapter changed.
- **Acceptance criteria** (`tests/test_form_submission_documents.py`, SQLite and PostgreSQL; both fail on the old adapter):
  1. ✅ Test: a submission reads back with its answers under `answers`, plus name, email, registration and time; an update changes only the fields it names (`::test_a_submission_reads_back_whole`).
  2. ✅ Test: a row stored before the fix reads back as `{'answers': …}` with its time (`::test_a_row_stored_before_the_fix_reads_back_as_answers`).
  - Full pytest: **832 passed** on SQLite and PostgreSQL 16; ruff clean.
- **Rule 8 (early pass, `db_adapter.py` changed):** all 35 open items checked against this change. Only UPG-01 reads form submissions (its criterion 2 needs this item). UPG-16's citation of the schema check's call site (`db_adapter.py:1822` at `986d108`) is now at `:1840`; its claims are unchanged. No other open item's claims change.
#### UPG-46 — Scheduled emails link to a fixed `sapthaevent.in`, not `BASE_URL`
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found while building UPG-07 [C]. The coordinators' day-before briefing links `https://sapthaevent.in/coordinator/scanner` (`tasks/scheduled_tasks.py:183`), and the SPOC's velocity alert links `https://sapthaevent.in/forms/register/<event>` (`:416`). BLK-16 moved every other emailed link to `BASE_URL`; these two point at a domain the deployment may not use.
- **Who benefits:** coordinators and SPOCs who click the link.
- **What to build:** both links built from `BASE_URL`, like the other emails (BLK-16's helper).
- **Files touched:** `tasks/scheduled_tasks.py`, tests.
- **Effort:** S · **Depends on:** BLK-16 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: with `BASE_URL=https://events.example.edu`, the briefing and the velocity alert link only to that host; `sapthaevent.in` appears in neither.
- **Not scheduled yet** (owner's call; it fits next to UPG-31).

#### UPG-47 — Events saved without times get the save time as their start and end (postgres mode)
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found while building UPG-07 [R]. The SQL adapter stores an event's `start_datetime` and `end_datetime` through `parse_datetime`, which returns *now* for an empty value (`db_adapter.py:1126-1127,1938-1940`). The SPOC's create form sends neither, so every such event reads back with its save time as start and end, not its `date`. Readers trust them [C]:
  - room-conflict checks (`services_venue.py:377,408,463`, `services_workflow.py:204`) compare the wrong times;
  - the calendar feeds read `start_datetime` before `date` (`app.py:1069-1070,1106-1111`), so they place each event at its save time;
  - UPG-07's lifecycle job works around it by using the later of `date` and `end_datetime`.
- **Who benefits:** SPOCs booking rooms; anyone reading the calendar.
- **What to build:** an empty start or end reads back empty (or derived from `date` and `time`), not the save time; readers fall back to `date`.
- **Files touched:** `db_adapter.py`, tests. Touches a shared file: run rule 8's early pass.
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** existing rows already hold save times; decide whether to clear them (a one-off script) or leave them.
- **Acceptance criteria:**
  1. Test (real DB): an event created through the SPOC form reads back with no `end_datetime` (or one on its `date`), never its save time.
  2. Test: a room conflict check for an event saved without times uses its date: a second event in the same room on that date and time clashes, one on another day doesn't.
- **Not scheduled yet** (owner's call).

#### UPG-48 — Team members get no confirmation, reminder or notice
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found while building UPG-31 [C]. Since UPG-08 a team's members are on the registration and can open its ticket, but every message goes to the lead only: the confirmation (`routes_forms.py:702`), the day-before ticket and the 3-day reminder (`tasks/scheduled_tasks.py:81,279`), and the change and cancellation notices (`services_venue.py:550`, `services_workflow.py:300`). Members find out only from the lead.
- **Who benefits:** every team member.
- **What to build:** each member with an email gets the day-before ticket (with the same QR) and the change and cancellation notices, once each, keyed per person; the confirmation tells members they were added.
- **Files touched:** `tasks/scheduled_tasks.py`, `services_venue.py`, `services_workflow.py`, `routes_forms.py`, `routes_teams.py`, tests.
- **Effort:** S · **Depends on:** UPG-08, UPG-31 · **Risk:** more email volume (Brevo's free tier allows 300 a day).
- **Acceptance criteria:**
  1. Test: for a team of three, the day-before reminder through the cron endpoint emails each member once.
  2. Test: a venue change and a cancellation reach each member once.
- **Not scheduled yet** (owner's call).

#### UPG-49 — The automation's WhatsApp channel calls a function that doesn't exist
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found while building UPG-31 [C]. `services_automation.dispatch_trigger` sends WhatsApp through `utils_whatsapp.send_whatsapp_message` (`services_automation.py:223`), which doesn't exist; the error is caught and recorded as `whatsapp_fallback`. The default rules for check-in and event reminders use that channel (`services_automation.py:51,75`), so those WhatsApp messages never go out.
- **Who benefits:** participants who opt in to WhatsApp.
- **What to build:** the channel sends through `utils_whatsapp._send`, and a failure is recorded as a failure, not a fallback.
- **Files touched:** `services_automation.py` or `utils_whatsapp.py`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low; nothing goes out without Twilio settings.
- **Acceptance criteria:**
  1. Test: a trigger with the WhatsApp channel, for a user who opted in, calls the Twilio client once (mocked).
- **Not scheduled yet** (owner's call).

#### UPG-50 — Email templates insert names and titles without escaping
- **Status:** TODO
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** Found while building UPG-31 [C]. The HTML emails put the recipient's name, the event title and messages straight into the markup (for example `utils_email.py:499,501,563,565,744,764,793`). A name typed at registration, or an event title, containing HTML is rendered as HTML in the email. Today the typed text mostly reaches its own author or comes from staff (titles, broadcast messages), so the risk is low; the notices from UPG-31 already escape.
- **Who benefits:** everyone who gets email from the app.
- **What to build:** escape every value inserted into an email template (one helper), keeping the templates' own markup.
- **Files touched:** `utils_email.py`, `tasks/scheduled_tasks.py` (the briefing and 3-day emails), tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a registrant named `<b>Ann</b>` gets a confirmation that shows the text `<b>Ann</b>`, not bold.
- **Not scheduled yet** (owner's call).

### G. Added 2026-10-10 (owner's run prompt)

#### UPG-51 — Cancelling a paid event refunds nobody
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** [C] Cancelling an event (`services_workflow.WorkflowEngine.transition_event` → `cancelled`) sends the cancellation notice (UPG-31) but touches no payment. The admin's refund action (`routes_admin.py:527`, `services_payments.start_refund`, `services_payments.py:265`) only refunds paid orders that have **no** registration, so the paid registrations of a cancelled event can only be marked "refunded" by hand, with the money returned outside the app.
- **Who benefits:** paying participants of a cancelled event; the finance office.
- **What to build:** when an event is cancelled, its staff and the Super Admin see its paid registrations, with a "Refund all through Razorpay" action: a confirm step (ticked box and the total), one Razorpay refund per payment, never twice (an atomic claim per order, as in UPG-30), failures listed with their reason and retryable, every refund audit-logged and emailed to the student.
- **Files touched:** `routes_admin.py`, `services_payments.py`, `utils_email.py`, `templates/admin/payments.html` (or a new cancelled-event refunds page), tests.
- **Effort:** M · **Depends on:** UPG-30 · **Risk:** moves real money; the confirm step and the per-order claim guard it.
- **Acceptance criteria:**
  1. Test (Razorpay mocked): a cancelled event with 3 paid registrations lists all 3; "Refund all" without the confirmation does nothing.
  2. Test: with the confirmation, the refund API is called once per payment with its ID and amount; each is recorded, audit-logged and emailed once; pressing again calls nothing.
  3. Test: one failed refund is listed with its reason, the others complete; retrying refunds only the failed one.
  4. Test: a non-admin who isn't the event's owner gets 403; refunds are refused for an event that isn't cancelled.

#### UPG-52 — Joining a team can overwrite another join or exceed `team_max`
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** [C] `routes_teams.join_team` (`routes_teams.py:64-102`) reads the registration's `members`, checks `len(members) >= team_max` (`:91`), appends, and writes the whole list back (`_save_members`, `:51`). Two people joining at once both read the same list: the second write drops the first member, or both pass the size check and the team exceeds `team_max`.
- **Who benefits:** team leads and members of hackathons and sports events.
- **What to build:** adding a member is atomic: a row lock (`SELECT … FOR UPDATE` on PostgreSQL) or a conditional update that only succeeds if `members` is unchanged, retried a few times; the size check runs inside it.
- **Files touched:** `routes_teams.py`, `db_adapter.py` (or a small SQL helper), tests.
- **Effort:** S · **Depends on:** UPG-08 · **Risk:** touches the adapter (rule 8's early pass when tested).
- **Acceptance criteria:**
  1. Test (PostgreSQL): two joins to a team with one free place, run concurrently, leave exactly one new member and `team_max` holds.
  2. Test: two joins to a team with two free places, run concurrently, keep both members.

#### UPG-53 — The home page shows a fake hackathon when there are no events
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** [C] When no event is listed, the home page builds a demo event (`app.py:704-706`, id `demo-hackathon-2026`, "SapthaHack 2026 — National AI Hackathon") and shows it as if it were real. Its links go nowhere real.
- **Who benefits:** visitors (no fake event); the university (nothing misleading on launch day).
- **What to build:** with no events, the home page shows an empty state ("No upcoming events yet") instead.
- **Files touched:** `app.py`, `templates/public/home.html` (or the home template in use), tests.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. Test: with no events, `/` returns 200, shows the empty state and doesn't contain `demo-hackathon-2026` or "SapthaHack 2026".

#### UPG-54 — The Android app loads an old Railway URL
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** [C] `capacitor.config.json:5-6` points the Android webview at `https://saptha-portal.railway.app`, a retired host; `allowNavigation` lists `*.railway.app` and `*.firebaseapp.com`. An APK built today opens a dead site.
- **Who benefits:** students using the Android app.
- **What to build:** the server URL comes from `BASE_URL` at build time (a `capacitor.config.ts` or a small script that writes the JSON before `npx cap sync`); `allowNavigation` holds only that host; the build steps are documented.
- **Files touched:** `capacitor.config.json` (or `.ts`), `package.json` script, `docs/DEPLOY.md`, tests.
- **Effort:** S · **Depends on:** none · **Risk:** low; the Flutter app under `~/development/saptha_app` is separate.
- **Acceptance criteria:**
  1. Test: no tracked file outside `functions/` and `scratch/` contains `railway.app` in the Capacitor config.
  2. Test: running the config step with `BASE_URL=https://events.example.edu` gives a config whose server URL and `allowNavigation` use only that host.

#### UPG-55 — Google sign-in and 2FA exist but nothing links to them
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** [C] `auth_oauth.py` serves `/auth/google` and `auth_2fa.py` serves `/auth/2fa/*`, but no template links to either (`grep -rn 'auth/google\|auth/2fa' templates` finds nothing). Users can't find them. (The matchmaker's `MOCK_STUDENTS`, also on the launch list, is already UPG-14 criterion 4.)
- **Who benefits:** every user (one-click login, a second factor for staff accounts).
- **What to build:** a "Sign in with Google" button on the login page only when Google OAuth is configured; a "Two-factor authentication" section on the profile page (set up / turn off) only when 2FA is available. UPG-10 later restricts Google sign-in to the university domain.
- **Files touched:** `templates/login.html`, the profile template, `app.py` (a context flag), tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: with Google OAuth configured, the login page links `/auth/google`; without it, it doesn't.
  2. Test: the profile page links the 2FA set-up when 2FA is available and not when it isn't.

#### UPG-56 — Checkout has no coupon field
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** [C] The server applies a coupon validated on the server when `create_order` gets one (`services_payments.server_price`, `services_payments.py:77`; uses held since UPG-36), but no template or script sends one: `grep -rni coupon templates static/js` finds only marketing copy.
- **Who benefits:** organisers running discounts; students with a code.
- **What to build:** a coupon field on the checkout page with an "Apply" button that shows the server's price (fee, discount, total) before paying, and sends the code with the order. The server's price stays the only price.
- **Files touched:** `templates/payment/checkout.html`, its script, `routes_payment.py` (a price-preview endpoint if needed), tests.
- **Effort:** S · **Depends on:** UPG-36 · **Risk:** low; the server already validates.
- **Acceptance criteria:**
  1. Test: the checkout page has a coupon input and its script sends the code with the order.
  2. Test: the price preview with a valid code shows the discounted total from the server; an invalid code shows the server's error and the full price.

#### UPG-57 — Placement drives: eligibility rules and shortlist rounds
- **Status:** TODO
- **Last verified:** 2026-10-10, commit `6b4fe41`
- **Problem:** MISSING [C]. The event-type table lists placement drives as "Generic registration only": eligibility (branch, CGPA, backlogs), shortlists per round and the company's lists are kept in Excel.
- **Who benefits:** the placement cell, students, recruiting companies.
- **What to build:** eligibility rules on the event (allowed branches, minimum CGPA, maximum active backlogs), checked at registration against what the student enters (or their roster record, UPG-10); named shortlist rounds the organiser moves registrations through (selected / rejected per round); an export per round.
- **Files touched:** `routes_spoc.py` (or a new `routes_placement.py`), `routes_forms.py`, `services_export.py`, templates, tests.
- **Effort:** M · **Depends on:** UPG-01 · **Risk:** self-declared CGPA can be wrong until the roster import holds it.
- **Acceptance criteria:**
  1. Test: a student whose branch isn't allowed, or whose CGPA is below the minimum, or with too many backlogs is refused with the reason; an eligible one registers.
  2. Test: the organiser moves 2 of 3 registrations into round 2; the round-2 export lists exactly those 2.
  3. Test: only the event's staff can move registrations or export a round.

---

## 7. Production-ready plan (phases)

*(Replaces "Recommended next 3 builds"; set in Phase 0, 2026-09-30.)* Work happens on the `production-ready` branch, one commit per item ("<ID>: <summary>"), in this order. Each phase ends with full checks, a re-verification of every open item (AGENTS.md rule 8, changed by the owner on 2026-10-02 from "after every 5 DONE items"), a phase summary in the changelog and a stop for the owner's "continue".

| Phase | Items, in order | Notes |
|---|---|---|
| 0. Sync the plan | — | Done 2026-09-30: every item re-verified; BLK-12, BLK-13, UPG-16 to UPG-32 added; sessions merged into BLK-08. |
| 1. Blockers | BLK-02 → BLK-14 → BLK-03 → BLK-04 + BLK-12 → BLK-05 → BLK-06 → BLK-07 → BLK-08 → BLK-10 → BLK-13 → BLK-15 → BLK-11, then BLK-16 (added 2026-10-02 from the PR #48 review) and BLK-17 (found starting UPG-33), both built before Phase 2 | **Done** (2026-10-01; BLK-16 and BLK-11's CI on GitHub 2026-10-02). Waiting on the owner: BLK-01's last criterion (the PR refs, GitHub Support, D-2); it doesn't block Phase 2. |
| 2. Event day | UPG-33 account emails → UPG-35 uniform login/reset messages → UPG-37 hourly login cap → UPG-39 links in the dev console → UPG-40 resend set-password links → UPG-41 leftover mail password → UPG-02 check-in → UPG-06 certificates → UPG-03 exports → UPG-29 assignment → UPG-01 forms → UPG-34 legacy registration route → UPG-08 teams → UPG-30 paid events → UPG-36 coupon uses → UPG-05 feedback → UPG-07 scheduled jobs → UPG-31 notifications | **Done** (2026-10-08), except UPG-30's criterion 4 (the owner's checkout in Razorpay test mode). Found and built during the phase: BLK-18, BLK-19, UPG-45. Not pushed yet: the remote `production-ready` is at `37c2a5c`. UPG-01 comes before UPG-08 (team fields need it); UPG-07 comes before UPG-31 (the reminder needs it). Each flow gets an end-to-end test on the real database layer. |
| 3. Production setup | UPG-43 event-day states → UPG-16 migrations → UPG-18 background jobs → UPG-19 pagination → UPG-20 boot checks/health/logs → UPG-21 backups (UPG-17 folded in, D-5) → UPG-22 privacy (with UPG-42) → UPG-51 refund all on cancellation → UPG-52 atomic team join | Order set by the owner's run prompt (2026-10-10). |
| 4. Frontend | UPG-23a–h layout → UPG-24 Bootstrap/fonts → UPG-25 inline scripts/CSP → UPG-26 forms → UPG-27 images → UPG-28 375px check → launch checks UPG-53, UPG-54, UPG-55, UPG-56 | One commit per UPG-23 area. |
| 5. Clean-up | UPG-14 → UPG-15 → UPG-38 Jekyll workflow → one seed command | UPG-15 removes `functions/saptha_app/` and `catalyst.json` (D-1). |
| 6. University features (2026-10-10) | UPG-04 → UPG-09 → UPG-10 → UPG-11 → UPG-12 → UPG-13 → UPG-57; UPG-44, UPG-46 to UPG-50 where they fit | Added by the owner's run prompt. |
| 7. Release check | UPG-32 | Fresh clone, production boot, restart/two instances, all scans, `docs/DEPLOY.md`, final report. |

*(2026-10-10: UPG-04 and UPG-09 to UPG-13 moved into Phase 6 above; UPG-32 is Phase 7.)*

**Development-only run (owner, 2026-10-10).** For the run that starts at `6b4fe41`, rule 5 (tests) and rule 8 (re-verification) are suspended. An item built in this run is marked **BUILT (untested)**, not DONE, and gets a "To test later" line listing what its acceptance criteria need. Every commit still passes `ruff check .` and starts the app (home page loads). No existing test is deleted, skipped or weakened.

### Decisions needed

| ID | Decision | Blocks | Status |
|---|---|---|---|
| D-1 | **Is Cloud Run the only deploy target?** If yes, `functions/saptha_app/` (the Zoho Catalyst copy) and `catalyst.json` are removed in Phase 5. That copy still has the kiosk/ticket holes (BLK-12), the public SuperAdmin sign-up (BLK-14), the bandit findings (BLK-11) and the walk-in default password (UPG-15). If Catalyst stays, it needs a build step instead of a tracked copy. | BLK-12 criterion 4; BLK-14 criterion 3; UPG-15 criteria 3–4 | **Decided (owner, 2026-10-01): yes, Cloud Run is the only deploy target.** UPG-15 removes `functions/saptha_app/` and `catalyst.json` in Phase 5, which completes BLK-12 criterion 4 and BLK-14 criterion 3; no Catalyst build step is needed. Until then, BLK-11 fixes the two flagged files in place so CI can go green. |
| D-2 | **BLK-01 owner actions:** force-push the rewritten `master`, delete the remote `main` and `claude/busy-davinci-6nkabi`, and ask GitHub Support to purge the 47 PR refs (commands in the 2026-09-29 changelog). The agent never pushes. | BLK-01 criteria 0 and 4 (CI green on GitHub); BLK-11 criterion 2 | **Done (owner, 2026-10-01):** `master` force-pushed, `main` and `claude/busy-davinci-6nkabi` deleted, `production-ready` pushed, GitHub Support contacted. Verified with `git ls-remote`; BLK-01 criterion 4 is met on GitHub. **Left:** Support removing the 47 PR refs (BLK-01 criterion 0). Nothing else waits on it. |
| D-3 | **UPG-35: should login, password-reset and sign-up messages hide whether an account exists?** | UPG-35 | **Decided (owner, 2026-10-02):** login and password-reset messages become uniform ("Email or password is incorrect"; "If an account exists for this email, we've sent a reset link"). Sign-up and registration stay as they are: an existing email is told to log in first. Scheduled in Phase 2 right after UPG-33. |
| D-5 | **UPG-17: fold into UPG-21?** Nothing the app runs stores files any more (end-of-Phase 2 re-verification), so UPG-17's criteria 3–4 have nothing to test. Proposed: move its storage settings (S3 endpoint, private objects, no silent local fallback) into UPG-21's backup work and close UPG-17. | UPG-17, UPG-21 | **Decided (owner, 2026-10-10): yes.** UPG-17 is folded into UPG-21: its storage settings (S3 endpoint, private objects, no silent local fallback) are built with the backups; UPG-17 is closed as MERGED. |
| D-4 | **UPG-42: which address should the privacy, terms and payment-failed pages give for help and privacy requests?** | UPG-42 | **Decided (owner, 2026-10-10):** `events@your-university-domain`. UPG-42 reads it from `SUPPORT_EMAIL`; `.env.example` gives this value. |
| D-6 | **UPG-30 criterion 4: when is the Razorpay test-mode checkout run?** | UPG-30 criterion 4 | **Decided (owner, 2026-10-10):** deferred to UPG-32 (release check), run on a public test deployment together with the webhook (Razorpay must reach `<BASE_URL>/payment/webhook/razorpay`). UPG-30 stays IN PROGRESS until then. |

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
- **Re-verification after Phase 1 (2026-10-02, `986d108`):** by reading the code [C], with runs where a claim could be run [R]: the empty-database Alembic upgrade, the counting script on `56a014d` and `986d108`, the app's URL map for the linked paths, the read-only `git ls-remote`, and the full test, lint and scan runs. As in Phase 0, no flow was re-driven over HTTP beyond what the tests do; inventory rows marked "not re-run" still are.

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
| 2026-10-01 | "BLK-05: …" (parent `7b394c0`) | BLK-05, BLK-06 | **BLK-05 DONE.** `tests/conftest.py` blanks every outbound credential before the app loads `.env`, and forces inline Celery on an in-memory broker (CI's Redis broker would have queued tasks that never run). New real-DB journey: create → appoint judge → register → check-in → allocate → score → complete → feedback → certificate. `_login` now fails on a failed login. BLK-06 gains renamed score keys (criterion 9). Full pytest 448 passed, 1 xfailed on SQLite, PostgreSQL 16 and with CI's broker variable; ruff clean. |
| 2026-10-01 | "BLK-06a: …" (parent `23a3ec5`) | BLK-06 | **BLK-06a done** (BLK-06 stays IN PROGRESS for 06b). Enum-backed filters compare the stored document value with explicit synonyms only; writes map values the same way; event/registration status enums gain the workflow states; `events.spoc_id` is an indexed SQL column; the audit actor and empty organisation keys are stored correctly. Kept the enum columns (an existing test pins `users.role` as an enum) instead of converting to strings; recorded the existing-database caveat for UPG-16. The strict xfail now passes (marker removed). 6 new real-DB tests (all fail on the old adapter). Full pytest 455 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-06b: …" (parent `dda7716`) | BLK-06, UPG-06 | **BLK-06 DONE** (06a + 06b). 06b: document shadow on the eight newer tables; member and score rows return the dicts they were written from (per-member attendance and the judge route's score keys now survive, and two judges' scores coexist); found and fixed new tickets reading back as checked in (an empty nullable date became "now"). Criterion 4's bulk-certificates check moved to UPG-06. 3 new real-DB tests (all fail on the old adapter); the journey test checks per-criterion scores again. Full pytest 458 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-07: …" (parent `c05af5e`) | BLK-07 | **BLK-07 DONE.** No migration on GET; "Migrate roles" previews (dry run) and applies only with `confirm=1`; login, password reset and the API login map the migrated names (`UniversityAdmin` → SuperAdmin, `UnitAdmin` → ClubSPOC), so the SuperAdmin keeps access after a confirmed migration (tested end to end). Kept the migration's `users.role` rewrite because an existing test pins it. 4 new real-DB tests (all fail on the old code). Full pytest 462 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-08: …" (parent `22598e7`) | BLK-08 | **BLK-08 DONE.** Sessions live in the app database (`session_store.py`, `flask_sessions` table; Redis when `REDIS_URL` is set), survive restarts and are shared across instances; cookies are HttpOnly, Secure in production and SameSite=Lax; empty sessions are never stored, and the shared layout no longer mints a CSRF token (and session) for anonymous page views. 5 new real-DB tests (all fail on the old code). Full pytest 467 passed on SQLite, PostgreSQL 16 and with CI's `SESSION_TYPE=filesystem`; ruff clean. |
| 2026-10-01 | "BLK-10a: …" (parent `04d2e27`) | BLK-10 | **BLK-10a done** (BLK-10 stays IN PROGRESS for 10b). New `seed_safety.guard()`, called first by all 31 seed/setup/wipe scripts: refuses production-looking targets (including `.env`'s `CLOUD_SQL_INSTANCE` and Cloud SQL sockets) with exit 3 before any connection unless `--i-know-this-is-production` is passed; Firestore scripts must also name the project. Found while testing: a local Unix-socket PostgreSQL URL has no host and must count as local. Full pytest 626 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-10b: …" (parent `8ecdc9e`) | BLK-10 | **BLK-10 DONE** (10a + 10b). No seed/setup script uses a string literal password; passwords come from `SEED_<ROLE>_PASSWORD` or `secrets.token_urlsafe(12)` and are printed once at exit; AST scan pins every script (`tests/test_seed_safety.py::test_no_script_uses_a_string_literal_as_a_password`). Full pytest 658 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-01 | "BLK-01: …" (parent `10207cd`) | BLK-01, D-1, D-2, BLK-11, BLK-12, BLK-14, UPG-15 | **Owner actions recorded.** D-2 done: the owner force-pushed the rewritten `master`, deleted the remote `main` and `claude/busy-davinci-6nkabi`, pushed `production-ready` and contacted GitHub Support. Verified read-only [R]: `git ls-remote` shows only `master` (`56a014d`, same as local) and `production-ready` (`10207cd`) plus the 47 unchanged PR refs; neither branch's history contains a removed path; CI run 36886209908 on `master` passed the secret scan and ruff; bandit failed on the known BLK-11 findings and pytest failed (reproduced locally, recorded as BLK-15 in the next entry). BLK-01 criterion 4 ✅; criterion 0 waits only on Support removing the PR refs, so BLK-01 stays IN PROGRESS. D-1 decided: Cloud Run is the only deploy target, so UPG-15 removes `functions/saptha_app/` and `catalyst.json` in Phase 5. That completes BLK-12 criterion 4 and BLK-14 criterion 3, and UPG-15's Catalyst build-step check is dropped as obsolete. BLK-11 still fixes the two flagged files in place until then, and now notes that CI doesn't run on `production-ready` pushes (only on pushes to `main`/`master`/`develop` and on PRs into them). Docs only. |
| 2026-10-01 | "BLK-01: …" (parent `10207cd`) | BLK-15, BLK-10, BLK-11 | **New blocker BLK-15**, found while checking CI after the push. CI's test job was reproduced in fresh clones with its exact environment, a Redis server and its exact command [R]. `master` (`56a014d`) fails `test_seminar_e2e.py::test_capacity_waitlist_and_promotion_guard`, because the Redis broker queues the promotion; BLK-05 already fixed this on `production-ready`. `production-ready` (`10207cd`) gives 657 passed, 1 failed: BLK-10's Firestore test needs the developer's git-ignored `serviceAccountKey.json`. The same mismatch means the guard checks a different key than the scripts use and accepts any project name when it finds none. Scheduled in Phase 1 before BLK-11, whose criterion 2 (every CI job green) needs it. Recorded, not fixed. |
| 2026-10-01 | "BLK-13: …" (parent `07cf145`) | BLK-13, UPG-07, UPG-14, UPG-20, UPG-35, BLK-11 | **BLK-13 DONE.** Failed logins (web and API share one counter) and password-reset requests are limited to 5 per IP and 5 per account per minute (settings `LOGIN_THROTTLE_*`). The next attempt gets 429 with "try again in N seconds" and `Retry-After`. The check runs before the account is looked up, so known and unknown accounts get the same answer. A success clears only the account's counter. Counters are hashed rows in the new `login_attempts` table, or Redis sorted sets when `REDIS_URL` is set (falling back to the database on Redis errors), so every instance shares them. An autouse conftest fixture resets them between tests, because all test clients share 127.0.0.1. 15 new tests on the real database, parametrised over both stores; criterion 3 uses a second process; 13 fail with the old route code, and the other 2 fail without the API's reset. Added `fakeredis==2.39.0` to dev requirements. Full pytest 673 passed on SQLite and PostgreSQL 16; ruff clean; bandit shows only the 5 BLK-11 findings; under CI's environment with Redis, 672 passed plus the known BLK-15 failure. Recorded: UPG-07 also purges old login attempts; UPG-14 gains the dead in-memory helpers in `security_middleware.py`; UPG-20 gains a stale `.env.example` comment; new UPG-35 (login/sign-up messages reveal whether an account exists; owner decision). **Rule 8:** 11 items DONE since the Phase 0 re-verification; the pass is scheduled for the end of Phase 1 (after BLK-15 and BLK-11). |
| 2026-10-01 | "BLK-15: …" (parent `9135851`) | BLK-15, BLK-10, BLK-11 | **BLK-15 DONE.** One credential resolver, `seed_safety.firestore_credentials` (order: `FIREBASE_CREDENTIALS`, `FIREBASE_KEY_PATH`, `./serviceAccountKey.json`, project-root key, `GOOGLE_APPLICATION_CREDENTIALS`; the first source set wins, even if broken). The guard confirms exactly that key's project and refuses when it can't read one; all 10 Firestore scripts connect through `firestore_key()`. The existing Firestore test now supplies its key through `FIREBASE_CREDENTIALS` (assertions unchanged). 15 new test cases, plus a runner that reports the project each script connects with; every new test fails on the old code (3 of them only in a clone without the developer's key). CI's exact test command in a fresh clone with Redis: 689 passed (it failed before). Full pytest 689 passed on SQLite and PostgreSQL 16; ruff clean; bandit shows the 5 BLK-11 findings only. |
| 2026-10-01 | "BLK-11: …" (parent `affcab7`) | BLK-11 | **BLK-11 DONE locally.** The `functions/saptha_app` copy gets the root copies' fixes: a reasoned `# nosec B104` on the placeholder IP in `audit_logger.py`, and bound parameters for the two `information_schema` lookups in `db_adapter.py`. `scripts/seed_emulator.py` gets a 30 s request timeout. CI's bandit command exits 0 on a fresh clone (5 findings before). Every CI job that can run here passes in a fresh clone with CI's settings: ruff, hygiene (37), full-history gitleaks, CI's pytest command with Redis (689), bandit; Docker build not run (no Docker here; it runs only on `master`). Criterion 2 (green on GitHub) waits on the owner's push and a pull request into `master`. Full pytest 689 passed on SQLite and PostgreSQL 16. |
| 2026-10-01 | "BLK-11: …" (parent `affcab7`) | Phase 1 summary | **Phase 1 (blockers) done.** **DONE:** BLK-02, BLK-14, BLK-03, BLK-04 (04a + 04b), BLK-12 (root app), BLK-05, BLK-06 (06a + 06b), BLK-07, BLK-08, BLK-10 (10a + 10b), BLK-13, BLK-15, BLK-11 (locally). **Still open, all waiting on the owner or a later phase:** BLK-01 criterion 0 (GitHub Support removing 47 PR refs); BLK-11 criterion 2 (CI green on GitHub after the push and a pull request into `master`); BLK-12 criterion 4 and BLK-14 criterion 3 (UPG-15 removes `functions/saptha_app` in Phase 5, D-1); BLK-03's manual Razorpay test-mode check (UPG-30). **Checks at the end of Phase 1:** full pytest 689 passed on SQLite and PostgreSQL 16 (414 + 1 xfailed at the start of the phase); ruff clean; bandit exit 0; CI's pytest command in a fresh clone with a Redis server: 689 passed. **Decisions recorded:** D-1 (Cloud Run only) and D-2 (push done). **New items opened during Phase 1:** BLK-14, BLK-15, UPG-33, UPG-34, UPG-35 (UPG-35 needs an owner decision). **Rule 8:** 13 items have been marked DONE since the Phase 0 re-verification, so a re-verification pass of every open item is due before Phase 2 starts. **Next:** the owner pushes `production-ready` and opens a pull request into `master` (CI only runs there); then the re-verification pass; then Phase 2, starting with UPG-33. |
| 2026-10-02 | "docs: …" (parent `9e28bf3`) | UPG-35, D-3, BLK-13 | Owner decision D-3: UPG-35 makes the login and password-reset messages uniform and keeps sign-up and registration as they are; scheduled in Phase 2 right after UPG-33. UPG-35 rewritten to match (a correct password with the wrong role may keep a role hint). "Before the next deploy" gains `LOGIN_THROTTLE_IP_LIMIT` ≈ 50 for campus Wi-Fi and the ProxyFix hop count. Docs only. |
| 2026-10-02 | "docs: …" (parent `986d108`) | ALL (re-verification after Phase 1) | **Full re-verification of every open item, plus sections 1–4, against the code at `986d108`** (rule 8: 13 items DONE since Phase 0; the count now restarts at 0). Each citation was mapped from its item's last-verified commit by exact line alignment, every moved or changed one was read, and the counts were re-run on `56a014d` and `986d108` with one script. **Status corrections:** UPG-06 → IN PROGRESS (criterion 2 already met by BLK-05's journey test); UPG-15 → IN PROGRESS (criterion 2 met by BLK-09's test). **Claims corrected:** UPG-02 (the kiosk/offline 403 now hits only unassigned coordinators; `get_ticket` is staff-only but still treats the token as an ID); UPG-03 (the AI report's gate passes for the owner; SPOC, coordinator and forms exports already check `export_data`, but only the forms one is tested); UPG-05 (the lead's feedback works on the real database; criterion 1 lacks only the read-back); UPG-06 (the certificate name is fixed; the bulk gate passes); UPG-08 (team settings persist; the fallback form adds only a team-name field); UPG-10 and UPG-12 (account creation moved to `services_accounts`); UPG-15 (the dead nav links are gone or resolve, there's no debug route, seed-script counts corrected); UPG-16 (tables and columns added since Phase 0 listed; `alembic upgrade head` on an empty DB still fails [R]); UPG-19 (25 `.stream()` calls in `routes_admin.py`); UPG-20 (43 of 91 env vars in `.env.example`); UPG-23 (111 standalone templates, not 110); UPG-25 (78 templates, 490 handlers). **Line moves only:** UPG-05, 06, 08, 10, 12, 14, 15, 16, 20, 25, 29, 30, 33, 34, BLK-01 and the deploy checklist. **Unchanged and still accurate:** UPG-01, 04, 07, 09, 11, 13, 17, 18, 21, 22, 24, 26, 27, 28, 31, 32, 35. **Inventory:** kiosk and venue-QR check-in → WORKING in the root app (BLK-12); org units → WORKING (BLK-07); audit log → WORKING (BLK-06a); manual check-in, feedback, offline, AI matching, results, email, admin dashboard and exports rows updated; line moves in 13 rows. **Journeys:** 18 steps updated with the item that fixed them. **Event types:** BLK items dropped from "Needed"; NSS/NCC keep their category (BLK-06a). No new items: nothing found needed one. **Checks [R]:** full pytest 689 passed on SQLite and PostgreSQL 16; ruff clean; bandit exit 0. BLK-01's remote state unchanged (47 PR refs). Next: Phase 2, starting with UPG-33 and then UPG-35. |
| 2026-10-02 | "docs: …" (parent `7aac9ca`) | BLK-16, UPG-30, UPG-36, UPG-37, UPG-38, UPG-20 | Owner's code review of PR #48 (merged into `master` as `86348fe`). **New blocker BLK-16:** email, WhatsApp, QR and referral links are built from the request's host, and ProxyFix trusts `X-Forwarded-Host`, so a forged header on a reset or registration makes the real email link to an attacker's site; to be built before Phase 2. **UPG-30** gains (a) paid-but-unregistered orders (plus: completion doesn't re-check capacity, so a late payment overbooks) and (b) no webhook, with a signed `payment.captured` webhook, an admin list of paid orders without a registration and a refund action (effort M → L). **New:** UPG-36 coupon uses can exceed `max_uses`; UPG-37 hourly per-account login cap (~20/h); UPG-38 delete the sample Jekyll workflow. Scheduled: UPG-37 after UPG-35, UPG-36 after UPG-30, UPG-38 in Phase 5. UPG-20 gains the retired Railway logo URL. Docs only. |
| 2026-10-02 | "BLK-16: …" (parent `0f22a5c`) | BLK-16, BLK-11 | **BLK-16 DONE.** One helper (`utils_email._base_url`) builds every outbound link from `BASE_URL`: reset and set-password emails, ticket and venue QR codes, referrals, WhatsApp messages, the waitlist pay link, reminder emails and certificate verify links. It never uses the request's host, and the old Cloud Run and Railway fallbacks are gone. Production refuses to start without an `https://`, non-localhost `BASE_URL`; ProxyFix trusts only `X-Forwarded-For` and `X-Forwarded-Proto`. 12 new real-database tests with a forged `Host` and `X-Forwarded-Host` (11 fail on the old code); the production-config test's valid config gains a `BASE_URL`. Full pytest 701 passed on SQLite and PostgreSQL 16; ruff clean. **BLK-11 DONE:** every CI job green on pull request #48 and, Docker build included, on `master` after the merge (`86348fe`). Rule 8: 2 items DONE since the 2026-10-02 re-verification. |
| 2026-10-02 | "BLK-17: …" (parent `a417e88`) | BLK-17, UPG-29 | **New blocker, found while starting UPG-33, and DONE** (built before UPG-33 under rule 2). 10 ClubSPOC write routes (end event, publish results, add judges by form or CSV, rooms, room reassignment, announcements, agenda, open hall, certificate templates) and 4 read pages acted on any event with no ownership check. One helper now requires the right permission on the event first; room reassignment also checks the registration's event. 3 new real-database tests (2 fail on the old code, where another SPOC could end the event). UPG-29 notes the judge routes are now covered. Full pytest 704 passed on SQLite and PostgreSQL 16; ruff clean. Rule 8: 3 items DONE since the 2026-10-02 re-verification. |
| 2026-10-02 | "UPG-33: …" (parent `0b9463a`) | UPG-33 | **UPG-33 DONE** (first Phase 2 item). Before building, the item was widened (rule 3) to the three more paths that emailed passwords: SPOC `assign_coordinator`, `add_judge` and `upload_judges_csv`, and admin `appoint_spoc` with its typed password. Every account someone else creates (walk-in, coordinator staff, SPOC-appointed coordinator or judge, admin-appointed SPOC) is now unverified and opened with a one-time set-password link whose email says why it exists. The staff WhatsApp notice carries no credentials, and the admin form has no password field. Reset links are bound to the current password hash, so each works once. 8 new real-database tests (all fail on the old code) record every plaintext passed to `generate_password_hash` and assert none reaches an email or WhatsApp message. Full pytest 712 passed on SQLite and PostgreSQL 16; ruff clean. Rule 8: 4 items DONE since the 2026-10-02 re-verification. |
| 2026-10-02 | "UPG-35: …" (parent `032e7c3`) | UPG-35, BLK-13 | **UPG-35 DONE** (D-3). Web and API login answer "Email or password is incorrect." for an unknown email, a wrong password and an old unhashed password, and the API no longer gives the latter its own 403. Password reset always answers "If an account exists for this email, we've sent a reset link." A correct password with the wrong role still gets a role hint. Sign-up and registration unchanged and now pinned. 4 new real-database tests (criteria 1–3 fail on the old code); BLK-13's API test now expects the new 401 wording (still exact). Full pytest 716 passed on SQLite and PostgreSQL 16; ruff clean. Rule 8: 5 items DONE since the 2026-10-02 re-verification (BLK-11, BLK-16, BLK-17, UPG-33, UPG-35). |
| 2026-10-02 | "docs: …" (parent `37c2a5c`) | Process, UPG-39, UPG-40, UPG-41 | Owner: AGENTS.md (and the identical CLAUDE.md) rule 8 now runs the re-verification once at the end of each phase, or early when a change touches files many open items depend on. "Before the next deploy" gains `BREVO_API_KEY`, `MAIL_FROM` and a test-send step, since UPG-33 makes the emailed link the only way into new accounts. **New:** UPG-39 (development logs set-password and reset links when no mail provider is set; never in production), UPG-40 (SuperAdmin users page with a resend button; no users page is routed today), UPG-41 (a third Gmail app password for the old mail account in `utils_email.py`'s docstring since 2026-04-19, revoked by the 2026-09-30 password change; remove it and the hard-coded sender). Scheduled after UPG-37. Docs only. |
| 2026-10-02 | "UPG-37: …" (parent `06f4b02`) | UPG-37, BLK-13 | **UPG-37 DONE.** Each throttle counter has its own window: logins are also capped at 20 failures per account per hour (`LOGIN_THROTTLE_ACCOUNT_HOURLY_LIMIT`), on the same stored attempts, which are now kept for an hour. A success clears both account windows; IPs and reset requests have no hourly cap. 6 new cases on both counter stores (criteria 1–2 fail on the old code). One BLK-13 test's fixed list of 20 Redis connections ran out with three counters per check; it now gets a new connection per call (same assertions). Full pytest 722 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-02 | "UPG-39: …" (parent `1b04a80`) | UPG-39 | **UPG-39 DONE.** With no mail provider configured, the set-password and reset emails log their link in development (WARNING, marked development-only) so the flows can be tested locally. In production only an error naming the missing provider is logged, never the link, and with a provider nothing is logged. 3 new real-database tests (criteria 1–2 fail on the old code). Full pytest 725 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-07 | "UPG-40: …" (parent `118dbf3`) | UPG-40, UPG-15 | **UPG-40 DONE.** New Super Admin page `/admin/users` on the shared layout, linked from the layout and the admin dashboard: every account with its role and whether it has set a password. Accounts still waiting get a POST "Resend set-password link" button that emails a fresh link (UPG-33's sender) and audit-logs it. Super Admin accounts, accounts with a password and unknown emails are refused and get nothing. The never-rendered standalone `templates/admin/users.html` (GET delete link, form to a missing route) is replaced. 6 new real-database cases (all fail on the old code). UPG-15's dead-link and unused-template notes updated. Full pytest 731 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-07 | "UPG-41: …" (parent `dee2135`) | UPG-41, UPG-42, D-4 | **UPG-41 DONE.** `utils_email.py`'s docstring names the mail settings only: the old account's address and app password are gone. The sender is `MAIL_FROM`, else `MAIL_USER`; with neither, Brevo and Resend refuse to send with an error naming `MAIL_FROM`. `config.py`'s mail account and password default to empty. New hygiene scan: no tracked file outside `functions/` and `scratch/` gives `MAIL_PASS`/`MAIL_PASSWORD` a value in code, docstrings or config (standard library only, so CI's hygiene job runs it). 28 new cases; criteria 1–2 fail on the old code. Criterion 3: the owner confirmed on 2026-10-07 that the old Gmail account lists no app passwords. Deploy checklist's `MAIL_FROM` row updated. **New:** UPG-42 (privacy, terms and payment-failed pages give the old account as the contact address) and D-4 (which address to use). Full pytest 759 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-07 | "BLK-18: …" (parent `2db0db1`) | BLK-18, Rule 8 | **New blocker, found while starting UPG-02, and DONE** (built before UPG-02 under rule 2, as with BLK-17). `can()` gave every Volunteer `check_in` on every event. On the real database an unassigned volunteer marked another event's registration `Present`, and could read its scanner view and open its ticket and QR. A Volunteer now has `check_in` only on events whose staff lists them, like an EventCoordinator. 3 new real-database tests (2 fail on the old code; the third guards against over-blocking). Full pytest 762 passed on SQLite and PostgreSQL 16; ruff clean. **Rule 8 early pass** (`services_permission.py` touched): all 37 open items checked against the change; only UPG-02 is affected, and in the direction it asks for. |
| 2026-10-07 | "UPG-02: …" (parent `5c54cb8`) | UPG-02, BLK-19, UPG-43, UPG-44, UPG-14 | **UPG-02 DONE.** One check-in, `routes_ticket.check_in`, behind `POST /ticket/api/checkin`. It takes the scanned link or signed token, never a registration ID. It needs `check_in` on the ticket's event and that the event exists, and refuses another event's ticket. One payment rule: free, waived or paid in any case; a free event owes nothing. A repeat answers "Already checked in at HH:MM." with the first time. The coordinator, SPOC and HUD scanners, a USB scanner at the kiosk and the rewritten offline queue (IndexedDB, one entry per ticket, replay-safe) all use it. `/ticket/verify` POST, `/ticket/api/verify` POST and kiosk confirm call the same function, which closes BLK-12's missing-event gap. 20 new cases, all failing on the old code, including a Node run of `offline-sync.js` against a live copy of the app. **New:** BLK-19 (registrant names inserted with `innerHTML` on staff pages run as script: stored XSS; to be built before UPG-06 under rule 2), UPG-43 (scanner list, walk-in list and venue self check-in accept only the old `active` status), UPG-44 (an empty payment status reads back `unpaid`). UPG-14 gains the by-ID check-in routes left beside the shared one, and `/ticket/api/verify`'s Bearer login, which imports a function that doesn't exist. Full pytest 782 passed on SQLite and PostgreSQL 16; ruff clean; bandit exit 0. |
| 2026-10-08 | "BLK-19: …" (parent `0a68ce6`) | BLK-19, UPG-15, UPG-25 | **BLK-19 DONE** (found in UPG-02; built before UPG-06 under rule 2). The audit found 241 places in 30 templates and scripts where a value went into HTML unescaped; other people's text could run as script on the public leaderboard, calendar, landing page and chatbot, on SPOC, judge, admin and coordinator pages, and in the student dashboard's notifications. New `static/js/escape.js` (`escapeHtml`, `escapeJsAttr` for handler attributes, `safeUrl` for links), loaded by the shared layout and each standalone page that uses it; shared scripts build text nodes instead; four page-local helpers, two of which missed single quotes, are gone. `tests/html_sinks.py` scans every tracked template and script, so new code is held to the same rule. 35 new test cases (the scan and the loader check fail on the old code; a Node test of the helpers; a real-database check that a markup name is stored as typed and shown as text). UPG-15's two dead templates are skipped by the scan until it deletes them; UPG-25 stays the second layer. Full pytest 817 passed on SQLite and PostgreSQL 16; ruff clean; bandit exit 0. |
| 2026-10-08 | "UPG-06: …" (parent `816808c`) | UPG-06, UPG-14 | **UPG-06 DONE.** One issuing path, `utils_certificate.issue_event_certificates`, for ending the event (through the Celery task, inline without a broker) and the SPOC's bulk button. Each attendee marked Present gets a PDF (uploaded template or built-in design; the top three scores get winner certificates), a certificate record and ID, the verify URL on the registration and an emailed PDF, and never a second one. Drawing a PDF no longer writes records; the download route and the email use the stored ID, so their QR and link resolve. The broken per-registration task and the two old send-all functions are removed; the bulk button uses BLK-17's permission check. 3 new real-database tests (all fail on the old code). UPG-14 gains API v1's separate certificate store, which `/verify` can't see. Full pytest 820 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-08 | "UPG-03: …" (parent `f964a34`) | UPG-03 | **UPG-03 DONE.** New `services_export.py`: one export of an event's registrations (CSV and Excel) used by the SPOC, coordinator and admin routes, with every column the item lists. Department and year come from the profile, form or USN; spreadsheet-formula names are quoted. A one-click event report (Excel): summary, by department, by year, feedback, winners, registrations; linked from the SPOC dashboard. Every export route now answers 403 to anyone without `export_data` on the event (or, for the all-events export, to non-admins), instead of a login redirect; the coordinator's Excel export no longer swallows its 403. 6 new real-database cases (all fail on the old code). Full pytest 826 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-08 | "UPG-29: …" (parent `2f6262f`) | UPG-29, UPG-04 | **UPG-29 DONE.** Tests first, then the fixes they called for. New `POST /spoc/remove_staff/<event_id>` removes a coordinator or judge from the event's staff and coordinators, ending their access to registrations, exports, check-in and scoring; the SPOC dashboard gets remove buttons on coordinator chips and a judge list with Remove in the judges dialog. `assign_coordinator` now answers another SPOC with 403 (it redirected) before creating anything. The judge dashboard's `active`-only filter stays with UPG-04 criterion 3. 4 new real-database cases (all fail on the old code). Full pytest 830 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-08 | "UPG-45: …" (parent `b5afda8`) | UPG-45, UPG-01, Rule 8 | **New item, found while building UPG-01, and DONE** (UPG-01's criterion 2 depends on it). On the SQL adapter a form submission kept only its answers, and read them back flattened with no `answers` key, so the responses page and the forms export showed every answer empty in postgres mode. The adapter now keeps and returns the whole submission; old rows read back as `{'answers': …}`. No schema change. 2 new tests on SQLite and PostgreSQL (both fail on the old adapter). Full pytest 832 passed on both; ruff clean. **Rule 8 early pass** (`db_adapter.py` touched): all 35 open items checked; only UPG-01 is affected. |
| 2026-10-08 | "UPG-01: …" (parent `2a69b17`) | UPG-01 | **UPG-01 DONE.** One normaliser, used by `_get_form`, gives every stored form field an id (else its `field_name`) and prepends full name, email, phone and USN once unless the form already asks for them. So template forms made by API v1's `instantiate_event` and the seeded events render named inputs and ask for identity, without rewriting stored data. Saving a form with an unnamed input field returns 400. Criterion 2 found UPG-45 (built first). 10 new real-database cases (all fail on the old code), including every template and the seeded conference registered end to end. Full pytest 842 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-08 | "UPG-34: …" (parent `2fb6e01`) | UPG-34 | **UPG-34 DONE.** One check, `routes_forms.registration_closed` (status and deadline), used by the registration page, `/forms/submit` (which missed the deadline and pending approval) and the legacy `/participant/public_register`, which now refuses closed events before creating anything. The public event page's Register buttons link to the event's own form; its bypassing modal form is removed. 7 new real-database cases (6 fail on the old code). Full pytest 849 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-08 | "UPG-08: …" (parent `98c3556`) | UPG-08 | **UPG-08 DONE.** Teams live on the registration. The form adds team name and member rows from the event's limits, and the server enforces team size (refusing extra member fields and duplicate emails). A team registration gets an invite code; `/teams/join` adds the student to its members (refusing full teams, closed events and people already registered). The lead removes members and replaces the code; members can leave; the team page shows the roster and ticket. The separate `teams` collection is no longer used. 6 new real-database cases (5 fail on the old code). `test_student_registers_for_free_team_event_and_spoc_checks_in` registered one person for a 2–4 team event, which the item now refuses; its form gained a second member, assertions unchanged. Full pytest 855 passed on SQLite and PostgreSQL 16; ruff clean. |
| 2026-10-08 | "UPG-30: …" (parent `f5ae29d`) | UPG-30, UPG-31, UPG-16, Rule 8 | **UPG-30 built; IN PROGRESS** until the owner's checkout in Razorpay test mode (criterion 4). Built: a receipt email after payment; capacity re-checked at completion, and a paid order that can't complete stays paid with its reason, the payer told it's recorded; a signed `payment.captured` webhook completing the stored registration once, whichever of webhook and browser arrives first; the admin's payments page listing paid orders with no registration, with a confirmed, once-only Razorpay refund; mark-refunded and cancel on paid registrations, audit-logged, which check-in then refuses; a one-row-per-payment finance export. `payment_orders` gains five columns (schema check for existing databases; UPG-16 updated). **Found:** the paid flow's ticket email and WhatsApp receipt tasks call their senders with the wrong arguments, so neither is sent; added to UPG-31. 12 new real-database cases with Razorpay mocked (all fail on the old code). Full pytest 867 passed on SQLite and PostgreSQL 16; ruff clean. **Rule 8 early pass:** only UPG-16 is affected (updated). |
| 2026-10-08 | "UPG-36: …" (parent `caaa317`) | UPG-36, UPG-16, Rule 8 | **UPG-36 DONE.** An order with a coupon now holds a use from the moment it's created, taken with one conditional UPDATE on a new `coupon_uses` counter (coupons themselves are schemaless documents). No use left means the payer is told and can pay full price. Unpaid holds expire after `COUPON_HOLD_MINUTES` (30) and give the use back once; a payer's retry gives back their earlier hold; an expired order paid late takes a use again or is kept for the admin, never lost. 4 new cases (all fail on the old code), including 10 concurrent checkouts on PostgreSQL getting exactly 3 discounts. Full pytest 871 passed on PostgreSQL 16 and 870 + 1 skipped on SQLite; ruff clean. **Rule 8** (`models_pg.py`: a new table): only UPG-16 is affected; its baseline list now includes `coupon_uses`. |
| 2026-10-08 | "UPG-05: …" (parent `c35bd09`) | UPG-05 | **UPG-05 DONE.** Feedback opens after check-in, to the lead and the registration's team members (others 403), and each person answers once. Each answer is its own document; the lead's is still kept on the registration, and older responses still count. The summary pages now need `view_analytics` on the event: before, any SPOC or coordinator could read any event's feedback. A new CSV export (one row per response) needs `export_data`. The certificate's feedback rule asks each person. 7 new real-database cases (6 fail on the old code). Full pytest 878 passed on PostgreSQL 16 and 877 + 1 skipped on SQLite; ruff clean. |
| 2026-10-08 | "UPG-07: …" (parent `125f7f7`) | UPG-07, UPG-14, UPG-18, UPG-22, UPG-31, UPG-43, UPG-46, UPG-47 | **UPG-07 DONE.** An outside scheduler runs the scheduled jobs through `POST /internal/cron/<job>` (`reminders`, `lifecycle`, `cleanup`): 503 until `CRON_SECRET` is set, 403 for a missing or wrong `X-Cron-Secret` (constant-time compare), CSRF-exempt. Reminders send once per registration (existing `*_sent` flags). **The lifecycle job no longer deletes anything:** it used to delete every event 5 days after its date, with its registrations; now it closes registration after the deadline and moves past events to `completed`, through the audited workflow transition. The clean-up deletes expired sessions and login attempts older than an hour, nothing else. New `.github/workflows/cron.yml` (idle until `CRON_URL`/`CRON_SECRET` are set) and `docs/DEPLOY.md` (Cloud Scheduler set-up); `CRON_SECRET` added to `.env.example` and the deploy checklist. 5 new real-database cases (criteria 1–4 fail on the old code). Full pytest 883 passed on PostgreSQL 16, 882 passed and 1 skipped on SQLite; ruff clean. Recorded: the reminders and velocity alert look only at `active` events (UPG-43 criterion 4); UPG-31's ticket-email signature bug also breaks the day-before reminder; UPG-18's outbox job goes on this endpoint; UPG-22 owns any retention rule; UPG-14 must decide on `tests/test_event_maintenance.py`, which imports `scheduler_enhanced.py`. **New:** UPG-46 (scheduled emails link to a fixed `sapthaevent.in`), UPG-47 (events saved without times get the save time as start and end on the SQL layer). |
| 2026-10-08 | "UPG-31: …" (parent `f570f07`) | UPG-31, UPG-18, UPG-48, UPG-49, UPG-50 | **UPG-31 DONE.** The change and cancellation notices existed but never emailed anyone: their email channel imported `utils_email.send_email_notification`, which didn't exist. Added it (escaped, through Brevo first), so those notices, and API v1's automation emails, now go out. The ticket-email task's `event_date`/`venue` are now accepted, so paid registrants get their ticket email again; the receipt WhatsApp gets the payment ID; the missing day-before WhatsApp function exists. The day-before email carries the entry QR (the ticket page's signed token) under the ticket's ID. Change notices use a stable key (Python's `hash()` differs per process), and the coordinator's edit sends them too. 5 new real-database cases with Brevo's HTTP API mocked and outside connections refused (4 fail on the old code). Full pytest 888 passed on PostgreSQL 16, 887 passed and 1 skipped on SQLite; ruff clean. A first draft of the tests overwrote the existing `tests/test_notifications.py`; it was restored unchanged before any commit, and the new tests are in `tests/test_notices.py`. **New:** UPG-48 (team members get no notices), UPG-49 (automation WhatsApp channel), UPG-50 (email templates don't escape). |
| 2026-10-08 | "docs: …" (parent `1b7fd7c`) | ALL (re-verification at the end of Phase 2) | **Full re-verification of every open item (33), plus sections 1–4 (their citations in 2–4), against the code at `1b7fd7c`** (rule 8: 22 items DONE since the post-Phase 1 pass, BLK-16 and BLK-17 included; the count restarts at 0). Each citation was mapped from the commit that last wrote its line (`git blame` on this file) to `1b7fd7c` by exact line alignment; every moved, changed or unresolved one was read, and the counts were re-run with one script on `986d108` and `1b7fd7c`. **Claims corrected:** UPG-17 (nothing live stores files any more: certificates are emailed and verified from the database since UPG-06, exports are streamed; criteria 3–4 have nothing to test; new decision D-5 proposes folding it into UPG-21; the uploads inventory row is now NOT USED); UPG-32 (`README.md` has no Railway/Render guide; `docs/DEPLOY.md` exists with the scheduled-jobs section); UPG-15 (walk-ins get no password since UPG-33; the `functions/` diff re-counted); UPG-13 (a second checklist label, `services_copilot.py:180`, was missed before); UPG-10, UPG-12 and the FDP row (the account helper's role is now a parameter that defaults to `Student`); UPG-20 (47 of 99 environment variables in `.env.example` by this pass's script, and `MAIL_FROM` isn't one); inventory rows for approval, the calendar feed, the registration form and the kiosk. **Counts updated:** UPG-19 (`.stream()` 27/27/13/7), UPG-23 (16 templates on the shared layout, 107 standalone), UPG-24 (Bootstrap 5.3.0 on 46), UPG-25 (70 templates with inline scripts; 483 handlers in 76), UPG-26 (24 templates load `global.js`). **UPG-14 gains** `tasks/export_tasks.py` and `tasks/webhook_tasks.py`, which nothing queues (the second is tested by `tests/test_tasks.py`, so rule 5 applies). **Line moves only:** UPG-04, 09, 10, 12, 14, 15, 16, 20, 25, 26, 30, 43, 46, 47, BLK-01 and 45 citations in sections 2–4. **Unchanged and still accurate:** UPG-11, 18, 21, 22, 27, 28, 38, 42, 44 (re-run [R]: an empty payment status still reads back `unpaid`), 48, 49, 50. **BLK-01** [R, read-only `git ls-remote`]: `master` at `8b72203` (PR #49 merged), the remote `production-ready` at `37c2a5c`, PR refs 1–49 (the same 47 old ones, plus #48 and #49 on the rewritten history). No status changes and no new items. Checks: see the Phase 2 summary. |
| 2026-10-08 | "docs: …" (parent `1b7fd7c`) | Phase 2 summary | **Phase 2 (event day) done, except UPG-30's criterion 4.** **DONE:** UPG-33, UPG-35, UPG-37, UPG-39, UPG-40, UPG-41, UPG-02, UPG-06, UPG-03, UPG-29, UPG-01, UPG-34, UPG-08, UPG-36, UPG-05, UPG-07, UPG-31; found and built during the phase: BLK-18, BLK-19, UPG-45. **Still open:** UPG-30 (built; waits on the owner's checkout in Razorpay test mode). **Opened during the phase:** UPG-42, UPG-43, UPG-44, UPG-46, UPG-47, UPG-48, UPG-49, UPG-50 (none scheduled yet; owner's call), and decisions D-4 and D-5 (both open). **Checks at the end of Phase 2 [R]:** full pytest 888 passed on PostgreSQL 16, and 887 passed with 1 skipped on SQLite (the PostgreSQL-only concurrency case); 689 at the start of the phase. CI's test command and environment in a fresh clone, with a Redis-protocol server (`fakeredis`'s TCP server, since this machine has no Redis): 887 passed, 1 skipped. ruff clean; CI's bandit command on the fresh clone: exit 0. **Waiting on the owner:** push `production-ready` (21 local commits; the remote is at `37c2a5c`) and open a pull request into `master` so CI runs; UPG-30's test-mode checkout; D-4; D-5; BLK-01's last criterion (GitHub Support, D-2). **Next:** Phase 3, starting with UPG-16. |
| 2026-10-10 | "docs: …" (parent `6b4fe41`) | Step 0: D-4, D-5, D-6, UPG-51 to UPG-57 | **Owner run prompt, Step 0.** `origin/master` holds PR #49 only (`37c2a5c`), so local `master` was not moved. `chore: keep generated proposals out of static/ and git` (`6b4fe41`) removed the generated proposals from `static/reports/` (servable by the website) and untracked them in `reports/`, ignored `static/reports/`, `reports/*.pdf`, `reports/*.docx` and the generated logo, moved `python-docx` to `requirements-dev.txt`, and cut `HANDOFF.md` to a pointer. **Decisions:** D-4 (contact address `events@your-university-domain`), D-5 (UPG-17 folded into UPG-21; UPG-17 → MERGED), D-6 (UPG-30 criterion 4 deferred to UPG-32 on a public test deployment). **New:** UPG-51 (refund all on cancellation), UPG-52 (atomic team join), launch checks UPG-53 (fake home-page hackathon), UPG-54 (Capacitor URL from `BASE_URL`), UPG-55 (Google and 2FA links; takes UPG-10 criterion 4), UPG-56 (coupon field at checkout); the matchmaker's `MOCK_STUDENTS` is already UPG-14 criterion 4. UPG-57 (placement drives) for Phase 6. Phases 3–7 reordered as the owner set; this run is development-only (rules 5 and 8 suspended; built items are BUILT (untested)). |
| 2026-10-10 | "UPG-43: …" (parent `932afdd`) | UPG-43 | **UPG-43 BUILT (untested).** One helper (`services_workflow.EVENT_DAY_STATUSES`, `is_event_day_status`) for the statuses an event runs in: published, registration open or closed, in progress, and the old `active`. Used by the coordinator scanner list and walk-in form, venue self check-in, the day-before and 3-day reminders; the velocity alert reads events still taking registrations. Judge dashboard left for UPG-04. ruff clean; app starts; existing cron, notice, check-in and coordinator tests pass on Python 3.11. |
