# SapthaEvent — Feature Review archive (done items and reference sections)

*Moved here from `docs/FEATURE_REVIEW.md` on 2026-10-20; nothing was deleted. The feature inventory, journey and event-type tables, decided decisions and every DONE / MERGED / DROPPED item are here. Open items, open decisions, the index and recent changelog are in `docs/FEATURE_REVIEW.md`; older changelog in `docs/archive/CHANGELOG.md`. Search with grep for one item rather than reading this whole file.*

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
- **[R]** means verified by running: a sandbox copy of the repo, no `.env`, no `serviceAccountKey.json`, `DATABASE_TYPE=postgres` code path through `db_adapter.py` on a throwaway SQLite file, seeded with `seed_all_roles_demo.py` + `seed_events_universal.py` (now `python seed.py --profile demo` and `--profile events`, UPG-15), then driven over HTTP as each role.
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
6. About 20 templates are never rendered, 3 blueprints are never registered, there are 2 parallel notification systems, 2 payment stacks, 13 seed scripts and a diverged copy of the whole app in `functions/saptha_app/` (UPG-14/15). *(2026-10-18: all resolved and tested; one seed command, `seed.py`, since UPG-15.)*

---

## 2. Feature inventory

Status: WORKING · PARTLY BUILT (says where it breaks) · NOT CONNECTED (code exists, no UI uses it) · MISSING.

| Feature | Status | Evidence | Notes |
|---|---|---|---|
| Home / event discovery / catalogue | WORKING [T, R at UPG-92] | `app.py:564-735`, `app.py:875-1030`, `templates/index.html`, `templates/public/_event_content.html`, `static/js/pages/index.js:72`, `university_info.py` | The home page shows live events (a "Coming up" list of the next open ones) and the university's real details from `university_info.py` (schools and programmes, highlights, official social accounts, contacts, links checked to open real pages); nothing invented. The old fake fallback hackathon is gone (re-verified at UPG-86). Clicking an event opens the event page's own content in a scrollable popup (UPG-92); registration's Back returns to the page the visitor came from. No AI chat widget since UPG-205 (owner, 2026-11-06); `/chatbot/ask` remains but nothing on the home page calls it [T]. |
| University calendar + event `.ics` | WORKING [R] | `app.py:1093`, `app.py:794` | Department-only visibility filter at `app.py:1011-1014`. |
| Personal calendar feed | WORKING [R at BLK-04b] | `app.py:1135-1210`, `services_accounts.py:143,149` | Own events when logged in; calendar apps use a signed, resettable per-user token; `?user=` is ignored (BLK-04). |
| Student sign-up / login | WORKING [R at UPG-35] | `routes_auth.py:272`, `routes_auth.py:66` | USN now persists (document shadow, `db_adapter.py` `extra_json`) [R at `1f4cdc8`]; it wasn't stored at `694c729`. Failed logins and reset requests answer the same for every email (UPG-35); sign-up still tells an existing email to log in. The role menu is Admin, SPOC, Event coordinator, Judge and Student only (UPG-197, UPG-204); Volunteer, IQAC coordinator and Department admin accounts can't choose their role on the page for now (the server still accepts it) [T]. |
| Google / Microsoft login | NOT CONNECTED [C] | `auth_oauth.py:32-135` | Login page has no link to `/auth/google` (`templates/login.html`). |
| 2FA (TOTP) | NOT CONNECTED [C] | `auth_2fa.py:42-155` | No template links to `/auth/2fa/*`. `totp_*` keys now persist [R round-trip at `1f4cdc8`]. |
| Event creation (SPOC) | WORKING [T, R headless at UPG-73] | `services_event_types.py`, `routes_spoc.py:224-540`, `templates/spoc/create_event.html`, `templates/spoc/review_event.html` | One 7-step wizard for 27 kinds of event in 8 groups (talks, competitions, cultural, sports, community, career, fests, custom), each with its own details; every event starts as a draft, is checked on a review page and published (or sent for approval) through the workflow; editing uses the same wizard; fees per participant group; fests hold sub-events (UPG-73, UPG-74). Step 6 is the registration form, saved as the SPOC's; "Also ask for" replaced by members' USN and phone (UPG-219). |
| Approval workflow (unit → admin) | WORKING [R] | `services_workflow.py:130-217`, `routes_admin.py:913` | Admin approval sets `published`; SPOC must still move it to `registration_open` (`published` is a closed status, `routes_forms.py:86`). |
| Registration form (custom fields) | WORKING [R at UPG-01; layout T at UPG-150] | `routes_forms.py:99-154`, `templates/public/registration_form.html` | Every form, template, seeded or SPOC-built, is normalised on read: each field has a name and the identity fields appear once. Answers are stored and shown on the responses page (UPG-45 fixed postgres mode). Since UPG-150 the page is a full-width form beside a sticky event summary, in numbered sections (participant, details, team with one block per member, declaration), with underlined fields. Since UPG-212 a form saved from the builder shows exactly the questions built: only name and email are added and always required, choices are checked against the options, and the SPOC chooses member USN and phone (`routes_forms.py:131`, `:196`, `:528`). The builder's title, description and question order are what the page shows; name and email stay first in both (UPG-216). A form made in step 6 of the wizard is exactly the one shown; catalogue questions are only suggested (UPG-219). |
| Form builder | WORKING [T, R at UPG-79] | `routes_forms.py:361-406`, `templates/coordinator/form_builder.html` | Only the event's owner (or admins) can edit the form; assigned staff can see responses (BLK-04). Back returns to the page that opened it; the page says which fields every form gets and what a team event adds; unsaved changes are guarded (UPG-79). The coordinator dashboard links coordinators to it, but they get 403 (UPG-68). |
| Auto-account on registration (no auto-login) | WORKING [R at BLK-02, T at UPG-97] | `services_accounts.py:41-80`, `routes_forms.py:613-726,1220`, `routes_auth.py:236` | Fixed by BLK-02: no path logs anyone in. Since UPG-97 (owner decision 2026-10-17), an existing account's email registers without logging in, changes no account, and is emailed a "Not you? Cancel this registration" link (it was "log in first" before). New emails get an unverified account and a one-time set-password link; no password is shown or emailed. Since UPG-33 the same goes for walk-ins and for staff and SPOC accounts someone else creates, and reset links work once. Since UPG-152 [T] a new account's registration is one email to the lead (the confirmation with the set-password link), set-password links last 48 hours and reset links 15 minutes, a registration account gets one reset email in its first 48 hours (then the organizer message), and organisers see each registration's login email status and can send a new link (`services_accounts.py:178-310`, `routes_coordinator.py:168`). |
| Waitlist | PARTLY BUILT [R at BLK-03, UPG-62] | `routes_forms.py`, `routes_waitlist.py:185-338`, `tasks/waitlist_tasks.py`, `services_ticket.py:139-217` | Promotion on a paid event holds the seat as `pending_payment` with a pay link (BLK-03); a free promotion now issues the same signed ticket as a normal registration and sends the promotion email with the canonical task arguments (UPG-62). Two promotion code paths remain (UPG-14). No SPOC UI link to `/waitlist/list`. |
| Paid registration (Razorpay) | WORKING in tests [R at UPG-30, T at UPG-94] | `routes_payment.py`, `services_payments.py`, `routes_admin.py:586-775`, `templates/payment/checkout.html` | Server-side price, recorded orders, single-use payment IDs (BLK-03). Since UPG-94: the order carries event, registration and payer with a unique receipt and asks for automatic capture. Verify confirms only when Razorpay says the order is paid (an authorized payment is captured) and otherwise waits for the webhook. The webhook also handles `payment.authorized`, `payment.failed`, `refund.processed` (dashboard refunds cancel the registration) and `refund.failed`, and needs https in production. The checkout page shows failure, cancellation and a retry on the page. `/admin/payments/orders` lists every order's status. A receipt email after payment. Capacity is re-checked at completion; a paid order that can't complete stays paid and is listed for the admin to complete or refund (Razorpay refund with confirmation). A signed `payment.captured` webhook completes registrations whose browser closed. Admins mark registrations refunded or cancelled, and those tickets stop checking in. Not yet run against Razorpay test mode (criterion 4). Cancelling a paid event offers "Refund all through Razorpay" (once per payment, failures retryable, emailed, audited; UPG-51, built, untested). |
| Stripe payments | REMOVED [T at UPG-14] | None (removed by UPG-14) | Removed in favor of Razorpay as the single payment provider. |
| Coupons | NOT CONNECTED in the UI [C] | `routes_coupons.py`, `services_payments.py:36-73` | `create_order` applies a coupon validated on the server if one is sent (BLK-03), but no template or JS sends one or calls `/coupons/*`. Since UPG-36 each order holds a use when it's created (race-free), so `max_uses` holds even when payers check out together. |
| Digital ticket page | PARTLY BUILT [R] | `routes_ticket.py:224-281` | New registrations open; the seeded registration shows "not your ticket" because `is_lead` reads `lead_email` (`routes_ticket.py:243`), which postgres mode returned as `leadEmail` at `694c729`. At `1f4cdc8` the key reads back correctly [R round-trip]; the page wasn't re-run. Re-run 2026-10-12 [R, SQLite dev seed]: the owner is sent back "not your ticket" again, because `to_dict()` returns only `leadEmail` (UPG-69). The page is restyled on the brand (UPG-63). |
| Camera QR check-in (coordinator, SPOC, HUD) | WORKING [R at UPG-02] | `routes_ticket.py:123-217`, `templates/coordinator/scan.html:238`, `templates/spoc/scan.html:454`, `templates/coordinator/scan_hud.html:340` | Every scanner posts the scanned ticket to `POST /ticket/api/checkin`: signed tokens only, assigned staff only (`can`, BLK-18), one payment rule (free/waived/paid in any case; a free event owes nothing), idempotent with the first check-in time, refuses another event's ticket and a ticket whose event is gone. Tested on the real database and against the page scripts; not yet driven with a phone camera. Scanner list shows events in every event-day status since UPG-43 (built, untested). With the SPOC's entry list on, a team not selected is refused: "Not on the entry list – no entry." (UPG-214, `routes_ticket.py:211`). |
| Manual check-in (SPOC list) | WORKING on event day [R at BLK-05] | `routes_spoc.py:481-555` | Locked until event date (intended). Names read back since BLK-09; BLK-05's journey test checks in through this route on the real database. |
| Kiosk check-in | WORKING in the root app [R at UPG-02] | `routes_checkin.py:236-349`, `templates/public/kiosk.html:700` | Login + coordinator role + `check_in` on the event; search returns no email or phone (BLK-12). Confirm after a name search uses the shared check-in (payment rule, "already checked in at HH:MM"); a USB scanner can scan tickets into the search box (UPG-02). Search results insert names with `innerHTML` (BLK-19). **The `functions/saptha_app` copy's kiosk has no login at all** (BLK-12); removed in Phase 5 (UPG-15, D-1). |
| Venue-QR self check-in | WORKING in the root app [R at BLK-12] | `routes_checkin.py:65-172` | Root app: needs the logged-in owner plus a signed venue code valid for 10 minutes (`routes_checkin.py:86-128`). Pinned on the real database by BLK-12. The `functions/` copy checks in by a typed email alone (removed in Phase 5, UPG-15, D-1). |
| Offline check-in (PWA queue) | WORKING in tests [R at UPG-02] | `static/js/offline-sync.js`, `templates/coordinator/scan_hud.html:13`, `static/sw.js:20` | The HUD queues scans in IndexedDB when offline (one entry per ticket) and replays them to the shared endpoint; repeats answer "already in". Run in Node against the live app, not yet in a phone browser. `/api/v1/.../checkin-batch` is JWT-only with no UI. The scan screen keeps the SPOC's entry list on the phone and turns away a team not on it while offline (UPG-214). |
| Coordinator assignment | WORKING [R at UPG-29] | `routes_spoc.py:1187-1250`, `:1253` (remove) | The owner assigns and removes coordinators from the dashboard; another SPOC gets 403. Removing ends access to registrations, exports and check-in (`tests/test_assignment.py`). |
| Judge assignment | WORKING [R at UPG-29] | `routes_spoc.py:1371-1430`, `:1253` (remove) | Writes `staff`; only on events the SPOC manages (BLK-17). Judges are listed and removable in the judges dialog; removing ends scoring. The judge dashboard lists events that are active, in progress or in evaluation [T at UPG-04]. |
| Judge dashboard | PARTLY BUILT [R] | `routes_judge.py:58-59` | Lists only events with status `active`; new workflow states never appear. |
| Judge scoring | PARTLY BUILT [R] | `routes_judge.py:158`, `templates/spoc/create_event.html:1117` | Criteria from the create form are objects; scoring crashes (`'dict' object has no attribute 'replace'` / 500) [R]. Works with string criteria [R]. |
| Rounds, lock scoring, advance round | WORKING [T at UPG-149] | `services_rounds.py`, `routes_spoc.py` round panel / lock / advance, `routes_coordinator.py` promote | One round service for the SPOC panel and the coordinator: "Round X of N" with a final round that publishes results, top N (ties go through) or a cut-off on the average score, every round kept in `round_history`, no stranded or double-advanced teams, one result email per person; judges score only the current round's teams; students see their round on the dashboard and ticket. |
| AI judge↔team matching | PARTLY BUILT [C] | `routes_ai_matching.py:87-116` | Reads `form_answers`/`team_name`, which persist since BLK-09/BLK-06 [R round-trip]; matching not re-run. |
| Results + public leaderboard | WORKING [T, R at UPG-84] | `services_leaderboard.py`, `routes_spoc.py:651`, `routes_live.py:27`, `routes_participant.py:258`, `routes_judge.py:360`, `routes_coordinator.py:426` | One ranking for every board, results publishing and exports: both score fields, 2 decimals, shared places for ties, cancelled and eliminated left out; the results page lists scored teams with unscored ones apart (UPG-84). |
| Certificates | WORKING [T at UPG-122 to UPG-141] | `services_certificates.py`, `services_certificate_runs.py`, `services_certificate_changes.py`, `services_signatories.py`, `certificate_pdf.py`, `routes_certificates.py` | One `certificates` table (migration 0008). Every type (participation, completion, extension hours, winner, runner-up and other places from published results, merit, volunteer, coordinator, organiser, judge, speaker) for the people owed it (Present, the multi-day minimum, each team member); one per person, event and type, enforced by the database. Two templates with the college's branding, Kannada and Devanagari fonts, 1–3 signatories per event with private signature images, a random number and a QR code. Issued in the background in chunks (end-event, the bulk button, the certificate page, published results, the API) with progress and a retry, or by hand; each PDF stored privately with its SHA-256; one email with a signed, expiring link; "My certificates" with PDF, LinkedIn image and share link; corrections as new versions; revocation; lists, exports and college-wide counts; all audit-logged. The participant guard checks event completion before attendance (UPG-62). Since UPG-206 an event can use its own uploaded design (A4 PNG, JPG or one-page PDF, stored privately) for its attendance certificate: the organiser drags the name box (and optional team, USN and college boxes) on it, the app writes the names, the number and a small QR, no signatory needed for that type; each certificate keeps the design it was issued with [T]. |
| Certificate public verification | WORKING [T at UPG-126, UPG-127, UPG-134, UPG-135] | `routes_verification.py`, `templates/certificates/verify.html` | `/verify/<number>` shows valid, revoked (with the date) or replaced, with the name, event, dates, type and college and no personal data; a PDF can be checked against its versions; `SUPPORT_EMAIL` shown; rate-limited. Older IDs (`verified_certificates`, registration IDs) keep their legacy pages; API v1 verifies from the same table (UPG-137). |
| Feedback | WORKING [R at UPG-05] | `routes_feedback.py`, `routes_participant.py:290-340` | Opens after check-in; each attendee (lead or team member) answers once; the event's staff see the summary and export it (others 403). An optional rule requires each person's feedback before their certificate. |
| Hackathon submission + kanban | WORKING (page load) [R] | `routes_hackathon.py:20-206` | Pipeline and project pages are public (`routes_hackathon.py:107,137`). Submitting should be refused [C]: the form posts without a CSRF token (UPG-66). **Since 2026-11-05:** the SPOC's hackathon page `/spoc/hackathon/<id>` (problem statements released now or at a set time, a submission form the SPOC builds with an opening time, a deadline and extensions, the submissions) and the team's page `/hackathon/<id>` (stages, countdowns, updates, team, WhatsApp link, the form; a 60-second poll), `services_hackathon.py`, `routes_hackathon.py:263-489` (UPG-190, UPG-191, UPG-196 [T]). The old fixed form redirects there once a form exists. |
| Teams (create/join by code) | WORKING [R at UPG-08] | `routes_teams.py`, `routes_forms.py:156-225` | A team is one registration: the form asks for members within the event's limits, others join with the lead's invite code, the lead removes members and replaces the code; tickets, judging and check-in read its members. Joining is atomic on PostgreSQL since UPG-52 (built, untested). Since UPG-207 each member the lead lists gets one link to confirm and set a password (or sign in), so they have their own login and see their own certificate; the lead sees Confirmed / Waiting, resends (3 a day) and corrects an email; invite-code joiners are confirmed; organisers send links to earlier teams and switch it off per event [T]. The hosting SPOC cancels a team, with a reason, until it is checked in (UPG-211). |
| Agenda / sessions | WORKING [T at UPG-159] | `routes_spoc.py:1021`, `services_sessions.py`, `routes_ticket.py:269`, `routes_participant.py:1010-1034` | Sessions with room, seats and hours; session check-in from both scanners; "My agenda" with an `.ics`; per-session hours in the ledger; a column per session in exports (UPG-159). |
| Announcements | not run [C] | `routes_spoc.py:696-771` | — |
| Email (Brevo / Resend / Gmail) | WORKING in tests [R at UPG-31, UPG-62] | `utils_email.py`, `tasks/email_tasks.py:82-96`, `routes_auth.py:473-478` | Confirmation, day-before ticket with the entry QR, and change and cancellation notices go through Brevo once each (`tests/test_notices.py`, HTTP mocked); not yet sent through a real Brevo account. Notices reach only the registration's lead (UPG-48); since UPG-152 every automated email does, team members only when `NOTIFY_TEAM_MEMBERS` is on. Every email counts, one per recipient, against `EMAIL_DAILY_LIMIT` (default 450 a UTC day, shared by all instances in the `email_quota` table); at the limit nothing is sent (`services_email_quota.py`, `utils_email.py:506-522`, UPG-152 [T]). Link tokens are redacted from the app's and gunicorn's logs (UPG-152). Every link in an email comes from `BASE_URL`, never the request's host (BLK-16). The generic task uses `body_text` and accepts the legacy `body` alias for older callers (UPG-62). No built-in sender or password: the sender is `MAIL_FROM`, else `MAIL_USER`; with neither, Brevo and Resend refuse to send (UPG-41). The SPOC blast email's `spoc_id` gate (`routes_spoc.py:972`) passes for the owner since BLK-09; not re-run. **Since 2026-11-05:** a hackathon is portal-only by default: participants are emailed at registration (with the WhatsApp group and the hackathon page), for passwords and for the final result to the lead; every other sender checks `services_hackathon.email_allowed` and posts a portal notice or an update instead (UPG-195 [T]). The blast still puts the SPOC's text into the HTML unescaped (UPG-200). A backup Brevo account (`BREVO_BACKUP_API_KEY`) sends past the main account's limit (UPG-224). |
| WhatsApp (Twilio) | not run [C] | `utils_whatsapp.py` | Needs a paid Twilio sender. The day-before reminder and the payment receipt tasks call their functions correctly since UPG-31; the automation's WhatsApp channel still doesn't (UPG-49). |
| In-app notifications | WORKING [T at UPG-14] | `routes_notifications_v2.py:22-150,283-350`, `static/js/notifications.js` | One system, `notifications_v2`: a notification from `create_notification` shows in `/notifications/feed`, which the bell on every app-layout page loads (only the user's own); `mark_read` and bulk operations; v1 removed. |
| Scheduled reminders / lifecycle | WORKING [T at UPG-07] | `routes_cron.py:45`, `tasks/scheduled_tasks.py:534`, `.github/workflows/cron.yml`, `docs/DEPLOY.md` | Self-hosted, Celery beat runs them (`docker-compose.yml`); on a single web service, Cloud Scheduler or GitHub Actions calls `POST /internal/cron/<job>` with a shared secret. The lifecycle closes registration and completes past events, and no longer deletes anything. The reminders read every event-day status since UPG-43 (built, untested); the ticket-email signature was fixed in UPG-31. |
| Registration exports (CSV/Excel) | WORKING [R at UPG-03] | `services_export.py`, `routes_spoc.py:346,355`, `routes_coordinator.py:523,533`, `routes_admin.py:285` | One export for SPOC, coordinator and admin: lead name, USN, department, year, email, phone, team, members (each with "[Confirmed]" or "[Waiting]" when member confirmation is on, UPG-207), attendance, payment, amount, score, rank, certificate ID. 403 without `export_data` on the event. Department and year are inferred from the profile, form or USN when not asked. Since UPG-222: the lead's USN and phone also from a hand-added question or the account, department and year from the university's USNs, each member's own columns, and a column per form question. |
| Admin dashboard / analytics / report | WORKING [T, R at UPG-83] | `routes_admin.py:44,143`, `routes_spoc.py:630`, `services_insights.py`, `templates/analytics/hub.html`, `static/js/se-echarts.js` | Analytics for the Super Admin (every event) and SPOCs (their events): period and category filters, an adjustable comparison of every event with a table view, trend, heatmap, funnel, revenue and no-shows on Apache ECharts; dashboards count real registrations (UPG-81, UPG-83). `/analytics` redirects by role. |
| Users page (Super Admin) | WORKING [R at UPG-40] | `routes_admin.py:429-467`, `templates/admin/users.html` | Lists every account with its role and whether it has set a password; resends the set-password link to accounts still waiting (not to Super Admins or accounts with a password), audit-logged. 25 a page with search since UPG-19 (built, untested). |
| Org units, scoped roles | WORKING [R at BLK-07] | `routes_admin.py:756-950` | Viewing never migrates; "Migrate roles" previews first, and migrated SuperAdmin and SPOC accounts keep access (BLK-07). |
| Venues, rooms, conflict check | WORKING [T at UPG-09] | `routes_admin.py:957-1153`, `routes_spoc.py:244-253,292-314`, `services_workflow.py:190-235,287-296` | Admin CRUD page loads [R]. The create form's room picker refuses a room with a confirmed overlapping booking and books a free one tentatively; approval confirms it; the calendar shows the room name (`tests/test_venue_booking_on_create.py`). Edit and publish also check. |
| Student portfolio `/u/<usn>` | WORKING [R at `1f4cdc8`] | `routes_portfolio.py:27` | Shows the right student; at `694c729` the ignored `usn` filter showed the Super Admin. |
| XP / gamification leaderboard | not re-run [C] | `routes_gamification.py` | `xp`/`badges` now persist [R round-trip at `1f4cdc8`]; leaderboard not re-run. |
| Referrals | not re-run [C] | `routes_referrals.py:39` | Filters on document-only fields now apply (`tests/test_db_documents.py:95`); referral page not re-run. |
| Teammate matchmaker | Hidden [T at UPG-14] | `routes_matchmaker.py:12-16`, `config.py:233-236` | Suggests hard-coded `MOCK_STUDENTS`, so it answers 404 unless `FEATURE_MATCHMAKER=true`. |
| Online exams / proctoring | PARTLY BUILT [R at `1f4cdc8`] | `templates/spoc/proctor_monitor.html:1` | SPOC proctor page now 200 [R]; exam flow not run. Submitting should be refused [C]: the form posts without a CSRF token (UPG-66). |
| Privacy (DPDP export/delete/consent) | WORKING [T at UPG-22] | `services_privacy.py`, `routes_compliance.py`, `templates/profile/dashboard.html` | Consent (time and notice version) required at registration and sign-up; own-data download and account deletion (30-day grace, then anonymised by the cron clean-up) from the profile page; privacy notice linked in the shared footer. Retention of payment and audit records: D-7. |
| Audit log | WORKING [R at BLK-06a] | `utils.py` `log_action`, `templates/admin/audit_log.html` | The page shows the actor again (reads the document's `user` key, now preserved). The SQL `actorEmail` column holds the acting user since BLK-06a [R]. |
| REST API v1 (JWT) + multi-tenant control plane | NOT CONNECTED [C] | `routes_api_v1.py` | Only the AI copilot endpoints are called from a template. Finance, analytics, evaluation, certificate and control-plane services are used only here. |
| AI copilot (admin) | not run [C] | `routes_api_v1.py:1466-1507`, `auth_jwt.py:212-242` | Session fallback exists; no Gemini key in sandbox. |
| Android app | Webview wrapper [T at UPG-54] | `capacitor.config.json`, `scripts/configure_capacitor.py` | Server URL derived from `BASE_URL` at build time; `allowNavigation` restricted to host; documented in `docs/DEPLOY.md` (UPG-54). |
| Payment failure page | WORKING [R at `1f4cdc8`] | `templates/payment/failed.html:1` | Now extends `base_classic.html`; 200 [R]. |
| Login rate limiting | WORKING [R at BLK-13] | `services_login_throttle.py`, `routes_auth.py:83-86,337-341`, `routes_api_v1.py:62-88` | 5 failed logins (web + API, one counter) or reset requests per IP and per account per minute, and 20 failed logins per account per hour (UPG-37), then 429 "try again in N seconds"; counters in the database (Redis if `REDIS_URL`), shared by every instance (BLK-13). The old in-memory helpers in `security_middleware.py` are unused (UPG-14). |
| Sessions | WORKING [R at BLK-08] | `session_store.py`, `config.py:49-64` | In the database (Redis if `REDIS_URL`): survive restarts, shared by instances, none for plain anonymous page views (BLK-08). |
| Database migrations | WORKING [T at UPG-16, on SQLite and PostgreSQL] | `migrations/versions/0001_baseline.py`, `db_pg.py:186`, `db_adapter.py:1847` | One baseline builds an empty PostgreSQL or SQLite database; production start-up issues no DDL and refuses a database not at head; development still aligns at start-up. `docs/DEPLOY.md` has the step (UPG-16). |
| File uploads (certificates, exports) | NOT USED by the app; helper fixed [T at UPG-21] | `utils_storage.py` | Nothing live stores files (UPG-06, UPG-03). Since UPG-21 (UPG-17 folded in): `S3_ENDPOINT_URL` for Supabase Storage, private uploads with 15-minute signed links for exports, and no silent local fallback in production. |
| Background jobs | WORKING [T at UPG-18] | `celery_app.py:33`, `services_outbox.py` | Without a Redis broker, each task runs inline once under a timeout; failures and timeouts go to the `outbox` table, retried by `POST /internal/cron/outbox` with backoff (UPG-18). Scheduled jobs run through the cron endpoint since UPG-07. |
| Health check | WORKING [T at UPG-20] | `app.py:522-560` | `SELECT 1` (or one document read in Firestore mode); 200 or 503 with no error text (UPG-20). |
| Error monitoring (Sentry) | WORKING [T at UPG-20] | `app.py:102-125`, `utils_logging.py` | On when `SENTRY_DSN` is set, no personal data, release = Cloud Run revision; documented in `.env.example`. Logs are JSON lines with `severity` in production (UPG-20). |
| Database backups | WORKING [T at UPG-21: backup and restore on PostgreSQL] | `scripts/backup_db.sh`, `scripts/restore_db.sh`, `.github/workflows/backup.yml` | Daily `pg_dump` to a private bucket with 30-day retention; restore into an empty database only; documented drill in `docs/DEPLOY.md` (UPG-21). |
| Pagination on web lists | WORKING [T at UPG-19] | `utils_pagination.py`, `templates/includes/pagination.html` | 25 a page with search on users, audit log, payments, the admin/SPOC/coordinator dashboards' events, event registrations and form responses; page and filters in the URL; users and the audit log page in SQL (UPG-19). |
| Shared page layout | WORKING [T at UPG-23] | `templates/layouts/document.html`, `templates/base_classic.html` | Every template a route renders extends the shared document (app layout, standalone or full-screen child); only unrendered templates remain standalone (UPG-15) (UPG-23). Since UPG-63 (built, untested), signed-in pages use one app bar, page head and flash (`templates/base_classic.html`, `templates/includes/ui.html`), and status pages use `templates/layouts/status.html`. |
| Portal design system | WORKING [T at UPG-63; 375px checks at UPG-23, UPG-28] | `static/css/global.css` (v9), `static/js/chart-theme.js`, `docs/FRONTEND_CHECKLIST.md` | One navy-and-gold token set, light by default with an optional dark theme, one heading and one body font, shared components, and a validated chart palette. Every rendered template is on it (56 rebuilt on the app/status layout, 49 restyled in place). Checked at 1280px and 360px for every role (UPG-63). |
| Super Admin control centre | WORKING [T at UPG-75] | `routes_admin.py:1588-1920`, `templates/admin/{events,user_detail,registrations,system}.html` | Every event (approvals, any workflow status, hand to another SPOC), every account (add any role, edit role/department/category, deactivate; login refuses deactivated accounts), every registration (search, attendance, cancel), system status (integrations yes/no, failed jobs, retry), announcements in the app; dashboard "needs attention" (UPG-75). |
| Coordinator view (Super Admin) | WORKING [T, R at UPG-80] | `routes_coordinator.py:80-125`, `templates/coordinator/dashboard.html` | Labelled "Coordinator view · Seen as Super Admin" with a way back to the admin dashboard; counts real registrations. Events are created only in the wizard; the old coordinator form and route are retired (UPG-78). |
| Profile photos | WORKING [T at UPG-71] | `routes_profile.py:119-221`, `static/img/avatars/`, `templates/profile/dashboard.html` | Every role can upload a photo (validated and re-encoded as a 512px WebP) or choose one of 8 brand avatars; shown in the app bar and on the profile; a Google/Microsoft photo is used when nothing was chosen (UPG-71). |
| Ticket types (early bird, seats per type, team or per-head price) | WORKING [T at UPG-155] | `services_ticket_types.py`, `services_payments.py:101-119`, `routes_payment.py:428-450` | Chosen on the form, priced at checkout, seats taken race-free; exports show the type. |
| Apple / Google Wallet passes | WORKING in tests, off until keys are set [T at UPG-156] | `services_wallet.py`, `routes_ticket.py:484,498` | Not tried with real Apple or Google accounts. |
| Browser push notifications | WORKING in tests, off until VAPID keys are set [T at UPG-157] | `services_push.py`, `routes_push.py`, `static/js/push-optin.js` | Copies of reminders, changes and results; never replaces an email. |
| Name badges | WORKING [T at UPG-158] | `services_badges.py`, `routes_ticket.py:457,468` | Sheets of 8 and a single badge after a scan; no phone or email. |
| Live polls and Q&A | WORKING [T at UPG-160] | `services_interact.py`, `routes_interact.py` | Checked-in attendees only; projector over SSE; results in the event report. |
| Ticket transfer | WORKING [T at UPG-161] | `services_transfer.py`, `routes_participant.py:1048`, `routes_ticket.py:42-65` | Off by default; the `tickets` record isn't moved yet (UPG-189). |
| Share links and registration sources | WORKING [T at UPG-162] | `services_share.py`, `routes_spoc.py:2494-2535` | Only the code is stored; unknown codes are "other". |

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
| Pay | **Works in tests** (BLK-03, UPG-30, UPG-94) | Charged at the server's price; confirmed only when Razorpay says the order is paid; a receipt email; a webhook completes payments whose browser closed; a failed or cancelled payment says so on the page, keeps the form and offers a retry; refunds and failed refunds arrive by webhook; a paid order that can't complete stays paid for the admin to complete or refund. Not yet run against Razorpay test mode (UPG-30 criterion 4). |
| Ticket | OK for new registrations [R] | QR hidden until 1 day before (intended, `routes_ticket.py:143-152`). The day before, the ticket email brings the same QR, and a WhatsApp reminder goes out (UPG-31, through UPG-07's cron). Changes of date, time or venue, and cancellation, are emailed once. No payment reference stored. |
| Check-in | **Works** [R at UPG-02; entry list T at UPG-214] | The ticket's QR is accepted by every scanner; see Coordinator. When the SPOC turns on the event's entry list (UPG-214), only selected teams get in, by every way in, and the team is never told. |
| Attend sessions | Not found | No session-level attendance. |
| Submit work (hackathon) | Page loads [R] | — |
| See results | OK [R] | Names read back since BLK-09 [R round-trip]. |
| Feedback | **Works** [R at UPG-05] | Every checked-in attendee, team members included, answers once; the SPOC dashboard links the summary and its CSV export. |
| Certificate | **Works** [T at UPG-125, UPG-132, UPG-138, UPG-207] | "My certificates" lists each certificate with its PDF, a LinkedIn image and a share link (a team member listed by the lead signs in after confirming their email, UPG-207); the certificate page links the PDF; it's emailed (a signed link) when issued, and `/verify/<number>` confirms it. Fits a 375px phone. |
| Portfolio | **Fixed** [R at `1f4cdc8`] | `/u/<usn>` shows the right student. |

### SPOC / organiser

| Step | Result | Where it breaks |
|---|---|---|
| Create event (seminar / hackathon / sports) | Created [R] | All settings persist since BLK-09 [R]. Sports fixtures & standings generated on tournament page (UPG-13, tested). Since UPG-73: every kind of event, saved as a draft, then reviewed and published. |
| Build form | Page OK [R] | — |
| Publish (pending → approve → open) | OK [R] | Two steps after approval; not obvious from the UI copy. |
| Manage registrations / waitlist | Partly [R] | Exports work since UPG-03 (CSV and Excel with every column); no waitlist screen. |
| Assign coordinators / judges / rooms | Judges and coordinators: assign and remove [R at UPG-29]; rooms not re-run | Tested end to end (`tests/test_assignment.py`). |
| Run the day | QR scans and the manual list [R at UPG-02] | Scans go through the shared check-in; the manual list still uses its own route (UPG-14); the blast email's `spoc_id` gate (`routes_spoc.py:963`) passes for the owner since BLK-09 (not re-run). WhatsApp groups used instead. |
| Results | Publish OK [R]; lock/advance not re-run | Their `spoc_id` gates (`routes_spoc.py:1652,1673`) pass for the owner since BLK-09. |
| Certificates | **Works** [T at UPG-124, UPG-138] | Ending the event, the bulk button or the certificate page issues each person's certificates once, in the background through one path; position certificates when results are published. |
| Report | **Event report** [R at UPG-03] | One click on the SPOC dashboard: registered vs present by department and year, feedback average, winners (Excel). The AI report still needs a Gemini key. |

### Coordinator / volunteer

| Step | Result | Where it breaks |
|---|---|---|
| Get assigned | OK [R at UPG-29] | The event appears on the coordinator's dashboard; removal by the SPOC ends access (`tests/test_assignment.py`). |
| Scan tickets | **Works** [R at UPG-02] | Coordinator, SPOC and HUD scanners and the kiosk use `POST /ticket/api/checkin` (`tests/test_checkin_unified.py`). The scanner list and walk-in form show events in every event-day status since UPG-43 (built, untested). |
| Walk-ins | Works [R at UPG-33] | `routes_coordinator.py:549-632`; needs `manage_registrations` on the chosen event (BLK-04a). A new walk-in gets the ticket and a one-time set-password link, never a password (`tests/test_account_emails.py`). Registers differently from the online form (no event questions, team, seat limit or count; always Paid): UPG-221. |
| Attendance (granular) | **Fixed** (BLK-04a) [R] | `routes_coordinator.py:759-761` needs `check_in` on the event; students and unassigned coordinators get 403 (`tests/test_coordinator_authz.py`). |
| Offline | **Works in tests** [R at UPG-02] | The HUD queues scans offline and replays them to the shared check-in without duplicates (run in Node against the live app). |

### Judge

| Step | Result | Where it breaks |
|---|---|---|
| See assigned events | **Broken** for new workflow states [R] | `routes_judge.py:59` filters `status == 'active'`. Judge needs a direct link. |
| Score with rubric | WORKING with form criteria `{name, max_score}` and string criteria [T at UPG-04: `tests/test_rubric_judging.py`]; over-maximum scores refused | `routes_judge.py:158`. Only attendees marked Present are listed (`routes_judge.py:104-105`), so this depends on check-in. |
| Locking | WORKING [T at UPG-04] | Scoring after the SPOC locks it is refused with 403 `locked` (`tests/test_rubric_judging.py::test_scoring_after_the_spoc_locks_it_is_refused`). |
| Conflicts of interest | MISSING | No declaration or recusal found. |

### Super Admin

| Step | Result | Where it breaks |
|---|---|---|
| Departments / clubs (org units) | Works [R at BLK-07] | Viewing never migrates; migration previews first and keeps everyone's access (BLK-07). |
| Approvals | OK [R] | — |
| Users / roles | Role assignment page OK [R]; `/admin/users` lists accounts and resends set-password links (UPG-40) [R]; the dead `/admin/events` link is gone from every template [C at `986d108`] | Every internal link, form action and fetch URL in the templates and scripts reaches a route [T at UPG-15]. |
| Calendar | OK [R] | — |
| Analytics / exports | Pages OK [R]; exports not re-run | Names read back since BLK-06 [R round-trip]; UPG-03. |
| Bulk student import | WORKING [T at UPG-10; CGPA and backlog columns at UPG-57] | UPG-10: SuperAdmin CSV roster import with USN, department, year, section; Google sign-in restricted to university domain. |

---

## 4. Event-type coverage

"Works today" is in postgres mode as verified at `694c729`. BLK-09 (`1f4cdc8`) removed most of the BLK-06 field loss these rows depended on; re-check a row before relying on it. Re-checked 2026-10-02 at `986d108`: every BLK item named here is DONE, so "Needed" lists only UPG items.

| Event type | Works today | Done outside the app | Needed |
|---|---|---|---|
| Seminar | Create from template, approval, free registration (any form, UPG-01), ticket, QR and manual check-in (UPG-02), certificates (UPG-06), attendance export and event report (UPG-03), feedback (UPG-05), calendar; waitlist promotion issues a signed ticket and notification for a newly available free seat (UPG-62); Own type with speaker details (UPG-73) Since 2026-11-02: Live polls and Q&A for checked-in attendees (UPG-160); name badges (UPG-158); share links with sources (UPG-162). | — | — |
| Workshop | Same as seminar; preset applied (`routes_spoc.py:154`); Own type with trainer, prerequisites, what to bring (UPG-73) | Same; paid workshops: payments are verified safely since BLK-03 and confirmed with Razorpay since UPG-94, not yet run against Razorpay test mode | + UPG-30 |
| Guest lecture | Same as seminar (no own template); Own type (UPG-73) | Speaker invite and attendance list | Seminar items |
| Hackathon | Create, judges, project submission page, rubric scoring (UPG-04), leaderboard, QR check-in (UPG-02), winner and participation certificates (UPG-06), team registration with invite codes (UPG-08); Own type: duration, themes, judging criteria, rounds, prizes in the wizard (UPG-73); qualifying rounds with shortlists by top N or cut-off, round history, result emails and the student's round status (UPG-149); one email per new team registration, to the lead, under a daily email limit, with one-time password links (UPG-152); problem statements published after registration, now or at a set time (UPG-190); a submission form the SPOC builds, open between two times, editable until the deadline, with deadline extensions (UPG-191); participants emailed only at registration, for passwords and the final result, the rest on the team's hackathon page with stages, countdowns and updates (UPG-195, UPG-196); each listed member gets one link to confirm and get a login, so they see their own certificate (UPG-207); the college's own certificate design (UPG-206) | WhatsApp group (link in the registration email) | AI scoring of submissions (UPG-192), the SPOC's ranking and top-N shortlist (UPG-193), the finale and results email (UPG-194); UPG-198, UPG-199 |
| Sports | Create, registration (teams since UPG-08), leaderboard page, fixtures & standings: knockout and league, results by the SPOC or an assigned coordinator, public fixtures page (UPG-13, tested); tournament and fixtures pages on the design system (UPG-63); Tournament (sport, format, gender category), athletics and e-sports types; a sports meet is a fest with sub-events (UPG-73, UPG-74) | Whiteboard/Excel replaced | — |
| Cultural | Template exists (`services_templates.py:494`); judging as hackathon; certificates (UPG-06); Cultural competition (discipline, solo/group, time on stage) and show/concert types; a cultural fest holds them as sub-events (UPG-73, UPG-74) | Slots, judging sheets | — (rubric judging done, UPG-04) |
| Club activities | Org units can be clubs (`routes_admin.py:812`); Club activity type (UPG-73) | Membership lists, recurring meetings, attendance across the year | Membership not yet listed (activity points ledger done, UPG-11) |
| Placement drives | Company details, eligibility from the roster (branch, year, CGPA, backlogs) checked at registration, rounds with shortlist/reject notices and per-round exports (UPG-57, tested); Placement drive type with company and eligibility in the wizard (UPG-73) | Company communication | — |
| FDPs | Faculty-only events: faculty register with designation and institution (UPG-12, tested); hours credited in the ledger and the department export (UPG-11, tested); FDP type: faculty and external by default, resource persons, multi-day dates (UPG-73) Since 2026-11-02: Session check-in with hours per attended session in the ledger (UPG-159). | Faculty registration, multi-day attendance, hours on certificate | Completion certificates with the hours, designation and institution (UPG-130, UPG-131), issued through the one path (UPG-138) |
| NSS / NCC | Category kept as `NSS` / `NCC` since BLK-06a; NSS/NCC activity and social drive types with volunteer hours (UPG-73); hours register per student and department export (UPG-11, tested) | Unit rolls, hours certificates | Extension-hours certificates with the hours on them (UPG-122, UPG-130), issued through the one path (UPG-138) |
| Department events | Department-only visibility (`app.py:1011-1014`), unit approval [R]; "My department only" visibility in the wizard; listings respect it (UPG-73) | Same as seminar | Seminar items |
| Conference / webinar | Templates exist; their forms work since UPG-01 [R]; faculty and external participants register (UPG-12, tested); Own types; webinar is online with a meeting link shown to registrants (UPG-73) Since 2026-11-02: Session check-in and "My agenda" (UPG-159), polls and Q&A (UPG-160), badges (UPG-158), wallet passes (UPG-156), ticket types and transfers (UPG-155, UPG-161). | — | — |

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
- **Status:** DONE
- **Evidence:** `routes_judge.py:45-98,149,208-254,269-317,330`, `templates/judge/teams.html:177-275`
- **Last verified:** 2026-10-17, commit "UPG-04: …" on `production-ready` (parent `778f973`) [T]
- **To test later:**
  1. ✅ Test: criteria `[{"name":"Innovation","max_score":10}]` → `submit_score` stores 8 and the leaderboard shows 8. [T `tests/test_rubric_judging.py::test_a_rubric_score_is_stored_and_shown_on_the_leaderboard` (fails on the old code through the remarks bug)]
  2. ✅ Test: a score of 11 on a max-10 criterion returns 400. [T `::test_a_score_above_the_maximum_is_refused`]
  3. ✅ Test: an assigned judge's dashboard lists an event in `in_progress` and in `evaluation`. [T `::test_the_dashboard_lists_events_in_progress_and_in_evaluation`]
  4. ✅ Test: scoring after the SPOC locks it returns "locked". [T `::test_scoring_after_the_spoc_locks_it_is_refused`]
- **Problem:** The create form saves criteria as `{name, description, max_score}` (`templates/spoc/create_event.html:1117`). `submit_score` calls `c.replace` (`routes_judge.py:158`) and `score_inline` uses the dict as a key → errors / 500 [R]. The judge dashboard lists only `status == 'active'` (`routes_judge.py:59`), so events in `registration_open`, `in_progress` or `evaluation` never show up [R]. There's no max-score validation. The missing `abort` import in `routes_judge.py` (a pre-existing `master` bug, where an unassigned judge got a swallowed `NameError` instead of a 403) was **fixed in `4699478`** at the owner's request, as part of finishing BLK-09. It's pinned by `tests/test_integration_flow.py::test_unassigned_judge_gets_403_and_nothing_is_saved`.
- **Who benefits:** judges and SPOCs of every competitive event (hackathon, cultural, quiz); removes paper score sheets.
- **What to build:** a single criteria normaliser (strings or objects → `{name, max_score}`) used by every judge route and template; validate `0 ≤ score ≤ max_score`; the dashboard lists assigned events in any judging-relevant state.
- **Files touched:** `routes_judge.py`, `templates/judge/teams.html`, `routes_spoc.py` (results), tests.
- **Built (2026-10-17):**
  - **Tested in Part 2. Found and fixed:** `routes_judge.submit_score` read the remarks as `json_data.get('remarks').strip()`, so every JSON score without remarks failed ("'NoneType' object has no attribute 'strip'") and redirected to the dashboard with nothing saved. A missing remark now reads as empty.
- **Files touched:** `routes_judge.py`, `tests/test_rubric_judging.py` (new).
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
- **2026-10-19 (UPG-138):** the one issuing path is now `services_certificates` (UPG-122 to UPG-127); `utils_certificate.issue_event_certificates` is retired. This item's tests moved with it, check by check (`tests/test_certificates.py`); the one change of meaning is that winner certificates come from published results, not the top scores at the end (the owner's brief, UPG-122).

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
- **Status:** DONE
- **Evidence:** `routes_spoc.py:142-143,244-253,292-314` (moved by UPG-82's wizard rework; same behaviour), `templates/spoc/create_event.html:211-213`, `services_workflow.py:287-296`, `app.py:1126-1133,1168,1204`
- **Last verified:** 2026-10-18, commit "UPG-09: …" on `production-ready` (parent `813b0ee`) [T]
- **To test later:**
  1. ✅ Test: creating an event in a room already booked for an overlapping time → error, no event created. [T `tests/test_venue_booking_on_create.py::test_a_room_booked_for_an_overlapping_time_is_refused_and_no_event_is_made`]
  2. ✅ Test: approval turns the tentative booking into confirmed. [T `::test_approval_turns_the_tentative_booking_into_confirmed` (also: the confirmed booking then refuses a second event at that time)]
  3. ✅ The calendar shows the room name for the event. [T `::test_the_calendar_shows_the_room_name_for_the_event` (`/api/calendar` and `/calendar`)]
- **Problem:** Room conflict detection exists (`services_venue.check_room_conflict`), but it runs only on edit (`routes_spoc.py:1138-1144`) and publish (`services_workflow.py:190-218`). The create form has no room field (no `room_id` in `templates/spoc/create_event.html`), so clashes surface late and rooms are booked by email or phone.
- **Who benefits:** SPOCs, the estates/admin office, and anyone who double-books halls.
- **What to build:** a room picker with availability on create; a booking created as tentative on submit and confirmed on approval.
- **Files touched:** `routes_spoc.py`, `templates/spoc/create_event.html`, `services_venue.py`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built.** No bug found. Each check was confirmed to catch its regression: with the create-time conflict check removed, criterion 1's test fails; with the approval confirm removed, criterion 2's fails. Passes on SQLite and PostgreSQL 16. A tentative booking does not block another create; only confirmed ones do, and a clash between two tentative ones surfaces when the second one is published (the publish guard).
- **Files touched:** `tests/test_venue_booking_on_create.py` (new).
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: creating an event in a room already booked for an overlapping time → error, no event created.
  2. Test: approval turns the tentative booking into confirmed.
  3. The calendar shows the room name for the event.

### B. New features the university needs

#### UPG-10 — Student roster import and university Google sign-in
- **Status:** DONE
- **Evidence:** `routes_admin.py:461-572`, `templates/admin/users.html:23-45`, `auth_oauth.py:51-57,205-217`, `config.py:296-297`
- **Last verified:** 2026-10-17, commit "UPG-10: …" on `production-ready` (parent `0f7ce11`) [T]
- **To test later:**
  1. ✅ Test: uploading 3 rows creates 3 users with USN and department read back. [T `tests/test_roster_and_google_domain.py::test_a_roster_creates_students_and_a_second_upload_updates_them_in_place`]
  2. ✅ Test: re-uploading updates in place, with no duplicates. [T same test: the second upload changes one student's USN, department and name, and the three emails are still three accounts]
  3. ✅ Test: a Google callback with a non-university domain is rejected. [T `::test_google_sign_in_is_limited_to_the_university_domain` ×2: through `/auth/google/callback` with Google mocked, a gmail account is refused with no account or session, and a `snpsu.edu.in` one signs in]
- **Problem:** Accounts come only from self sign-up (`routes_auth.py:276-323`) or registration, which creates an unverified account since BLK-02 (`routes_forms.py:570-572`, `services_accounts.py:58`). There's no bulk import (not found). USN is now stored (fixed by BLK-09 [R round-trip at `1f4cdc8`]), but department and year are often blank, so department filters and reports are unreliable. OAuth routes exist, configured via `config.py:227-230`, but at `986d108` no template links to `/auth/google` or `/auth/microsoft`, and `auth_oauth.py` has no university-domain restriction [C].
- **Who benefits:** every student (one-click login) and every report that needs department/year.
- **What to build:** a SuperAdmin CSV upload (email, name, USN, department, year, section) that creates or updates users. Show a "Sign in with Google" button restricted to the university domain.
- **Files touched:** `routes_admin.py`, `templates/admin/*`, `auth_oauth.py`, `templates/login.html`, `config.py`, tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** Criterion 4 (the Google button) belongs to UPG-55.
- **Files touched:** `tests/test_roster_and_google_domain.py` (new).
- **Effort:** M · **Depends on:** BLK-06, BLK-02 · **Risk:** account merging for existing emails.
- **Acceptance criteria:**
  1. Test: uploading 3 rows creates 3 users with USN and department read back.
  2. Test: re-uploading updates in place, with no duplicates.
  3. Test: a Google callback with a non-university domain is rejected.
  4. The login page shows the Google button when OAuth is configured. *(2026-10-10: moved to UPG-55, which links Google sign-in and 2FA before launch; UPG-10 adds the domain rule.)*

#### UPG-11 — Participation ledger: activity points and NSS / NCC / FDP hours
- **Status:** DONE (criterion 4, the certificate, is UPG-130, DONE 2026-10-19)
- **Evidence:** `models_pg.py:64-65`, `migrations/versions/0005_activity_points_hours.py`, `services_event_types.py:481-482,543-544` (the wizard's fields since UPG-73), `routes_spoc.py:589` (SPOC export), `:1366` (edit), `services_ledger.py:12-17`, `services_export.py:221-319`, `routes_admin.py:209-213,243-263`, `routes_participant.py:859-947`, `templates/participant/ledger.html` (the certificate lines were reverted, see below)
- **Last verified:** 2026-10-18, commit "UPG-11: …" on `production-ready` (parent `74cc875`) [T]
- **Changed 2026-10-10 (owner's second run prompt, Step 0):**
  - **Credit once per registration.** Points and hours are worked out from the registration's current attendance by one helper, `services_ledger.credit_for`, used by the ledger page (`routes_participant.participation_ledger`) and the department export (`services_export.department_activity_data`, which already counts each registration once). Check-in no longer writes `activity_points_credited`/`activity_hours_credited` (nothing read them, and they went stale when attendance was undone). Checked by hand [R] on a temporary database: two scans of one ticket (the second answers "already in"), then attendance undone and redone: the ledger and the export show 5 points / 2 hours, one event, each time; 0 while undone.
  - **Certificate part reverted, deferred (owner, 2026-10-10):** the hours line on the certificate page and in the PDF (`templates/participant/certificate.html`, `utils_certificate.py`) is removed; criterion 4 waited until certificate work resumed, and is UPG-130 (DONE 2026-10-19).
- **To test later:**
  1. ✅ Test: an event worth 2 hours / 5 points credits a Present attendee and not an Absent one. [T `tests/test_participation_ledger.py::test_a_present_attendee_is_credited_and_an_absent_one_is_not` (also: a second scan credits nothing more)]
  2. ✅ Test: the ledger totals across 3 events are correct. [T `::test_the_ledger_adds_up_three_events` (5+3+10 points, 2+1.5+4 hours; a fourth event registered but not attended adds nothing; the page shows the same totals)]
  3. ✅ Test: the department export lists every student in the department with totals. [T `::test_the_department_export_lists_every_student_with_totals` (a student with no events is listed with 0; another department's student isn't)]
  4. ~~The certificate shows the hours when the event has them.~~ Certificate part deferred (owner, 2026-10-10); built and tested as UPG-130 (2026-10-19).
- **Problem:** MISSING. No points or hours fields exist anywhere (searched routes, services and templates for activity points, AICTE, NSS/volunteer/credit hours). Mentors and NSS/NCC officers keep these registers in Excel or on paper.
- **Who benefits:** every student (activity points), NSS/NCC units, faculty (FDP hours), IQAC.
- **What to build:** per-event points and/or hours set by the organiser; credited on attendance; a per-student ledger page; department/unit export; hours printed on certificates.
- **Files touched:** `models_pg.py` + migration, `routes_spoc.py`, `routes_participant.py`, `services_export.py`, `utils_certificate.py`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built; no change to the code.** Points and hours are set on the create form, a SPOC check-in credits them, an admin's "absent" doesn't, and a second scan doesn't credit twice. Breaking `credit_for` fails criteria 1 and 2's tests. Passes on SQLite and PostgreSQL 16. Criterion 4 stays deferred with certificates.
- **Files touched:** `tests/test_participation_ledger.py` (new).
- **Effort:** M · **Depends on:** UPG-02, BLK-06 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: an event worth 2 hours / 5 points credits a Present attendee and not an Absent one.
  2. Test: the ledger totals across 3 events are correct.
  3. Test: the department export lists every student in the department with totals.
  4. The certificate shows the hours when the event has them.

#### UPG-12 — Faculty and external participants (FDPs, guest lectures, conferences)
- **Status:** DONE (criterion 2, the certificate, is UPG-131, DONE 2026-10-19)
- **Last verified:** 2026-10-17, commit "UPG-12: …" on `production-ready` (parent `33b31af`) [T]
- **Problem:** Every registrant is created as `Student`: registration through `services_accounts.create_unverified_account` (its role defaults to `Student`, `services_accounts.py:59,66`; used at `routes_forms.py:571`), and sign-up at `routes_auth.py:306`. There's no faculty or external participant type (`utils.py:24-36`, `services_permission.py:53-80`), so FDPs and conferences can't be run for their real audience.
- **Who benefits:** HR/IQAC (FDP records), departments running FDPs and conferences, external delegates.
- **What to build:** `participant_type` (student / faculty / external) with designation and institution; the same participant dashboard; FDP certificate wording; analytics split by type.
- **Files touched:** `routes_forms.py`, `routes_auth.py`, `models_pg.py` + migration, `routes_participant.py`, `utils_certificate.py`, tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** Criterion 2 (certificate wording) was deferred with certificates; it is UPG-131 (DONE).
- **Files touched:** `tests/test_participant_types.py` (new).
- **Effort:** M · **Depends on:** BLK-02, BLK-06 · **Risk:** role checks assume `Student`.
- **What was built (2026-10-10, owner's second run; no certificate work):**
  - **Data:** `participant_type` (student / faculty / external), `designation` and `institution` on users and registrations (`models_pg.py`; migration `0006_participant_types`, which matches the models with 0 differences on PostgreSQL 16 and downgrades cleanly). `services_participants.py` holds the types, labels and helpers; records without a type are students.
  - **The event decides who may register:** "Who can register" checkboxes (students, faculty, external participants) on the SPOC's create and edit forms, stored as the event's `allowed_participants`; an event that doesn't say takes students only, so existing events behave as before.
  - **Registration form:** when the event takes more than students, it asks "I'm registering as" (or fixes the only allowed type) and shows designation and institution only for faculty and external participants (`static/js/handlers/public__registration_form.js` toggles them). The server refuses a type the event doesn't take ("This event is for faculty only.") and missing designation or institution, beside the fields (UPG-26). The registration stores the type and affiliation; a new account gets them too, with the set-password link and never a password (UPG-33); an existing account takes the type the first time it's given.
  - **Same journey as students:** the account keeps the participant role, so faculty and external participants use the same dashboard, ticket, check-in and feedback.
  - **Ledger and department export:** the department export (`services_export.department_activity_*`) includes faculty FDP hours, has a Participant Type column and a `?participant_type=` filter on the SPOC and admin export routes. The ledger page already works for any signed-in participant.
  - **Analytics and exports:** registration exports gain Participant Type, Designation and Institution; the event report has a "By participant type" sheet (registered and present); the admin analytics page shows registrations and attendance by participant type.
  - **Certificate part deferred (owner, 2026-10-10):** criterion 2 (FDP certificate wording with designation and institution) wasn't built then; it is UPG-131 (DONE 2026-10-19).
  - Checked by hand [R] on a temporary database: an FDP (faculty only) form fixes the type and shows the affiliation fields; a conference (faculty + external) offers two choices; a plain event doesn't ask; missing designation and a student registering for the FDP are refused with the reason; a valid faculty registration stores type and affiliation and creates a faculty account waiting for its set-password link, who opens the ticket and dashboard (200); exports, report sheet, the faculty-filtered department export (6 FDP hours) and the analytics table show the split. Export, form, team, journey, adapter and ticketing tests pass.
- **To test later:** criteria 1 and 3, plus the event's allowed types being enforced, the affiliation fields being required only for faculty and external, and the department export filter. Criterion 2 was deferred (certificates); it is UPG-131 (DONE).
- **Acceptance criteria:**
  1. ✅ Test: a faculty registration creates a user with `participant_type = faculty` who can open their ticket. [T `tests/test_participant_types.py::test_a_faculty_registration_makes_a_faculty_account_that_opens_its_ticket`]
  2. ~~Test: the FDP certificate shows designation and institution.~~ Certificate part deferred (owner, 2026-10-10); built and tested as UPG-131 (2026-10-19).
  3. ✅ Test: the admin analytics split counts by participant type. [T `::test_the_analytics_split_counts_by_participant_type` (exact counts from `services_insights.build`), `::test_the_admin_analytics_page_shows_the_split`]
  - "To test later" extras: `::test_the_events_allowed_types_are_enforced`, `::test_the_affiliation_is_required_only_for_faculty_and_external`, `::test_the_department_export_filters_by_participant_type`.

#### UPG-13 — Sports tournaments: fixtures, results, standings
- **Status:** DONE
- **Evidence:** `routes_sports.py:1-132`, `services_sports.py:1-192`, `templates/spoc/tournament.html:1-221`, `templates/includes/tournament.html:1-80`, `templates/public/tournament_fixtures.html:1-48`, `templates/public/event_details.html:541-546`, `templates/spoc/dashboard.html:1957-1961`, `app.py:320,347,946-976`
- **Last verified:** 2026-10-18, commit "UPG-13: …" on `production-ready` (parent `737d7be`) [T]
- **Problem:** The sports template promises "fixture brackets, live match score updates, point tables" (`services_templates.py:392-434`), but no model, route or template builds fixtures or standings. The only mentions are checklist labels (`services_event.py:63`, `services_copilot.py:180`; the second was missed before). Sports officers run tournaments on whiteboards and in Excel.
- **Who benefits:** Physical Education department, sports clubs, inter-department tournaments.
- **What to build:** a fixture generator (knockout and league) from confirmed teams; coordinator result entry; automatic advancement or points table; a public fixtures page.
- **Files touched:** new `routes_sports.py`, `services_sports.py`, `models_pg.py` + migration, templates, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built; no change to the code.** Through the routes on the real database layer: generate, results, schedule permissions and the public pages. Removing the result route's permission check, or stopping winners advancing, fails the tests. Passes on SQLite and PostgreSQL 16. Team ids in a tournament are the registrations' stored ids (the SQL layer keeps a registration id as a `uuid5` of the one given, `db_adapter.py:337`); the tests read them back rather than assume the id they wrote.
- **Files touched:** `tests/test_sports_tournament.py` (new).
- **Effort:** L · **Depends on:** UPG-08, BLK-06 · **Risk:** scope creep; start with knockout and league only.
- **What was built (2026-10-10, owner's second run; no certificate/medal work):**
  - **Team rosters:** `services_sports.confirmed_teams` pulls confirmed registrations for the event (teams with members since UPG-08 or individual participants).
  - **Fixture generation:** `services_sports.py` generates single-elimination knockout brackets (padding to next power of 2 with byes automatically settled) and round-robin leagues (circle method) with configurable win/draw/loss points (default 3/1/0).
  - **Match management:** SPOC or assigned coordinator (`routes_sports.py`) schedules match date, time, and venue; enters match scores and tie-break winners. Knockout automatically advances winners to next round until a champion is crowned; league dynamically computes the points table / standings (played, won, drawn, lost, goals for/against, goal difference, points).
  - **Public access:** embedded tournament bracket/table in public event details (`templates/includes/tournament.html`, `templates/public/event_details.html`) and dedicated public fixtures page (`templates/public/tournament_fixtures.html` at `/tournament/fixtures/<event_id>` and `/sports/fixtures/<event_id>`), both accessible without authentication.
  - **SPOC dashboard:** added "Sports Tournament: Fixtures & Standings" management action button in `templates/spoc/dashboard.html` for sports events.
  - **No certificate, medal or award documents built** (as directed).
  - Checked by hand [R] on temporary database: 5-team knockout generates 7 matches with 3 byes; entering results advances winner; 4-team league generates 6 matches and updates points table; public routes `/tournament/fixtures/<event_id>`, `/sports/fixtures/<event_id>`, and `/event/<event_id>` render with 200 without login.
- **To test later:** criteria 1–4.
- **Acceptance criteria:**
  1. ✅ Test: 8 teams → a knockout with 7 matches; entering results advances the winners to a single champion. [T `tests/test_sports_tournament.py::test_eight_teams_make_a_seven_match_knockout_with_one_champion` (a cancelled team isn't drawn; a tie goes to the chosen side; the public page names the champion)]
  2. ✅ Test: a 4-team league points table is correct after 6 results. [T `::test_a_four_team_league_table_is_right_after_six_results` (played/won/drawn/lost/for/against/points, ties broken on goal difference, the public table in that order; entered by the assigned coordinator)]
  3. ✅ Test: only the SPOC or assigned coordinator can enter results (unauthorized returns 403). [T `::test_only_the_spoc_or_an_assigned_coordinator_can_enter_results` (another SPOC, an unassigned coordinator and a student get 403 on results and the staff page; only the SPOC can generate, the assigned coordinator gets 403 there)]
  4. ✅ The public fixtures page renders without login. [T `::test_the_public_fixtures_page_renders_without_login` (also `/sports/fixtures/<id>` redirects there; the staff page needs a login)]

### C. Remove / merge

#### UPG-14 — Merge duplicate subsystems
- **Status:** DONE
- **Evidence:** `routes_notifications_v2.py:280-350`, `static/js/notifications.js:34`, `routes_matchmaker.py:12-16`, `config.py:233-236`, `app.py:315-395`, `scheduler_enhanced.py:1-170`, `tasks/waitlist_tasks.py:28-40`, git rm `routes_notifications.py`, `routes_payment_stripe.py`, `scheduler.py`, `tests.py`
- **Last verified:** 2026-10-18, commit "UPG-14: …" on `production-ready` (parent `12cb6ed`) [T]
- **To test later:**
  1. ✅ Test: a notification created with `create_notification` appears in the dashboard feed endpoint (`/notifications/feed`). [T `tests/test_merged_subsystems.py::test_a_created_notification_appears_in_the_dashboard_feed` (another user's notification isn't shown; the dashboard loads `notifications.js`, which fetches the feed)]
  2. ✅ Test: `/payment/stripe/create_session` → 404. [T `::test_stripe_checkout_is_gone` (GET and POST)]
  3. ✅ `grep -r "import scheduler" *.py` finds nothing and `pytest` passes. [T `::test_nothing_imports_the_old_scheduler_and_the_duplicates_are_gone` (no tracked file imports `scheduler`; `scheduler.py`, `tests.py`, the v1 notifications and Stripe routes aren't tracked); full suite 1087 passed, 6 skipped]
  4. ✅ Test: `/participant/matchmaker/` → 404 unless `FEATURE_MATCHMAKER=true` is set. [T `::test_the_matchmaker_is_404_unless_the_flag_is_on`, `::test_the_matchmaker_flag_comes_from_the_environment` (fail on the old code)]
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
- **Built (2026-10-18):**
  - **Tested in Part 2. Found and fixed:** the matchmaker's guard reads `FEATURE_MATCHMAKER` from the app config, but `config.Config` never set it, so the flag could not be switched on from the environment (criterion 4). `Config.FEATURE_MATCHMAKER` now comes from the environment (`config.py:233-236`), off by default.
  - **Not built, moved to UPG-112:** the rest of the problem list (`scheduler_enhanced.py`, the dead login throttling, the second waitlist promotion, unqueued tasks, other check-in paths). Several need the owner's decision because removing them deletes tests.
- **Files touched:** `config.py`, `tests/test_merged_subsystems.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a notification created with `create_notification` appears in the dashboard feed endpoint.
  2. Test: `/payment/stripe/create_session` → 404.
  3. `grep -r "import scheduler" *.py` finds nothing and `pytest` passes.
  4. Test: `/participant/matchmaker/` → 404 unless the feature flag is on.

#### UPG-15 — Delete dead code and fix dead links
- **Status:** DONE (criterion 5's check of the old Zoho deploy's walk-in accounts is the owner's)
- **Evidence:** `git rm` `functions/saptha_app/`, `catalyst.json`, `saptha-event-portal`, `routes_public.py`, `routes_head.py`, `routes_super.py`, `routes_api.py`, 17 unrendered templates; `app.py:300-335`, `templates/participant/my_events.html:143`; `seed.py`, `scripts/generate_vapid.py`, `git rm` `reset_system.py`, `run_alembic.py`, `scratch/` (26 files), redundant `seed_*.py` files
- **Last verified:** 2026-10-18, commit "UPG-15: …" on `production-ready` (parent `cddc491`) [T]
- **To test later:**
  1. ✅ Test: parse every template's internal `href`/`action`/`fetch` URL and assert each matches a rule in `app.url_map`. [T `tests/test_dead_code_and_links.py::test_every_internal_link_action_and_fetch_url_reaches_a_route` (749 URLs in templates and `static/js`, 184 of them templated; `::test_the_link_check_catches_a_dead_link` proves the check fails on dead ones); `::test_every_blueprint_in_a_route_module_is_registered`]
  2. Test: `git ls-files` lists nothing under `functions/saptha_app/`, `scratch/`, no `catalyst.json`, no `reset_system.py`, and no unregistered route blueprints.
  3. ✅ Test: `python seed.py --profile demo|events|scale` executes under `seed_safety.guard()`. Note: `test_seed_safety.py` scripts count assertion (`assert len(SCRIPTS) >= 25`) needs updating for consolidated seed structure. [T `::test_the_removed_copies_and_scripts_stay_gone` (fails before this change); `tests/test_seed_command.py` (demo, events and showcase profiles run; scale needs `DATABASE_URL`); `::test_every_seed_profile_is_behind_the_guard`, `::test_the_override_flag_reaches_every_profile` (fails before the guard fix)]
  4. Test: no tracked file sets a default walk-in password (`WALKIN_DEFAULT_PASSWORD`).
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
- **Built (2026-10-18):**
  - **Tested in Part 2.** Links, removed files, blueprints and the walk-in password were as built. The seed part wasn't: Phase 5 gave `seed.py` its profiles but left 10 `seed_*.py` scripts tracked, so criterion 3 failed. **Finished here:**
    - the four data sets `seed.py` runs moved, unchanged, into a `seeds/` package (`seeds/all_roles_demo.py`, `events_universal.py`, `scale_test.py`, `showcase.py`). Each still calls `seed_safety.guard()` first and is still checked by `tests/test_seed_safety.py` (its patterns now include `seeds/*.py`);
    - `seed.py --profile showcase [--summary FILE]` replaces `python seed_showcase.py` (UPG-88);
    - the six seeders no profile used are deleted: `seed_demo.py`, `saptha_full_seed.py` and `scripts/seed_events.py` (Firestore), `scripts/seed_emulator.py` (the Firebase SQL Connect emulator), `seed_data.py` and `seed_events.py`.
  - **Tests moved with the scripts, none weakened:**
    - `tests/test_seed_safety.py`'s Firestore-guard tests targeted `seed_demo.py`; they now target `setup_db.py`, which has the same guard and key loading.
    - Its count checks now read 13 scripts and 3 Firestore scripts, and name the four `seeds/` modules.
    - Its parametrized cases fell from 131 to 92 with the six scripts.
    - `tests/test_universal_seeder.py` and `tests/test_registration_forms.py` import `seeds.events_universal`.
  - **Found and fixed:** `seed_safety.guard()` takes `--i-know-this-is-production` out of `sys.argv`, so the guard a seed module runs when `seed.py` imports it refused again. That broke the override for the showcase profile (which worked as `python seed_showcase.py`), and in practice for demo and events too. The guard now remembers an override given on the process's own command line (`seed_safety.py:129-145`); an environment variable still can't stand in for it.
  - **Ran for real** on a throwaway SQLite database: demo (9 accounts, the flagship), events (+7), showcase (72 accounts, 48 events, 17 s).
  - **Found, not fixed (UPG-113):** bandit's two Medium B608 findings in the showcase seeder.
- **Files touched:** `seed.py`, `seeds/` (moved from `seed_all_roles_demo.py`, `seed_events_universal.py`, `seed_scale_test.py`, `seed_showcase.py`), `seed_safety.py`, `docs/DATABASE.md`, deleted `seed_demo.py`, `seed_data.py`, `seed_events.py`, `saptha_full_seed.py`, `scripts/seed_events.py`, `scripts/seed_emulator.py`; tests `tests/test_dead_code_and_links.py`, `tests/test_seed_command.py` (new), `tests/test_seed_safety.py`, `tests/test_universal_seeder.py`, `tests/test_registration_forms.py`.
- **Effort:** M · **Depends on:** none · **Risk:** low for deploys (nothing else deploys the copy, D-1).
- **Acceptance criteria:**
  1. Test: parse every template's internal `href`/`action`/`fetch` URL and assert each matches a rule in `app.url_map`.
  2. ✅ Test: `/debug-modal` → 404 (`tests/test_integration_flow.py:198`, `test_removed_debug_and_legacy_endpoints`, since BLK-09).
  3. `git ls-files` lists nothing under `functions/saptha_app/`, no `catalyst.json`, and no `seed_*.py` beyond the kept one. This also completes BLK-12 criterion 4 and BLK-14 criterion 3.
  4. ~~The Catalyst deploy still works via the build step (manual check).~~ Dropped: D-1 (owner, 2026-10-01) ends the Catalyst deploy, so there's no build step to check. Covered instead by criterion 3 (`catalyst.json` is gone).
  5. ✅ Walk-in accounts created on the Zoho deploy with the old default password have been forced to reset (owner check), and no tracked file sets a default walk-in password (test). [T `::test_no_tracked_file_sets_a_default_walk_in_password`; the owner's check of the old Zoho deploy remains]

### D. Production setup (added in Phase 0, 2026-09-30)

#### UPG-16 — Alembic baseline: build an empty database through migrations
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-16: …" on `production-ready` (parent `64c6eaf`) [T]
- **Problem:**
  - `migrations/versions/` isn't empty (the plan's prompt said it was): it has two tracked incremental migrations, `0001_add_org_units_and_scoped_roles.py` and `0002_add_campuses_buildings_rooms_bookings.py`. They assume the core tables already exist: `alembic upgrade head` on an empty SQLite database fails with `NoSuchTableError: events` [R at `56a014d`].
  - The real schema comes from start-up code in every environment, production included: `Base.metadata.create_all` (`db_pg.py:171-184`) plus `ALTER TABLE … ADD COLUMN` in `db_pg.py:197` and `db_adapter.verify_and_align_schema` (`db_adapter.py:201-326`, called at `:1856`). Column changes are never recorded, can't be reviewed or rolled back, and race when several instances start together.
  - **Added since Phase 0, which the baseline must include:** the tables `payment_orders` (BLK-03; with UPG-30's columns `regDataJson`, `failureReason`, `refundId`, `refundedAt`, `refundedBy`), `coupon_uses` (UPG-36), `flask_sessions` (BLK-08) and `login_attempts` (BLK-13); the column `events.spoc_id` and the new status enum members (BLK-06a); `extra_json` on eight more tables (BLK-06b). Re-run 2026-10-02 [R]: `alembic upgrade head` on an empty SQLite database still fails with `NoSuchTableError: events`.
- **Who benefits:** whoever deploys and operates the app; every schema change after this.
- **What to build:** one baseline migration matching `models_pg.py` (0001/0002 folded in, or rebased onto the baseline); start-up `create_all`/`ALTER TABLE` only in development; `alembic upgrade head` as a deploy step (a Cloud Run job or the container entrypoint before gunicorn), documented in `docs/DEPLOY.md`. Existing databases get `alembic stamp` instructions.
- **Files touched:** `migrations/versions/*`, `migrations/env.py`, `db_pg.py`, `db_adapter.py`, `Dockerfile` or a deploy script, `docs/DEPLOY.md`, tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** Each step runs in a subprocess with its own `DATABASE_URL`. The PostgreSQL steps create a fresh database on `TEST_DATABASE_URL`'s server and drop it afterwards; without PostgreSQL they skip.
- **Files touched:** `tests/test_migrations_baseline.py` (new).
- **Effort:** M · **Depends on:** BLK-06 (its column changes go into or on top of the baseline) · **Risk:** a baseline that differs from a database created by `create_all`; the comparison test guards it.
- **What was built (2026-10-10, development-only run):**
  - **One baseline migration**, `migrations/versions/0001_baseline.py`, generated by `alembic revision --autogenerate` against an empty PostgreSQL 16: every table in `models_pg.py`, including `payment_orders` with UPG-30's columns, `coupon_uses`, `flask_sessions`, `login_attempts`, `events.spoc_id`, the full status enums and every `extra_json`. Its downgrade also drops the six enum types on PostgreSQL. The old `0001_add_org_units_and_scoped_roles.py` and `0002_add_campuses_buildings_rooms_bookings.py` are folded into it and removed.
  - **Production start-up issues no DDL.** `SQLFirestoreAdapter.__init__` (`db_adapter.py:1847`) calls `init_db` and `verify_and_align_schema` only outside production; in production it calls `db_pg.require_schema_at_head` (`db_pg.py:186`), which compares Alembic's current revision with the code's head (`schema_revisions`, `:174`) and raises `DatabaseConfigError` naming the command to run.
  - `migrations/env.py` compares types on autogenerate and drops its dead `try` blocks; `migrations/README` points at the guide.
  - **`docs/DEPLOY.md`, "Database migrations":** the Cloud Run job that runs `alembic upgrade head` before deploying, why not in each container's start command, `alembic stamp 0001_baseline` for a database built by the old start-up, checking, rolling back and adding a change.
  - Checked by hand [R]: `alembic upgrade head` on an empty SQLite file and an empty PostgreSQL 16 database; `compare_metadata` reports 0 differences on PostgreSQL (on SQLite only UUID columns differ, because SQLite reflects `UUID` as `NUMERIC`); `downgrade base` then `upgrade head` on PostgreSQL, 0 differences; a production start-up on the migrated database loads `/` with 0 CREATE/ALTER/DROP statements; on an empty database it refuses with the message.
  - Not changed: `run_alembic.py` still generates an "initial_schema" revision with autogenerate; it's obsolete next to the baseline (left for UPG-15's clean-up).
- **To test later:** criterion 1 (upgrade on empty SQLite and PostgreSQL; `compare_metadata` empty on PostgreSQL, and on SQLite ignoring UUID-vs-NUMERIC type reflection); criterion 2 (downgrade base → upgrade head on PostgreSQL); criterion 3 (production start-up: an engine listener sees no CREATE/ALTER; an unmigrated database raises `DatabaseConfigError`); criterion 4 is the guide section. No existing test referenced the removed migrations.
- **Seen in the Google Cloud test deployment (2026-10-17) [R]:** `alembic upgrade head` on a new, empty Cloud SQL PostgreSQL 16 database ran 0001_baseline to 0006_participant_types and exited 0, and the production app started against it (it refuses to start unless the database is at head). That is part of criterion 1 only; `compare_metadata`, downgrade and SQLite are still to test.
- **Acceptance criteria:**
  1. ✅ Test: `alembic upgrade head` on an empty SQLite and an empty PostgreSQL database succeeds, and Alembic's `compare_metadata` against `models_pg.Base.metadata` reports no differences. [T `tests/test_migrations_baseline.py::test_upgrade_head_builds_an_empty_sqlite_database_that_matches_the_models` (types not compared on SQLite), `::test_upgrade_head_builds_an_empty_postgresql_database_that_matches_the_models` (**PostgreSQL 16.2**, types compared): `compare_metadata` reports nothing]
  2. ✅ Test: `alembic downgrade base` then `upgrade head` works on PostgreSQL. [T `::test_downgrade_base_then_upgrade_head_on_postgresql`]
  3. ✅ Test: with `FLASK_ENV=production`, app start-up issues no `CREATE TABLE` or `ALTER TABLE` (engine event listener), and refuses to start with a clear message if the database isn't at head. [T `::test_production_start_up_refuses_an_unmigrated_database_and_never_alters_one` (refused with "Run `alembic upgrade head`…"; at head it starts with no CREATE or ALTER seen by an engine listener)]
  4. ✅ `docs/DEPLOY.md` shows the migration step and how to stamp an existing database. [T `::test_the_deploy_guide_shows_the_migration_step_and_the_stamp`]

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
- **Built with UPG-21 (2026-10-10):** criteria 1–2 (S3 endpoint; no local fallback in production) and criterion 3's private upload with signed links are in `utils_storage.py`; see UPG-21.
- **Acceptance criteria:**
  1. Test (boto3 client stubbed): with `STORAGE_TYPE=s3` and `S3_ENDPOINT_URL` set, the client is created with that endpoint and the returned URL points at it.
  2. Test: with production config, an S3 failure raises and nothing is written under `static/uploads/`.
  3. Test: exports are uploaded without a public ACL and handed out as signed URLs that expire.
  4. Test: a certificate uploaded through one app instance is readable through a second instance (shared stubbed bucket), and after an app restart. *(Re-verification 2026-10-08: nothing uploads certificates any more; this criterion and criterion 3 have nothing live to test. Proposed in D-5: keep criteria 1–2 and fold them into UPG-21.)*
  - **2026-10-18:** its criteria are tested under UPG-21 (`tests/test_storage_endpoints.py`).

#### UPG-18 — Background tasks without a broker: inline with timeouts, plus an outbox for retries
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-18: …" on `production-ready` (parent `5eff67c`) [T]
- **Problem:** [C at `56a014d`] Without `CELERY_BROKER_URL=redis://…`, Celery runs every task inline in the request (`celery_app.py:49-58`, `task_always_eager`), with no timeout: a slow mail or WhatsApp provider holds the request (and the gunicorn worker). A failed send is logged and lost; nothing retries it. The Cloud Run + Supabase target has no Redis or worker. (Scheduled jobs are UPG-07.)
- **Who benefits:** everyone who waits on a page that sends mail; attendees whose confirmation would otherwise be lost.
- **What to build:** an outbox table (task name, arguments, attempts, next attempt, status, last error); with no broker, tasks run inline under a per-task timeout, and failures or timeouts are stored in the outbox; UPG-07's cron endpoint retries due rows with backoff and a maximum number of attempts. With a broker, behaviour is unchanged. Document both modes.
- **Files touched:** `celery_app.py`, new `services_outbox.py`, `models_pg.py` + migration, `tasks/*`, `docs/DEPLOY.md`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built; no change to the code.** Throwaway tasks registered on the app's Celery instance, plus one real request: a student's cancellation queues the waitlist promotion. Passes on SQLite and PostgreSQL 16. Making `_claim` always succeed fails the double-send test. The UPG-31 note stands: the notice keys are still read-then-write.
- **Files touched:** `tests/test_background_outbox.py` (new).
- **Effort:** M · **Depends on:** UPG-07 (retry trigger), UPG-16 (migration) · **Risk:** sending twice; each task keeps an idempotency key.
- **Noted in UPG-07 (2026-10-08):** the endpoint is built (`routes_cron.py`, jobs in `JOBS`). Add an `outbox` job there for due retries, and old outbox rows to the `cleanup` job, with a schedule line in `docs/DEPLOY.md` and `.github/workflows/cron.yml`. Until then, the day-before reminder's emails go out inline in the cron request, which `docs/DEPLOY.md` covers with a 30-minute deadline. **Noted in UPG-31:** the notice keys (`notification_dedup`, the reminders' `*_sent` flags) are read, then written, so two runs at the same instant could both send; the outbox's idempotency key should be a unique insert.
- **What was built (2026-10-10, development-only run):**
  - **Outbox table** `outbox` (`models_pg.OutboxTask`, `models_pg.py:640`; migration `migrations/versions/0002_outbox.py` on top of UPG-16's baseline): key (idempotency key, primary key), task name, JSON arguments, status (pending / running / done / failed), attempts, next attempt, last error.
  - **Inline with a timeout** (`services_outbox.py`): with no broker, `celery_app.OutboxTask.apply_async` (`celery_app.py:33`, the app's `task_cls`) hands each queued task to `run_inline` (`services_outbox.py:100`). It runs once in a worker thread (no inline retries) and the request waits at most `TASK_INLINE_TIMEOUT` (10 s). A failure or timeout is stored (`store`, `:118`: a unique insert on the key; a waiting row is kept, an old done/failed one re-armed). A timed-out run that later succeeds marks its row done, so it isn't retried. With a broker, Celery queues as before.
  - **Retries:** the cron endpoint's new `outbox` job (`routes_cron.py:49`) calls `retry_due` (`:203`): each due row is claimed with a conditional UPDATE (`_claim`, `:168`), run once, then marked done, rescheduled (5 min doubling to 6 h) or, after `OUTBOX_MAX_ATTEMPTS` (5), failed and logged. Rows left `running` by a dead process are retried after 30 minutes. The `cleanup` job deletes done rows after 7 days and failed rows after 30 (`purge_old`, `:239`).
  - `.github/workflows/cron.yml` runs `outbox` every 15 minutes; `docs/DEPLOY.md` documents the Cloud Scheduler job and both modes ("Background tasks"); `.env.example` lists `TASK_INLINE_TIMEOUT`, `TASK_INLINE_THREADS`, `OUTBOX_MAX_ATTEMPTS`.
  - Checked by hand [R] with throwaway tasks: a raising task runs once and leaves one row (attempts 1) while the call returns; a 3-second task returns control at the 1-second limit and its row turns `done` when it finishes; the retry job sends a stored task once, a second run sends nothing, and a row that keeps failing is `failed` at the maximum. Existing notice, cron, payment, certificate, task, waitlist, account-email, team and feedback tests pass.
  - Not done: the notice keys from UPG-31 (`notification_dedup`, `*_sent`) are still read-then-write; only the outbox's own rows are a unique insert.
- **To test later:** criteria 1–3 below (a raising task leaves one outbox row with attempts 1 and the request succeeds; a task past `TASK_INLINE_TIMEOUT` returns within the limit and is stored; the retry job sends once, a second run sends nothing, and the maximum marks the row failed); plus: the cron `outbox` job needs the secret like the others, `cleanup` deletes only old done/failed rows, and with `CELERY_BROKER_URL=redis://…` `apply_async` isn't intercepted. Criterion 4 is the guide section.
- **Acceptance criteria:**
  1. ✅ Test: with no broker, a task that raises leaves one outbox row (attempts 1) and the request still succeeds. [T `tests/test_background_outbox.py::test_a_failing_task_leaves_one_row_with_attempts_1_and_the_call_returns` (ran once, no inline retries; the same failure again keeps one row); `::test_a_request_whose_task_fails_still_succeeds` (the cancel answers 302, the registration is cancelled, the promotion waits in the outbox)]
  2. ✅ Test: a task that runs past its timeout returns control to the request within the limit and is stored for retry. [T `::test_a_task_past_the_timeout_returns_within_the_limit_and_is_stored` (0.5 s limit, 2 s task; when it finishes the row turns `done`)]
  3. ✅ Test: the retry job sends a stored task once; running it again sends nothing; after the maximum attempts the row is marked failed. [T `::test_the_retry_job_sends_a_stored_task_once` (not before it's due), `::test_a_task_that_keeps_failing_is_marked_failed_at_the_maximum`, `::test_a_claimed_row_isnt_sent_by_a_second_run`; extras: `::test_the_outbox_job_needs_the_cron_secret`, `::test_cleanup_deletes_only_old_sent_and_failed_rows`, `::test_with_a_broker_apply_async_is_not_intercepted`]
  4. ✅ `docs/DEPLOY.md` explains the inline + outbox mode and the broker mode. [T `::test_the_deploy_guide_explains_both_modes` (`docs/DEPLOY.md` "Background tasks")]

#### UPG-19 — Pagination and search on every admin, SPOC and coordinator list
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-19: …" on `production-ready` (parent `1536aae`) [T]
- **Problem:** [C at `56a014d`] Only `routes_api_v1.py` and `routes_notifications_v2.py` read a page or limit parameter (the plan's prompt said 3 route files). The web lists stream whole collections into one page: `.stream()` appears 27 times in `routes_admin.py`, 27 in `routes_spoc.py`, 13 in `routes_coordinator.py` and 7 in `routes_forms.py` (re-counted 2026-10-08; 25, 29, 15 and 6 at `986d108`) (for example users, registrations, form responses, audit log). With a whole university's data these pages will be slow or time out.
- **Who benefits:** admins, SPOCs and coordinators of large events.
- **What to build:** one pagination helper (page, per-page capped at 100, total, next/previous links) with SQL-side limit/offset where the adapter can push it down, and a search box (name, email, USN) on each list. The item lists every covered endpoint when done.
- **Files touched:** new helper, `routes_admin.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_forms.py`, list templates, `db_adapter.py` (offset), tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built; no change to the code.** Every covered list was filled with 120 rows marked with a unique token and searched by it, so other tests' data doesn't change the counts. Passes on SQLite and PostgreSQL 16. Swapping the users list's SQL paging for a load-everything list fails the `LIMIT` test.
  - **Covered endpoints:** `/admin/users`, `/admin/audit_log`, `/admin/payments` (paid registrations), `/admin/registrations`, `/admin/dashboard` (event table), `/admin/events`, `/spoc/dashboard`, `/coordinator/dashboard`, `/coordinator/registrations/<event_id>`, `/forms/responses/<event_id>`.
  - **On purpose, not paged:**
    - the dashboards' chart data (`<script>` JSON) and event pickers (`<select>`, e.g. the announcement's event) list every event;
    - the SPOC scan page's manual list, the payments page's unmatched orders and the admin's recent activity (as built).
- **Files touched:** `tests/test_pagination_lists.py` (new).
- **Effort:** M (split by area if it grows past ~800 lines) · **Depends on:** BLK-06 (indexed columns) · **Risk:** low.
- **What was built (2026-10-10, development-only run; 25 a page, the owner's number, instead of the 50 in criterion 1):**
  - **One helper**, `utils_pagination.py`: `page_args` reads `?page`, `?per_page` (25 by default, capped at 100) and `?q`; `paginate_query` pages a database query with LIMIT/OFFSET; `paginate_items` searches and pages a loaded list; `paginate_events` adds `?status=` (active / completed) for dashboards. Links keep every other query argument, so the search, filters and page stay in the URL. Shared partials `templates/includes/list_search.html` and `templates/includes/pagination.html` ("Showing 26–50 of 61", previous/next).
  - **The SQL adapter gained `offset()` and `count()`** (`db_adapter.py:1695,1701`, also on collections `:1842,1845`): both go into SQL when every filter and order is a plain column (an unfiltered `count()` is one `COUNT`), else they apply after loading.
  - **Lists covered:**
    - admin users (`routes_admin.py:455`, SQL LIMIT/OFFSET in email order; a search loads and filters on name, email, USN and role, `:453`);
    - admin audit log (`:589` SQL-paged, newest first; was capped at the last 100; role, action and text filters are now a GET form, `:587`);
    - admin payments, paid registrations (`:510`);
    - admin dashboard event table and its modals (`:112`);
    - SPOC dashboard sidebar and event panels (`routes_spoc.py:107`; the filter pills are links);
    - coordinator dashboard cards (`routes_coordinator.py:118`) and event registrations (`:146`);
    - form responses (`routes_forms.py:767`).
    Stats and charts on the dashboards still count every event. The client-side filter scripts on the audit log, admin dashboard and form responses were removed (the server filters now).
  - **Not paginated, on purpose:** the SPOC scan page's manual check-in list (on event day staff search the whole list on one screen); the admin payments page's unmatched-orders table (exceptions, few); the admin dashboard's "recent activity" (20 rows).
  - Checked by hand [R] with 61 users, 60 audit entries, 30 events and 60 registrations and submissions: every list shows 25 then "51–60 of 60" on page 3; searches by name, email or USN narrow it and combine with the page; `per_page=1000` shows 61 (cap 100); the users page issues `SELECT … FROM users … LIMIT`. Related existing tests pass.
- **To test later:** criteria 1–4 below with 25 as the default (each covered list with 120 rows: 25 by default, page 5 shows the last 20; search by name, email or USN narrows and combines with the page; `per_page=1000` capped at 100; the users list issues a SQL `LIMIT`), plus `?status=` on the three dashboards and the audit log's role/action filters, and that the dashboards' stats still count every event.
- **Acceptance criteria:**
  1. ✅ Test: each covered list with 120 rows shows 25 by default (the owner's page size, 2026-10-10; this criterion first said 50, with page 3 holding the last 20), and page 5 shows the last 20. [T `tests/test_pagination_lists.py::test_each_list_shows_25_and_page_5_holds_the_last_20` (10 lists; a page past the end shows the last)]
  2. ✅ Test: searching by name, email or USN narrows the list; search and page combine. [T `::test_search_narrows_each_list_and_combines_with_the_page` (name on all 10; email on 6, USN on 4 lists that hold them)]
  3. ✅ Test: `per_page=1000` is capped at 100. [T `::test_per_page_is_capped_at_100`]
  4. ✅ Test: the users list issues a SQL `LIMIT` rather than loading every row (query count or compiled SQL check). [T `::test_the_users_list_pages_in_sql` (every `SELECT … FROM users` carries `LIMIT`); extras: `::test_the_dashboards_status_filter` (3 dashboards), `::test_the_dashboard_totals_count_every_event`, `::test_the_audit_log_role_and_action_filters`]

#### UPG-20 — Boot checks, health, logs, Sentry and security headers for production
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-20: …" on `production-ready` (parent `5b18a3d`) [T]
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
- **Built (2026-10-18):**
  - **Tested in Part 2. Found and fixed:** `.env.example` had fallen behind. It lacked ten settings the app reads, all added after UPG-20:
    - `REFERRALS_ENABLED` (UPG-105), `DEMO_PAGES_ENABLED` (UPG-65) and `FEATURE_MATCHMAKER` (UPG-14), now under a new "Features off by default" group;
    - `GOOGLE_ALLOWED_DOMAIN` and `UNIVERSITY_EMAIL_DOMAIN` (UPG-10);
    - `ZOHO_AUTH_TOKEN`, `CATALYST_AUTH_TOKEN`, `ZOHO_CATALYST_ORG`, `ZOHO_QUICKML_ENDPOINT` and `ZOHO_QUICKML_MODEL` (the Zoho AI provider, UPG-109).
    It also listed `NO_SCHEDULER`, which nothing has read since UPG-112 removed the scheduler file; that line is gone from `.env.example` and from CI's environment.
  - The boot tests start the real app in a subprocess with `FLASK_ENV=production`, on a database built by `alembic upgrade head`: SQLite with `ALLOW_SQLITE_IN_PRODUCTION`, and PostgreSQL 16 when `TEST_DATABASE_URL` points at one. The existing `tests/test_health.py` and `tests/test_checkin_security.py` boot test still pass.
- **Files touched:** `.env.example`, `.github/workflows/ci.yml`, `tests/test_production_boot.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** a stricter boot check refuses to start a misconfigured deploy (intended).
- **What was built (2026-10-10, development-only run):**
  - **One production boot check** (`config.production_problems`, `config.py:43`; `check_production_settings`, `:89`, called at app start in place of `validate_production_config`): it lists **every** missing or weak setting in one error: `SECRET_KEY`, `MASTER_SECRET_KEY`, `JWT_SECRET_KEY` (32+, different from `SECRET_KEY`; no silent fallback in production any more), a 12+ `SUPER_ADMIN_PASS` when set, `BASE_URL` (https, not localhost), the database (PostgreSQL, the old separate check merged in), a mail provider and sender, `CRON_SECRET` (unless Celery beat runs), Razorpay all-or-none, and no `PAYMENT_SIMULATION`. The class-level `SECRET_KEY` refusal in `Config` (which existing tests pin) keeps its message and now appends the other problems. `validate_production_config` is unchanged for its existing test.
  - **`/health` and `/health/ready`** (`app.py:515`) run a real round trip (`_database_ok`, `:495`: `SELECT 1` on the SQL layer, one document read in Firestore mode) and answer 200 or 503 with only status, time and version (the Cloud Run revision); the error goes to the log, never the body.
  - **JSON logs**: `utils_logging.CloudRunJsonFormatter` writes one JSON object per line in production with `severity`, `message`, logger, time, source location and, on Cloud Run, the request's trace; development stays plain text.
  - **Sentry**: `init_sentry` (`app.py:102`) is on only when `SENTRY_DSN` is set, with `send_default_pii=False` and the Cloud Run revision as the release.
  - **Headers**: HSTS (one year) is always sent in production behind `ProxyFix` (`app.py:223`), plus `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: SAMEORIGIN` and a `Permissions-Policy` (camera and microphone for this site only; `:233`). *(Corrected the same day: the header first used Feature-Policy syntax, `camera='self'`, which Chrome rejects; it's now `camera=(self)`. Found by UPG-25's browser pass.)*
  - **`.env.example`** lists all 94 environment variables the app code reads (scan of 105 app files; 50 before), grouped, with what each is for and how to generate or find each value. `COLLEGE_LOGO_URL` no longer defaults to the retired Railway domain (unset → `BASE_URL` + `/static/snpsu-logo.png`).
  - Checked by hand [R]: production start-up on a migrated PostgreSQL 16 with strong dummy values serves `/` and `/health` (200) with HSTS, nosniff, referrer, frame and permissions headers; with `BREVO_API_KEY` and `CRON_SECRET` blanked it refuses with one error naming both; with the database unreachable `/health` is 503 with no error text; a log line is JSON with `severity`. Health, check-in security, integration, session, hygiene, cron, mail and security tests pass.
- **To test later:** criteria 1–6 below. For criterion 2, the scan used here (`os.environ.get`/`os.getenv`/`os.environ[...]` in tracked app files, excluding tests, seeds, generators, one-off scripts, `functions/` and `scratch/`) found 94 names, all in `.env.example`. The existing `tests/test_health.py` (expects `healthy`/`unhealthy`, `timestamp`, `version`) and `tests/test_checkin_security.py::test_app_refuses_to_boot_in_production_without_secret_key` still pass and should stay.
- **Acceptance criteria:**
  1. ✅ Test: production boot with two required settings missing raises one error naming both; with strong dummy values it starts. [T `tests/test_production_boot.py::test_production_refuses_with_one_error_naming_every_missing_setting` (mail provider and `CRON_SECRET` in one error), `::test_production_starts_with_strong_settings_and_is_hardened`, `::test_production_starts_on_postgresql` (also refuses a JWT key equal to `SECRET_KEY` plus a missing `MAIL_FROM` together), `::test_without_a_database_production_names_that_too`]
  2. ✅ Test: every environment variable read by app code (AST scan) appears in `.env.example`, or in a short allow-list of test-only names. [T `::test_every_environment_variable_the_app_reads_is_in_env_example` (AST scan of every tracked non-test file, 100+ names; allow-list: the two read only by `seed_safety.py`); fails on the old `.env.example`]
  3. ✅ Test: `/health` returns 503 when the database is unreachable and 200 otherwise; neither body contains exception text. [T `::test_health_is_503_without_the_database_and_shows_no_error` (real SQL layer, then an unreachable PostgreSQL: 503 on `/health` and `/health/ready`, no error, host or password in the body); 200 in the production boot]
  4. ✅ Test: with production config, a log call produces one JSON object with `severity` and `message`. [T `::test_production_starts_with_strong_settings_and_is_hardened` (a warning logged after start-up is one JSON line with `severity` WARNING and the message)]
  5. ✅ Test: with `SENTRY_DSN` set, `sentry_sdk.init` is called with `send_default_pii=False`; without it, it isn't called. [T `::test_sentry_starts_only_with_a_dsn_and_without_personal_data`]
  6. ✅ Test: production responses carry HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy` and a frame policy. [T `::test_production_starts_with_strong_settings_and_is_hardened` (HSTS one year, `nosniff`, `strict-origin-when-cross-origin`, `SAMEORIGIN`)]

#### UPG-21 — Daily database backups and a tested restore
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-21: …" on `production-ready` (parent `79768c5`) [T]
- **Problem:** MISSING [C]. Nothing in the repo dumps or restores the database (searched for `pg_dump` and backup scripts; the only "backup" hits are 2FA backup codes). Whether the Supabase plan in use keeps its own backups isn't known; don't rely on it.
- **Who benefits:** the university (every record of every event).
- **What to build:** `scripts/backup_db.sh` (`pg_dump -Fc` to a private bucket, dated names, retention), run daily by the external scheduler (Cloud Scheduler + a Cloud Run job, or GitHub Actions); `scripts/restore_db.sh`; a documented restore drill. Dumps are never committed.
- **Files touched:** `scripts/backup_db.sh`, `scripts/restore_db.sh`, `.gitignore`, `tests/test_repo_hygiene.py`, `docs/DEPLOY.md`, tests.
- **Built (2026-10-17):**
  - **Tested in Part 2.**
  - **Found and fixed:** criterion 2 wasn't built. `.gitignore` refused `*.dump`/`*.sql`/`*.sql.gz`/`*.backup`, but the hygiene test's forbidden list had no such pattern, so a tracked dump would have passed. The pattern and examples are added to `tests/test_repo_hygiene.py` (a stricter test; nothing tracked matches).
  - The backup test uses the PostgreSQL tools from `pgserver` and a stand-in `aws` command that keeps the bucket in a local folder.
- **Files touched:** `tests/test_repo_hygiene.py`, `tests/test_backup_restore.py` (new), `tests/test_storage_endpoints.py` (new).
- **Effort:** S · **Depends on:** UPG-17 (bucket settings) · **Risk:** a dump holds all personal data; the bucket must be private and access-limited.
- **What was built (2026-10-10, development-only run; UPG-17 folded in, D-5):**
  - **`scripts/backup_db.sh`**: `pg_dump --format=custom` of `DATABASE_URL`, a `pg_restore --list` check, upload to `BACKUP_BUCKET` (`s3://`, with `S3_ENDPOINT_URL` for Supabase Storage, or `gs://`) as `saptha-<UTC time>.dump`, and deletion of dumps older than `BACKUP_RETENTION_DAYS` (30) by the date in their names. The local copy is removed on exit.
  - **`scripts/restore_db.sh <dump> <target URL>`**: downloads (or takes a file), refuses a target that already has tables, restores with `pg_restore --exit-on-error`, and prints rows per table.
  - **Schedule**: `.github/workflows/backup.yml` (daily 02:00 IST and by hand; installs the matching `postgresql-client`; idle until `BACKUP_DATABASE_URL` and `BACKUP_BUCKET` are set; no permissions); the Cloud Run job alternative is documented.
  - **`docs/DEPLOY.md`**: "Backups" (what runs, both schedules, retention, private-bucket permissions, the storage settings) and "Restore drill" (five steps, every term).
  - **`.gitignore`** refuses `*.dump`, `*.sql`, `*.sql.gz`, `*.backup` (nothing tracked matches).
  - **UPG-17's storage settings** (`utils_storage.py`): `S3_ENDPOINT_URL` is passed to the S3 client and used for URLs; new `upload_private` (no public ACL) and `signed_url` (15 minutes) for exports, used by `tasks/export_tasks._upload_export`; in production an S3 or GCS error raises `StorageError` and nothing is written to `static/uploads/` (local disk is development only). `upload_file` keeps its public contract, which `tests/test_storage.py` pins. For Supabase Storage public URLs, set `AWS_S3_CUSTOM_DOMAIN` to the bucket's public path (the S3 endpoint isn't the public download address).
  - `.env.example` documents `S3_ENDPOINT_URL`, `BACKUP_BUCKET` and `BACKUP_RETENTION_DAYS`.
  - Checked by hand [R] on PostgreSQL 16 (bundled `pg_dump`/`pg_restore`, a local stand-in for the `aws` CLI): the backup of a database with 7 users and 3 events uploaded one dump and pruned a 2020 one; restoring it into an empty database gave the same counts and Alembic revision; restoring again into the now non-empty database was refused (exit 3). With stubbed boto3: the endpoint reaches the client, private uploads carry no ACL, a signed URL comes back, and a production failure raises without writing locally.
- **To test later:** criteria 1–3 below (backup against a test PostgreSQL → restore into an empty database gives the same row counts per table; the hygiene test fails on a tracked `*.dump`/`*.sql`/`*.sql.gz`/`*.backup`; the guide section), plus UPG-17's criteria 1–2 (the S3 endpoint is used; a production S3 failure raises and writes nothing under `static/uploads/`) and the signed, non-public export upload.
- **Acceptance criteria:**
  1. ✅ Test: the backup script against a test PostgreSQL produces a dump; restoring it into an empty database gives the same row counts per table. [T on **PostgreSQL 16.2**: `tests/test_backup_restore.py::test_a_backup_restores_into_an_empty_database_with_the_same_rows` (a migrated database with 7 users; one dump uploaded and a 2020 one pruned; restored with identical row counts in every table and the same Alembic revision; a second restore into the non-empty database refused with exit 3)]
  2. ✅ Test: the hygiene test fails if a `*.dump`, `*.sql`, `*.sql.gz` or `*.backup` file is tracked. [T `tests/test_repo_hygiene.py::test_patterns_flag_forbidden_paths` (now including dump files) and `::test_gitignore_rules`]
  3. ✅ `docs/DEPLOY.md` documents the schedule, retention, bucket permissions and the restore drill. [T `tests/test_backup_restore.py::test_the_guide_documents_backups_and_the_restore_drill`]
  - UPG-17's part: `tests/test_storage_endpoints.py` (boto3 stubbed): the S3 endpoint reaches the client and the URL; private uploads carry no ACL and come back through a 15-minute signed link; in production an S3 failure raises and nothing is written under `static/uploads/`.

#### UPG-22 — Privacy notice, consent at registration, working data export and deletion
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-22: …" on `production-ready` (parent `b72a9b5`) [T]
- **Problem:** [C at `56a014d`] `routes_compliance.py` has data export (`:50`), deletion request (`:126`), cancel deletion (`:188`) and consent (`:211`, `:250`) endpoints, never run end to end. The registration form has no consent checkbox (no "consent" in `templates/public/registration_form.html`). The privacy page is linked from only 5 templates, because pages don't share a footer (UPG-23).
- **Who benefits:** every student and external participant; the university's DPDP obligations.
- **What to build:** a privacy notice linked from the shared footer; a required consent checkbox at registration and sign-up, stored with the time and notice version; a working export (the user's own data as a download) and deletion (account removed, registrations anonymised, kept only where records must be retained).
- **Files touched:** `routes_compliance.py`, `routes_forms.py`, `routes_auth.py`, `templates/public/registration_form.html`, the shared layout, tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** Payment orders and the audit log keeping the email is still the open policy decision D-7.
- **Files touched:** `tests/test_privacy_rights.py` (new).
- **Effort:** M · **Depends on:** BLK-02, UPG-23 (footer) · **Risk:** what must be kept (e.g. certificates, finance records) is a policy question; record it under "Decisions needed" if it blocks.
- **Noted in UPG-07 (2026-10-08):** the scheduled lifecycle job used to delete events 5 days after their date and registrations after 30 days. It now only changes statuses, so nothing is deleted on a schedule. If old data should go after some time, that rule belongs here, with the policy above.
- **What was built (2026-10-10, development-only run):**
  - **Notice and footer:** the privacy page shows its version (`services_privacy.PRIVACY_NOTICE_VERSION`, `services_privacy.py:26`, now `2026-10-10`) and says how to download data and delete an account and what stays after deletion. `templates/base_classic.html` gained a footer (privacy notice, terms) on every page that uses the shared layout, public ones included (the old link was only in the signed-in sidebar); the stray `</div>` closing `<main>` is now `</main>`.
  - **Consent at registration and sign-up:** a required checkbox on the registration form and the sign-up page. The server refuses without it, with a clear message, right before anything is created (`routes_forms.py:570`, `routes_auth.py:303`), so "log in first" and "already registered" answers are unchanged. The registration stores `privacy_consent: {at, version}`; the person's `user_consent` document keeps the latest consent (`record_consent`). The user document gets the same on sign-up.
  - **Export from the profile page** ("Your data and privacy" card): `POST /compliance/export-data` (`routes_compliance.py:52`) returns a JSON download built by `own_data` (`services_privacy.py:98`): profile (no password, 2FA or calendar secrets), registrations they lead or are a member of, form submissions, feedback, notifications and consent. A team member sees only their own entry; the lead's and other members' details are left out (an allow-list, because the SQL layer also returns aliases such as `leadEmail`).
  - **Deletion from the profile page:** a confirmed form posts to `/compliance/delete-request` (`:76`, form posts now get a flash and a redirect; JSON callers unchanged), which schedules it in 30 days; the card then offers "Cancel deletion". The cron `cleanup` job runs `process_due_deletions` (`services_privacy.py:181`; `routes_cron.py:44`): `anonymise_account` (`:137`) deletes the account (no login, no reset), replaces the person's name, email, phone, USN and answers in registrations they lead and in team entries, form submissions and feedback, deletes their notifications and consent, and marks the request completed with a hashed email. Registration rows stay (attendance and payment totals feed reports). Error replies no longer include exception text.
  - **Kept, pending a policy decision (D-7):** payment orders (finance records) and the audit log keep the email. API v1 registrations (Android and Flutter apps) don't require consent, to stay backward compatible; coordinator walk-ins record none.
  - **Existing tests:** 41 registration posts in 22 test files gained `'privacy_consent': 'yes'` in their form data; no assertion changed. Full pytest on SQLite: 893 passed, 1 skipped (same as before this run).
  - Checked by hand [R]: without the box, no registration and the message; with it, the consent is stored with time and version; a member's export holds nothing about the lead; scheduling, then processing 31 days later, removes the account (login fails) and leaves "Deleted user" with a placeholder email in both the led registration and the other team's member entry; the privacy page shows the version and the shared footer links it.
- **To test later:** criteria 1–4 below, plus the cancel path, the member-view export (no other person's data, aliases included) and that the cron `cleanup` processes only due requests.
- **Acceptance criteria:**
  1. ✅ Test: registration without consent → refused with a clear message; with consent → stored with time and notice version. [T `tests/test_privacy_rights.py::test_registration_needs_consent_and_stores_it_with_time_and_version`]
  2. ✅ Test: export returns the user's profile and registrations and nothing about anyone else. [T `::test_the_export_holds_only_the_persons_own_data` (a team member's export holds none of the lead's name, email or phone, nor another registrant's)]
  3. ✅ Test: after deletion is processed, the user can't log in and their registrations hold no name, email or phone. [T `::test_deletion_can_be_cancelled_and_the_cleanup_only_does_due_requests` (no confirmation → nothing; cancel; through `/internal/cron/cleanup` only the due request is carried out; login then fails and the registrations hold no name or email; the not-due person is untouched)]
  4. ✅ Test: every page on the shared layout links the privacy notice. [T `::test_shared_layout_pages_link_the_privacy_notice`]
  - **Re-verified at the end of Part 1 (2026-10-17):** since UPG-69 the SQL layer always returns `lead_email`/`lead_name`/`lead_phone` for registrations as well as `leadEmail`. The team member's allow-list still leaves the lead's details out (it lists what to keep, not what to drop).

### E. Frontend (added in Phase 0, 2026-09-30)

#### UPG-23 — Every page on one shared layout (split by area: UPG-23a–h)
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-23: …" on `production-ready` (parent `216f7a3`) [T]
- **Problem:** [C at `56a014d`, counted with a script] Of 129 templates, 16 extend `base_classic.html` (12 at `986d108`; Phase 2 added `admin/payments.html` and moved `admin/users.html`, `teams/join.html` and `teams/view.html` onto it), 1 extends `coordinator/base.html`, which doesn't exist (`templates/coordinator/view_scores.html`; nothing renders it, UPG-15), 5 are partials, and **107 are standalone pages** with their own `<head>`, CDN tags and navigation (111 at `986d108`; the plan's prompt said 108 of 126 and ~13). So fixes to navigation, CSP, fonts, footer or loading states have to be made 107 times. (Re-counted 2026-10-02: Phase 0 wrote 110, which left the four groups one short of 129.)
- **Who benefits:** every user (consistent navigation, mobile layout); every later frontend item.
- **What to build:** a role-aware shared layout (extend `base_classic.html`, with blocks for per-role navigation, and a minimal child layout for full-screen pages such as the kiosk, scanners and printable certificate). Move pages one area at a time, one commit each: 23a public, 23b participant, 23c teams/profile/payment, 23d SPOC, 23e coordinator, 23f judge, 23g admin, 23h marketing. Keep the existing design tokens in `static/css/global.css`; no redesign. Where a headless browser is available, screenshot each area's key pages at 375px and 1280px before and after.
- **Files touched:** `templates/**`, `templates/base_classic.html`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2 (all of 23a–h at once), as built; no change to the app.** 23 key pages across six roles: anonymous (8), student (5), SPOC (3), coordinator (2), judge (1) and Super Admin (4).
  - **The 375px check runs in headless Chromium.** Each page is loaded as the app rendered it for that role, with `/static` from disk and Bootstrap from `tests/fixtures/bootstrap-5.3.3.min.css`, the exact file the templates load (a test checks its SHA-384 against their `integrity` attribute). There are no before-screenshots, so "nothing lost" is checked against the same page at 1280px: every heading and form field visible there is visible at 375px. Sideways scroll counts when the page itself scrolls (`window.scrollX`), or when text, an image or a control sticks out past the screen without a box the user can scroll around it. Removing an admin table's `.table-responsive` fails it.
  - **Recorded as intended, not lost:**
    - the login page's brand panel shows on wide screens only (`static/css/global.css` `.auth-info-panel`), and the form is complete on a phone;
    - the SPOC dashboard is master/detail on a phone, so the test opens its overview with the "Overview" tap and counts both views;
    - the home page has its own footer landmark, with the privacy notice and terms;
    - `public/event_fragment.html` is the home popup's fragment (UPG-92), not a page.
- **Files touched:** `tests/test_shared_layout.py`, `tests/fixtures/bootstrap-5.3.3.min.css` (new; Bootstrap 5.3.3, MIT).
- **Effort:** L (8 sub-items) · **Depends on:** none (UPG-24/25 get easier after it) · **Risk:** lost page-specific CSS or scripts; the screenshot comparison and page tests guard it.
- **What was built (2026-10-10, development-only run, 23a–23h, one commit each):**
  - **One document for every page:** `templates/layouts/document.html` holds the doctype, charset, viewport, CSRF meta, the CSRF fetch shim (moved out of `base_classic.html`), the shared footer (privacy notice and terms, UPG-22) and its styles, with the blocks `html_attrs`, `csrf_meta`, `head`, `body_attrs`, `body`, `site_footer`, `body_end`. Its children: `base_classic.html` (the app layout with the role-aware sidebar, unchanged output; its footer stays in the content column), `layouts/standalone.html` (pages with their own header, navigation and design) and `layouts/fullscreen.html` (no footer: kiosk, exam, certificate embed, reels, live board, scanners and HUD, NFC scanner, badge, certificate).
  - **Every template a route renders now extends the document** (directly or through `base_classic.html`): 35 public (23a), 8 participant (23b), 2 profile/payment (23c), 14 SPOC (23d), 10 coordinator (23e), 2 judge (23f), 12 admin (23g), 5 marketing/onboarding (23h). A converter moved each page's `<head>` and `<body>` into the `head` and `body` blocks byte for byte (it asserts the reconstruction) minus the charset and viewport metas the document now provides; a page's own CSRF meta, `<html>` and `<body>` attributes go into their blocks. Pages whose `<body>` centres one card get the footer pinned to the bottom (`site_footer_fixed`). No URL, style or script changed, so there's no redesign; per-page CDN tags stay until UPG-24.
  - **Left standalone:** the 18 templates nothing renders (UPG-15 deletes them).
  - **Checked [R]:** a crawl of every GET route (858 fetches: anonymous, Super Admin, SPOC, coordinator, judge, student, on a seeded event and registration) before 23a and after each area gives the same status, `<title>` and visible text (the shared footer aside) every time; full pytest 893 passed, 1 skipped. Not done: screenshots at 375px and 1280px (no headless browser yet; UPG-28 adds one).
  - Found: 17 fetches answer 500 before and after this run (AI match page, exams, gamification leaderboard, hackathon submit, SPOC stats API) → new item UPG-59.
- **To test later:** criteria 1–2 (every rendered template extends the document; key pages per role return 200 with the footer landmark) and 3 (375px, no horizontal scroll, nothing lost against before-screenshots; with UPG-28's browser). Criterion 4 holds: no URL changed.
- **Acceptance criteria (per sub-item, for its area):**
  1. ✅ Test: every template in the area that is rendered by a route extends the shared layout (or its minimal child). [T `tests/test_shared_layout.py::test_every_rendered_template_extends_the_shared_document` (every literal `render_template` name, through its `{% extends %}` chain)]
  2. ✅ Test: each key page returns 200 for its role and contains the shared navigation and footer landmarks. [T `::test_each_key_page_answers_with_the_shared_footer_and_navigation` (30 pages, 6 roles)]
  3. ✅ At 375px no key page scrolls horizontally, and no content is lost compared with the before-screenshot (headless check, when available). [T `::test_key_pages_fit_a_375px_phone_and_lose_nothing`, `::test_the_bootstrap_fixture_is_the_file_the_templates_load`]
  4. ✅ No URL changes. [T `tests/test_dead_code_and_links.py::test_every_internal_link_action_and_fetch_url_reaches_a_route` (UPG-15)]
- **2026-10-19, in the full run:** with many events in the database, the home page's photo marquee (a strip that scrolls by itself, a CSS animation) has images past the screen edge. They come into view on their own, so the 375px check now treats content inside a running animation like content in a box the user can scroll. Test-only change.

#### UPG-24 — One Bootstrap version and one font set, loaded once, with SRI
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-24: …" on `production-ready` (parent `9d6ea24`) [T]
- **Problem:** [C at `56a014d`] Bootstrap 5.3.0 is loaded by 46 templates and 5.3.3 by 34 (re-counted 2026-10-08; 50 and 34 at `986d108`, before four pages moved onto the shared layout). Google Fonts families: Inter (29 templates), Poppins (27), Plus Jakarta Sans (4), Cinzel (3), Orbitron (1), Outfit (1), while `static/css/global.css` uses Inter, Plus Jakarta Sans and Outfit (`global.css:189,201,897`). Of 261 CDN `<script>`/`<link>` tags, 2 have an `integrity` hash (still 2 on 2026-10-08; the font and tag counts fell slightly as pages moved onto the shared layout).
- **Who benefits:** every user (one download, consistent look); security (SRI).
- **What to build:** Bootstrap 5.3.3 and the font set `global.css` uses, loaded once in the layout, with `integrity` and `crossorigin` on every CDN file.
- **Files touched:** `templates/base_classic.html`, templates still carrying their own tags, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built; no change to the app.** The template scan covers every file under `templates/`. The font check loads four pages in headless Chromium and records every font request: only the three files in `static/fonts/` (and Font Awesome's own icon font). Removing a partial's `integrity` attribute fails criterion 2's test. The Poppins → Outfit screenshot comparison has no "before" to compare with. UPG-23's 375px check now covers those pages' headings and fields.
- **Files touched:** `tests/test_assets_and_fonts.py` (new).
- **Effort:** S (after UPG-23) · **Depends on:** UPG-23 · **Risk:** pages relying on 5.3.0 quirks or on Poppins; check in screenshots.
- **What was built (2026-10-10, development-only run):**
  - **One Bootstrap (5.3.3) and one Font Awesome (6.5.1)**, each defined once, with `integrity` and `crossorigin`: `templates/layouts/_bootstrap_css.html`, `_bootstrap_js.html`, `_fontawesome.html`. Every page that loaded any Bootstrap 5.3.x or Font Awesome 6.x copy now includes the partial **at the same place** its own tag was (88 CSS, 45 JS, 99 icon tags; a page that loaded one twice keeps one), so the order of stylesheets, and with it the cascade, is unchanged. No template references `bootstrap@5.3.0` any more, and Bootstrap tags exist only in the layout partials. Pages that never loaded Bootstrap (the `base_classic.html` pages) still don't, which avoids a redesign.
  - **One font set, self-hosted:** the three families `global.css` uses (Inter, Plus Jakarta Sans, Outfit) as variable Latin `woff2` files in `static/fonts/` (112 KB, SIL OFL, from @fontsource-variable 5.1.0), declared in `static/css/fonts.css` and loaded once by `layouts/document.html`. All 72 Google Fonts links and the `@import` in `global.css` are gone, so pages make no third-party font requests (and need no SRI for fonts). Other families were mapped in page styles (223 places): Poppins and Orbitron → Outfit, Montserrat → Inter, Cinzel → Georgia, JetBrains Mono → the system monospace font; `marketing.css` likewise. **This changes how headings look on pages that used Poppins (the closest match, Outfit, is used); check in UPG-28's screenshots.**
  - **Every other CDN file pinned and hashed:** Chart.js 4.4.0 (one page loaded an unversioned `chart.js`), FullCalendar 6.1.11 (one page had 6.1.8), html5-qrcode 2.3.8 and Leaflet 1.9.4 moved from unpkg to jsdelivr (the CSP never allowed unpkg, so Leaflet was blocked), canvas-confetti 1.6.0: 13 tags with `integrity`/`crossorigin`. **Exception:** Razorpay's `checkout.js`, which Razorpay changes in place and doesn't publish hashes for.
  - The CSP no longer allows `fonts.googleapis.com`/`fonts.gstatic.com` (`app.py`).
  - Checked [R]: the 858-fetch crawl gives the same status, title and visible text; template, security and offline tests pass; ruff clean; app starts. Hashes were computed from the CDN files themselves (Bootstrap's match the published ones).
- **To test later:** criteria 1–3 below, with Razorpay's `checkout.js` as the one allowed exception to criterion 2, and a screenshot comparison of pages that used Poppins.
- **Acceptance criteria:**
  1. ✅ Test: no template references `bootstrap@5.3.0`; Bootstrap CSS and JS appear only in the layout files. [T `tests/test_assets_and_fonts.py::test_one_bootstrap_defined_only_in_the_layout_partials`]
  2. ✅ Test: every CDN `<script>` and stylesheet `<link>` has `integrity` and `crossorigin`. [T `::test_every_cdn_script_and_stylesheet_has_integrity_and_crossorigin`, `::test_razorpay_is_the_only_unhashed_script` (only `checkout.razorpay.com/v1/checkout.js`); Bootstrap's hash is also checked against the file itself at UPG-23]
  3. ✅ Test: only the font families used by `global.css` are requested. [T `::test_only_the_three_families_are_declared_and_nothing_loads_web_fonts`, `::test_a_page_requests_only_the_self_hosted_fonts` (4 pages, headless)]

#### UPG-25 — Move inline scripts into static files; remove `'unsafe-inline'` from `script-src`
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-25: …" on `production-ready` (parent `d29e2de`) [T]
- **Problem:** [C at `56a014d`] 70 templates contain inline `<script>` blocks, and 76 templates contain 483 inline event handlers (`onclick=` and similar; re-counted 2026-10-08: 72, 78 and 490 at `986d108`). So the CSP's `script-src` allows `'unsafe-inline'` (`app.py:221`), which removes most of its protection against injected scripts; `content_security_policy_nonce_in=[]` (`app.py:236`).
- **Who benefits:** every user (XSS protection).
- **What to build:** page scripts in `static/js/`; event handlers bound with `addEventListener`; a per-request nonce (`content_security_policy_nonce_in=['script-src']`) for anything that must stay inline (e.g. a small JSON bootstrap); then remove `'unsafe-inline'` from `script-src`.
- **Files touched:** `templates/**`, `static/js/**`, `app.py`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2, as built; no change to the app.** The browser check is now in the repo (it ran from a scratch harness at build time). Each of UPG-23's 23 key pages is loaded in headless Chromium under the exact CSP header the app sent with it, and every `data-h-*` key on the page must have a registered handler (`handlers.js` warns otherwise). Removing the nonce from one inline script on the admin dashboard fails both the template scan and the browser check. The template scan also covers the app's own JS files, which build HTML strings.
- **Files touched:** `tests/test_csp_strict.py` (new).
- **Effort:** L (split by area like UPG-23) · **Depends on:** UPG-23 · **Risk:** a missed handler breaks a button; a headless click-through catches CSP violations.
- **What was built (2026-10-10, development-only run):**
  - **`script-src` has no `'unsafe-inline'`**; it carries a per-request nonce (`content_security_policy_nonce_in=['script-src']`, `app.py`). Since the nonce makes browsers ignore `'unsafe-inline'` anyway, every inline script and handler had to move first.
  - **Inline handlers (403 `on…=` attributes in 63 live templates):** each became `data-h-<event>="<page>:<n>"`, and its code moved, unchanged, into `static/js/handlers/<page>.js` (63 files), registered in `window.SE_H`. **`static/js/handlers.js`** (loaded by `layouts/document.html`) binds them on `DOMContentLoaded` and for elements added later (a `MutationObserver`), with the same `this`, `event`, scope chain (`with (document) / (this.form) / (this)`, as the browser does for inline handlers) and `return false` behaviour; an `<img>` that already failed or loaded gets its handler once; `<body>` load waits for `window` load. Template values that were rendered into handler code (34 handlers) now travel as `data-h-aN` attributes the code reads from `this.dataset`. Each page includes its handler file through a `handler_scripts` block (includes load theirs where they're included).
  - **Handlers that scripts build into HTML strings (51, plus 3 in `static/js`):** converted by hand to `data-h-*` with shared helpers in `handlers.js` (`se:remove-parent`, `se:remove-grandparent`, `se:remove-closest`, `se:hide`, `se:go`, `se:back`, and `se:call` with `data-call`/`data-args` JSON) or to page keys registered in that page's handler file (form builders, judge sliders, notification rows).
  - **Inline `<script>` blocks:** the 49 without template values moved unchanged to `static/js/pages/` and are loaded from the same place in the page (so execution order is unchanged); the 21 that carry template values stay inline with `nonce="{{ csp_nonce() }}"`. JSON data blocks (8) aren't executed and need no nonce.
  - **`javascript:` links (5):** "Go back" links now go to `/` and run `history.back()` through `se:back`; the closed-registration link is `href="#"` and prevents the jump.
  - Unrendered templates (UPG-15 deletes them) and `public/home.html` (listed as not rendered in `tests/html_sinks.py`) keep their inline scripts.
  - **Checked [R] in Chromium (Playwright) over every page that answers 200 for some role (240 page loads):** every `data-h-*` handler on each page is bound; **no script CSP violation** under the strict policy; no page error or console error that the same pass doesn't also show on the code before UPG-23a (the only new message is the HUD scanner reaching its camera start in headless Chromium, which before this run never loaded its QR library: the CSP blocked unpkg, fixed by UPG-24). Click-throughs: the login password toggle, the SPOC dashboard's event selection, and the form builder's add / select / rename / delete of a field drawn at run time all work. The 858-fetch crawl's text is unchanged; full pytest 893 passed, 1 skipped; the HTML-sink scan now also reads `static/js/pages/` and `static/js/handlers/` and passes (two `data-href` values use `safeUrl`).
- **To test later:** criteria 1–2 (the header has no `'unsafe-inline'` in `script-src`; no live template has an inline `<script>` without the nonce or an `on…=` attribute) and 3 (key pages load with no CSP violation; the Playwright pass used here is in the scratch harness, not in the repo yet; UPG-28 adds a browser check to the repo).
- **Acceptance criteria:**
  1. ✅ Test: the CSP header's `script-src` has no `'unsafe-inline'`. [T `tests/test_csp_strict.py::test_script_src_has_a_nonce_and_no_unsafe_inline` (no `'unsafe-inline'` or `'unsafe-eval'`; a fresh nonce per response; the page's inline scripts carry it)]
  2. ✅ Test: no template has an inline `<script>` without the nonce, and no inline `on*=` handler. [T `::test_no_template_has_an_inline_script_without_the_nonce_or_a_handler_attribute`, `::test_no_app_script_builds_an_inline_handler_into_html`]
  3. ✅ Key pages load with no CSP violation in the browser console (headless check, when available). [T `::test_key_pages_load_with_no_csp_violation_and_every_handler_bound` (23 pages, 6 roles)]

#### UPG-26 — Forms: visible labels, clear errors, a loading state and one submit per click
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-26: …" on `production-ready` (parent `0680785`) [T]
- **Evidence:** `static/js/forms.js:1-72`, `templates/layouts/document.html:20`, `routes_forms.py:228-240,480-496,539-546,598-610`, `services_idempotency.py:1-70`, `models_pg.py:640-648`, `migrations/versions/0004_submission_keys.py:1-33`
- **To test later:** criterion 1 (every form loads submit guard), criterion 2 (visible inputs have `<label for>` or `aria-label`), criterion 3 (posting registration twice quickly creates one registration), criterion 4 (payment button disabled after one click).
- **Problem:** [C at `56a014d`] The only double-submit guard is the "button loading state" in `static/js/global.js:211-229`, and only 24 of 129 templates load `global.js` (25 at `986d108`); the payment pages `payment/checkout.html` and `public/payment_gateway.html` don't. The guard also re-enables the button after 15 seconds. Labels and error messages haven't been checked across forms.
- **Who benefits:** every user, especially on slow mobile networks (double registrations, double payments).
- **What to build:** the submit guard in the shared layout for every form (payment buttons stay disabled until the result arrives); a visible label for every input; field-level error messages from the server; server-side idempotency for registration submits.
- **Files touched:** `static/js/global.js`, the layout, form templates, `routes_forms.py`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2. Found and fixed:** the roster CSV upload on `/admin/users` (UPG-10) had a file input with no label. It now has a visually hidden `<label for="roster-csv">` (`templates/admin/users.html:47-49`).
  - **Notes on the checks:**
    - The label check loads 20 pages with fields in headless Chromium (UPG-23's key pages plus forgot-password, sign-up, the SPOC's edit form and the admin's send-email page). Each visible field needs a label (`for` or wrapping), `aria-label` or `aria-labelledby`.
    - The payment check runs the real checkout page with Razorpay's `checkout.js` replaced by a stand-in and the order and verify calls answered by the test.
    - Switching the submission-key claim off lets two simultaneous copies make two registrations (1 run in 3), so the race test catches a broken key.
  - **Found, not fixed (UPG-115):** two different forms for the same email sent at the same instant (two tabs) make two registrations every time (6 of 6). The duplicate-email check is a read before the write (`routes_forms.py:647-656`).
- **Files touched:** `templates/admin/users.html`, `tests/test_forms_guard.py` (new).
- **Effort:** M · **Depends on:** UPG-23 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: every page with a `<form>` loads the submit guard (through the layout). [T `tests/test_forms_guard.py::test_the_shared_document_loads_the_guard_for_every_page` (every rendered template with a form sits on the document, which loads `forms.js`), `::test_each_key_page_with_a_form_loads_the_guard`]
  2. ✅ Test: every visible input, select and textarea has a `<label for>` or `aria-label`. [T `::test_every_visible_field_on_the_key_pages_has_a_label` (failed on the roster upload before the fix)]
  3. ✅ Test: posting the same registration twice quickly creates one registration. [T `::test_the_same_registration_sent_twice_registers_once`, `::test_two_copies_sent_at_the_same_instant_register_once`]
  4. ✅ The payment button is disabled after one click until the payment result arrives (headless check, when available). [T `::test_the_payment_button_stays_disabled_until_the_result_arrives` (headless: a second click creates no second order; cancelling re-enables it; a payment leaves it disabled as "Payment received")]

#### UPG-27 — Images: compress, lazy-load, alt text; visible keyboard focus
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-27: …" on `production-ready` (parent `07d3508`) [T]
- **Evidence:** `static/img` (797 KB total; 6 WebP images + 1 PNG), `templates/**/*.html` (111 `<img>` tags all have `alt` and `loading`), `static/css/global.css:229` (`:focus-visible` outline style).
- **To test later:** criterion 1 (static/img totals under 1.5 MB), criterion 2 (alt on every img; loading="lazy" outside first screen), criterion 3 (global.css focus-visible).
- **Problem:** [C at `56a014d`] `static/img` is 4.5 MB in 7 files: `event_slide1–4.png` are 0.8–1.06 MB each, `feature-showcase.png` 0.6 MB, `hero-banner.png` 0.39 MB. Of 111 `<img>` tags in templates, 4 have no `alt` and 77 have no `loading` attribute. Keyboard focus styles haven't been checked.
- **Who benefits:** students on mobile data; keyboard and screen-reader users.
- **What to build:** compressed images (WebP where it helps, same dimensions and look); `loading="lazy"` below the fold; `alt` on every image; a visible `:focus-visible` style in `global.css` that uses the existing tokens.
- **Files touched:** `static/img/*`, templates, `static/css/global.css`, tests.
- **Built (2026-10-18):**
  - **Tested in Part 2. Found and fixed:**
    - the profile page's avatar picker loaded its eight images eagerly below the first screen; they now load lazily (`templates/profile/dashboard.html:137`);
    - the matchmaker's script built teammate photos with no `alt` (now the person's name, escaped, and lazy; `static/js/pages/participant__matchmaker.js:98`).
  - **Notes:** `static/img` is 1.06 MB. The lazy-loading check loads UPG-23's 23 key pages at 1280×800, with the test event given a banner and a sponsor logo so images appear further down. The brand logos without a `loading` attribute all sit in the first screen, where eager loading is right. The focus check tabs through the login page in headless Chromium and needs a visible outline or focus ring on each control.
- **Files touched:** `templates/profile/dashboard.html`, `static/js/pages/participant__matchmaker.js`, `tests/test_images_and_focus.py` (new).
- **Effort:** S · **Depends on:** UPG-23 (fewer places to edit) · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ `static/img` totals under 1.5 MB. [T `tests/test_images_and_focus.py::test_static_img_is_under_1_5_mb`]
  2. ✅ Test: every `<img>` in templates has `alt`; every image outside the first screen has `loading="lazy"`. [T `::test_every_template_image_has_alt`, `::test_every_image_the_app_scripts_build_has_alt` (failed on the matchmaker), `::test_images_below_the_first_screen_load_lazily` (failed on the avatar picker)]
  3. ✅ Test: `global.css` defines a `:focus-visible` style. [T `::test_global_css_defines_a_focus_visible_style`, `::test_a_keyboard_user_sees_where_the_focus_is`]

#### UPG-28 — The student journey and the scanner work on a 375px phone
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-28: …" on `production-ready` (parent `7ea50d4`) [T]
- **Evidence:** `templates/layouts/document.html:23` (`html, body { max-width: 100%; overflow-x: hidden; }`), `templates/participant/certificate.html:20-33` (mobile container scaling), journey and scanner templates verified responsive.
- **Changed 2026-10-10 (owner, Step 0):** the certificate page's phone scaling (`templates/participant/certificate.html`) is reverted: certificate part deferred (owner, 2026-10-10). The layout's overflow safeguard stays. *(The certificate part is UPG-132, DONE 2026-10-19.)*
- **To test later:** criteria 1–3 (headless browser check of student journey discover → register → pay → ticket → scanner → feedback → certificate at 375px; scrollWidth <= innerWidth; mock camera token submit; screenshots).
- **Problem:** Not verified. Nobody has checked discover → register → pay → ticket → check-in → feedback → certificate, or the scanner pages, at phone width. `MOBILE_UX_PLAN.md` exists, but its claims weren't checked. No headless browser is set up in the repo.
- **Who benefits:** students (most use phones) and coordinators scanning on phones.
- **What to build:** a Playwright (Chromium) check, as a dev dependency, that walks the student journey and opens the scanner at 375×812 and 1280×800 with seed data, checks for horizontal scroll, and saves screenshots outside git; fix what it finds.
- **Files touched:** `tests/e2e/` (or `scripts/`), `requirements-dev.txt`, templates/CSS as needed.
- **Built (2026-10-18):**
  - **Tested in Part 2.** `tests/test_phone_journey.py` runs the app on a local server and walks it in headless Chromium at 375×812 and 1280×800:
    - log in → dashboard → events → event page → registration form, filled and sent → confirmation → ticket;
    - a paid event's form → payment page;
    - the coordinator's scanner, with the camera replaced by a stand-in that "reads" the student's ticket QR; the real check-in marks them present;
    - the feedback form.
    Every page is checked for sideways scroll and cut-off text, images or controls (UPG-23's measure). The certificate step, deferred with certificates, is UPG-132 (DONE, `tests/test_certificate_phone.py`). Playwright 1.64.0 is now in `requirements-dev.txt`. CI doesn't download Chromium, so the browser tests skip there.
  - **The screenshots showed two problems, now fixed, each with a check that fails without the fix:**
    - the payment page's "Order summary" title was navy on navy (contrast 1.1:1): the panel's white-heading rule covered `h2`/`h3`, but the title is an `h1` (`templates/payment/checkout.html:12`). Check: every heading on the journey must reach 3:1 against its background;
    - the ticket page pinned the site footer to the bottom of the screen, where it covered the ticket's own footer on a phone (and on a desktop). The footer now follows the ticket, and the page stacks as a column (`templates/participant/ticket.html:3,12-19`). Check: no text under a pinned footer at the top or the bottom of the page.
  - **Screenshots** (20, outside git): the scratch folder `shots/upg28/` for this run; set `UPG28_SHOTS` to keep them. Listed in the Part 2 summary.
- **Files touched:** `templates/payment/checkout.html`, `templates/participant/ticket.html`, `requirements-dev.txt`, `tests/test_phone_journey.py` (new).
- **Effort:** M · **Depends on:** UPG-23, UPG-26 · **Risk:** the browser download needs network access in CI.
- **Acceptance criteria:**
  1. ✅ Headless check: every journey page at 375px has `document.documentElement.scrollWidth <= innerWidth`. [T `tests/test_phone_journey.py::test_the_student_journey_and_the_scanner_fit_a_phone` (10 pages; no sideways scroll and nothing cut off. The page-wide `scrollWidth` alone over-reports when a wide table scrolls inside its own box, UPG-23)]
  2. ✅ Headless check: the scanner page loads at 375px with the camera mocked and a token can be submitted. [T same test: the scanner at 375px, camera mocked, the ticket's token "read" → the real check-in → "Checked in" and attendance Present]
  3. ✅ The phase report includes the 375px and 1280px screenshots. [screenshots at 375px and 1280px of all 10 pages, written by the test; in the Part 2 summary]

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
- *Open: full text in `docs/FEATURE_REVIEW.md`.*

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
- **Status:** DONE, except the container step (no Docker on the release machine; it is on the go-live checklist)
- **Last verified:** 2026-10-19, commit "UPG-32: …" on `production-ready` (parent `845476b`) [T]
- **Problem:** There's no deploy guide for Cloud Run + Supabase, and no end-to-end release check from a fresh clone. `docs/DEPLOY.md` has only the scheduled-jobs section (UPG-07); `docs/DEPLOYMENT.md` covers the container and settings in general. *(Corrected 2026-10-08: `README.md` has no Railway/Render deploy guide; it names Cloud Run (`README.md:287,542`) and calls Brevo "Railway-safe" (`:211`).)*
- **Who benefits:** whoever deploys and runs the app.
- **What to build:** the Phase 6 release check (fresh clone → `docker-compose up` → `alembic upgrade head` on an empty PostgreSQL → non-production seed → every role end to end at 375px and 1280px; production boot with strong dummy settings, then with one missing; restart mid-session and two instances; full pytest on SQLite and PostgreSQL, ruff, bandit, pip-audit, full-history gitleaks) and `docs/DEPLOY.md`: Cloud Run + Supabase set-up, every setting and how to generate it, the migration step, first Super Admin creation, rollback (redeploy the previous revision), backups and restore, monitoring.
- **Files touched:** `docs/DEPLOY.md`, `README.md` (link), this review (final report).
- **Built (2026-10-19):**
  - **`docs/DEPLOY.md`** is the deploy guide: Google Cloud set-up (project, region, Cloud SQL, Secret Manager, the Cloud Run service and the migration job, with the `gcloud` commands); every setting and how to make it; migrations; first Super Admin; uploads and private links; scheduled jobs (Cloud Scheduler schedules matching the table); background tasks; backups and the restore drill; rollback (redeploy the previous revision); monitoring; the release check (9 steps); and the go-live checklist of owner-only tasks. Linked from `README.md:254`.
  - **The release check**, run on 2026-10-19 from a fresh clone of `production-ready` at `eaea1fe` (scripts and logs kept outside the repo):
    1. Fresh install of `requirements-dev.txt` and Chromium in a new virtual environment: OK.
    2. `pip-audit -r requirements.txt --no-deps --disable-pip`: no known vulnerabilities (re-run after UPG-123's two new packages: still none); the environment-wide audit flagged only Werkzeug (fixed, UPG-119) and setuptools 79.0.1 (build tooling, not shipped; recorded). `gitleaks` over the full history: 3 test-only dummy secrets (fixed, UPG-118), then no leaks (re-run at `845476b`: no leaks).
    3. `ruff check .`: clean. `bandit -ll` on the tracked app files: no findings (re-run at `845476b`: none).
    4. `alembic upgrade head` on an empty PostgreSQL database: 0001 to 0007 in order (0008 since, checked by `tests/test_migrations_baseline.py` on PostgreSQL). Non-production seed (`showcase`): 72 accounts, 48 events, 544 registrations.
    5. Production boot with strong dummy settings: `/` and `/health` answer 200 with HSTS and a CSP nonce; plain HTTP redirects. With the mail provider removed, start-up is refused (exit 1) and the log names "no mail provider".
    6. Two gunicorn instances on one database: a login on A works on B, and still works after A restarts; a forged session cookie goes to `/login`.
    7. Full pytest from the clone: SQLite 1,199 passed, 7 skipped, 1 failed; PostgreSQL 1,205 passed, 1 skipped, 1 failed. The one failure on both is `tests/test_type_check_config.py::test_pyrefly_accepts_the_config_and_finds_no_errors_in_routes_coordinator`, because the clone's virtual environment wasn't at `.venv` (the test runs `.venv/bin/python`); it passes with the environment at `.venv`, and the release check now says so (`docs/DEPLOY.md` step 1).
    8. Browser pass, headless Chromium against the production build over HTTPS with real logins: 31 key pages for each of 7 roles (Super Admin, SPOC, coordinator, judge, volunteer, student, faculty) at 375px and 1280px: 0 problems after two fixes it found (UPG-120: volunteers had no login option; UPG-121: the audit log was cut off on a phone).
    9. Container (`docker compose up --build`): **not run**, Docker isn't available on this machine. Cloud Build builds the same `Dockerfile` on deploy; it's on the go-live checklist.
- **Files touched:** `docs/DEPLOY.md`, this review
- **Effort:** M · **Depends on:** every other item in phases 1–5 · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Each release-check step above passes, with its output recorded in the changelog. [R: steps 1–8 pass, with their results above and in the changelog; step 9 (container) not run, no Docker here, left to the owner]
  2. ✅ `docs/DEPLOY.md` covers every topic listed. [R `docs/DEPLOY.md`: every topic listed has its section]
  3. ✅ The final report lists every item's status, anything not DONE and why, and a go-live checklist. [R: the final report below; the go-live checklist is `docs/DEPLOY.md` "Go-live checklist"]
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** still TODO; it is Part 3 of the production-ready run. Since it was written, the browser checks it asks for are in the repo (`tests/headless.py`; UPG-23, UPG-25 to UPG-28, UPG-60) and Playwright is in `requirements-dev.txt`.
- **Final report (Part 3, 2026-10-19).** 156 items: 139 DONE (this one included, and UPG-122, 123, 130, 131 and 136 from the certificate work), 13 TODO, 2 IN PROGRESS, 1 merged (UPG-17 into UPG-21), 1 dropped (UPG-85, no new AI features). Not DONE, and why:
  - **BLK-01** (IN PROGRESS): only GitHub Support's removal of the old pull-request refs is left, which only the owner can ask for.
  - **UPG-30** (IN PROGRESS): criterion 4 is the owner's Razorpay Test Mode checkout and refund.
  - **UPG-102** (TODO): 1,044 Pyrefly type errors, mostly checker noise; a separate clean-up, not needed for go-live.
  - **UPG-117** (TODO): found in UPG-114; the JSON waitlist join refuses new events. No page calls it.
  - **UPG-124 to UPG-129, UPG-132 to UPG-135, UPG-137** (TODO): the certificate system, in scope since 2026-10-19 and being built now. The release check will be run again when it's done.
- **Go-live checklist:** `docs/DEPLOY.md` "Go-live checklist" (email, Razorpay Test Mode then live keys, Sentry, Cloud Scheduler, budget alert, `SUPPORT_EMAIL`, campus facts, the login limit, backups, the signed-link check on Cloud Run, old data, GitHub refs, the container).

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
| `JWT_SECRET_KEY` | New random value, 32+ characters, different from `SECRET_KEY` | Yes since UPG-20 (`config.production_problems`) |
| `SUPER_ADMIN_PASS` (with `SUPER_ADMIN_EMAIL`) | New strong password, used to create the first SuperAdmin | Only against the list of published passwords (`validate_production_config`) |
| `RAZORPAY_KEY_SECRET` (with `RAZORPAY_KEY_ID`) | Set before any paid event is opened | Since UPG-20, half a set-up (one or two of the key ID, key secret and webhook secret) is refused, and so is `PAYMENT_SIMULATION`; with none set, online payment refuses with 503 (fails closed since BLK-03). |
| `RAZORPAY_WEBHOOK_SECRET` | The secret set on the Razorpay webhook (Dashboard → Webhooks: URL `https://<BASE_URL>/payment/webhook/razorpay`; events `payment.captured`, `payment.authorized`, `payment.failed`, `refund.processed`, `refund.failed`, UPG-94). It completes registrations whose browser closed after paying (UPG-30). | Required with the other two Razorpay settings since UPG-20 |
| `DATABASE_URL` | PostgreSQL (`postgresql://…`) | Yes: named with every other problem at start-up (UPG-20), and the schema must be at Alembic head (UPG-16) |
| `BREVO_API_KEY` | A Brevo API key (Brevo → Settings → SMTP & API → API Keys). **Required in practice:** since UPG-33, new staff, SPOCs and walk-ins can get in only through the emailed set-password link. | Yes since UPG-20: production refuses to start with no mail provider |
| `MAIL_FROM` | The sender, e.g. `SapthaEvent <events@your-domain>`, an address verified as a sender in Brevo. Unset, the sender is `MAIL_USER`; with neither, Brevo and Resend refuse to send and `/diag/email` says why (`utils_email.py:51-61`, UPG-41). | Yes since UPG-20 (`MAIL_FROM` or `MAIL_USER`) |
| `BASE_URL` | The site's public `https://` address, e.g. the Cloud Run URL or the university domain. Every emailed, WhatsApp, QR and referral link is built from it. | Yes: production refuses a missing, `http://` or localhost value (`config.py:267-270`, BLK-16) |
| `CRON_SECRET` | New random value. Needed where Celery beat doesn't run (Cloud Run): Cloud Scheduler or GitHub Actions sends it to `/internal/cron/<job>` (`docs/DEPLOY.md`, UPG-07). | Yes since UPG-20 (24+ characters), unless `CELERY_BROKER_URL` is Redis (Celery beat) |
| `LOGIN_THROTTLE_IP_LIMIT` | **About 50** (owner, 2026-10-02). On campus Wi-Fi many students share one public IP, so the default of 5 failed logins a minute per IP would lock out a whole lab. Leave `LOGIN_THROTTLE_ACCOUNT_LIMIT` at 5. | No: it defaults to 5 (`config.py:131`, BLK-13) |

- **Use a fresh database.** If an old one is reused (the earlier Cloud SQL or Supabase database), first reset every account's password (the SuperAdmin's was the published demo password) and delete the demo accounts (BLK-10) and walk-in accounts created with the default password (UPG-15).
- **Test-send (owner, 2026-10-02).** After the first deploy, log in as the SuperAdmin and open `/diag/email?to=<your address>` (SuperAdmin-only, `routes_auth.py`). The message must arrive, not in spam, from `MAIL_FROM`. Then appoint a test judge on a test event and check that their set-password link arrives and works.
- **Proxy hops (owner, 2026-10-02).** `ProxyFix(x_for=1, x_proto=1)` (`app.py:151`) trusts exactly one proxy, which is right for Cloud Run alone; it never trusts `X-Forwarded-Host` (BLK-16). If Cloudflare or a load balancer is ever put in front, set `x_for` to the real number of proxies. Otherwise the app sees the proxy's address for every visitor, and BLK-13's per-IP limit counts everyone as one IP. Never set it higher than the real number: clients could then forge their IP in `X-Forwarded-For` and dodge the per-IP limit.
- **Check:** start the app once with these values and `FLASK_ENV=production`. It must start, and it must refuse to start if any start-up-checked value above is missing or weak (`tests/test_integration_flow.py::test_production_config_requires_real_secrets`).


#### BLK-01 — Admin credentials and a user database are in the public GitHub history
- *Open: full text in `docs/FEATURE_REVIEW.md`.*

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
  1. ✅ *(Changed by UPG-97, owner decision 2026-10-17: such a submit now registers without logging in and emails a cancel link; the test is now `::test_anonymous_submit_with_existing_email_registers_without_logging_in` and still checks that nobody is logged in.)* An anonymous submit with an existing student's email → no `user_id` in the session, a redirect to `/login?next=/forms/register/<event>`, no registration and no email; logging in returns to the form; an off-site `next` is ignored (`test_anonymous_submit_with_existing_email_must_log_in_first`, `test_login_ignores_an_off_site_next`).
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
- **Status:** DONE (the last criterion met by UPG-15: the `functions/` copy is gone, `tests/test_dead_code_and_links.py::test_the_removed_copies_and_scripts_stay_gone`; re-verified 2026-10-19)
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
- **Status:** DONE (the last criterion met by UPG-15: the `functions/` copy is gone, `tests/test_dead_code_and_links.py::test_the_removed_copies_and_scripts_stay_gone`; re-verified 2026-10-19)
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
  4. ✅ *(Registration part changed by UPG-97, 2026-10-17: registration no longer asks an existing account to log in; the test is now `tests/test_uniform_auth_messages.py::test_sign_up_still_tells_an_existing_email_to_log_in_and_registration_needs_no_login`. Sign-up and the API still answer "already exists".)* Test: sign-up (web and API) and registration with an existing email still tell the user to log in first (unchanged behaviour, now pinned: `::test_sign_up_and_registration_still_tell_an_existing_email_to_log_in`).
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
- **Status:** DONE (criterion 2, the next CI run on GitHub, waits for a push)
- **Evidence:** `git rm .github/workflows/jekyll-docker.yml`
- **Last verified:** 2026-10-19, commit "UPG-38: …" on `production-ready` (parent `5bc9d85`) [T]
- **To test later:**
  1. ✅ Test: no tracked workflow file runs Jekyll (`tests/test_repo_hygiene.py`). [T `tests/test_repo_hygiene.py::test_no_workflow_runs_jekyll`]
  2. The next CI run on GitHub shows no "Jekyll site CI" check.
- **Problem:** From the code review of PR #48 (owner, 2026-10-02). `.github/workflows/jekyll-docker.yml` is GitHub's "Jekyll site CI" sample: it builds a Jekyll site in Docker on every push and pull request to `master`. The repo has no Jekyll site (no `_config.yml` or `Gemfile`), so the check means nothing and costs CI time.
- **Who benefits:** developers (CI shows only real checks).
- **What to build:** delete the file.
- **Files touched:** `.github/workflows/jekyll-docker.yml`, `tests/test_repo_hygiene.py`.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built.** No tracked workflow mentions Jekyll, and `.github/workflows/jekyll-docker.yml` isn't tracked. Criterion 2 can only be seen on GitHub after a push, which this run doesn't do.
- **Files touched:** `tests/test_repo_hygiene.py`.
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
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-42: …" on `production-ready` (parent `1644907`) [T]
- **Problem:** Found 2026-10-07 while building UPG-41 [C]. Three public pages tell people to write to the old mail account, the one whose password was changed on 2026-09-30 (BLK-01, UPG-41):
  - `templates/public/privacy.html:60` (exercising data rights) and `:77`;
  - `templates/public/terms.html:68`;
  - `templates/payment/failed.html:43`.
  If nobody reads that inbox, privacy requests and payment problems go unanswered. The privacy notice's grievance contact is also part of the university's DPDP obligations (UPG-22).
- **Who benefits:** students and external participants who need help; the university (privacy requests reach someone).
- **What to build:** one contact address from a setting (e.g. `SUPPORT_EMAIL`, documented in `.env.example`), used by all three pages. When it's unset, the pages show no address rather than a personal one.
- **Needs from the owner:** ~~the contact address (D-4).~~ Decided 2026-10-10: `events@your-university-domain` (D-4).
- **Files touched:** `config.py` or a context processor in `app.py`, the three templates, `.env.example`, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** With `SUPPORT_EMAIL` set, `/privacy`, `/terms` and `/payment/failed` each show it as a `mailto:` link; unset, none has a `mailto:`. The old team account's address is in no tracked file outside the plan docs.
- **Files touched:** `tests/test_contact_and_links.py` (new; also holds UPG-46's tests).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **What was built (2026-10-10, owner's second run; D-4):** the address comes from the `SUPPORT_EMAIL` setting through a template context value (`app.py`, `inject_auth_features`). The privacy page (rights and contact), terms page (contact) and payment-failed page show it as a `mailto:` link when it's set, and no address when it isn't (the privacy page then points to the profile page's data tools). The old Gmail address is gone from every tracked file. `.env.example` documents `SUPPORT_EMAIL` with the placeholder `events@your-university-domain`; the owner sets the real value in the deployment. Checked by hand [R]: with it unset, the three pages answer 200 with no `mailto:`; set to a test address, all three show it.
- **To test later:** criteria 1–2.
- **Acceptance criteria:**
  1. ✅ Test: with `SUPPORT_EMAIL` set, the privacy, terms and payment-failed pages show it, and no tracked template outside `functions/` and `scratch/` contains the old account's address. [T `tests/test_contact_and_links.py::test_the_contact_pages_show_support_email`, `::test_the_old_account_is_in_no_tracked_file`]
  2. ✅ Test: with it unset, those pages render without a `mailto:` link. [T `::test_without_support_email_the_pages_show_no_address`]

#### UPG-43 — Event-day lists show only events whose status is the old `active`
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-43: …" on `production-ready` (parent `cf71222`) [T]
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
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.**
  - **Found:** the scanner list falls back to the invented venue "SNPSU Campus" (`routes_coordinator.scanner_selector`). It's logged as a new item, not fixed here.
- **Files touched:** `tests/test_event_day_statuses.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **What was built (2026-10-10, development-only run):**
  - One helper: `services_workflow.EVENT_DAY_STATUSES` (published, registration open or closed, in progress, and the old `active`) and `is_event_day_status` (`services_workflow.py:63-71`), plus `REGISTRATION_OPEN_STATUSES`.
  - The coordinator's scanner list and walk-in form query those statuses (`routes_coordinator.py:549,638`); venue-QR self check-in accepts them and refuses the rest (`routes_checkin.py:78,103`).
  - The day-before and 3-day reminders read every event-day status, and the velocity alert reads events still taking registrations (`tasks/scheduled_tasks.py:21,48,246,379`); the lifecycle job's `RUNNING`/`REGISTRATION_OPEN` are now these constants.
  - The judge dashboard is left for UPG-04 (Phase 6), as the item says.
- **To test later:** criteria 1–4 below (real database): the scanner list and walk-in form list a `registration_open` event today and not a `cancelled` one; venue self check-in for `in_progress` vs `cancelled`; the day-before reminder through `/internal/cron/reminders` for a `registration_closed` event tomorrow and not a `cancelled` one. Existing `tests/test_cron.py` and `tests/test_notices.py` use `active` events and still pass.
- **Acceptance criteria:**
  1. ✅ Test (real DB): an assigned coordinator's scanner list shows today's `registration_open` event; a `cancelled` one isn't listed. [T `tests/test_event_day_statuses.py::test_the_scanner_list_and_walk_in_form_show_open_events_not_cancelled_ones`]
  2. ✅ Test: the walk-in form lists the same event. [T same test (`/coordinator/on_spot`)]
  3. ✅ Test: venue self check-in works for an `in_progress` event and refuses a `cancelled` one. [T `::test_venue_self_check_in_works_while_running_and_not_when_cancelled` (a signed venue code; `in_progress` marks Present; `cancelled` answers 400 "This event is not running")]
  4. ✅ Test: the day-before reminder, through `/internal/cron/reminders`, reaches registrants of a `registration_closed` event tomorrow, and not of a `cancelled` one. [T `::test_the_day_before_reminder_reaches_closed_registration_events_not_cancelled_ones` (cron endpoint, Brevo's API mocked, network blocked)]
- **Not scheduled yet:** it fits Phase 2 next to UPG-29 (owner's call).

#### UPG-44 — An empty payment status reads back as `unpaid` (postgres mode)
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-44: …" on `production-ready` (parent `ad988a5`) [T]
- **Problem:** Found while building UPG-02 [R]. A registration written with `payment_status: ''` reads back as `'unpaid'` on the SQL adapter: the enum column gets its default and the read returns it. Every live registration path sets a status (form, waitlist, walk-in, payment), so this affects old, seeded or imported rows. Reports then count them as unpaid. Before UPG-02's rule (a free event owes nothing), such an attendee would have been refused at the gate.
- **Who benefits:** organisers reading payment figures.
- **What to build:** an empty or missing payment status reads back as written, as other fields do since BLK-06b; an explicit `unpaid` still reads `unpaid`.
- **Files touched:** `db_adapter.py`, tests. Touches a shared file: run rule 8's early pass.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** PostgreSQL for this run comes from `pgserver` (PostgreSQL 16.2 in the project's environment, dev only); the tests use it through `TEST_DATABASE_URL`, confirmed by the engine's dialect.
- **Files touched:** `tests/test_empty_payment_status.py` (new).
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** low.
- **What was built (2026-10-10, owner's second run):** when the SQL layer overlays the stored document on the columns, an empty or missing `payment_status` now reads back as written instead of the enum column's default `unpaid` (`EMPTY_READS_BACK`, `db_adapter.py:696`, used in `_merge_shadow`). An explicit `unpaid` still reads `unpaid`, and the `payment_status == 'unpaid'` filter finds only it (the filter compares the document value). Checked by hand [R] on SQLite and PostgreSQL 16: `''` → `''`, missing → missing, `'unpaid'` → `'unpaid'`, `'Paid'` → `'Paid'`; the filter returns only the explicit one; updating the empty one to `unpaid` reads `unpaid`. Adapter, filter, payment, export and check-in tests pass.
- **To test later:** criterion 1 (SQLite and PostgreSQL). Touches `db_adapter.py` (a shared file); rule 8 is off for this run.
- **Acceptance criteria:**
  1. ✅ Test (SQLite and PostgreSQL): `''` and a missing `payment_status` read back as `''` and missing; `'unpaid'` reads back `'unpaid'`; filters on `payment_status == 'unpaid'` find only the explicit one. [T `tests/test_empty_payment_status.py::test_empty_and_missing_payment_status_read_back_as_written`, passing on **SQLite and PostgreSQL 16.2**; it also checks that writing `unpaid` over an empty status reads `unpaid`]

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
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-46: …" on `production-ready` (parent `869741f`) [T]
- **Problem:** Found while building UPG-07 [C]. The coordinators' day-before briefing links `https://sapthaevent.in/coordinator/scanner` (`tasks/scheduled_tasks.py:183`), and the SPOC's velocity alert links `https://sapthaevent.in/forms/register/<event>` (`:416`). BLK-16 moved every other emailed link to `BASE_URL`; these two point at a domain the deployment may not use.
- **Who benefits:** coordinators and SPOCs who click the link.
- **What to build:** both links built from `BASE_URL`, like the other emails (BLK-16's helper).
- **Files touched:** `tasks/scheduled_tasks.py`, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** The real tasks run (`send_24h_reminders`, `check_registration_velocity`), with the generic email task captured and `BASE_URL=https://events.example.edu`. Every link in the coordinators' briefing and the SPOC's low-registration alert starts with that host, and the briefing's scanner link reaches a real route. Making the helper return the old domain fails both tests. Both emails still name an invented venue when an event has none (now part of UPG-111).
- **Files touched:** `tests/test_contact_and_links.py`.
- **Effort:** S · **Depends on:** BLK-16 · **Risk:** low.
- **What was built (2026-10-10, owner's second run):** `tasks/scheduled_tasks.py` builds both links from `BASE_URL` through a `_base_url()` helper (it uses `utils_email._base_url`, BLK-16's): the coordinators' day-before briefing (in `send_24h_reminders`) links `<BASE_URL>/coordinator/scanner`, and the SPOC's velocity alert (`check_registration_velocity`) links `<BASE_URL>/forms/register/<event>`. No tracked file mentions `sapthaevent.in` any more. Checked by hand [R] with `BASE_URL=https://events.example.edu`: both emails link only to `events.example.edu`.
- **To test later:** criterion 1.
- **Acceptance criteria:**
  1. ✅ Test: with `BASE_URL=https://events.example.edu`, the briefing and the velocity alert link only to that host; `sapthaevent.in` appears in neither. [T `tests/test_contact_and_links.py::test_the_coordinator_briefing_links_to_base_url`, `::test_the_low_registration_alert_links_to_base_url`]
- **Not scheduled yet** (owner's call; it fits next to UPG-31).

#### UPG-47 — Events saved without times get the save time as their start and end (postgres mode)
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-47: …" on `production-ready` (parent `aae62ea`) [T]
- **Problem:** Found while building UPG-07 [R]. The SQL adapter stores an event's `start_datetime` and `end_datetime` through `parse_datetime`, which returns *now* for an empty value (`db_adapter.py:1126-1127,1938-1940`). The SPOC's create form sends neither, so every such event reads back with its save time as start and end, not its `date`. Readers trust them [C]:
  - room-conflict checks (`services_venue.py:377,408,463`, `services_workflow.py:204`) compare the wrong times;
  - the calendar feeds read `start_datetime` before `date` (`app.py:1069-1070,1106-1111`), so they place each event at its save time;
  - UPG-07's lifecycle job works around it by using the later of `date` and `end_datetime`.
- **Who benefits:** SPOCs booking rooms; anyone reading the calendar.
- **What to build:** an empty start or end reads back empty (or derived from `date` and `time`), not the save time; readers fall back to `date`.
- **Files touched:** `db_adapter.py`, tests. Touches a shared file: run rule 8's early pass.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** Since UPG-73's wizard, an event created through the SPOC form with no time is stored as its date's whole day, 00:00–23:59 (criterion 1's "one on its date"), and its page says "Time to be announced". The adapter's own fix still matters for events saved with no times at all (API v1 drafts, seeds): they read back with none. Restoring the old "save time" fallback (`db_adapter.py:1157-1158`) fails that test. Room clashes for time-less events go by the date. Passes on SQLite and PostgreSQL 16.
- **Files touched:** `tests/test_untimed_events.py` (new).
- **Effort:** S · **Depends on:** BLK-06 · **Risk:** existing rows already hold save times; decide whether to clear them (a one-off script) or leave them.
- **What was built (2026-10-10, owner's second run):**
  - **Times stay empty.** Creating an event on the SQL layer no longer stores the save time when no start or end is given: `start_datetime` and `end_datetime` stay empty (`db_adapter.py`, the events branch of `_dict_to_new_record`). Updates already kept empty times empty. Existing rows aren't changed (the item's open question: they keep their save times; a one-off clean-up would need the owner's go-ahead).
  - **"Time to be announced"** shows where the event's time is empty: the public event page (hero and timeline), the coordinator's scanner list and the SPOC dashboard's event panel. The calendar feeds and calendar links already fall back to the date.
  - **Room clashes still work without times.** A booking whose end isn't after its start (an event saved without times) now holds two hours from its start, like the requested slot already did, so two time-less events in one room on the same day clash and on different days don't (`services_venue.check_room_conflict`).
  - Checked by hand [R]: an event saved without times reads back with no start or end and its page says "Time to be announced"; the same-day booking clashes, the next day's doesn't. Venue, calendar, adapter and cron tests pass.
- **To test later:** criteria 1–2.
- **Acceptance criteria:**
  1. ✅ Test (real DB): an event created through the SPOC form reads back with no `end_datetime` (or one on its `date`), never its save time. [T `tests/test_untimed_events.py::test_an_event_saved_without_a_time_has_no_start_or_end` (the form: the date's whole day, never the save time), `::test_the_database_layer_keeps_missing_times_empty` (no times through the SQL layer: none back)]
  2. ✅ Test: a room conflict check for an event saved without times uses its date: a second event in the same room on that date and time clashes, one on another day doesn't. [T `::test_untimed_events_clash_by_their_date` (same day clashes, the next day doesn't)]
- **Not scheduled yet** (owner's call).

#### UPG-48 — Team members get no confirmation, reminder or notice
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-48: …" on `production-ready` (parent `baeb512`) [T]
- **Problem:** Found while building UPG-31 [C]. Since UPG-08 a team's members are on the registration and can open its ticket, but every message goes to the lead only: the confirmation (`routes_forms.py:702`), the day-before ticket and the 3-day reminder (`tasks/scheduled_tasks.py:81,279`), and the change and cancellation notices (`services_venue.py:550`, `services_workflow.py:300`). Members find out only from the lead.
- **Who benefits:** every team member.
- **What to build:** each member with an email gets the day-before ticket (with the same QR) and the change and cancellation notices, once each, keyed per person; the confirmation tells members they were added.
- **Files touched:** `tasks/scheduled_tasks.py`, `services_venue.py`, `services_workflow.py`, `routes_forms.py`, `routes_teams.py`, tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** The team of three includes a member whose email is in capitals.
- **Files touched:** `tests/test_team_member_notices.py` (new).
- **Effort:** S · **Depends on:** UPG-08, UPG-31 · **Risk:** more email volume (Brevo's free tier allows 300 a day).
- **What was built (2026-10-10, owner's second run):**
  - **One list of recipients per registration:** `services_recipients.registration_people` gives the lead and every team member with an email, each once (case-insensitive), with name and phone.
  - **Confirmation:** each member the lead listed gets the confirmation, saying who added them to which team (`routes_forms.submit_form`; `utils_email.send_registration_confirmed_email` gained `added_by`/`team_name`); someone who joins with the invite code gets it too (`routes_teams.join_team`; a repeat join stops before it, so once).
  - **Day-before ticket (with the entry QR) and 3-day reminder** (`tasks/scheduled_tasks.py`): sent to each person once; the registration remembers who has them (`ticket_sent_to`, `early_reminder_sent_to`) as well as the old `ticket_sent`/`early_reminder_sent` flags. The WhatsApp reminder goes to each person with a phone.
  - **Change and cancellation notices** (`services_venue.notify_event_details_changed`, `services_workflow._notify_participants_of_cancellation`): every person on each registration, under the existing per-email idempotency keys.
  - Checked by hand [R] with a team of three (one email in capitals): the day-before and 3-day jobs run twice, a venue change sent twice, and a cancellation sent twice each reach each member exactly once. Notice, cron, team, form, account-email and workflow tests pass.
  - Not changed: people who join a team after its day-before ticket went out don't get a late ticket (they can open it from the team page).
- **To test later:** criteria 1–2, plus the member confirmation at registration and on joining.
- **Acceptance criteria:**
  1. ✅ Test: for a team of three, the day-before reminder through the cron endpoint emails each member once. [T `tests/test_team_member_notices.py::test_the_day_before_ticket_reaches_each_member_once` (cron run twice)]
  2. ✅ Test: a venue change and a cancellation reach each member once. [T `::test_a_venue_change_and_a_cancellation_reach_each_member_once` (each sent twice)]
- **Not scheduled yet** (owner's call).
  - "To test later" extra: `::test_listed_members_and_a_joiner_get_the_confirmation_once` (listed members at registration; a joiner by code, joining twice).

#### UPG-49 — The automation's WhatsApp channel calls a function that doesn't exist
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-49: …" on `production-ready` (parent `dfd7cef`) [T]
- **Problem:** Found while building UPG-31 [C]. `services_automation.dispatch_trigger` sends WhatsApp through `utils_whatsapp.send_whatsapp_message` (`services_automation.py:223`), which doesn't exist; the error is caught and recorded as `whatsapp_fallback`. The default rules for check-in and event reminders use that channel (`services_automation.py:51,75`), so those WhatsApp messages never go out.
- **Who benefits:** participants who opt in to WhatsApp.
- **What to build:** the channel sends through `utils_whatsapp._send`, and a failure is recorded as a failure, not a fallback.
- **Files touched:** `services_automation.py` or `utils_whatsapp.py`, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** Twilio is replaced by a stand-in client. For a user who opted in, one message goes to their number in WhatsApp format, through a custom rule and through the default event-reminder rule. Someone who didn't opt in gets none; without Twilio settings the channel is skipped and no client is made; a refused send is recorded as `whatsapp (failed)`, never as a fallback.
- **Files touched:** `tests/test_whatsapp_and_escaping.py` (new; also holds UPG-50's tests).
- **Effort:** S · **Depends on:** none · **Risk:** low; nothing goes out without Twilio settings.
- **What was built (2026-10-10, owner's second run):** `utils_whatsapp.send_whatsapp_message(phone, body)` exists now (it sends through `_send`, Twilio) together with `whatsapp_configured()`. The automation's WhatsApp channel (`services_automation.NotificationAutomationEngine.dispatch_trigger`) is off cleanly when Twilio isn't configured (recorded as skipped "whatsapp (not configured)", nothing attempted); when it is configured, it sends to a user who opted in and records a failed send as "whatsapp (failed)", no longer as a "fallback". Checked by hand [R] with Twilio mocked: configured and opted in → one Twilio call, channel dispatched; not configured → skipped, no call. Automation, notice and notification tests pass.
- **To test later:** criterion 1, plus the unconfigured and failed cases.
- **Acceptance criteria:**
  1. ✅ Test: a trigger with the WhatsApp channel, for a user who opted in, calls the Twilio client once (mocked). [T `tests/test_whatsapp_and_escaping.py::test_an_opted_in_user_gets_one_whatsapp_message`, `::test_the_default_reminder_rule_reaches_whatsapp_too`; extras: `::test_a_user_who_didnt_opt_in_gets_none`, `::test_without_twilio_settings_the_channel_is_off`, `::test_a_refused_send_is_a_failure_not_a_fallback`]
- **Not scheduled yet** (owner's call).

#### UPG-50 — Email templates insert names and titles without escaping
- **Status:** DONE (the certificate email, deferred with certificates, is UPG-133, DONE)
- **Last verified:** 2026-10-19, commit "UPG-50: …" on `production-ready` (parent `cb9fa04`) [T]
- **Problem:** Found while building UPG-31 [C]. The HTML emails put the recipient's name, the event title and messages straight into the markup (for example `utils_email.py:499,501,563,565,744,764,793`). A name typed at registration, or an event title, containing HTML is rendered as HTML in the email. Today the typed text mostly reaches its own author or comes from staff (titles, broadcast messages), so the risk is low; the notices from UPG-31 already escape.
- **Who benefits:** everyone who gets email from the app.
- **What to build:** escape every value inserted into an email template (one helper), keeping the templates' own markup.
- **Files touched:** `utils_email.py`, `tasks/scheduled_tasks.py` (the briefing and 3-day emails), tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** The real confirmation is built and captured at `_send` (`real_app` normally stubs it out). A registrant named `<b>Ann</b>` for "Fest & <i>Fun</i>" sees both as text. The coordinators' briefing and the 3-day reminder (run through their tasks) show the title as text, and an attendee named `<script>x</script>` doesn't reach the reminder's HTML as markup. Making `_e` a no-op fails both tests. The certificate email stays deferred.
- **Files touched:** `tests/test_whatsapp_and_escaping.py`.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **What was built (2026-10-10, owner's second run):** one helper `_e()` (`utils_email.py`, and the same in `tasks/scheduled_tasks.py`) escapes every value put into an email's HTML: names, emails, event titles, dates, venues, rooms, roles, links, scores and messages, in the confirmation, ticket, credentials, password reset and set-password, receipt, refund, appointment, result, broadcast, room-assignment and advancement emails and in each email's `<title>`; and in the coordinators' day-before briefing, the 3-day reminder and the SPOC's velocity alert. Subjects stay plain text (they aren't HTML). The broadcast message is now text, like the notices (UPG-31). Checked by hand [R]: a registrant named `<b>Ann</b>` for "Fest & <i>Fun</i>" gets the text, not markup. Email tests (notices, sender, account emails, paid events, cron, links, tasks) pass.
  - **Certificate part deferred (owner, 2026-10-10):** the certificate email (`utils_email._send_cert_email`) was left unchanged then; UPG-133 (2026-10-19) escapes it and the new certificate email.
- **To test later:** criterion 1, plus the briefing and 3-day emails with a title containing markup.
- **Acceptance criteria:**
  1. ✅ Test: a registrant named `<b>Ann</b>` gets a confirmation that shows the text `<b>Ann</b>`, not bold. [T `tests/test_whatsapp_and_escaping.py::test_a_name_with_markup_shows_as_text_in_the_confirmation`, `::test_the_briefing_and_the_3_day_reminder_show_a_title_as_text`]
- **Not scheduled yet** (owner's call).

### G. Added 2026-10-10 (owner's run prompt)

#### UPG-51 — Cancelling a paid event refunds nobody
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-51: …" on `production-ready` (parent `72bac11`) [T]
- **Problem:** [C] Cancelling an event (`services_workflow.WorkflowEngine.transition_event` → `cancelled`) sends the cancellation notice (UPG-31) but touches no payment. The admin's refund action (`routes_admin.py:527`, `services_payments.start_refund`, `services_payments.py:265`) only refunds paid orders that have **no** registration, so the paid registrations of a cancelled event can only be marked "refunded" by hand, with the money returned outside the app.
- **Who benefits:** paying participants of a cancelled event; the finance office.
- **What to build:** when an event is cancelled, its staff and the Super Admin see its paid registrations, with a "Refund all through Razorpay" action: a confirm step (ticked box and the total), one Razorpay refund per payment, never twice (an atomic claim per order, as in UPG-30), failures listed with their reason and retryable, every refund audit-logged and emailed to the student.
- **Files touched:** `routes_admin.py`, `services_payments.py`, `utils_email.py`, `templates/admin/payments.html` (or a new cancelled-event refunds page), tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** The shared Razorpay fake in `tests/test_paid_events.py` gains two hooks: `refund_fail` (a payment's refund raises) and `during_refund` (run something while a refund call is in flight).
- **Files touched:** `tests/test_cancelled_event_refunds.py` (new), `tests/test_paid_events.py` (fake hooks only).
- **Effort:** M · **Depends on:** UPG-30 · **Risk:** moves real money; the confirm step and the per-order claim guard it.
- **What was built (2026-10-10, development-only run):**
  - **Page `/admin/events/<event_id>/refunds`** (`routes_admin.event_refunds`; `templates/admin/event_refunds.html`): every paid registration of the event with its amount, payment ID and refund state (to refund, in progress, refunded with the refund ID, failed with the reason, or "no Razorpay order on record: refund by hand"). Open to the Super Admin and anyone who may edit the event (its owner SPOC); others 403 (`_refund_event_or_abort`).
  - **"Refund all through Razorpay"** (`POST /admin/events/<event_id>/refund_all`, `routes_admin.refund_all`): only for a cancelled event; needs the ticked confirmation, which states the count and total. Each payment is claimed atomically on its order (`services_payments.start_registration_refund`: paid and linked to a registration → `refunding`), refunded once with its payment ID and amount, then recorded (`finish_refund`), the registration set `Refunded`/`cancelled` with the refund ID, an audit line `PAYMENT_REFUNDED`, and an email to the student (`utils_email.send_refund_email`). A failed call puts the order back to paid with its reason (`refund_failed`), listed on the page; pressing again retries only those.
  - **Where staff find it:** the admin payments page lists cancelled events that still hold payments, and cancelling a paid event from the SPOC dashboard flashes the refunds link.
  - Checked by hand [R] with Razorpay mocked: 3 paid registrations listed; no confirmation → no call; with it, 3 calls (one failing with "gateway timeout", shown as failed), 2 emails; the retry calls only the failed one and emails it; a third press calls nothing; 3 audit lines; another SPOC gets 403 on both routes, the owner 200; a non-cancelled event is refused.
- **To test later:** criteria 1–4 below; also two concurrent "refund all" requests call Razorpay once per payment, and a registration without an order is listed for a manual refund.
- **Acceptance criteria:**
  1. ✅ Test (Razorpay mocked): a cancelled event with 3 paid registrations lists all 3; "Refund all" without the confirmation does nothing. [T `tests/test_cancelled_event_refunds.py::test_refund_all_needs_the_confirmation_then_refunds_each_payment_once`]
  2. ✅ Test: with the confirmation, the refund API is called once per payment with its ID and amount; each is recorded, audit-logged and emailed once; pressing again calls nothing. [T same test: one call per payment with its ID and ₹250, each order `refunded` with its refund ID, the registration `Refunded`/`cancelled`, one email and one `PAYMENT_REFUNDED` line each; a second press calls nothing]
  3. ✅ Test: one failed refund is listed with its reason, the others complete; retrying refunds only the failed one. [T `::test_a_failed_refund_is_listed_and_only_it_is_retried`]
  4. ✅ Test: a non-admin who isn't the event's owner gets 403; refunds are refused for an event that isn't cancelled. [T `::test_only_the_admin_and_the_owner_may_refund_and_only_a_cancelled_event`]
  - "To test later" extras: `::test_two_requests_at_once_refund_each_payment_once` (a second "refund all" runs to completion inside the first request's first Razorpay call; each payment is still refunded once, with 3 audit lines), `::test_a_registration_without_an_order_is_listed_for_a_manual_refund`.

#### UPG-52 — Joining a team can overwrite another join or exceed `team_max`
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-52: …" on `production-ready` (parent `74a7e81`) [T]
- **Problem:** [C] `routes_teams.join_team` (`routes_teams.py:64-102`) reads the registration's `members`, checks `len(members) >= team_max` (`:91`), appends, and writes the whole list back (`_save_members`, `:51`). Two people joining at once both read the same list: the second write drops the first member, or both pass the size check and the team exceeds `team_max`.
- **Who benefits:** team leads and members of hackathons and sports events.
- **What to build:** adding a member is atomic: a row lock (`SELECT … FOR UPDATE` on PostgreSQL) or a conditional update that only succeeds if `members` is unchanged, retried a few times; the size check runs inside it.
- **Files touched:** `routes_teams.py`, `db_adapter.py` (or a small SQL helper), tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** Two threads call `routes_teams._add_member` released together by a barrier, for 5 rounds.
  - **The test catches the bug:** with the row lock removed (and a short pause between counting and inserting), the one-place test fails with both joins added.
- **Files touched:** `tests/test_team_join_race.py` (new).
- **Effort:** S · **Depends on:** UPG-08 · **Risk:** touches the adapter (rule 8's early pass when tested).
- **What was built (2026-10-10, development-only run):** `routes_teams._add_member` (`routes_teams.py:55`) adds a member in one transaction on the SQL layer: it locks the registration row (`SELECT … FOR UPDATE`), counts its `team_members` rows, refuses a duplicate or a full team, and inserts the one new member row, instead of rewriting the whole list. `join_team` keeps its early checks for clear messages and uses `_add_member` for the decision (`'added'`, `'full'`, `'already'`). Firestore mode (legacy) keeps the read-then-write. Checked by hand [R] on PostgreSQL 16, five rounds each: two simultaneous joins to a team with one free place left exactly one new member and the team at `team_max` (4); with two free places, both joined. Existing `tests/test_teams.py` passes. On SQLite `FOR UPDATE` is ignored (writes are serialised by the file lock), so the race guarantee is PostgreSQL's.
- **To test later:** criteria 1–2 below (PostgreSQL, concurrent joins).
- **Acceptance criteria:**
  1. ✅ Test (PostgreSQL): two joins to a team with one free place, run concurrently, leave exactly one new member and `team_max` holds. [T on **PostgreSQL 16.2**: `tests/test_team_join_race.py::test_two_joins_for_the_last_place_leave_exactly_one` (5 rounds: `added` + `full`, team at 4). Skipped on SQLite, where writes are serialised.]
  2. ✅ Test: two joins to a team with two free places, run concurrently, keep both members. [T `::test_two_joins_with_two_free_places_keep_both` (PostgreSQL: concurrent, 5 rounds; SQLite: one after the other)]

#### UPG-53 — The home page shows a fake hackathon when there are no events
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-53: …" on `production-ready` (parent `701c14b`) [T]
- **Evidence:** `app.py:698`, `templates/index.html:1186-1196`
- **Problem:** [C] When no event is listed, the home page builds a demo event (`app.py:704-706`, id `demo-hackathon-2026`, "SapthaHack 2026 — National AI Hackathon") and shows it as if it were real. Its links go nowhere real.
- **Who benefits:** visitors (no fake event); the university (nothing misleading on launch day).
- **What to build:** with no events, the home page shows an empty state ("No upcoming events yet") instead.
- **Files touched:** `app.py`, `templates/public/home.html` (or the home template in use), tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** The app starts in a subprocess on a fresh database with no events (the test checks the count is 0). `/` answers 200 with "No Events Currently Listed" and neither `demo-hackathon-2026` nor "SapthaHack 2026".
- **Files touched:** `tests/test_home_empty_and_app_config.py` (new; also holds UPG-54's tests).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: with no events, `/` returns 200, shows the empty state and doesn't contain `demo-hackathon-2026` or "SapthaHack 2026". [T `tests/test_home_empty_and_app_config.py::test_with_no_events_the_home_page_shows_its_empty_state`]
- **To test later:**
  - Verify `/` returns 200, renders the empty state ("No Events Currently Listed") and contains neither `demo-hackathon-2026` nor "SapthaHack 2026" when no events exist in the database.

#### UPG-54 — The Android app loads an old Railway URL
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-54: …" on `production-ready` (parent `cbd5e5c`) [T]
- **Evidence:** `capacitor.config.json`, `scripts/configure_capacitor.py`, `package.json:8`, `docs/DEPLOY.md:252-269`
- **Problem:** [C] `capacitor.config.json:5-6` points the Android webview at `https://saptha-portal.railway.app`, a retired host; `allowNavigation` lists `*.railway.app` and `*.firebaseapp.com`. An APK built today opens a dead site.
- **Who benefits:** students using the Android app.
- **What to build:** the server URL comes from `BASE_URL` at build time (a `capacitor.config.ts` or a small script that writes the JSON before `npx cap sync`); `allowNavigation` holds only that host; the build steps are documented.
- **Files touched:** `capacitor.config.json` (or `.ts`), `package.json` script, `docs/DEPLOY.md`, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** No tracked Capacitor config, nor the config script or `package.json`, mentions `railway.app` or `firebaseapp.com`. The config step, run with `BASE_URL=https://events.example.edu/` into a temporary file, writes that URL (trailing slash dropped) and only that host in `allowNavigation`; `package.json`'s `cap:config` runs it. The committed `capacitor.config.json` holds the placeholder host, which the build step replaces.
- **Files touched:** `tests/test_home_empty_and_app_config.py`.
- **Effort:** S · **Depends on:** none · **Risk:** low; the Flutter app under `~/development/saptha_app` is separate.
- **Acceptance criteria:**
  1. ✅ Test: no tracked file outside `functions/` and `scratch/` contains `railway.app` in the Capacitor config. [T `tests/test_home_empty_and_app_config.py::test_the_capacitor_config_never_points_at_railway`]
  2. ✅ Test: running the config step with `BASE_URL=https://events.example.edu` gives a config whose server URL and `allowNavigation` use only that host. [T `::test_the_config_step_writes_only_the_base_url_host`]
- **To test later:**
  - Verify `capacitor.config.json` contains no reference to `railway.app`.
  - Verify running `scripts/configure_capacitor.py` with `BASE_URL=https://events.example.edu` sets `url` to `https://events.example.edu` and `allowNavigation` to `["events.example.edu"]`.

#### UPG-55 — Google sign-in and 2FA exist but nothing links to them
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-55: …" on `production-ready` (parent `22e20d7`) [T]
- **Evidence:** `app.py:425-443`, `templates/login.html:206-215`, `templates/profile/dashboard.html:238-285`, `auth_oauth.py:35`, `auth_2fa.py:169-181`
- **Problem:** [C] `auth_oauth.py` serves `/auth/google` and `auth_2fa.py` serves `/auth/2fa/*`, but no template links to either (`grep -rn 'auth/google\|auth/2fa' templates` finds nothing). Users can't find them. (The matchmaker's `MOCK_STUDENTS`, also on the launch list, is already UPG-14 criterion 4.)
- **Who benefits:** every user (one-click login, a second factor for staff accounts).
- **What to build:** a "Sign in with Google" button on the login page only when Google OAuth is configured; a "Two-factor authentication" section on the profile page (set up / turn off) only when 2FA is available. UPG-10 later restricts Google sign-in to the university domain.
- **Files touched:** `templates/login.html`, the profile template, `app.py` (a context flag), tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.**
- **Files touched:** `tests/test_google_and_2fa_links.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: with Google OAuth configured, the login page links `/auth/google`; without it, it doesn't. [T `tests/test_google_and_2fa_links.py::test_the_login_page_links_google_only_when_configured` (and `/auth/google` redirects to Google's consent page)]
  2. ✅ Test: the profile page links the 2FA set-up when 2FA is available and not when it isn't. [T `::test_the_profile_offers_2fa_only_when_available` (and `/auth/2fa/setup` opens, 200)]
- **To test later:**
  - Verify `/login` displays the "Sign in with Google" button linking `/auth/google` when `OAUTH_GOOGLE_CLIENT_ID` or `GOOGLE_CLIENT_ID` is set, and omits it when empty.
  - Verify `/profile/` displays the 2FA section with "Set Up 2FA" linking `/auth/2fa/setup` when 2FA dependencies are available, and omits the section when unavailable.

#### UPG-56 — Checkout has no coupon field
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-56: …" on `production-ready` (parent `5525921`) [T]
- **Evidence:** `routes_payment.py:97,231-285`, `templates/payment/checkout.html:45-140`
- **Problem:** [C] The server applies a coupon validated on the server when `create_order` gets one (`services_payments.server_price`, `services_payments.py:77`; uses held since UPG-36), but no template or script sends one: `grep -rni coupon templates static/js` finds only marketing copy.
- **Who benefits:** organisers running discounts; students with a code.
- **What to build:** a coupon field on the checkout page with an "Apply" button that shows the server's price (fee, discount, total) before paying, and sends the code with the order. The server's price stays the only price.
- **Files touched:** `templates/payment/checkout.html`, its script, `routes_payment.py` (a price-preview endpoint if needed), tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.**
- **Files touched:** `tests/test_checkout_coupon.py` (new).
- **Effort:** S · **Depends on:** UPG-36 · **Risk:** low; the server already validates.
- **Acceptance criteria:**
  1. ✅ Test: the checkout page has a coupon input and its script sends the code with the order. [T `tests/test_checkout_coupon.py::test_the_checkout_page_has_a_coupon_field_whose_code_goes_with_the_order`, `::test_the_order_is_priced_with_the_code_on_the_server` (₹500 less 50% → 25000 paise)]
  2. ✅ Test: the price preview with a valid code shows the discounted total from the server; an invalid code shows the server's error and the full price. [T `::test_the_preview_shows_the_servers_discount_or_its_error_and_the_full_price`]
- **To test later:**
  - Verify `templates/payment/checkout.html` renders the coupon input and "Apply" button, and passes `coupon` with `/payment/create_order`.
  - Verify `/payment/price_preview` returns `valid: True` and discounted total for a valid coupon code, and `valid: False` with server error and full price for an invalid code.

#### UPG-57 — Placement drives: eligibility rules and shortlist rounds
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-57: …" on `production-ready` (parent `eaab561`) [T]
- **Problem:** MISSING [C]. The event-type table lists placement drives as "Generic registration only": eligibility (branch, CGPA, backlogs), shortlists per round and the company's lists are kept in Excel.
- **Who benefits:** the placement cell, students, recruiting companies.
- **What to build:** eligibility rules on the event (allowed branches, minimum CGPA, maximum active backlogs), checked at registration against what the student enters (or their roster record, UPG-10); named shortlist rounds the organiser moves registrations through (selected / rejected per round); an export per round.
- **Files touched:** `routes_spoc.py` (or a new `routes_placement.py`), `routes_forms.py`, `services_export.py`, templates, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** Students come in through the admin's real roster CSV import (with `cgpa` and `backlogs`). Each drive gets a unique branch, so other tests' students don't change its eligible count. Approving everyone in `eligibility` fails six of the tests. Passes on SQLite and PostgreSQL 16.
- **Files touched:** `tests/test_placement_drives.py` (new).
- **Effort:** M · **Depends on:** UPG-01 · **Risk:** self-declared CGPA can be wrong until the roster import holds it.
- **What was built (2026-10-10, owner's second run):**
  - **On the event:** "This is a placement drive" with company, role, package and job-description link, and the eligibility rules (branches or departments, years, minimum CGPA, maximum active backlogs) on the SPOC's create and edit forms, stored as `is_placement` and `placement` (`services_placement.from_form`; rounds survive edits).
  - **Academic record from the roster:** UPG-10's CSV import reads `cgpa` (or `gpa`) and `backlogs` (or `active_backlogs`) and stores them on the student's account (`routes_admin.import_student_roster`). Admins correct them at `/admin/users/<email>/academics` (linked from the users list; numbers validated, audit-logged). Students see them on their profile page, read-only; the profile update ignores them.
  - **Registration checks eligibility** (`routes_forms.submit_form`, `services_placement.eligibility`) against the roster record, after "log in first" and before anything is created, and says why: wrong branch or year, CGPA below the minimum, too many backlogs, a value not on record, or not on the roster at all (no account is created then).
  - **The organiser's page `/placement/<event_id>`** (`routes_placement.py`, linked from the SPOC dashboard for placement events): company and rules, **eligible students on the roster against registrations**, rounds the organiser adds (e.g. Aptitude, Technical, HR), and each registrant's result per round. Ticking students and choosing a round and a result marks them shortlisted or rejected; each change sends one notice through the notification service (key per student, round and result) and is kept in the registration's history. Viewing needs `view_analytics` on the event, changes `edit_event`, exports `export_data`; others get 403.
  - **The student sees their current round** (the latest result) on their ticket page.
  - **Export per round** as CSV or Excel (`services_export.placement_round_rows`, through `to_csv`/`to_xlsx`), optionally shortlisted only.
  - Checked by hand [R] on a temporary database: a roster of three imported with CGPA and backlogs; for a CSE, year-4, CGPA ≥ 7, 0-backlog drive the CGPA-6.5 and the ECE students were refused with the reason, an unknown email was refused without creating an account, the eligible student registered; the page showed 1 eligible and 1 registered; adding Aptitude and shortlisting the student twice sent one notice; CSV and Excel exports listed them with USN, branch, CGPA and result; another SPOC got 403 on the page and the move; the ticket showed "Aptitude: Shortlisted"; the profile showed the CGPA and a profile update couldn't change it; the admin form changed another student's CGPA.
- **To test later:** criteria 1–3, plus the roster columns, the admin-only academic record, the eligible-vs-registered count, the one-notice-per-move rule and the per-round export.
- **Acceptance criteria:**
  1. ✅ Test: a student whose branch isn't allowed, or whose CGPA is below the minimum, or with too many backlogs is refused with the reason; an eligible one registers. [T `tests/test_placement_drives.py::test_an_ineligible_student_is_refused_with_the_reason` (branch, CGPA, backlogs, year), `::test_someone_not_on_the_roster_is_refused_and_no_account_is_made`, `::test_an_eligible_student_registers`; roster and admin-only record: `::test_the_roster_import_stores_cgpa_and_only_an_admin_changes_it`]
  2. ✅ Test: the organiser moves 2 of 3 registrations into round 2; the round-2 export lists exactly those 2. [T `::test_round_2_holds_the_two_moved_and_only_staff_can_move_or_export` (4 eligible against 3 registered on the page; moving twice sends one notice each; the round-2 CSV lists exactly the two; the Excel export opens)]
  3. ✅ Test: only the event's staff can move registrations or export a round. [T same test: another SPOC and a student get 403 on the page, the move and the export, and the third registration is unchanged]

#### UPG-58 — The native document store creates its table at runtime, outside migrations
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-58: …" on `production-ready` (parent `afd6daf`) [T]
- **Problem:** Found while building UPG-19 [C]. Collections with no SQL model live in `native_document_store`, which `_ensure_native_table` (`db_adapter.py:523`) creates with a raw `CREATE TABLE IF NOT EXISTS` on **every** read and write. The table isn't in `models_pg.py`, so UPG-16's baseline doesn't build it and `compare_metadata` doesn't see it; in production this is DDL at runtime (UPG-16 forbids it at start-up) and needs the app's database user to hold `CREATE`.
- **Who benefits:** whoever deploys the app (a database user with no DDL rights works); every request touching those collections (one statement fewer).
- **What to build:** a `NativeDocument` model for the table and a migration (`0003`), and `_ensure_native_table` only in development.
- **Files touched:** `models_pg.py`, `migrations/versions/`, `db_adapter.py`, tests.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.**
- **Files touched:** `tests/test_native_store_migration.py` (new).
- **Effort:** S · **Depends on:** UPG-16 · **Risk:** a production database created before this already has the table; the migration must create it only if missing.
- **What was built (2026-10-10, development-only run):** a `NativeDocument` model for `native_document_store` (`models_pg.py`, before `OutboxTask`) and migration `migrations/versions/0003_native_document_store.py`, which creates the table only if a pre-migration database doesn't already have it. `_ensure_native_table` (`db_adapter.py:526`) now runs at most once per process and never in production. Checked by hand [R] on PostgreSQL 16: `upgrade head` → 0 metadata differences; `downgrade base` → `upgrade head` → 0; with production settings, a write and a read on `announcements` (a native collection) issue no DDL, and the home page loads with none.
- **To test later:** criteria 1–2 below.
- **Acceptance criteria:**
  1. ✅ Test: `alembic upgrade head` on an empty database creates `native_document_store`, and `compare_metadata` stays empty. [T `tests/test_native_store_migration.py` on SQLite and **PostgreSQL 16.2**: after `upgrade head` the table exists and `compare_metadata` is empty]
  2. ✅ Test: with production settings, reading and writing a native collection issues no `CREATE`. [T same tests: with production settings, a write and a read on `announcements` issue no CREATE or ALTER]

#### UPG-59 — Five pages answer 500 for any role
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-59: …" on `production-ready` (parent `6980bf9`) [T]
- **Problem:** Found by UPG-23's route crawl [R], on a seeded event with one registration, the same before this run (`932afdd`) and after: `/ai/match_page/<event>`, `/exams/<event>`, `/gamification/leaderboard`, `/hackathon/submit/<event>` (Super Admin, SPOC, coordinator, judge, and the leaderboard for students too) and `/spoc/api/stats` (SPOC) answer 500. Causes not yet traced.
- **Who benefits:** whoever opens those pages (judging matcher, online exams, the XP leaderboard, hackathon submissions, SPOC dashboard stats).
- **What to build:** trace each 500 and fix it, or remove the page if UPG-15 finds it dead.
- **Files touched:** `routes_ai_matching.py`, `routes_exams.py`, `routes_gamification.py`, `routes_hackathon.py`, `routes_spoc.py`, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the code.** All six roles plus a student not registered for the event open the five pages, with the data that broke each one: a judge on the staff list with no name, the unregistered student, nobody with XP yet. None answers 500, and the people each page is for get it. The empty registration time can only occur in the document store (the SQL layer falls back to the row's creation time), so that case runs on the mock database. Undoing the stats sort fix fails it. The match-judges JSON route's 500 without an AI provider was UPG-109, fixed in Part 1.
- **Files touched:** `tests/test_five_pages_no_500.py` (new).
- **Effort:** S–M · **Depends on:** none · **Risk:** low.
- **What was built (2026-10-10, owner's second run):** each 500 traced and fixed; none of the pages was dead, so none was removed.
  - `/ai/match_page/<event>`: a judge's staff entry without a `name` raised `KeyError`; the name now falls back to the account's name, then the email (`routes_ai_matching.py:439`).
  - `/exams/<event>` and `/hackathon/submit/<event>`: someone not registered was redirected with `url_for('public.event_details')`, an endpoint of the blueprint UPG-15 removed (`BuildError`); now `event_details` (`routes_exams.py:54`, `routes_hackathon.py:46`). Two more `url_for('public.index')` redirects in `routes_hackathon.py` (`:114,143`) would have failed the same way; now `home`.
  - `/gamification/leaderboard`: dividing by the top department's XP failed when nobody had XP yet (`templates/gamification/leaderboard.html:476`).
  - `/spoc/api/stats`: sorting registrations whose `registered_at` is empty compared `None` with text; the sort keys are strings now (`routes_spoc.py:1952`).
  - Found starting this item: a development database made before UPG-11 broke every events query (UPG-61, fixed first).
  - Checked [R]: a crawl of every GET route as six roles (888 fetches) answers no 500; the five pages answer 200 for whoever may use them and redirect the others.
- **To test later:** criterion 1.
- **Acceptance criteria:**
  1. ✅ Test: each page answers 200 (or a deliberate 403/404) for each role on a seeded event; none answers 500. [T `tests/test_five_pages_no_500.py::test_the_five_pages_never_answer_500`, `::test_not_registered_is_sent_to_the_event_page`, `::test_the_stats_api_counts_every_registration`, `::test_the_stats_api_survives_a_registration_with_no_time`]
  - **Re-verified at the end of Part 1 (2026-10-17):** UPG-65 removed the Zoho round-robin "96%" fallback. With neither Zoho QuickML nor `GEMINI_API_KEY` configured, `POST /ai/match_judges/<event>` now answers a JSON error (500, the exception text) instead of an invented plan. Logged as UPG-109. The pages this item lists are otherwise unchanged.

#### UPG-60 — Front-end errors the browser pass found (before and after this run)
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-60: …" on `production-ready` (parent `203e1ec`) [T]
- **Problem:** Found by UPG-25's Chromium pass over every page [R]; each also appears on the code before UPG-23a:
  - files the pages ask for don't exist: `/static/favicon.ico` (linked by the app layout and most pages, so nearly every page logs a 404), `/static/banner-bg.png`, and the payment logos under `/static/assets/logo/` (`visa.svg`, `mastercard.svg`, `upi.svg`, `netbanking.svg`);
  - the reels page plays sample videos from `commondatastorage.googleapis.com`, which the CSP's `media-src` refuses, so it shows nothing;
  - `/spoc/create_event` throws "Identifier 'cr_step2_init' has already been declared" (two scripts declare it);
  - `/spoc/ai_report/<event>` throws "Cannot read properties of null (reading 'addEventListener')";
  - some charts log "Unknown option 'mousemove'" and an SVG gets `height="auto"`.
- **Who benefits:** everyone (no broken images or icons); SPOCs creating events.
- **What to build:** add the favicon and the missing images (or drop the references); give the reels page real event media or remove the demo videos; fix the two script errors and the chart options.
- **Files touched:** `static/`, `templates/public/reels.html`, `static/js/pages/spoc__create_event*.js`, `static/js/pages/spoc__ai_report.js`, tests.
- **Built (2026-10-19):**
  - **Tested in Part 2, as built; no change to the app.** 30 pages for six roles: UPG-23's key pages plus the pages UPG-60 fixed (round panel, AI report, tournament and fixtures, payments, audit log, verify). They load in headless Chromium with the app's static files and the real CDN libraries. `tests/headless.py` now keeps integrity-checked copies of every hashed CDN file in a git-ignored cache (`tests/.cdn-cache/`), downloaded once; the test skips if they can't be had offline. A planted missing image and a planted script error on `/login` both fail it. The create-event page loads without a page error, so its script runs.
- **Files touched:** `tests/test_frontend_errors.py` (new), `tests/headless.py` (CDN cache), `.gitignore`.
- **Effort:** S · **Depends on:** UPG-25 · **Risk:** low.
- **What was built (2026-10-10, owner's second run):**
  - **Favicon:** `static/favicon.ico` (16/32/48 px, from `static/app-icon.png`), linked by `layouts/document.html`; the existing `/favicon.ico` route now finds it.
  - **Missing images:** the events catalogue's banner used a `banner-bg.png` that never existed; it uses `static/img/hero-banner.webp`. The checkout's payment-method logos came from Razorpay's CDN, which refuses outside requests (403); they're text badges now (UPI, Cards, Netbanking).
  - **Demo videos:** `/live/reels` and `/live/streams` played cartoon sample videos from `commondatastorage.googleapis.com`, which the CSP refuses; the external sources are gone and the event images show as posters (the streams page's channel buttons switch posters). Whether these demo pages should stay public is decision D-8.
  - **Script errors:** `/spoc/create_event` declared `cr_step2_init` twice with `let`, a parse error that stopped **the whole create-event script** from running (`static/js/pages/spoc__create_event.js`); `/spoc/round_panel/<event>` bound a listener to the cut-off field even when no score exists yet (`templates/spoc/round_panel.html`).
  - **Calendar and charts:** the calendar linked a FullCalendar CSS file that doesn't exist (FullCalendar 6 injects its own) and passed an unknown `mousemove` option; the SPOC dashboard's wayfinder SVGs had `height="auto"`, now a style.
  - Every file under `static/js` parses (`node --check`).
  - Checked [R] in Chromium over every page that answers 200 for some role (254 page loads): no page error, no 404 for a `/static/` file, no CSP violation; the only messages are the scanner HUD's "camera not supported" warnings in headless Chromium.
- **To test later:** criterion 1 (headless check, no 404 or page error), plus the create-event wizard working end to end now that its script runs.
- **Acceptance criteria:**
  1. ✅ Headless check: no page logs a 404 for a `/static/` file or a page error. [T `tests/test_frontend_errors.py::test_no_page_logs_an_error_or_a_missing_static_file`]
  - **Re-verified at the end of Part 1 (2026-10-17):** the reels page is now hidden unless `DEMO_PAGES_ENABLED` (UPG-65), so its demo videos no longer show by default; the other findings are unchanged.

#### UPG-61 — A development database made before a NOT NULL column was added breaks every query on its table
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-61: …" on `production-ready` (parent `5ce60e6`) [T]
- **Problem:** Found starting UPG-59 [R]. Development start-up (`db_pg.init_db`) added only *nullable* columns to existing tables. UPG-11 added `events.activity_points` and `activity_hours` as NOT NULL with a default, so on any development database created before UPG-11 every events query failed with "no such column: events.activity_points" and most pages answered 500. Production is unaffected (migration `0005` adds them).
- **What was built:** `init_db` (`db_pg.py`) also adds a NOT NULL column when it has a constant default, as `ADD COLUMN … NOT NULL DEFAULT <value>`, so existing rows get the default. Columns without a constant default are still skipped (as before). Checked by hand [R] on a database created before UPG-11: after start-up both columns exist with default 0.0 and the SPOC dashboard answers 200. Adapter tests pass.
- **To test later:** criterion 1.
- **Built (2026-10-17):**
  - **Tested as built (Part 2); no change to the code.** The test builds the old database in a subprocess (the models' tables with `events.activity_points` dropped), then starts the app in development mode against it.
- **Files touched:** `tests/test_dev_schema_catch_up.py` (new).
- **Effort:** S · **Depends on:** UPG-16 · **Risk:** low; development only.
- **Acceptance criteria:**
  1. ✅ Test: a SQLite database created without `events.activity_points` gets it (NOT NULL, default 0) at development start-up, and `/spoc/dashboard` answers 200. [T `tests/test_dev_schema_catch_up.py::test_an_old_development_database_gets_the_not_null_column_and_the_dashboard_works`]

#### UPG-62 — 19 existing tests fail since the clean-up and seed commits
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-62: …" on `production-ready` (parent `858be1e`) [T]
- **Problem:** Found by the full pytest after Part 1 of the owner's second run [R]: 19 failed, 792 passed, 1 skipped on SQLite (Python 3.11). The same 19 fail at `251f444`, before this run's commits, so they come from the earlier commits (UPG-14, UPG-15, the seed fold, UPG-04/UPG-11), not from Part 1. No test file was changed or deleted; the total fell from 894 to 812 because `tests/test_seed_safety.py` is parametrised over the seed scripts, which are now one `seed.py`.
  - **Obsolete after removals (owner's rule: leave them, note them):** `tests/test_global_scale.py::test_stripe_create_session_simulation_fallback` and `::test_stripe_success_redirection_and_registration` (Stripe removed, UPG-14); `tests/test_next_gen.py::test_matchmaker_page_requires_auth`, `::test_matchmaker_endpoint_calculates_jaccard_matches`, `::test_matchmaker_message_exchange_simulates_realtime_replies` (matchmaker hidden, UPG-14).
  - **Seed safety (12 cases):** `tests/test_seed_safety.py` now collects `scripts/configure_capacitor.py` and `scripts/generate_vapid.py` as seed scripts (they don't call `seed_safety.guard()`), and `test_there_are_scripts_to_check` / `test_there_are_firestore_scripts_to_check` find no seed scripts under the old names. Running it also executes `scripts/configure_capacitor.py`, which **rewrites the tracked `capacitor.config.json`** with the developer's `BASE_URL` (seen 2026-10-10; the file was restored).
  - **Order-dependent (seen 2026-10-10):** `tests/test_admin_users.py` passes alone but 2 of its cases fail after other tests add accounts, because the users list now shows 25 a page (UPG-19) and the test's accounts land on page 2.
  - **Real bugs:** `tests/test_no_html_injection.py::test_every_value_put_into_html_is_escaped` finds `maxScore` put into HTML unescaped in `templates/judge/teams.html` (UPG-04's rubric); `tests/test_seminar_e2e.py::test_capacity_waitlist_and_promotion_guard`: a promoted waitlist registrant gets no `ticket_id`, and `routes_waitlist.auto_promote` calls `send_generic_email_task` with `body=` (it takes `body_text`), so the promotion email fails (now kept in the outbox and retried, still failing).
- **What to build:** fix the three real bugs; point the seed-safety test at `seed.py` (and exclude scripts that aren't seeds) without weakening it; for the Stripe and matchmaker tests, the owner decides whether they're retired (D-9).
- **Built (2026-10-17):**
  - The three real bugs and the seed-safety test were already fixed at `7accdd9`/`da7700a`; see above.
  - **D-9 (owner, 2026-10-17): the 5 obsolete tests are deleted:**
    - `tests/test_global_scale.py::test_stripe_create_session_simulation_fallback` (Stripe removed in UPG-14);
    - `tests/test_global_scale.py::test_stripe_success_redirection_and_registration` (Stripe removed);
    - `tests/test_next_gen.py::test_matchmaker_page_requires_auth` (matchmaker hidden in UPG-14);
    - `tests/test_next_gen.py::test_matchmaker_endpoint_calculates_jaccard_matches` (matchmaker hidden);
    - `tests/test_next_gen.py::test_matchmaker_message_exchange_simulates_realtime_replies` (matchmaker hidden).

    Nothing else in either file changed, apart from removing the matchmaker section's now-empty header comment.
  - A full run no longer touches `capacitor.config.json` (`git status` clean afterwards).
- **Files touched:** `tests/test_global_scale.py`, `tests/test_next_gen.py`.
- **Effort:** S · **Depends on:** UPG-14, UPG-15 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Full pytest passes, except tests the owner retires under D-9. [T full pytest on SQLite: **984 passed, 1 skipped, 0 failed** at this commit]
- **2026-10-11 baseline (UPG-63 start, Python 3.11, SQLite):** **20 failed, 791 passed, 1 skipped** at `0fd9f3a`. The 19 above plus `tests/test_seminar_e2e.py::test_seminar_full_lifecycle_and_certificate_guards`: `/participant/certificate/<reg>` now checks attendance before completion (`routes_participant.py:232` before `:238`), so a registrant who hasn't attended gets "Certificates are only issued to students who attended." and the test's `b"completed"` check fails. That is backend order, not a template. Running the suite rewrote `capacitor.config.json` again (restored).
- **2026-10-12 (full pytest, Python 3.11, SQLite):** **19 failed, 848 passed, 1 skipped.** The 19 are: Stripe (2) and matchmaker (3), both D-9; seed safety (12); `test_seminar_full_lifecycle_and_certificate_guards` (certificate order) and `test_capacity_waitlist_and_promotion_guard` (promoted waitlist entry gets no ticket). `tests/test_no_html_injection.py` now passes, and so does `tests/test_admin_users.py`. Running the suite still rewrites `capacitor.config.json` (restored).
- **Progress 2026-10-11 (frontend part only; the owner's UPG-63 run keeps backend files unchanged):** the `maxScore` escaping bug is fixed in `templates/judge/teams.html:201-206` (`escapeHtml(maxScore)`), so `test_no_html_injection.py` should pass again (not re-run: the owner asked for no test runs in this session). Still open and **blocked by the frontend-only rule**: the waitlist promotion bugs (`routes_waitlist.auto_promote`), the certificate guard order, the seed-safety test's script list; the Stripe and matchmaker tests wait on D-9.
- **2026-10-17 verification [R at `da7700a`]:** fixed free waitlist promotion ticket issuance and returned registration ID, corrected the promotion email payload to use `body_text` while retaining a compatibility alias for older callers, moved certificate completion validation before attendance validation, and narrowed seed-safety discovery to actual seed/setup scripts while including the unified `seed.py`. Targeted lifecycle, payment, seed-safety, HTML-injection and admin tests: **315 passed** across the focused runs. Full pytest: **937 passed, 1 skipped, 5 failed**; the five failures are exactly the Stripe ×2 and matchmaker ×3 tests listed under open D-9. No tests were deleted, skipped or weakened.

#### UPG-63 — Portal-wide design system and visual consistency
- **Status:** DONE (full pytest 2026-10-13: 892 passed, 1 skipped, 21 failed = the 19 UPG-62 failures, UPG-90's time-of-day failure and one order-dependent new home test, since fixed; no regression from this item)
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed)
- **Problem:** [R, headless Chromium screenshots of every role at `0fd9f3a`] The portal looks like several products. The home page hero is navy and gold, but its lower half is a near-black "aurora" theme with purple, blue, green and amber glows; the student dashboard is a light LMS with royal-blue accents; the SPOC, coordinator and admin dashboards are dark consoles where some text is unreadable (navy headings on dark navy on `/coordinator/dashboard`; near-white text on white table rows on `/admin/dashboard`); `base_classic.html` pages render dark because `static/js/global.js:14` defaults the theme to dark, and they load no Bootstrap CSS though their content uses its grid. Counted at `0fd9f3a`: 57 templates define their own `:root` palette, 88 have an inline `<style>`, about 30 don't load `static/css/global.css`, headings use three fonts (Plus Jakarta Sans, Outfit, Inter), there are about ten different page headers, and the logo appears in four treatments. `global.js` turns **every** `.alert` on a page into a toast and deletes it, so static guidance (modal hints, form notes) disappears into a pile of toasts (13 on `/admin/dashboard`). `static/css/mobile.css` gives every link a 44px minimum height and `inline-flex` on phones (text links break lines) and is loaded only by the home page, while `base_classic.html` includes the mobile bottom bar it styles.
- **Who benefits:** every user of every role; the university's credibility.
- **What to build (frontend only: `templates/`, `static/`; no route, service, schema or auth change):**
  1. One design system in `static/css/global.css` (v9): tokens from the official lockup (`static/snpsu-logo.jpg`: navy `#00185e`, gold `#c69d67`), neutral light surfaces, one heading and one body font, semantic status colours, spacing, radius, control heights, motion; Bootstrap's CSS variables mapped to the brand; the optional dark theme only swaps tokens.
  2. Logo: the reversed transparent logo is used only on navy, through a tight crop of the same artwork (`static/img/snpsu-logo-reversed.png`; the original keeps 35% empty padding); light surfaces show it on a navy tile.
  3. Shared pieces: `includes/ui.html` (app bar with role links, page header, stat tile, status badge, empty state), `includes/flash_messages.html`, `base_classic.html` rebuilt as the app layout on the app bar; mobile bottom bar styled in `global.css`.
  4. Every rendered template moved onto the system, area by area: public, participant, SPOC, coordinator, judge, admin, developer/marketing/other, tickets and certificates; page palettes replaced by tokens; dark consoles turned light; retired decorative layers (aurora, liquid blobs, ripple) removed.
  5. Responsive and accessibility pass at 1440, 1280, 1024, 768, 390 and 360px.
- **Inventory:** 129 templates (123 pages and partials rendered by 179 GET routes; 6 never rendered, UPG-64), 8 roles (anonymous, Student/Participant, Club SPOC, Event Coordinator, Volunteer, Judge, Super Admin, and the tenant/marketing pages). Per-template status: `docs/FRONTEND_CHECKLIST.md`.
- **Files touched:** `static/css/global.css`, `static/css/{analytics,developer,marketing}.css`, `static/js/global.js`, `static/js/command-palette.js`, `static/js/chart-theme.js` (new), `static/js/notifications.js` (new), page scripts under `static/js/pages/` and `static/js/handlers/` (colours, labels, null-safe charts), `static/js/proctor.js`, `static/sw.js` (cache version), `static/img/snpsu-logo-reversed.png` (new), `templates/**` (114 files, 3 of them new), `docs/FRONTEND_CHECKLIST.md` (new). `static/css/mobile.css` is no longer loaded by any page; its rules moved into `global.css` §33 and the file was left in place.
- **Effort:** XL · **Depends on:** UPG-23 (shared document) · **Risk:** lost page-specific behaviour; every page keeps its ids, `data-h-*` handlers, forms and URLs, and each area is checked in headless Chromium before and after.
- **Acceptance criteria:**
  1. Test: every template a route renders loads `/static/css/global.css` (directly or through `base_classic.html`) and none defines its own `:root` colour palette.
  2. Test: no template uses the retired decorative classes (`aurora-*`, `liquid-blob`, `grid-overlay`) or the `Outfit` font.
  3. Test: each role's dashboard and key pages render the shared app bar with `/static/img/snpsu-logo-reversed.png`.
  4. Test: flash messages render through `includes/flash_messages.html` (`data-flash`); headless: a static `.alert` stays on the page after `global.js` runs.
  5. Headless: at 1280, 768, 390 and 360px no key page scrolls horizontally, logs a page error or misses a `/static/` file.
  6. Full pytest shows no new failure against the 2026-10-11 baseline (20 failed, UPG-62).
- **What was built (2026-10-11 to 2026-10-12, development-only run; no pytest at the owner's request):**
  - **Design system v9:** `static/css/global.css:1-2519`, 41 numbered sections.
    - Tokens are at §1 (`:26`) and dark tokens at §2 (`:223`). `--brand-ink` keeps navy text legible in dark mode.
    - The logo is §3 (`:267`), the app bar §6 (`:422`), page head §7, stat tiles §9, buttons §10 and status pages §37.
    - §33 (`:2301`) is the mobile bar. On phones it hides the app bar's duplicated workspace links (`body:has(.mobile-nav-bar) .app-bar__link--ws`).
    - Focus: `--focus-ring` (`:67`) is two-tone, and `:focus-visible` uses `--brand-gold-700` (at least 3:1 on white and on navy).
  - **Light by default:** `static/js/global.js:12-15` uses dark only when chosen (`ds-theme`). Flash conversion touches only `[data-flash]`/`.flash`, so static `.alert` guidance stays.
  - **Shared pieces:**
    - `templates/includes/ui.html:18` is `app_bar`, with role links, the admin "More" menu (which now includes Email diagnostics) and the user chip. Next to it are `page_head` (`:114`), `stat_tile` (`:131`), `status_badge` (`:142`) and `empty_state` (`:158`).
    - `templates/includes/flash_messages.html` uses `data-flash` and `striptags`.
    - `templates/layouts/status.html` is the status card.
    - `templates/base_classic.html:35` is the app bar, `:61-69` the page head and `:72` the flash include.
    - `templates/components/mobile_nav.html:1-30` shows role-aware links (SPOC, coordinator, volunteer, judge, admin); students and visitors keep the original links.
  - **Charts:**
    - `static/js/chart-theme.js:11` holds the palette, validated with the dataviz validator in light mode.
    - Admin (`static/js/pages/admin__dashboard.js`, `static/js/pages/admin__analytics.js`), SPOC and analytics charts assign hues in a fixed order, fold categories beyond five into "Other", use one hue per series and a single-hue ramp for magnitude, and use status colours only for status.
  - **Pages:** every rendered template is on the system; per-template status is in `docs/FRONTEND_CHECKLIST.md`. 56 were rebuilt on the app or status layout, including:
    - the admin dashboard (sidebar removed; its links are in the app bar), analytics, audit log, org units, venues, sponsors and send email;
    - the coordinator dashboard, scanner selector, helpdesk, form responses, AI matching and AI results;
    - the judge panel and scoring;
    - the four certificate-verification pages;
    - the status pages.

    49 were restyled on their own layout, including:
    - the full-screen scanners (camera stays dark, chrome on navy and gold);
    - the ticket and wallet pass (QR codes eager-loaded, unscaled);
    - the A4 report;
    - the form builder;
    - the marketing pages.
  - **Campus photo shown in full (2026-10-12, owner request):**
    - `profile_hero` (`templates/includes/ui.html:182`, `static/css/global.css` §43) shows the whole `static/campus.jpg` at its own 1347:533 ratio. It used to be a 132px strip under a 90% navy overlay.
    - It's served as WebP (`static/img/campus.webp` 158 KB, `campus-800.webp` 59 KB for phones; the JPEG is 826 KB and remains the fallback).
    - It's used on the student dashboard and on `/profile/`, which every role uses.
  - **Inaccurate or invented content removed (frontend only):**
    - The wallet pass (`templates/tickets/digital_wallet.html`) invented "Gate 1", "General Open", "Main Venue", "Delegate" and a fake "HMAC: Verified-2026-Saptha". It now shows "Not assigned" or "—", and the hash row only appears when a hash exists.
    - The verification pages' "Generated / Delivered / Claimed" tracker was hard-coded; it's removed.
    - `templates/public/verify_success.html` (the legacy registration-ID path) no longer claims a cryptographic signature that path never checks.
    - The scan HUD's fallback total of 100 is gone.
    - The student dashboard's personal-looking fallbacks (name, personal email, USN, batch) now show "—".
    - The feedback page's NPS badge only appears when there are responses.
  - **Accessibility:**
    - Emoji used as UI were replaced with labelled icons.
    - The helpdesk's payment choice and the feedback stars are keyboard-reachable.
    - Live regions were added to scan results and copy toasts.
    - Tables got `scope` and abbreviation titles.
    - Confetti is skipped for reduced motion.
  - **Regressions found when the suite was run on 2026-10-12, all fixed:**
    - The verify page's "Certificate Verified" text (`test_certificates.py`).
    - The toast built from an HTML string (`static/js/global.js`, now DOM nodes).
    - `notifications.js` relying on `safeUrl` from another file (it now checks links itself). Both of these are `test_no_html_injection.py`.
  - **Existing tests kept intact (checked without running pytest):** every string literal the tests assert (289 positive, 59 negative) was compared with the old and new templates. The 12 pages whose wording the redesign had changed now carry the exact text again:
    - "Verification Failed", "QR Scanner & Check-in", "RFID Scan Terminal", "Student PASS", "Ticket Valid";
    - "Registration Closed", "Campus Wayfinder", "SapthaEvent Wayfinder", "SapthaEvent LiveStream";
    - "Schedule &amp; Timetable Optimizer", "Hackathon Innovation Pipeline", "Campus Venues &amp; Room Bookings".

    No test was changed.
  - **Checked [R] in headless Chromium with seeded data on 2026-10-12:**
    - 45 pages at 1280px across six roles: all 200, no page or console error, no failed `/static/` file.
    - 48 pages at 360px: none scrolls horizontally.
    - Dark mode on four dashboards.
    - Render check: 125/132 with a stand-in context; the 7 others need real data and were loaded in Chromium.
    - Every edited script passes `node --check`.
- **Known exceptions to criterion 1** (a test written as stated will flag them). These rendered templates still declare `:root` variables:
  - Aliases that point at tokens: `coordinator/ai_matching`, `coordinator/results_summary`, `coordinator/form_builder`, `participant/ticket`, `public/verify_certificate`, `public/verify_success`.
  - Device screens with a dark camera surface: `spoc/scan`, `spoc/nfc_scanner`.
  - The per-event theme override on `tickets/digital_wallet`.
  - The A4 report's heading font: `admin/report` doesn't load `global.css`, so it prints standalone.
  - Medal colours on the projector board `live/leaderboard` (gold, silver and bronze).
  - The glass-panel effect variables in `gamification/leaderboard`.

  The test needs to allow token aliases and these cases, or the pages need scoped variables. That's a decision for whoever writes the test, not a reason to drop the criterion.
- **To test later:** criteria 1–6. For criterion 6, run the full pytest against the 2026-10-11 baseline (20 failed); templates now render through `base_classic.html`, so tests that match old page text (for example "Super Admin HQ", "Club SPOC HQ", "Entry Granted", "Certificate Claimed") may need checking against the new wording rather than weakening. Also, by hand:
  - the admin "More" menu on touch devices;
  - the role-aware bottom bar for each role;
  - the confetti and copy-link behaviour on the verification pages;
  - printing the ticket, the wallet pass and the A4 report.

#### UPG-64 — Six templates are still never rendered
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-64: …" on `production-ready` (parent `c9353ba`) [T]
- **Problem:** Found starting UPG-63 [C, every `render_template`/`include`/`extends` and every Python string checked]: `templates/admin/leaderboard.html`, `templates/includes/chatbot.html`, `templates/participant/success.html`, `templates/payment/success.html`, `templates/public/login.html` and `templates/public/register.html` are not rendered or included anywhere. UPG-15 removed 17 such templates; these remain. They are full HTML documents outside the shared layout with their own palettes, so they would look wrong if anything rendered them again. UPG-63 leaves them unchanged.
- **What to build:** delete them, or wire them up if a route should render them.
- **Built (2026-10-17):**
  - Re-checked with a script over every template, `extends`/`include`/`import` and every Python string: still exactly these six. Deleted: `templates/admin/leaderboard.html`, `templates/includes/chatbot.html`, `templates/participant/success.html`, `templates/payment/success.html`, `templates/public/login.html`, `templates/public/register.html`. Nothing referred to them.
- **Files touched:** the six templates (deleted), `tests/test_every_template_rendered.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: every file under `templates/` is rendered by a route or included/extended by a rendered template. [T `tests/test_every_template_rendered.py::test_every_template_is_rendered_or_included`]
  - **Commit note:** the six deletions were staged early and went into the UPG-69 commit (`24d6eec`) by mistake; this commit adds the test and this entry. Nothing was pushed, and the history wasn't rewritten.

#### UPG-65 — Fabricated figures and simulated features on live pages
- **Status:** DONE (the certificate pages' support address, deferred with certificates, is UPG-134, DONE)
- **Last verified:** 2026-10-17, commit "UPG-65: …" on `production-ready` (parent `6c356b4`) [T]
- **Problem:** Found during UPG-63 [C, templates read; R, pages loaded]. Several pages show numbers or behaviour that no data or backend supports:
  - **Hard-coded figures:**
    - ~~Home page credibility figures, shown as count-ups (`data-count="2400"` and others), and the hero's "₹0" entry-fee tile~~: removed in UPG-86, with the invented testimonials and the "Saptha 2026 – The Grand College Fest" card.
    - The platform landing page's "50+ colleges, 10K+, 500K+, 99.9%" (`templates/marketing/landing.html`).
    - ~~The analytics KPI trend text "+12%", "+28%", "+45%", "+2.4%"~~: removed with the page in UPG-83; the new analytics computes its comparisons.
    - The SLA page's metrics and mock uptime ticks (`templates/compliance/sla.html`).
  - **Simulated features:**
    - The live-streams page's simulated viewer and like counts and its bot chat lines (`templates/public/live_streams.html`, `static/js/pages/public__live_streams.js`).
    - Comment and share buttons on reels that do nothing (`templates/public/reels.html`).
    - The NFC terminal's 1.2 s artificial "RFID parsing" delay and its "Using emulator" alert, though there is no emulator (`templates/spoc/nfc_scanner.html`).
  - **Backend default:** `routes_participant.py:176` falls back to `or 20` XP when a student has none.
  - **Hard-coded contact:** `support@snpsu.edu.in` is written into `templates/public/verify_success.html`, `templates/public/verify_certificate.html` and `chatbot_routes.py:180`. A `SUPPORT_EMAIL` setting already reaches every template as `support_email` (`app.py:446`), but these pages don't use it, and the address itself is unconfirmed.
  - **Event page defaults** (`app.py`, `event_details`): an event without a venue shows "SNPSU Campus", and one without limits shows 200 seats. These are invented values, left for this item.
  - **Already removed in UPG-63 (frontend only):** the wallet pass's invented values, the certificate status tracker, the student dashboard's fake fallbacks and push-notification stub, and the scan HUD's total of 100.
- **Who benefits:** the university's credibility; visitors and students who read the numbers as real.
- **What to build:** either compute each figure from data (counts already exist in the admin dashboard queries) or remove it. Give demo-only pages an owner decision (D-8 covers the reels and streams pages). Move the support address to configuration after confirming it.
- **Built (2026-10-17):**
  - **Owner instruction 2026-10-17 (production-ready brief): remove or hide every made-up figure and simulated feature.** This also settles D-8.
  - **Hidden demo pages:** `DEMO_PAGES_ENABLED` (`config.py`, off by default) hides the SaaS marketing pages and the live streams and reels pages. Those pages had invented customers, prices, uptime, viewers, likes, chat, and comment and share buttons that did nothing. `/platform`, `/pricing`, `/features` (`routes_marketing._demo_page`), `/live/streams` and `/live/reels` (`routes_live.py`) answer 404 unless it's on. The command palette no longer lists streams and reels.
  - **Landing page cleaned anyway:**
    - the invented stats strip (50+, 10K+, 500K+, 99.9%), "99.9% Uptime SLA" and "Join over 50 universities" are removed;
    - "GDPR Compliant" becomes "Privacy notice, data export and account deletion".
  - **Service status** (`/compliance/sla`, `routes_compliance.py`, `templates/compliance/sla.html`) shows only what it can check when it opens: the database answers (`app._database_ok`), and whether email, Razorpay (with "test mode"), WhatsApp and the AI assistant are configured. Uptime figures, history ticks and the SLA promises are gone.
  - **NFC terminal:** the 1.2 s "simulate RFID parsing" delay and the "Using emulator" alert are removed (`templates/spoc/nfc_scanner.html`).
  - **Points:** a student without points shows 0, not 20 (`routes_participant.py`).
  - **Event page:** an event without a venue shows "Venue to be announced", and one without a seat limit shows no seat count, not "SNPSU Campus" and 200 (`app.py`, `event_details`).
  - **Chatbot:**
    - its fallback replies no longer claim an AI answered;
    - the FAQ contact (`help@sapthagiri.edu`) and the fallback's address come from `SUPPORT_EMAIL`, and are left out when it's unset.
    - **Found while testing:** without Zoho credentials, `zoho_zia.ask_zia_chatbot` returned canned "[Zoho QuickML AI]" answers that pasted the prompt, including the student's own registrations, into the chat. It now returns nothing.
    - `zoho_zia.match_teams_zia`'s fallback assigned judges round-robin and called it a 96%-confident QuickML match. It now raises, so `routes_ai_matching` uses Gemini, which it also does for an unusable Zoho plan. That route's fixed `avg_confidence: 94` is computed from the matches.
  - **Existing tests changed by this instruction:**
    - `tests/test_global_scale.py::test_sla_uptime_page` now checks the computed status and that the invented strings are absent;
    - `tests/test_next_gen.py::test_live_streams_page_returns_200` and `::test_live_reels_page_returns_200` check 404 by default and the same content with the setting on.
  - **Deferred then, done since (UPG-134, 2026-10-19):** the support address hard-coded on the certificate verification pages (`templates/public/verify_success.html`, `verify_certificate.html`); criterion 3 is met for the chatbot only.
  - **New:** UPG-108 (the chatbot FAQ's campus facts are unconfirmed).
- **Files touched:** `config.py`, `routes_marketing.py`, `routes_live.py`, `routes_compliance.py`, `routes_participant.py`, `routes_ai_matching.py`, `app.py`, `chatbot_routes.py`, `zoho_zia.py`, `static/js/command-palette.js`, `templates/compliance/sla.html`, `templates/marketing/landing.html`, `templates/spoc/nfc_scanner.html`, `tests/test_no_made_up_figures.py` (new), `tests/test_global_scale.py`, `tests/test_next_gen.py`.
- **Effort:** M · **Depends on:** D-8 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: the home page and the platform landing page show no figure that isn't computed from the database or configuration. [T `tests/test_no_made_up_figures.py::test_the_home_page_and_platform_pages_show_no_invented_figures`]
  2. ✅ Test: no template has a hard-coded `data-count` figure or the strings "99.9%", "500K+" or "Verified-2026". [T `::test_no_template_has_a_hard_coded_count_or_invented_figure`]
  3. ✅ Test: the verification pages and the chatbot take the support address from `SUPPORT_EMAIL`. [T `::test_the_chatbot_takes_its_contact_from_support_email` ×2; the verification pages: UPG-134, `tests/test_certificate_verification.py::test_upg134_verification_pages_show_support_email_or_none`]
  - Also: `::test_a_new_student_starts_with_zero_points`, `::test_an_event_without_venue_or_limit_shows_no_invented_values`, `::test_without_zoho_the_ai_helpers_simulate_nothing`, `::test_the_status_page_and_nfc_terminal_simulate_nothing`. 7 of the 8 fail on the old code. Full pytest: 992 passed, 1 skipped, 0 failed.

#### UPG-66 — Two forms post without a CSRF token
- **Status:** DONE
- **Last verified:** 2026-10-17, commit on `production-ready` [T]
- **Problem:** Found during UPG-63 [C]. `templates/public/exam_interface.html:49` (`examForm`, also submitted by `static/js/proctor.js:99`) and `templates/hackathon/submit_project.html:29` post plain forms with no `csrf_token` field. `CSRFProtect` is on for the whole app (`app.py:146`), and the fetch helper (`static/js/pages/includes__csrf_fetch.js`) only covers `fetch()`. So both submissions should be refused with 400: an exam that is submitted (or force-submitted by the proctor) is lost, and a hackathon project can't be submitted.
- **Who benefits:** students taking proctored exams; hackathon teams.
- **What to build:** add `<input type="hidden" name="csrf_token" value="{{ csrf_token() }}">` to both forms (frontend only), with a test.
- **What was built:** Added hidden `csrf_token` input to `templates/public/exam_interface.html` (`#examForm`) and `templates/hackathon/submit_project.html`. Verified with `tests/test_upg66_csrf_forms.py`.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: posting each form as rendered (token included) succeeds, and posting without the token is refused (`tests/test_upg66_csrf_forms.py::test_hackathon_submission_csrf_protection`, `::test_exam_submission_csrf_protection`).
  2. ✅ Test: every `<form method="POST">` in `templates/` contains a `csrf_token` field, except the routes that are exempt (`tests/test_upg66_csrf_forms.py::test_every_rendered_post_form_in_templates_has_csrf_token`).

#### UPG-67 — The coordinator scanner throws a script error when it is locked
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-67: …" on `production-ready` (parent `dfcdb48`) [T]
- **Problem:** Found during UPG-63 [R, headless Chromium]. `templates/coordinator/scan.html` calls `startCamera()` on `DOMContentLoaded` even when `scanning_open` is false. In that state the camera elements (`#cam-placeholder`, `#cam-error`) aren't rendered, so the page logs "Cannot read properties of null (reading 'style')" on every locked event.
- **What to build:** only start the camera when the scanner view exists (frontend only).
- **Built (2026-10-17):**
  - `templates/coordinator/scan.html` starts the camera on load only when the camera view (`#cam-placeholder`) exists; a locked event renders no camera view and no longer throws.
  - `tests/headless.py` (new): loads a page the app rendered in headless Chromium, with `/static` served from disk and every other request blocked, and collects page errors, CSP violations and navigations; UPG-70 and UPG-72 use it too. Its tests skip only where Playwright's Chromium isn't installed.
- **Files touched:** `templates/coordinator/scan.html`, `tests/headless.py` (new), `tests/test_scanner_locked.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Headless: `/coordinator/scan/<event>` for an event on another day logs no page error. [T `tests/test_scanner_locked.py::test_a_locked_scanner_logs_no_page_error` (headless Chromium; fails on the old template with "Cannot read properties of null"), `::test_todays_scanner_still_has_its_camera_view`]

#### UPG-68 — The coordinator dashboard links to a form builder coordinators can't open
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-68: …" on `production-ready` (parent `9d7804d`) [T]
- **Problem:** Found during UPG-63 [R]. "Build registration form" on each event card of `/coordinator/dashboard` links to `/forms/builder/<event>`. That URL answers 403 for the seeded Event Coordinator (`coord1`) on their own assigned event, while the Club SPOC can open it. Either coordinators should be allowed to build forms (a permission change) or the button shouldn't be shown to them (a template change). That is an owner decision.
- **Built (2026-10-17):**
  - **Decision taken in this run (the brief left it open):** hide the button from those who can't use it rather than widen coordinators' permissions.
  - The builder requires `edit_event` on the event (`routes_forms.builder`). The coordinator dashboard sets `can_edit_form` per event with that same check (`routes_coordinator.py`), and the form-responses page passes it too (`routes_forms.view_responses`). The templates show "Build/Edit registration form" and "Edit form" only when it's true (`templates/coordinator/dashboard.html`, `templates/coordinator/form_responses.html`).
- **Files touched:** `routes_coordinator.py`, `routes_forms.py`, `templates/coordinator/dashboard.html`, `templates/coordinator/form_responses.html`, `tests/test_form_builder_links.py` (new).
- **Effort:** S · **Depends on:** owner decision · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: for each role that sees the button, the link answers 200; roles that can't use it don't see it. [T `tests/test_form_builder_links.py::test_builder_links_are_shown_only_to_those_who_can_open_them`: the assigned coordinator sees none (and gets 403 at the builder); every link the owner SPOC and the Super Admin are shown answers 200. Fails on the old code.]

#### UPG-69 — The legacy certificate check and the digital ticket lose the lead's name and email on the SQL adapter
- **Status:** DONE (the ticket part here; the certificate verification part, deferred with certificates, is UPG-135, DONE)
- **Last verified:** 2026-10-17, commit "UPG-69: …" on `production-ready` (parent `211b96a`) [T]
- **Problem:** Found during UPG-63. `registrations` `document(id).get().to_dict()` returns `leadEmail` and `leadName` but not `lead_email` and `lead_name`. As a result:
  - `/ticket/<reg_id>` sends the student who owns the registration back to the dashboard with "Unauthorised — this is not your ticket." The check is `routes_ticket.py:243`, `is_lead = reg.get('lead_email') == user_email`.
  - `/verify/<reg_id>` greets an empty name.
  - `/verify/<reg_id>/preview` prints "Participant" (`routes_verification.py:103`).

  This contradicts the "Digital ticket page" inventory note that the key reads back correctly at `1f4cdc8`. Also on this path:
  - The legacy `/verify/<reg_id>` route (`routes_verification.py:36-57`) checks attendance only, with no signature. The page now says exactly that (UPG-63).
  - `services_certificate.py:46-50` documents `generate_verification_hash` as HMAC-SHA256, but it is a truncated SHA-256 of the payload with the secret appended.
- **What to build:** return the snake_case keys from the adapter for registrations, or read both forms in the routes. Decide whether the legacy registration-ID verification should stay. Make the certificate hash a real HMAC, or correct its documentation.
- **Built (2026-10-17):**
  - **Ticket part (the brief's scope):** `db_adapter.SQLDocumentReference._record_to_dict` always exposes `lead_email`, `lead_name` and `lead_phone` for registrations, from their columns. Before, those snake_case keys existed only in the stored document, so rows written straight into the table (`seed.py`) lost them, and the ticket's owner check (`routes_ticket.py`, `is_lead`) failed.
  - **Re-checked [R]:** on a fresh database an app-written registration already carried both forms; the fault was seeded rows only, which the test reproduces.
  - **Deferred then, done since (UPG-135, 2026-10-19):** `/verify/<reg_id>`, its preview's name, the legacy attendance-only verification, and the certificate hash's HMAC documentation (criterion 2).
  - `db_adapter.py` is shared by many items, so rule 8's early re-verification ran; see the changelog.
- **Files touched:** `db_adapter.py`, `tests/test_ticket_owner_seeded.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** medium (touches the adapter that many routes use).
- **Acceptance criteria:**
  1. ✅ Test: on SQLite and PostgreSQL, a student opens `/ticket/<own reg_id>` (200) and sees their name. [T on SQLite: `tests/test_ticket_owner_seeded.py::test_a_student_opens_their_seeded_registrations_ticket_and_sees_their_name` (a row inserted without its stored document; another student is still refused). Fails on the old code. PostgreSQL: in the Part 3 release check.]
  2. Test: `/verify/<present reg_id>` and its preview show the lead's name.

#### UPG-70 — The confetti library's worker is blocked by the CSP
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-70: …" on `production-ready` (parent `24d6eec`) [T]
- **Problem:** Found during UPG-63 [R]. `canvas-confetti` on the certificate verification pages creates a `blob:` worker, and the CSP's `script-src`/`worker-src` refuse it. The browser console shows a CSP violation on every successful verification. The celebration is decorative; UPG-63 brands it and skips it for reduced motion.
- **What to build:** pass `useWorker: false` (frontend), allow `worker-src blob:` (CSP change), or drop the effect.
- **Built (2026-10-17):**
  - Both verification scripts (`static/js/pages/public__verify_success.js`, `public__verify_certificate.js`) create their own confetti instance with `confetti.create(null, { resize: true, useWorker: false })`. The library's default instance starts a `blob:` worker, which the CSP refuses; this one draws on the page. The CSP is unchanged.
  - `tests/headless.py` gains `stand_ins` (an outside file replaced offline) and `live_server`/`navigations_on_first_visit` (used by UPG-72).
- **Files touched:** `static/js/pages/public__verify_success.js`, `static/js/pages/public__verify_certificate.js`, `tests/headless.py`, `tests/test_confetti_csp.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Headless: `/verify/<valid id>` logs no CSP violation. [T `tests/test_confetti_csp.py::test_the_verification_confetti_needs_no_worker_under_the_apps_csp` ×2: headless Chromium, the app's real CSP header, canvas-confetti replaced offline by a stand-in that starts a blob worker unless told not to. Both fail on the old scripts with a CSP violation.]

#### UPG-71 — A profile photo for every role
- **Status:** DONE (full pytest 2026-10-13: 892 passed, 1 skipped, 21 failed = the 19 UPG-62 failures, UPG-90's time-of-day failure and one order-dependent new home test, since fixed; no regression from this item)
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed)
- **Problem:** Owner request during UPG-63. Every account showed only initials, and nobody could add a photo or choose an image. Google/Microsoft sign-in already stored the provider's `avatar_url` (`auth_oauth.py:232`), but no page showed it. `/profile/update` (`routes_profile.py:62`) accepts only name, phone and USN.
- **Who benefits:** every role; a recognisable face or image in the app bar and on the profile.
- **Owner decision (2026-10-12):** allow a small backend change, outside UPG-63's frontend-only rule: photo upload plus preset avatars.
- **What was built:**
  - **Route:** `POST /profile/avatar` (`routes_profile.py:160`) has three actions:
    - `preset` saves `users.avatar = 'preset:<key>'` for one of the 8 keys in `AVATAR_PRESETS` (`:119`).
    - `upload` checks the file is JPEG, PNG or WebP, at most 2 MB and 6000 px (`_square_webp`, `:135`). It crops to 512×512 and re-encodes as WebP, which drops EXIF data such as location and camera. Then it stores it through the existing `utils_storage.upload_file`, as `avatars/<hash of the email>-<random>.webp`, so the address isn't in the public name.
    - `remove` goes back to initials.
    - It needs a signed-in session and CSRF, writes an audit line (`PROFILE_PHOTO_UPDATED`), and needs no schema change, because `users.extra_json` keeps the field.
  - **Display:**
    - `avatar_value` (`:124`) picks the chosen photo, then a provider photo (https only), then initials.
    - A blueprint context processor (`:210`) gives every template `current_avatar`. It reads the user once per session and then caches it, so the login code is unchanged.
  - **Presets:** 8 brand avatars in `static/img/avatars/` (campus, cap, book, code, trophy, music, sport, star), on the validated chart palette.
  - **Templates:**
    - `avatar` macro (`templates/includes/ui.html:169`, CSS `static/css/global.css` §42), used in the app bar for every role, on the `profile_hero` and on the profile page.
    - "Profile photo" card at `/profile/#photo`, with the upload form, a keyboard-reachable preset radio grid and a remove button (`templates/profile/dashboard.html`).
    - Camera button on the hero linking to it.
  - **Checked [R] on 2026-10-12** in headless Chromium as a student on the SQLite dev database:
    - A preset showed in the app bar.
    - A text file was refused ("isn't an image we can read").
    - A 1600×1000 JPEG with EXIF was stored as a 512×512 WebP with no EXIF, and showed on the dashboard hero.
    - Remove went back to initials.
    - No page errors.
    - `/profile/` answered 200 with the picker for ClubSPOC, EventCoordinator, Judge and SuperAdmin.
- **Tests (written, not run, at the owner's request):** `tests/test_profile_avatar.py` covers criteria 1–4.
- **To test later:**
  - Run `tests/test_profile_avatar.py` and the full suite.
  - Upload to S3 in staging. The bucket must allow public-read on `avatars/`, as for certificates.
  - Set `MAX_CONTENT_LENGTH`: the route reads at most 2 MB, but Flask has no app-wide request size limit, so the whole body is received first.
- **Effort:** M · **Depends on:** UPG-17 (storage), UPG-63 (shared components) · **Risk:** low; uploaded images are re-encoded, never served as uploaded.
- **Acceptance criteria:**
  1. Test: choosing a preset saves `preset:<key>` and the app bar shows that avatar; an unknown key is refused.
  2. Test: an upload is stored as a 512×512 WebP without EXIF under `avatars/`, with no email address in the path. A non-image, a GIF and a file over 2 MB are refused and nothing is stored.
  3. Test: removing the photo shows initials again; a provider photo is used only when nothing was chosen, and only over https.
  4. Test: ClubSPOC, EventCoordinator and Judge accounts can set a photo; a signed-out request changes nothing.

#### UPG-72 — The first page view loads twice when the service worker installs
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-72: …" on `production-ready` (parent `d725b2e`) [T]
- **Problem:** Found during UPG-71 [R, headless Chromium navigation log]. `static/js/pages/includes__pwa_head.js:82-85` reloads the page on `controllerchange`. On a first visit the new service worker claims the page, so the page the person just opened loads a second time. That costs a whole extra page load, and anything typed in the meantime is lost.
- **What to build:** reload only when an *existing* controller is replaced (an update the person accepted), not when the first one takes control.
- **Built (2026-10-17):**
  - `static/js/pages/includes__pwa_head.js` notes whether a service worker already controlled the page when it loaded, and reloads on `controllerchange` only then (an update replacing an existing worker). On a first visit the new worker simply takes control of the page.
- **Files touched:** `static/js/pages/includes__pwa_head.js`, `tests/test_first_visit_loads_once.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Headless: a first visit to `/profile/` in a fresh browser profile navigates once. [T `tests/test_first_visit_loads_once.py::test_a_first_visit_to_the_profile_navigates_once`: the real app on a local port, a fresh Chromium profile, the worker takes control, 1 navigation. The old script navigates twice.]

#### UPG-73 — Event creation that fits every kind of event
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed); full pytest 19 failed (the UPG-62 set), 848 passed, 1 skipped
- **Problem:** Found 2026-10-12 [C, `routes_spoc.py:137-374`, `templates/spoc/create_event.html`, `services_templates.py`; R, headless].
  - **Types:**
    - The wizard offers four types (Hackathon, Seminar, Workshop, Custom). `create_event` applies a preset only for seminar and workshop; anything else is saved as `event_type='hackathon'`. The catalogue's sports, cultural, conference and webinar presets are never used.
    - Guest lectures, FDPs, NSS/NCC, social drives, club activities, quizzes, debates, coding contests, paper presentations, project expos, esports, athletics, career fairs and exhibitions have no entry point. Placement is a checkbox inside step 3.
  - **Lost or invented data:**
    - The wizard collects a map link, prize pool and sponsors that the route never saves.
    - No end date or time is stored, so multi-day events aren't possible.
    - `event_mode`, `end_datetime`, `total_rounds` and `max_teams` exist on the model but are never set.
    - The organiser's phone is saved as `9999999999` with a group link of `#`.
    - The banner falls back to an external placeholder image.
    - The category list sends `Tech` and `Workshop`, which aren't model categories.
  - **No validation:** an empty title, a date in the past, a deadline after the event, or team minimum > maximum are all accepted, and errors show as raw exception text.
  - **Publishing:** competitions go live immediately, while seminars and workshops start as drafts.
  - **Visibility:** the public catalogue (`app.py:747`) lists every event, including drafts, private (link-only), department-only and cancelled ones. The home page hides drafts but not private events.
  - **Fees:** there's one fee for everyone; faculty and external participants can't be charged differently.
- **Who benefits:** SPOCs creating any event, from a club meeting to a multi-day tournament; students, who see correct and complete event pages and never see unpublished events.
- **Owner decisions (2026-10-12):** every new event is a **draft** the SPOC reviews and then publishes (or sends for approval where the unit requires it); fests hold sub-events (UPG-74); backend changes allowed; tests written and run.
- **What to build:**
  1. **Type registry:** one registry of event types (`services_event_types.py`), grouped as talks & learning, competitions, cultural, sports, community & clubs, career, fests and custom. Each type has:
     - a default category, participation, team size, mode and audience;
     - whether it's judged;
     - the catalogue preset it uses (workflow, evaluation and certificate settings, but never the preset's ticket prices);
     - its own required details: sport, format and gender for tournaments; discipline, solo/group and time limit for cultural; and so on.
  2. **The wizard rebuilt** around the registry: type → basics → when & where (mode; start and end date/time; registration window; venue/room or online link) → who can take part (audience, years, capacity, team rules, fees per group) → type details and competition setup (rounds, judging criteria, prizes, submission) → form, team & extras (coordinators, sponsors, contact, activity points) → review. Every field the wizard shows is saved.
  3. **`create_event` rebuilt** on the registry:
     - Validation returns every error at once, without losing what was typed.
     - Every event is saved as `draft`; there are no placeholder phone, link or banner values.
     - End date/time and mode are stored.
     - Fees are kept per participant group.
  4. **Review page** (`/spoc/event/<id>/review`) showing what participants will see and a checklist of what's missing. **Publish** goes through `WorkflowEngine` (draft → published → registration open, or → pending approval for unit events, with the existing room-conflict guard).
  5. The edit page covers the new fields.
  6. The public catalogue and home page show only published, publicly visible events; draft and private events stay hidden except to their owners.
  7. Checkout charges the fee for the registrant's group (`server_price`), falling back to the regular fee.
- **Effort:** XL · **Depends on:** UPG-01, UPG-12, UPG-13, UPG-57 · **Risk:** medium; event creation feeds registration, payments, check-in and certificates.
- **Acceptance criteria:**
  1. Test: every type in the registry can be created from the wizard's form; the event stores its type, category, mode, dates, audience, team rules, fees and type details, and its status is `draft`.
  2. Test: invalid input (missing title, deadline after the event, end before start, team minimum above maximum, a sport missing for a tournament, an http online link) is refused with every message shown and nothing saved. *(Changed while building: a past start date is a **warning**, not an error. Recording a past event for attendance, hours or certificates is a real need, and `tests/test_cron.py` creates past events.)*
  3. Test: the map link, prize pool, sponsors and contact details the wizard sends are stored; no event gets `9999999999`, `#` or an external placeholder banner.
  4. Test: publishing a central event opens registration; a unit event goes to `pending_approval`; a registrant can't register while the event is a draft.
  5. Test: `/events` and `/` list neither drafts nor private events; the owner can still open a draft's review page.
  6. Test: with a faculty fee set, a faculty registrant is charged that fee and a student the regular fee.
- **What was built:**
  - **Type registry:** `services_event_types.py` holds 27 kinds of event in 8 groups (`GROUPS` `:24`, `TYPES` `:59`), each with its defaults, judged or not, preset, and own details.
    - **Learning:** seminar, guest lecture, workshop, conference, webinar, FDP, orientation.
    - **Competitions:** hackathon, coding contest, quiz, paper presentation, project expo, debate, case/business plan.
    - **Cultural:** cultural competition, show/concert.
    - **Sports:** tournament, athletics, e-sports.
    - **Community, clubs & exhibitions:** NSS/NCC, social drive, club activity, exhibition.
    - **Career:** placement drive, career fair.
    - **Big events:** fest.
    - **Anything else:** custom.

    `parse_form` (`:287`) checks everything at once and returns errors and warnings. Each type's fields are named `detail_<type>__<field>`.
  - **Wizard:** `templates/spoc/create_event.html` and `static/js/pages/spoc__create_event.js` (no `innerHTML`). Seven steps:
    1. kind of event, and whether it's part of a fest;
    2. basics, with the AI description writer;
    3. when and where: mode, start and end date/time, registration window, room or venue, map and online links;
    4. who can take part: audience, years, seats, team rules, fees per group;
    5. details and judging: the type's fields, placement, rounds, criteria, prizes, submission;
    6. form and extras: extra questions, coordinators, contact, activity points and hours, sponsors;
    7. check and save.

    It works without JavaScript, and a failed save shows every message with the typed values kept.
  - **Routes:**
    - `create_event` (`routes_spoc.py:224`) always saves a `draft`. It keeps the room-conflict check and form seeding, applies the preset's workflow, evaluation, notification and certificate settings (never its ticket prices), and takes the contact phone from the SPOC's profile; there are no placeholders. `_owner_unit` (`:146`) uses a unit only if it exists.
    - `review_event` (`:394`) shows what participants will see plus a checklist (`_review_checklist` `:361`).
    - `event_setup` (`:422`) edits in the same wizard (`form_values` `services_event_types.py:602`).
    - `publish_event` (`:485`) goes draft → published → registration open through `WorkflowEngine`, or to `pending_approval` in a unit.
    - The console shows "Review & publish" and "Edit" on each event (`templates/spoc/dashboard.html`).
  - **Listings:** `is_listed` (`services_event_types.py:582`) is used by the home page (`app.py:634`), the public calendar and the catalogue (`app.py:774`), which used to list drafts, private and cancelled events.
  - **Fees per group:** `fee_for` (`services_payments.py:77`) is used by registration's paid/free decision (`routes_forms.py`) and by `server_price` (`:90`) on order creation, checkout, simulated payment and the price preview (`routes_payment.py`).
  - **Public page** (`templates/public/event_details.html`) shows the kind, mode, date range, type details, fees per group and sponsors; the meeting link appears only to registered participants.
  - **Found and fixed on the way** (both blocked acceptance criteria):
    - A SPOC whose `department` isn't an `org_units` id (the seeded SPOC, "Computer Science & Engineering") could not save any event: foreign-key error, in the old route too.
    - Every catalogue preset defines `stages` without `pending_approval`, so a unit event using a preset could never be sent for approval, nor published. `services_workflow.py:129` now lets any staged draft go to `pending_approval`.
- **Tests:** `tests/test_event_creation.py` (36 tests, 46 cases) covers criteria 1–6. One existing helper's setup changed: `tests/test_integration_flow.py::_create_event` now checks that the event is a draft, then puts it in the live `active` state those 33 callers were written against. No assertion was changed or removed.
- **Checked [R]** in headless Chromium as the seeded SPOC:
  - invalid sports tournament → 4 messages, title kept;
  - fixed → draft → review → publish → listed in `/events`;
  - fest → "Add an event to this fest" → cultural competition inside it → the fest's public programme lists it;
  - wizard at 360px with no horizontal scroll;
  - no page errors.

#### UPG-74 — Fests: one big event that holds many sub-events
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed)
- **Problem:** Owner request 2026-10-12. A college fest, such as a cultural fest with 20 competitions or a sports meet with ten sports, has to be created today as unrelated events. Nothing groups them, shows the fest's programme, or keeps the competitions inside the fest's dates.
- **What to build:**
  - A **fest** type (theme, kind, dates, venue, banner; no registration of its own).
  - "Add an event to this fest" from the fest's review page opens the wizard with the fest set as parent. Sub-events must fall inside the fest's dates and inherit its unit.
  - The fest's public page lists its published sub-events by day. Each sub-event links back to its fest, and the SPOC's review page lists the sub-events with their status and a publish action.
  - Only the fest's owner (or someone who can edit it) can add sub-events.
- **Effort:** L · **Depends on:** UPG-73 · **Risk:** medium.
- **Acceptance criteria:**
  1. Test: a fest is created as a draft without registration; a sub-event created with the fest as parent stores `parent_event_id`, and its dates must fall within the fest's.
  2. Test: someone who can't edit the fest can't add a sub-event to it.
  3. Test: the fest's public page lists its published sub-events and not its drafts; a sub-event's page links to its fest.
- **What was built:**
  - **The `fest` type** (`services_event_types.py`) has a kind (Cultural, Technical, Sports meet, Management, Multi-category) and a theme, and no registration.
  - **Adding events:** the fest's review page has "Add an event to this fest" (`/spoc/create_event?parent=<id>`, also "Part of a fest?" in step 1).
    - `_fest_for` (`routes_spoc.py:174`) allows it only for someone who can edit the fest.
    - `parse_form` keeps the sub-event within the fest's dates, refuses a fest inside a fest, and the sub-event inherits the fest's unit, department and visibility.
  - **The fest's review page** lists its events with their status.
  - **The fest's public page** shows a programme of published events by day, with no registration bar. Each event shows "Part of <fest>".
  - **Ids:** `id_variants` (`services_event_types.py:561`) matches the parent id with or without dashes, since links use both forms.
- **Tests:** `tests/test_event_creation.py` covers criteria 1–3, including opening the fest by its dash-less id.


#### UPG-75 — Super Admin control centre: see and control everything
- **Status:** DONE (full pytest 2026-10-13: 892 passed, 1 skipped, 21 failed = the 19 UPG-62 failures, UPG-90's time-of-day failure and one order-dependent new home test, since fixed; no regression from this item)
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed). Its own 9 tests pass; the full pytest was deferred by the owner ("test the full thing at the last").
- **Problem:** Owner request 2026-10-12: the Super Admin is the person with access to everything, and the pages must let them run the whole portal. Found [C, `routes_admin.py`, `templates/admin/*`]:
  - Access itself is not the gap: `role_required` and `can()` already let `SuperAdmin` through everywhere.
  - **No overview:**
    - There is no page listing **every event**, in every status and from every SPOC.
    - Events waiting for approval are reachable only from the org-units page (`/admin/events/approve/<id>`).
    - An admin can't change an event's status or hand it to another SPOC.
    - The dashboard's "New event" posts to the old `/coordinator/create_event`, which bypasses the UPG-73 draft flow.
  - **Users:** the page can list, import students and resend set-password links, but can't **add a user of any role**, **change a role, name, department or category**, or **deactivate** someone. `is_active` is never checked at login (`routes_auth.py`, `auth_oauth.py`), so deactivation would do nothing.
  - **Registrations:** there's no way to find a registration across events, or to mark attendance or cancel from one place.
  - **System:** nothing shows whether email, payments, storage and sign-in are configured, or lists background jobs that failed (`outbox`).
  - **Announcements:** reach email only, never the in-app bell.
- **Who benefits:** the Super Admin, and everyone who waits on them (approvals, fixes, account problems).
- **What to build:**
  1. **All events** (`/admin/events`), with search, filters (status, kind) and pages:
     - an approval queue on top (approve, or return to draft);
     - per event: review, edit in the wizard, change status through `WorkflowEngine`, hand to another SPOC, registrations, refunds, delete;
     - "New event" opens the UPG-73 wizard.
  2. **Users:** add a user of any role (they get a set-password email); a page per user to change name, phone, role, department and category, deactivate or reactivate, and see their registrations and events. An admin can't remove their own Super Admin role or deactivate themselves. Login refuses deactivated accounts (password and Google/Microsoft).
  3. **Registrations** (`/admin/registrations`): search every registration by name, email, USN, team or id, with filters (event, status, attendance); mark present or absent, cancel with a reason, open the ticket.
  4. **System** (`/admin/system`): database check; which integrations are configured (yes/no only, never values); background jobs by status, with failed ones listed and a "retry now".
  5. **Announcements:** the send-email page can also post an in-app notification.
  6. **Dashboard and navigation:** a "needs attention" panel (approvals waiting, failed jobs, drafts) and the admin menu covering every admin page.
- **Effort:** L · **Depends on:** UPG-19, UPG-40, UPG-73 · **Risk:** medium (account state and login).
- **Acceptance criteria:**
  1. Test: `/admin/events` lists events of every status and SPOC; a non-admin gets 403. An admin can approve a pending event, change a status through the workflow, and hand an event to another SPOC (only to a ClubSPOC account).
  2. Test: an admin adds a user of a given role (set-password email sent), changes their role and department, and deactivates them; a deactivated account can't log in, and reactivating restores login. An admin can't deactivate or demote themselves.
  3. Test: `/admin/registrations` finds a registration by email and USN across events; marking attendance and cancelling with a reason are saved and logged.
  4. Test: `/admin/system` shows integration status without any secret value; failed background jobs are listed.
  5. Test: an announcement with "also in-app" creates a notification for each recipient.
- **What was built:**
  - **All events:** `all_events` (`routes_admin.py:1588`, `templates/admin/events.html`).
    - Every event of every status and owner, with status counts, search, status and kind filters, and pages.
    - Approval queue on top: approve and publish, or send back to draft. The existing approve route now returns to the page it came from.
    - Per event:
      - review, edit in the wizard, registrations, refunds, delete (with a confirm);
      - "move to" any status the event's workflow allows, including a preset's own stages (`set_event_status` `:1615`);
      - hand to another Club SPOC (`set_event_owner` `:1641`; refused for other roles).
    - "New event" opens the UPG-73 wizard; the dashboard's old modal posted to `/coordinator/create_event`.
  - **Users:** `add_user` (`:1668`) adds any of the five roles the login accepts, with category and department; the account is locked until its set-password link is used. `user_detail` (`:1706`, `templates/admin/user_detail.html`):
    - edit name, phone, role, department and category;
    - deactivate or reactivate;
    - see their registrations and the events they own;
    - resend the set-password link, open the academic record, delete.

    The users list gains a role filter (including "Deactivated"), an Add form, a badge and an Open link. The row markup the existing tests read is unchanged.

    An admin can't deactivate, demote or delete themselves (`delete_user` `:452` gained the guard). Login refuses deactivated accounts, both with a password (`routes_auth.py:158`) and through Google/Microsoft (`auth_oauth.py:223`).
  - **Registrations:** `all_registrations` (`:1773`, `templates/admin/registrations.html`) searches by name, email, USN, team or id across events, with event, status and attendance filters. It can set attendance (`set_attendance` `:1807`) and cancel with a required reason (`cancel_registration` `:1828`); both are logged.
  - **System:** `system_status` (`:1889`, `templates/admin/system.html`) shows a database check and totals, 11 integrations as set up / not set up (`_integrations` `:1852`; names only, never values), background jobs by status with failed and waiting ones and their errors, and "retry due jobs now" (`services_outbox.retry_due`).
  - **Announcements:** the send-email page has "Send by: email, in-app notification or both" (`:1020`), using `create_notification`.
  - **Dashboard and navigation:**
    - The dashboard gains a "Needs your attention" panel (approvals waiting, failed jobs, drafts, deactivated accounts) and 15 "Everything you can manage" cards.
    - The admin app bar is Admin · Events · Users · Registrations, plus a More menu with every other admin page (`templates/includes/ui.html`). The phone bar has the same four links.
- **Tests:** `tests/test_admin_control.py`, 9 tests covering criteria 1–5 (they pass when run on their own).
- **Checked [R]** on the dev server as the seeded Super Admin: every page 200; add user → edit role → deactivate → login refused; self-deactivate refused; hand-over to a student refused, to a SPOC done; registration found and marked present; in-app announcement to 2 judges; the system page contains no key values.
- **Known limits:** deactivation stops new logins only. Someone already logged in stays in until their session ends (UPG-76). The admin acts as themselves everywhere; there is no "log in as another user" (deliberately: every action stays in the audit log under the admin's name).
- **To test later:** the full pytest.

#### UPG-76 — A deactivated account keeps its open session
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-76: …" on `production-ready` (parent `f1426f4`) [T]
- **Problem:** Found building UPG-75 [C]. Deactivating an account (UPG-75) is checked only at login. A session that's already open (up to its lifetime, or 30 days with "remember me") keeps working, because `login_required` (`utils.py`) doesn't look at the account again.
- **What to build:** on deactivation, delete that user's server-side sessions (the `sessions` table), or have `login_required` refuse a session whose account is inactive (cached per request).
- **Built (2026-10-17):**
  - `app.end_sessions_of_deactivated_accounts` (`app.py`, a `before_request` hook) looks up the signed-in account on every request except static files and health checks. If it is deactivated (`is_active` false), the session is cleared and audit-logged (`SESSION_ENDED_DEACTIVATED`).
    - Pages are sent to `/login` with "This account has been deactivated…"; JSON and `/api/` callers get `401 {"error": "account_deactivated"}`.
    - A failed lookup lets the request through, so a database hiccup can't sign everyone out.
- **Files touched:** `app.py`, `tests/test_deactivated_sessions.py` (new).
- **Effort:** S · **Depends on:** UPG-75 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a logged-in user who is then deactivated is sent to the login page on their next request. [T `tests/test_deactivated_sessions.py::test_an_open_session_ends_when_the_account_is_deactivated`, through the admin's real deactivate action; also `::test_json_callers_get_401_and_active_accounts_are_untouched`]

#### UPG-77 — The admin's announcement email puts the message into HTML unescaped
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-77: …" on `production-ready` (parent `938048f`) [T]
- **Problem:** Found building UPG-75 [C]. `send_bulk_email` (`routes_admin.py`) builds the email body with `f'...{message}</div>'`, so whatever the admin types is sent as HTML. Only Super Admins can send, but a pasted `<` or a stray tag breaks the email, and nothing stops markup.
- **What to build:** escape the message (`markupsafe.escape`) and keep the line breaks.
- **Built (2026-10-17):**
  - `routes_admin.send_bulk_email` escapes the message and the subject with `markupsafe.escape` before they go into the email's HTML. `white-space: pre-line` keeps the line breaks. The in-app notification is unchanged (its template escapes).
- **Files touched:** `routes_admin.py`, `tests/test_announcement_escaping.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a message containing `<b>` arrives as the text `<b>`, and line breaks are kept. [T `tests/test_announcement_escaping.py::test_markup_in_an_announcement_arrives_as_text`: `<b>`, `<script>`, `&` and a tag in the subject arrive as text, and the newline is kept]

#### UPG-78 — Coordinators still create events through an old form that skips the draft flow
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server]
- **Problem:** Found building UPG-75 [C].
  - `templates/coordinator/dashboard.html`'s "Create event" modal posted to `/coordinator/create_event`, which created live events without UPG-73's types, validation, draft status or review.
  - The admin dashboard still held a copy of that modal (no longer opened, and missing a closing `</div>`, so the AI copilot modal sat inside it).
  - The wizard itself is `ClubSPOC`-only (`role_required`; Super Admin passes everywhere).
- **Owner decision (2026-10-12):** "keep the one and remove the other": the wizard stays, the old form goes. Coordinators ask their SPOC.
- **Scope note:** the original criterion ("no route creates an event except through `parse_form`") also covers `/api/v1/events` and `/api/v1/events/from-template`, which are API behaviour, not this form. They are split out as UPG-82.
- **Built:**
  - `routes_coordinator.py:160-172`: `/coordinator/create_event` no longer saves anything. A SPOC or Super Admin is sent to `/spoc/create_event`; a coordinator goes back with a message to ask their SPOC.
  - `templates/coordinator/dashboard.html`: the old 4-step modal is removed; "Create event" links to the wizard and is shown only to roles that can use it.
  - `templates/admin/dashboard.html`: the dead `#createEventModal` is removed, which also un-nests the AI copilot modal.
- **Effort:** S · **Depends on:** UPG-73 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: posting to `/coordinator/create_event` as Super Admin, SPOC or coordinator creates no event; the first two are sent to the wizard [T `tests/test_builder_and_coordinator_view.py::test_the_old_coordinator_create_route_no_longer_creates_events`].
  2. Test: the coordinator dashboard (as admin and as coordinator) and the admin dashboard have no form posting to the old route; the admin's "Create event" links to the wizard and a coordinator sees none [T `::test_dashboards_have_no_old_create_form_and_send_creators_to_the_wizard`].

#### UPG-79 — The form builder's Back goes to the wrong page
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server]
- **Problem:** Owner report 2026-10-12 (screenshot). In `templates/coordinator/form_builder.html` Back was hard-coded: `/spoc/dashboard` for a ClubSPOC, `/coordinator/dashboard` for everyone else. A Super Admin who opened the builder from an event's review page or `/admin/events` landed on the coordinator dashboard instead. Checking the builder against what registration actually does also found:
  - "Load Simple Template" added an optional "Team Name" to every form, solo or team. Team events already get a required team name and member rows from `team_fields`, so solo forms gained a stray question and team names could be skipped.
  - An event with no saved form opened to an empty canvas, though registrants see the standard form.
  - Nothing said that name, email, phone and USN are always added (`normalise_fields`) or that team rows come from the event's team size.
  - Leaving with unsaved changes lost them silently.
  - A refused save (403/404 answer `{'error': …}`) showed "Error: undefined".
  - The per-field buttons were icons with only a `title`.
- **Built:**
  - `routes_forms.py:386-408` `_builder_back_url`: Back is the same-site page that opened the builder (`?next=` or the referrer). Other hosts, `//`, backslashes, non-http schemes and the builder itself are ignored. "Same site" means `BASE_URL`, not the request's Host (changed at UPG-86 after `tests/test_public_links.py` flagged `request.host`, BLK-16). The fallback is `/admin/events` for a Super Admin, the event's review page for a SPOC, and the coordinator dashboard otherwise.
  - `templates/coordinator/form_builder.html`:
    - a note on what every form gets, plus the team size for team events;
    - the standard template without a team-name field, preloaded when there's no saved form;
    - the AI generator told whether the event is a team event;
    - a leave-page warning when there are unsaved changes;
    - the server's message shown when a save is refused;
    - `aria-label`s on the field buttons.
- **Effort:** S · **Depends on:** UPG-01, UPG-08 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: Back returns to the referring page or `?next=` [T `tests/test_builder_and_coordinator_view.py::test_builder_back_returns_to_the_page_that_opened_it`]; never to another site [T `::test_builder_back_never_leaves_the_site`, 4 cases]; without an origin, it goes to the role's page for the event [T `::test_builder_back_without_an_origin_goes_to_the_roles_page_for_the_event`].
  2. Test: the builder states what every form gets and the team size for team events only; the template has no optional team name; the unsaved-changes guard and preload are on the page [T `::test_builder_says_what_every_form_gets_and_team_rows_come_from_the_event`].

#### UPG-80 — A Super Admin's "Coordinator view" looks like a second admin home
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server]
- **Problem:** Owner report 2026-10-12 (screenshots). `/coordinator/dashboard`, opened from the admin's "Coordinator view", was titled "Welcome, <name> (Super Admin)" under an "Admin console" bar with Admin highlighted, and had its own create-event form (UPG-78). It read as an older admin dashboard rather than the coordinators' page. Its "Total registrations" added up the cached `registration_count` on each event. That counter can be stale: it showed 658, then 13 after another page reconciled the counters (`routes_spoc.py:2085-2100`).
- **Built:**
  - `templates/coordinator/dashboard.html`: for a Super Admin the page and app bar say "Coordinator view · Seen as Super Admin", the Admin link isn't marked current, and the callout points back to the admin dashboard. Coordinators still see "Welcome, <name>".
  - `routes_coordinator.py:100-108`: the totals and each card's participants count the event's registrations, which the route already reads.
- **Effort:** S · **Depends on:** UPG-63 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: as Super Admin the page is titled "Coordinator view", not "Welcome, …", and the Admin link isn't current; a coordinator still sees "Welcome, <name>" [T `tests/test_builder_and_coordinator_view.py::test_super_admin_coordinator_view_is_labelled_as_that_view`].
  2. Test: a stale counter (645) isn't shown; the real count is [T `::test_coordinator_view_counts_registrations_not_the_cached_counter`].

#### UPG-81 — The admin dashboard and analytics add up a cached registration counter that can be stale
- **Status:** DONE (with UPG-83)
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server]
- **Problem:** Found doing UPG-80 [C, owner screenshot]. The admin dashboard (`routes_admin.py:58`) and analytics (`:1085`) summed each event's `registration_count`, with revenue as that count times the fee. Seeded values, and any path that doesn't reconcile the counter, leave it wrong: the owner's dashboard showed 658 registrations and ₹7,550 while the events held 13. The SPOC analytics page rewrites the counters from real registrations (`routes_spoc.py:2085-2100`), so the figures changed depending on which page was opened last. The SPOC dashboard did the same (it counted only when the counter was missing).
- **Built:**
  - `routes_admin.py:44-75`: the admin dashboard counts each event's registrations and adds up `amount_paid` (refunds excluded).
  - `routes_spoc.py:54-90`: the SPOC dashboard does the same.
  - The analytics pages count from the records (UPG-83).
- **Acceptance criteria:**
  1. Test: with a stale counter (645), the admin dashboard's chart and the SPOC dashboard's breakdown show the real 5 [T `tests/test_analytics_and_leaderboards.py::test_dashboards_count_registrations_not_the_cached_counter`]; the analytics page counts real registrations and paid revenue [T `::test_admin_analytics_counts_real_registrations_and_filters`, `::test_build_counts_registrations_not_the_cached_counter_and_compares_periods`].

#### UPG-82 — The API creates live events that skip the draft and review flow
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-82: …" on `production-ready` (parent `1b65815`) [T]
- **Problem:** Split from UPG-78 [C]. `POST /api/v1/events` (`routes_api_v1.py:270-310`) saves `status: 'active'` from a few fields, and `POST /api/v1/events/from-template` goes through `services_event.create_event` (`:165`, also `active`). Neither uses `services_event_types.parse_form` or starts as a draft. Changing them is API behaviour, so it needs the owner's decision.
- **What to build:** either validate API input with `parse_form` and save a draft, or remove the endpoints if nothing uses them.
- **Built (2026-10-17):**
  - **Owner decision 2026-10-17:** API-created events start as drafts and go through the same review as the web form.
  - **Checks and draft:** `routes_api_v1._save_api_draft` runs the API body through the wizard's own `services_event_types.parse_form` and refuses with its errors (`400 invalid_event`, every message in `details.errors`). Otherwise it saves a **draft** owned by the caller (`spoc_id`, organizer from the token, `source: "api"`, the wizard's warnings), so it shows in their SPOC console for review and publishing.
  - **Old body keys** (`fee`, `deadline`, `min_team_size`, `max_team_size`, `capacity`, `is_team_event`) map onto the wizard's names, and the registration deadline defaults to the event date as before.
  - **From template:** `POST /api/v1/events/from-template` picks the event type whose catalogue preset (or key) is the template, unknown templates get `400 invalid_template`, and the rest goes through the same path.
  - **Shared preset step:** `services_event_types.apply_preset` (the preset's workflow, judging, notification and certificate settings, never its prices, plus its registration form) is used by the web wizard and the API alike; the wizard's behaviour is unchanged.
- **Files touched:** `routes_api_v1.py`, `services_event_types.py`, `routes_spoc.py`, `tests/test_api_event_drafts.py` (new).
- **Effort:** S–M · **Depends on:** UPG-73, owner decision · **Risk:** medium (API clients).
- **Acceptance criteria:**
  1. ✅ Test: an event created through the API starts as a draft and is refused with the same errors as the wizard. [T `tests/test_api_event_drafts.py::test_an_api_event_starts_as_a_draft_owned_by_the_caller` (also: the owner opens its review page; it isn't public), `::test_the_api_refuses_with_the_wizards_own_errors` ×4 (the API's errors equal `parse_form`'s), `::test_from_template_is_a_draft_too_and_unknown_templates_are_refused`. All fail on the old code; the existing template test in `tests/test_workflow_engine.py` passes unchanged.]


#### UPG-83 — Analytics pages that are correct, comparable and adjustable
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server, seeded 14 events / 1,087 registrations]
- **Problem:** Owner request 2026-10-12: the analytics look jumbled; use the best tools, make a multi-event bar chart that can be adjusted and viewed, and fix the leaderboard (UPG-84). Found [R, C]:
  - **Wrong figures on `/admin/analytics`:**
    - The funnel's "Confirmed" was always 0 and the no-show rate 0%: it compared `'Confirmed'` with the stored `'confirmed'`.
    - "Active events" counted only the legacy `active` status, not the UPG-43 live statuses.
    - A revenue bar was labelled "Unknown".
  - **No way to compare events:** fixed top-10 bar charts with titles cut at 22 characters, no period or category filter, no table.
  - **A second analytics page:** `/analytics`, open to SPOCs and coordinators, showed every event with made-up trend text ("+12% vs last semester", UPG-65). Its `/analytics/api/stats` (names and payments of the 20 latest registrations, portal-wide) answered any logged-in user, students included.
  - **No analytics for SPOCs** beyond two dashboard charts. The SPOC dashboard's "Attendance overview" labelled everyone not present as "Pending", including no-shows.
  - **Errors:** `/spoc/api/stats` answered 500 whenever someone was marked present without a check-in time (`routes_spoc.py:2108`). The feedback star chart used a red-to-green scale for an ordered rating, and its cards were hard-coded white in dark mode.
  - **Charts:** Chart.js 4.4 with no zoom, no table view and no download; colours not checked across all pairs.
- **Built:**
  - `services_insights.py`: one `build()` that counts everything from the registrations (UPG-81) and returns:
    - headline figures with the previous period beside them (computed, not invented);
    - one row per event (registered, confirmed, attended, no-show, not held yet, waitlisted, pending, cancelled, attendance rate, capacity filled, revenue);
    - a daily or weekly trend in total and by category, a weekday × hour heatmap, the funnel, categories, participant types and no-shows.

    Statuses are compared case-insensitively and the workflow statuses are folded in; refunds don't count as revenue.
  - `templates/analytics/hub.html` and `static/js/pages/analytics__hub.js`, served at `/admin/analytics` (every event, `routes_admin.py:143`) and the new `/spoc/analytics` (only events the SPOC may view, `routes_spoc.py:630`):
    - filters for period (7, 30, 90 days, 12 months, all time) and category;
    - **Compare events:** pick up to four measures; sort by registrations, attendance, attendance rate, no-shows, revenue, date or name; show top 10, top 25 or all; side by side, or a breakdown whose parts add up to the registrations; search; a slider and scroll for long lists; click an event to open it; a sortable table view of every event;
    - the trend with a zoom slider and a total or by-category split, the heatmap, the funnel with shares, revenue and no-show charts (status colours with text labels and a 30% line), and participant types.
  - `static/js/se-echarts.js`: Apache ECharts 5.5.1 (jsDelivr, SRI-pinned):
    - theme from the design tokens, redrawn when the dark-mode toggle flips;
    - four categorical hues that pass the dataviz validator on **every** pair in light and dark mode (the old six did not: teal/cyan and blue/purple were too close), with a fifth series folding into a grey "Other";
    - a validated single-hue ramp for magnitude;
    - "Show as table" (built from DOM nodes) and "Download PNG" on every chart, with shorter labels and fewer ticks on phones.
  - **Dashboards:** the admin dashboard's charts (most registrations, events by category) and the SPOC dashboard's charts (per-event breakdown, attendance overview) are on ECharts with real counts. The feedback star chart uses one hue with counts and shares. Chart.js and `chart-theme.js` are no longer loaded anywhere.
  - **`/analytics` retired** (`routes_analytics.py:13`): it redirects the Super Admin to `/admin/analytics` and a SPOC to `/spoc/analytics`. Its stats API answers only a Super Admin. Removed: `templates/analytics/dashboard.html`, `static/js/analytics.js`, `static/css/analytics.css`, `templates/admin/analytics.html`, `static/js/pages/admin__analytics.js`. The SPOC top bar gains "Analytics".
  - `/spoc/api/stats` sorts check-in times that may be missing.
- **Effort:** L · **Depends on:** UPG-43, UPG-63 · **Risk:** medium (dashboards stream all registrations; fine at university scale, see UPG-19 for very large data).
- **Acceptance criteria:**
  1. Test: figures fold status case and workflow statuses; the period comparison, refunds, held/not-held split and the breakdown add up [T `tests/test_analytics_and_leaderboards.py::test_registration_states_fold_case_and_new_statuses`, `::test_build_counts_registrations_not_the_cached_counter_and_compares_periods`, `::test_build_filters_by_category_and_all_time`, `::test_heatmap_and_no_shows`].
  2. Test: `/admin/analytics` counts real registrations and applies the period and category filters; a SPOC gets 403 there; `/spoc/analytics` shows only the SPOC's events [T `::test_admin_analytics_counts_real_registrations_and_filters`, `::test_spoc_analytics_shows_only_their_events`].
  3. Test: `/analytics` redirects by role and its stats API refuses students and SPOCs [T `::test_the_old_analytics_page_is_retired`]; `/spoc/api/stats` answers 200 with a present registration that has no check-in time [T `::test_spoc_live_stats_survive_attendance_without_a_checkin_time`].
  4. Every value the new scripts put into HTML is escaped [T `tests/test_no_html_injection.py`, run against an index that includes the new files and the deletions; it passes once they are committed].

#### UPG-84 — Leaderboards disagree with each other and drop the evaluation engine's scores
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server]
- **Problem:** Owner request 2026-10-12 ("fix the leaderboard"). Found [R, C]:
  - **Seven copies of the ranking**, each different: the projector board (`routes_participant.py:257`), the live board (`routes_live.py:27`), the judges' board (`routes_judge.py:357`), the SPOC results (`routes_spoc.py:627`), results publishing (`routes_coordinator.py:422`), the AI report (`routes_spoc.py:1076`) and the event report export (`services_export.py:47-58`).
  - **Wrong scores:**
    - All seven read only a judge's `total`. Scores saved through the evaluation engine (`services_evaluation.py:147`) store `final_score`, so they counted as 0 and dragged teams down.
    - The projector board and results publishing cut scores to whole numbers (`safe_int`), so the published winners and certificate ranks could differ from the results page. The same team showed 89.3, 89.7 and 89.67 on three pages.
  - **Ties:** equal scores got different places, and the boards labelled the podium by position, so a tie for 2nd showed one team as "3rd place".
  - **SPOC results page:** listed every registration (180 rows, unscored and cancelled teams at 0).
- **Built:**
  - `services_leaderboard.py`: `rank()` / `for_event()` read `total`, `final_score` or `score`; average across judges to 2 decimals; give equal scores a shared place (1, 2, 2, 4) ordered by the innovation/impact/clarity/presentation criteria and then name; leave out eliminated and cancelled registrations; and optionally list unscored teams last without a place. `score_text()` is the one display format.
  - All seven places use it. Results publishing writes the 2-decimal score and the shared place, and notifies everyone placed 1st to 3rd.
  - **Boards:** the projector, live and judges' boards show "Joint 2nd place" and "=2" for shared places. The SPOC results page has score tiles, a podium, a score bar per team, only scored teams in the standings, and unscored teams in a collapsed "Not scored yet" list, plus a link to the projector board.
- **Effort:** M · **Depends on:** UPG-08 · **Risk:** medium (published ranks and certificates).
- **Acceptance criteria:**
  1. Test: a team's score reads both fields and keeps decimals; equal scores share a place; cancelled and eliminated teams are left out; ties follow the criteria, then the name [T `tests/test_analytics_and_leaderboards.py::test_score_reads_both_fields_and_keeps_decimals`, `::test_ranking_shares_places_and_leaves_out_cancelled_and_eliminated`, `::test_ties_are_ordered_by_criteria_then_name`].
  2. Test: the projector board, live board and SPOC results show the same scores and places, the evaluation engine's `final_score` included [T `::test_every_board_shows_the_same_scores_and_places`].
  3. Test: publishing results stores the 2-decimal score and shared place, and every team sharing a top-3 place is a winner [T `::test_publishing_results_keeps_decimals_and_shared_places`].

#### UPG-85 — AI summaries after publishing results never run
- **Status:** DROPPED (owner, 2026-10-17: no new AI features)
- **Last verified:** 2026-10-12, working tree on `0fd9f3a`
- **Problem:** Found testing UPG-84 [T, traceback in the test log]. `routes_coordinator.py` starts a thread for `_bg_summaries`, which calls `current_app.app_context()` inside the thread. There is no app context there, so it raises `RuntimeError: Working outside of application context` every time, and the summaries the flash message promises ("AI summaries generating in background") are never made.
- **What to build:** pass the real app object into the thread (`current_app._get_current_object()`) or queue it through the outbox (UPG-18); show the message only when the job was queued.
- **Effort:** S · **Depends on:** UPG-18 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: after publishing, the summary job runs (or is queued) without an error.


#### UPG-86 — A production home page with the university's real details
- **Status:** DONE
- **Last verified:** 2026-10-12, working tree on `0fd9f3a` (not committed) [T, R dev server at 1280 and 390 px]
- **Problem:** Owner request 2026-10-12: use snpsu.edu.in for real data (Instagram and the rest); remove the entry-fee display at the top, the "60 seconds" steps and the "0 Registrations"; align everything, because the home page is going to production. Found [R, C]:
  - **Hero card:** an invented "Saptha 2026 – The Grand College Fest", a fixed "₹0 Entry Fee", and "Registrations" that read a field the route never sets, so it was always 0.
  - **Invented content:** a "Register in Under 60 Seconds" section, three made-up student testimonials, and count-ups of 2400 / 150 / 98% / 8500 (UPG-65).
  - **Event cards:** each showed the cached counter as "N registered" (UPG-81).
  - **Footer:**
    - The Instagram, LinkedIn and YouTube buttons linked to `#`.
    - One phone number differed from the university's site.
    - Four university links (`/about-us/`, `/departments/`, `/news-events/`, `/human-resource-development-hrd/`) only reach the site's catch-all page: same content as a made-up address.
    - A second, shared footer was drawn under the page's own.
  - **Navbar:** "Dashboard" sent SPOCs and Super Admins to the coordinator page.
  - **Scripts:** the hero category chips called `filterByCategory`, which was never defined. The page showed every script error, and a "Clicked event" debug message on each card click, as a pop-up to visitors.
  - **Language switcher:** it can put back the old hero text ("Saptha — The Grand College Fest", `i18n.py:90`).
- **Built:**
  - `university_info.py`: the university's facts, taken from snpsu.edu.in on 2026-10-12. Each link was checked to open a real page:
    - name and tagline, address, phones, admissions email, WhatsApp;
    - the five official social accounts;
    - the four schools with their programmes as listed;
    - six highlights (hospital, 19 international partners, industry MoUs, ISO 9001:2015, Centre for Innovation Leadership, arts and sport);
    - eight university links.

    Placement claims are left out. `app.py:735-747` passes it, the next three open events and the open count.
  - `templates/index.html`:
    - **hero:** the full campus photograph (`static/img/campus.webp`, smaller on phones), "Every campus event. One place to join in.", calls to Explore events and Event calendar, and a **Coming up** card listing the next three events open for registration (date chip, category, venue; each opens the event) with category chips that work;
    - **events section:** unchanged apart from the copy and the cached count;
    - **gallery:** the university's photos, with links to its gallery and Instagram;
    - **About the university:** school cards, highlights and a source note;
    - **Follow SNPSU:** branded cards for Instagram, YouTube, LinkedIn, Facebook and X;
    - **footer:** real social links, portal links (including certificate verification), the eight university links and tappable phone, email and WhatsApp contacts, with the shared footer turned off for this page;
    - navbar links Events, Calendar and About SNPSU, with each role's own dashboard; `sameAs` added to the organisation's structured data; data-i18n removed from the changed hero text.
  - `static/js/pages/index.js`: `filterByCategory()` added, script errors go to the console only, and the event dialog no longer shows a registration count.
- **Effort:** M · **Depends on:** UPG-63 · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the hero has no entry fee or registrations figure, and the page has no 60-second steps, testimonials, count-ups or cached counts [T `tests/test_home_page.py::test_nothing_invented_is_left_on_the_home_page`].
  2. Test: "Coming up" lists the next open events and leaves out past and closed ones [T `::test_coming_up_lists_the_next_open_events_from_the_database`].
  3. Test: every official account, university link, school, the tagline and email appear; no social button points to `#`; the four dead links are gone; structured data lists the accounts [T `::test_real_university_details_and_links`].
  4. Test: one footer; the hero chips' function exists; no error pop-ups [T `::test_one_footer_and_working_category_chips`].


#### UPG-87 — Home page: no calendar, and "Coming up" stays inside its card
- **Status:** DONE
- **Last verified:** 2026-10-13, working tree on `0fd9f3a` (not committed) [T, R at 1440 px with long titles]
- **Problem:** Owner report 2026-10-13 (screenshot):
  - The calendar isn't wanted on the home page (navbar, hero button, footer link).
  - Long event titles and venues pushed the "Coming up" rows past the right edge of the card: the list's grid track sized itself to its content (`min-width: auto`).
- **Built:** `templates/index.html`:
  - the calendar links are removed; the hero's second button goes to "About SNPSU";
  - the list is one `minmax(0, 1fr)` column, rows and card have `min-width: 0`, and titles and venues end with an ellipsis.
- **Acceptance criteria:**
  1. Test: the home page has no link to `/calendar` [T `tests/test_home_page.py::test_nothing_invented_is_left_on_the_home_page`]; checked in the browser at 1440 px.

#### UPG-88 — A clean, realistic demo dataset
- **Status:** DONE
- **Last verified:** 2026-10-13, working tree on `0fd9f3a` (not committed) [R: every role's pages load on the seeded database, 0 problems]
- **Problem:** Owner request 2026-10-13: clean all the data and create proper demo data for the final submission: two events a day for the next 20 days, 3 SPOCs, students and the rest, with a PDF of the details. The local database held months of test leftovers: probe organisations, stale counters (UPG-81), half-made events.
- **Built:** `seed_showcase.py`, guarded by `seed_safety.guard()` (refuses production-looking databases). It:
  - empties every table except `alembic_version` and recreates the default organisation and central unit;
  - creates the people: 1 Super Admin, 3 Club SPOCs (Technical & Careers, Cultural, Sports), 3 coordinators, 4 judges, 1 volunteer and 60 students with USN, programme, year and batch;
  - creates the campus, 4 buildings and 13 rooms through the admin pages;
  - creates **40 upcoming events (2 a day for 20 days)** and **8 finished events** through the SPOC wizard and publishing, with room bookings, coordinators and judges appointed through the staff route;
  - registers students through the real form (answering each event's own questions; teams with members). Paid events are recorded as paid by UPI, because the demo has no payment gateway;
  - for finished events, writes attendance and judges' scores, publishes results through the shared ranking, issues certificates and collects feedback through the student form;
  - posts two in-app announcements, sets one spelling for registration statuses, and leaves the outbox, login attempts and sessions empty.

  Email, WhatsApp, push and AI are off for the run. Every account uses `@snpsu.test`, a reserved domain that never delivers. Passwords come from `seed_password` and are printed once. The owner's database was backed up first, to `saptha_fallback.backup-2026-10-12-before-demo.db` (gitignored).
- **Result on the owner's database:** 72 accounts, 48 events and 544 registrations. Every upcoming registration has a ticket; 4 judged events have results; certificates and feedback are in place. A demo guide PDF (accounts, the 20-day schedule, results and a tour per role) was generated outside git.
- **Acceptance criteria:**
  1. Run: the seed ends without errors and every registration it attempts is saved [R, `scratchpad/real_seed.log`: no "not registered" lines].
  2. Run: logged in as each role, every main page answers 200 with no script error [R, 25 pages].

#### UPG-89 — Repository clean-up and README
- **Status:** DONE
- **Last verified:** 2026-10-13, working tree on `0fd9f3a` (not committed)
- **Problem:** Owner request 2026-10-13: remove the PDFs and old documents from git, keep only what is needed, and rewrite the README.
- **Built:**
  - **Removed from git** (owner's choice "old reports + plans"; all of it stays in git history):
    - the 7 PDFs and the `reports/` folder;
    - the generated HTML reports (`MARKETING_REPORT.html`, `SapthaEvent_Project_Report.html`, `scratch_audit_out.html`) and `test_event_id.txt`;
    - the root planning notes (`CURRENT_ARCHITECTURE`, `DATABASE_EVOLUTION_PLAN`, `GAP_ANALYSIS`, `GEMINI`, `HANDOFF`, `MOBILE_UX_PLAN`, `PHASED_IMPLEMENTATION_PLAN`, `SECURITY_HARDENING_PLAN`, `UNIVERSAL_EVENT_ENGINE_PLAN`, `upgrade-log`);
    - the 115 unrelated `.agents/` skill files.
  - **Kept:** `README.md`, `CLAUDE.md`, `AGENTS.md`, `privacy_policy.md`, `.github/` and `docs/`.
  - **`.gitignore`:** now ignores `*.pdf`, `*.docx`, `*.pptx`, `static/uploads/` (user uploads) and `test_event_id.txt`.
  - **`README.md`:** rewritten twice. The second version, at the owner's request (2026-10-13), has:
    - the university's real logo on a navy banner (`docs/assets/banner.png`, built from `static/snpsu-logo.png`) and eight real screenshots of the running portal (`docs/assets/*.webp`, demo data);
    - what each role can do, the features, the technology (each item checked against `requirements.txt`), the test results and links to the docs;
    - no local-run instructions, no "scan me" QR code and no AI-generated images.
  - **Removed images:** the AI-generated ones the old README used (`static/img/hero-banner.webp`, `feature-showcase.webp`, `portal-qr.png`) and the unused `dashboard-banner.jpg`.
- **Acceptance criteria:**
  1. `git ls-files` lists no `.pdf`, `.docx` or `.pptx` file, nothing under `reports/` or `.agents/`, and none of the removed notes.


#### UPG-90 — Events turn "completed" up to 5½ hours late, and a test fails after midnight
- **Status:** DONE
- **Last verified:** 2026-10-17, commit on `production-ready` [T]
- **Problem:** Found in the full run at UPG-89 [T]. `scheduler_enhanced.py:149` compares event dates, which are local (IST), with today's date in **UTC**. Between 00:00 and 05:30 IST, yesterday's events don't count as past yet. `tests/test_event_maintenance.py::test_event_auto_transition_job` builds "yesterday" from the local date, so it fails in that window (seen at 00:30 IST) and passes the rest of the day.
- **What to build:** use the university's timezone (a `TIMEZONE` setting, default Asia/Kolkata) for "today" in the scheduler and wherever dates are compared.
- **What was built:** `scheduler_enhanced.py:149` loads university timezone (`TIMEZONE` setting, defaulting to `Asia/Kolkata` via `ZoneInfo`), ensuring date comparisons match local event days regardless of midnight UTC skew.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: with the clock at 00:30 IST, an active event dated yesterday is transitioned. Since UPG-112 this runs on the live job, `tests/test_cron.py::test_just_after_midnight_ist_yesterdays_events_are_completed` (the cron `lifecycle` job, `tasks/scheduled_tasks.run_event_lifecycle`, which already used IST). The first test was on `scheduler_enhanced.py`, which the app never ran and UPG-112 removed.


#### UPG-91 — Emails: the logo shows, and links open where the portal is being used
- **Status:** DONE
- **Last verified:** 2026-10-13, working tree on `4deb9ac` (not committed) [T; R: Gmail login checked with the owner's settings, nothing sent]
- **Problem:** Owner report 2026-10-13 (screenshot of a set-password email). Three problems:
  - **Broken logo:** emails linked the logo at `BASE_URL/static/snpsu-logo.png`. The configured deployment answers 404 there, and a laptop's address can't be reached by mail services anyway.
  - **Links pointed elsewhere:** every emailed link went to `BASE_URL` (the online deployment), so a link sent while using the portal locally or through ngrok opened a site with a different database.
  - **Hidden Gmail errors:** a refused Gmail login showed only "Connection unexpectedly closed". After Gmail answers 535 to AUTH PLAIN, `smtplib` retries with AUTH LOGIN, which Gmail answers by closing the connection, so the real reason was lost. This hid a mistyped `MAIL_USER` (two words swapped) for most of a morning.
- **Built:**
  - `utils_links.py`: `is_trusted_host()` and `request_origin()`.
    - Trusted everywhere: the `BASE_URL` host and `TRUSTED_HOSTS` (with `*.` wildcards).
    - Trusted outside production only: this machine, private (LAN) addresses and ngrok tunnels.
    - Only the Host header is read; X-Forwarded-Host stays untrusted (ProxyFix `x_host=0`).
  - `utils_email.py`: `_base_url()` uses the trusted request origin, else `BASE_URL`, so a forged Host still gets `BASE_URL` (BLK-16). `_configured_base_url()` is `BASE_URL` alone.
  - **Logo:** emails use `cid:snpsu-logo`, and the SMTP path attaches `static/img/email-logo.png` (a 480 px copy of the white logo) inline in a multipart/related part. Brevo and Resend get `COLLEGE_LOGO_URL` or `BASE_URL/static/img/email-logo.png`.
  - **SMTP login:** `_smtp_login()` uses AUTH PLAIN only, so Gmail's 535 reaches the error message, which now names the likely cause.
  - **Form builder Back (UPG-79):** now accepts any trusted address.
  - `.env.example` documents `TRUSTED_HOSTS` and the logo.
  - `tests/test_public_links.py`'s static check lists `utils_links.py` as a module allowed to read `request.host`, with the reason. Its behaviour tests (a forged host gets `BASE_URL`) are unchanged and pass.
- **Acceptance criteria:**
  1. Test: this machine, LAN addresses and ngrok are trusted in development; other hosts, look-alike suffixes and public IPs never are; production trusts only `BASE_URL` and `TRUSTED_HOSTS` [T `tests/test_email_links_and_logo.py::test_development_trusts_this_machine_the_lan_and_ngrok`, `::test_untrusted_hosts_are_never_used`, `::test_production_trusts_only_base_url_and_listed_hosts`].
  2. Test: a set-password email sent from `http://192.168.1.6:5001` links there; from a forged host, and outside a request, it links to `BASE_URL` [T `::test_a_link_sent_from_a_trusted_address_opens_there`, `::test_a_forged_address_still_gets_base_url`, `::test_set_password_email_links_to_the_address_in_use`].
  3. Test: an SMTP email carries the logo inline (`Content-ID: <snpsu-logo>`, PNG) and logs in with PLAIN only; Brevo gets a public logo address [T `::test_smtp_email_carries_the_logo_inline_and_logs_in_with_plain_only`, `::test_brevo_gets_a_public_logo_address`].


#### UPG-92 — One event view: the home page popup shows the event page, and registration's Back returns where the visitor came from
- **Status:** DONE
- **Last verified:** 2026-10-13, working tree on `2bda4a8` (not committed) [T; R: Playwright on the seeded database]
- **Problem:** Owner report 2026-10-13 (two screenshots). Clicking an event on the home page and opening its page showed the same event two different ways:
  - **Two versions of one event:** the home page's popup was built in `index.js` from the card's text and added invented "Event Highlights". The full page (`/event/<id>`) had different content and left the home page.
  - **Back went to the wrong place:** "Back to event" on the registration page always went to `/event/<id>`, even when the visitor came from the home page's popup.
- **Built:**
  - **One content template:** `templates/public/_event_content.html` holds the hero, the details, the rules, registrations, key dates, calendar, organiser and share sections. Both `public/event_details.html` and the new `public/event_fragment.html` include it. The page's CSS moved to `static/css/event-details.css`.
  - **The popup:** `/event/<id>?fragment=1` (`app.py:1009`) returns only that content, without the page-only parts (breadcrumb, live countdown, copy button). It shows "In N days" instead of the countdown, plus a sticky bar with Register, "Already registered" or "Registration closed".
    - `index.js:72` `openEventPopup()` loads it into a centred, scrollable Bootstrap modal (not full screen).
    - Event cards and the "Coming up" list (`data-open-event`) open it; `/?event=<id>` reopens it.
    - The invented highlights are gone.
  - **Real numbers:** the registrations shown on the page and in the popup are counted from non-cancelled registrations (`app.py:996`), not the cached counter. Share links are built on the server from the trusted address (UPG-91).
  - **Back:** `utils_links.back_path()` (`utils_links.py:81`) returns the page on this site the visitor came from (`?next=`, else the referrer), as a path only. Other sites, `//` and backslash tricks and non-http schemes are refused.
    - The registration page (`routes_forms.py:518`) remembers that page across a reload or a resubmission and falls back to `/event/<id>`.
    - The popup's Register link carries `next=/?event=<id>`, so Back reopens the popup.
- **Acceptance criteria:**
  1. Test: the popup and the page show the same sections; the popup has no breadcrumb, countdown or copy button, shows "In 5 days" and links Register with `next=/?event=<id>` [T `tests/test_event_popup.py::test_popup_shows_the_event_page_content_without_page_only_parts`].
  2. Test: a closed event's popup says "Registration closed" and has no register link [T `::test_popup_shows_closed_registration_instead_of_a_register_link`].
  3. Test: the registrations shown are counted (2 of 3, one cancelled), not the cached 999 [T `::test_registrations_shown_are_counted_not_cached`].
  4. Test: the home page opens the popup from `data-open-event`, uses a scrollable dialog and has no "Event Highlights" [T `::test_home_page_opens_the_popup_and_invents_nothing`].
  5. Test: Back goes to the page given in `next`, else to a trusted referrer, and is remembered on reload [T `::test_back_returns_to_the_page_given_in_next` ×3, `::test_back_follows_a_trusted_referrer_and_is_remembered`].
  6. Test: Back never leaves the site (another host, `//host`, `javascript:`, `/\host`, a foreign referrer) [T `::test_back_never_leaves_the_site` ×5].
  7. Checked [R] in Playwright: card → popup (8 sections, no errors) → Register → Back → `/?event=<id>` with the popup open again; "Coming up" opens the popup.

#### UPG-93 — UPG-91's test sets a password-shaped MAIL_PASS literal, failing the repo hygiene scan
- **Status:** DONE
- **Last verified:** 2026-10-13, working tree on `2720e1a` [T]
- **Problem:** Found in the full run at UPG-92 [T]. `tests/test_email_links_and_logo.py:118` calls `monkeypatch.setenv('MAIL_PASS', ...)` with a made-up app password written as a literal, so `tests/test_repo_hygiene.py::test_no_mail_password_in_tracked_files` fails. The value is not a real password, but the scan is right to refuse any literal there.
- **What to build:** generate the dummy value when the test runs (for example `uuid.uuid4().hex`), so no password-shaped literal is committed. The hygiene scan stays as it is.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Built:** `tests/test_email_links_and_logo.py:119` sets `MAIL_PASS` to `uuid.uuid4().hex`; no assertion changed, and the hygiene scan is unchanged.
- **Acceptance criteria:**
  1. ✅ Test: `tests/test_repo_hygiene.py::test_no_mail_password_in_tracked_files` passes and `tests/test_email_links_and_logo.py` still passes (84 passed together).

#### UPG-94 — Razorpay: confirm capture with Razorpay, failed and refund webhooks, retry on the checkout page
- **Status:** DONE (the owner's Test Mode run stays with UPG-30 criterion 4, in UPG-32)
- **Last verified:** 2026-10-17, working tree on `43f2c00` (not committed) [T]
- **Problem:** Owner's Razorpay integration request, 2026-10-17. BLK-03 and UPG-30 built most of it: the server's price, recorded orders, single-use payment IDs, a `payment.captured` webhook, the receipt, the admin refund. Checked against the code at `43f2c00` [C], these gaps remain:
  - **Browser trusted for capture:** `/payment/verify` confirms on the checkout signature alone (`routes_payment.py:165-171`). It never asks Razorpay whether the payment was captured. A payment that is only authorized (auto-capture off) is confirmed but never captured, and Razorpay later returns the money on its own.
  - **Only one webhook event handled:** the webhook handles `payment.captured` and ignores everything else (`routes_payment.py:471-475`):
    - `payment.failed` is not recorded;
    - `refund.processed` from the Razorpay dashboard leaves the registration paid and its ticket valid;
    - `refund.failed` after an admin refund leaves the order marked refunded although the money never went back.
  - **Order details:** the receipt is a timestamp to the second (`routes_payment.py:124`), so two orders in the same second share it. The notes carry the event and email but not the registration ID that the form already assigned (`routes_forms.py:704`). The order doesn't ask for automatic capture.
  - **Checkout page:** there is no handler for a failed payment and no retry message (`templates/payment/checkout.html:249` only resets the button). Errors use `alert()`.
  - **Webhook over plain http:** nothing in the webhook refuses plain http in production. (`FORCE_HTTPS` redirects, which drops Razorpay's POST without saying so.)
  - **Admin view:** the admin's payments page lists only paid orders with no registration, and paid registrations. There is no list of every order with its status, timestamps and refund.
- **Who benefits:** paying participants (no lost payments, a clear retry), the finance office (reconciliation), whoever turns on live keys.
- **What to build:**
  - **Order details:** create the order with `payment_capture: 1`, a unique receipt (registration ID plus a random suffix, at most 40 characters), and notes with `event_id`, `registration_id` and `email`.
  - **Verify asks Razorpay:** `/payment/verify` keeps its database checks first (mismatch 400, used 409), then fetches the order from Razorpay.
    - Razorpay says the order is `paid` for the recorded amount in INR → confirm.
    - The payment is only `authorized` → capture it for the recorded amount, then confirm.
    - Razorpay can't be reached, or the payment isn't settled yet → 202 "payment received, confirming". Nothing is claimed; the webhook completes it.
    - The payment failed, or Razorpay's amount differs → 400; nothing is claimed.
  - **Webhook events** (all idempotent):
    - `payment.authorized`: capture the payment once, for a recorded open order of the same amount.
    - `payment.failed`: record the reason on the open order, which stays open for a retry.
    - `refund.processed`, full refund: mark the order refunded, and its registration `cancelled` / `Refunded`, so check-in refuses it. Covers refunds made from the Razorpay dashboard.
    - `refund.processed`, partial refund: noted on the order, and the registration is unchanged.
    - `refund.failed`: put the order back to paid with the reason, and mark the registration `Refund failed`, so the admin can retry.
    - In production, a webhook that doesn't arrive over https gets 403.
  - **Checkout page:** shows payment failure, cancellation, "confirming" and errors in a message box on the page, with Pay ready to try again. The form data stays in the session.
  - **Admin's payments page:** an "All orders" table of the latest 50 orders: event, payer, amount, status, order and payment IDs, registration, created / paid / refunded times, refund ID and note (the CSV has all of them). *(Built as its own page, `/admin/payments/orders`, linked from `/admin/payments`: `/admin/payments` stays the list of things to act on, and UPG-30's test checks that a refunded order leaves it.)*
  - **Documentation:** `.env.example` and this item say how to set up Test Mode and the live webhook.
- **Built** (2026-10-17, re-checked against `43f2c00`, rule 3: the payment files were last changed by UPG-56 and `ee483fa`; the claims above hold):
  - **Order details** (`routes_payment.py:118-136`):
    - the order is for the server's amount in INR, with `payment_capture: 1`;
    - its receipt is the registration ID plus 8 random hex characters (at most 40);
    - its notes are `event_id`, `registration_id` and `email`.
    - The registration ID is the one the form assigned, kept in the session and the order, so a retry keeps it.
  - **Verify asks Razorpay** (`routes_payment.py:189-198`):
    - The database checks run first, unchanged in effect: `services_payments.check_order` (`services_payments.py:335`) is claim_order's checks without the claim. It also refuses a payment ID used on another order before any Razorpay call, so 400/409 come as before.
    - `_razorpay_settled` (`routes_payment.py:241`) fetches the order. `paid` for the recorded amount in INR → confirm. Otherwise it fetches the payment: an `authorized` payment for this order and amount is captured; `captured` → confirm; `failed` or another amount → 400 and nothing claimed. Anything else, including an error reaching Razorpay → 202 `PENDING_MESSAGE` (`:25`), nothing claimed, the form kept; the webhook completes it.
  - **Webhook** (`routes_payment.py:506`): one parser and a handler per event (`_WEBHOOK_HANDLERS`, `:635`).
    - `payment.captured` is unchanged (`_webhook_captured`, `:539`).
    - `payment.authorized` captures an open order's payment of the same amount (`:563`).
    - `payment.failed` records "Payment attempt failed: <reason>" on an open order, which stays open (`:578`; `note_failed_attempt`, `services_payments.py:420`). A later claim clears the note.
    - `refund.processed` (`:592`) finds the order by payment ID (`order_for_payment`, `services_payments.py:410`).
      - Full refund (this refund, or the payment's `amount_refunded` total): `record_refund` (`:439`) moves `paid`/`refunding` → `refunded` once, with `refunded_by` `razorpay`. The registration becomes `cancelled` / `Refunded`, with its refund ID, so check-in refuses it.
      - Partial refund: noted once (`note_order`, `:431`).
      - The admin's own refund, already recorded: nothing.
    - `refund.failed` (`:619`): `refund_reversed` (`:451`) puts a `refunding` order, or a `refunded` one with that refund ID, back to `paid` with "Refund <id> failed: …". Its registration is marked `Refund failed`, so it shows again for a retry.
    - In production, a request that isn't https gets 403 (`:516`). Behind Cloud Run, ProxyFix reads `X-Forwarded-Proto`.
    - Every change is audit-logged.
  - **Checkout page** (`templates/payment/checkout.html:82`, script `:240-292`):
    - a `role="alert"` message box replaces every `alert()`;
    - `rzp.on('payment.failed')` and `ondismiss` say nothing was charged, the details are saved, and to press Pay to try again;
    - a 202 shows "Payment received" and never offers to pay again.
    - `.callout--danger` added to `static/css/global.css`.
  - **Admin:** `/admin/payments/orders` (`routes_admin.py:610`, `templates/admin/payment_orders.html`), Super Admin only.
  - **`.env.example`:** Test Mode first, then the key placeholders, the webhook URL and its five events, how to make the webhook secret, and live keys only in the host's settings.
  - **Test fakes:** the Razorpay fakes in `tests/test_paid_events.py`, `tests/test_payments_secure.py` and `tests/test_coupon_limits.py` gain `order.fetch`, which reports a checked-out order as paid, the way `tests/test_registration_no_auto_login.py`'s fake already did. `test_paid_events.py`'s fake can also be told an order's Razorpay state, and it records captures. No existing assertion changed.
  - **Not built:** no refund email for a dashboard refund (`send_refund_email` is worded for a cancelled event; UPG-51). The webhook keeps no event log of its own: its effects are idempotent and audit-logged.
- **Files touched:** `routes_payment.py`, `services_payments.py`, `routes_admin.py`, `templates/payment/checkout.html`, `templates/admin/payments.html`, `templates/admin/payment_orders.html` (new), `static/css/global.css`, `.env.example`, `tests/test_razorpay_flow.py` (new), `tests/test_paid_events.py`, `tests/test_payments_secure.py`, `tests/test_coupon_limits.py` (fakes only).
- **Effort:** M · **Depends on:** BLK-03 (DONE); UPG-30 (IN PROGRESS: its built code is done, and only its manual Test Mode run, criterion 4, is open). The owner chose on 2026-10-17 to go ahead. That manual run covers this item too, in UPG-32. · **Risk:** a verify that can't reach Razorpay no longer confirms at once, and the payer waits for the webhook. So the webhook must be set up before going live (already on the deploy checklist).
- **Acceptance criteria** (Razorpay client mocked; the existing fakes gain `order.fetch`, which reports a checked-out order as paid, the way `tests/test_registration_no_auto_login.py`'s fake already does; no existing assertion changes):
  1. ✅ Test: the Razorpay order is created for the server's amount in INR, with `payment_capture`, notes carrying the event ID, the registration ID and the payer's email, and a receipt of at most 40 characters that differs between two orders made in the same second. [T `tests/test_razorpay_flow.py::test_the_order_carries_event_registration_payer_and_a_unique_receipt`]
  2. ✅ Test: verify confirms when Razorpay says the order is paid. An authorized-only payment is captured once for the recorded amount, then confirmed. When Razorpay says failed, or another amount, the answer is 400 and nothing is registered or claimed. [T `::test_an_authorized_payment_is_captured_once_then_confirmed`, `::test_verify_refuses_what_razorpay_says_failed_or_was_another_amount`]
  3. ✅ Test: browser closed or Razorpay unreachable at verify gives 202 "confirming", with no registration and the order still open. A webhook that arrives later completes it once, with one receipt, and a later verify goes to the ticket. [T `::test_when_razorpay_cant_confirm_the_webhook_completes_it_later`]
  4. ✅ Test: a webhook that arrives after the browser's verify changes nothing: one registration, one receipt, one ticket email. [T `::test_a_webhook_after_the_browser_verified_changes_nothing`; already true before this item]
  5. ✅ Test: a failed payment (`payment.failed`), or a cancelled checkout, creates no registration and leaves the order open with the reason recorded. The payer's form data is still in the session, and a retry creates a new order with the same registration ID and a new receipt. The checkout page handles `payment.failed` and dismissal, and uses no `alert()`. [T `::test_a_failed_or_cancelled_payment_registers_nothing_and_can_be_retried`, `::test_the_checkout_page_handles_failure_and_cancel_on_the_page`]
  6. ✅ Test: a full `refund.processed` cancels the paid registration as Refunded, and the ticket is refused at check-in. A replay changes nothing. A partial refund only adds a note. `refund.failed` after an admin refund puts the order back to paid, with the reason, in the admin list. [T `::test_razorpay_refunds_cancel_the_registration_and_stop_the_ticket`, `::test_a_failed_refund_puts_the_order_back_for_the_admin`]
  7. ✅ Test: after a paid registration, the payer gets exactly one ticket (confirmation) email and one receipt, the ticket's QR PNG is made, and the ticket checks in. [T `::test_a_paid_registration_gets_its_ticket_qr_and_emails`; already true before this item]
  8. ✅ Test: in production, the webhook refuses plain http (403) and accepts https. [T `::test_the_webhook_needs_https_in_production`, plain http and `X-Forwarded-Proto: https`]
  9. ✅ Test: the admin's payments page shows every recent order with its status, payment ID, registration, amount and timestamps. A non-admin gets 403. [T `::test_admins_see_every_orders_status_and_others_get_403`, on `/admin/payments/orders`]
  - Already covered by existing tests: duplicate payment attempt (`tests/test_payments_secure.py::test_a_payment_id_can_be_used_once`); duplicate callback and amount mismatch on the webhook (`tests/test_paid_events.py::test_the_webhook_completes_a_payment_whose_browser_never_returned_once`, `::test_the_webhook_refuses_bad_signatures_and_ignores_unknown_orders`); simulation never in production (`tests/test_payments_secure.py::test_simulated_checkout_needs_the_flag_and_never_runs_in_production`, `config.production_problems`).
  - Manual (owner, Test Mode, no real money): part of UPG-30 criterion 4 / UPG-32.
  - 10 of the 12 new tests fail on the old code; criteria 4 and 7 already held and are now pinned.
  - Full pytest on SQLite (the SQL layer; no `TEST_DATABASE_URL`, so PostgreSQL 16 wasn't run): **955 passed, 1 skipped, 5 failed**. The 5 failures are UPG-62's known Stripe and matchmaker tests (D-9), which also fail at `43f2c00` (943 passed before). ruff clean.


#### UPG-95 — Registration IDs come from the clock, so two at the same millisecond overwrite each other
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-95: …" on `production-ready` (parent `72804cf`) [T]
- **Problem:** Found building UPG-94 [C]. A registration's ID is `REG-<milliseconds>`. It's set in the form (`routes_forms.py:704`) and as a fallback when a payment completes (`routes_payment.py:407`), and becomes the document ID (`routes_payment.py:434`: `document(reg_id).set(...)`). Two registrations submitted in the same millisecond, on any instance, get the same ID, and the second `set` replaces the first, which may be a paid registration. Waitlist IDs (`WL-…`, `routes_forms.py:761`) have the same problem.
- **What to build:** add a random part to the ID (for example `REG-<ms>-<6 hex>`), keeping the `REG-` prefix that tickets and exports show. Writing a new registration must never replace an existing one.
- **Built (2026-10-17):**
  - **New IDs:** `utils.generate_reg_id(prefix='REG')` (`utils.py:145`) is the prefix plus 20 hex characters of `uuid4` (80 random bits), for example `REG-9F2C…`; waitlist entries use `WL-`. Every place that built an ID from the clock now calls it: the registration form, its waitlist branch, the legacy public route and its waitlist, the coordinator's walk-in, and payment completion's fallback.
  - **No overwriting:** `utils.create_registration` refuses (raises `RegistrationExists`) when the ID is already taken, because the database layer's `set()` merges into an existing record. New registrations and waitlist entries are written through it.
    - A paid completion uses it unless the registration is the payer's own held (`pending_payment`) seat, which it updates as before.
- **Files touched:** `utils.py`, `routes_forms.py`, `routes_participant.py`, `routes_coordinator.py`, `routes_payment.py`, `tests/test_registration_ids.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low; existing IDs are unchanged.
- **Acceptance criteria:**
  1. ✅ Test: two registrations created with the clock frozen get different IDs, and both rows exist. [T `tests/test_registration_ids.py::test_two_registrations_in_the_same_millisecond_get_different_ids`; also `::test_a_new_registration_is_never_written_over_an_existing_one`, `::test_ids_are_unique_in_bulk_and_waitlist_ids_too`. The file can't import on the old code.]

#### UPG-96 — The checkout script puts the event title into a JavaScript string with HTML escaping only
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-96: …" on `production-ready` (parent `e070b2e`) [T]
- **Problem:** Found building UPG-94 [C]. `templates/payment/checkout.html:227` writes `description: "{{ event.title }}"`. Autoescape turns quotes into `&#34;`, so a title can't break out of the string. But a title ending in a backslash ends the string early, the script fails, and Pay does nothing. Titles with `&` or quotes also reach Razorpay as `&amp;` and `&#34;`.
- **What to build:** pass the title with `|tojson`, the way JSON values reach scripts elsewhere.
- **Built (2026-10-17):**
  - `templates/payment/checkout.html` passes the title to Razorpay's options as `{{ event.title|tojson }}`, a JSON literal (quotes, `&`, `<` and backslashes escaped for JavaScript), instead of an HTML-escaped string in quotes.
- **Files touched:** `templates/payment/checkout.html`, `tests/test_checkout_title.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: the checkout page for an event titled `Rock & "Roll" \` renders a script whose description is that exact string as a JSON literal. [T `tests/test_checkout_title.py::test_the_checkout_script_gets_the_title_as_a_json_literal`]


#### UPG-97 — Registering without logging in, for an email that already has an account
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-97: …" on `production-ready` (parent `ae9f7d2`) [T]
- **Problem:** Owner report 2026-10-17, with a screenshot. A visitor who registers from the home page with an email that already has an account is sent to log in: "An account already exists for this email. Please log in to register" (`routes_forms.py:636-639`, `routes_participant.py:401-403`, through `services_accounts.resolve_registrant`, `services_accounts.py:39-51`). The owner wants registration not to require a login: register now, and see the registration after logging in later. BLK-02 added the redirect as an extra guard next to its real fix (no path logs anyone in), so a stranger couldn't register someone else and nothing was sent to their inbox. **Owner decision 2026-10-17:** register straight away, and email the account a "Not you? Cancel this registration" link. The three existing tests that pin the redirect change to the new behaviour with the owner's approval: `tests/test_registration_no_auto_login.py::test_anonymous_submit_with_existing_email_must_log_in_first`, `::test_legacy_public_register_route_never_logs_in`, and `tests/test_uniform_auth_messages.py::test_sign_up_and_registration_still_tell_an_existing_email_to_log_in`. Sign-up's own "already exists" answer is unchanged.
- **Who benefits:** students registering from the home page or a shared link without remembering their password.
- **What to build:**
  - **No login needed:** an anonymous visitor who types an existing account's email is registered under that email (free → confirmed; paid → checkout; full → waitlist).
    - Still never logs anyone in.
    - Creates no account and sends no set-password link.
    - Doesn't change the account's profile.
    - The registration is marked `registered_without_login`.
  - **Cancel link in the email:** the account's confirmation email for such a registration, and its ticket email after payment, carry a signed "Not you? Cancel this registration" link (90 days).
    - The link opens a page that asks for confirmation (so mail scanners that open links cancel nothing).
    - Confirming cancels the registration once, the same way the participant's own cancel does: seat count, waitlist promotion, audit log.
    - A paid registration is cancelled with its reason and the payment stays for the organisers to refund (their refund in the Razorpay dashboard is recorded by UPG-94's webhook).
  - **Seen after login:** the participant dashboard already lists registrations by email (`routes_participant.py:671,835`), so the registration shows up once they log in.
  - Same for the legacy `/participant/public_register` route.
- **Built:**
  - **`services_accounts.resolve_registrant(db, email)`** (`services_accounts.py:41`) returns `(email, without_login)` and never a login redirect. `make_cancel_token` / `load_cancel_token` (`:56`, `:62`) sign the registration ID and email (90 days). `cancel_url_for` (`:75`) gives the link only for a `registered_without_login` registration that isn't cancelled. The now-unused `login_url` is removed.
  - **Form** (`routes_forms.py:613`): the "log in first" redirect is gone.
    - An existing account's email is not "new" (`:681`), so it gets no account and no set-password link.
    - Its profile is only updated for a logged-in visitor (`:689`).
    - The registration gets `registered_without_login` (`:725-726`), which a paid registration carries through checkout.
    - The confirmation email gets the link (`:839`).
  - **Legacy route** (`routes_participant.py:392-533`): the same, and its confirmation page now uses the real new-user flag (it said `True` for everyone).
  - **Emails:** `utils_email._cancel_block` (`utils_email.py:511`) is added to the confirmation (`:576`) and ticket (`:648`) emails when a link is given. `tasks/email_tasks.send_ticket_email_task` looks the link up from the registration (`_cancel_url`, `tasks/email_tasks.py:117`), so the ticket email after payment carries it, and so does the day-before ticket.
  - **Cancel page** `GET/POST /forms/cancel/<token>` (`routes_forms.py:1220`, `templates/public/cancel_registration.html`).
    - GET only asks. POST cancels through `routes_participant.cancel_registration_record` (`routes_participant.py:575`): the participant's own cancel, moved into a function and shared (status, seat count, waitlist promotion, audit line). It is called with a reason.
    - A paid registration's reason says the payment is to be refunded.
    - A cancelled registration shows "cancelled" again without counting twice.
    - A bad, expired or borrowed token, or a registration not made without login, gets 400.
  - **Tests changed with the owner's approval** (they pinned the old redirect; each still checks that nobody is logged in and no account is created or changed):
    - `tests/test_registration_no_auto_login.py`: `::test_anonymous_submit_with_existing_email_registers_without_logging_in` (renamed) and `::test_legacy_public_register_route_never_logs_in`;
    - `tests/test_uniform_auth_messages.py`: `::test_sign_up_still_tells_an_existing_email_to_log_in_and_registration_needs_no_login` (renamed; the sign-up and API checks are unchanged).
  - **Not built:** a waitlist entry for such an email gets no cancel link; the promotion email reaches the account.
- **Files touched:** `services_accounts.py`, `routes_forms.py`, `routes_participant.py`, `utils_email.py`, `tasks/email_tasks.py`, `templates/public/cancel_registration.html` (new), `tests/test_guest_registration.py` (new), `tests/test_registration_no_auto_login.py`, `tests/test_uniform_auth_messages.py`.
- **Effort:** S · **Depends on:** BLK-02 (DONE) · **Risk:** anyone can register an existing student for an event; the emailed cancel link and the audit log are the guard (owner's choice).
- **Acceptance criteria:**
  1. ✅ Test: an anonymous registration with an existing account's email (free event) is confirmed under that email. Nobody is logged in, no account is created or changed, and no set-password email is sent. The account gets one confirmation email with a cancel link. [T `tests/test_guest_registration.py::test_an_existing_account_registers_without_logging_in_and_gets_a_cancel_link`; also `::test_a_logged_in_registration_has_no_cancel_link`]
  2. ✅ Test: after the student logs in, the dashboard shows the registration. [T `::test_the_registration_shows_on_the_dashboard_after_login`]
  3. ✅ Test: the same on a paid event goes to checkout; after payment, the ticket email carries the cancel link. [T `::test_a_paid_registration_without_login_gets_the_link_in_its_ticket_email`, which also cancels it and keeps the payment]
  4. ✅ Test: the cancel link's page changes nothing. Confirming cancels once: status, seat count, audit line. A second confirm, a tampered token, or a token for another registration changes nothing. [T `::test_the_cancel_link_asks_first_then_cancels_once`, `::test_a_tampered_or_borrowed_cancel_token_changes_nothing`]
  5. ✅ Test: the legacy public route registers an existing account the same way, without logging in. [T `::test_the_legacy_public_route_registers_an_existing_account_the_same_way`]
  6. ✅ The three tests named above expect the new behaviour (owner-approved change); the full pytest passes otherwise as before. [T: all three pass]
  - The new test file can't import on the old code (no `make_cancel_token`); `::test_a_logged_in_registration_has_no_cancel_link` describes behaviour that is unchanged.
  - Full pytest on SQLite (the SQL layer; PostgreSQL 16 not run): **962 passed, 1 skipped, 5 failed**. The 5 failures are the known D-9 Stripe and matchmaker tests; with UPG-94 alone it was 955 passed. ruff clean.


#### UPG-98 — The container image would include the Firebase key and local database copies
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-98: …" on `production-ready` (parent `ec0b29a`) [T]
- **Problem:** Found preparing the Google Cloud deployment, 2026-10-17 [C]. `.dockerignore` excludes `.env` and `saptha_fallback.db` but not:
  - `serviceAccountKey.json` (a Firebase service-account key; the app only reads it if present, `app.py:275-283`);
  - `saptha_fallback.backup-2026-10-12-before-demo.db` (a database copy with user data);
  - other `*.db` files.

  `gcloud run deploy --source` skips them only because it falls back to `.gitignore`. A `docker build`, or Cloud Build with its own config, would put them in the image. The image also carried `android/` (64 MB), `functions/` (26 MB) and `dataconnect/`, none of which the web app imports.
- **What to build:** exclude credentials, local databases, Word documents and those three folders in `.dockerignore`.
- **Built:** `.dockerignore` adds `serviceAccountKey.json`, `**/serviceAccountKey*.json`, `**/*.db`, `**/*.db-journal`, `**/*.sqlite`, `**/*.sqlite3`, `*.docx`, `android`, `functions` and `dataconnect`. In production, Firebase (optional; the app runs on PostgreSQL) takes `FIREBASE_CREDENTIALS` from the environment instead.
- **Files touched:** `.dockerignore`, `tests/test_dockerignore.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: the key, `.env` files, local databases, Word documents and the three folders are excluded; the app's code, templates, static files, requirements and migrations are not [T `tests/test_dockerignore.py::test_credentials_and_local_data_stay_out_of_the_image`, `::test_the_app_itself_still_goes_in`; the first fails on the old file].


#### UPG-99 — Signed download links fail on Cloud Run's default credentials
- **Status:** DONE (criterion 2, the check on Cloud Run, waits for the next deploy; nothing is deployed in this run)
- **Last verified:** 2026-10-17, commit "UPG-99: …" on `production-ready` (parent `34b8cde`) [T]
- **Problem:** Found in the test deployment [R]. `utils_storage.signed_url` (`utils_storage.py:162`) calls `blob.generate_signed_url(...)` with the default credentials. On Cloud Run those are compute-engine credentials with no private key, so it raises `AttributeError: you need a private key to sign credentials`. The only caller is `tasks/export_tasks.py:187-188`, which nothing queues (UPG-14's list), so no feature fails today. Public uploads (`upload_file`, `make_public`) and private uploads work.
- **What to build:** sign through the IAM signBlob API when the credentials have no key: pass `service_account_email` and `access_token` from refreshed default credentials to `generate_signed_url`, and grant the runtime service account `roles/iam.serviceAccountTokenCreator` on itself. Document the role in `docs/DEPLOY.md`.
- **Built (2026-10-17):**
  - `utils_storage._keyless_signer`: when the default credentials can't sign locally (no private key, as on Cloud Run), it refreshes them and returns their `service_account_email` and `access_token`. `signed_url` passes those to `generate_signed_url`, which signs through IAM signBlob. Credentials with a key still sign locally.
  - `docs/DEPLOY.md` gains "Uploads and private file links": a fine-grained bucket, `roles/storage.objectAdmin`, and `roles/iam.serviceAccountTokenCreator` for the runtime service account on itself.
- **Files touched:** `utils_storage.py`, `docs/DEPLOY.md`, `tests/test_signed_urls.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: with key-less credentials (mocked), `signed_url` signs through `service_account_email` and `access_token` instead of raising. [T `tests/test_signed_urls.py::test_keyless_credentials_sign_through_iam` (fails on the old code), `::test_credentials_with_a_key_still_sign_locally`]
  2. Checked [R] on Cloud Run: a private upload's signed link downloads, and the object's plain URL is refused.
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** unchanged; criterion 2 waits for the next deploy (none in this run).

#### UPG-100 — The editor's type checker can't read its config, so it reports missing modules and the optional-import fallbacks
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-100: …" on `production-ready` (parent `cc334ef`) [T]
- **Problem:** Owner report 2026-10-17 (Pyrefly diagnostics pasted from VS Code for `routes_coordinator.py`). `pyrefly.toml` used keys Pyrefly doesn't accept (`python_interpreter`, `[errors] ignore = [...]`), so Pyrefly 1.4 stopped with "TOML parse error … Fatal configuration error" and fell back to defaults. That gave:
  - "Cannot find module `flask`" / "`google.cloud`" warnings, because it looked in a `.venv/lib/python3.9` that no longer exists (the venv is 3.11);
  - four errors in `routes_coordinator.py` (`:54`, `:90`, `:276`, `:374`): `firestore` / `FieldFilter` "may be `None`". They are set to `None` when the import fails, and the code then uses `firestore.Query`, `ArrayUnion` and `DELETE_FIELD` without a check, so the fallback protected nothing. `google-cloud-firestore` is pinned in `requirements.txt`.

  `pyrightconfig.json` also said Python 3.9.
- **What to build:** a valid `pyrefly.toml` (interpreter, excludes for the old copies and generated folders, the two docstring-noise kinds and untyped third-party imports off), Python 3.11 in `pyrightconfig.json`, and a plain import in `routes_coordinator.py`.
- **Built:**
  - `pyrefly.toml` rewritten (`python-interpreter-path`, `project-excludes`, `[errors]` as kind = false); Pyrefly now uses `.venv/lib/python3.11/site-packages`.
  - `routes_coordinator.py:5-8` imports `firestore` and `FieldFilter` directly, with a comment saying why.
  - `pyrightconfig.json` says 3.11.
  - `pyrefly==1.4.0` added to `requirements-dev.txt`.
- **Not done here:** the other 1,044 Pyrefly errors in the project (UPG-102).
- **Files touched:** `pyrefly.toml`, `pyrightconfig.json`, `routes_coordinator.py`, `requirements-dev.txt`, `tests/test_type_check_config.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low; behaviour is unchanged where the package is installed, which is everywhere the app runs.
- **Acceptance criteria:**
  1. ✅ Test: `pyrefly.toml` is valid TOML with the known keys, and `pyrightconfig.json` says 3.11 [T `tests/test_type_check_config.py::test_the_pyrefly_config_is_valid_toml_with_known_keys`].
  2. ✅ Test: Pyrefly accepts the config and reports 0 errors in `routes_coordinator.py` [T `::test_pyrefly_accepts_the_config_and_finds_no_errors_in_routes_coordinator`]. Both fail on the old files.

#### UPG-101 — README: the live link, a live-demo button, running it locally, and current facts
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-101: …" on `production-ready` (parent `0d60c3a`) [T]
- **Problem:** Owner request 2026-10-17. The README had no link to the deployed site. Its test badge (893) and Quality section (20 known failures, 13 October) were out of date. It listed only Docker for deployment, and it had no instructions to run the app or the tests.
- **Built:**
  - a "Live demo" button and link at the top, and a "Live demo" section: no login needed to register, Razorpay Test Mode with test cards, the first-visit wake-up, `/health/ready`, and what it runs on;
  - Cloud Run and Razorpay test-mode badges;
  - a "Run it locally" section (venv, `requirements-dev.txt`, `.env.example`, `python app.py`, pytest, ruff, Razorpay test keys, never commit `.env`);
  - Payments, Deployment and Security text matching UPG-94 and UPG-97;
  - the test numbers from the full run on 17 October, and the 5 known failures (D-9).
- **Files touched:** `README.md`, `tests/test_readme.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: the README links the live URL, has the "Run it locally" section, and its test badge matches the Quality section [T `tests/test_readme.py::test_the_readme_links_the_live_site_and_says_how_to_run_it`].

#### UPG-102 — 1,044 Pyrefly type errors across the app
- *Open: full text in `docs/FEATURE_REVIEW.md`.*

#### UPG-103 — No way back to the previous page in the installed app
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-103: …" on `production-ready` (parent `ece4bf5`) [T; R: Playwright at 375 and 1280 px]
- **Problem:** Owner report 2026-10-17: "for all pages I can't go back to the previous step". The app installs as a PWA with `"display": "standalone"` (`static/manifest.webmanifest:7`), which has no browser toolbar and so no Back button. The shared app bar supports a back link (`templates/includes/ui.html:18`, `back=`), but no page passes one. Of the pages outside the app bar, these have no way back at all: `participant/certificate.html`, `tickets/digital_wallet.html`, `public/verify_success.html`, `live/leaderboard.html`, `login.html` and `register.html`.
- **What to build:**
  - **App bar:** on every page except the role's home (and `/`), a "Back" link. Its link is `utils_links.back_path` (the page on this site the visitor came from, else the role's home). Clicking it goes back in the browser history when the previous page is on this site, and otherwise follows the link.
  - **The six pages without one:** the same Back link (shared include, hidden when printing).
- **Built:**
  - **Helpers:** `utils_links.role_home()` (each role's home; `/` for a visitor) and `page_back()` (show it, and where it goes: `back_path(role home, skip_prefix=this page)`), both template globals (`app.py`).
  - **App bar** (`templates/includes/ui.html`): a Back link before the logo on every page but the role's home and `/`; an explicit `app_back` still wins (the old in-nav back link is gone).
  - **Handler:** `se:back-in-site` (`static/js/handlers.js`) goes back in history only when `document.referrer` has this site's origin, and otherwise follows the link.
  - **Phones:** below 480 px the Back arrow takes the logo's place (home is in the bottom bar), and app-bar icons get 0.5 rem padding. That also fixes a 4 px overflow of the SPOC app bar.
  - **The six pages without the app bar:** `includes/back_link.html`, a floating "← Back" pill, hidden in print.
  - **Checked [R]:** the student dashboard, my events, events, the SPOC event view and SPOC analytics are no wider than the screen at 375 and 1280 px, with no console errors. Back shows on my events and not on the dashboard.
- **Files touched:** `utils_links.py`, `app.py`, `templates/includes/ui.html`, `templates/includes/back_link.html` (new), `static/js/handlers.js`, `static/css/global.css`, the six templates above, `tests/test_back_navigation.py` (new).
- **Effort:** S · **Depends on:** UPG-92 (`back_path`, DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: an inner page (for example `/participant/my_events`) has the Back link to the referring page on this site, or to the role's home; the role's home page has none; another site's referrer is never used [T `tests/test_back_navigation.py::test_inner_pages_have_back_to_the_referring_page_on_this_site`, `::test_the_role_home_has_no_back`].
  2. ✅ Test: the six pages listed above render a Back link [T `::test_the_pages_without_the_app_bar_get_a_floating_back`: each includes it; `/login` and `/register` render it].
  3. ✅ Test: the in-site back handler uses history only for a same-site referrer [T `::test_the_in_site_back_handler_uses_history_only_for_this_site`]. Three of the four fail on the old code; the home page already had no Back.
  - Full pytest on SQLite: 976 passed, 1 skipped, 5 failed (known D-9); ruff clean.

#### UPG-104 — Student dashboard: unstyled on desktop, squeezed on phones, and tabs that don't match the events
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-104: …" on `production-ready` (parent `7f623d0`) [T; R: Playwright at 375 and 1280 px on the demo database]
- **Problem:** Owner report 2026-10-17: "in the student dashboard all the above buttons are just dummy … some details not properly mobile friendly".
  - **CSS typo:** `templates/participant/dashboard.html:18` opens `@media (max-width: 767.98px) {` and never closes it. Every rule after it (51 of them: widgets, the attendance donut, ticket cards, QR boxes, past events, discovery) applies only on screens up to 767 px.
    - On desktop the page is unstyled: the donut fills the width, QR codes are full-width images, and the cards have no layout.
    - On phones the widget grid gets the desktop three columns, so a card is 495 px wide on a 375 px screen.
    - It is the only unbalanced style block in the templates [R, a script over every `<style>`].
  - **Upcoming:** a registration counts as upcoming by its event's status alone (`routes_participant.py:112`). Events whose date has passed (14 and 16 October, "Completed") and cancelled registrations sit under "My active tickets" and the Upcoming tab.
  - **Category tabs:** the tabs are fixed (Technical, Cultural, Sports) whatever the student registered for. A "Management" event matches none of them, and a tab with nothing behind it empties the page without saying so. Every link on the page works (69 checked).
- **What to build:**
  - **CSS:** close the media query so the grid is three columns on desktop and one on phones.
  - **Upcoming:** an event the student is registered for, not cancelled, dated today or later. Past or cancelled registrations go to past events.
  - **Tabs from the student's data:** All, Upcoming (n), Past (n), one tab per category the student actually has (n), and Certificates (n) when there are any.
  - **Empty tabs:** a tab with nothing to show says so.
  - **Mobile:** no part of the page is wider than a 375 px screen.
- **Built:**
  - **CSS:** the widget grid is a plain rule, 3 columns, with one column below 992 px. Widget cards get `min-width: 0` and ticket headers wrap, so nothing is pushed wider than the screen.
  - **Upcoming:** `routes_participant.dashboard` puts a registration under Upcoming only if its event is live, dated today or later (or undated) and the registration isn't cancelled or refunded. Everything else goes to past events, where a cancelled one shows a "Cancelled" chip.
  - **Tabs:** built in the route (`ticket_tabs`) from the student's registrations with counts: All, Upcoming, Past, one per category (keys from `_category_key`, for example `cat-management`), and Certificates when any are earned. Cards carry the same key.
  - **Tab script:** exact matching, hides a section with nothing to show, and shows "Nothing here yet" for an empty tab.
  - **Checked [R]** on the demo student (16 registrations): the tabs read All 16 · Upcoming 9 · Past 7 · Technical 6 · Cultural 5 · Sports 3 · Management 2 · Certificates 4. The two events whose dates had passed moved to Past. The page is 375 px wide on a 375 px screen (it was 495) and 1,280 on desktop, styled, with no console errors.
- **Files touched:** `routes_participant.py`, `templates/participant/dashboard.html`, `tests/test_student_dashboard.py`.
- **Effort:** M · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: the dashboard's style block is balanced (no rule is trapped in a media query) [T `tests/test_student_dashboard.py::test_the_dashboard_style_block_is_balanced`].
  2. ✅ Test: a registration for a past-dated event and a cancelled registration are not among the upcoming tickets; a future one is [T `::test_only_future_not_cancelled_registrations_are_upcoming`].
  3. ✅ Test: the tabs are built from the student's own registrations, with counts (a Management event gets its own tab; no tab for a category they don't have) [T `::test_the_tabs_come_from_the_students_own_registrations`]. All three fail on the old code.
  4. ✅ Checked [R] with Playwright at 375 px and 1280 px: the page is no wider than the screen, the donut and QR codes have their sizes, each tab shows its cards or an empty message, and there are no console errors.

#### UPG-105 — Hide the referral section for now
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-105: …" on `production-ready` (parent `250252a`) [T]
- **Problem:** Owner request 2026-10-17: "for now remove that referral section". The student dashboard shows "Refer students, earn rewards" with a link, counts, "₹ earned" and a Withdraw button (`templates/participant/dashboard.html:177-197`), and calls `/participant/referrals/api/stats` on every load (`:457`). No payout process exists behind it.
- **What to build:** a `REFERRALS_ENABLED` setting, off by default. When it's off, the section, its script and its API call are not on the page. The referral routes stay in the code for later.
- **Built:** `config.REFERRALS_ENABLED` (`config.py`, off unless `REFERRALS_ENABLED=true`). `templates/participant/dashboard.html` wraps the referral section and its script (the stats call, copy and withdraw) in `{% if config.get('REFERRALS_ENABLED') %}`. `routes_referrals.py` is unchanged.
- **Files touched:** `config.py`, `templates/participant/dashboard.html`, `tests/test_student_dashboard.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: by default the dashboard has no referral section and makes no referral API call; with `REFERRALS_ENABLED=true` the section is back. [T `tests/test_student_dashboard.py::test_the_referral_section_is_hidden_unless_switched_on`; fails on the old code]


#### UPG-106 — The SPOC event panel runs off a phone screen, and its buttons squeeze the title
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-106: …" on `production-ready` (parent `2fd03cf`) [T; R: Playwright at 375 and 1280 px]
- **Problem:** Owner report 2026-10-17, with a phone screenshot of a SPOC event. On a phone (375 px) [R]:
  - `.dashboard-layout` used `grid-template-columns: 1fr` below 992 px (`templates/spoc/dashboard.html:38-44`). A plain `1fr` grows to its widest content, so the column was 465 px inside a 311 px container. The page also hides sideways overflow, so the right side was cut off and couldn't be scrolled to.
  - The event header put the status and action buttons ("Review", "Edit", "Advance to …") in a column that doesn't shrink (398 px). The title and venue got 25 px, so the venue wrapped one word per line and the buttons covered the title.
- **Built:**
  - `grid-template-columns: minmax(0, 1fr)` below 992 px, and `min-width: 0; max-width: 100%` on the detail column and panel.
  - Below 768 px the header (`.event-head`) stacks: title and venue first, then the status and actions left-aligned and wrapping (`.event-head-actions`).
  - **Checked [R]:** the event view is 375 px on a 375 px screen, the header sections are 277 px each, the venue is on one line, and there are no console errors; the desktop layout is unchanged.
- **Files touched:** `templates/spoc/dashboard.html`, `tests/test_spoc_mobile.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: the phone grid is `minmax(0, 1fr)`, and the header stacks below 768 px [T `tests/test_spoc_mobile.py::test_the_spoc_event_panel_fits_a_phone`; fails on the old code].
  2. ✅ Checked [R] with Playwright at 375 px: no part of the event view is wider than the screen.


#### UPG-107 — Google Search Console ownership file
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-107: …" on `production-ready` (parent `95a5b3f`) [T]
- **Problem:** Owner request 2026-10-17. Google Search Console verifies the site with an HTML file, `google8e55d49885709546.html`, that must be served at the site root. Cloud Run serves only what the app serves; there is no file manager.
- **Built:** the file (53 bytes, as downloaded) is in `static/`, and `app.py` serves it at `/google8e55d49885709546.html` (`google_site_verification`, next to `robots.txt`).
  - Note: pages keep `noindex` (`base_classic.html`) and `robots.txt` limits crawling. Verification works regardless, but what Google may index is a separate decision.
- **Files touched:** `app.py`, `static/google8e55d49885709546.html` (new), `tests/test_site_verification.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: `GET /google8e55d49885709546.html` answers 200, `text/html`, with exactly `google-site-verification: google8e55d49885709546.html` [T `tests/test_site_verification.py::test_the_google_verification_file_is_served_at_the_root`].
  2. ✅ Checked [R] on the deployment (revision `saptha-00004-q58`, image `web:fca39ec`): `https://saptha-967997581752.asia-south1.run.app/google8e55d49885709546.html` answers 200 with the file's contents.


#### UPG-108 — The chatbot's built-in campus FAQ states unconfirmed facts
- **Status:** DONE for now (the campus facts await the owner's confirmation)
- **Last verified:** 2026-10-17, commit "UPG-108: …" on `production-ready` (parent `034e0e5`) [T]
- **Problem:** Found building UPG-65. The prompt sent to the AI assistant (`chatbot_routes.py`, `FAQ_CONTEXT`) presents campus facts as true: where Zones A–D are, "parking at the North Gate", "the Student Food Court near the Basketball court", how certificates are downloaded. Nobody has confirmed them for Sapthagiri NPS University; the AI repeats them to students. UPG-65 replaced its invented contact address with `SUPPORT_EMAIL`.
- **What to build:** the owner confirms each fact, or the FAQ moves to configuration (or an admin-editable page) and only confirmed answers are sent.
- **Built (2026-10-17):**
  - **Owner instruction 2026-10-18:** until the campus facts are confirmed, the chatbot doesn't state them; it answers "Please check with the college office." The facts still need the owner's confirmation before any of them comes back.
  - **Prompt:** `chatbot_routes.py` no longer sends the unconfirmed campus FAQ (zones, parking, food court, help desk and contact, the ID-card rule). What's left is a short "PORTAL FAQ" about the portal itself (check-in with the ticket QR; certificates under past events), plus an instruction to answer campus questions with exactly that sentence.
  - **Direct answer:** a question clearly about the campus (parking, canteen, hostel, toilets, Wi-Fi, directions, a block, building, zone or gate, transport, ID card; `_CAMPUS_QUESTION`) gets "Please check with the college office." before any AI is called. Event details come from the database and are still answered.
  - `tests/test_no_made_up_figures.py`'s chatbot test (UPG-65) now asks a non-campus question, so it still reaches the support-address fallback it checks.
- **Files touched:** `chatbot_routes.py`, `tests/test_chatbot_campus_facts.py` (new), `tests/test_no_made_up_figures.py`.
- **Effort:** S · **Depends on:** owner input · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: (owner, 2026-10-18) until the facts are confirmed, campus questions get "Please check with the college office." and the prompt carries no campus facts. [T `tests/test_chatbot_campus_facts.py::test_campus_questions_get_the_college_office` ×5, `::test_the_ai_prompt_carries_no_campus_facts`. All fail on the old code.]
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** unchanged; the campus facts still wait for the owner's confirmation.

#### UPG-109 — AI judge matching without any AI provider answers 500 with the raw error
- **Status:** DONE
- **Last verified:** 2026-10-17, commit "UPG-109: …" on `production-ready` (parent `848d402`) [T]
- **Problem:** Found re-verifying UPG-59 after UPG-65. With neither Zoho QuickML nor `GEMINI_API_KEY` configured, `POST /ai/match_judges/<event>` (`routes_ai_matching.py`) falls through to Gemini, which raises, and the route answers `500 {"status": "error", "message": <exception text>}`. Before UPG-65 the Zoho fallback invented a round-robin "96%-confident" plan instead.
- **What to build:** answer `503` with "AI matching isn't set up: add GEMINI_API_KEY (or Zoho QuickML)", and offer a plain manual assignment, clearly labelled as not AI.
- **Built (2026-10-17):**
  - **Owner's wording (2026-10-18):** "AI matching isn't set up; assign judges manually."
  - **Route:** `routes_ai_matching._ai_configured()` checks for `GEMINI_API_KEY` (config or environment) or a Zoho QuickML token (`ZOHO_AUTH_TOKEN`/`CATALYST_AUTH_TOKEN`). Without either, `POST /ai/match_judges/<event>` answers `503 {"status": "not_configured", "message": …}` before calling anything, and saves no plan.
  - **Page:** `/ai/match_page/<event>` shows the message as an information notice and disables "Generate Match Plan" (`templates/coordinator/ai_matching.html`). A 503 reply also shows as a notice, not as "Matching failed".
- **Files touched:** `routes_ai_matching.py`, `templates/coordinator/ai_matching.html`, `tests/test_ai_matching_not_set_up.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: without AI keys the route answers 503 with that message and saves no plan. [T `tests/test_ai_matching_not_set_up.py::test_matching_without_an_ai_provider_says_so_and_saves_nothing`, `::test_the_matching_page_shows_the_notice_and_disables_the_button`. Both fail on the old code.]


#### UPG-110 — Background tasks run in a stale Flask app (the suite turns order-dependent)
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-110: …" on `production-ready` (parent `46bc891`) [T]
- **Problem:** Found in Part 2 [R]. After the Part 2 test files were added, the full run failed two tests that pass alone: `tests/test_guest_registration.py::test_a_paid_registration_without_login_gets_the_link_in_its_ticket_email` (the emailed cancel link answered 400) and `tests/test_notices.py::test_the_day_before_ticket_goes_out_once_with_the_entry_qr` (the emailed QR differed from the expected one).
  - **Traced:** the ticket email's signed link was made under one Flask app instance and checked under another, with different `SECRET_KEY`s. `celery_app.init_celery` gave `ContextTask` the app in a closure, and task classes are built once, the first time a task is used. The tests' `client` fixture reloads the app module (a new app and a new `init_celery` call), but tasks kept pushing the first app.
  - **Production:** one app and one `init_celery`, so production behaved correctly; the suite just depended on test order.
- **Built:** `init_celery` records the app in a module-level `_flask_app`, which `ContextTask` reads when a task runs, so a later binding reaches every task (`celery_app.py`).
- **Files touched:** `celery_app.py`, `tests/test_task_app_context.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a task built while one app is bound runs in the app bound afterwards [T `tests/test_task_app_context.py::test_a_task_runs_in_the_app_bound_most_recently`; fails on the old code with `['first']`].
  2. ✅ The full pytest passes in its normal order: 1041 passed, 2 skipped, 0 failed.

#### UPG-111 — Pages and emails invent a venue ("SNPSU Campus") for events without one
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-111: …" on `production-ready` (parent `644b882`) [T]
- **Problem:** Found testing UPG-43. `routes_coordinator.scanner_selector` shows `d.get('venue', 'SNPSU Campus')`, an invented place, for an event with no venue. UPG-65 replaced the same default on the event page.
- **Widened 2026-10-18 (testing UPG-46):** the same default appears in 13 more places: emails (`tasks/scheduled_tasks.py:79,143,277,417`, the day-before, briefing, 3-day and velocity emails; `routes_waitlist.py:320`, the promotion email), pages (`routes_live.py:47`, `routes_participant.py:92,720`, `routes_portfolio.py:59`; `templates/live/leaderboard.html:200`, `participant/dashboard.html:228`, `public/calendar.html:136`, `spoc/ai_report.html:52`). Found with `git grep "SNPSU Campus"`; the demo seed's real hall name and the hidden live-streams demo page are not defaults.
- **What to build:** show "Venue to be announced" (as the event page does), or nothing, everywhere a venue is missing.
- **Built (2026-10-19):**
  - **One helper, `utils.venue_label(event)`:** the room's name or the venue; "Online" for an online event with neither (owner, 2026-10-19); else "Venue to be announced". Templates reach it as the `venue_label` global. It replaces every invented fallback:
    - **app code:** the scanner list (`routes_coordinator`), live board (`routes_live`), student dashboard and my-events (`routes_participant`), portfolio (`routes_portfolio`), waitlist promotion email (`routes_waitlist`), the day-before, briefing, 3-day and velocity emails (`tasks/scheduled_tasks.py`, 4 places), both calendar feeds (`app.py`, which said "SNPSU") and the event page;
    - **templates:** `live/leaderboard.html`, `participant/dashboard.html` (2), `public/calendar.html`, `public/self_checkin.html` (it said "SNPSU"), `spoc/ai_report.html`; and the ticket, wallet and judge pages, which already said "Venue to be announced" but now also say "Online".
  - **The certificate preview's "Main Campus"** was deferred with certificates and is fixed by UPG-136. `db_adapter.py`'s "Main Campus" is a campus record's default name, not a venue.
  - Stashing the change fails 5 of the 12 tests.
- **Files touched:** `utils.py`, `app.py`, `routes_coordinator.py`, `routes_live.py`, `routes_participant.py`, `routes_portfolio.py`, `routes_waitlist.py`, `tasks/scheduled_tasks.py`, 9 templates, `tests/test_venue_label.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: an event without a venue appears in the scanner list without "SNPSU Campus". [T `tests/test_venue_label.py::test_pages_say_venue_to_be_announced` (the scanner list, calendar and its feed, event page, student dashboard)]
  2. ✅ Test: no app code or template outside the seeds uses "SNPSU Campus" as a fallback (a scan), and an email for an event without a venue doesn't name one. [T `::test_no_app_code_or_page_falls_back_to_an_invented_place`, `::test_the_briefing_email_never_invents_a_venue` (in-person: "Venue to be announced"; online: "Online"), `::test_an_online_event_says_online`, `::test_the_label_never_invents_a_place`]
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** matches the code (widened the same day). Still TODO.
- **2026-10-19 (Part 3 full run):** the calendar page lists every event, and other events have "Main Campus" as their real venue, so the test now checks the placeless event's own entry. Test-only.

#### UPG-112 — UPG-14's leftover duplicates
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-112: …" on `production-ready` (parent `4ee3f27`) [T]
- **Problem:** Found testing UPG-14. Its criteria are met, but parts of its problem list were never built:
  - **`scheduler_enhanced.py` stays.** Nothing in the app imports it; only `tests/test_event_maintenance.py:10,144` does. Removing it means deleting or moving those tests, which needs the owner's decision (rule 5), as D-9 was for Stripe.
  - **Dead login throttling:** `security_middleware.record_login_attempt`, `is_account_locked` and `block_ip` (`security_middleware.py:25-90`) are called only by `tests/test_security.py`; `services_login_throttle.py` does the real work. Removing them also removes those tests (owner's decision, rule 5).
  - **Two waitlist promotions:** `routes_waitlist.auto_promote` (`routes_waitlist.py:216`, ordered by `position`) and `tasks/waitlist_tasks.promote_from_waitlist` (ordered by `joined_at`, issues a ticket).
  - **Tasks nothing queues:** `tasks/export_tasks.py` and `tasks/webhook_tasks.py` are only registered in `celery_app.py:53-54,85-86`; `tests/test_tasks.py` tests `process_razorpay_payment` (owner's decision, rule 5).
  - **Check-in paths** beside the shared check-in (the SPOC manual list, the coordinator's `get_ticket`/`mark_attendance_granular`), and the two certificate stores (deferred with certificates; one store since UPG-137).
- **What to build:** after the owner decides on the tests named above, remove the dead code and merge the waitlist promotion into one.
- **Built (2026-10-18):**
  - **Owner's rule (2026-10-18, as D-9):** a test may go only if the code it tests was removed on purpose in UPG-14; a leftover still used anywhere stays, with its tests.
  - **Removed (UPG-14 had listed each for removal; nothing in the app used them):**
    - `scheduler_enhanced.py`: nothing imported it but `tests/test_event_maintenance.py`. The live jobs are the cron endpoint's (UPG-07).
    - The in-memory IP blocking and login tracking in `security_middleware.py` (`block_ip`, `unblock_ip`, `is_ip_blocked`, `record_login_attempt`, `is_account_locked`, `get_remaining_lockout` and their stores), and the per-request `check_ip_block` hook, which could never block anyone because nothing called `block_ip`. Login throttling is `services_login_throttle.py` (BLK-13).
    - `tasks/export_tasks.py` and `tasks/webhook_tasks.py`, with their lines in `celery_app.py`'s `include` and routes; nothing queued them (exports are served by `services_export`, payments by `routes_payment`'s webhook).
  - **Fixed:** the waitlist promotion took the lowest `position`. Both join paths (`routes_waitlist.join_waitlist`, `routes_forms`) set it to the number still waiting plus one, so after a promotion or a departure a later joiner could get a lower position and be promoted first. `auto_promote` and the SPOC's list now order by `joined_at` (`routes_waitlist.py:176,227`). The task already called `auto_promote` (UPG-14), so there was one path; it issues the ticket for a free seat.
  - **Kept, still used:** the SPOC manual check-in list (`/spoc/api/checkin`, used by `templates/spoc/scan.html` and `nfc_scanner.html`) and the coordinator's `mark_attendance_granular` (`templates/coordinator/scan.html`). Also kept: the coordinator's `get_ticket`. No page calls it, but UPG-14 never meant to remove it, and its access rules are tested (`tests/test_coordinator_authz.py`, `tests/test_volunteer_scope.py`). The two certificate stores, deferred with certificates, are UPG-137 (DONE 2026-10-19).
  - **Not fixed (shown, not used to order):** the waitlist status page still reports the stored `position`, which can repeat as described above.
  - **UPG-90's test moved to the live job:** `tests/test_cron.py::test_just_after_midnight_ist_yesterdays_events_are_completed`. Switching the live job to UTC makes it fail.
- **Files touched:** deleted `scheduler_enhanced.py`, `tasks/export_tasks.py`, `tasks/webhook_tasks.py`; `security_middleware.py`, `celery_app.py`, `routes_waitlist.py`; tests `tests/test_waitlist_promotion.py` (new), `tests/test_cron.py`, `tests/test_merged_subsystems.py`, `tests/test_security.py`, `tests/test_event_maintenance.py`, `tests/test_tasks.py`.
- **Effort:** M · **Depends on:** the owner's rule 5 decision · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: one waitlist promotion path, used by the cancel route and the waitlist routes, issues a ticket in `joined_at` order. [T `tests/test_waitlist_promotion.py::test_promotion_follows_join_order_and_issues_a_ticket` (SPOC promote, a departure, a later joiner with a lower position, then a student's cancellation promotes the earlier joiner with a ticket; fails on the old order), `::test_the_task_and_the_spoc_route_share_one_promotion`]
  2. ✅ `git ls-files` has no `scheduler_enhanced.py`, and `security_middleware.py` has no login-attempt functions (after the owner's decision). [T `tests/test_merged_subsystems.py::test_upg_14s_leftovers_are_gone`]

#### UPG-113 — CI's bandit step fails on the showcase seeder's table wipes
- **Status:** DONE
- **Last verified:** 2026-10-18, commit "UPG-113: …" on `production-ready` (parent `4cdd02b`) [T]
- **Problem:** Found testing UPG-15. CI runs `bandit -r . -x tests/,__pycache__/ -ll -q` (`.github/workflows/ci.yml:146`). Since the final-submission commit (`ee483fa`), that reports two Medium B608 findings (SQL built from a string) in the showcase seeder, now `seeds/showcase.py:75` and `:692`: `DELETE FROM "{t}"` over the table names it empties. The names come from the database's own table list and the code's collection names, not from input, so it isn't injectable, but the step fails on any Medium. Every other tracked file is clean at `-ll`.
- **What to build:** delete through SQLAlchemy's table objects (`table.delete()`) or quote the name with the dialect's identifier preparer, or, if the owner prefers, a `# nosec B608` with that reason on each line, as BLK-11 did for its findings.
- **Built (2026-10-18):**
  - **Fixed in code, no `# nosec`:** the SQLite wipe deletes through the schema's own table objects (`MetaData.reflect` then `table.delete()`), and the end-of-run clean-up of `outbox`, `login_attempts` and `flask_sessions` uses `Table(..., autoload_with=conn).delete()` (`seeds/showcase.py:65-84,692-699`). The PostgreSQL `TRUNCATE` now quotes each name with the dialect's identifier preparer instead of hand-made quotes; bandit never flagged it.
  - Bandit at `-ll` over every tracked non-test file now reports nothing. The showcase still empties and rebuilds the portal on SQLite (`tests/test_seed_command.py`) and on PostgreSQL 16, run by hand twice on a freshly migrated database: 72 accounts, 48 events and 544 registrations each time, so the second run's `TRUNCATE` emptied the first.
- **Files touched:** `seeds/showcase.py`, `tests/test_bandit_clean.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ `bandit -ll -q` over the tracked non-test files reports no Medium or High finding. [T `tests/test_bandit_clean.py::test_bandit_finds_nothing_medium_or_high` (fails on the old code with the two B608 findings)]
  2. ✅ Test: `python seed.py --profile showcase` still empties the tables and rebuilds the portal (`tests/test_seed_command.py`). [T `tests/test_seed_command.py::test_the_showcase_profile_rebuilds_the_portal_and_writes_its_summary`; PostgreSQL by hand, above]

#### UPG-114 — The waitlist shows a position that can repeat
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-114: …" on `production-ready` (parent `6f35c5e`) [T]
- **Problem:** Found in UPG-112. Both join paths store `position` as the number still waiting plus one (`routes_waitlist.py:70-88`, `routes_forms.py:751-774`), so after a promotion or a departure two people can hold the same number, or a later joiner a lower one (shown in `tests/test_waitlist_promotion.py`). Promotion no longer uses it (join order since UPG-112), but `/waitlist/status/<event_id>` and the "joined the waitlist at position #N" message still show it.
- **What to build:** work out the place in line at read time (how many waiting people joined earlier, plus one), and show that.
- **Built (2026-10-19):**
  - **One order, worked out when shown:** `services_waitlist.py` gives the waitlist in join order (`joined_at`, then the entry's id for two joined in the same instant). A place is one more than the number still waiting who joined earlier. It's used by:
    - the join answer and its notice (`routes_waitlist.join_waitlist`);
    - the status endpoint (`waitlist_status`);
    - the organiser's list (`view_waitlist`, each row with its place now);
    - the student's waitlist badge (`routes_participant.waitlist_status`);
    - the "joined the waitlist at position #N" message on both registration forms (`routes_forms`, `routes_participant`);
    - promotion (`auto_promote`).
    So places never repeat, close up when someone ahead leaves or is promoted, and match the order of promotion. The stored `position` is only the place on the day the person joined. Putting back the old status and list code fails the main test.
  - **Found, not fixed (UPG-117):** the JSON join (`POST /waitlist/join/<event>`) accepts only events in the old `active` status, not `registration_open`. No page calls it (the registration form waitlists people itself).
- **Files touched:** `services_waitlist.py` (new), `routes_waitlist.py`, `routes_forms.py`, `routes_participant.py`, `tests/test_waitlist_places.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: after one promotion and one departure, each person still waiting sees a distinct place that matches the order they'll be promoted in. [T `tests/test_waitlist_places.py::test_places_follow_join_order_and_never_repeat` (status, organiser's list, badge and promotion agree after a promotion and a departure), `::test_two_who_joined_in_the_same_instant_still_get_different_places`, `::test_the_registration_form_says_the_right_place`]
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** matches the code. Still TODO.

#### UPG-115 — Two registration forms sent at the same instant register the same person twice
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-115: …" on `production-ready` (parent `3910397`) [T]
- **Problem:** Found testing UPG-26. The duplicate check in `routes_forms.submit_form` (`routes_forms.py:647-656`) reads the event's registrations for the email, then writes a new one. Two different forms for one email (two tabs, or the form and a resend with a new `submission_id`) sent at the same instant both pass the read: 6 of 6 tries made two registrations. UPG-26's submission key covers one form sent twice, not two forms. On a paid event each holds a seat and can reach checkout.
- **What to build:** make "one registration per person per event" atomic: a unique claim on (event, lead email) taken before the write (as UPG-26's submission keys are), released if the registration fails; or a unique index if the native table can carry one.
- **Built (2026-10-19):**
  - **The database keeps the rule (owner, 2026-10-19: "enforced by the database, not only in the form code"):** a partial unique index `uq_registrations_active_lead` on registrations (event, lower(lead email)) where the status isn't cancelled or waitlisted. It's declared on the model (`models_pg.py`, `Registration.__table_args__`) and created by migration `migrations/versions/0007_one_active_registration.py`. Before creating it, the migration looks for people already registered twice and, if there are any, stops and lists them (it never changes a registration); `docs/DEPLOY.md` says what to do. Development start-up now also adds missing indexes (`db_pg.init_db`), logging one that existing rows break.
  - **Every way in handles the refusal:** `utils.create_registration` turns it into `AlreadyRegistered`:
    - the registration form (`routes_forms.submit_form`) and the participant route answer "You're already registered for this event";
    - the coordinator's walk-in says the person is already registered;
    - a paid registration refused this way returns `already_registered`, so the paid order stays on the admin's payments page for a refund (UPG-30's path);
    - the waitlist promotion marks that entry `already_registered` and promotes the next person.
  - **Found and fixed with it:** for a new email, both tabs also created the account, and the second hit the users table's unique email ("Submission failed"). `create_unverified_account` now reports whether it created the account; if another tab made it a moment earlier, the form carries on with it and doesn't send a second set-password link.
  - Passes on SQLite and PostgreSQL 16. The PostgreSQL test database was rebuilt first: 16 duplicate pairs left by earlier race tests had kept the index from being created, as designed.
- **Files touched:** `models_pg.py`, `migrations/versions/0007_one_active_registration.py` (new), `db_pg.py`, `utils.py`, `services_accounts.py`, `routes_forms.py`, `routes_payment.py`, `routes_participant.py`, `routes_coordinator.py`, `routes_waitlist.py`, `docs/DEPLOY.md`, `tests/test_one_registration.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low; existing duplicates (if any) must be checked before adding a constraint.
- **Acceptance criteria:**
  1. ✅ Test: two different forms for the same email, sent at the same instant (a barrier, repeated), make exactly one registration; the other answer says the person is already registered. [T `tests/test_one_registration.py::test_two_tabs_at_once_give_one_registration` (5 tries, each one registration and one "already registered"), `::test_the_database_refuses_a_second_active_registration_in_any_case`, `::test_a_cancelled_registration_doesnt_block_registering_again`, `::test_a_paid_order_the_database_refuses_is_kept_for_a_refund`, `::test_the_waitlist_skips_someone_already_registered`, `::test_the_migration_refuses_to_run_over_duplicates`]
  2. ✅ Test: on SQLite and PostgreSQL. [T the same file on PostgreSQL 16 (`TEST_DATABASE_URL`): 10 passed; `tests/test_migrations_baseline.py` builds the schema from empty with 0007 and matches the models]
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** matches the code (`routes_forms.py:647-656` reads, then writes). Still TODO.
- **Corrected 2026-10-19 (Part 3 full run):** the index also covered registrations with no lead email (old or imported rows, and some tests), so two of those in one event blocked each other (`tests/test_event_popup.py` failed). The rule now applies only to rows that name a person (`"leadEmail" <> ''`, `models_pg.ACTIVE_WHERE` and migration 0007, which hadn't run on any deployed database). New test: `tests/test_one_registration.py::test_registrations_without_an_email_dont_block_each_other`. A development database that already got the first version of the index keeps it until the index is dropped (`DROP INDEX uq_registrations_active_lead`) and the app restarted.

#### UPG-116 — A popup test fails when a random event id contains "999"
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-116: …" on `production-ready` [T]
- **Problem:** Found in the end-of-Part-2 full run. `tests/test_event_popup.py::test_registrations_shown_are_counted_not_cached` plants a cached count of 999 and checked `'999' not in popup`. The page includes the event's random id (in the `.ics` link); when that id held "999" (`…-29997b0f4084`), the test failed with nothing wrong in the app.
- **Built (2026-10-19):** the check looks for 999 as a number on its own (not inside a word or an id), so it still catches the cached count shown and no longer trips on an id.
- **Files touched:** `tests/test_event_popup.py`.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: the popup test passes whatever the event id is, and still fails if the cached count is shown. [T `tests/test_event_popup.py::test_registrations_shown_are_counted_not_cached`; a page showing "999 registered" still fails it]

#### UPG-118 — The CI secret scan flags the production boot test's dummy settings
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-118: …" on `production-ready` [T]
- **Problem:** Found in Part 3's full-history gitleaks scan (8.30.1, CI's version and command). `tests/test_production_boot.py` (UPG-20, commit `216f7a3`) held its strong dummy `SECRET_KEY`, `MASTER_SECRET_KEY` and `JWT_SECRET_KEY` as literals; gitleaks reported them as 3 `generic-api-key` leaks, so CI's secret-scan job would fail. They were never real values.
- **Built (2026-10-19):** the test makes its dummy settings at run time (`secrets.token_urlsafe`), so no secret-looking literal remains; the three findings in commit `216f7a3` are listed in `.gitleaksignore` as accepted test dummies, as the repo records the others.
- **Files touched:** `tests/test_production_boot.py`, `.gitleaksignore`.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ `gitleaks git --redact --exit-code 1 --gitleaks-ignore-path .gitleaksignore .` over the full history finds nothing [R, Part 3 release check]; `tests/test_production_boot.py` still passes.

#### UPG-119 — Werkzeug 3.1.8 has a known vulnerability (fixed in 3.1.9)
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-119: …" on `production-ready` [T]
- **Problem:** Found by Part 3's `pip-audit` of a fresh install of `requirements-dev.txt`: Werkzeug 3.1.8 has PYSEC-2026-4312 (`safe_join` accepts Windows device names with an empty ADS marker, so `send_from_directory` can hang on Windows/NTFS). The app runs on Linux (Cloud Run), so it isn't exposed, but the fix is a patch release. The same audit lists setuptools 79.0.1 (PYSEC-2026-3447, building source distributions on macOS); setuptools comes with the virtual environment, not from `requirements.txt`, and the app never builds packages, so it's recorded, not changed.
- **Built (2026-10-19):** `requirements.txt` pins `Werkzeug==3.1.9`.
- **Files touched:** `requirements.txt`.
- **Effort:** S · **Depends on:** none · **Risk:** low (patch release).
- **Acceptance criteria:**
  1. ✅ `pip-audit` reports no vulnerability in the app's requirements [R, Part 3 release check]; the full pytest passes on Werkzeug 3.1.9 [T, Part 3 release check].

#### UPG-120 — Volunteers can't log in
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-120: …" on `production-ready` [T]
- **Problem:** Found by Part 3's browser pass of every role. A volunteer account's role is `Volunteer` (staff appointment, the showcase seed), but the login form offered Student, Event coordinator, Club SPOC, Judge and Super admin only. The login refuses a role that doesn't match the account (`routes_auth.py`), so a volunteer could never sign in. Their home, the scanner list, and the scan page also admitted only coordinators and admins. `tests/test_volunteer_scope.py` had covered volunteers' check-in rights by setting the session directly, so it never met the login.
- **Built (2026-10-19):** the form offers "Event volunteer" (`templates/login.html`). The scanner list and the scan page admit volunteers (`routes_coordinator.py`); both already show and open only the events where the person is on the staff, and the check-in still checks the event (UPG-02, BLK-18).
- **Files touched:** `templates/login.html`, `routes_coordinator.py`, `tests/test_volunteer_login.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a volunteer logs in and lands on the scanner list. [T `tests/test_volunteer_login.py::test_a_volunteer_logs_in_and_lands_on_the_scanner`, `::test_the_login_form_offers_every_role_an_account_can_have` (both fail on the old form)]
  2. ✅ Test: they see and open only the events they're staff on, and can't log in as another role. [T `::test_a_volunteer_scans_only_the_events_they_are_staff_on`, `::test_a_volunteer_cant_log_in_as_another_role`]

#### UPG-121 — The admin audit log's table is cut off on a phone
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-121: …" on `production-ready` [T]
- **Problem:** Found by Part 3's browser pass of every role (production build, 375px). The audit log's table sits in a card with `overflow: hidden` (`templates/admin/audit_log.html`), so on a phone its right-hand columns were clipped and couldn't be scrolled to. UPG-23's key pages didn't include the audit log.
- **Built (2026-10-19):** the table is wrapped in Bootstrap's `.table-responsive`, so it scrolls sideways inside its card. UPG-23's 375px check now includes `/admin/audit_log` (with a row to lay out) and `/admin/payments`.
- **Files touched:** `templates/admin/audit_log.html`, `tests/test_shared_layout.py`.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: at 375px the audit log has no clipped content and doesn't scroll the page sideways. [T `tests/test_shared_layout.py::test_key_pages_fit_a_375px_phone_and_lose_nothing` (fails on the old template)]

### H. Certificates (owner, 2026-10-19: "Certificates are now in scope")

**Step 0, stock-take (2026-10-19, at `eaea1fe`).** Certificates were out of scope from 2026-10-10. What exists:
- **One issuing path:** `utils_certificate.issue_event_certificates` (UPG-06), called by end-event (`tasks/cert_tasks.bulk_generate_certificates`) and the SPOC's bulk button (`routes_spoc.bulk_certs`). For each registration marked Present without a `certificate_id`, it gives:
  - the top three scorers a "winner" certificate, everyone else "participation";
  - only the team lead, never the members;
  - a PDF drawn by ReportLab (`generate_certificate_pdf`, or an uploaded image template), not stored;
  - a record in `verified_certificates/<id>` and the ID on the registration;
  - an emailed PDF.
- **Weak spots:**
  - The ID is a SHA-256 of who and what (`certificate_id_for`), so it's deterministic, not random.
  - The college name, "Dean of Student Affairs" and three signature blocks are hard-coded.
  - There are no signatories, no other types, no hours or points (UPG-11 criterion 4), no designation or institution (UPG-12 criterion 2), and no multi-day rule.
  - PDFs are re-drawn on download (`/verify/<id>/download`), so nothing detects a changed file.
  - There's no revocation or correction.
  - API v1 has a second store, `services_certificate.CertificateService` writing `certificates/<id>`, which `/verify` never reads (UPG-14/UPG-112).
- **Verification today:** `routes_verification.py` (`/verify/<hash>`, `/preview`, `/download`); `app.py` `/verify` (a lookup form); `routes_coordinator.py` `/certificate/<reg_id>/<usn>` (the legacy attendance check). The verification pages hard-code a support address (UPG-65).
- **Fonts:** Helvetica only. ReportLab 5 shapes Kannada and Devanagari correctly with `uharfbuzz` and `shapeStr` (checked: conjuncts and vowel signs right). Text extracted from a PDF can't round-trip shaped Indian-language glyphs, so the PDF-text test uses a Latin name.

The items below are built in this order, one commit each; each deferred part is built with the section it belongs to.

#### UPG-122 — Certificate types, who gets them, and one record per person, event and type
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-122: …" on `production-ready` (parent `c8ea1db`) [T]
- **What to build:**
  - **Types:** participation; winner, runner-up and other positions (from published results); merit or special mention; volunteer; coordinator or organiser; judge; speaker or resource person; FDP or workshop completion with hours; NSS / NCC / extension hours.
  - **Eligibility:**
    - participation and completion only for people marked Present;
    - multi-day events need a minimum share of days attended that the organiser sets (default 80%), counted from check-ins recorded per day;
    - every team member gets their own certificate, by their own attendance;
    - faculty and external participants carry designation and institution (UPG-12);
    - the event's activity points and hours are on the record when the event has them (UPG-11).
  - **One store:** a `certificates` table (migration 0008) replaces `verified_certificates` and API v1's `certificates/<id>` documents. A unique index keeps at most one current certificate per person, event and type, so issuing again never makes a duplicate.
- **Built (2026-10-19):**
  - **One store:** a `certificates` table (`models_pg.py:685-721` `Certificate`; migration `0008_certificates.py`): number, version, current flag, status (valid / revoked / superseded), event, person key, recipient name and email, registration, type, position, the wording as issued (`dataJson`), the private PDF key and its SHA-256, who issued it and when, and the revocation fields. A unique partial index (`uq_certificates_current`: event, person, type WHERE current) keeps at most one current certificate per person, event and type; `(number, version)` is unique.
  - **Who gets what** (`services_certificates.py`): `TYPES` (`:31`) covers participation, completion (workshop, FDP, orientation), extension hours (NSS/NCC, social drives), position, merit, volunteer, coordinator, organiser, judge and speaker. `recipients()` (`:177`) lists every certificate the event owes: participants marked Present (lead and each team member by their own attendance), positions from published results (`services_leaderboard` podium), staff by role, the organiser, and listed speakers or resource persons; deduplicated by person and type.
  - **Attendance per day:** check-in records each IST day attended (`routes_ticket.py:123`, `:180-203`: a second day's scan on a Present ticket is "Entry granted (day N)"); a multi-day event needs the organiser's minimum share of days (`min_attendance`, default 80%; `attended_enough` `:104`).
  - **Designation, institution, hours and points** are on each record's wording (UPG-12, UPG-11).
  - **Issuing never duplicates:** `claim()` (`:250`) inserts the record and treats the index's refusal as "already issued"; `issue_event()` (`:404`) renders only the PDFs it claimed, stores them privately with their SHA-256 (`store_pdf` `:363`; `utils_storage.put_private`/`get_private`, never under `static/`), and takes over a record left without a PDF for 10 minutes by a conditional update (`_take_over` `:376`), so two runs at once draw each PDF once.
  - The PDF itself is still the old generator here; UPG-123 replaces it.
- **Files touched:** `models_pg.py`, `migrations/versions/0008_certificates.py` (new), `services_certificates.py` (new), `utils_storage.py`, `routes_ticket.py`, `.env.example`, `tests/test_certificate_types.py` (new)
- **Effort:** L · **Depends on:** UPG-06, UPG-11, UPG-12 · **Risk:** medium (the store moves).
- **Acceptance criteria:**
  1. ✅ Test: an Absent participant gets no participation certificate; a multi-day event with an 80% minimum certifies someone who attended 4 of 5 days and not 3 of 5. [T `tests/test_certificate_types.py`::test_absent_people_and_too_few_days_get_no_participation_certificate, ::test_check_in_records_each_day_attended]
  2. ✅ Test: a team of 3 present members gets 3 certificates, each in the member's own name. [T `tests/test_certificate_types.py`::test_every_team_member_gets_their_own_certificate]
  3. ✅ Test: positions from published results give winner/runner-up/position certificates; staff on the event get volunteer, coordinator and judge certificates; listed speakers get speaker certificates; an FDP gives completion certificates with hours; an NSS event gives extension-hours certificates. [T `tests/test_certificate_types.py`::test_positions_staff_organiser_and_speakers, ::test_unpublished_results_give_no_position_certificates, ::test_fdp_gives_completion_with_hours_and_nss_gives_extension_hours]
  4. ✅ Test: issuing twice, or two runs at once, leaves exactly one certificate per person, event and type (the database refuses a second); on SQLite and PostgreSQL. [T `tests/test_certificate_types.py`::test_issuing_twice_never_duplicates, ::test_two_runs_at_once_leave_one_certificate_each, ::test_the_database_refuses_a_second_current_certificate, ::test_a_record_left_without_a_pdf_is_finished_by_a_later_run; SQLite and PostgreSQL]
  5. ✅ Test: a faculty participant's certificate record carries designation and institution; an event's hours and points are on its certificates. [T `tests/test_certificate_types.py`::test_faculty_designation_and_event_hours_are_on_the_record]
- **2026-10-19 (follow-up, from its full run):** `tests/test_one_registration.py::test_the_migration_refuses_to_run_over_duplicates` failed: it seeds a database at 0006 through the app, development start-up creates the new `certificates` table, and migration 0008 then refused ("table certificates already exists"). 0008 now takes an existing table and creates only the indexes it lacks (`migrations/versions/0008_certificates.py`). The test passes again on SQLite and PostgreSQL; nothing in it changed.

#### UPG-123 — Certificate templates, branding and each event's signatories
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-123: …" on `production-ready` (parent `912a445`) [T]
- **What to build:**
  - **Templates:** a default template per type, with the college's name, logo and colours from settings.
  - **Signatories, per event:** 1 to 3 on the event's page ("Certificate signatories"), each with a name, title, order and signature image. The image must be PNG or JPG, at most 1 MB, with a white or transparent background; it's trimmed and resized, and anything else is refused with a clear message.
  - **Copying:** a SPOC can copy the signatories from one of their own earlier events.
  - **Private storage:** signature images are stored privately and served only inside certificates and to the event's staff.
  - **Gate:** certificates can't be issued until the event has at least one signatory with a signature, and the button says what's missing.
  - **History:** changes affect only certificates issued afterwards (each certificate keeps a snapshot) and are audit-logged.
  - **Per event:** the organiser picks the template, and a live preview shows the real signatories with sample data.
  - **Wording:** filled from the event (name, title, type, department, dates, position or role, hours, issue date).
  - **Fonts and safety:** Noto Sans with Kannada and Devanagari, shaped; every value is escaped, and long names shrink to fit.
  - **Number and QR:** each certificate has a unique, unguessable number and a QR code to its verification page on `BASE_URL`.
- **Built (2026-10-19):**
  - **The certificate** (`certificate_pdf.py`, new): A4 landscape in two templates (`STYLES` `:34`, classic and modern), each type with its own title and accent colour (`TYPE_ACCENTS` `:35`). The college's name, logo and colours come from `COLLEGE_NAME`, `COLLEGE_LOGO_PATH` (a file under `static/` only), `CERT_PRIMARY_COLOR` and `CERT_ACCENT_COLOR` (`branding` `:148`; `.env.example`). It prints the name, the designation and institution, a sentence from the event (phrase, title, team, dates, hours, points), the signatories left to right with their signatures, the number, the issue date, the verification link and a QR code to `BASE_URL/verify/<number>` (`render` `:182`).
  - **Fonts:** Noto Sans, Noto Sans Kannada and Noto Sans Devanagari (OFL, `static/fonts/certificate/`), chosen per run of script (`runs` `:62`) and shaped with HarfBuzz (`uharfbuzz`, in `requirements.txt` with `pypdfium2`), with widths measured on the shaped text. Every value is drawn as text, never markup. Names shrink to fit, and a very long name goes onto two lines (`name_lines` `:119`).
  - **Signatories** (`services_signatories.py`, new): 1 to 3 per event with name, title, order and a signature. `process_signature` (`:30`) refuses anything but PNG or JPG, over 1 MB, or on a dark background, each with a clear message; it makes the background transparent, trims to the ink and resizes to at most 600×200. Images are stored with `put_private` (UPG-122), never under `static/`. Add, remove, reorder and copy from one of the SPOC's own events (`:112-167`; copies get their own image files), each audit-logged (`CERT_SIGNATORY_ADDED`, `_REMOVED`, `CERT_SIGNATORIES_REORDERED`, `_COPIED`).
  - **The event's certificate page** (`routes_certificates.py`, new blueprint, `/certificates/events/<id>`, linked from the SPOC's event review page): the signatories table, the add and copy forms, the template choice (audit-logged as `CERT_TEMPLATE_CHOSEN`) and a live preview PNG with the real signatories and sample data (`:182`). Managing needs `edit_event`; the page and preview also open for `issue_certificates`. Signature images are served only to the event's staff, `Cache-Control: private, no-store` (`:144`).
  - **Gate:** `issue_event` refuses, with the message saying what's missing, until a signatory has a signature (`services_certificates.require_signatories` `:405`); the certificate page shows the same message.
  - **History:** each certificate's wording keeps a snapshot of its signatories and template (`wording` `:327`), so later changes affect only certificates issued afterwards.
- **Files touched:** `certificate_pdf.py` (new), `services_signatories.py` (new), `routes_certificates.py` (new), `templates/certificates/manage.html` (new), `static/fonts/certificate/` (new: 6 Noto fonts, OFL), `services_certificates.py`, `app.py`, `templates/spoc/review_event.html`, `requirements.txt`, `.env.example`, `tests/test_certificate_signatories.py` (new), `tests/test_certificate_types.py` (its events get a signatory)
- **Effort:** L · **Depends on:** UPG-122, UPG-21, UPG-99 · **Risk:** medium.
- **Acceptance criteria:**
  1. ✅ Test: only someone with `edit_event` on the event can add, reorder, remove or copy signatories; a fourth is refused; a GIF, a 2 MB file, a non-image and a dark-background image are refused with a clear message; an accepted image is trimmed and resized. [T `tests/test_certificate_signatories.py`::test_only_editors_manage_signatories_and_bad_images_are_refused, ::test_an_accepted_signature_is_trimmed_resized_and_transparent, ::test_reorder_remove_and_copy_from_an_own_event]
  2. ✅ Test: a signature image is never at a public URL: the event's staff can fetch it, another SPOC and a student get 403. [T `tests/test_certificate_signatories.py`::test_signature_images_are_private]
  3. ✅ Test: issuing is refused, with a message saying what's missing, until a signatory has a signature. [T `tests/test_certificate_signatories.py`::test_no_certificate_without_a_signature]
  4. ✅ Test: certificates issued before a signatory change keep the old signatories; later ones show the new; each change is audit-logged. [T `tests/test_certificate_signatories.py`::test_issued_certificates_keep_their_signatories_and_changes_are_audited]
  5. ✅ Test: the preview shows the real signatories and sample data; the college name and logo come from settings. [T `tests/test_certificate_signatories.py`::test_the_preview_shows_real_signatories_and_branding_comes_from_settings]
  6. ✅ Test: the PDF's text holds the recipient's name, the event and the certificate number (extracted in the test); a 120-character name stays inside the page; markup in a name is printed as text; a Kannada name uses the Kannada font; the number is random, not derived from the person; the QR encodes `BASE_URL/verify/<number>`. [T `tests/test_certificate_signatories.py`::test_the_pdf_says_who_what_and_which_number, ::test_long_names_fit_and_markup_is_printed_as_text, ::test_a_kannada_name_uses_the_kannada_font, ::test_the_number_is_random_and_the_qr_links_to_verification]
- **Note:** the "Issue certificates" button comes with UPG-124; it uses the same gate and message. Shaped Kannada and Devanagari text can't be read back from a PDF, so the PDF-text checks use Latin names and the Kannada check looks for the embedded font.

#### UPG-124 — Issuing certificates: in bulk in the background, automatically on results, and by hand
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-124: …" on `production-ready` (parent `cd1842b`) [T]
- **What to build:**
  - **Bulk:** from the event's page after the event ends, and automatically when results are published (the organiser can switch the automatic issue off).
  - **Background:** runs through the outbox (UPG-18) in chunks, with progress, failures and a retry shown to the organiser.
  - **By hand:** issue to one person (a late attendance fix), and see who got which certificate.
  - **Integrity:** each PDF is stored privately with its SHA-256 on the record, so a changed file is detected.
- **Built (2026-10-19):**
  - **Runs** (`services_certificate_runs.py`, new): `start` (`:61`) fixes who a run covers (everyone the event owes, or some types), splits them into chunks of `CERT_CHUNK_SIZE` (default 100), records the run in `certificate_runs/<id>` and queues `tasks.cert_tasks.issue_certificate_run` (`tasks/cert_tasks.py:52`). Without a broker the task runs inline under `TASK_INLINE_TIMEOUT`, goes on in a thread past it, and is retried by the outbox's cron job if its process stops (UPG-18). `work` (`:123`) does the unfinished chunks and records each one's issued, already and failed counts and its errors; `progress` (`:115`) gives done and failed counts; `retry` (`:167`) queues the failed chunks again. Each person's certificate is issued once (`issue_one` and the unique index), so a retry or a second run issues nothing twice. Starting and retrying are audit-logged (`CERT_RUN_STARTED`, `CERT_RUN_RETRIED`).
  - **Not before the event ends:** `ready_to_issue` (`:49`) refuses until the event is completed or past its last day in IST (`services_certificates.event_ended` `:413`) and until a signatory has signed; the "Issue certificates" button is disabled with that reason under it.
  - **When results are published:** both publish routes (`routes_spoc.py:1046`, `routes_coordinator.py:483`) call `on_results_published` (`:186`), which issues the position certificates unless the organiser switched it off (`cert_auto_issue`, toggled on the certificate page and audit-logged as `CERT_AUTO_ISSUE`); without a signature it says so to the publisher.
  - **By hand:** `POST /certificates/events/<id>/issue_one` (`routes_certificates.py:268`) issues one owed person's certificate (e.g. after a late attendance fix), audit-logged as `CERT_ISSUED_BY_HAND`; someone not owed it is refused.
  - **The list:** the certificate page lists everyone owed a certificate with its number and date, or "Not yet" with an Issue button, plus anything issued earlier and no longer owed; recent runs show their progress (the page refreshes itself while one runs), failures and a retry button. `GET …/runs/<run id>` gives a run's progress as JSON.
  - **Integrity:** `file_check` (`services_certificates.py:424`) compares the stored PDF with the SHA-256 on its record; "Check the stored files" reports any that changed or are missing.
  - A PDF that can't be made no longer leaves its record behind (`_release` `:463`), so a retry can issue it at once.
  - Issuing, retrying and issuing by hand need `issue_certificates` on the event; the page opens with it or `edit_event`. The old path (end-event, the bulk button) still runs beside this until UPG-138.
- **Files touched:** `services_certificate_runs.py` (new), `services_certificates.py`, `tasks/cert_tasks.py`, `routes_certificates.py`, `templates/certificates/manage.html`, `routes_spoc.py`, `routes_coordinator.py`, `tests/test_certificate_issuing.py` (new)
- **Effort:** M · **Depends on:** UPG-122, UPG-123, UPG-18 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a bulk issue for 1,200 eligible people runs in chunks and finishes; progress reports done and failed counts; a failed chunk can be retried and issues nothing twice. [T `tests/test_certificate_issuing.py`::test_a_bulk_issue_for_1200_people_runs_in_chunks_reports_progress_and_retries: 1,200 participants and the organiser in 13 chunks, 3 failed, retried to 1,201 with 1,201 distinct numbers, a third run issues 0; SQLite and PostgreSQL]
  2. ✅ Test: publishing results issues the position certificates; with the automatic issue switched off it doesn't. [T `tests/test_certificate_issuing.py`::test_publishing_results_issues_the_position_certificates, ::test_with_the_automatic_issue_off_publishing_issues_nothing, ::test_publishing_without_a_signatory_says_why_nothing_was_issued]
  3. ✅ Test: issuing before the event ends is refused; issuing to one person works and is audit-logged; the organiser's list shows who got which certificate. [T `tests/test_certificate_issuing.py`::test_not_before_the_event_ends_then_by_hand_with_the_list, ::test_an_event_past_its_last_day_can_issue]
  4. ✅ Test: the stored PDF's SHA-256 matches the record; a changed file is reported as changed. [T `tests/test_certificate_issuing.py`::test_the_stored_pdf_matches_its_hash_and_a_changed_file_is_reported, ::test_a_failed_render_leaves_nothing_behind]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO. Since written, UPG-122 stores each PDF privately with its SHA-256 on the record (`services_certificates.store_pdf`) and issues in one call (`issue_event`), and UPG-123 adds the signatory gate the button must show; what's left is the outbox chunks and progress, the automatic issue on results with its switch, issuing to one person, the after-the-event check, the list, the changed-file check, and moving end-event and the bulk button (`utils_certificate.issue_event_certificates`, UPG-06) onto the new service.
- **Note:** the 1,200-person test stubs out drawing the PDF (its content is tested in UPG-123); the database, storage, chunks, task and outbox path are real.
- **2026-10-19 (follow-up, from the full run at `45899bf`):** `CERT_CHUNK_SIZE` was missing from `.env.example`, which `tests/test_production_boot.py::test_every_environment_variable_the_app_reads_is_in_env_example` requires; added.
- **2026-10-19 (follow-up, the final headless pass):** `tests/test_certificate_phone.py::test_the_organiser_signs_issues_and_lists_on_a_phone`: in headless Chromium with a real login, the organiser's certificate page (unsigned, with the Issue button disabled; after adding a signatory through the form with a real upload; after issuing 31 certificates from the button, with the run shown done) and the list page are measured at 375px and 1280px (UPG-23's measure): no sideways scroll or cut-off text. Nothing needed changing.

#### UPG-125 — Delivering certificates: email, "My certificates", sharing and phones
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-125: …" on `production-ready` (parent `9b1be9f`) [T]
- **What to build:**
  - **Email:** one per certificate, with a signed, expiring download link (never sent twice).
  - **"My certificates":** a list on the student and faculty dashboards, with links from the participation ledger (UPG-11).
  - **Sharing:** a share link, and "download PNG for LinkedIn".
  - **Phones:** downloads work on a 375px phone screen (UPG-28's certificate part).
- **Built (2026-10-19):**
  - **Email, once:** each issued certificate queues `tasks.email_tasks.send_certificate_email` (`services_certificates.deliver` `:561`; outbox-backed). `email_once` (`:572`) claims the send with a conditional update on `emailedAt`, so it goes out once; a failed send gives the claim back and the outbox retries it. The email (`utils_email.send_certificate_issued_email`, `utils_email.py:1139`) has a signed download link, how long it works, the number and the verification link; every value is escaped.
  - **Signed links:** `itsdangerous` with the app's `SECRET_KEY` and its own salt, carrying the number and version (`download_token` `:547`), valid for `CERT_LINK_DAYS` (default 30; `read_token` `:551`). `/certificates/download/<token>` (`routes_certificates.py:393`) serves the stored PDF if the file still matches its SHA-256; an expired link says so (410), an altered one isn't valid (404), and a replaced or revoked certificate's link says it was replaced (410), each on `templates/certificates/link_problem.html` (new).
  - **"My certificates"** (`/certificates/mine`, `:356`; `templates/certificates/mine.html`, new): the signed-in person's current certificates (team members get their own, by their email), with Download PDF, Image for LinkedIn, a share link (the public page) and Share on LinkedIn. Linked from the student navigation, the dashboard (students and faculty share it) and the participation ledger, whose rows link each event's certificate (`routes_participant.py:901-935`, `templates/participant/ledger.html`).
  - **Own downloads:** `/certificates/c/<number>/pdf` and `/png` (`:377`, `:383`) are for the certificate's own person and the event's staff who manage certificates (`_may_download` `:328`); the PNG is drawn from the stored PDF (`certificate_pdf.to_png`, 2×).
  - **Phones:** the status layout lets a page unpin its footer (`templates/layouts/status.html`; the default stays pinned), and the verification page does, as it can be longer than a phone screen.
- **Files touched:** `services_certificates.py`, `utils_email.py`, `tasks/email_tasks.py`, `routes_certificates.py`, `templates/certificates/mine.html` (new), `templates/certificates/link_problem.html` (new), `templates/certificates/verify.html`, `templates/layouts/status.html`, `templates/includes/ui.html`, `templates/participant/dashboard.html`, `templates/participant/ledger.html`, `routes_participant.py`, `tests/test_certificate_delivery.py` (new), `tests/test_certificate_phone.py` (new)
- **Effort:** M · **Depends on:** UPG-124 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: each certificate sends exactly one email whose link downloads the PDF; the link stops working after it expires and when altered; a re-run sends nothing. [T `tests/test_certificate_delivery.py`::test_one_email_per_certificate_with_a_link_that_expires_and_resists_tampering, ::test_a_failed_send_is_retried_and_still_sent_once, ::test_a_replaced_certificates_link_says_so]
  2. ✅ Test: "My certificates" lists the person's certificates (team members included) and the ledger links them. [T `tests/test_certificate_delivery.py`::test_my_certificates_lists_the_persons_own_including_team_members]
  3. ✅ Test: the PNG download is a real image of the certificate; the share link opens the public verification page. [T `tests/test_certificate_delivery.py`::test_the_png_is_an_image_of_the_certificate_and_the_share_link_verifies]
  4. ✅ Test: at 375px the list and the download work in headless Chromium, with no sideways scroll. [T `tests/test_certificate_phone.py::test_certificates_fit_a_phone_and_download_from_it`: real login, the list and the verification page measured at 375 and 1280, the PDF downloaded in the browser and compared with the stored file]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO; nothing delivers the new certificates yet.
- **2026-10-19 (follow-up, from the full run at `45899bf`):** `CERT_LINK_DAYS` was missing from `.env.example`, which `tests/test_production_boot.py::test_every_environment_variable_the_app_reads_is_in_env_example` requires; added.

#### UPG-126 — Verifying a certificate
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-126: …" on `production-ready` (parent `45899bf`) [T]
- **What to build:**
  - **`/verify/<certificate number>`:** valid, revoked (with the date) or replaced, showing the name, event, date, type and college, never email, phone or other personal data.
  - **Support address** from `SUPPORT_EMAIL` (UPG-65).
  - **Limits:** rate limits on the page and the lookup.
  - **Legacy routes:** the lookup form and the coordinator's legacy check go to the new page; old certificate IDs keep their legacy pages (see criterion 3).
- **Built (2026-10-19):**
  - **`/verify/<number>`** (`routes_verification.py:54`, `_number_page` `:27`; `templates/certificates/verify.html`, new): a certificate number shows "Valid", "Revoked" with the date (not the reason), or, for `/verify/<number>/v<n>` (`:35`), "Replaced" with the current version and its date. It shows the name, the type (and place), the event, its dates, the college (`COLLEGE_NAME`), the issue date and the number, from `services_certificates.public_view` (`:317`), which never returns an email, phone, USN or registration ID. An unknown number is a 404 "Certificate not found". Numbers are accepted in any case (`looks_like_number` `:300`).
  - **Support address:** the new page shows `SUPPORT_EMAIL` when it's set (UPG-134 does the legacy pages).
  - **Limits:** every lookup (`/verify/<id>`, its version, preview and download, and the lookup form's POST, `app.py:1315`) shares one limit per address, `VERIFY_RATE_LIMIT` (default 30 a minute; `verify_rate` `:24`), then 429.
  - **The form and the legacy check:** the lookup form takes a number in any case, with spaces, and redirects to its page; the coordinator's `/coordinator/certificate/<reg>/<usn>` redirects to the person's new certificate when they have one (`routes_coordinator.py:796`) and otherwise shows the old page as before.
  - **Older IDs:** `verified_certificates` hashes and registration IDs keep their pages at the same address (criterion 3's note).
- **Files touched:** `routes_verification.py`, `templates/certificates/verify.html` (new), `services_certificates.py`, `app.py`, `templates/public/verify_lookup.html`, `routes_coordinator.py`, `tests/test_certificate_verification.py` (new)
- **Effort:** M · **Depends on:** UPG-122 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a valid certificate shows valid with the name, event, date, type and college, and no email or phone; an unknown number shows not found; a revoked one shows revoked and the date; a replaced version shows it was replaced. [T `tests/test_certificate_verification.py`::test_a_valid_certificate_shows_its_facts_and_no_personal_data, ::test_an_unknown_number_is_not_found, ::test_a_revoked_certificate_shows_revoked_and_the_date, ::test_a_replaced_version_says_it_was_replaced]
  2. ✅ Test: more than the limit of lookups a minute from one address gets 429. [T `tests/test_certificate_verification.py`::test_lookups_past_the_limit_get_429]
  3. ✅ Test: the lookup form and the coordinator's legacy check redirect to the new page; `/verify/<old hash>` keeps showing its legacy record. *(Reworded 2026-10-19 while building: old hashes and registration IDs are printed on certificates already issued and have no new number, so they keep their own pages at the same address until UPG-138 retires the old store; UPG-06's tests check those pages and stay as they are.)* [T `tests/test_certificate_verification.py`::test_the_lookup_form_and_the_legacy_check_lead_to_the_new_page; UPG-06's `tests/test_certificates.py` and `tests/test_coordinator_authz.py` unchanged and passing]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO; `/verify/<number>` doesn't exist yet. UPG-136 changed only the old preview's venue (`routes_verification.py:87-91`).
- **2026-10-19 (follow-up, from the full run at `45899bf`):** `VERIFY_RATE_LIMIT` was missing from `.env.example`, which `tests/test_production_boot.py::test_every_environment_variable_the_app_reads_is_in_env_example` requires; added.
- **2026-10-19 (follow-up, from the end-of-phase type check):** `routes_verification.py` uses `limiter.shared_limit`, which the no-op limiter `extensions.py` falls back to without flask-limiter didn't have, so the module would fail to import there. Added (`extensions.py`); `tests/test_certificate_verification.py::test_the_verification_limits_work_without_flask_limiter_too` runs the module's fallback and fails without the fix.

#### UPG-127 — Correcting and revoking certificates
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-127: …" on `production-ready` (parent `979a228`) [T]
- **What to build:**
  - **Corrections:** a student asks for a name correction from "My certificates", and the organiser approves or rejects it. On approval, a new version replaces the old one with the same number, and the old file no longer verifies as current.
  - **Revocation:** an organiser or admin revokes with a reason, and verification shows "revoked" and the date.
  - **Audit:** every issue, correction and revocation is audit-logged.
- **Built (2026-10-19):**
  - **Corrections** (`services_certificate_changes.py`, new): the certificate's own person asks from "My certificates" (`POST /certificates/c/<number>/correction`, `routes_certificates.py:422`; `request_correction` `:59`), one open request per certificate, kept in `certificate_corrections/<id>`. The event's certificate page lists open requests; whoever holds `issue_certificates` approves or rejects (`routes_certificates.py:436`). Approving (`approve` `:99`, `new_version` `:110`) marks the current version superseded and adds the next version under the same number with the new name in one transaction, then draws, stores (with its SHA-256) and emails it. Rejecting changes nothing.
  - **Checking a file:** the verification page takes an uploaded PDF (`POST /verify/<number>/file`, `routes_verification.py:35`, rate-limited) and says whether it is the current version, a replaced one, a revoked one or not ours (`check_file` `:164`, by SHA-256).
  - **Revocation:** a reason is required (`revoke` `:146`; `POST /certificates/events/<id>/revoke`, `routes_certificates.py:456`); the verification page shows "revoked" with the date, never the reason; "My certificates" shows it revoked with no download, and its own download answers 410 (`:377`).
  - **Audit:** every certificate issued (`CERT_ISSUED`, `services_certificates._audit_issue` `:524`; possible from background runs since UPG-140), every correction asked for, approved or rejected, and every revocation with its reason.
- **Files touched:** `services_certificate_changes.py` (new), `services_certificates.py`, `routes_certificates.py`, `routes_verification.py`, `templates/certificates/manage.html`, `templates/certificates/mine.html`, `templates/certificates/verify.html`, `tests/test_certificate_changes.py` (new)
- **Effort:** M · **Depends on:** UPG-124, UPG-126 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: a correction request, approved, gives version 2 with the same number and the new name; version 1's hash no longer verifies as current; a rejected request changes nothing; only the certificate's owner can ask. [T `tests/test_certificate_changes.py`::test_a_correction_gives_version_2_with_the_same_number_and_version_1_stops_verifying]
  2. ✅ Test: a revocation needs a reason, shows on verification with the date, and is audit-logged. [T `tests/test_certificate_changes.py`::test_a_revocation_needs_a_reason_shows_on_verification_and_is_audited]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO; the `certificates` table has the version, status and revocation fields it needs (UPG-122).

#### UPG-128 — Certificate lists, exports and college-wide counts
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-128: …" on `production-ready` (parent `cb8772c`) [T]
- **What to build:**
  - **Per event:** the certificate list with search and pages (UPG-19), and CSV and XLSX exports.
  - **College-wide:** certificates issued per department, event type and month, as a data source for the NAAC/AQAR report (not built now).
- **Built (2026-10-19):**
  - **The event's list** (`/certificates/events/<id>/list`, `routes_certificates.py:485`; `templates/certificates/list.html`, new; linked from the certificate page): every current certificate with name, type and place, number and version, status and issue date, 25 a page with the shared pager (UPG-19), searched by name, number or type. For the event's staff (`edit_event` or `issue_certificates`).
  - **Exports** (`/certificates/events/<id>/export.csv` and `.xlsx`, `routes_certificates.py:496`): the list's rows, with its search, through `services_export` (formula-safe cells); columns `EXPORT_COLUMNS` (`services_certificates.py:654`).
  - **College-wide counts** (`services_certificates.college_counts`, `services_certificates.py:670`): valid current certificates per department, event type and month of issue, a data source for the NAAC/AQAR report (not built). Super Admins see them at `/certificates/reports/counts` (`templates/certificates/counts.html`, new; linked from the admin dashboard) and download them as CSV.
- **Files touched:** `services_certificates.py`, `routes_certificates.py`, `templates/certificates/list.html` (new), `templates/certificates/counts.html` (new), `templates/certificates/manage.html`, `templates/admin/dashboard.html`, `tests/test_certificate_lists.py` (new)
- **Effort:** S · **Depends on:** UPG-122 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: the event's list pages at 25, searches by name, number and type, and exports the same rows as CSV and XLSX. [T `tests/test_certificate_lists.py`::test_the_list_pages_at_25_searches_and_exports_the_same_rows]
  2. ✅ Test: the college-wide counts per department, event type and month match the certificates issued. [T `tests/test_certificate_lists.py`::test_the_college_wide_counts_match_the_certificates_issued: a revoked certificate and a back-dated one included]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO.

#### UPG-129 — Who may issue, revoke, approve and download certificates
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-129: …" on `production-ready` (parent `3396622`) [T]
- **What to build:** issuing, revoking and approving corrections only for the event's owner or someone holding `issue_certificates` on that event (`services_permission.can`); students download only their own certificates.
- **Built (2026-10-19):**
  - Every certificate action checks the event through `services_permission.can`: issuing, retrying a run, issuing to one person, revoking, approving or rejecting a correction and the automatic-issue switch need `issue_certificates` (`routes_certificates.py`, UPG-124 and UPG-127); the certificate page needs `edit_event` or `issue_certificates`; a certificate's own downloads are for its person and the event's staff who manage certificates (`_may_download`, UPG-125); asking for a correction is for the certificate's own person (UPG-127).
  - This item adds the test across every role. It found nothing to change: the event's owner, a Super Admin and an EventOrganizer assigned to that event alone may act; another SPOC and the event's own coordinator, judge and volunteer may not.
- **Files touched:** `tests/test_certificate_permissions.py` (new)
- **Effort:** S · **Depends on:** UPG-124, UPG-127 · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test, for each role (owner SPOC, another SPOC, coordinator, judge, volunteer, student, Super Admin): only the owner, Super Admin and anyone holding `issue_certificates` on the event can issue, revoke or approve; a student downloads their own certificate and gets 403 for someone else's. [T `tests/test_certificate_permissions.py::test_only_the_owner_an_admin_and_an_issue_certificates_holder_issue_revoke_and_approve` (8 roles × issue, retry, issue to one, revoke, approve, the switch and the page, each checked by its effect), `::test_a_student_downloads_only_their_own`; SQLite and PostgreSQL]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO. The certificate page already checks `edit_event` / `issue_certificates` per event (UPG-123); issuing, revoking and approving routes come with UPG-124 and UPG-127.

#### UPG-130 — Hours on the certificate (UPG-11's deferred criterion 4)
- **Status:** DONE · **Built with:** UPG-122/UPG-123
- **Last verified:** 2026-10-19, commit "UPG-130: …" on `production-ready` (parent `2312681`) [T]
- **Built (2026-10-19):** an event's activity hours and points go on each certificate's record (UPG-122) and into its sentence ("…, 12 hours (5 activity points).", `certificate_pdf.render`), for every type that has them.
- **Files touched:** `tests/test_certificate_wording.py` (new; the code came with UPG-122 and UPG-123)
- **Acceptance criteria:** 1. ✅ Test: a certificate for an event with hours shows the hours in its PDF text. [T `tests/test_certificate_wording.py::test_upg130_the_hours_are_in_the_pdf`: issued through `issue_event`, read back from the stored PDF]

#### UPG-131 — FDP wording with designation and institution (UPG-12's deferred criterion 2)
- **Status:** DONE · **Built with:** UPG-123
- **Last verified:** 2026-10-19, commit "UPG-131: …" on `production-ready` (parent `f2d7fcc`) [T]
- **Built (2026-10-19):** an FDP (or workshop or orientation) gives a completion certificate (UPG-122) whose record keeps the faculty member's designation and institution from their registration; the PDF prints them on their own line under the name ("Assistant Professor, Example College of Engineering"), with the hours in the sentence (`certificate_pdf.render`, UPG-123).
- **Files touched:** `tests/test_certificate_wording.py`
- **Acceptance criteria:** 1. ✅ Test: an FDP certificate's PDF text shows the faculty member's designation and institution. [T `tests/test_certificate_wording.py::test_upg131_an_fdp_certificate_shows_designation_and_institution`]

#### UPG-132 — The certificate page and download on a phone (UPG-28's certificate part)
- **Status:** DONE · **Built with:** UPG-125
- **Last verified:** 2026-10-19, commit "UPG-132: …" on `production-ready` (parent `d72ae12`) [T]
- **Built (2026-10-19):** the participant's certificate page (`templates/participant/certificate.html`) was a fixed 1000×700 box: on a 375px phone it hung off both sides and long names spilled out (found by this test). It now scales down to the screen: its width is capped at the page, sizes use `clamp()`, long names and titles wrap, the signature lines wrap, and on a phone the print button sits in the page instead of floating over the share buttons. Printing keeps the full 1000×700 certificate. "My certificates" and its download were checked at 375px with UPG-125.
- **Files touched:** `templates/participant/certificate.html`, `tests/test_certificate_phone.py`
- **Acceptance criteria:** 1. ✅ Test: at 375px the certificate page has no sideways scroll and its download works (headless). [T `tests/test_certificate_phone.py::test_certificates_fit_a_phone_and_download_from_it`: the participant's certificate page (with a long name) measured at 375 and 1280 with no sideways scroll or cut-off text, beside "My certificates" with a real download; fails on the old page]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO (built with UPG-125).

#### UPG-133 — Escaping in the certificate email (UPG-50's deferred part)
- **Status:** DONE · **Built with:** UPG-125
- **Last verified:** 2026-10-19, commit "UPG-133: …" on `production-ready` (parent `77e843b`) [T]
- **Built (2026-10-19):** the new certificate email (`utils_email.send_certificate_issued_email`, UPG-125) escapes every value it prints with `_e()`: the name, the event, the type, the number and both links. The old path's email (`utils_email._send_cert_email`, sent by end-event until UPG-138) printed the name, event title and certificate ID raw; it now escapes them too.
- **Files touched:** `utils_email.py` (`_send_cert_email`), `tests/test_certificate_delivery.py`
- **Acceptance criteria:** 1. ✅ Test: a recipient named `<b>Ann</b>` gets a certificate email showing the text, not markup. [T `tests/test_certificate_delivery.py::test_upg133_the_certificate_email_shows_markup_as_text`: a recipient named `<b>Ann</b>` at an event called `<i>Ital</i> & Co`, issued and emailed through the real path, and the old path's email; fails on the old code]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO (built with UPG-125).

#### UPG-134 — The support address on the verification pages (UPG-65's deferred part)
- **Status:** DONE · **Built with:** UPG-126
- **Last verified:** 2026-10-19, commit "UPG-134: …" on `production-ready` (parent `6e472df`) [T]
- **Built (2026-10-19):** the legacy certificate and registration verification pages (`templates/public/verify_certificate.html:535-543`, `verify_success.html:491-499`) show "contact <SUPPORT_EMAIL>" only when `SUPPORT_EMAIL` is set, as the new page does (UPG-126); the hard-coded `support@snpsu.edu.in` is gone from every verification page.
- **Files touched:** `templates/public/verify_certificate.html`, `templates/public/verify_success.html`, `tests/test_certificate_verification.py`
- **Acceptance criteria:** 1. ✅ Test: the verification pages show `SUPPORT_EMAIL`, or no address when it's unset; nothing hard-coded. [T `tests/test_certificate_verification.py::test_upg134_verification_pages_show_support_email_or_none`: the new page, an old hash, a registration check and a not-found page, with and without the setting; no verification template holds an address]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO (built with UPG-126).

#### UPG-135 — Certificate verification keeps the lead's name and email (UPG-69's deferred part)
- **Status:** DONE · **Built with:** UPG-126
- **Last verified:** 2026-10-19, commit "UPG-135: …" on `production-ready` (parent `177db09`) [T]
- **Built (2026-10-19):** the legacy registration check (`/verify/<reg_id>`) and its preview read the lead's name, which the SQL layer now gives every registration from its columns (UPG-69's adapter fix), so a seeded row shows it too; the test seeds one. `services_certificate.CertificateService.generate_verification_hash` (API v1) is documented as what it is: the first 24 hex characters of a SHA-256 of the ID, event, email and secret, not an HMAC (`services_certificate.py:46-49`); new certificates carry a random number instead (`services_certificates.new_number`). The legacy check stays, labelled an attendance check (UPG-63), until UPG-138 moves registrations to the new certificates.
- **Files touched:** `services_certificate.py`, `tests/test_certificate_verification.py`
- **Acceptance criteria:** 1. ✅ Test: `/verify/<present reg_id>` (the legacy form) and its preview show the lead's name, on seeded rows too, and the certificate number's documentation describes how it's made. [T `tests/test_certificate_verification.py::test_upg135_the_legacy_check_shows_the_leads_name_on_a_seeded_row`, `::test_upg135_the_old_hash_is_documented_as_it_is_made`]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO (built with UPG-126).

#### UPG-136 — No invented venue in the certificate preview (UPG-111's deferred part)
- **Status:** DONE · **Built with:** UPG-123
- **Last verified:** 2026-10-19, commit "UPG-136: …" on `production-ready` (parent `389c8ad`) [T]
- **Built (2026-10-19):** the old certificate preview (`/verify/<id>/preview`, `routes_verification.py:87-91`) takes the venue from the certificate's event and prints `venue_label(event)` (`templates/public/certificate_preview_embed.html:132,136`): the venue or room, "Online", or "Venue to be announced". The new certificate (UPG-123) prints no venue. `tests/test_venue_label.py` no longer exempts these two files from its scan for invented places.
- **Files touched:** `routes_verification.py`, `templates/public/certificate_preview_embed.html`, `tests/test_venue_label.py`, `tests/test_certificate_wording.py`
- **Acceptance criteria:** 1. ✅ Test: no certificate page or PDF says "Main Campus" for an event without a venue. [T `tests/test_certificate_wording.py::test_upg136_no_certificate_page_or_pdf_invents_a_venue`, `tests/test_venue_label.py::test_no_app_code_or_page_falls_back_to_an_invented_place` (no exemptions)]

#### UPG-137 — One certificate store (UPG-112's "two certificate stores")
- **Status:** DONE · **Built with:** UPG-122
- **Last verified:** 2026-10-19, commit "UPG-137: …" on `production-ready` (parent `27d081f`) [T]
- **Built (2026-10-19):** API v1's `POST /api/v1/events/<id>/issue-certificates` (`routes_api_v1.py:1058`) starts the web's issuing run (UPG-124) into the `certificates` table, answering 202 with the run's progress and the certificates' numbers and verification links; it checks `issue_certificates` on the event (as the web does) and accepts SPOC tokens, whose role "ClubSPOC" its role list had left out; an optional `category` limits it to one type. `GET /api/v1/certificates/<id>` (`:1090`) answers from the same table for a certificate number (valid, revoked or replaced; no personal data) and falls back to the older API store (`services_certificate.CertificateService`, `certificates/<id>` documents) for older IDs, whose tests stay as they are. Removing that older store needs the owner's word (as D-9).
- **Files touched:** `routes_api_v1.py`, `tests/test_certificate_api.py` (new)
- **Acceptance criteria:** 1. ✅ Test: API v1's issue and verify endpoints use the same `certificates` records as the web, and `/verify` finds an API-issued certificate. [T `tests/test_certificate_api.py::test_the_api_issues_into_the_same_store_and_the_web_verifies_it`, `::test_a_web_issued_certificate_verifies_through_the_api`; `tests/test_evaluation_and_certs.py` (older store) unchanged and passing; SQLite and PostgreSQL]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO; API v1 still uses `services_certificate.CertificateService` (`routes_api_v1.py`, unchanged).


#### UPG-138 — One issuing path again: the old callers move to the new certificates
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-138: …" on `production-ready` (parent `161d0a8`) [T]
- **Problem:** Found starting UPG-124. Ending an event (`routes_spoc.py:793` → `tasks/cert_tasks.py:25`) and the SPOC's bulk button (`routes_spoc.py:2143`) still issue through UPG-06's `utils_certificate.issue_event_certificates`: `verified_certificates` documents, `certificate_id` on the registration, a PDF attached to an email. The participant's certificate page (`routes_participant.py:277`, `templates/participant/certificate.html:169-172`), the ledger (`templates/participant/ledger.html:79`) and `/verify/<id>/download` read those. Moving them before the new delivery (UPG-125) and verification (UPG-126) exist would break those links, so UPG-124 builds the new issuing beside the old and this item switches over.
- **What to build:** end-event and the bulk button start a run of the new issuing (UPG-124); the participant's certificate page and the ledger link the person's new certificates (UPG-125's download, UPG-126's page); `utils_certificate.issue_event_certificates` and its writes to `verified_certificates` are retired (old certificates keep verifying, UPG-126). UPG-06's tests move to the new path without losing a check.
- **Built (2026-10-19):**
  - **End-event and the bulk button** (`routes_spoc.py` `end_event`, `bulk_certs`) start a run of the one issuing path (`services_certificate_runs.start`, UPG-124); the queued task `tasks.cert_tasks.bulk_generate_certificates` keeps its name for anything already in the outbox and starts a run too. If the event can't issue yet (no signature, not ended), the SPOC is told why; ending the event still ends it.
  - **`utils_certificate.issue_event_certificates` is retired** (96 lines), so nothing writes `verified_certificates` any more; its records keep their legacy pages (UPG-126).
  - **Registrations keep their link:** issuing writes the certificate's number, verification link, type and time onto the lead's registration (`services_certificates._link_registration`), a place taking precedence over attendance, so the dashboards, insights and exports that read `certificate_id` carry on.
  - **The participant's certificate page** links the viewer's own new certificate (download and public page) and keeps the old links for a certificate issued before the switch (`routes_participant.py` certificate route, `templates/participant/certificate.html`); the ledger links it (UPG-125).
  - **UPG-06's tests** (`tests/test_certificates.py`) moved to the new path check by check: the ID and link on the registration, the record (now a `certificates` row), one PDF per attendee (now through the email's signed link), the public page, the attendee's download (the PDF is no longer public), no second issue from the bulk button or end-event, another SPOC refused. The winner check now follows the published results, as the brief requires. Nothing was dropped; four checks were added.
- **Files touched:** `routes_spoc.py`, `tasks/cert_tasks.py`, `utils_certificate.py`, `services_certificates.py`, `routes_participant.py`, `templates/participant/certificate.html`, `tests/test_certificates.py`, `tests/test_certificate_switch.py` (new)
- **Effort:** M · **Depends on:** UPG-124, UPG-125, UPG-126 · **Risk:** medium (the live path moves).
- **Acceptance criteria:**
  1. ✅ Test: ending an event issues each Present attendee's certificate once in the `certificates` table, and nothing is written to `verified_certificates`; running it again issues nothing. [T `tests/test_certificate_switch.py::test_ending_the_event_issues_once_into_the_certificates_table_only`]
  2. ✅ Test: the participant's certificate page and the ledger link the person's certificate, its download works, and a certificate issued before the switch still opens. [T `tests/test_certificate_switch.py::test_the_page_and_ledger_link_the_certificate_and_an_older_one_still_opens`]
  3. ✅ Test: every check in UPG-06's tests still holds on the new path (none deleted or weakened). [T `tests/test_certificates.py` (3 tests, 27 checks where there were 23; each old check kept on the new path, see above); SQLite and PostgreSQL]

#### UPG-139 — The coordinator's "publish results" doesn't mark the results published
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-139: …" on `production-ready` (parent `2572093`) [T]
- **Problem:** Found starting UPG-124. `POST /coordinator/publish_results/<id>` (`routes_coordinator.py:422-484`) ranks the event, writes each place, emails the top three and marks the event completed, but never sets `results_published`. The SPOC's route does (`routes_spoc.py:1041-1044`). So after a coordinator publishes, the SPOC's results page still says the results aren't published (`templates/spoc/results.html:10`), and nothing that waits for published results (position certificates, `services_certificates._ranks`) sees them.
- **What to build:** the coordinator's route sets `results_published` as the SPOC's does.
- **Built (2026-10-19):**
  - `routes_coordinator.publish_results` sets `results_published` with the winners and the completed status (`routes_coordinator.py:457`), as the SPOC's route does.
- **Files touched:** `routes_coordinator.py`, `tests/test_analytics_and_leaderboards.py`
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: after the coordinator publishes, the event has `results_published` set, and its podium owes position certificates. [T `tests/test_analytics_and_leaderboards.py::test_upg139_the_coordinators_publish_marks_the_results_published`: the SPOC's results page stops offering "Publish results", and the three joint winners are owed winner certificates; fails without the fix]


#### UPG-140 — Audit rows written outside a request are lost
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-140: …" on `production-ready` (parent `2368312`) [T]
- **Problem:** Found building UPG-127. `utils.log_action` (`utils.py:90-138`) reads `session` for the user and role whatever the context. Outside a request (a background task, a scheduled job, a thread such as the certificate runs of UPG-124) that raises "Working outside of request context", which the function catches and logs as a warning, so the audit row is never written. Every `log_action` call from `tasks/` and from services run in the background is affected.
- **What to build:** outside a request, write the row with the user and role "system" (or the actor passed in the details) instead of dropping it.
- **Built (2026-10-19):**
  - `utils.log_action` reads the session only inside a request; outside one (a background task, a scheduled job, a worker thread) the row is written with user and role "system" instead of being dropped (`utils.py:120-136`).
- **Files touched:** `utils.py`, `tests/test_audit_outside_request.py` (new)
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. ✅ Test: `log_action` called with no request (as a background task does) writes its row, with user and role "system"; inside a request it still records the signed-in user. [T `tests/test_audit_outside_request.py::test_an_audit_row_with_no_request_is_written_as_system` (a worker thread; fails on the old code), `::test_inside_a_request_the_row_names_the_signed_in_user`]

#### UPG-141 — The participant's certificate page prints "at ." for an event without a venue
- **Status:** DONE
- **Last verified:** 2026-10-19, commit "UPG-141: …" on `production-ready` (parent `020cb88`) [T]
- **Problem:** Found building UPG-132. `templates/participant/certificate.html` says "held on <date> at {{ event.venue }}." With no venue the sentence ends "at ." UPG-111 gave every page `venue_label` ("Venue to be announced" or "Online"); this page wasn't on its list because it prints the raw field with no fallback.
- **What to build:** use `venue_label(event)` there.
- **Built (2026-10-19):**
  - `templates/participant/certificate.html:181` prints `venue_label(event)`: the venue or room, "Online", or "Venue to be announced".
- **Files touched:** `templates/participant/certificate.html`, `tests/test_certificate_wording.py`
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ Test: the participant's certificate page for an event with no venue says "Venue to be announced" (or "Online"), never "at .". [T `tests/test_certificate_wording.py::test_upg141_the_participant_certificate_page_never_says_at_nothing`: fails on the old page]


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

### Master "To test later" list (ordered by risk)

All items built in the development-only run (`BUILT (untested)`), prioritized by risk for full verification before release:

#### Tier 1: Payments, Refunds & Idempotency (Highest Risk)
1. **UPG-51 (Refund all on cancellation):**
   - Concurrent "refund all" calls Razorpay once per payment.
   - Per-payment failure recorded and retryable without re-refunding succeeded ones.
   - Audit log entry created and confirmation email sent to participant for every refund.
   - Registrations without an online payment order listed for manual processing.
2. **UPG-26 (Form & payment idempotency):**
   - Single submit guard disabled after one click (checkout especially).
   - Double-submit of registration form with same `submission_id` creates exactly one registration.
   - Field-level validation error messages displayed beside fields with user input values preserved.
3. **UPG-56 (Checkout coupons & price preview):**
   - Coupon field on checkout submits to `/payment/price_preview` returning server fee, discount, and total.
   - Final Razorpay order creation uses server-verified discounted price.
   - Invalid/expired coupons rejected with clear error message.
4. **UPG-44 (Empty payment status handling):**
   - Empty/missing payment status reads back as empty string on PostgreSQL and SQLite (not enum default `'unpaid'`).
   - Query filters for `'unpaid'` match only explicit unpaid registrations.

#### Tier 2: Permissions, Concurrency & Security
5. **UPG-52 (Atomic team join):**
   - Two concurrent join requests on PostgreSQL when 1 spot remains: exactly one succeeds and one is rejected.
   - Team max limit is strictly preserved under concurrency.
6. **UPG-22 (Privacy notice consent & account deletion):**
   - Consent checkbox required at registration/signup; records timestamp and notice version.
   - Profile data export returns only user's own data (no leaked team member personal info).
   - Account deletion anonymizes personal data while keeping necessary registration count aggregates; executed by cron cleanup.
7. **UPG-10 (Roster CSV import & Google auth domain restriction):**
   - SuperAdmin roster CSV import handles valid/invalid columns, duplicate emails, and creates unverified student accounts.
   - Google OAuth sign-in rejects emails outside configured university domain.
8. **UPG-20 (Boot checks, health & security headers):**
   - Production boot checks aggregate all missing configurations into single startup error.
   - `/health` endpoint returns minimal 200 OK or 503 Service Unavailable without exposing stack traces.
   - HSTS and CSP security headers applied on all responses.

#### Tier 3: Check-in, Workflow & Access Control
9. **UPG-43 (Workflow states in event-day jobs):**
   - Coordinator scanner and walk-in lists include `registration_open`, `registration_closed`, `in_progress`, and `published` events.
   - Scheduled reminders process events in new workflow states; cancelled events excluded.
10. **UPG-12 (Faculty & external participants):**
    - Event allowed-participant types enforced (e.g. FDP faculty-only, conference faculty+external).
    - Designation and institution required only for faculty and external participants.
    - New faculty/external accounts receive set-password token without raw passwords.
    - Participant dashboard, tickets, check-in, and feedback function identically to students.
    - Department activity export and admin analytics split counts by participant type.
11. **UPG-57 (Placement drives):**
    - Eligibility rules (CGPA, backlogs, branch, year) verified against roster on registration.
    - Ineligible registration attempts rejected with specific reason.
    - Organizer view compares eligible vs registered students.
    - Candidate round transitions (shortlisted/rejected) dispatch notification once.
    - Per-round CSV and XLSX exports function correctly.
12. **UPG-09 (Room booking conflict detection):**
    - Room booking picker during event creation creates tentative booking.
    - Overlapping room bookings detected and rejected.
    - Approval/publish workflow transition confirms tentative booking.
13. **UPG-04 (Judging rubric criteria):**
    - Per-criterion max scores enforced; score inputs reject out-of-range scores.
    - Locked scoring prevents further edits.
    - Judge dashboard displays events in `in_progress` and `evaluation` states.
14. **UPG-13 (Sports tournaments):**
    - Knockout bracket generation handles uneven teams with byes and advances winners to final champion.
    - League round-robin computes accurate points table (win/draw/loss points configurable).
    - Result entry restricted to SPOC and assigned coordinators (unauthorized returns 403).
    - Public fixtures page (`/tournament/fixtures/<event_id>` and `/sports/fixtures/<event_id>`) renders without login.

#### Tier 4: Background Jobs, Data Layer & Notifications
15. **UPG-16 (Alembic baseline migration):**
    - `alembic upgrade head` builds empty PostgreSQL schema matching models with zero diffs.
    - Downgrade to base and upgrade back to head succeeds.
    - Production boot verifies schema is at head.
16. **UPG-18 (Inline task timeout & outbox):**
    - Background tasks run inline with timeout when no Celery broker configured.
    - Failed tasks stored in `outbox` table; retried by `/internal/cron/outbox`.
17. **UPG-21 (Database backup and restore):**
    - Daily `pg_dump` script runs and uploads to private S3.
    - Restore script verifies dump and refuses to overwrite non-empty target without explicit flag.
18. **UPG-19 (Server-side pagination & search):**
    - 25 per page pagination across admin, SPOC, coordinator event lists, users, payments, audit log.
    - Search filters and page parameters preserved in URL query strings.
19. **UPG-47 (Event times & room clashes):**
    - Events saved without times keep start/end empty and display "Time to be announced".
    - Zero-length bookings hold date and detect conflicts on same day.
20. **UPG-48 (Team member notifications):**
    - Team members (not only lead) receive confirmations, 24h reminders, 3-day reminders, and change/cancellation notices once each.
    - Registration tracks `*_sent_to` to prevent duplicate dispatch.
21. **UPG-49 (WhatsApp automation):**
    - Automation WhatsApp channel dispatches via Twilio when configured; cleanly skipped when unconfigured.
22. **UPG-50 (Email HTML escaping):**
    - HTML values escaped in outbound email templates; subjects stay plain text.
23. **UPG-46 (Base URL in emails):**
    - Scheduled email links dynamically generated from `BASE_URL`.
24. **UPG-42 (Support contact email):**
    - `SUPPORT_EMAIL` rendered on privacy, terms, payment-failed pages; omitted when unset.
25. **UPG-61 (Dev database startup schema sync):**
    - Local SQLite startup synchronizes new NOT NULL columns with defaults on existing databases.

#### Tier 5: Frontend, Mobile & Hygiene
26. **UPG-23a–h (Consolidated template layout):**
    - Every rendered template extends `layouts/document.html`; consistent header/footer across roles.
27. **UPG-24 (Bootstrap 5.3.3, self-hosted fonts & SRI):**
    - Bootstrap and Font Awesome loaded once with SRI; self-hosted Inter/Plus Jakarta Sans/Outfit fonts; external CDNs pinned.
28. **UPG-25 (Nonce-based CSP & externalized scripts):**
    - Inline scripts and handlers externalized; CSP script-src excludes `'unsafe-inline'`.
29. **UPG-27 (Image optimization & accessibility):**
    - Static images compressed to WebP under 1.5 MB total; `alt` and `loading="lazy"` on images below fold; `:focus-visible` outlines.
30. **UPG-28 (Mobile responsiveness):**
    - Student journey (discover → register → pay → ticket → scanner → feedback) verified on 375px viewport with no horizontal overflow.
31. **UPG-53 (Empty home page state):**
    - Home page renders clean empty state when no events exist (no fake hackathon).
32. **UPG-54 (Capacitor dynamic configuration):**
    - Android webview config derived from `BASE_URL` at build time.
33. **UPG-55 (Conditional Google login & 2FA):**
    - Google login and 2FA settings displayed only when configured.
34. **UPG-59 (Fixed 500 routes):**
    - All 5 fixed routes render without 500 errors.
35. **UPG-60 (Frontend browser pass fixes):**
    - Favicon, reels posters, create-event wizard script parse errors resolved.
36. **UPG-14 (Subsystem deduplication):**
    - Notifications v2 feed functional; Stripe routes 404; matchmaker guarded.
37. **UPG-15 (Cleaned code & templates):**
    - Catalyst code, unregistered blueprints, and unrendered templates removed.
38. **UPG-38 (Jekyll workflow removed):**
    - Jekyll workflow file deleted.


### Decisions needed

| ID | Decision | Blocks | Status |
|---|---|---|---|
| D-1 | **Is Cloud Run the only deploy target?** If yes, `functions/saptha_app/` (the Zoho Catalyst copy) and `catalyst.json` are removed in Phase 5. That copy still has the kiosk/ticket holes (BLK-12), the public SuperAdmin sign-up (BLK-14), the bandit findings (BLK-11) and the walk-in default password (UPG-15). If Catalyst stays, it needs a build step instead of a tracked copy. | BLK-12 criterion 4; BLK-14 criterion 3; UPG-15 criteria 3–4 | **Decided (owner, 2026-10-01): yes, Cloud Run is the only deploy target.** UPG-15 removes `functions/saptha_app/` and `catalyst.json` in Phase 5, which completes BLK-12 criterion 4 and BLK-14 criterion 3; no Catalyst build step is needed. Until then, BLK-11 fixes the two flagged files in place so CI can go green. |
| D-2 | **BLK-01 owner actions:** force-push the rewritten `master`, delete the remote `main` and `claude/busy-davinci-6nkabi`, and ask GitHub Support to purge the 47 PR refs (commands in the 2026-09-29 changelog). The agent never pushes. | BLK-01 criteria 0 and 4 (CI green on GitHub); BLK-11 criterion 2 | **Done (owner, 2026-10-01):** `master` force-pushed, `main` and `claude/busy-davinci-6nkabi` deleted, `production-ready` pushed, GitHub Support contacted. Verified with `git ls-remote`; BLK-01 criterion 4 is met on GitHub. **Left:** Support removing the 47 PR refs (BLK-01 criterion 0). Nothing else waits on it. |
| D-3 | **UPG-35: should login, password-reset and sign-up messages hide whether an account exists?** | UPG-35 | **Decided (owner, 2026-10-02):** login and password-reset messages become uniform ("Email or password is incorrect"; "If an account exists for this email, we've sent a reset link"). Sign-up and registration stay as they are: an existing email is told to log in first. Scheduled in Phase 2 right after UPG-33. |
| D-5 | **UPG-17: fold into UPG-21?** Nothing the app runs stores files any more (end-of-Phase 2 re-verification), so UPG-17's criteria 3–4 have nothing to test. Proposed: move its storage settings (S3 endpoint, private objects, no silent local fallback) into UPG-21's backup work and close UPG-17. | UPG-17, UPG-21 | **Decided (owner, 2026-10-10): yes.** UPG-17 is folded into UPG-21: its storage settings (S3 endpoint, private objects, no silent local fallback) are built with the backups; UPG-17 is closed as MERGED. |
| D-4 | **UPG-42: which address should the privacy, terms and payment-failed pages give for help and privacy requests?** | UPG-42 | **Decided (owner, 2026-10-10):** the address comes from `SUPPORT_EMAIL`. The owner sets the real address in the deployment's `.env`/secret settings; `events@your-university-domain` is only the placeholder in `.env.example`, never a default in code. |
| D-6 | **UPG-30 criterion 4: when is the Razorpay test-mode checkout run?** | UPG-30 criterion 4 | **Decided (owner, 2026-10-10):** deferred to UPG-32 (release check), run on a public test deployment together with the webhook (Razorpay must reach `<BASE_URL>/payment/webhook/razorpay`). UPG-30 stays IN PROGRESS until then. |
| D-7 | **UPG-22: what is kept after an account is deleted?** Built: the account and the person's name, email, phone, USN and answers go; registration rows stay without them (attendance and payment totals for reports). Still holding the email: payment orders (finance records) and the audit log. Also: should API v1 registrations (the apps) require consent once the apps are updated? | UPG-22 (policy, not code) | Open (2026-10-10). Proposed: keep payment orders and the audit log for the finance and audit retention period (e.g. 8 years), then anonymise; require consent in API v1 after the next app release. |
| D-8 | **Keep `/live/reels` and `/live/streams` public?** Both are demo pages: made-up like and viewer counts, a "Live" badge, and (until UPG-60) cartoon sample videos. UPG-60 replaced the videos with event images; the counts are still invented. | none (content, not code) | Open (2026-10-10). Proposed: hide both until there's real event media, as UPG-53 did for the home page's fake hackathon. |
| D-9 | **Retire the Stripe and matchmaker tests?** UPG-14 removed Stripe and hid the matchmaker, so 5 existing tests (`test_global_scale.py` Stripe ×2, `test_next_gen.py` matchmaker ×3) now fail. The rules say never delete or weaken a test. | UPG-62 | **Decided (owner, 2026-10-17, production-ready run brief):** yes, delete the 5 tests. Done in UPG-62. |

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

---

### Done since 2026-10-20


#### UPG-142 — Merit and special-mention certificates can't be awarded
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-142: …" (parent `c9571df`) [T]
- **Problem:** Found while making the sample emails. `services_certificates.TYPES` has "merit" and "special_mention" (the brief's "merit or special mention"), and the PDF has their wording and colours, but nothing awards them: `recipients()` never lists them and "issue to one person" (UPG-124) only issues certificates someone is already owed. UPG-122's criterion 3 didn't ask for them, so its tests didn't notice.
- **What to build:** on the event's certificate page, the organiser picks a registered person and awards "merit" or "special mention" (with an optional line of wording); it is then issued like any other (once, emailed, audit-logged), with `issue_certificates` on the event.
- **Effort:** S · **Depends on:** UPG-124 · **Risk:** low.
- **Built (2026-10-20):** The certificate page has an Award form: pick a registered person (each team member too, `services_certificates.registered_people`), merit or special mention, and an optional line of wording. `services_certificates.award` checks the event can issue, issues it once through `issue_one` (stored, emailed, audit-logged as CERT_ISSUED) and logs CERT_AWARDED; `POST /certificates/events/<id>/award` needs `issue_certificates`.
- **Files touched:** `services_certificates.py`, `routes_certificates.py`, `templates/certificates/manage.html`, `tests/test_certificate_awards.py` (new)
- **Acceptance criteria:**
  1. ✅ Test: the organiser awards a merit and a special-mention certificate to two registered people; each is issued once, emailed and audit-logged; someone without `issue_certificates` gets 403. [T `tests/test_certificate_awards.py::test_the_organiser_awards_merit_and_special_mention`]

#### UPG-117 — The JSON waitlist join only takes events in the old "active" status
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-117: …" (parent `810abc8`) [T]
- **Problem:** Found in UPG-114. `POST /waitlist/join/<event_id>` (`routes_waitlist.join_waitlist`) answers "Event is not active" (400) unless the event's status is `active`. Since UPG-73, an event that is taking registrations is `registration_open` (or `published`), so the endpoint refuses every new event. No page calls it today: the registration form puts people on the waitlist itself when an event is full.
- **What to build:** accept the statuses in which registration is open (as the form does), and refuse the rest with the same message the form gives; or remove the endpoint if nothing will call it.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Built (2026-10-20):** `POST /waitlist/join/<id>` (`routes_waitlist.py:44`) uses the registration form's own rule (`routes_forms.registration_closed`: closed statuses and the deadline) instead of accepting only the old "active" status, and refuses with the form's message.
- **Files touched:** `routes_waitlist.py`, `tests/test_waitlist_places.py`
- **Acceptance criteria:**
  1. ✅ Test: joining a full `registration_open` event through the endpoint adds the person to the waitlist; a cancelled or completed event is refused. [T `tests/test_waitlist_places.py::test_upg117_the_json_join_follows_the_forms_rule` (registration_open and active join; published, registration_closed, completed and cancelled refused)]
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO; `routes_waitlist.py:44` still refuses any status but `active`.
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still TODO; `routes_waitlist.py:44` still refuses any status but `active`.

#### UPG-143 — Tests that make an event "today" fail when a run crosses midnight
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-143: …" (parent `8204fce`) [T]
- **Problem:** Found in the final PostgreSQL run of the certificate phase. `tests/test_teams.py::test_joining_by_code_adds_the_member_and_they_can_open_the_ticket` builds its event for `datetime.date.today()`; the run created it at 23:53 and joined at 00:09, when the event was in the past and closed, so the join was refused. Re-run the next day it passes on both databases (6 of 6). Other fixtures that use "today" (`tests/test_certificates.py`, `tests/test_phone_journey.py`) can fail the same way.
- **What to build:** those fixtures use a date a day or more ahead where "today" isn't the point, or fix the clock for the test.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Built (2026-10-20):** The team test keeps its event on today (the ticket QR shows on the event day) but its registration now runs until a week ahead, so a join after midnight is still open; UPG-06's certificate fixture makes its event a week ahead (nothing there needs today). A new test sets the clock to 23:59 for the lead's registration and 00:01 the next day for the join. `tests/test_phone_journey.py` still needs today (the scanner opens only on the event day); left as is.
- **Files touched:** `tests/test_teams.py`, `tests/test_certificates.py`
- **Acceptance criteria:**
  1. ✅ Test: the team-join test passes with the clock set to 23:59 at the start and 00:01 by the join. [T `tests/test_teams.py::test_upg143_joining_still_works_when_the_clock_passes_midnight`]

#### UPG-144 — NAAC / AQAR report from event data
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-144: …" (parent `7fc18b1`) [T]
- **Problem:** The IQAC coordinator collects a year's NAAC evidence from departments by hand. SapthaEvent holds most of it (events, attendance, hours, certificates, results) but has no NAAC view, no post-event report and no export.
- **What to build:**
  - **Roles:** IQAC coordinator (university-wide, read-only on events, runs reports, sends reminders) and department admin (sees its own department's events and reports), both assigned by the Super Admin; migration 0009 adds them to the role type.
  - **NAAC category** per event, picked by the organiser from a list the Super Admin edits (a sensible default list, not hard-coded).
  - **Post-event report**, due N days after the event (`NAAC_REPORT_DAYS`, default 7): objectives, summary, outcomes; resource person or chief guest (name, designation, organisation); collaborating organisation; photos (geotag kept when present; each can be marked shareable), brochure or notice, evidence files (PDF, JPG or PNG, size limits, private storage). Attendance from check-ins (students, faculty, external) and ledger hours, automatic. Daily reminders to the organiser until submitted; the IQAC coordinator sees missing reports and can send a reminder.
  - **Report builder** for an academic year (`NAAC_YEAR_START_MONTH`, default June): filters (year, department or club, NAAC category, event type); summary per category (events, participants by type, hours); detail per category (title, dates, department, resource person, participants, evidence link); awards and positions won; faculty participation in FDPs and workshops.
  - **Exports:** XLSX (a sheet per category), PDF with the college letterhead, ZIP of evidence by category and event. Column layout in a template file (`config/naac_layout.json`), not hard-coded; decision D-10 asks the owner to confirm the AQAR layout with the IQAC coordinator.
  - **Permissions:** organisers edit only their own events' reports; the IQAC coordinator and Super Admin see all; department admins see their department.
- **Effort:** L · **Depends on:** UPG-12, UPG-11, UPG-122 · **Risk:** medium (new roles).
- **Built (2026-10-20):** `services_naac.py` and `routes_naac.py` (new, `/naac`): roles IQACCoordinator and DepartmentAdmin (enum + migration 0009, assignable by the Super Admin, login option, land on `/naac/`); NAAC categories editable by the Super Admin (default list) and picked per event; the post-event report (objectives, summary, outcomes, resource person, collaborator) with photos (EXIF geotag kept, shareable flag), brochure and evidence (PDF/JPG/PNG, 5/10 MB, private storage); attendance by type and hours from check-ins; due `NAAC_REPORT_DAYS` after the event, a daily `naac` cron reminder and an IQAC reminder button; the yearly builder (`NAAC_YEAR_START_MONTH`) with filters, summary, detail, awards and faculty; XLSX, letterhead PDF and evidence ZIP following `config/naac_layout.json` (D-10).
- **Files touched:** `services_naac.py`, `routes_naac.py`, `templates/naac/*` (new), `config/naac_layout.json` (new), `migrations/versions/0009_naac_roles.py` (new), `models_pg.py`, `utils.py`, `routes_admin.py`, `routes_cron.py`, `app.py`, `templates/login.html`, `templates/includes/ui.html`, `templates/spoc/review_event.html`, `templates/admin/dashboard.html`, `.env.example`, `docs/DEPLOY.md`, `tests/test_naac.py` (new)
- **Acceptance criteria:**
  1. ✅ Test: the Super Admin assigns the IQAC coordinator and department admin roles; each logs in and lands on the NAAC page; migration 0009 matches the models on SQLite and PostgreSQL. [T `tests/test_naac.py`::test_the_super_admin_assigns_the_two_roles_and_they_land_on_naac; `tests/test_migrations_baseline.py` on SQLite and PostgreSQL]
  2. ✅ Test: the Super Admin adds, renames and removes NAAC categories; the organiser picks one for an event. [T `tests/test_naac.py`::test_categories_are_edited_by_the_super_admin_and_picked_by_the_organiser]
  3. ✅ Test: the organiser fills and submits a report with a resource person, a collaborator and uploads (a geotagged JPEG keeps its coordinates; a GIF and an oversized file are refused); attendance counts students, faculty and external participants who were Present and their hours. [T `tests/test_naac.py`::test_the_organiser_fills_and_submits_a_report_with_evidence]
  4. ✅ Test: an event past its due date without a report gets one reminder a day until submitted; the IQAC coordinator sees it as missing and sends a reminder. [T `tests/test_naac.py`::test_overdue_reports_get_one_reminder_a_day_and_the_iqac_coordinator_can_remind]
  5. ✅ Test: the builder for an academic year, with each filter, gives the right summary per category, detail rows, awards and positions, and faculty participation. [T `tests/test_naac.py`::test_the_builder_summarises_details_awards_and_faculty_with_each_filter]
  6. ✅ Test: the XLSX has a sheet per category with the columns from the layout file; the PDF's text has the letterhead and the totals; the ZIP holds each event's evidence under its category. [T `tests/test_naac.py`::test_the_exports_follow_the_layout_file]
  7. ✅ Test, for each role (organiser, another SPOC, IQAC coordinator, department admin of the event's department and of another, Super Admin, student, coordinator): who may edit, view, run the builder, export and remind. [T `tests/test_naac.py`::test_each_role_may_do_only_its_part (8 roles)]
- **2026-10-20 (follow-up):** the reminder button redirected back by comparing the referrer with `request.host_url`, which `tests/test_public_links.py::test_no_app_module_builds_links_from_the_request_host` forbids (BLK-16); it now returns to a `next` path checked by `is_safe_next`.

#### UPG-145 — Track record: impact dashboard, time saved, testimonials, impact report and page
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-145: …" (parent `5c6dd25`) [T]
- **Problem:** Nothing shows what the college has run on SapthaEvent, so there's no proof to show other colleges. Every figure must be real data, never invented, rounded up or padded; a figure that isn't available is left out.
- **What to build:**
  - **Impact dashboard** (Super Admin), per month and per year: events held, registrations, check-ins, attendance rate (with its counts), certificates issued, departments and clubs using it, external participants, NAAC reports submitted, and forms saved (registrations made online, not walk-ins at the desk; walk-ins are marked from now on and recognised by their signature before that).
  - **Time saved:** one optional question to the organiser after each event ("About how many hours did SapthaEvent save you?"); the total and the average per answering event, labelled as organisers' estimates.
  - **Testimonials:** after an event, the organiser and a sample of participants (`TESTIMONIAL_SAMPLE`, default 10) get one emailed, signed link asking for a 1–5 rating and a comment with "You may quote this, with my name and role." Only those with that permission can be approved by the Super Admin for public use.
  - **Impact report:** a 2-page PDF for a chosen period: the college, what was run, the key numbers, approved testimonials, and photos marked shareable in post-event reports.
  - **Public Impact page**, off by default; the Super Admin switches it on.
- **Effort:** M · **Depends on:** UPG-144 · **Risk:** low.
- **Built (2026-10-20):** `services_impact.py` and `routes_impact.py` (new): the Super Admin's `/impact/dashboard` counts records per month and year (events held, registrations, check-ins, attendance with its counts, valid certificates, departments and clubs, external participants, submitted NAAC reports, forms saved = registrations not made at the desk; walk-ins are marked `source: walk_in` now and recognised by their signature before); organisers' optional hours-saved answer on the NAAC report page, shown as estimates; the daily `impact` cron job asks the organiser and `TESTIMONIAL_SAMPLE` Present attendees once per event through a signed link; only quotable comments can be approved; a 2-page impact PDF with approved testimonials and shareable photos; a public `/impact` page, off by default, switched and audit-logged by the Super Admin.
- **Files touched:** `services_impact.py`, `routes_impact.py`, `templates/impact/*` (new), `routes_cron.py`, `routes_coordinator.py`, `app.py`, `templates/naac/report.html`, `templates/admin/dashboard.html`, `.env.example`, `docs/DEPLOY.md`, `tests/test_impact.py` (new)
- **Acceptance criteria:**
  1. ✅ Test: for a month and its year, every dashboard figure equals the count in the data (a walk-in isn't a form saved; a revoked certificate and an unsubmitted report don't count); a month with no data shows none; only the Super Admin opens it. [T `tests/test_impact.py`::test_the_dashboard_counts_every_figure_exactly]
  2. ✅ Test: organisers' answers give the total and average over the events that answered; an unanswered event doesn't count; the page labels them as estimates. [T `tests/test_impact.py`::test_hours_saved_are_the_organisers_estimates]
  3. ✅ Test: the testimonial job emails the organiser and at most the sample size of Present participants once per event; the signed link takes a rating and comment; an altered link fails; a comment without permission can't be approved; an approved one can be withdrawn. [T `tests/test_impact.py`::test_testimonials_are_asked_once_and_only_quotable_ones_can_be_approved]
  4. ✅ Test: the impact PDF for a period has at most 2 pages, the college's name, the key numbers, approved testimonials only and a shareable photo (no unshareable one). [T `tests/test_impact.py`::test_the_impact_report_and_the_public_page_show_approved_material_only]
  5. ✅ Test: the public Impact page is a 404 until switched on, then shows the numbers and approved testimonials only; switching it is audit-logged. [T `tests/test_impact.py`::test_the_impact_report_and_the_public_page_show_approved_material_only]

#### UPG-146 — Reach beyond one campus: open events, external students, share cards, listing kit, "Powered by"
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-146: …" (parent `b58ec15`) [T]
- **Problem:** Events are visible only to this campus. There's no public list of events other colleges can join, the event page's schema.org data is hand-escaped (a quote or newline in a title breaks it, and an event without a venue says "None"), it has no Open Graph or Twitter tags, and nothing helps an organiser list an event on outside sites.
- **What to build:**
  - **Audience per event:** campus only (default) or open to other colleges, set by the organiser; open lets external participants register (UPG-12), campus only takes that back.
  - **`/open-events`:** upcoming open events with search and filters (category, type, dates), no login.
  - **External students** register with their college as external participants and get the same ticket, check-in and certificate.
  - **Share cards** on every public event page: Open Graph and Twitter tags (title, date, venue, image), schema.org Event data built and JSON-encoded in code, and the WhatsApp share link.
  - **Cross-posting:** Unstop, KnowAFest and Festooo were checked on 2026-10-20: none publishes an official API for posting listings (Unstop has only unofficial scrapers; no developer documentation was found for KnowAFest or Festooo). So: a "Listing kit" with copy-ready text, the poster and the registration link for each site's own form. Nothing is posted automatically or scraped.
  - **"Powered by SapthaEvent"** on public pages, tickets and emails, which the Super Admin can switch off.
- **Effort:** M · **Depends on:** UPG-12, UPG-111 · **Risk:** low.
- **Built (2026-10-20):** `services_reach.py` and `routes_reach.py` (new): the organiser's campus-only / open switch on the event review page (open adds external participants, campus removes them; audit-logged); public `/open-events` with search, category, type and date filters and pages, linked in the public navigation; external registrations use UPG-12 and get the same ticket, check-in and certificate; the event page's Open Graph and Twitter tags and schema.org Event data are built in `share_meta` and JSON-encoded (`templates/public/event_details.html`), the WhatsApp link stays; the listing kit for Unstop, KnowAFest and Festooo (none has a posting API, checked 2026-10-20); a "Powered by SapthaEvent" line in the site footer and every email, switched by the Super Admin at `/reach/settings`.
- **Files touched:** `services_reach.py`, `routes_reach.py`, `templates/reach/*` (new), `app.py`, `templates/public/event_details.html`, `templates/includes/site_footer.html`, `templates/includes/ui.html`, `templates/spoc/review_event.html`, `templates/admin/dashboard.html`, `utils_email.py`, `tests/test_reach.py` (new)
- **Acceptance criteria:**
  1. ✅ Test: the organiser opens an event to other colleges and back (another SPOC gets 403); open adds external participants, campus only removes them; `/open-events`, without a login, lists upcoming open events only, and its search and filters narrow the list. [T `tests/test_reach.py`::test_organisers_open_events_and_the_public_page_lists_them]
  2. ✅ Test: a student from another college registers for an open event with their college; their ticket opens, the staff check-in marks them Present, and their certificate carries their college; a campus-only event refuses an external registration. [T `tests/test_reach.py`::test_a_student_from_another_college_registers_checks_in_and_gets_a_certificate]
  3. ✅ Test: the event page has Open Graph and Twitter tags with the title, date and venue, schema.org data that parses as JSON (also for a title with quotes and a line break, and "Venue to be announced" without a venue), and the WhatsApp link. [T `tests/test_reach.py`::test_event_pages_carry_share_cards_and_valid_schema_org_data]
  4. ✅ Test: the listing kit shows each site's fields with the registration link; only the event's editors open it. [T `tests/test_reach.py`::test_the_listing_kit_is_for_the_events_editors]
  5. ✅ Test: "Powered by SapthaEvent" is on a public page, the ticket and an email; the Super Admin hides it everywhere (audit-logged); nobody else can switch it. [T `tests/test_reach.py`::test_the_powered_by_line_and_its_switch]

#### UPG-147 — WhatsApp notifications through the official API, with opt-in, once-only sends and a monthly cap
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-147: …" (parent `dc3987b`) [T]
- **Problem:** WhatsApp (Twilio, UPG-49) sends whenever Twilio is configured, to any phone on a registration, with no opt-in, no STOP handling, no limit on cost and no once-only rule; only Twilio is supported, and the messages aren't approved templates.
- **What to build:**
  - **Provider:** Meta's WhatsApp Cloud API or Twilio, by settings; off by default: nothing is sent until a provider is configured, and `WHATSAPP_ENABLED=false` pauses it. *(Built this way rather than requiring `WHATSAPP_ENABLED=true`, so UPG-49's existing behaviour and tests hold.)*
  - **Messages:** registration confirmation with the ticket link, the day-before reminder, and change and cancellation notices, each once (the same rule as email).
  - **Templates** in `config/whatsapp_templates.json`, with the variables marked, ready to submit for approval; the approval steps in `docs/DEPLOY.md`.
  - **Opt-in:** a checkbox at registration, saved with the time; a STOP reply (through the provider's signed webhook) or the profile switch stops all WhatsApp to that number.
  - **Fallback:** email always goes out; a failed WhatsApp send goes to the outbox for retry (UPG-18).
  - **Monthly cap** set by the Super Admin: at the cap WhatsApp pauses for the month, email carries on, and the admin is told once.
- **Effort:** M · **Depends on:** UPG-18, UPG-49 · **Risk:** medium (sends cost money).
- **Built (2026-10-20):** `services_whatsapp.py` (new) and `routes_whatsapp.py` (new): every WhatsApp send passes `gate()` in `utils_whatsapp._send` (on only with a configured provider, opted-in number not STOPped, under the monthly cap); Meta Cloud API or Twilio; the four messages from `config/whatsapp_templates.json` (registration confirmed with the ticket link, reminder, change, cancellation), once each through `whatsapp_log` and the outbox task `send_whatsapp_template` (the reminder keeps its Twilio wording and uses the template on Meta); a registration checkbox saved with its time, the profile switch, and a signed webhook (Twilio X-Twilio-Signature over BASE_URL, Meta X-Hub-Signature-256) honouring STOP/START; UPG-49 notification preferences count as opt-in; the Super Admin's cap at `/whatsapp/settings` with one alert email at the cap; approval steps in `docs/DEPLOY.md` ("WhatsApp").
- **Files touched:** `services_whatsapp.py`, `routes_whatsapp.py`, `config/whatsapp_templates.json`, `templates/whatsapp/settings.html` (new), `utils_whatsapp.py`, `services_automation.py`, `services_venue.py`, `services_workflow.py`, `tasks/notification_tasks.py`, `tasks/scheduled_tasks.py`, `routes_forms.py`, `templates/public/registration_form.html`, `templates/profile/dashboard.html`, `templates/admin/dashboard.html`, `app.py`, `.env.example`, `docs/DEPLOY.md`, `tests/test_whatsapp.py` (new)
- **Acceptance criteria:**
  1. ✅ Test: with no provider set, or with `WHATSAPP_ENABLED=false`, nothing is sent; with a provider configured, a message goes through it (Twilio or Meta). [T `tests/test_whatsapp.py`::test_nothing_goes_unless_switched_on_and_configured]
  2. ✅ Test: the registration confirmation (with the ticket link), the day-before reminder, a change notice and a cancellation notice each go once to an opted-in person, even when the job or change runs again. [T `tests/test_whatsapp.py`::test_each_of_the_four_messages_goes_once]
  3. ✅ Test: every template's variables match its numbered placeholders, and `docs/DEPLOY.md` describes submitting them for approval. [T `tests/test_whatsapp.py`::test_the_templates_are_ready_for_approval]
  4. ✅ Test: without the checkbox nothing is sent; the opt-in is saved with its time; a signed STOP reply (Twilio and Meta) stops messages and an unsigned one is refused; the profile switch turns them off and on. [T `tests/test_whatsapp.py`::test_opt_in_stop_and_the_profile_switch]
  5. ✅ Test: when the provider fails, the email still goes and the WhatsApp send waits in the outbox. [T `tests/test_whatsapp.py`::test_a_failed_whatsapp_waits_in_the_outbox_and_email_still_goes]
  6. ✅ Test: at the monthly cap nothing more is sent, the Super Admin is told once, and email still goes; only the Super Admin sets the cap. [T `tests/test_whatsapp.py`::test_the_monthly_cap_pauses_whatsapp_and_tells_the_admin_once]

#### UPG-148 — The registration confirmation hides text under the pinned footer on a phone
- **Status:** DONE
- **Last verified:** 2026-10-20, commit "UPG-148: …" (parent `e4c0012`) [T]
- **Problem:** Found by the end-of-run browser pass. `templates/participant/registration_confirmed.html` uses the status layout, which pins the footer to the bottom of the screen. For someone registering without an account, the page adds a "Set your password" box and becomes taller than a 375px screen, so the pinned footer sits over that box. The phone journey (UPG-28) registers a signed-in student, whose page has no such box, so it never showed.
- **What to build:** the page doesn't pin its footer (as the certificate verification page, UPG-125).
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Built (2026-10-20):** `templates/participant/registration_confirmed.html` sets `site_footer_fixed = false`, so the footer follows the page instead of covering the set-password box. Found by the end-of-run browser pass (`tests/test_reach_and_reports_phone.py`, which also covers the IQAC report flow, the impact dashboard and the open-events page for UPG-144 to UPG-146).
- **Files touched:** `templates/participant/registration_confirmed.html`, `tests/test_reach_and_reports_phone.py` (new)
- **Acceptance criteria:**
  1. ✅ Test: at 375px and 1280px, the confirmation for a new account (with the "Set your password" box) has no text under the footer (headless). [T `tests/test_reach_and_reports_phone.py::test_reports_impact_open_events_and_an_external_registration_fit_both_widths` (an external student's confirmation with the set-password box, measured at 375 and 1280); fails before the change]

#### UPG-149 — Multi-round competitions (hackathons with 2–3 rounds) end to end
- **Status:** DONE
- **Last verified:** 2026-10-31, commit "UPG-149: …" (parent `f6fcf99`) [T]
- **Problem:** Owner request 2026-10-31: "is the website compatible for two rounds or three rounds like hackathons?" The pieces existed: the wizard's "Number of rounds" (`services_event_types.py:444`, saved as `total_rounds`), the SPOC's round panel with lock scoring and advance by top N or cut-off (`routes_spoc.py:1829-1991` at `f6fcf99`), the coordinator's "Next round / eliminate" (`routes_coordinator.py:353-388`), and judges who see only the current round's present teams (`routes_judge.py:155-168`). But:
  1. **Advancing deleted the round's scores.** Advancers got `scores: {}` (`routes_spoc.py:1962`; the coordinator used `DELETE_FIELD`, `routes_coordinator.py:373`). Round 1's marks, criteria and remarks were gone, and nothing kept a round history. In postgres mode the `{}` didn't even clear them (UPG-151), so round 1's scores were counted again in round 2.
  2. **Unscored teams were stranded.** `advance_round` skipped teams with no score (`:1938`): they were neither advanced nor eliminated, and stayed on round 1 while the event moved on.
  3. **The number of rounds was ignored.** Nothing read `total_rounds`; the panel offered "Advance to Round 4" in a 3-round event and never named the final round.
  4. **A second click advanced again.** The form didn't say which round it was for, so a double submit or a stale tab ran 2 → 3 straight after 1 → 2.
  5. **Ties at the top-N cut were split arbitrarily**, by sort order.
  6. **Nobody was told they were out**, though the panel said "Eliminated participants are notified" (`templates/spoc/round_panel.html:233`); students saw their round status nowhere.
  7. **Two rules.** The coordinator's promote compared the *sum* of the judges' totals with the cut-off (`routes_coordinator.py:370`); the SPOC panel and every leaderboard use the average (UPG-84).
  8. **Judges could score teams that were out**: `submit_score` (`routes_judge.py:189`) didn't check the team's round or elimination.
- **Who benefits:** organisers of hackathons, quizzes and any competition with qualifying rounds; the teams.
- **Built (2026-10-31):**
  - **One round service, `services_rounds.py` (new).**
    - `round_info` (`:48`): current round, total and final; an event advanced past its `total_rounds` counts the current round as the total.
    - `round_teams` (`:61`) skips eliminated, cancelled and refunded teams.
    - `advance` (`:127`) is used by the SPOC panel (`routes_spoc.py:1911`) and the coordinator's promote (`routes_coordinator.py:361`). It refuses, changing nothing, when:
      - the posted round isn't the event's current round;
      - the round is the final one;
      - no team has a score;
      - present teams are unscored and "eliminate unscored teams" isn't ticked;
      - nobody reaches the mark.
    - Teams go through by top N, with every team tied at the cut included, or by a cut-off on the shared average (`score_of`, UPG-84).
    - The event moves first (`:175`), so a second submit of the same page is refused.
    - Every team in the round gets a `round_history` entry: round, score, judges, the judges' scores, result, time and organiser (`:186`).
    - Advancers' scores are cleared with `DELETE_FIELD` (`:193`). Everyone else is eliminated with `eliminated_in_round`; unscored teams that weren't present are recorded as absent.
    - `_notify` (`:208`) sends one email to each person on every team (`services_recipients.registration_people`): the existing advancement email, or the new `send_round_not_qualified_email` (`utils_email.py:1059`; absent teams get their own wording). The coordinator also sends its elimination WhatsApp.
  - **Judges:** `submit_score` and `score_inline` refuse, with 409, a team that is eliminated, cancelled or not in the current round (`can_score`, `services_rounds.py:228`; `routes_judge.py:211`, `:313`).
  - **Round panel** (`routes_spoc.py:1832`, `templates/spoc/round_panel.html`):
    - "Round X of N" and "· Final".
    - In the final round, a link to publish the results instead of the advance form (`:176`).
    - The advance form posts its round (`:204`) and shows an "eliminate unscored teams" tick when present teams are unscored (`:240`).
    - An "Earlier rounds" card with each round's counts and top teams (`:267`, `services_rounds.history`).
  - **The coordinator's and admin's promote modals** post their round (`templates/coordinator/dashboard.html:297`, `templates/admin/dashboard.html:833`) and say the cut-off applies to the average judge score.
  - **Students:** the dashboard (`routes_participant.py:111`, `templates/participant/dashboard.html:260`) and ticket (`routes_ticket.py:293`, `templates/participant/ticket.html:393`) show "Round 1 of 3", "Qualified for round 2 of 3" or "Not qualified after round 1 of 3". One-round events show nothing new.
- **Files touched:** `services_rounds.py` (new), `routes_spoc.py`, `routes_coordinator.py`, `routes_judge.py`, `routes_participant.py`, `routes_ticket.py`, `utils_email.py`, `templates/spoc/round_panel.html`, `templates/coordinator/dashboard.html`, `templates/admin/dashboard.html`, `templates/participant/dashboard.html`, `templates/participant/ticket.html`, `tests/test_multi_round.py` (new)
- **Effort:** M · **Depends on:** UPG-84 (DONE) · **Risk:** the coordinator's cut-off changed from a sum to an average (said on its modal).
- **Acceptance criteria** (`tests/test_multi_round.py`, real database layer; all 9 tests fail on `f6fcf99`):
  1. ✅ Test: a 3-round hackathon runs round 1 → 2 → 3 → publish results; each team's `round_history` keeps every round's score, and the final ranking uses only the final round's scores. [T `::test_a_three_round_hackathon_runs_to_results_and_keeps_every_round`]
  2. ✅ Test: an unscored present team stops the advance (nothing changes) unless "eliminate unscored" is ticked; an absent unscored team is eliminated as absent; no team is left on an old round. [T `::test_unscored_teams_stop_the_advance_or_are_eliminated_never_stranded`]
  3. ✅ Test: advancing in the final round is refused; a stale round number changes nothing. [T `::test_the_final_round_cant_be_advanced_and_a_stale_page_changes_nothing`]
  4. ✅ Test: top N with a tie at the cut advances every tied team. [T `::test_top_n_lets_every_team_tied_at_the_cut_through`]
  5. ✅ Test: each person on advancing and eliminated teams gets one email. [T `::test_every_person_on_each_team_gets_one_result_email`]
  6. ✅ Test: the coordinator's promote uses the same service and the average; a stale coordinator form changes nothing. [T `::test_the_coordinators_promote_uses_the_average_and_keeps_history`]
  7. ✅ Test: a judge's score for an eliminated team, or a team on an earlier round, is refused (409) and stores nothing, on both scoring routes. [T `::test_judges_cant_score_eliminated_teams_or_teams_on_another_round`]
  8. ✅ Test: the student dashboard and ticket show the round status; the round panel shows "Round X of N" and, in the final round, no advance form. [T `::test_students_see_their_round_and_the_panel_says_round_x_of_n`, `::test_a_one_round_event_shows_no_round_status`]
  - Full pytest: at "UPG-150: …": SQLite 1,316 passed, 7 skipped; PostgreSQL 16 1,322 passed, plus `tests/test_backup_restore.py`, which failed only because the run gave `psql` a `postgresql+psycopg2://` URL and passes with the plain `postgresql://` one; ruff clean.

#### UPG-150 — The registration form as a full-page, official form
- **Status:** DONE
- **Last verified:** 2026-10-31, commit "UPG-150: …" (parent `820a5ce`) [T]
- **Problem:** Owner request 2026-10-31: the registration form should fill the screen, structured and official, with underlined fields instead of boxes, like Google Forms or Unstop. `templates/public/registration_form.html` was a 680px column (`.reg-wrap`, `:10` at `f6fcf99`): a navy banner over one card, every input a bordered box, and the identity questions, event questions and consent in one undivided list.
- **Built (2026-10-31):** the same form, with the same field names, ids, errors, CSRF, submission id and Back link (UPG-26, UPG-63 and the popup's Back test unchanged), laid out as a full page:
  - **Two columns at 992px and wider** (`templates/public/registration_form.html:15-17`). On the left, a sticky navy event summary (`:228`): category, title, date and time, venue, entry fee, team size (team events), "N rounds" (multi-round events), register-by and a privacy note. On the right, the form sheet with "* Indicates a required question". One column on a phone.
  - **Numbered sections** (`:276`, `:325`, `:336`, `:359`): 1 Participant details (who's registering, affiliation, identity), Registration details (the event's own questions), Team (team name and members, team events only), Declaration (privacy consent and WhatsApp opt-in). Empty sections are left out and the numbers follow. `routes_forms.form_sections` (`routes_forms.py:191`, with `IDENTITY_FIELD_IDS` `:185`) splits the fields, keeping each form-builder heading with the questions after it; the route passes it with the team size (`:589`).
  - **One block per team member** (owner's review of the first version, 2026-10-31: "keep a separate section for each member, don't put member 3's name beside member 2's details"). `routes_forms.team_blocks` (`routes_forms.py:220`; template `:344`, CSS `:84`) splits the team fields into the team name and one block per member, numbered as people see them (member 1 is the lead). Each block has a "Member N" title marked Required or Optional, a gold rule at its side, and that member's name, email and USN on one row; on a phone they stack. Field names are unchanged; only the visible label inside a block drops the "Member N" prefix.
  - **Underlined fields** (`:62`): inputs, selects and text areas have only a bottom rule, a navy underline on focus, gold on keyboard focus and red on error. Radios and checkboxes are plain rows. Fields sit two to a row from 768px; long ones span the row.
- **Files touched:** `templates/public/registration_form.html`, `routes_forms.py`, `tests/test_registration_form_layout.py` (new)
- **Effort:** S · **Depends on:** UPG-63 (DONE) · **Risk:** low; the route's handling is unchanged.
- **Acceptance criteria** (`tests/test_registration_form_layout.py`, headless Chromium as in UPG-28):
  1. ✅ Test: at 1280px the form and summary together span at least 85% of the page's content width, side by side, with no contrast failures, for a solo and a team event. [T `::test_the_form_and_summary_fill_the_page_side_by_side`]
  2. ✅ Test: every visible text input, select and text area has no top, left or right border and a solid bottom border. [T `::test_every_field_is_underlined_not_boxed`]
  3. ✅ Test: the form is in numbered sections, with the team fields in their own section on a team event; the summary shows the team size and rounds; a builder heading stays with its questions. [T `::test_the_form_is_in_numbered_sections_with_the_team_on_its_own`, `::test_a_builder_heading_stays_with_the_questions_after_it`]
  4. ✅ Test: at 375px there's no sideways scroll or clipped content and the fields stay underlined [T `::test_no_sideways_scroll_on_a_phone`]; the registration journey still registers (UPG-28's `tests/test_phone_journey.py::test_the_student_journey_and_the_scanner_fit_a_phone`, unchanged).
  5. ✅ Test (added from the owner's review): each team member's name, email and USN are in a block of their own, titled "Member N" and marked required or optional; at 1280px and 375px no block shares a row with another, and at 1280px a member's three fields sit on one row. [T `::test_each_team_member_has_a_block_of_their_own`, `::test_team_blocks_group_fields_by_member`]; a member asked five details gets three on the first row and two below, inside the block, and the form has no empty section [T `::test_more_details_per_member_wrap_inside_their_block`]
  - Full pytest: at "UPG-150: …": SQLite 1,316 passed, 7 skipped; PostgreSQL 16 1,322 passed, plus `tests/test_backup_restore.py`, which failed only because the run gave `psql` a `postgresql+psycopg2://` URL and passes with the plain `postgresql://` one; ruff clean.

#### UPG-152 — Low-email registration and login for the hackathon
- **Status:** DONE
- **Last verified:** 2026-10-31, commit "UPG-152: …" (parent `57a5922`) [T]
- **Problem (owner's 14 requirements, 2026-10-31):** the mail provider's free tier allows about 500 emails a day (Brevo's free plan about 300), and a hackathon registers many teams in a day. At `57a5922`:
  - a new team registration emailed the lead twice (the confirmation and a separate "Set your SapthaEvent password" email) and every team member once more (`routes_forms.py` member loop; `routes_teams.py` join confirmation);
  - reminder, ticket, cancellation and round emails went to every person on the team (`services_recipients.registration_people`);
  - set-password links lasted 7 days and reset links 1 hour; any number of reset emails could be asked for;
  - nothing counted emails, so the app could pass the provider's daily quota and lose mail silently;
  - the request log (`app.py`) and gunicorn's access log wrote `/set_password/<token>` and `/reset_token/<token>` paths, so the tokens were in the logs.
- **Who benefits:** organisers (no lost mail on the busy day, a per-registration view of the login email), participants (one clear email), the owner (stays inside the free quota).
- **What was built:**
  - **One email per new registration, to the lead only.** A new account's registration email is the confirmation and the one-time set-password link together: subject "Registration Confirmed — <event>", the event, date, venue, team and registration ID, then the link (`utils_email.send_set_password_email`, `utils_email.py:799`; `_registration_block`, `:783`; `routes_forms._email_new_account`, `routes_forms.py:251`). An existing account still gets one confirmation with its cancel link, and no login link. No password or credential is ever emailed. The legacy `/register` route does the same (`routes_participant.py:572-578`).
  - **Team members get nothing automated by default.** `NOTIFY_TEAM_MEMBERS` (config, default off; `config.py:214`) decides; `services_recipients.registration_people` returns only the lead unless it is on (`services_recipients.py:12-36`). This covers the confirmation, reminders, tickets, cancellations, round results and the WhatsApp reminder loop; the team join confirmation follows the same switch (`routes_teams.py:154`). Team members get no accounts.
  - **Set-password links last 48 hours and work once** (`SET_PASSWORD_MAX_AGE`, `services_accounts.py:25`; the token is bound to the password hash, as since UPG-33). This applies to every set-password link (participants, staff, walk-ins).
  - **Reset links last 15 minutes and work once** (`RESET_MAX_AGE`, `services_accounts.py:27`); the email says so.
  - **One reset email in a registration account's first 48 hours** (`PARTICIPANT_RESET_LIMIT` = 1, `PARTICIPANT_RESET_WINDOW_HOURS` = 48, `config.py:215-216`; `reset_refusal`, `services_accounts.py:280`). Accounts made by a registration carry `registration_account_at`; staff and older accounts keep the normal reset. A second request, or one after the 48 hours, is refused with exactly "We could not complete your password reset. Please contact the hackathon organizer for assistance." (`ORGANIZER_MESSAGE`, `services_accounts.py:33`; `routes_auth.py:394-399`).
  - **A daily email limit** (`EMAIL_DAILY_LIMIT`, default 450, 0 = none; `config.py:213`). Every email the app sends counts, one per recipient, in one per-UTC-day row of the new `email_quota` table (`models_pg.py:626`, migration `0010_email_quota`), shared by all instances (`services_email_quota.py`). `utils_email._send` reserves the places atomically before sending (an `INSERT … ON CONFLICT DO NOTHING`, then `UPDATE … WHERE sent + n <= limit`) and gives them back if the provider refuses (`utils_email.py:506-522`). At the limit nothing is sent; forgot-password shows the organizer message before looking up the account, so the answer doesn't reveal whether an account exists (`routes_auth.py:371-373`), and the registration page says the password email couldn't be sent and the registration is saved (`REGISTRATION_EMAIL_NOT_SENT`, `services_accounts.py:35`; `templates/participant/registration_confirmed.html:44`). If the counter can't be read the email is sent (fail open), with a logged error. `/diag/email` shows today's count and the limit (`routes_auth.py:545`).
  - **What organisers can see.** Each send writes `login_link` on the account (kind, status, when, expiry, who sent it) and an audit line `LOGIN_LINK_EMAIL` with the status and expiry (`email_login_link`, `services_accounts.py:178`); reset requests write `reset_last` and audit lines `RESET_REQ_REFUSED`, `RESET_REQ_EMAIL_LIMIT`, `RESET_LINK_SENT`, `RESET_LINK_FAIL` (`note_reset_request`, `:297`). The coordinator's registrations page has a "Login email" column (password set, link sent and when it expires, expired, refused, not sent at the limit, failed) and a "Send password link" button for a participant's account, needing `manage_registrations` (`login_status`, `services_accounts.py:243`; `routes_coordinator.py:155,168`; `templates/coordinator/registrations.html:54`).
  - **No passwords or tokens in any log.** Passwords are hashed (werkzeug pbkdf2, unchanged) and never logged or stored in plain text. The token is never stored or written to the audit log. The app's request, 404, 429 and CSRF log lines redact link tokens (`log_redact.redact`; `app.py:152,1376,1384,1404,1409`), and gunicorn's access log uses a redacting logger for the request line, path and query (`gunicorn.conf.py:49-68`).
  - **Messages.** Clear success and error messages for registration, password setup (expired: "works for 48 hours"; used; success names the email to log in with), login and reset (expired: "reset links work for 15 minutes").
- **Not covered (outside the app):** Cloud Run's own platform request log records URLs; the tokens there are one-time and short-lived. The paid flow still sends a new user three emails (UPG-153). UPG-39's development-only console link stays (no mail provider, never production).
- **Files touched:** `services_email_quota.py` (new), `log_redact.py` (new), `migrations/versions/0010_email_quota.py` (new), `models_pg.py`, `config.py`, `utils_email.py`, `services_accounts.py`, `services_recipients.py`, `routes_auth.py`, `routes_forms.py`, `routes_participant.py`, `routes_teams.py`, `routes_coordinator.py`, `app.py`, `gunicorn.conf.py`, `templates/coordinator/registrations.html`, `templates/participant/registration_confirmed.html`, `.env.example`, `tests/conftest.py`, `tests/test_low_email_auth.py` (new).
- **Existing tests changed (preconditions or helpers only; no assertion weakened):** `tests/test_team_member_notices.py` and `tests/test_multi_round.py::test_every_person_on_each_team_gets_one_result_email` turn `NOTIFY_TEAM_MEMBERS` on, because they test the team-member emails that are now opt-in; `tests/test_registration_no_auto_login.py`'s `_set_password_links` finds the link in any email to the address, because it now arrives inside the confirmation instead of a separate email. `tests/conftest.py` gains an autouse fixture that empties `email_quota` before each test.
- **Effort:** M · **Depends on:** UPG-33, UPG-39, UPG-48 (all DONE) · **Risk:** the refusal message tells a caller that an email is a participant account (accepted for requirement 8; the hourly login and reset throttle limits probing). Migration 0010 must run before the new revision serves (the `saptha-migrate` job).
- **Acceptance criteria** (`tests/test_low_email_auth.py`, real database layer, Brevo HTTP mocked):
  1. ✅ A new team registration sends exactly one email, to the lead, with the confirmation and a set-password link; team members get none (`::test_a_new_team_registration_sends_one_email_to_the_lead_only`).
  2. ✅ An existing account gets one confirmation and no login link (`::test_an_existing_account_gets_one_confirmation_and_no_login_link`).
  3. ✅ Team members get emails only when `NOTIFY_TEAM_MEMBERS` is on (`::test_team_members_get_emails_only_when_the_owner_turns_it_on`).
  4. ✅ The set-password link works after 47 hours, not after 49, works once, and the participant then logs in with email and the new password (`::test_the_set_password_link_lasts_48_hours_works_once_and_then_login_works`).
  5. ✅ One reset email in the first 48 hours; the second request and any after 48 hours get exactly the organizer message and send nothing (`::test_one_reset_email_in_the_first_48_hours_then_the_organizer_message`).
  6. ✅ The reset link works at 14 minutes, not at 16, and once (`::test_the_reset_link_lasts_15_minutes_and_works_once`).
  7. ✅ Registration and reset emails count against one daily limit; at the limit nothing is sent and the organizer message shows (`::test_the_daily_limit_counts_every_email_together_then_sends_nothing`).
  8. ✅ The counter never passes the limit and gives back emails the provider refused (`::test_the_counter_is_atomic_and_gives_back_refused_emails`).
  9. ✅ Email status, expiry and reset status are logged; no password and no token appears in the logs, the audit log or the account (`::test_status_and_expiry_are_logged_never_a_password_or_token`, `::test_link_tokens_are_redacted_in_request_and_access_logs`).
  10. ✅ The organiser sees each registration's login email status and can send a new link; another SPOC gets 403, a registration from another event sends nothing, and at the limit nothing is sent and the page says so (`::test_the_organizer_sees_the_login_email_and_can_send_a_new_link`).
  - Full pytest: SQLite 1,326 passed, 7 skipped, 1 failed: `tests/test_production_boot.py::test_every_environment_variable_the_app_reads_is_in_env_example`, because the four new settings weren't in `.env.example` yet; added, and the file passes. PostgreSQL 16 on an empty database, after that fix: 1,334 passed. (A run on a reused PostgreSQL test database with 1,873 leftover accounts failed the three `/admin/users` page tests: UPG-154.) ruff clean.

#### UPG-155 — Ticket types: early-bird windows, seat limits per ticket and group prices
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: Luma, KonfHub, Ticket Tailor, Whova and Eventzilla sell several ticket types with their own dates and seat limits. SapthaEvent priced by participant group only (`services_payments.fee_for`: student, faculty, external, regular). `ticket_tiers` was stored and filled by the AI copilot, but nothing priced a registration from it.
- **Who benefits:** organisers of paid events, the finance office.
- **What was built:**
  - **The types.** An event's `ticket_types` (name, price, sale start and end dates, seats, who may buy, and per registration or per person), at most 10, edited in the wizard's ticket-type box (`templates/spoc/create_event.html:276`; `static/js/pages/spoc__create_event.js:290`; `services_ticket_types.from_form`, `services_ticket_types.py:187`; `services_event_types.py:404`). A sale ending before it starts is refused. The legacy `ticket_tiers` field is never used for prices (`services_ticket_types.py:17-18`).
  - **The form.** It lists the types on sale for the registrant with price, early-bird dates and seats left (`templates/public/registration_form.html:323`; `routes_forms._ticket_types_offered`, `routes_forms.py:617`). On an event with types one must be chosen; the choice is checked at submit (on sale, open to that participant type, seats left; `services_ticket_types.check_choice`, `:165`; `routes_forms.py:686`).
  - **The price.** `services_payments.registration_fee` and `server_price` use the chosen type, else `fee_for` as before (`services_payments.py:101-119`). A per-registration type charges once for a whole team; a per-person type charges price × members (`services_ticket_types.price`, `:94`). The sale window is checked again when the Razorpay order is made (`routes_payment.py:369,685`).
  - **Seats.** Counted in the new `ticket_type_sales` table (`models_pg.py:674`, migration `0011_ticket_type_sales`) and taken with one conditional UPDATE, so two completions can't both take the last seat (`take_seat`, `services_ticket_types.py:121`). A paid registration takes its seat when the payment completes; a sold-out type then records the payment for a refund and registers nobody (`routes_payment.py:428-450`). A free type takes the seat at submit (`routes_forms.py:908`). Cancelling gives the seat back (`routes_participant.py:636-640`).
  - **Storage and exports.** The registration stores `ticket_type_id` and `ticket_type_name` (`routes_forms.py:817`); the exports have a "Ticket type" column (`services_export.py:113`).
  - **Waitlist.** A promotion is paid when the chosen type costs something (`routes_waitlist.promotion_terms`, `routes_waitlist.py:189`) and records the seat with no limit, because the event's own limit already let them in (`routes_waitlist.py:280`).
- **Decided while building:** completion checks only seats, not the sale dates: someone who started paying inside the window is not refused for finishing a minute after it closed (the dates are checked at submit and at order creation). A held waitlist seat skips the sale check.
- **Files touched:** `services_ticket_types.py` (new), `migrations/versions/0011_ticket_type_sales.py` (new), `models_pg.py`, `services_payments.py`, `services_event_types.py`, `routes_forms.py`, `routes_payment.py`, `routes_participant.py`, `routes_waitlist.py`, `routes_spoc.py`, `services_export.py`, `templates/spoc/create_event.html`, `static/js/pages/spoc__create_event.js`, `templates/public/registration_form.html`, `tests/test_ticket_types.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** money: the server-side price is kept (BLK-03). Migration 0011 must run before the new revision serves.
- **Acceptance criteria** (`tests/test_ticket_types.py`, real database layer, Razorpay mocked):
  1. ✅ An early-bird type is charged before its end date and refused after; the regular type is charged after (`::test_early_bird_is_charged_before_its_end_and_refused_after`).
  2. ✅ A type with 2 seats refuses the third registration (`::test_a_type_with_two_seats_refuses_the_third`), also when two payments complete for the last seat (`::test_two_payments_completing_for_the_last_seat_register_one`); ten payments at once take exactly two seats on PostgreSQL (`::test_ten_payments_at_once_take_exactly_two_seats`, `::test_take_seat_is_race_free_on_the_database`).
  3. ✅ A team type charges one price per team; a per-head type charges price × members (`::test_a_team_type_charges_once_and_a_per_head_type_per_member`).
  4. ✅ An event with no types is priced exactly as before (`::test_an_event_without_types_is_priced_by_fee_for`, `::test_an_event_without_types_charges_its_fee_at_checkout`).
  5. ✅ The export shows each registration's ticket type (`::test_the_export_shows_each_registrations_ticket_type`).
  - Also: a type must be chosen, a cancelled registration frees its seat, the wizard rejects a sale ending before it starts, the form lists price and seats, a paid type makes a waitlist promotion paid.

#### UPG-156 — Apple Wallet and Google Wallet tickets
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: Luma and Ticket Tailor put tickets in Apple/Google Wallet. SapthaEvent had no wallet pass.
- **Who benefits:** participants (no hunting for the email at the gate), check-in staff.
- **What was built:**
  - **Apple Wallet.** `GET /ticket/<reg_id>/wallet/apple.pkpass` (`routes_ticket.py:484`) returns a signed `.pkpass`: `pass.json` with the event, date, venue when set and the registration; a manifest of SHA-1 hashes; a detached PKCS#7 signature with the pass certificate and Apple's WWDR certificate (`services_wallet.build_pkpass`, `services_wallet.py:117`; `_sign`, `:103`).
  - **Google Wallet.** `GET /ticket/<reg_id>/wallet/google` (`routes_ticket.py:498`) redirects to a "Save to Google Wallet" link: a JWT signed with the service account's key, holding a generic class and object for the ticket (`google_claims`, `services_wallet.py:141`; `google_save_url`, `:170`).
  - **The QR.** Both carry the same QR as the ticket page: the ticket's verify link with its signed token, so every scanner accepts it.
  - **When they show.** Each button shows on the ticket page only when its keys are set (`routes_ticket.py:376`; `apple_configured`/`google_configured`, `services_wallet.py:46-50`), with the same day-before window as the ticket's QR. A cancelled registration and another person's ticket get no pass.
  - **Settings.** `APPLE_PASS_TYPE_ID`, `APPLE_TEAM_ID`, `APPLE_PASS_CERT`, `APPLE_PASS_KEY`, `APPLE_WWDR_CERT`, optional `APPLE_PASS_KEY_PASSWORD`, `GOOGLE_WALLET_ISSUER_ID`, `GOOGLE_WALLET_SERVICE_ACCOUNT` (PEM/JSON text or a file path; `.env.example:199-206`). They are secrets: Secret Manager, never in git.
- **Decided while building:** the barcode is the verify link (what the ticket page's QR holds), not the bare token, so a phone camera also opens the verify page.
- **Not covered:** a real Apple or Google account wasn't used: the tests make their own keys and check the files and the JWT; nothing is sent out. Passes aren't updated after issue (no push updates to the pass).
- **Files touched:** `services_wallet.py` (new), `routes_ticket.py`, `templates/participant/ticket.html`, `.env.example`, `tests/test_wallet_passes.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** signing keys are secrets; a pass's QR follows the scanner's refusals (cancelled, transferred since UPG-161).
- **Acceptance criteria** (`tests/test_wallet_passes.py`, keys made by the test):
  1. ✅ With keys configured the ticket page offers both buttons; without, neither shows (`::test_the_buttons_show_only_with_keys`, `::test_no_buttons_without_any_keys`).
  2. ✅ The `.pkpass` is a valid zip whose `pass.json` barcode is the ticket's signed token, its signature verifies, and the scanner accepts it (`::test_the_pkpass_carries_the_signed_token_and_the_scanner_accepts_it`).
  3. ✅ The Google Wallet link's JWT decodes to the same token and event details (`::test_the_google_wallet_link_carries_the_same_token_and_event`).
  4. ✅ Another person's ticket gets 403 for both (`::test_another_persons_ticket_is_403_for_both`).
  - Also: a cancelled registration gets no pass; before the QR opens the registrant gets none.

#### UPG-157 — Browser push notifications, switched on
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: Luma, Whova, Bizzabo and Webex Events push reminders and changes to phones. SapthaEvent had a push backend (`routes_push.py`) but no page subscribed and nothing sent.
- **Who benefits:** participants (the installed PWA), organisers (fewer emails under `EMAIL_DAILY_LIMIT`).
- **What was built:**
  - **Opt-in.** A "Get notifications on this device" box after registration (`templates/participant/registration_confirmed.html:56`) and in profile settings (`templates/profile/dashboard.html:227`); the browser asks only when the button is pressed, never on page load (`templates/includes/push_optin.html`, `static/js/push-optin.js`).
  - **Subscriptions.** One per browser (its endpoint), for the logged-in user; logged out and malformed subscriptions are refused (`routes_push.py:17-30`; `services_push.subscribe`, `services_push.py:35`).
  - **What is pushed.** Copies of notices that also go by email or in-app: the day-before reminder (`tasks/scheduled_tasks.py:113`), change and cancellation notices through the notification channels (`services_automation.py:119,241`; `services_workflow.py:353`; `services_venue.py:572`) and published results (`routes_spoc._push_results`, `routes_spoc.py:1057`; `routes_coordinator.py:497`). Each is sent once per person (`send_once`, `services_push.py:106`) to that event's registrants only (`push_to_registrants`, `:120`).
  - **Clean-up.** A 404 or 410 from the push service deletes the subscription; other failures keep it (`services_push.send`, `services_push.py:83`).
  - **Off until set up.** With no `VAPID_PUBLIC_KEY` and `VAPID_PRIVATE_KEY` there's no prompt and nothing is sent (`app.py:464-466`; `.env.example:193`).
- **Decided while building:** the subscription is the opt-in; the UPG-49 preferences can still turn push off (`services_automation.py:126`).
- **Files touched:** `services_push.py` (new), `routes_push.py`, `app.py`, `services_automation.py`, `services_workflow.py`, `services_venue.py`, `tasks/scheduled_tasks.py`, `routes_spoc.py`, `routes_coordinator.py`, `templates/includes/push_optin.html` (new), `static/js/push-optin.js` (new), `templates/participant/registration_confirmed.html`, `templates/profile/dashboard.html`, `.env.example`, `tests/test_push_notifications.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** push never replaces a required email.
- **Acceptance criteria** (`tests/test_push_notifications.py`, push service mocked):
  1. ✅ Subscribing stores one subscription per browser for the logged-in user; logged out is refused (`::test_subscribing_keeps_one_subscription_per_browser`, `::test_logged_out_and_malformed_subscriptions_are_refused`).
  2. ✅ A change notice is pushed once to each subscriber of that event and to nobody else (`::test_a_change_notice_is_pushed_once_to_each_subscriber_of_the_event`); results too (`::test_published_results_push_once_to_each_registrant`).
  3. ✅ A 410 deletes the subscription (`::test_a_410_from_the_push_service_deletes_the_subscription`); another failure keeps it (`::test_another_failure_keeps_the_subscription`).
  4. ✅ With no VAPID keys no prompt shows and nothing is sent (`::test_without_vapid_keys_no_prompt_and_nothing_is_sent`).

#### UPG-158 — Name badges printed at check-in
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: 16 of the 38 platforms read print badges at the door. SapthaEvent had no badge printing.
- **Who benefits:** conferences, FDPs, fests with outside colleges.
- **What was built:**
  - **The badge.** Name; college (faculty and external participants) or department (students); participant type or team; the university logo; the event; and the QR of the registration's signed ticket token, which every scanner accepts (`services_badges.participant_badges`, `services_badges.py:43`; `_draw`, `:118`). Each team member gets a badge with the team's QR. Staff, judges and volunteers get role badges in their own colour, without a QR (`staff_badges`, `:63`).
  - **Bulk sheets.** `GET /ticket/badges/<event_id>.pdf` (`routes_ticket.py:457`): A4 sheets of 8 (2 × 4, 105 × 74 mm) with cut lines, one per confirmed registration and person (`event_badges`, `services_badges.py:85`; `render`, `:160`); cancelled, unpaid and waitlisted registrations are left out.
  - **At the door.** After a successful check-in both scanners show a "Print badge" link to `GET /ticket/<reg_id>/badge.pdf`, one badge on its own page (`routes_ticket.py:198,468`; `templates/spoc/scan.html:549`; `templates/coordinator/scan.html:300`). The SPOC dashboard links to the bulk PDF.
  - **Who prints.** Only the event's check-in staff (`check_in` permission); others get 403.
- **Decided while building:** one badge per person, not per registration.
- **Files touched:** `services_badges.py` (new), `routes_ticket.py`, `templates/spoc/scan.html`, `templates/coordinator/scan.html`, `templates/spoc/dashboard.html`, `tests/test_badges.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** personal data on paper: only a name, an institution or department and a role.
- **Acceptance criteria** (`tests/test_badges.py`):
  1. ✅ The bulk PDF has one badge per confirmed registration, 8 a page, with each name and a QR the scanner accepts (`::test_the_sheet_has_one_badge_per_confirmed_registration_8_a_page`, `::test_a_team_gets_a_badge_per_member_with_its_qr`, `::test_the_scanner_gives_the_badge_link_after_a_check_in`).
  2. ✅ A badge never shows a phone number or email (`::test_a_badge_never_shows_a_phone_or_email`).
  3. ✅ Only the event's staff can print; others 403 (`::test_only_the_events_staff_can_print`).

#### UPG-159 — Session check-in and a personal agenda
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: Whova, Swapcard, vFairs and Webex Events check people into each session and let attendees star sessions. SapthaEvent had an agenda (`routes_spoc.py` manage_agenda) but attendance was per event only.
- **Who benefits:** conferences, FDPs (hours per session), fest sub-events.
- **What was built:**
  - **Sessions.** Each agenda item gets an ID, an end time, a room, seats and optional hours (`services_sessions.parse_agenda`, `services_sessions.py:41`; `templates/spoc/agenda.html`, `static/js/pages/spoc__agenda.js`; `routes_spoc.py:1021`). An agenda saved before this gets IDs on its next save. At most 60 items.
  - **Session scans.** Both scanners have a Session mode (`templates/spoc/scan.html:176,489`; `templates/coordinator/scan.html:63,269`; the session list from `routes_spoc.py:714`, `routes_coordinator.py:716`). `POST /ticket/api/session_checkin` (`routes_ticket.py:269`) takes the same signed ticket, runs the shared event check-in first (with all its rules), then records one row per registration and session in the new `session_attendance` table (`models_pg.py:683`, migration `0012_session_attendance`; `services_sessions.attend`, `services_sessions.py:110`). A repeat says "Already in <session> since HH:MM." At capacity the scanner gets a 409 warning and staff may let the person in anyway (recorded as over capacity).
  - **My agenda.** `/participant/agenda/<event_id>` (`routes_participant.py:1010`) lists every session with a star button and "My agenda" with only the starred ones (`session_stars` table, `models_pg.py:742`); `/participant/agenda/<event_id>.ics` (`:1034`) has the starred sessions in IST converted to UTC (`services_sessions.ics`, `services_sessions.py:205`). Anyone who can see the event, or is registered, can star. The event page links to it; the ticket page links to it once the person is checked in.
  - **Hours.** When an event's sessions have hours, the ledger credits the sum of the attended sessions' hours instead of the event's; points stay the event's (`services_ledger.credit_for`, `services_ledger.py:16`; `services_sessions.session_hours`, `services_sessions.py:153`).
  - **Exports.** The registration CSV, Excel and event report have a "Session: <time> <title>" column per session with "Yes" for attended (`services_export.registration_columns`, `services_export.py:83`; `:114`).
- **Decided while building:** a session scan checks the person in to the event implicitly, through the same `check_in` as the gate, so the gate's rules (payment, event, cancelled, transferred) apply. Attendance is per registration.
- **Files touched:** `services_sessions.py` (new), `migrations/versions/0012_session_attendance.py` (new), `models_pg.py`, `routes_ticket.py`, `routes_spoc.py`, `routes_coordinator.py`, `routes_participant.py`, `services_ledger.py`, `services_export.py`, `templates/spoc/agenda.html`, `static/js/pages/spoc__agenda.js`, `templates/spoc/scan.html`, `templates/coordinator/scan.html`, `templates/participant/my_agenda.html` (new), `templates/public/_event_content.html`, `templates/participant/ticket.html`, `tests/test_sessions.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** event-level check-in unchanged. Migration 0012 must run before the new revision serves.
- **Acceptance criteria** (`tests/test_sessions.py`):
  1. ✅ A session scan records one row per person and session; a repeat says "already in" (`::test_a_session_scan_records_one_row_and_a_repeat_says_already_in`); the gate's rules still apply (`::test_a_session_scan_keeps_the_gates_rules`).
  2. ✅ A session at capacity warns the scanner (`::test_a_session_at_capacity_warns_the_scanner`).
  3. ✅ "My agenda" lists only starred sessions and its `.ics` has them (`::test_my_agenda_lists_only_starred_sessions_and_its_ics_has_them`).
  4. ✅ An FDP with per-session hours credits only attended sessions' hours (`::test_per_session_hours_credit_only_the_attended_sessions`).
  5. ✅ The export has a column per session (`::test_the_export_has_a_column_per_session`).

#### UPG-160 — Live polls and Q&A during talks
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: Whova, Zoho Backstage, Hubilo, Airmeet and Swapcard run live polls and Q&A. SapthaEvent had a projector leaderboard over SSE (`routes_live.py`) but no polls or questions.
- **Who benefits:** seminars, guest lectures, conferences, FDPs.
- **What was built:**
  - **Host.** `/interact/<event_id>/host` (`routes_interact.py:127`) for the event's check-in staff: open a single- or multiple-choice poll (2 to 8 options) for the event or one session (UPG-159), close it, see the counts; moderate questions (show, mark answered, hide); switch moderation on (`qa_moderated`, `routes_interact.py:182`), when new questions wait as pending.
  - **Attendees.** `/interact/<event_id>` (`routes_interact.py:54`): people checked in to the event (lead or member of a Present registration; `services_interact.checked_in`, `services_interact.py:42`) answer open polls once each and ask and upvote questions, one upvote each. "Once" is the database key, so two taps together count once (`live_poll_votes`, `live_question_votes`; `models_pg.py:697-740`, migration `0013_live_polls`). The ticket page links to it when the person is checked in.
  - **Projector.** `/interact/<event_id>/screen` (`routes_interact.py:194`), full screen, updated over SSE every 3 s like the live leaderboard (`/stream`, `:208`; `static/js/pages/interact__screen.js` sets `textContent` only). Pending and hidden questions never reach it (`ON_SCREEN`, `services_interact.py:26`).
  - **Report.** The event report has a Polls sheet (poll, option, answers, % of those who answered, people who answered; `services_export.py:209,249`).
- **Decided while building:** voting needs an event check-in; a session's poll doesn't need a scan into that session. The host and the projector need `check_in` on the event.
- **Files touched:** `services_interact.py` (new), `routes_interact.py` (new), `migrations/versions/0013_live_polls.py` (new), `models_pg.py`, `app.py`, `services_export.py`, `templates/interact/attendee.html`, `templates/interact/host.html`, `templates/interact/screen.html` (new), `static/js/pages/interact__screen.js` (new), `templates/participant/ticket.html`, `templates/spoc/dashboard.html`, `templates/coordinator/dashboard.html`, `tests/test_live_polls.py` (new).
- **Effort:** M · **Depends on:** UPG-159 (DONE) for per-session polls · **Risk:** all text escaped (BLK-19). Migration 0013 must run before the new revision serves.
- **Acceptance criteria** (`tests/test_live_polls.py`):
  1. ✅ Only checked-in attendees vote, once each; counts are right (`::test_only_checked_in_attendees_vote_once_each_and_counts_are_right`); only the event's staff host (`::test_only_the_events_staff_host`).
  2. ✅ An upvote counts once per person; hidden and pending questions don't show on the projector (`::test_an_upvote_counts_once_and_hidden_questions_stay_off_the_projector`).
  3. ✅ A question with `<script>` shows as text on every page and the projector (`::test_a_question_with_a_script_shows_as_text`).
  4. ✅ The event report includes poll results (`::test_the_event_report_includes_poll_results`).

#### UPG-161 — Transfer a ticket to someone else
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: KonfHub, Luma and Ticket Tailor let a holder transfer a ticket. SapthaEvent had cancellation and refunds (UPG-30, UPG-51) but no transfer.
- **Who benefits:** participants who can't attend; organisers who keep the seat filled.
- **What was built:**
  - **Settings.** Off by default per event; the wizard's "Ticket transfers" box sets `transfers_allowed` and `transfer_cutoff_hours` (default 24, 0 to 720; `services_event_types.py:484,658`; `templates/spoc/create_event.html`).
  - **The page.** `/participant/transfer/<reg_id>` (`routes_participant.py:1048`), linked from the ticket page for the lead (`templates/participant/ticket.html:406`). It's open only when the event allows transfers, the person is the registration's lead, the registration is confirmed, the ticket wasn't used at the entrance and it's before the cut-off (`services_transfer.open_for`, `services_transfer.py:56`). Team members see why they can't; anyone else gets 403.
  - **The recipient** must have an account, so the checks use their own profile (`check_recipient`, `services_transfer.py:85`): a valid email, not one's own, not already registered, a participant type the event takes (campus-only stays on campus), placement eligibility, the ticket type open to them, and a fee no higher than the ticket's ("They would pay Rs X…"). Refusals are shown as they are.
  - **The transfer** (`transfer`, `services_transfer.py:128`): the lead fields and the lead's member entry become the recipient's (a team keeps its other members and name), `transfers` keeps the history, and `ticket_gen` goes up by one. Both people are emailed (`notify`, `:158`); audit-logged as TICKET_TRANSFERRED.
  - **The old ticket stops working.** The ticket token carries the generation once it isn't 0, so an untransferred ticket's token is exactly what it was (`generate_ticket_token`, `ticket_token_for`, `token_is_current`; `routes_ticket.py:42-65`). The shared check-in refuses an older generation with 409 "transferred" and logs CHECKIN_REFUSED (`routes_ticket.check_in`, `routes_ticket.py:153`); the verify page and API refuse it too (`routes_ticket.py:607,766`). Every place that makes a ticket token uses `ticket_token_for`, including the emailed ticket (`tasks/email_tasks.py`), the wallet passes (UPG-156) and the badges (UPG-158).
- **Decided while building:** a recipient who would pay more is refused rather than charged the difference (no partial payments in the flow). The registration keeps its ID, payment and refund record.
- **Not covered:** the separate `tickets` record made by `TicketService` (waitlist promotions) keeps the old holder: UPG-189.
- **Files touched:** `services_transfer.py` (new), `routes_ticket.py`, `routes_participant.py`, `services_event_types.py`, `tasks/email_tasks.py`, `templates/participant/transfer.html` (new), `templates/participant/ticket.html`, `templates/spoc/create_event.html`, `tests/test_ticket_transfer.py` (new).
- **Effort:** M · **Depends on:** none · **Risk:** a transfer can't dodge eligibility or price (refused, above).
- **Acceptance criteria** (`tests/test_ticket_transfer.py`):
  1. ✅ After a transfer the old ticket is refused at check-in, the verify page and API, and the new one is accepted (`::test_after_a_transfer_the_old_ticket_is_refused_and_the_new_one_works`).
  2. ✅ An ineligible recipient (campus-only, placement rules, no account, already registered, oneself) is refused (`::test_an_ineligible_recipient_is_refused`), and so is one who would pay more (`::test_a_recipient_who_would_pay_more_is_refused`).
  3. ✅ A transfer after the cut-off or on an event without transfers is refused (`::test_after_the_cut_off_or_without_transfers_it_is_refused`); the wizard saves the settings (`::test_the_wizard_saves_the_transfer_settings`).
  4. ✅ Team members can't transfer the team's registration; only the lead can (`::test_only_the_lead_transfers_a_team_registration`).

#### UPG-162 — Where registrations come from: tracked share links
- **Status:** DONE
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (with UPG-152's uncommitted work) [T]
- **Problem:** Market: Luma's Event Insights and KonfHub's referral contests show which channel brought each registration. SapthaEvent recorded no source (no `utm_` handling); referrals are hidden on purpose (UPG-105).
- **Who benefits:** organisers and the Super Admin (which promotion works), NAAC/impact reports.
- **What was built:**
  - **Links.** `/spoc/event/<event_id>/share` (`routes_spoc.py:2494-2525`; `templates/spoc/share_links.html`), linked from the SPOC dashboard: organisers name links (a code is made from the name, or given: lowercase letters, digits, `-`, `_`, up to 32; at most 30) stored on the event as `share_links` (`services_share.add_link`, `services_share.py:40`). Each is `/event/<id>?src=<code>` with a poster QR PNG (`routes_spoc.py:2528`). Seeing needs `view_analytics`; adding and removing need `edit_event`.
  - **Capture.** The event page and the registration form read `src`, else `utm_source` (`app.py:909`; `routes_forms.py:561`; `services_share.capture`, `services_share.py:74`), and keep the code in the session for that event; the form carries it in a hidden `src` field (`templates/public/registration_form.html:270`), so it survives the form's Back, an error resubmission and a lost session. On submit the code is checked again against the event's links and stored on the registration as `source` (`routes_forms.py:819-822`; `for_submission`, `services_share.py:93`); it rides inside the registration data through payment and the waitlist.
  - **Only the code.** A code the event doesn't know is stored as "other"; a visit without one stores nothing (direct). Visits are a count per link, one per browser session per event, in the new `source_visits` table (`models_pg.py:753`, migration `0014_source_visits`; `record_visit`, `services_share.py:102`), written on the primary database even during a GET (`db_pg.get_session(primary=True)`, `db_pg.py:258`).
  - **Sources table.** Per link, then removed links still on registrations, "Other" and "Direct": visits, registrations (cancelled, refunded and rejected left out) and conversion (registrations per visit), with a bar (`services_share.report`, `services_share.py:128`). Every label and code is escaped.
- **Decided while building:** a removed link's registrations keep their code and are listed as "(link removed)"; new visits with it become "other". Direct visits aren't counted (no write on every page view), so direct conversion shows "—".
- **Files touched:** `services_share.py` (new), `migrations/versions/0014_source_visits.py` (new), `models_pg.py`, `db_pg.py`, `app.py`, `routes_forms.py`, `routes_spoc.py`, `templates/spoc/share_links.html` (new), `templates/public/registration_form.html`, `templates/spoc/dashboard.html`, `tests/test_share_sources.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** no third-party trackers; only the code is stored (DPDP). Migration 0014 must run before the new revision serves.
- **Acceptance criteria** (`tests/test_share_sources.py`):
  1. ✅ A registration that started from `?src=poster` is stored with that source, also after the form's Back, after an error resubmission, with only the hidden field, and through payment; `utm_source` is read; a direct visit has none (`::test_a_registration_from_the_poster_keeps_its_source_also_after_back`, `::test_a_paid_registration_keeps_its_source_through_payment`).
  2. ✅ The table counts visits (once per session), registrations (not cancelled ones) and conversion per source; the QR is a PNG; a removed link stays counted (`::test_the_sources_table_counts_registrations_and_visits_per_source`); only the event's organisers see and change links (`::test_only_the_events_organisers_see_and_change_the_links`).
  3. ✅ An unknown code, including `<script>` and a forged hidden field, is stored as "other"; nothing a visitor or organiser types reaches the page as HTML (`::test_an_unknown_code_is_other_and_cant_inject_html`).

### Hackathon, Phase 1 (owner, 2026-11-05: a Hack2skill-style flow)

The owner's request: the SPOC creates the hackathon without problem statements and adds them later; registered teams see them on the portal; the SPOC builds the submission form, with a deadline that can be extended; participants get one email at registration (join the WhatsApp group, check the portal), the password emails, and the final result to the lead; everything else is a portal update; the login page shows Admin, SPOC, Event coordinator, Judge and Student. Phase 1 is UPG-190, UPG-191, UPG-195, UPG-196 and UPG-197; Phase 2 (AI scoring, the shortlist, the finale and the deploy) is UPG-192 to UPG-194, UPG-198 and UPG-199.

Defaults chosen in Phase 1 (each one can be changed; listed in the changelog): "Admin" on the login page is the Super Admin; the registration email goes to the lead only; each team picks one problem statement; portal mode is the default for every hackathon and the SPOC can switch it per event; a deadline extension adds time to the current deadline, for the whole event, and works after the deadline has passed if the new deadline is in the future; the page refreshes by a 60-second poll, not SSE.

#### UPG-197 — The login page offers five roles
- **Status:** DONE
- **Last verified:** 2026-11-05, uncommitted on `57a5922` (with the uncommitted UPG-152 to UPG-162 work) [T]
- **Problem:** The login page's role menu listed eight roles. The owner wants Admin, SPOC, Event coordinator, Judge and Student. Volunteer, IQAC coordinator and Department admin accounts exist and must still be able to log in (`tests/test_volunteer_login.py`, `tests/test_reach_and_reports_phone.py`).
- **What was built:** the menu shows Admin (`SuperAdmin`), SPOC, Event coordinator, Judge and Student; the three other roles sit in a hidden `<optgroup id="otherRoles">` that an "Other staff role" link under the menu reveals (`templates/login.html:117-125`; `static/js/pages/login.js:84-93`, no inline script). Role values and the login handler are unchanged.
- **Files touched:** `templates/login.html`, `static/js/pages/login.js`, `tests/test_hackathon_portal.py` (new).
- **Effort:** S · **Depends on:** none · **Risk:** whether every phone browser hides an `<optgroup hidden>` is checked in UPG-198.
- **Superseded in part (2026-11-06):** Safari showed the hidden group; the owner asked for the five roles only, and UPG-204 removed the group, the link and the script.
- **Acceptance criteria** (`tests/test_hackathon_portal.py`, real database layer):
  1. ✅ The visible options are exactly Admin, SPOC, Event coordinator, Judge and Student; Volunteer, IQAC coordinator and Department admin are in the hidden group, revealed by the link's script; SPOC, coordinator, judge, student, volunteer and IQAC accounts log in through `/login` (`::test_the_login_page_offers_five_roles_and_hides_the_older_staff_roles`). The Super Admin login (secret key) is covered unchanged by `tests/test_volunteer_login.py`.

#### UPG-195 — A hackathon emails participants twice: registration and the result
- **Status:** DONE
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [T]
- **Problem:** Since UPG-152 a hackathon registration is one email to the lead, but every later step still emailed: the day-before ticket and the 3-day reminder, round results, room assignments, the SPOC's blast and the coordinator's broadcast, certificates, waitlist and transfer notices, feedback requests, change notices and team join confirmations. The owner wants one email at registration (with "join the WhatsApp group" and "check the portal"), the password emails, and the final result to the team lead; the rest on the portal.
- **What was built:**
  - **An email mode per event:** `portal` (the default for a hackathon) or `all` (every other event type, unchanged), stored as the event's `participant_emails`; the SPOC switches it on the hackathon page (`services_hackathon.email_mode`, `email_allowed`, `email_allowed_for`, `services_hackathon.py:63-90`; `PORTAL_MODE_EMAILS` = registration, password, result, `:31`; `/spoc/hackathon/<id>/emails`, `routes_hackathon.py:478`, audit line `HACKATHON_EMAIL_MODE`).
  - **The registration email carries the instructions:** the WhatsApp group link (`contact.group_link`, as set in the wizard), the hackathon page's address with "We won't email them", "log in as Student; only the team lead submits", and that only a password reset and the final result follow (`utils_email._instructions_block`, `utils_email.py:543`; in the new-account email at `:838` and the existing-account confirmation at `:603`; `services_hackathon.registration_instructions`, `services_hackathon.py:113`; `routes_forms.py:963-983`; the legacy `/register`, `routes_participant.py:575`).
  - **Gated senders, each replaced by a portal notice or an update on the hackathon page:** the day-before ticket (`tasks/scheduled_tasks.py:99-103`; push and WhatsApp unchanged) and 3-day reminder (`:310-313`); round results (`services_rounds.py:214-226`); room assignments (`routes_spoc.py:1829`, `routes_coordinator.py:387`); the SPOC blast (`routes_spoc.py:1244`) and the coordinator broadcast (`routes_coordinator.py:451`); a walk-in's ticket (`routes_coordinator.py:638`); certificates (`services_certificates.py:645`, the certificate stays in the portal); feedback requests to attendees (`services_impact.py:211`, the organiser still gets theirs); waitlist (`routes_waitlist.py:324`) and transfer (`services_transfer.py:162`) notices; change notices from the automation engine (`services_automation.py:199-206`); team join confirmations and member emails (`routes_teams.py:154`, `routes_forms.py:983`).
  - **Still emailed:** forgot-password and set-password (UPG-152), and the final result to the team lead (`routes_coordinator.publish_results`, unchanged).
- **Not covered:** a paid hackathon still emails the ticket and receipt after payment (UPG-201). The final-results email itself is reworked in UPG-194.
- **Files touched:** `services_hackathon.py` (new), `utils_email.py`, `routes_forms.py`, `routes_participant.py`, `routes_teams.py`, `services_rounds.py`, `tasks/scheduled_tasks.py`, `routes_spoc.py`, `routes_coordinator.py`, `services_certificates.py`, `services_impact.py`, `services_transfer.py`, `routes_waitlist.py`, `services_automation.py`, `services_venue.py` and `services_workflow.py` (pass `event_id` to the automation context), `tests/test_hackathon_portal.py`.
- **Effort:** M · **Depends on:** UPG-152 (DONE) · **Risk:** an event switched to `all` mid-way sends the later emails again; the switch is the SPOC's.
- **Acceptance criteria** (`tests/test_hackathon_portal.py`, real database layer, `_send` recorded):
  1. ✅ A new account's registration sends one email, to the lead, with the WhatsApp link, the hackathon page and the set-password link; an existing account gets one confirmation with the same instructions and no ticket line; members get none (`::test_a_hackathon_registration_is_one_email_with_the_whatsapp_and_portal_instructions`).
  2. ✅ Advancing a round sends no email; each team gets a portal notice and the page shows "Round 1 results are out" (`::test_round_results_in_portal_mode_are_portal_notices_not_emails`).
  3. ✅ The day-before and 3-day jobs, the SPOC's blast and certificate delivery send nothing for the hackathon and still send for a workshop; the blast appears on the hackathon page; the gate refuses every other kind (ticket, reminder, round, broadcast, room, certificate, team, waitlist, feedback, transfer, change) and allows registration, password and result (`::test_portal_mode_sends_no_ticket_reminder_broadcast_certificate_or_waitlist_email`).
  4. ✅ Forgot-password still emails the lead; published results email the lead (`::test_forgot_password_and_the_result_still_email_the_lead`).
  5. ✅ The SPOC switches the mode; another SPOC gets 403; a workshop is `all` (`::test_the_spoc_switches_the_email_mode_and_others_cant`).

#### UPG-190 — Problem statements added after registration, released now or at a set time
- **Status:** DONE
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [T]
- **Problem:** A hackathon's problem statements had to be in the event when it was created (themes in the wizard, UPG-73). The owner creates the hackathon first and publishes the statements later, to registered teams only.
- **What was built:**
  - **The SPOC's hackathon page** `/spoc/hackathon/<id>` (`routes_hackathon.py:367`; `templates/hackathon/manage.html`), linked from the SPOC dashboard (`templates/spoc/dashboard.html:1788`); every SPOC route needs `edit_event` on that event (`_managed`, `routes_hackathon.py:360`).
  - **Statements** with a title, description, optional track and an optional PDF (checked as a PDF by its first bytes, up to 10 MB, in private storage under `hackathon/<event>/problems/`); released now or at a time in the event's timezone (stored in UTC; a past time is refused) (`add_problem`, `services_hackathon.py:246`). A scheduled statement shows itself when the clock passes its time, with no job (`is_released`, `:219`); "Release now" (`:283`); a released statement can't be removed (`:300`). Each release posts an update on the hackathon page.
  - **Teams see them** on their hackathon page (UPG-196) once released, with "released on …" for the next one; the PDF opens for staff and, after release, for registered teams only (`problem_pdf`, `routes_hackathon.py:322`).
- **Files touched:** `services_hackathon.py`, `routes_hackathon.py`, `templates/hackathon/manage.html` (new), `templates/hackathon/portal.html` (new), `static/js/pages/hackathon__manage.js` (new), `templates/spoc/dashboard.html`.
- **Effort:** M · **Depends on:** none · **Risk:** statements live on the event document (`extra_json`), no migration; capped by the UI, not the database.
- **Acceptance criteria** (`tests/test_hackathon_portal.py`):
  1. ✅ A statement released now shows to a registered team and on the updates; a scheduled one doesn't until the clock passes its time (IST input stored as UTC); the PDF opens for the team and the SPOC, 403 for a student who isn't registered, who also gets no page (`::test_problem_statements_show_to_registered_teams_only_after_release`).
  2. ✅ A scheduled statement's PDF is 403 before release and "Released on" shows; "Release now" releases it; a released one can't be removed; a non-PDF, a past time and an empty title are refused (`::test_a_scheduled_pdf_is_refused_before_release_and_released_ones_cant_be_removed`).
  3. ✅ Another SPOC gets 403 on the page and on every action, and nothing changes (`::test_another_spoc_cant_manage_the_hackathon`).

#### UPG-191 — A submission form the SPOC builds, with a server-enforced window and deadline extensions
- **Status:** DONE
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [T]
- **Problem:** The project submission page had fixed fields, no opening or closing time, let any team member submit, and found the student's registration by streaming every registration in the database (`routes_hackathon.py:20-100` at `57a5922`). The owner wants a form the SPOC designs, open between two times, editable until the deadline, and a way to extend the deadline (owner, 2026-11-05: "extend deadline by some time").
- **What was built:**
  - **The form builder** on the SPOC's page: up to 15 fields of five kinds (short text, long text, link, PDF upload with its own size limit up to 25 MB, the problem statement picked), each with a label, help and required; at most one problem field; opens and closes in the event's timezone (`parse_fields`, `save_form`, `services_hackathon.py:350,387`; `hackathon__manage.js` adds rows from a `<template>`). Saving posts "Submission form published", or "Submission deadline changed" when the closing time moves.
  - **Submitting** from the hackathon page: only the team lead, only while the window is open on the server's clock (before opening and from the deadline on, a direct POST is refused and nothing is saved), a team that has been eliminated can't; every field validated (required, length, `http(s)` links only, a real PDF within its limit, a released problem); PDFs in private storage under `hackathon/<event>/submissions/<reg>/`; resubmitting replaces the answers and keeps a PDF when no new file is sent; `versions`, `updated_at` and `last_edited_by` kept (`submit`, `services_hackathon.py:485`; `/hackathon/<id>/submit`, `routes_hackathon.py:292`). Files open for the team and staff only (`routes_hackathon.py:335`).
  - **Deadline extensions:** 15 minutes, 30 minutes, 1, 2, 6 or 12 hours, 1 day, or a custom hours-and-minutes, up to 7 days, with an optional reason; added to the current deadline, and allowed after it has passed if the new deadline is in the future; the whole event gets it; each one is kept in a history on the SPOC's page, posted as "Deadline extended by …" with the new time on the teams' page, and audit-logged as `HACKATHON_DEADLINE_EXTENDED` (`extend_deadline`, `services_hackathon.py:415`; `EXTENSION_CHOICES`, `:45`; `/spoc/hackathon/<id>/extend`, `routes_hackathon.py:445`).
  - **The SPOC sees the submissions** with each answer and file on the same page.
  - **The old page** sends a team to the hackathon page once the SPOC has a form (`routes_hackathon.py:39`) and, without one, finds the student's registration and submission by query, not by streaming everything (`:43,61`).
- **Files touched:** `services_hackathon.py`, `routes_hackathon.py`, `templates/hackathon/manage.html`, `templates/hackathon/portal.html`, `static/js/pages/hackathon__manage.js`.
- **Effort:** M · **Depends on:** UPG-190 · **Risk:** submissions use `project_submissions` with answers in `extra_json`; no migration.
- **Acceptance criteria** (`tests/test_hackathon_portal.py`):
  1. ✅ The SPOC builds a form with all five kinds and IST times stored as UTC; the lead submits and edits before the deadline (the PDF kept, two versions, one submission); the PDF opens for the team and the SPOC, 403 for another team's lead; the SPOC's page lists it (`::test_the_spoc_builds_a_form_and_the_lead_submits_and_edits_until_the_deadline`).
  2. ✅ Before opening and at the deadline a POST is refused and nothing is saved; the page says submissions are closed and shows no form (`::test_the_server_refuses_submissions_before_opening_and_after_the_deadline`).
  3. ✅ A missing required answer, a `javascript:` link, a non-PDF, a PDF over its limit, an unreleased problem and an over-long title each save nothing (`::test_bad_answers_are_refused_and_nothing_is_saved`).
  4. ✅ A team member who isn't the lead gets 403; an eliminated team's lead saves nothing (`::test_only_the_team_lead_submits`).
  5. ✅ After the deadline, a 15-minute extension that still ends in the past is refused; a 2-hour one lets the late team submit and shows "Deadline extended by 2 hours" with its reason on the page; a custom 1 h 30 min adds to it; 0, negative, over 7 days and non-numbers are refused; after the new deadline the POST is refused again (`::test_the_spoc_extends_the_deadline_and_late_teams_can_submit_again`).
  6. ✅ Another SPOC gets 403 on the form and the extension (`::test_another_spoc_cant_manage_the_hackathon`).
  7. ✅ With a form, the old page redirects to the hackathon page; the page, the submit and the old page without a form read no unfiltered `registrations` or `project_submissions` stream (`::test_the_submit_page_reads_one_event_not_every_registration`).

#### UPG-196 — The student's hackathon page
- **Status:** DONE
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [T]
- **Problem:** With email reduced to two messages (UPG-195), a team needs one place that shows where the hackathon is, what's next and what changed.
- **What was built:** `/hackathon/<id>` for a registered team (`routes_hackathon.py:263`; `templates/hackathon/portal.html`): the WhatsApp join link, a stage tracker (registration, problem statements, submission, shortlist, finale, results; done, current or upcoming from the clock and the event, `stages`, `services_hackathon.py:607`) with live countdowns to the next release and the deadline, the team (lead and members), the updates feed, the problem statements and the submission form. Staff are sent to the SPOC page; a student who isn't registered is sent to the event page. The page polls `/hackathon/<id>/state` every 60 seconds and reloads when its version (a hash of what the page shows, `page_version`, `:670`) changes and nobody is typing; a countdown reaching zero reloads it (`static/js/pages/hackathon__portal.js:36,53`). No SSE, so no long-held connections on Cloud Run. The lead's dashboard links to the page (`routes_participant.py:112`; `templates/participant/dashboard.html:320`). Everything shown is escaped.
- **Files touched:** `routes_hackathon.py`, `services_hackathon.py`, `templates/hackathon/portal.html` (new), `static/js/pages/hackathon__portal.js` (new), `routes_participant.py`, `templates/participant/dashboard.html`.
- **Effort:** M · **Depends on:** UPG-190, UPG-191, UPG-195 · **Risk:** a poll a minute per open page: 500 teams with the page open are about 8 requests a second, each a few reads.
- **Acceptance criteria** (`tests/test_hackathon_portal.py`):
  1. ✅ The stages move as the clock passes the release, the opening and the deadline, and after round 2 starts and results are published; the countdowns point at the next release and the deadline (`::test_the_page_tracks_the_stages_as_time_passes`).
  2. ✅ The page shows the WhatsApp link, the lead and members and the SPOC's updates, escaped; the lead's dashboard links to it (`::test_the_page_shows_the_whatsapp_link_team_and_updates`).
  3. ✅ The state version stays the same until an update or an extension changes it; a student who isn't registered gets 403; the script polls every 60 seconds and uses no EventSource (`::test_the_page_polls_a_version_that_changes_only_when_something_does`).

### Owner changes after the Safari check (2026-11-06)

#### UPG-204 — The login menu has the five roles only
- **Status:** DONE
- **Last verified:** 2026-11-06, uncommitted on `57a5922` [T]
- **Problem:** UPG-197 put Volunteer, IQAC coordinator and Department admin in a hidden group behind "Other staff role", and UPG-198's script took the group out of the menu for iOS Safari. On the owner's Mac, Safari still listed the three, indented under the five. The owner: "for time being only keep 5 roles remove rest".
- **What was built:** the menu is "Choose your role…", Admin, SPOC, Event coordinator, Judge and Student; the `<optgroup>`, the "Other staff role" button and the script that moved the group are gone (`templates/login.html:108-117`; `static/js/pages/login.js`, the block removed). The login handler is unchanged (`routes_auth.py:34-45`), so a Volunteer, IQAC coordinator or Department admin login still works when that role is posted, but nobody can choose it on the page.
- **Consequence the owner accepted "for the time being":** volunteer, IQAC coordinator and department admin accounts can't log in through the page until the options come back (put the three `<option>`s back in `templates/login.html`).
- **Tests changed to the new requirement** (each with a comment naming UPG-204): `tests/test_hackathon_portal.py::test_the_login_page_offers_only_five_roles` (was `…_and_hides_the_older_staff_roles`); `tests/test_volunteer_login.py::test_the_login_form_offers_the_five_roles_the_owner_chose` (UPG-120 had asserted the Volunteer option; the volunteer login, landing and scope tests are unchanged and pass); `tests/test_naac.py::test_the_super_admin_assigns_the_two_roles_and_they_land_on_naac` (its last line asserted "IQAC coordinator" on the login page; now that it isn't); `tests/test_hackathon_browser.py` (the login step); `tests/test_phone_journey.py::_login_in_browser` (for the three roles it adds the option and posts the same form, as a direct post would).
- **Files touched:** `templates/login.html`, `static/js/pages/login.js`, the five test files above.
- **Effort:** S · **Depends on:** none · **Risk:** the three roles' users are locked out of the page (accepted).
- **Acceptance criteria:**
  1. ✅ The menu's options are exactly the placeholder and the five roles, with no group, button or script for others (`tests/test_hackathon_portal.py::test_the_login_page_offers_only_five_roles`; in Chromium, `tests/test_hackathon_browser.py::test_the_hackathon_pages_work_and_fit_a_phone_and_a_desktop`).
  2. ✅ The five log in through `/login`; a volunteer and an IQAC coordinator still log in when the role is posted (same test; `tests/test_volunteer_login.py::test_a_volunteer_logs_in_and_lands_on_the_scanner`; `tests/test_reach_and_reports_phone.py`).

#### UPG-205 — No AI chat widget on the home page
- **Status:** DONE
- **Last verified:** 2026-11-06, uncommitted on `57a5922` [T]
- **Problem:** The owner asked to "remove the ai agent from home screen". The home page had a floating "Sparky — AI Assistant" button and chat window, and an "Ask Sparky" prompt after 2 seconds.
- **What was built:** removed from `templates/index.html` the widget (now a comment, `:848`), its prompt-bubble styles and "AI Assistant" in the JSON-LD features (`:270`); from `static/js/pages/index.js` `initChatPrompt`, `dismissChatPrompt`, `toggleChat`, `sendChat`, `addBubble`, `addTyping`; from `static/js/handlers/index.js` handlers `index:55` to `index:59`. The `/chatbot/ask` route and its tests stay; the shared `.chat-*` styles in `static/css/global.css` are unused but left.
- **Files touched:** `templates/index.html`, `static/js/pages/index.js`, `static/js/handlers/index.js`, `tests/test_hackathon_portal.py`, `tests/test_hackathon_browser.py`.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. ✅ The home page has no chat button, window, prompt or "Sparky", and its scripts no chat code (`tests/test_hackathon_portal.py::test_the_home_page_has_no_ai_chat_widget`).
  2. ✅ In Chromium the home page shows no widget after 2.5 seconds, has no script error and fits 375 and 1280 (`tests/test_hackathon_browser.py::test_the_hackathon_pages_work_and_fit_a_phone_and_a_desktop`).

### Own certificate design and team members' logins (owner, 2026-11-09)

#### UPG-206 — The organiser's own certificate design, with the name placed on it
- **Status:** DONE
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T]
- **Problem:** Certificates were drawn only in the app's two built-in styles (`certificate_pdf.STYLES`, `render`) with the college's branding and the event's signatories (UPG-123). Colleges usually have a designed certificate with logos, borders and signatures already printed; there was no way to upload it and have the app write only each name. Issuing also needed a signatory with a signature (`services_certificates.require_signatories`), which a finished design doesn't need.
- **What was built:**
  - **Upload** on the event's certificate page (`templates/certificates/manage.html:97`, card "Your own certificate design"): PNG, JPG or a one-page PDF (first page drawn with `pypdfium2`), at most 5 MB, A4 landscape or portrait within 2%; other shapes are refused with the needed shape and the best size (3508 × 2480 px); below 2000 px on the long side a "may print blurry" warning. Normalised once (flattened on white, at most 3508 px, JPEG) and stored privately (`services_certificate_design.process` `:75`, `upload` `:170`; `put_private`), served only to `edit_event` or `issue_certificates` (`routes_certificates.py:301`, `private, no-store`). Routes `:259` (upload), `:277` (settings), `:290` (remove), all `edit_event`.
  - **Placing the name:** the design as a stage with a box per field; drag to move, drag the right edge for the width, or type the values (`static/js/pages/certificates__design.js`). Distance from the top and left and the width are percentages of the page; font size in points (default 40), colour (hex), left/centre/right (default centre), bold (default). Optional boxes, off by default: team name, USN, college (`parse_fields` `:144` clamps every value).
  - **Text and QR:** Noto Sans with Kannada and Devanagari shaping as before; a name wider than its box shrinks to 60% of the size, then goes onto two lines (`certificate_pdf.fit_box` `:287`); every value drawn as text. The number and a QR to `/verify/<number>` in the corner chosen (default bottom right), on a white panel with the number under it (`qr_box` `:307`, `render_design` `:316`).
  - **Preview:** a live PNG with the longest registered name (a sample name if none) and sample values for the optional boxes (`routes_certificates._sample_values` `:98`).
  - **Issuing:** the design covers the event's attendance certificate, i.e. participation, or completion / extension for workshops, FDPs and NSS events (`services_certificate_design.covers` `:128`, `services_certificates.attendance_type`); for that type no signatory is needed (`can_issue_type` `services_certificates.py:554`, `require_signatories` `:562`, `services_certificate_runs.ready_to_issue` `:49`, `issue_event` `:723`). Other types keep the built-in templates and still need a signatory, with the same message. The design, its settings and its SHA-256 are snapshotted into each certificate (`_design_snapshot` `:453`, `snapshot` `services_certificate_design.py:212`); a later change affects only later certificates; the old file is kept. `CERT_DESIGN_UPLOADED`, `_CHANGED`, `_REMOVED` audit-logged.
  - **Difference from the item text:** the item said "participation certificates"; the design is used for whichever certificate everyone who attended gets (participation at most events), so a workshop's completion certificate can use it too.
- **Files touched:** `services_certificate_design.py` (new), `certificate_pdf.py`, `services_certificates.py`, `services_certificate_runs.py`, `routes_certificates.py`, `templates/certificates/manage.html`, `static/js/pages/certificates__design.js` (new), `tests/test_certificate_design.py` (new).
- **Effort:** M · **Depends on:** UPG-122 to UPG-126 (DONE) · **Risk:** low to medium.
- **Acceptance criteria:**
  1. ✅ Only `edit_event` uploads, changes or removes (another SPOC, a student and a coordinator 403); a GIF, a 6 MB file, a two-page PDF and a square image refused with their messages; an A4 PNG, JPG and one-page PDF accepted; the stored file 403 for another SPOC and a student (`tests/test_certificate_design.py::test_only_editors_upload_bad_files_are_refused_and_the_design_is_private`).
  2. ✅ Settings are percentages; a 3508 px and a 1754 px copy put the name within 1 mm (`::test_settings_are_percentages_and_place_the_name_alike_at_any_image_size`).
  3. ✅ The PDF's text holds the name, the number and the team; a 120-character name stays in its box; markup printed as text; a Kannada name in the Kannada font; the QR encodes `BASE_URL/verify/<number>` in the chosen corner (`::test_the_pdf_says_who_with_the_team_number_and_a_qr_in_its_corner`).
  4. ✅ With a design and no signatories participation certificates are issued; a winner certificate still needs a signatory (`::test_the_design_needs_no_signatory_but_other_types_still_do`).
  5. ✅ Certificates issued before a change keep the old design; later ones the new; each change audit-logged (`::test_issued_certificates_keep_their_design_and_changes_are_audited`).
  6. ✅ The preview uses the longest registered name, else a sample (`::test_the_preview_uses_the_longest_registered_name`).
  7. ✅ Headless Chromium at 1280 and 375 px: no sideways scroll; dragging changes the saved values; typing moves the box (`::test_the_placement_page_fits_and_dragging_or_typing_moves_the_box`).

#### UPG-207 — Team members confirm their email and get their own portal login
- **Status:** DONE
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T]
- **Problem:** The lead types each member's name and email; only the lead got an account and a set-password link, members got no email (unless `NOTIFY_TEAM_MEMBERS`) and no account, and nobody checked a typed email. Every member gets a certificate under their email, but "My certificates" needs a signed-in account, and portal mode sends no certificate email: a hackathon member's certificate was made but they couldn't see it.
- **What was built** (`services_team_confirm.py`, new):
  - **One email per member** after the team registers: the free form (`routes_forms.py:985`), the older form (`routes_participant.py:592`) and after paying (`routes_payment.py:496`), via `after_registration` (`:244`, never fails a registration). "<Lead> added you to team <team> for <event>": "Confirm and set your password", or "Sign in to confirm" for an existing account (`utils_email.send_member_confirm_email` `:875`). A member without an account gets an unverified one first, never a second one (`_ensure_account` `:197`). The kind `member_confirm` is allowed in portal mode (`services_hackathon.PORTAL_MODE_EMAILS` `:32`); counted against the daily limit, `'limit'` when held back (`send` `:208`).
  - **The link:** signed, 48 hours, carrying the registration, the email and a nonce kept on the member; a resend or an email correction replaces the nonce, so older links say "no longer works" (`make_token` `:116`, `load_token` `:120`). `/teams/confirm/<token>` (`routes_teams.py:235`): a new account sets a password (same strength rule; the set-password page with its own heading) and is signed in; an existing account confirms when signed in as that email, otherwise goes to `/login?next=…`; signed in as someone else, it says so. Confirming stores `confirmed_at` and `confirmed_by` (`confirm` `:313`). Invite-code joiners are confirmed when they join (`routes_teams.py:143`).
  - **Saving a member's state** locks the registration row and rewrites only that member on the SQL layer, as `_add_member` does (`update_member` `:145`).
  - **The lead's team page** (`templates/teams/view.html:22`, `routes_teams.py:181`): Confirmed / Waiting (or held back, failed, not sent) per member; while waiting, "Resend link" (3 in 24 hours, `resend` `:264`) and "Correct the email" (`correct_email` `:285`): a new link to the new address, the old link stops; refused once confirmed, or once a certificate was issued to that email (the message points to the organiser). Both audit-logged (`TEAM_CONFIRM_EMAIL`, `TEAM_MEMBER_EMAIL_CORRECTED`); others get 403 (`routes_teams.py:199`, `:217`).
  - **Organisers** (`routes_coordinator.py:159`, `templates/coordinator/registrations.html:22`): each member's status under the team; a count of waiting and held-back members; "Send confirmation links to waiting members" (`send_member_links` `:226`, `send_waiting` `:321`) sends to each waiting member not yet sent a link (earlier teams, held back or failed), so a second press sends nothing more; "Turn off / Turn on" for the event (`switch_member_confirm` `:257`, `edit_event`). The export's Members cell adds " [Confirmed]" or " [Waiting]" after "Name (USN)" (`services_export.py:89`, `:121`), keeping `Ticket Type` the last column.
  - **Switch:** `member_confirm` on the event, on unless set False, for team events only (`enabled` `:67`). Off, members get nothing, as before.
  - **Differences from the item text:** the button is on the event's registrations page (`/coordinator/registrations/<id>`), next to UPG-152's login-email column, not the event page. With `NOTIFY_TEAM_MEMBERS` on, members still also get the "Registration Confirmed" email (UPG-48), so they get two; with it off (the default) the link is their only email.
- **Tests changed to the new requirement** (each with a comment naming UPG-207): `tests/test_hackathon_portal.py::test_a_hackathon_registration_is_one_email_with_the_whatsapp_and_portal_instructions` now expects the lead's one email and then exactly one confirmation link to the member (it had asserted the lead's email only); `tests/test_low_email_auth.py::test_a_new_team_registration_sends_one_email_to_the_lead_only` and `::test_team_members_get_emails_only_when_the_owner_turns_it_on` switch member confirmation off for their event and keep every assertion (they test the switched-off path). `tests/test_hackathon_rehearsal.py::test_ten_teams_run_the_whole_hackathon_with_two_emails_each` (UPG-198) had asserted members get no email: it now checks the leads' emails exactly as before, and that each member gets exactly one email in the whole run, the confirmation link with no WhatsApp link (30 emails in all, was 20).
- **Files touched:** `services_team_confirm.py` (new), `utils_email.py`, `services_hackathon.py`, `routes_forms.py`, `routes_participant.py`, `routes_payment.py`, `routes_teams.py`, `routes_coordinator.py`, `services_export.py`, `templates/teams/view.html`, `templates/coordinator/registrations.html`, `templates/reset_password_token.html`, `tests/test_team_member_confirm.py` (new), the two test files above.
- **Effort:** M · **Depends on:** UPG-08, UPG-122, UPG-125, UPG-152, UPG-195 (DONE) · **Risk:** medium: a team of 4 adds 3 emails under the daily limit.
- **Found while building:** UPG-208 (the organiser's correction can't change a certificate's email), UPG-209 (a team promoted from the waitlist gets no member links).
- **Acceptance criteria:**
  1. ✅ A team of 3 sends the lead's email and one link to each of the 2 members, in portal mode too; switched off, members get nothing and no account (`tests/test_team_member_confirm.py::test_a_team_of_three_sends_the_lead_one_email_and_each_member_one_link`).
  2. ✅ Setting a password from the link confirms with a time and signs in; the link then says "already confirmed"; an existing account confirms by signing in from the link, its password and name untouched, one account (`::test_setting_a_password_or_signing_in_from_the_link_confirms_without_a_second_account`).
  3. ✅ The lead sees Confirmed and Waiting; three resends, the fourth refused; a resent link replaces the old one; a corrected email gets a link and the old link stops; audit-logged; another team's lead and a member get 403 (`::test_the_lead_sees_status_resends_three_times_and_corrects_an_email_others_cannot`).
  4. ✅ In a portal-mode hackathon a confirmed member sees their participation certificate in "My certificates" and downloads the PDF; the waiting member's is issued too (`::test_a_confirmed_member_sees_and_downloads_their_certificate_and_a_waiting_one_is_issued`).
  5. ✅ After issuing, the team page refuses to change that member's email and points to the organiser (same test).
  6. ✅ Under the daily limit the links are held back and listed; the organiser's button sends nothing while at the limit, then each once (`::test_the_daily_limit_holds_links_back_and_the_organisers_button_sends_them_once`).
  7. ✅ The button sends one link to each waiting member of earlier teams and nothing on a second press; confirmed and invite-code members get nothing (`::test_the_organisers_button_sends_earlier_teams_once_and_skips_confirmed_and_invite_members`).
  8. ✅ The export shows "[Confirmed]" and "[Waiting]" per member (`::test_the_registrations_export_shows_each_members_status`).

### The SPOC cancels a team (owner, 2026-11-09)

#### UPG-211 — The SPOC who hosts an event cancels a team's registration before it is checked in
- **Status:** DONE
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T]
- **Problem:** Owner, 2026-11-09: "make like spoc also can delete on they hosted event, full control to spoc also". Only a SuperAdmin or University admin could cancel a registration (`routes_admin.py:1696`), the lead their own (`routes_participant.py:615`); the SPOC had no way to remove a team from their own event, and the SPOC dashboard didn't link to the registrations page at all (exports only).
- **What was built:**
  - `POST /coordinator/registrations/<event_id>/cancel_team` (`routes_coordinator.py:293`), allowed by `can(session, 'edit_event', event)`: the hosting SPOC and the admins; another SPOC and the event's coordinators get 403. A reason is required (300 characters, shown to the team); a registration of another event, one already cancelled, or one checked in (`checked_in`, `routes_coordinator.py:282`: the team, any member, or any attendance day) is refused.
  - It reuses the participant's own cancel, `routes_participant.cancel_registration_record`: status Cancelled, the seat and any ticket-type seat freed, the waitlist promoted, `REGISTRATION_CANCELLED` audit-logged with who and why; adds `cancelled_at` and `cancelled_by`. The ticket is then refused at every scanner (the existing check at `routes_ticket.py:206`).
  - Everyone on the team gets a portal notice with the reason (`services_hackathon.notify`); the lead gets an email (`send_email_notification`) unless the event is a portal-mode hackathon (`email_allowed(event, 'cancellation')`). A paid team: the flash tells the SPOC to ask the admin to refund it (refunds stay admin-only).
  - The registrations page (`templates/coordinator/registrations.html:89`): a "Cancel team" form per row with the reason, for the hosting SPOC only; "Checked in: can't be cancelled" once in; cancelled rows show the reason. The SPOC dashboard links each event to it, "Registrations & Teams (cancel a team)" (`templates/spoc/dashboard.html:1894`).
- **Not done (by design):** nothing is deleted from the database, so payments, the audit trail and the waitlist stay consistent; a cancellation can't be undone from the page; event coordinators can't cancel (the owner asked for the SPOC).
- **Acceptance criteria** (`tests/test_spoc_cancel_team.py`, real database layer):
  1. ✅ The hosting SPOC cancels a team: status, reason, who and when stored; the count goes down by one; only that team; the scanner answers 409 "cancelled" for it and still admits another team; the lead and the member each get a portal notice with the reason and the lead one email; audit-logged; a second press frees nothing more (`::test_the_hosting_spoc_cancels_a_team_and_its_seat_ticket_and_people_follow`).
  2. ✅ Another SPOC and the event's coordinator get 403; the button shows to the hosting SPOC and not to the coordinator; the SPOC dashboard links to the page (`::test_only_the_hosting_spoc_may_cancel_and_the_page_shows_the_button_to_them_only`).
  3. ✅ Refused without a reason, through another event, and after the team is checked in (the page says so) (`::test_no_cancel_without_a_reason_after_check_in_or_for_another_events_team`).
  4. ✅ A portal-mode hackathon: notices to both, no email (`::test_a_portal_mode_hackathon_team_gets_portal_notices_and_no_email`).
- **Tests changed:** none.

### The registration form is what the SPOC built (owner, 2026-11-09)

#### UPG-212 — The registration form shows exactly what the SPOC built
- **Status:** DONE
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T]
- **Problem:** Owner, 2026-11-09: "the form building and displaying the same form built need to be flexible, however the SPOC can add, remove and make it mandatory". Every form was normalised on read with phone (required) and USN added back, so a SPOC who removed them still saw them on the public form; team members were always asked USN; a choice answer wasn't checked against the options; the builder saved fields the form couldn't show.
- **What was built:**
  - A form saved from the builder is marked chosen (`form_chosen` on the event, read in `_get_form`, `routes_forms.py:162`): only name and email are added if missing, and both are always required (`FIXED_IDENTITY`, `normalise_fields`, `routes_forms.py:114`, `:131`). Every other question shows exactly as built, required or optional as set; required ones are enforced on the server as before.
  - A select, radio or checkbox-group answer must be one of the SPOC's options: "Choose from the options given for '…'." (`routes_forms.py:392-398`).
  - What each team member is asked besides name and email: USN and phone, each Don't ask / Optional / Required (`MEMBER_DETAILS`, `member_settings`, `team_fields`, `routes_forms.py:117`, `:123`, `:196`); required applies to the members up to the team minimum. Stored as `form_member_fields` on the event; the builder shows the choice for team events only (`templates/coordinator/form_builder.html:291`).
  - The builder refuses a form it couldn't show and keeps the last one (`_builder_problem`, `routes_forms.py:528`): an unknown field type, an input without a label, two fields with one id, a field named like the team member rows, a choice question without options; blank and repeated options are dropped.
  - The builder: name and email carry "Always asked" with no delete or duplicate, their Required box fixed on; "Clear all" and AI-made forms keep them (`LOCKED_IDS`, `templates/coordinator/form_builder.html:403`); the note says "Name and email are always asked and required …" (`:284`).
- **Not done (by design):** forms saved before this change, and by the event wizard, are not chosen and keep phone (required), USN and member USN, as before. The form title and description still aren't kept on the SQL database: new item UPG-213.
- **Acceptance criteria** (`tests/test_form_builder_choices.py`, real database layer):
  1. ✅ The form shows exactly the questions built, phone and USN removed stay removed, required and optional as set and enforced, answers stored (`::test_the_form_shows_exactly_what_the_spoc_built_with_phone_and_usn_removed`, `::test_a_question_can_be_made_optional_or_required_and_phone_required`).
  2. ✅ Name and email are always asked and required, even if left out or marked optional; the builder says so (`::test_name_and_email_are_always_asked_and_required`).
  3. ✅ A choice outside the SPOC's options is refused and nothing is registered (`::test_a_choice_must_be_one_of_the_spocs_options`).
  4. ✅ The builder refuses five kinds of broken form with a 400 and keeps the saved one; blank and repeated options are dropped (`::test_the_builder_refuses_a_form_it_could_not_show_and_keeps_the_last_one`).
  5. ✅ The SPOC chooses member USN and phone: required up to the minimum, optional beyond, stored on the member; off leaves no rows; shown for team events only (`::test_the_spoc_chooses_what_each_team_member_is_asked`).
  6. ✅ A form saved without the builder's mark keeps phone, USN and member USN as before (`::test_a_form_saved_before_the_change_keeps_phone_and_usn_and_member_usn`).
- **Tests changed:** `tests/test_builder_and_coordinator_view.py:82` asserted the builder's old note; it now asserts the new one (comment names UPG-212).

### The SPOC chooses who may attend (owner, 2026-11-09)

#### UPG-214 — The SPOC quietly chooses which registered teams may attend
- **Status:** DONE
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T]
- **Problem:** Owner, 2026-11-09: "all registered students need not attend; the SPOC selects before the event who is not to attend, and the scanner needs to show those people", then "that team need not get to know they are removed, just ignored; that's the main thing". Every registered, paid, not-cancelled team got in at every scanner; the scanner didn't even look at round eliminations (`routes_ticket.check_in`).
- **What was built:**
  - The rule, in one place (`services_entry.py`): with the event's switch on (`entry_selection`), a registration may enter only if the SPOC selected it (`entry_selected`) and it isn't out of the competition; a team already checked in stays in; off by default, so other events don't change. No migration (event and registration `extra_json`).
  - The SPOC's controls on Registrations & Teams (`entry_selection`, `routes_coordinator.py:371`; `templates/coordinator/registrations.html:48`): the switch with an optional hall-seat limit; a tick per team (`:129`) with "Select ticked" / "Take ticked off", select all, take all off, "Select the teams still in the competition" (eliminated ones come off), and a CSV of team names, emails or ticket IDs (rows that match nothing are listed); counts (selected, not selected, checked in, turned away) and a warning above the hall limit; filters selected / not selected / paid / not paid (`routes_coordinator.py:149`). Only the hosting SPOC and the admins (`edit_event`); coordinators see the list. A checked-in team can't be taken off; an eliminated one can't be ticked; taking a paid team off reminds the SPOC to ask the admin for the refund. Audit-logged (`ENTRY_SELECTION`).
  - Nobody is told: selecting, unselecting and the switch send no notice, email or push, and the team's dashboard and ticket don't change.
  - Every way in: the shared check-in answers 409 `not_selected`, "Not on the entry list – no entry.", counts the attempt and logs `CHECKIN_REFUSED` (`routes_ticket.py:211`), which covers the QR, session and kiosk scanners; self check-in says only "Please see the registration desk." (`routes_checkin.py:155`); the coordinator's tick (`routes_coordinator.py:1087`) and the admin's "Present" (`routes_admin.py:1692`) are refused.
  - The scan screen: a red "Not On Entry List" result and the list's counts (`templates/coordinator/scan_hud.html:225`); it fetches the list every minute (`/coordinator/scan-hud/<event_id>/entry.json`, `routes_coordinator.py:1016`) and keeps it on the phone, so a scan made without a connection still turns the team away (`static/js/offline-sync.js:64`, `:89`, reading the registration ID from the signed ticket).
  - They hear nothing more: the day-before and 3-day reminders (`tasks/scheduled_tasks.py:96`, `:310`, with their push), the coordinator's broadcast and round alerts (`routes_coordinator.py:693`, `:624`), the SPOC's email blast (`routes_spoc.py:1272`), the automation broadcast (`services_automation.py:311`) and venue or time change notices (`services_venue.py:556`) skip them.
  - Reports: the event report counts them as "Not selected to attend" and the attendance % is over the teams expected (`services_export.py:230`, `:256`); the analytics page doesn't count them as no-shows (`services_insights.py:145`, `:189`); exports get a "Selected to attend" column while the list is on (`services_export.py:108`). They get no participation certificate (never present).
- **Not done (by design):** result emails and the "Results are out" push still go to every lead (UPG-194: each lead gets one result email; in a hackathon the shortlist leaves the non-finalists off the list). A hackathon page update is one page for all teams, so it isn't filtered. The walk-in desk (a new registration made at the door) isn't affected. Only the full-screen scan screen works offline; the other scanners need a connection, as before. Members are selected with their team, not one by one.
- **Acceptance criteria** (`tests/test_entry_selection.py`, real database layer):
  1. ✅ With the list on, the scanner refuses a team not selected (409, the message, counted, audit-logged) and admits a selected one; a team registering later isn't on it; nobody gets a notice or email and the team's dashboard and ticket say nothing; off again, everyone gets in (`::test_only_selected_teams_get_in_at_the_scanner_and_nobody_is_told`).
  2. ✅ Another SPOC and the coordinator get 403; the SPOC's page has the switch, ticks and counts, the coordinator's only the list (`::test_only_the_hosting_spoc_may_choose_and_the_page_shows_it`).
  3. ✅ Select all with the hall warning, take all off, another event's team refused, a CSV with a header and an unknown row, an eliminated team refused and the shortlist button, a checked-in team kept, the refund reminder, the filters, the audit log (`::test_select_all_csv_shortlist_and_who_can_be_ticked`).
  4. ✅ Self check-in ("see the desk"), the kiosk, the coordinator's tick and the admin's "Present" all refuse; absent can still be set; once selected, self check-in works (`::test_every_other_way_in_follows_the_list`).
  5. ✅ The day-before and 3-day reminders, the SPOC's blast, the coordinator's broadcast and a venue change reach the selected team and not the other (`::test_teams_not_on_the_list_hear_nothing_more`).
  6. ✅ The event report, its Excel summary (50 % of the expected), the CSV column, the analytics no-shows and the certificate (`::test_reports_and_exports_dont_count_them_absent`).
  7. ✅ The scan screen's counts and list (403 for another SPOC), and `offline-sync.js` run in Node: a listed ticket (token or verify link) is turned away offline, others aren't, nothing with the list off (`::test_the_scan_screen_shows_the_list_and_keeps_it_for_offline_scans`, `::test_the_phone_turns_away_a_listed_ticket_offline`).
- **Tests changed:** none.

### The registration form is the one the SPOC built (owner, 2026-11-09)

#### UPG-216 — The registration page keeps the builder's title, description and order
- **Status:** DONE
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T, and walked through in a browser on a copy of the local data]
- **Problem:** Owner, 2026-11-09: "whichever form the SPOC builds, only that needs to display… it was not working as expected". A walk-through in the builder (questions added, removed, made required and reordered; a title and description; members' USN and phone) showed questions, options, help text, placeholders, number limits, required marks, members' fields, validation, the responses page and the CSV all following the builder (UPG-212), but two things not: (1) the form's title and description were lost on every save, the first included: the builder reopened, and the page showed, "Registration Form" with no description, because the SQL store keeps only a form's fields (UPG-217); (2) the page's "Participant details" section pulled phone and USN to the top wherever the SPOC put them, while the builder let name and email be moved anywhere though the page always shows them first.
- **What was built:**
  - The builder's title and description are kept on the event (`form_title`, `form_desc`, `routes_forms.py:629`) and read back into the form (`routes_forms.py:181`), as UPG-212 did for its settings; the builder and the page show them.
  - In a form built in the builder, "Participant details" holds only the who-you-are questions the SPOC put directly under name and email; a question placed lower stays where it was put, phone and USN included (`form_sections(fields, chosen)`, `routes_forms.py:233`, `:241`, `:701`). Wizard and template forms keep the layout they had.
  - In the builder, name and email stay at the top, as on the page: no move or drag for them, nothing moves above them, and a question dropped above name goes back below email; the badge says "Always asked, always first" and the hint says the rest appears in the order set (`templates/coordinator/form_builder.html:406`, `:520`, `:527`, `:619`).
- **Not done:** the cause, the SQL store dropping everything but the fields, is UPG-217.
- **Acceptance criteria** (`tests/test_form_builder_order.py`, real database layer):
  1. ✅ The title and description show on the page and come back in the builder; a second save replaces them, an empty description included (`::test_the_title_and_description_the_spoc_gives_are_kept`).
  2. ✅ The page asks in the SPOC's order: phone right under email opens the form, USN below the SPOC's questions stays there, a heading stays above its question; phone moved below a question leaves "Participant details"; a form not built in the builder keeps its layout (`::test_the_page_keeps_the_spocs_order_phone_and_usn_included`, `::test_a_form_not_built_in_the_builder_keeps_its_layout`).
  3. ✅ The builder's own script, run in Node: name and email go to the top and can't be moved, nothing moves above them, other questions still move, a question dropped above name goes back (`::test_the_builder_keeps_name_and_email_at_the_top`).
- **Tests changed:** none (the builder's hint keeps the sentence `tests/test_form_builder_choices.py` checks).

### The form made in step 6 is the one people register with (owner, 2026-11-10)

#### UPG-219 — The registration form is what step 6 of the event wizard shows
- **Status:** DONE
- **Last verified:** 2026-11-10, uncommitted on `55d4736` [T, and walked through in Chromium at 1300 and 390 wide on a copy of the local data]
- **Problem:** Owner, 2026-11-10, with screenshots: "while creating the event, in the 6th step, only what is created there needs to display for register". Step 6 added phone (required) and USN itself and said so; with no question added it saved the event type's catalogue questions unseen (a Hackathon got GitHub URL, tech stack, T-shirt size and diet, mostly required); its "Checkboxes" saved a single tick box without the choices; its "Also ask for" choices were saved in `form_schema` and read by nothing; a wizard form wasn't the SPOC's (`form_chosen`), so phone and USN came back if removed.
- **What was built:**
  - Step 6 for a new event lists the whole form: name and email as fixed rows, Phone Number (required) and USN (optional) as ordinary questions, then the SPOC's, each with type, choices, required, move up and down, and remove; types as on the page (Checkboxes is `checkbox_group`); a choice question without choices stops the step (`templates/spoc/create_event.html:414`, `static/js/pages/spoc__create_event.js:256`).
  - The type's catalogue questions are "Suggested" buttons that add one each (`services_event_types.py:702`, `routes_spoc.py:254`); nothing is added unseen.
  - Team events choose Member USN and Member phone as in the builder; "Also ask for" is gone and `form_schema` keeps only the submission type (`services_event_types.py:550`).
  - The wizard checks the list before the event is made and saves exactly it as the SPOC's form, with the members' choices (`routes_spoc.py:205`, `:300`, `:365`; `routes_forms.py:564` shared with the builder's checks). Requests without step 6's list keep the catalogue form.
  - Editing: step 6 lists the questions in the page's order and what members give, with "Edit the registration form"; saving the edit leaves the form alone (`routes_spoc.py:228`, `create_event.html:406`). Step 7 lists the questions in order.
- **Acceptance criteria** (`tests/test_wizard_form.py`, real database layer):
  1. ✅ Phone removed, USN optional and two questions: the page asks exactly name, email, USN and those two, in order; the builder opens with the same list; phone moved below a question stays there (`::test_the_page_asks_exactly_step_6s_questions_in_its_order`, `::test_phone_moved_below_a_question_stays_there`).
  2. ✅ A Hackathon without the suggestions has none of the catalogue's questions; one added from them is asked (`::test_a_hackathon_gets_none_of_the_template_questions_unless_added`).
  3. ✅ Checkboxes show each choice; a choice question without choices is refused and no event is made (`::test_checkboxes_show_each_choice_and_a_choice_without_choices_is_refused`).
  4. ✅ Members' USN and phone as chosen; no "Also ask for" (`::test_the_members_usn_and_phone_are_chosen_in_step_6`).
  5. ✅ Editing lists the form in the page's order and doesn't change it (`::test_editing_lists_the_form_and_leaves_it_alone`).
  6. ✅ A request without step 6's list keeps the catalogue form (`::test_a_request_without_step_6s_list_keeps_the_template_form`; `tests/test_seminar_e2e.py` unchanged).
- **Tests changed:** none.

#### UPG-220 — The builder's preview title is dark on the dark header
- **Status:** DONE
- **Last verified:** 2026-11-10, uncommitted on `55d4736` [T; R in Chromium: the title is rgb(255, 255, 255) on rgb(0, 24, 94)]
- **Problem:** "Form Preview" was navy on the navy header: `.modal-title` sets its own colour over the header's inline white.
- **What was built:** the preview header uses the site's `on-brand` header (`templates/coordinator/form_builder.html:371`), with labels for the close button and the icon hidden from screen readers.
- **Acceptance criteria:** 1. ✅ `tests/test_form_builder_order.py::test_the_preview_title_is_white_on_the_brand_header`.
- **Tests changed:** none.

### The registrations export shows every detail (owner, 2026-11-10)

#### UPG-222 — The registrations export leaves out the lead's USN and phone, department, year, members' details and the form's answers
- **Status:** DONE
- **Last verified:** 2026-11-10, uncommitted on `6a2638c` [T; the live SAPTHAHACKS'26 page read for its question ids and labels]
- **Problem:** Owner, 2026-11-10, with the SAPTHAHACKS'26 CSV: Lead USN and Lead Phone empty for every team but the first, Department and Year empty for all. The export read the lead's USN and phone only from `lead_usn`/`lead_phone`, which registration fills from the ids `usn` and `phone`; SAPTHAHACKS'26 asks them as questions added in the builder (`f_g9oz1z` "USN", `f_voc3qf` "Phone Number"). Department and year were read only from USNs like 1SN22CS007, not the university's 25SUUBEAML231. Members were one cell, without their emails or phones, with "()" when no USN; the form's own questions had no columns at all.
- **What was built:**
  - The lead's USN and phone: the registration's, else the answer to a question whose label asks for it, else the account's (`services_export.py:158`, `:165`, `USN_LABEL` `:132`).
  - Department and year also from the university's USNs (`USN_BE`, `services_export.py:31`, `:43`).
  - Before "Attendance": Member 2, 3, … Name, USN, Email, Phone (each part when any member gave it) and Confirmed (when members confirm), then one column per question on the form in its order (headings left out, choices joined, repeated labels made unique), then answers to questions since removed (`services_export.py:193`, `:223`). The Members cell stays, without "()".
  - The CSV routes read columns and rows once, so they always match (`routes_spoc.py:627`, `routes_coordinator.py:803`); Excel and the event report likewise. The all-events export keeps COLUMNS only.
  - Nothing saved is changed: the export reads what is there.
- **Acceptance criteria** (`tests/test_export_details.py`, real database layer, Excel and CSV):
  1. ✅ The lead's USN and phone from a hand-added "USN" and "Phone Number", else from the account (`::test_the_leads_usn_and_phone_come_from_the_spocs_own_question_or_the_account`).
  2. ✅ Department and year from 25SUUBEAML231, 24SUUBECS0758, 24BECSE0624, and the old 1SN22CS007 (`::test_department_and_year_come_from_the_universitys_usns`).
  3. ✅ Each member's own columns; no "()" (`::test_each_member_has_their_own_columns`).
  4. ✅ A column per question in the form's order, removed questions after; headings, the USN and phone questions not repeated; headers unique and rows full (`::test_every_question_on_the_form_has_a_column_in_the_forms_order`).
  5. ✅ The all-events export keeps the same columns (`::test_the_all_events_export_keeps_the_same_columns_for_every_event`); `tests/test_exports.py`, `test_sessions.py`, `test_ticket_types.py`, `test_team_member_confirm.py` unchanged and passing.
- **Tests changed:** none.

### A backup email account (owner, 2026-11-10)

#### UPG-224 — A backup Brevo account sends once the main one reaches its daily limit
- **Status:** DONE
- **Last verified:** 2026-11-10, uncommitted on `6a2638c` [T]
- **Problem:** Owner, 2026-11-10: "email backup because the daily limit is reaching soon; Brevo as backup, and it needs to work deployed". The live site sends through one Brevo account capped at `EMAIL_DAILY_LIMIT=270` (Brevo's free 300 a day); past it nothing is sent and people are told to contact the organizer.
- **What was built:**
  - `BREVO_BACKUP_API_KEY`, a second Brevo account, sends through `_send_via_brevo_backup` (`utils_email.py:300`, sharing `_brevo` `:308` with the main account) from `MAIL_FROM_BACKUP`, else `MAIL_FROM`.
  - `_send` (`utils_email.py:510`) tries the main provider within its limit as before; when the main account is at its limit or refuses the email, `send_via_backup` (`:546`) sends it within the backup's own limit.
  - The backup's count and limit: `EMAIL_BACKUP_DAILY_LIMIT` (default 270, `config.py:215`), kept in `email_quota` under `YYYYMMDD-b` so no migration is needed; `reserve`, `release`, `sent_today` and `limit` take the account, and `available()` is True while either has room (`services_email_quota.py:38-127`), so the organizer-contact message shows only when both are full.
  - `/diag/email?via=backup` (Super Admin) sends a test through the backup alone and shows its key, count and limit (`routes_auth.py:525`). `.env.example` and `docs/DEPLOY.md` describe the settings.
- **Acceptance criteria** (`tests/test_email_backup.py`, real database layer, both senders replaced):
  1. ✅ Past the main limit the backup sends, each counted on its own; both full sends nothing and `available()` is False; a new day starts both at zero; a registration past the main limit gets its email through the backup (`::test_the_backup_sends_once_the_main_account_is_at_its_limit`, `::test_a_registration_past_the_main_limit_is_emailed_through_the_backup`).
  2. ✅ An email the main account refuses goes through the backup and the main places are given back (`::test_the_backup_sends_what_the_main_account_refuses`).
  3. ✅ Without the key nothing changes (`::test_without_a_backup_key_nothing_changes`; `tests/test_low_email_auth.py` unchanged and passing).
  4. ✅ The backup uses its own key and sender (`::test_the_backup_uses_its_own_key_and_sender`).
  5. ✅ The admin's email check tests the backup alone and says when the key isn't set (`::test_the_admin_tests_the_backup_from_the_email_check`).
- **Tests changed:** none.
