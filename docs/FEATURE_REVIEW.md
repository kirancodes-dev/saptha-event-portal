# SapthaEvent — Feature Review (the short file)

The source of truth for planned work: work on one item ID at a time (`AGENTS.md`). This file holds the index of every item, the full text of open items, open decisions and the last 20 changelog lines. Done items, the feature inventory and the journey and event-type tables are in `docs/archive/FEATURE_REVIEW_DONE.md`; older changelog rows in `docs/archive/CHANGELOG.md`. Open the archive only for a specific item, with grep.

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

## Index

| ID | Title | Status | One line |
|---|---|---|---|
| UPG-01 | Registration forms render every template field and always ask for identity | DONE | Template and seeded forms store field_name (services_templates.py form_config; seeded event_forms rows), but… |
| UPG-02 | QR check-in that works with real tickets, for assigned coordinators only | DONE | Three scanners, three broken paths : |
| UPG-03 | Exports and an event report with real participant data | DONE | /spoc/export_csv, /coordinator/export_registrations, /forms/responses/export and… |
| UPG-04 | Judging works for rubric criteria from the create form and for new workflow states | DONE | The create form saves criteria as {name, description, max_score} (templates/spoc/create_event.html:1117).… |
| UPG-05 | Feedback forms that load, save, and feed the report | DONE | At 694c729 students were told "Unauthorised access." on /feedback/submit/<reg> and… |
| UPG-06 | Certificates generate with the right name and can be issued in bulk | DONE | (the signature mismatch is re-checked unchanged at 1f4cdc8 ; the name and bulk-gate bullets were caused by… |
| UPG-07 | Reminders and lifecycle jobs run on free-tier hosting | DONE | Reminders, the day-before QR email and lifecycle transitions are Celery beat jobs (celery_app.py:95-120).… |
| UPG-08 | Team registration linked to tickets and judging | DONE | The SPOC-created team hackathon form showed only name/email/phone/USN [R at 694c729], because is_team_event… |
| UPG-09 | Book the venue while creating the event | DONE | Room conflict detection exists (services_venue.check_room_conflict), but it runs only on edit… |
| UPG-10 | Student roster import and university Google sign-in | DONE | Accounts come only from self sign-up (routes_auth.py:276-323) or registration, which creates an unverified… |
| UPG-11 | Participation ledger: activity points and NSS / NCC / FDP hours | DONE | MISSING. No points or hours fields exist anywhere (searched routes, services and templates for activity… |
| UPG-12 | Faculty and external participants (FDPs, guest lectures, conferences) | DONE | Every registrant is created as Student: registration through services_accounts.create_unverified_account (its… |
| UPG-13 | Sports tournaments: fixtures, results, standings | DONE | The sports template promises "fixture brackets, live match score updates, point tables"… |
| UPG-14 | Merge duplicate subsystems | DONE | a v2-only notification API and dashboard feed; remove v1, Stripe, both scheduler files and tests.py; hide the… |
| UPG-15 | Delete dead code and fix dead links | DONE | remove or merge the above; move scratch/ tools worth keeping into scripts/ and delete the rest; fold the seed… |
| UPG-16 | Alembic baseline: build an empty database through migrations | DONE | one baseline migration matching models_pg.py (0001/0002 folded in, or rebased onto the baseline); start-up… |
| UPG-17 | Uploads go to object storage and survive restarts | MERGED | [C at 56a014d] |
| UPG-18 | Background tasks without a broker: inline with timeouts, plus an outbox for retries | DONE | [C at 56a014d] Without CELERY_BROKER_URL=redis://…, Celery runs every task inline in the request… |
| UPG-19 | Pagination and search on every admin, SPOC and coordinator list | DONE | [C at 56a014d] Only routes_api_v1.py and routes_notifications_v2.py read a page or limit parameter (the… |
| UPG-20 | Boot checks, health, logs, Sentry and security headers for production | DONE | [C at 56a014d] |
| UPG-21 | Daily database backups and a tested restore | DONE | MISSING . Nothing in the repo dumps or restores the database (searched for pg_dump and backup scripts; the… |
| UPG-22 | Privacy notice, consent at registration, working data export and deletion | DONE | [C at 56a014d] routes_compliance.py has data export (:50), deletion request (:126), cancel deletion (:188)… |
| UPG-23 | Every page on one shared layout (split by area: UPG-23a–h) | DONE | [C at 56a014d, counted with a script] Of 129 templates, 16 extend base_classic.html (12 at 986d108; Phase 2… |
| UPG-24 | One Bootstrap version and one font set, loaded once, with SRI | DONE | [C at 56a014d] Bootstrap 5.3.0 is loaded by 46 templates and 5.3.3 by 34 (re-counted 2026-10-08; 50 and 34 at… |
| UPG-25 | Move inline scripts into static files; remove `'unsafe-inline'` from `script-src` | DONE | [C at 56a014d] 70 templates contain inline <script> blocks, and 76 templates contain 483 inline event… |
| UPG-26 | Forms: visible labels, clear errors, a loading state and one submit per click | DONE | [C at 56a014d] The only double-submit guard is the "button loading state" in static/js/global.js:211-229, and… |
| UPG-27 | Images: compress, lazy-load, alt text; visible keyboard focus | DONE | [C at 56a014d] static/img is 4.5 MB in 7 files: event_slide1–4.png are 0.8–1.06 MB each, feature-showcase.png… |
| UPG-28 | The student journey and the scanner work on a 375px phone | DONE | Not verified. Nobody has checked discover → register → pay → ticket → check-in → feedback → certificate, or… |
| UPG-29 | Coordinator and judge assignment by a SPOC, end to end | DONE | Assignment works since BLK-09 (routes_spoc.py:1171-1252 coordinators, :1379-1435 judges), and one test covers… |
| UPG-30 | Paid events end to end: receipt email, refunds and cancellations | IN PROGRESS | [C at 56a014d] After a verified payment only a WhatsApp receipt task is queued (routes_payment.py:356);… |
| UPG-31 | Notifications: confirmation, day-before reminder, change and cancellation notices through Brevo | DONE | [C at 56a014d] Confirmation (utils_email.send_registration_confirmed_email, utils_email.py:439) and… |
| UPG-32 | Release check and `docs/DEPLOY.md` | DONE | There's no deploy guide for Cloud Run + Supabase, and no end-to-end release check from a fresh clone.… |
| BLK-01 | Admin credentials and a user database are in the public GitHub history | IN PROGRESS |  |
| BLK-02 | The public registration form logs the visitor in as any email they type | DONE | submit_form set session['user_id'] to the submitted email (routes_forms.py:598 at 56a014d; waitlist branch… |
| BLK-03 | Paid events can be completed without paying | DONE | BLK-09 fixed two prerequisites: the event fee now persists (₹500 stored as entry_fee 500 and fees.regular 500… |
| BLK-04 | Endpoints missing authorization | DONE | can(session, <perm>, event) on every open endpoint above; state-changing routes become POST (keeping the old… |
| BLK-05 | Route tests never run against the SQL adapter the app uses | DONE | run the seminar/hackathon journey (register → check-in → score → certificate → feedback) on real_app; a… |
| BLK-06 | The SQL adapter loses, renames and ignores fields (postgres mode) | DONE | Re-ran the original round-trip on 1f4cdc8 . |
| BLK-07 | Role migration locks out SuperAdmin and SPOC accounts | DONE | Re-run on 1f4cdc8 . |
| BLK-08 | Users are logged out at random once ~500 sessions exist; sessions don't survive restarts or span instances | DONE | Unchanged by BLK-09 [C at 56a014d]. |
| BLK-09 | Merge the `claude/busy-davinci-6nkabi` branch from GitHub | DONE | origin/claude/busy-davinci-6nkabi (3 commits, 2026-09-26: 348aceb, 6d5bec0, c49291b, forked from 89af3d3)… |
| BLK-10 | Seed scripts write known passwords and don't refuse production databases | DONE |  |
| BLK-11 | CI's bandit job fails on 5 pre-existing issues, so CI can't go green | DONE | The CI job "Security scan (bandit)" (bandit -r . -x tests/,__pycache__/ -ll -q, .github/workflows/ci.yml)… |
| BLK-12 | Kiosk and ticket-verify holes (and tests for them on the real database) | DONE | Added in Phase 0 from the production-ready plan's list: unauthenticated kiosk search and confirm, a raw… |
| BLK-13 | Login has no rate limiting | DONE | Added in Phase 0 . Re-checked against the code at 07cf145 before building: routes_auth.py, routes_api_v1.py,… |
| BLK-14 | Anyone can create a SuperAdmin account through the public tenant sign-up | DONE | Found while working on BLK-02 . POST /onboarding/signup (routes_onboarding.py:17-84 at dc8ea5a, registered… |
| BLK-15 | The Firestore seed guard checks a different key than the scripts use, and its test fails in CI | DONE | Found on 2026-10-01 while checking CI after the owner's push. Reproduced in fresh clones with CI's test-job… |
| BLK-16 | Email, QR and referral links follow a forged Host header | DONE | From the code review of PR #48 (owner, 2026-10-02); confirmed in the code . |
| BLK-17 | Any SPOC can end, publish, staff and edit other SPOCs' events | DONE | Found while starting UPG-33 [C at a417e88, AST scan of routes_spoc.py plus reading each route]. These… |
| BLK-18 | Any Volunteer can mark attendance and open tickets at any event | DONE | Found while starting UPG-02 . services_permission.can gave the Volunteer session role check_in on every… |
| BLK-19 | Registrant names run as HTML on staff pages (stored XSS) | DONE | Found while building UPG-02 . Registration stores the lead's name, the team name and member names exactly as… |
| UPG-33 | Account emails: walk-in passwords by email, reusable reset links | DONE | Found while building BLK-02 . |
| UPG-34 | The legacy public registration route skips the "registration closed" check | DONE | Found while building BLK-02 . POST /participant/public_register/<event_id> (routes_participant.py:355), still… |
| UPG-35 | Login and password-reset messages reveal whether an account exists | DONE | Found while building BLK-13 . BLK-13's throttle answers the same for known and unknown accounts, but other… |
| UPG-36 | Coupons can be used more than `max_uses` times | DONE | From the code review of PR #48 (owner, 2026-10-02) . find_valid_coupon refuses a coupon only when… |
| UPG-37 | Hourly per-account login cap on top of the per-minute limit | DONE | From the code review of PR #48 (owner, 2026-10-02). BLK-13 allows 5 failed logins per account per minute… |
| UPG-38 | Delete the sample Jekyll workflow | DONE | From the code review of PR #48 (owner, 2026-10-02). .github/workflows/jekyll-docker.yml is GitHub's "Jekyll… |
| UPG-39 | In development, log set-password and reset links when no mail provider is set | DONE | Owner, 2026-10-02. Since BLK-02 and UPG-33 the emailed set-password link is the only way into a new account,… |
| UPG-40 | The Super Admin can resend a set-password link from a users page | DONE | Owner, 2026-10-02. Since UPG-33, staff, SPOCs and walk-ins can get in only through the emailed set-password… |
| UPG-41 | Remove the leftover Gmail app password from `utils_email.py` | DONE | Found 2026-10-02 while recording UPG-39 . The module docstring of utils_email.py (:26-27, also in… |
| UPG-42 | The privacy, terms and payment-failed pages give the old Gmail account as the contact address | DONE | Found 2026-10-07 while building UPG-41 . Three public pages tell people to write to the old mail account, the… |
| UPG-43 | Event-day lists show only events whose status is the old `active` | DONE | Found while building UPG-02 . Events created by SPOCs move through workflow states… |
| UPG-44 | An empty payment status reads back as `unpaid` (postgres mode) | DONE | Found while building UPG-02 . A registration written with payment_status: '' reads back as 'unpaid' on the… |
| UPG-45 | Form submissions lose who sent them, and read back flattened (postgres mode) | DONE | Found while building UPG-01 . utils.record_form_submission writes {event_id, reg_id, email, name, answers,… |
| UPG-46 | Scheduled emails link to a fixed `sapthaevent.in`, not `BASE_URL` | DONE | Found while building UPG-07 . The coordinators' day-before briefing links… |
| UPG-47 | Events saved without times get the save time as their start and end (postgres mode) | DONE | Found while building UPG-07 . The SQL adapter stores an event's start_datetime and end_datetime through… |
| UPG-48 | Team members get no confirmation, reminder or notice | DONE | Found while building UPG-31 . Since UPG-08 a team's members are on the registration and can open its ticket,… |
| UPG-49 | The automation's WhatsApp channel calls a function that doesn't exist | DONE | Found while building UPG-31 . services_automation.dispatch_trigger sends WhatsApp through… |
| UPG-50 | Email templates insert names and titles without escaping | DONE | Found while building UPG-31 . The HTML emails put the recipient's name, the event title and messages straight… |
| UPG-51 | Cancelling a paid event refunds nobody | DONE |  Cancelling an event (services_workflow.WorkflowEngine.transition_event → cancelled) sends the cancellation… |
| UPG-52 | Joining a team can overwrite another join or exceed `team_max` | DONE |  routes_teams.join_team (routes_teams.py:64-102) reads the registration's members, checks len(members) >=… |
| UPG-53 | The home page shows a fake hackathon when there are no events | DONE |  When no event is listed, the home page builds a demo event (app.py:704-706, id demo-hackathon-2026,… |
| UPG-54 | The Android app loads an old Railway URL | DONE |  capacitor.config.json:5-6 points the Android webview at https://saptha-portal.railway.app, a retired host;… |
| UPG-55 | Google sign-in and 2FA exist but nothing links to them | DONE |  auth_oauth.py serves /auth/google and auth_2fa.py serves /auth/2fa/*, but no template links to either (grep… |
| UPG-56 | Checkout has no coupon field | DONE |  The server applies a coupon validated on the server when create_order gets one… |
| UPG-57 | Placement drives: eligibility rules and shortlist rounds | DONE | MISSING . The event-type table lists placement drives as "Generic registration only": eligibility (branch,… |
| UPG-58 | The native document store creates its table at runtime, outside migrations | DONE | Found while building UPG-19 . Collections with no SQL model live in native_document_store, which… |
| UPG-59 | Five pages answer 500 for any role | DONE | Found by UPG-23's route crawl , on a seeded event with one registration, the same before this run (932afdd)… |
| UPG-60 | Front-end errors the browser pass found (before and after this run) | DONE | Found by UPG-25's Chromium pass over every page ; each also appears on the code before UPG-23a: |
| UPG-61 | A development database made before a NOT NULL column was added breaks every query on its table | DONE | Found starting UPG-59 . Development start-up (db_pg.init_db) added only *nullable* columns to existing… |
| UPG-62 | 19 existing tests fail since the clean-up and seed commits | DONE | Found by the full pytest after Part 1 of the owner's second run : 19 failed, 792 passed, 1 skipped on SQLite… |
| UPG-63 | Portal-wide design system and visual consistency | DONE | [R, headless Chromium screenshots of every role at 0fd9f3a] The portal looks like several products. The home… |
| UPG-64 | Six templates are still never rendered | DONE | Found starting UPG-63 [C, every render_template/include/extends and every Python string checked]:… |
| UPG-65 | Fabricated figures and simulated features on live pages | DONE | Found during UPG-63 [C, templates read; R, pages loaded]. Several pages show numbers or behaviour that no… |
| UPG-66 | Two forms post without a CSRF token | DONE | Found during UPG-63 . templates/public/exam_interface.html:49 (examForm, also submitted by… |
| UPG-67 | The coordinator scanner throws a script error when it is locked | DONE | Found during UPG-63 [R, headless Chromium]. templates/coordinator/scan.html calls startCamera() on… |
| UPG-68 | The coordinator dashboard links to a form builder coordinators can't open | DONE | Found during UPG-63 . "Build registration form" on each event card of /coordinator/dashboard links to… |
| UPG-69 | The legacy certificate check and the digital ticket lose the lead's name and email on the SQL adapter | DONE | Found during UPG-63. registrations document(id).get().to_dict() returns leadEmail and leadName but not… |
| UPG-70 | The confetti library's worker is blocked by the CSP | DONE | Found during UPG-63 . canvas-confetti on the certificate verification pages creates a blob: worker, and the… |
| UPG-71 | A profile photo for every role | DONE | Owner request during UPG-63. Every account showed only initials, and nobody could add a photo or choose an… |
| UPG-72 | The first page view loads twice when the service worker installs | DONE | Found during UPG-71 [R, headless Chromium navigation log]. static/js/pages/includes__pwa_head.js:82-85… |
| UPG-73 | Event creation that fits every kind of event | DONE | Found 2026-10-12 [C, routes_spoc.py:137-374, templates/spoc/create_event.html, services_templates.py; R,… |
| UPG-74 | Fests: one big event that holds many sub-events | DONE | Owner request 2026-10-12. A college fest, such as a cultural fest with 20 competitions or a sports meet with… |
| UPG-75 | Super Admin control centre: see and control everything | DONE | Owner request 2026-10-12: the Super Admin is the person with access to everything, and the pages must let… |
| UPG-76 | A deactivated account keeps its open session | DONE | Found building UPG-75 . Deactivating an account (UPG-75) is checked only at login. A session that's already… |
| UPG-77 | The admin's announcement email puts the message into HTML unescaped | DONE | Found building UPG-75 . send_bulk_email (routes_admin.py) builds the email body with f'...{message}</div>',… |
| UPG-78 | Coordinators still create events through an old form that skips the draft flow | DONE | Found building UPG-75 . |
| UPG-79 | The form builder's Back goes to the wrong page | DONE | Owner report 2026-10-12 (screenshot). In templates/coordinator/form_builder.html Back was hard-coded:… |
| UPG-80 | A Super Admin's "Coordinator view" looks like a second admin home | DONE | Owner report 2026-10-12 (screenshots). /coordinator/dashboard, opened from the admin's "Coordinator view",… |
| UPG-81 | The admin dashboard and analytics add up a cached registration counter that can be stale | DONE | Found doing UPG-80 [C, owner screenshot]. The admin dashboard (routes_admin.py:58) and analytics (:1085)… |
| UPG-82 | The API creates live events that skip the draft and review flow | DONE | Split from UPG-78 . POST /api/v1/events (routes_api_v1.py:270-310) saves status: 'active' from a few fields,… |
| UPG-83 | Analytics pages that are correct, comparable and adjustable | DONE | Owner request 2026-10-12: the analytics look jumbled; use the best tools, make a multi-event bar chart that… |
| UPG-84 | Leaderboards disagree with each other and drop the evaluation engine's scores | DONE | Owner request 2026-10-12 ("fix the leaderboard"). Found [R, C]: |
| UPG-85 | AI summaries after publishing results never run | DROPPED | Found testing UPG-84 [T, traceback in the test log]. routes_coordinator.py starts a thread for _bg_summaries,… |
| UPG-86 | A production home page with the university's real details | DONE | Owner request 2026-10-12: use snpsu.edu.in for real data (Instagram and the rest); remove the entry-fee… |
| UPG-87 | Home page: no calendar, and "Coming up" stays inside its card | DONE | Owner report 2026-10-13 (screenshot): |
| UPG-88 | A clean, realistic demo dataset | DONE | Owner request 2026-10-13: clean all the data and create proper demo data for the final submission: two events… |
| UPG-89 | Repository clean-up and README | DONE | Owner request 2026-10-13: remove the PDFs and old documents from git, keep only what is needed, and rewrite… |
| UPG-90 | Events turn "completed" up to 5½ hours late, and a test fails after midnight | DONE | Found in the full run at UPG-89 . scheduler_enhanced.py:149 compares event dates, which are local (IST), with… |
| UPG-91 | Emails: the logo shows, and links open where the portal is being used | DONE | Owner report 2026-10-13 (screenshot of a set-password email). Three problems: |
| UPG-92 | One event view: the home page popup shows the event page, and registration's Back returns where the visitor came from | DONE | Owner report 2026-10-13 (two screenshots). Clicking an event on the home page and opening its page showed the… |
| UPG-93 | UPG-91's test sets a password-shaped MAIL_PASS literal, failing the repo hygiene scan | DONE | Found in the full run at UPG-92 . tests/test_email_links_and_logo.py:118 calls… |
| UPG-94 | Razorpay: confirm capture with Razorpay, failed and refund webhooks, retry on the checkout page | DONE | Owner's Razorpay integration request, 2026-10-17. BLK-03 and UPG-30 built most of it: the server's price,… |
| UPG-95 | Registration IDs come from the clock, so two at the same millisecond overwrite each other | DONE | Found building UPG-94 . A registration's ID is REG-<milliseconds>. It's set in the form (routes_forms.py:704)… |
| UPG-96 | The checkout script puts the event title into a JavaScript string with HTML escaping only | DONE | Found building UPG-94 . templates/payment/checkout.html:227 writes description: "{{ event.title }}".… |
| UPG-97 | Registering without logging in, for an email that already has an account | DONE | Owner report 2026-10-17, with a screenshot. A visitor who registers from the home page with an email that… |
| UPG-98 | The container image would include the Firebase key and local database copies | DONE | Found preparing the Google Cloud deployment, 2026-10-17 . .dockerignore excludes .env and saptha_fallback.db… |
| UPG-99 | Signed download links fail on Cloud Run's default credentials | DONE | Found in the test deployment . utils_storage.signed_url (utils_storage.py:162) calls… |
| UPG-100 | The editor's type checker can't read its config, so it reports missing modules and the optional-import fallbacks | DONE | Owner report 2026-10-17 (Pyrefly diagnostics pasted from VS Code for routes_coordinator.py). pyrefly.toml… |
| UPG-101 | README: the live link, a live-demo button, running it locally, and current facts | DONE | Owner request 2026-10-17. The README had no link to the deployed site. Its test badge (893) and Quality… |
| UPG-102 | 1,044 Pyrefly type errors across the app | TODO | With a working config (UPG-100), pyrefly check reports 1,044 errors in the app. The most are in models_pg.py… |
| UPG-103 | No way back to the previous page in the installed app | DONE | Owner report 2026-10-17: "for all pages I can't go back to the previous step". The app installs as a PWA with… |
| UPG-104 | Student dashboard: unstyled on desktop, squeezed on phones, and tabs that don't match the events | DONE | Owner report 2026-10-17: "in the student dashboard all the above buttons are just dummy … some details not… |
| UPG-105 | Hide the referral section for now | DONE | Owner request 2026-10-17: "for now remove that referral section". The student dashboard shows "Refer… |
| UPG-106 | The SPOC event panel runs off a phone screen, and its buttons squeeze the title | DONE | Owner report 2026-10-17, with a phone screenshot of a SPOC event. On a phone (375 px) : |
| UPG-107 | Google Search Console ownership file | DONE | Owner request 2026-10-17. Google Search Console verifies the site with an HTML file,… |
| UPG-108 | The chatbot's built-in campus FAQ states unconfirmed facts | DONE | Found building UPG-65. The prompt sent to the AI assistant (chatbot_routes.py, FAQ_CONTEXT) presents campus… |
| UPG-109 | AI judge matching without any AI provider answers 500 with the raw error | DONE | Found re-verifying UPG-59 after UPG-65. With neither Zoho QuickML nor GEMINI_API_KEY configured, POST… |
| UPG-110 | Background tasks run in a stale Flask app (the suite turns order-dependent) | DONE | Found in Part 2 . After the Part 2 test files were added, the full run failed two tests that pass alone:… |
| UPG-111 | Pages and emails invent a venue ("SNPSU Campus") for events without one | DONE | Found testing UPG-43. routes_coordinator.scanner_selector shows d.get('venue', 'SNPSU Campus'), an invented… |
| UPG-112 | UPG-14's leftover duplicates | DONE | Found testing UPG-14. Its criteria are met, but parts of its problem list were never built: |
| UPG-113 | CI's bandit step fails on the showcase seeder's table wipes | DONE | Found testing UPG-15. CI runs bandit -r . -x tests/,__pycache__/ -ll -q (.github/workflows/ci.yml:146). Since… |
| UPG-114 | The waitlist shows a position that can repeat | DONE | Found in UPG-112. Both join paths store position as the number still waiting plus one… |
| UPG-115 | Two registration forms sent at the same instant register the same person twice | DONE | Found testing UPG-26. The duplicate check in routes_forms.submit_form (routes_forms.py:647-656) reads the… |
| UPG-116 | A popup test fails when a random event id contains "999" | DONE | Found in the end-of-Part-2 full run.… |
| UPG-117 | The JSON waitlist join only takes events in the old "active" status | DONE | Found in UPG-114. POST /waitlist/join/<event_id> (routes_waitlist.join_waitlist) answers "Event is not… |
| UPG-118 | The CI secret scan flags the production boot test's dummy settings | DONE | Found in Part 3's full-history gitleaks scan (8.30.1, CI's version and command).… |
| UPG-119 | Werkzeug 3.1.8 has a known vulnerability (fixed in 3.1.9) | DONE | Found by Part 3's pip-audit of a fresh install of requirements-dev.txt: Werkzeug 3.1.8 has PYSEC-2026-4312… |
| UPG-120 | Volunteers can't log in | DONE | Found by Part 3's browser pass of every role. A volunteer account's role is Volunteer (staff appointment, the… |
| UPG-121 | The admin audit log's table is cut off on a phone | DONE | Found by Part 3's browser pass of every role (production build, 375px). The audit log's table sits in a card… |
| UPG-122 | Certificate types, who gets them, and one record per person, event and type | DONE |  |
| UPG-123 | Certificate templates, branding and each event's signatories | DONE |  |
| UPG-124 | Issuing certificates: in bulk in the background, automatically on results, and by hand | DONE |  |
| UPG-125 | Delivering certificates: email, "My certificates", sharing and phones | DONE |  |
| UPG-126 | Verifying a certificate | DONE |  |
| UPG-127 | Correcting and revoking certificates | DONE |  |
| UPG-128 | Certificate lists, exports and college-wide counts | DONE |  |
| UPG-129 | Who may issue, revoke, approve and download certificates | DONE | issuing, revoking and approving corrections only for the event's owner or someone holding issue_certificates… |
| UPG-130 | Hours on the certificate (UPG-11's deferred criterion 4) | DONE | 1. ✅ Test: a certificate for an event with hours shows the hours in its PDF text. [T… |
| UPG-131 | FDP wording with designation and institution (UPG-12's deferred criterion 2) | DONE | 1. ✅ Test: an FDP certificate's PDF text shows the faculty member's designation and institution. [T… |
| UPG-132 | The certificate page and download on a phone (UPG-28's certificate part) | DONE | 1. ✅ Test: at 375px the certificate page has no sideways scroll and its download works (headless). [T… |
| UPG-133 | Escaping in the certificate email (UPG-50's deferred part) | DONE | 1. ✅ Test: a recipient named <b>Ann</b> gets a certificate email showing the text, not markup. [T… |
| UPG-134 | The support address on the verification pages (UPG-65's deferred part) | DONE | 1. ✅ Test: the verification pages show SUPPORT_EMAIL, or no address when it's unset; nothing hard-coded. [T… |
| UPG-135 | Certificate verification keeps the lead's name and email (UPG-69's deferred part) | DONE | 1. ✅ Test: /verify/<present reg_id> (the legacy form) and its preview show the lead's name, on seeded rows… |
| UPG-136 | No invented venue in the certificate preview (UPG-111's deferred part) | DONE | 1. ✅ Test: no certificate page or PDF says "Main Campus" for an event without a venue. [T… |
| UPG-137 | One certificate store (UPG-112's "two certificate stores") | DONE | 1. ✅ Test: API v1's issue and verify endpoints use the same certificates records as the web, and /verify… |
| UPG-138 | One issuing path again: the old callers move to the new certificates | DONE | Found starting UPG-124. Ending an event (routes_spoc.py:793 → tasks/cert_tasks.py:25) and the SPOC's bulk… |
| UPG-139 | The coordinator's "publish results" doesn't mark the results published | DONE | Found starting UPG-124. POST /coordinator/publish_results/<id> (routes_coordinator.py:422-484) ranks the… |
| UPG-140 | Audit rows written outside a request are lost | DONE | Found building UPG-127. utils.log_action (utils.py:90-138) reads session for the user and role whatever the… |
| UPG-141 | The participant's certificate page prints "at ." for an event without a venue | DONE | Found building UPG-132. templates/participant/certificate.html says "held on <date> at {{ event.venue }}."… |
| UPG-142 | Merit and special-mention certificates can't be awarded | DONE | Found while making the sample emails. services_certificates.TYPES has "merit" and "special_mention" (the… |
| UPG-143 | Tests that make an event "today" fail when a run crosses midnight | DONE | Found in the final PostgreSQL run of the certificate phase.… |
| UPG-144 | NAAC / AQAR report from event data | DONE | NAAC categories, post-event reports with evidence, a yearly report builder and exports; IQAC coordinator and department admin roles. |
| UPG-145 | Track record: impact dashboard, time saved, testimonials, impact report and page | DONE | Real-data impact dashboard, organisers' time-saved estimates, permissioned testimonials, a 2-page impact PDF and an optional public page. |
| UPG-146 | Reach beyond one campus: open events, external students, share cards, listing kit, "Powered by" | DONE | Campus-only or open events, a public open-events page, external registrations, share cards with valid schema.org, a listing kit (no site offers an API) and a switchable "Powered by" line. |
| UPG-147 | WhatsApp notifications through the official API, with opt-in, once-only sends and a monthly cap | DONE | WhatsApp via Meta Cloud API or Twilio, off by default: opt-in, once-only template messages, STOP replies, outbox retries and a monthly cap. |
| UPG-148 | The registration confirmation hides text under the pinned footer on a phone | DONE | The confirmation page for a new account no longer pins its footer over the set-password box on a phone. |
| UPG-149 | Multi-round competitions (hackathons with 2–3 rounds) end to end | DONE | One round service for the SPOC panel and the coordinator: round history kept, "Round X of N" and a final round, no stranded or double-advanced teams, ties go through, every team emailed, judges limited to the current round, students see their status. |
| UPG-150 | The registration form as a full-page, official form | DONE | A full-width form beside a sticky event summary, in numbered sections (participant, details, team, declaration), with underlined fields instead of boxes. |
| UPG-151 | Writing an empty `scores` map keeps the old scores (postgres mode) | TODO | Found building UPG-149. `update({'scores': {}})` deletes no Score rows in the SQL adapter (Firestore would empty the map); only `DELETE_FIELD` clears them. |
| UPG-152 | Low-email registration and login for the hackathon | DONE | One email per new registration, to the lead only, with a one-time set-password link (48 hours); 15-minute reset links, one reset in the first 48 hours then the organizer message; a shared daily email limit (default 450); login email status for organisers; no tokens or passwords in the logs. |
| UPG-153 | A new participant at a paid event still gets three emails | TODO | Found building UPG-152. Set-password at submit, then the ticket and the receipt after the payment (`routes_forms.py:1093` after UPG-244, `routes_payment.py:474-479`); one email after the payment would do. |
| UPG-154 | `tests/test_admin_users.py` depends on how many accounts earlier tests made | TODO | Found building UPG-152. Its tests look for a new account on page 1 of `/admin/users` (25 a page), so they fail after enough earlier accounts, or on a reused PostgreSQL test database. |
| UPG-155 | Ticket types: early-bird windows, seat limits per ticket and group prices | DONE | Ticket types in the wizard (sale dates, seats, who may buy, per team or per person); priced at checkout with seats taken race-free; on the form, registration and exports. |
| UPG-156 | Apple Wallet and Google Wallet tickets | DONE | Apple Wallet `.pkpass` and Google Wallet links carrying the ticket QR every scanner accepts; hidden until their keys are set. |
| UPG-157 | Browser push notifications, switched on | DONE | Push opt-in after registration and in the profile; reminders, changes and results pushed once to the event's subscribers; gone subscriptions removed; off without VAPID keys. |
| UPG-158 | Name badges printed at check-in | DONE | A4 sheets of 8 badges and one badge from the scanner after a check-in, with the ticket QR; name, college or department and role only; staff only. |
| UPG-159 | Session check-in and a personal agenda | DONE | Agenda sessions with room, seats and hours; a scanner session mode; "My agenda" with stars and an `.ics`; per-session hours in the ledger; a column per session in exports. |
| UPG-160 | Live polls and Q&A during talks | DONE | Host-run polls and an upvoted, moderated question queue for checked-in attendees; a projector view over SSE; poll results in the event report. |
| UPG-161 | Transfer a ticket to someone else | DONE | The lead transfers a ticket before the cut-off to an eligible account that wouldn't pay more; the old QR is refused everywhere; both emailed. |
| UPG-162 | Where registrations come from: tracked share links | DONE | Named share links with poster QRs; `src`/`utm_source` kept to the registration (unknown codes as "other"); visits, registrations and conversion per source. |
| UPG-163 | Call for papers with reviewer scoring (conferences) | TODO | Paper/abstract submission, blind review by assigned reviewers, accept/reject emails, proceedings list. |
| UPG-164 | Hackathon project gallery and a people's choice vote | TODO | A public gallery of submitted projects and a one-person-one-vote audience award. |
| UPG-165 | Mentor office hours for hackathons | TODO | Mentors publish slots; teams book them; no-shows and load are visible to the organiser. |
| UPG-166 | Judges declare conflicts of interest | TODO | Judges mark teams they know; those teams are scored by others and the ranking stays fair. |
| UPG-167 | Volunteer sign-up and shift rota | TODO | Students apply to volunteer; organisers approve and assign shifts; hours go to the ledger. |
| UPG-168 | Event budget, expenses and approval | TODO | A budget with the event proposal, expenses with bills, and a budget-vs-actual report. |
| UPG-169 | Sponsor tiers, deliverables and sponsor reports | TODO | Sponsors per event with tiers, logos on pages and certificates, and a post-event report for them. |
| UPG-170 | Event photo gallery | TODO | Organisers upload event photos; attendees see, download and share them; photos feed NAAC evidence. |
| UPG-171 | Outgoing webhooks and a Google Sheets sync | TODO | Send registrations, check-ins and results to other tools as they happen; a live Sheet per event. |
| UPG-172 | A registration widget for other websites | TODO | One snippet puts an event's card and register button on a department or club site. |
| UPG-173 | Kannada and Hindi interface | TODO | Switch on the existing `hi` and `kn` translations and finish them for the student journey. |
| UPG-174 | Teammate matching on real profiles | TODO | Replace the hidden mock matchmaker with opt-in skill profiles and suggestions from real students. |
| UPG-175 | AI writing help for organisers | TODO | Draft the event description, rules and social posts in the wizard; the post-event summary in the report. |
| UPG-176 | Live stream and recordings on the event page (replaces the invented live pages) | TODO | Embed a YouTube/Meet stream on the event page during the event and the recording after. |
| UPG-177 | Reserved seating for auditorium events | TODO | A seat map per venue; attendees pick seats; the ticket shows the seat. |
| UPG-178 | Merchandise and add-ons at checkout | TODO | Fest T-shirts, lunch coupons and kits sold with the ticket and collected by QR. |
| UPG-179 | A verified co-curricular transcript for every student | TODO | One PDF with every event, role, rank, hours, points and certificate, verifiable by QR. |
| UPG-180 | Inter-college championship points for fests | TODO | A college-wise points table across a fest's sub-events, live on the projector. |
| UPG-181 | Accommodation and travel desk for outstation participants | TODO | Request a stay at registration; organisers allot rooms; participants get the details on their ticket. |
| UPG-182 | Clubs: members, office-bearers and club pages | TODO | Each club has a page, a member list with join requests, office-bearers and its activity report. |
| UPG-183 | On-duty (OD) attendance letters for participants | TODO | Automatic OD lists and letters to class teachers for students who attended during class hours. |
| UPG-184 | Accessibility check to WCAG 2.1 AA | TODO | An automated and manual accessibility pass of the public and student pages, with fixes. |
| UPG-185 | A weekly "what's on" digest | TODO | One opt-in weekly email/WhatsApp/push of upcoming events for each student's department and interests. |
| UPG-186 | Recurring events (weekly club meetings, lecture series) | TODO | Create a series once; each occurrence has its own registration and attendance. |
| UPG-187 | Personalised event recommendations for students | TODO | "For you" on the home page and dashboard from department, past events and interests. |
| UPG-188 | A waitlist promotion ignores group fees | TODO | Found building UPG-155. `promotion_terms` decides paid or free from `fee`/`entry_fee`, not the registrant's group fee (`routes_waitlist.py:209`). |
| UPG-189 | After a transfer, the ticket record and its wallet page keep the old holder | TODO | Found building UPG-161. The `tickets` record (`TicketService`) isn't moved, so `/ticket/wallet/<id>` still opens for the old holder, with a QR scanners refuse. |
| UPG-190 | Problem statements added after registration, released now or at a set time | DONE | The SPOC's hackathon page: statements with an optional private PDF, released now or at a time; registered teams see them once released. |
| UPG-191 | A submission form the SPOC builds, with a server-enforced window and deadline extensions | DONE | Five field kinds, opens and closes on the server's clock, the lead edits until the deadline; extend by 15 min to 7 days with a reason, shown to every team. |
| UPG-192 | AI scores and sorts the hackathon submissions | DONE | After the deadline Gemini scores each submission against the SPOC's criteria, in batches the SPOC's page drives (capped at 500 calls); bad replies are "not scored"; off without a key; judges never see it. |
| UPG-193 | The SPOC ranks the submissions and shortlists the top N | DONE | A ranking table (AI total, the SPOC's overriding score and note); top N or hand-picked shortlist with a preview and ties, through `services_rounds.advance_to`; portal notices, "Finalists announced", undo until judging starts. |
| UPG-194 | The finale: judges score the finalists, results published, the lead emailed | DONE | Judges see finalists and their submissions (no AI score); both publish paths email each team lead once (none to members); results, podium and certificates on the team's page. |
| UPG-195 | A hackathon emails participants twice: registration and the result | DONE | Portal mode (default for hackathons): the registration email with the WhatsApp group and portal instructions, password emails and the final result; every other sender becomes a portal notice or update. |
| UPG-196 | The student's hackathon page | DONE | Stages, countdowns, team, WhatsApp link, updates, problem statements and the form on one page, refreshed by a 60-second poll. |
| UPG-197 | The login page offers five roles | DONE | Admin, SPOC, Event coordinator, Judge, Student; volunteer, IQAC and department admin behind "Other staff role" (the three since taken off the menu: UPG-204). |
| UPG-198 | Hackathon rehearsal and browser checks before going live | IN PROGRESS | A 10-team rehearsal (20 emails, two per lead) and a Chromium pass at 375/1280 pass. The owner's Safari check showed the three hidden roles; the menu is now five roles only (UPG-204). Left: Firefox, Safari and an iPhone show the five, by hand (owner). |
| UPG-199 | Deploy the hackathon release | IN PROGRESS | Deployed 2026-11-06: `406f952` as `saptha-00007-j48` (rollback `saptha-00006-rmz`), migrations run, Gemini key and email limit set; health and the login menu checked live. Left: the owner's smoke checks 3 to 8 (a test hackathon end to end) and the iPhone look. |
| UPG-200 | The SPOC's blast email puts the SPOC's text into HTML unescaped | TODO | Found building UPG-195. `{name}` (participant-typed) and `{body}` go into the email HTML as is (`routes_spoc.py:1277-1278`). |
| UPG-201 | A paid hackathon in portal mode still emails the ticket and receipt | TODO | Found building UPG-195. `routes_payment.py:474-482` isn't gated by the email mode. |
| UPG-202 | The old project submission stores a session ID as its submission time | TODO | Found building UPG-191. `submitted_at` is `session.get('_id', uuid4())` (`routes_hackathon.py:93`). |
| UPG-203 | The AI summaries after the coordinator publishes results never run | TODO | Found building UPG-195. The thread uses `current_app` outside the request (`routes_coordinator.py:1215-1227`), so it raises and nothing is generated. |
| UPG-204 | The login menu has the five roles only | DONE | Owner, 2026-11-06, after Safari listed the hidden roles: Volunteer, IQAC coordinator and Department admin are off the menu, with no "Other staff role". Those accounts can't pick their role until the options come back. |
| UPG-205 | No AI chat widget on the home page | DONE | Owner, 2026-11-06: the "Sparky" button, window and "Ask Sparky" prompt are gone from the home page and its script; `/chatbot/ask` is unchanged. |
| UPG-206 | The organiser's own certificate design, with the name placed on it | DONE | Owner, 2026-11-09: upload a finished certificate design (A4, signatures already on it), drag the name box, set size and colour; the app writes each name, the number and a small QR; no signatory needed for that certificate. |
| UPG-207 | Team members confirm their email and get their own portal login | DONE | Owner, 2026-11-09: each member the lead types gets one email to confirm and set a password; the lead sees who confirmed, resends and fixes an email; organisers send links to earlier teams; members then see their own certificate. |
| UPG-208 | The organiser's certificate correction can't change a certificate's email | TODO | Found building UPG-207: a correction changes only the name, so a certificate issued to a mistyped email must be revoked and issued again. |
| UPG-209 | A team promoted from the waitlist gets no member confirmation links | TODO | Found building UPG-207: `auto_promote` creates the registration directly; the organiser's "send to waiting members" button is the only way. |
| UPG-210 | A coordinator dashboard test fails when the random event title contains "645" | TODO | Found running the full suite for UPG-207: `test_coordinator_view_counts_registrations_not_the_cached_counter` looks for "645" anywhere on the page. |
| UPG-211 | The SPOC who hosts an event cancels a team's registration before it is checked in | DONE | Owner, 2026-11-09: a reason the team sees; seat freed, waitlist promoted, ticket refused at the scanner, portal notice to each person and an email to the lead (not in portal mode); another SPOC and the coordinators get 403. |
| UPG-212 | The registration form shows exactly what the SPOC built | DONE | Owner, 2026-11-09: the SPOC adds, removes and makes required any question; only name and email are fixed; the SPOC chooses what team members are asked; choices checked against the options. |
| UPG-213 | On the SQL database a saved form loses its title, description and any key but the fields | TODO | Found building UPG-212: saving over an existing `event_forms` record keeps only `fields`. |
| UPG-214 | The SPOC quietly chooses which registered teams may attend | DONE | Owner, 2026-11-09: with the event's entry list on, only selected teams get in, through every way in; the team is never told and hears nothing more; reports don't count them absent; the scan screen keeps the list for offline scans. |
| UPG-215 | Self check-in and the manual attendance marks let a cancelled team in | TODO | Found building UPG-214: only the shared check-in refuses cancelled registrations. |
| UPG-216 | The registration page keeps the builder's title, description and order | DONE | Owner, 2026-11-09: the form the SPOC builds is the one shown. The title and description were lost on every save; phone and USN jumped to the top whatever their place. |
| UPG-217 | The SQL store keeps only a form's fields | TODO | Found building UPG-216: everything else in a saved form (title, description, type, source, author) is dropped. |
| UPG-218 | Live polls made in the same second come back in either order | DONE | Found in the full test run for UPG-214/216: `tests/test_live_polls.py` failed now and then. Times kept to the microsecond, never the same twice (`services_interact.py:43`). |
| UPG-219 | The registration form is what step 6 of the event wizard shows | DONE | Owner, 2026-11-10, with screenshots: the form made in step 6 when creating the event is the one people should register with. Step 6 adds phone and USN itself, adds the event type's template questions when the SPOC adds none, keeps "Checkboxes" as one tick box, and saves four "Also ask for" choices nothing reads. |
| UPG-220 | The builder's preview title is dark on the dark header | DONE | Found building UPG-219: "Form Preview" is navy text on the navy header. |
| UPG-221 | The walk-in desk registers a person differently from the online form | TODO | Found answering the owner, 2026-11-10: the desk asks a fixed name, USN, email and phone; not the event's questions, no team or team code, no seat limit or count, always "Paid" at the regular fee. |
| UPG-222 | The registrations export leaves out the lead's USN and phone, department, year, members' details and the form's answers | DONE | Owner, 2026-11-10, with the SAPTHAHACKS'26 sheet: Lead USN and Lead Phone empty for every team but the first, department and year empty for all, members in one cell, the form's own questions nowhere. |
| UPG-223 | A USN or phone question added by hand isn't saved as the lead's USN or phone | TODO | Found building UPG-222: registration takes them only from the ids `usn` and `phone`, so `lead_usn` and `lead_phone` stay empty (SAPTHAHACKS'26 asks them as `f_g9oz1z` and `f_voc3qf`). |
| UPG-224 | A backup Brevo account sends once the main one reaches its daily limit | DONE | Owner, 2026-11-10: the daily email limit is close to being reached; a second Brevo account as backup, working on the live site. |
| UPG-225 | The SPOC and the team lead correct a registration's details | DONE | Owner, 2026-11-10: the SPOC edits a registered student's details, and the team lead edits their own when something was entered wrong; every place that shows them must follow, and nothing else may change. |
| UPG-226 | The SPOC's registrations list shows and searches a USN no registration has | DONE | Found building UPG-225: the list reads `reg.usn` (`templates/coordinator/registrations.html:133`, search `routes_coordinator.py:162`), but the form and the walk-in desk save `lead_usn`, so the USN line is always empty and a USN search finds nothing. |
| UPG-227 | A team member sees their team's registration on their dashboard and in My events | DONE | Owner, 2026-11-10: "the team lead's dashboard shows the details but the member's shows nothing; find what the member's dashboard needs and do it". Both pages looked only for registrations the person leads. |
| UPG-228 | The activity points page and the privacy export read every registration to find a member's teams | TODO | Found building UPG-227: `routes_participant.py:1104` (`participation_ledger`, `:1036` before UPG-236) and `services_privacy.py:79` (`registrations_of`) stream the whole `registrations` collection on each request; UPG-227's `member_registrations` (`routes_participant.py:88`) finds them through the member rows. |
| UPG-229 | The SPOC's registrations list as a clear table, with Edit, Cancel and Delete buttons | DONE | Owner, 2026-11-10 (screenshot of the live list): "add an option to delete a team; the details look jumbled; a proper table with proper edit and delete options". Owner chose both a Cancel (keeps the record) and a permanent Delete. |
| UPG-230 | The SPOC sees the event's waitlist and accepts people from it | DONE | Owner, 2026-11-11: "where will the waitlist display; make sure the SPOC can accept the waitlist". The SPOC's registrations page had no waitlist (only a JSON list nothing linked to), and only "promote the first in line" existed. |
| UPG-231 | The SPOC's registrations list shows every detail the form asked | DONE | Owner, 2026-11-11: "all details mentioned in the form need to display in the SPOC portal, so it is easy to understand". The list showed name, team, members' names and contact; the form's own answers and members' USN, email and phone were only in the export. |
| UPG-232 | The waitlist's JSON list and "promote next" don't check the event | DONE | Found building UPG-230: any SPOC or coordinator could read another event's waitlist and promote its first in line. Both now check the event (`routes_waitlist.py:31`, `:178`, `:192`). |
| UPG-233 | The entry-list test's admin can't log in | DONE | Found in the full run for UPG-230: the test helper's SuperAdmin login sent no master key. It does now (`tests/test_integration_flow.py:30`); the login rule is unchanged. |
| UPG-234 | The SPOC's registrations page: Details and dialogs work, the waitlist folds away, search keeps your place | DONE | Owner, 2026-11-12: "if I search or clear, it goes back to the start and I need to scroll down; a drop-down for the waitlist; the details button is not working; easy to understand, for accessibility". The page's layout loads no Bootstrap script, so Details, Show all, Cancel, Delete and Accept did nothing. |
| UPG-235 | Accepting from the waitlist emails the person and may go past the seat limit | DONE | Owner, 2026-11-12: "if I accept the waitlist the count goes past the limit of 170, it's okay, let them; the email needs to go: you have been accepted". Accept sent the generic promotion email (none in portal mode) and didn't say the count went over. |
| UPG-236 | A person on the waitlist sees where they stand in their portal | DONE | Owner, 2026-11-12: "if the person is in the waitlist, give them access so they see whether they're still waiting or accepted". My events' Waitlisted tab read registrations only, so waitlist entries never showed; nothing told a person their place or that they'd been accepted. |
| UPG-237 | An automatic waitlist promotion in a portal-mode hackathon sends no email | DONE | Found building UPG-235: `promote_entry` emails with kind `waitlist` (`routes_waitlist.py:339`), which portal mode blocks, so a person moved up when a seat frees is registered without an email; the form still promises "We'll email you if a spot opens". |
| UPG-238 | An online screening round for the waitlist | DONE (removed by UPG-246) | Owner, 2026-11-12: "we will conduct an online round to filter the waiting list for the limited seats". The SPOC writes multiple-choice questions, opens the round, sees each waiting team's score and accepts the top N (`services_screening.py`, `routes_coordinator.py:649`, `:688`); D-13 decided. |
| UPG-239 | The SPOC gives registered teams a document: instructions, a PDF, or both | DONE | Owner, 2026-11-12: "the SPOC uploads the PDF with a box for instructions; it shows in the student portal; they download it and submit it physically". Nothing let an organiser hand teams a form such as an undertaking. |
| UPG-240 | One "you're in" email after a waitlist promotion, with the set-password link, and one reminder | DONE | Owner, 2026-11-12: "if the SPOC cancels or deletes a team the count goes down, the next on the waitlist comes in and gets the confirmation and password in one email, with a reminder". The promotion email had no login link (the join-time link lasts 48 hours) and none went out in portal mode. |
| UPG-241 | The team lead adds members up to the team limit | DONE | Owner, 2026-11-12: "if the lead registered 3 of 4, they can add one more; replace a member". Others could only join by the invite code; the lead couldn't type a member in. |
| UPG-242 | The event's own guidelines and support email on the ticket and in the emails | DONE | Owner, 2026-11-12, with the ticket's back and SAPTHAHACKS'26's 20 rules: "add some from these 20, and innovedge.snpsu@gmail.com as the support email". The ticket's back was the same for every event. |
| UPG-243 | A per-event switch: the waitlist moves up on its own, or only when the SPOC accepts | DONE | Owner, 2026-11-12: "until the SPOC accepts, a waiting team must not enter the list; stop pushing teams from the waitlist automatically, or keep a toggle". |
| UPG-244 | The SPOC adds a team by hand, straight into the list | DONE | Owner, 2026-11-12: "add the manual option for the SPOC to add the team", "manually adding the other team, then the waitlist". Only the waitlist's Accept could add a team; a team that applied by other means had to sign up itself. |
| UPG-245 | A deleted team leaves the event; the accounts stay and can sign up again | DONE | Owner, 2026-11-12: "the student who was deleted needs to be deleted from that event, but the portal account exists, and for the next event they can participate by adding manually or registering". Deleting already kept the accounts and let them sign up again; a team accepted from the waitlist then deleted still showed "Accepted: registered" on its waitlist card. |
| UPG-246 | Remove the waitlist's screening round | DONE | Owner, 2026-11-12: "remove that waitlist screening also". UPG-238's round (questions, scores, Accept the top N, the lead's answer page) is taken out; the waitlist's one-by-one Accept and the UPG-243 switch stay. |
| UPG-247 | A cancelled team that came off the waitlist still shows "Accepted" on its waitlist card | TODO | Found building UPG-245: `services_waitlist._registration` falls back to a cancelled registration (`services_waitlist.py:79`), so `standing` (`:133-144`) shows "Accepted: registered" with a link for a team the SPOC cancelled. |
| UPG-248 | A team the SPOC cancelled can't sign up again or be added by hand | TODO | Found building UPG-245: the duplicate check at submit (`routes_forms.py:922-934`) counts a cancelled registration, so its lead is told they already registered; deleting (UPG-245) lets them back. Needs the owner to say which is wanted. |

## Open items

#### UPG-30 — Paid events end to end: receipt email, refunds and cancellations
- **Status:** IN PROGRESS (built 2026-10-08; criterion 4, the owner's checkout with Razorpay test keys, is left)
- **Last verified:** 2026-10-08, commit `1b7fd7c` (end-of-Phase 2 re-verification)
- **Problem:** [C at `56a014d`] After a verified payment only a WhatsApp receipt task is queued (`routes_payment.py:356`); there's no email receipt. There's no admin action to mark a payment refunded or a paid registration cancelled; `services_finance.py:249-264` only counts `refunded` in reports. BLK-03 makes verification safe; this item makes the whole flow work.
  - **Added 2026-10-02 from the code review of PR #48 (owner)** [C at `7aac9ca`]:
    - (a) **Money taken, no registration.** `verify_payment` claims the order (marks it paid, `routes_payment.py:177`) before `_complete_registration` runs (`:197`). If completion fails (the payer is already registered, or any exception), the payer has paid but has no registration; the only trace is an audit line (`PAYMENT_UNMATCHED`, `:209`, or `PAYMENT_FAILED`, `:374`), and the browser gets a 400. Completion also doesn't re-check capacity (capacity is checked only at form submit, `routes_forms.py:606-607`), so a payment finished after the last seat went **overbooks** the event instead of failing.
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
  - **Receipt.** A completed payment with an amount queues one receipt email: amount, event, registration, payment ID (`routes_payment.py:351`, `utils_email.send_payment_receipt_email`, `utils_email.py:908`).
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
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** unchanged; criterion 4 (the owner's checkout with Razorpay test keys) goes on Part 3's go-live checklist.
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still IN PROGRESS; `routes_payment.py` unchanged since UPG-115. Criterion 4 is the owner's Test Mode checkout and refund (go-live checklist).
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still IN PROGRESS; `routes_payment.py` untouched by the certificate work. Criterion 4 is the owner's Test Mode checkout and refund.
- **Re-verified 2026-10-31 (rule 8, after UPG-149 and UPG-150, on `f6fcf99`):** still IN PROGRESS. `routes_payment.py`, `services_payments.py` and `routes_admin.py` are unchanged; `routes_ticket.py` changed only in `view_ticket` (the round status), so check-in's refusal of refunded and cancelled tickets is as cited; the admin dashboard changed only in the promote modal. Criterion 4 is the owner's Test Mode checkout and refund.
- **Re-verified 2026-10-31 (rule 8, early pass during UPG-152, because `tests/conftest.py` and `models_pg.py` changed; on `57a5922` plus UPG-152):** still IN PROGRESS. `routes_payment.py`, `services_payments.py`, `routes_admin.py` and `routes_ticket.py` are unchanged. UPG-152 changes only the paid branch of the form: a new account's set-password link is sent at submit as before (`routes_forms.py:873`), now counted against the daily limit; the ticket and receipt emails after the payment are as cited (their count is UPG-153). The new `email_quota` table is separate from `payment_orders`. Criterion 4 is the owner's Test Mode checkout and refund.
- **Re-verified 2026-11-02 (rule 8, early pass during UPG-155 to UPG-162, because `models_pg.py`, `db_pg.py` and `tests/conftest.py` changed; uncommitted on `57a5922`):** still IN PROGRESS. UPG-155 changed the payment path: order creation re-checks the ticket type's sale dates (`routes_payment.py:369,685`), completion takes the type's seat and records a sold-out payment for a refund instead of registering (`routes_payment.py:428-450`), and `services_payments.registration_fee` prices from the type, else `fee_for` as before (`services_payments.py:101-119`). The ticket and receipt emails after a payment are now at `routes_payment.py:474-479`, the paid branch's set-password link at `routes_forms.py:900`. Refunds, cancellations and the finance export are unchanged; a transfer (UPG-161) keeps the registration's payment and refund record. The criteria still hold; criterion 4 is the owner's Test Mode checkout and refund.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still IN PROGRESS. `routes_payment.py`, `services_payments.py` and `routes_admin.py` are unchanged by Phase 1. The paid branch's set-password email at submit is now `routes_forms.py:900` (UPG-155 moved it from `:873`). A paid hackathon in portal mode keeps the ticket and receipt emails (new item UPG-201).
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still IN PROGRESS. The receipt email is now `utils_email.py:908` (it had moved before Phase 2; corrected). Phase 2 didn't touch payments; a paid portal-mode hackathon is still UPG-201.

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
    - The walk-in default password in `functions/saptha_app/routes_coordinator.py:716` at HEAD (recorded under UPG-15).
    - Not a problem: a CI step's dummy service-account JSON (`sapthagiri_app/static/uploads/.github/workflows/pipeline.yml`); fake `98765…` phone numbers in seed scripts; test-only secrets and one report-table false positive (baselined in `.gitleaksignore`). There are no CSV/XLSX/SQL exports, private keys, real service-account JSON or other API keys anywhere.
  - **GitHub pull-request refs keep removed files after the force-push**, and repo owners can't delete them (only GitHub Support can). By PR number, all **47** PR refs contain at least one removed file [R, read-only fetch of GitHub's refs]:
    - PRs **#1–#5**: `instance/event_portal.db`, `__pycache__/*.pyc`.
    - PRs **#6–#47**: `.env`, `instance/event_portal.db`, `__pycache__/*.pyc`.
    - None contains `saptha_fallback.db` or `dataconnect/.dataconnect/`.
    - The remote branches `master` (all five paths), `main` (`.env`, `instance/`, `.pyc`) and `claude/busy-davinci-6nkabi` (all five) contained them too. **Fixed 2026-10-01** [R, `git ls-remote`]: GitHub's `master` is the rewritten `56a014d` (the same hash as local `master`), `production-ready` is `10207cd`, and `main` and `claude/busy-davinci-6nkabi` no longer exist. `git log origin/master origin/production-ready` finds none of the removed paths.
    - There are 0 commits reachable only from PR refs, so the PR refs add no content beyond the scanned branch history.
    - **Still on GitHub (2026-10-01):** all 47 `refs/pull/*` refs, unchanged. The owner has contacted GitHub Support.
  - **Mitigation from BLK-09:** `config.check_production_settings` (`app.py:133`, `config.py:89`; corrected 2026-11-02: the cited `validate_production_config` hasn't been called at start-up since UPG-20) refuses to start production with a published default (`_KNOWN_WEAK_SECRETS`, `config.py:33`). Both leaked values are on its blocklist [C]. A SuperAdmin account already created with the leaked password keeps it in the database.
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
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** unchanged; only GitHub Support's removal of the PR refs is left (owner).
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still IN PROGRESS; nothing in the code changes it. Only GitHub Support's removal of the old pull-request refs is left (owner; on the go-live checklist).
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still IN PROGRESS; only GitHub Support's removal of the old pull-request refs is left (owner).
- **Re-verified 2026-10-31 (rule 8, after UPG-149 and UPG-150, on `f6fcf99`):** still IN PROGRESS; nothing in this change touches it. Only GitHub Support's removal of the old pull-request refs is left (owner).
- **Re-verified 2026-10-31 (rule 8, early pass during UPG-152, because `tests/conftest.py` and `models_pg.py` changed; on `57a5922` plus UPG-152):** still IN PROGRESS; nothing in UPG-152 touches it (no secrets or tracked data files added; `tests/test_repo_hygiene.py` passes).
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still IN PROGRESS; Phase 1 adds no secrets, keys or tracked data files (`tests/test_bandit_clean.py` and the repo checks pass). Only GitHub Support's removal of the old pull-request refs is left (owner).

#### UPG-102 — 1,044 Pyrefly type errors across the app
- **Status:** TODO
- **Last verified:** 2026-10-17, after UPG-100 [R]
- **Problem:** With a working config (UPG-100), `pyrefly check` reports 1,044 errors in the app. The most are in `models_pg.py` (171, mostly SQLAlchemy `Column` typing), the report generators (`generate_*.py`, about 350), the seed scripts and `utils_certificate.py`. By kind: `bad-argument-type` 381, `unbound-name` 197, `missing-attribute` 151, `not-callable` 126, `unsupported-operation` 117. Most are type-checker noise (optional imports set to `None`, SQLAlchemy columns, dynamic proxies), but `unbound-name` and `not-callable` can hide real bugs.
- **What to build:** go through them file by file:
  - fix real bugs as their own items;
  - type the database proxies and the optional imports properly;
  - adopt SQLAlchemy 2's `Mapped[...]` in `models_pg.py`, or turn off the noise kinds there;
  - add `pyrefly check` to CI once the count is low.
- **Effort:** L · **Depends on:** UPG-100 · **Risk:** low per file; never change behaviour to quiet the checker.
- **Acceptance criteria:**
  1. Test: `pyrefly check` reports 0 errors in the routes, services and utils files, or each remaining kind is turned off with a reason in `pyrefly.toml`.
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** `pyrefly check` now reports 1,058 errors (1 suppressed), up from 1,044; the new code and tests since added the difference. Still TODO.
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO. `pyrefly check` now reports 1,081 errors (1,044 when written): 7 are in the new certificate code (`certificate_pdf.py:172`, `services_certificates.py:402`, `services_signatories.py:53-67`), all of the noise kinds above (PIL's `load()` typed as optional, qrcode's image factory, SQLAlchemy's `Result.rowcount`); the rest come from Parts 2–3.
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still TODO. `pyrefly check` reports 1,119 errors (1,081 at the end of Part 3). The certificate code adds 9, all of the known noise kinds (PIL's `load()` typed as optional, qrcode's image factory, SQLAlchemy's `Result.rowcount`, a lookup that can't be `None` after an update in `services_certificate_changes.revoke`); the one real finding (the fallback limiter without `shared_limit`) is fixed as a UPG-126 follow-up. `routes_coordinator.py` stays at 0 (`tests/test_type_check_config.py`).
- **Re-verified 2026-10-20 (end of the NAAC / reach / WhatsApp run, at `3a8fb29`):** still TODO; `pyrefly check` reports 1,139 errors (1,119 before this run), the new ones in the new modules and of the known noise kinds; `routes_coordinator.py` stays at 0.
- **Re-verified 2026-10-31 (rule 8, after UPG-149 and UPG-150, on `f6fcf99`):** still TODO. `pyrefly check` reports 1,136 errors (1,139 before); the new `services_rounds.py` has 0, `routes_coordinator.py` stays at 0, and the new `routes_forms` helpers add none (its 13 are the known optional-import and placement noise).
- **Re-verified 2026-10-31 (rule 8, early pass during UPG-152, because `tests/conftest.py` and `models_pg.py` changed; on `57a5922` plus UPG-152):** still TODO. `pyrefly check` reports 1,145 errors (1,136 before). In the changed files the new ones are: two `unbound-name` for `send_set_password_link` in `routes_participant.py` (a false positive: it is imported at `:509` and both calls, `:551` and `:573`, sit under the same `is_new_user`), SQLAlchemy's `Result.rowcount` in `services_email_quota.py`, and an unpacked `**kwargs` at `routes_admin.py:496` against the new `from_registration` parameter, all known noise kinds; the rest are in the new test file. `routes_coordinator.py` stays at 0.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO. `pyrefly check` reports 1,196 errors, the same as before Phase 1; the new `services_hackathon.py`, `routes_hackathon.py` and `tests/test_hackathon_portal.py` have 0 (two found in Phase 1's own code were fixed), and `routes_coordinator.py` stays at 0.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO. `pyrefly check` reports 1,196 errors, the same as at the end of Phase 1; the new `services_hackathon_eval.py` and the three new test files have 0 (four found in Phase 2's own code were fixed), `services_rounds.py` and `routes_hackathon.py` stay at 0, and `routes_coordinator.py` stays at 0.

#### UPG-151 — Writing an empty `scores` map keeps the old scores (postgres mode)
- **Status:** TODO
- **Last verified:** 2026-10-31, commit `f6fcf99` [R, found by `tests/test_multi_round.py` while building UPG-149]
- **Problem:** In the SQL adapter, a registration's judge scores live in their own `Score` table. `update({'scores': {...}})` adds or changes one row per judge in the map (`db_adapter.py:1530-1532`), so `update({'scores': {}})` deletes nothing; only `firestore.DELETE_FIELD` clears the rows. Firestore would replace the map with an empty one. The round panel's old advance relied on `{}` (`routes_spoc.py:1971` at `f6fcf99`), so in postgres mode round 1's scores were still counted in round 2. UPG-149 now uses `DELETE_FIELD` (`services_rounds.py:193`). No other code writes an empty map to an existing registration: `demo_reset.py:630` writes `{}` only when it creates a new one. Any future "reset the scores" code would hit the same trap.
- **What to build:** in the registrations update path, treat `scores: {}` (an empty map) as "replace with nothing": delete the registration's `Score` rows, the same as `DELETE_FIELD`. Keep merging a non-empty map judge by judge, as today, since judges' scores are written one judge at a time.
- **Effort:** S · **Depends on:** none · **Risk:** low; an empty map then means "no scores" in both backends.
- **Acceptance criteria:**
  1. Test (real database layer): a registration with two judges' scores, updated with `scores: {}`, reads back with no scores and leaves no `Score` rows.
  2. Test: updating with one judge's scores still keeps the other judge's.
- **Re-verified 2026-10-31 (rule 8, early pass during UPG-152, because `tests/conftest.py` and `models_pg.py` changed; on `57a5922` plus UPG-152):** still TODO; `db_adapter.py`, `services_rounds.py`, `routes_spoc.py` and `demo_reset.py` are unchanged, so the claims hold as cited.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO; `db_adapter.py` is unchanged and `services_rounds.py:193` still clears scores with `DELETE_FIELD`. Phase 1's round notices (`services_rounds.py:214-226`) write no scores.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; `services_rounds.py` now clears scores with `DELETE_FIELD` in the shared `_apply` (`services_rounds.py:244`), used by both `advance` and the new `advance_to` (UPG-193), so the shortlist relies on the same adapter behaviour.

#### UPG-153 — A new participant at a paid event still gets three emails
- **Status:** TODO
- **Last verified:** 2026-11-02, uncommitted on `57a5922` (lines moved by UPG-155) [C, found building UPG-152]
- **Problem:** UPG-152 brings a free registration down to one email for a new account. In the paid flow a new account gets three: the set-password link when the form is submitted, before checkout (`routes_forms.py:1093` after UPG-244), then the ticket email (`routes_payment.py:474`) and the receipt (`:479`) after the payment. Each counts against `EMAIL_DAILY_LIMIT`.
- **What to build:** after a verified payment, send one email to a new account: the ticket, the receipt and the set-password link together. Send the set-password link at submit only if the payment isn't completed (an abandoned checkout still leaves an account the person can reach). Existing accounts get the ticket and receipt together as one email.
- **Effort:** S · **Depends on:** UPG-30 (IN PROGRESS: the same code), UPG-152 · **Risk:** the receipt is a finance record; keep its content as UPG-30 built it.
- **Acceptance criteria:**
  1. Test (Razorpay mocked): a new account's paid registration sends one email after the payment, with the ticket, the receipt and a set-password link.
  2. Test: an existing account's paid registration sends one email, with the ticket and the receipt.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO; the cited lines hold (`routes_forms.py:900`, `routes_payment.py:474`). Portal-mode hackathons share the same paid path (UPG-201, which depends on this item).

#### UPG-154 — `tests/test_admin_users.py` depends on how many accounts earlier tests made
- **Status:** TODO
- **Last verified:** 2026-10-31, on `57a5922` [R, found building UPG-152]
- **Problem:** `::test_the_super_admin_sees_who_is_waiting_and_a_resend_button_only_for_them` (and one more in the file) look for a just-made account on the first page of `/admin/users`, which shows 25 a page in email order (`routes_admin.py:370`). When enough earlier tests in the same run have made accounts that sort before it, the row is on page 2 and the test fails. It fails the same way on the unchanged code with the same test selection (checked with `git stash`); it passes alone and in the normal full run, so it depends on test order, not on a bug in the page.
  - The same happens on PostgreSQL whenever `TEST_DATABASE_URL` isn't an empty database: a reused test database had 1,873 accounts left from earlier runs (328 sorting before the test's), and all three page tests in the file failed; on a fresh database they pass.
- **What to build:** find the row with the page's search (`?q=<email>`) instead of assuming page 1, or give the test's accounts addresses that sort first. Don't change the page.
- **Effort:** S · **Depends on:** none · **Risk:** none (tests only).
- **Acceptance criteria:**
  1. Test: the file passes after a test that makes 30 accounts sorting before its own.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO; `tests/test_admin_users.py` and `routes_admin.py` are unchanged. Phase 1's tests add accounts (`hklead…`, `hkspoc…`, `role…`), so the order dependence can still show.
- **Re-verified 2026-11-12 (UPG-244, uncommitted on `ddcc1a8`):** still TODO and showed again: in the full run, `::test_the_super_admin_sees_who_is_waiting_and_a_resend_button_only_for_them` failed ("waiting-…@test.edu listed 0 times") because UPG-244's new test file, then named `tests/test_add_team.py`, ran before it and with `tests/test_account_emails.py` made enough accounts sorting before its own; it passes alone and without either file. The new file is now `tests/test_spoc_add_team.py` (it runs after, with the other SPOC tests); `tests/test_admin_users.py` is unchanged. Any new test file sorting before `test_admin_users.py` that makes accounts can bring it back until this item is built.

#### UPG-163 — Call for papers with reviewer scoring (conferences)
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Whova, Hasgeek, Sched, Cvent and EventsAir run calls for papers or speakers. SapthaEvent's conference type has no submission or review flow (the phrase appears only in template text, `services_templates.py`).
- **Who benefits:** conference organisers, research deans, IQAC (NAAC research criteria).
- **What to build:** per conference: tracks, deadline, file upload (PDF, private storage, UPG-21), co-authors; assigned reviewers score against a rubric, optionally blind (author names hidden); decisions with emails; accepted papers get a session slot (UPG-159), a presenter certificate (UPG-122 types) and a proceedings export; feeds UPG-144's NAAC report.
- **Effort:** L · **Depends on:** UPG-159 (session slots) for scheduling only · **Risk:** authors' files are private; reviewers never see author identity in blind mode; reuse the judging rubric code (UPG-04) rather than a second scorer.
- **Acceptance criteria:**
  1. Test: a submission after the deadline is refused; a PDF over the size limit is refused.
  2. Test: in blind mode the reviewer page and its download contain no author name or email.
  3. Test: a reviewer sees only papers assigned to them (others 403).
  4. Test: accepting sends one email and makes the paper appear in the proceedings export.
  5. Test: an accepted paper's presenter can get a presenter certificate.

#### UPG-164 — Hackathon project gallery and a people's choice vote
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Devpost and Devfolio show every project in a permanent gallery with public voting. SapthaEvent has a submission page and kanban (`routes_hackathon.py`), but no gallery or vote.
- **Who benefits:** hackathon teams (a portfolio link), organisers (a people's choice prize).
- **What to build:** a gallery per hackathon (project name, team, summary, demo/repo links, screenshot), visible when the organiser publishes it; a voting window where each logged-in voter (optionally checked-in only) votes once and teams can't vote for themselves; a people's choice result that can award a special-mention certificate (UPG-142); each project has a share card (UPG-146).
- **Effort:** M · **Depends on:** none · **Risk:** vote stuffing: one vote per account, accounts created after the window opens can be excluded, own team excluded.
- **Acceptance criteria:**
  1. Test: an unpublished gallery is 404 to the public.
  2. Test: a person votes once; a second vote replaces or is refused (as decided); team members can't vote for their own project.
  3. Test: the people's choice result matches the votes and can issue a special-mention certificate.
  4. Test: project text with HTML shows as text.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO. Projects now have a SPOC-built submission (UPG-191): answers by field in `project_submissions` (`extra_json`), link fields checked as `http(s)`, PDFs in private storage. The gallery should read those answers and show only fields the SPOC marks public; private PDFs stay private.

#### UPG-165 — Mentor office hours for hackathons
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Devfolio and HackerEarth hackathons, Reskilll and EventBeep offer mentor sessions. SapthaEvent has no mentor role or booking.
- **Who benefits:** hackathon and ideathon teams, alumni and industry mentors.
- **What to build:** a Mentor staff role per event (assigned like judges, UPG-29); mentors set expertise and time slots; team leads book one slot at a time; reminders by push/WhatsApp; the organiser sees bookings per mentor; mentors can't judge teams they mentored (feeds UPG-166).
- **Effort:** M · **Depends on:** UPG-166 for the mentor–judge conflict rule · **Risk:** none beyond the usual permission checks.
- **Acceptance criteria:**
  1. Test: two teams can't book the same slot (also at the same instant).
  2. Test: only team leads book; a team holds at most one future slot.
  3. Test: removing a mentor ends their access and cancels their future bookings with a notice.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO. In a portal-mode hackathon (UPG-195) booking notices go through `services_hackathon.notify`, not email; the team's page (UPG-196) is where a booking would show.

#### UPG-166 — Judges declare conflicts of interest
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: fair-judging is standard on Devpost and enterprise awards tools. SapthaEvent's own journey table lists judge conflicts of interest as MISSING (archive, section 3, Judge).
- **Who benefits:** judges, organisers, participants (trust in results).
- **What to build:** before scoring, a judge can declare a conflict with any team (and mentors are conflicted with their teams, UPG-165); conflicted pairs can't be scored; ranking uses the average of the scores a team received so missing judges don't lower it; the organiser sees conflicts and reassigns.
- **Effort:** S · **Depends on:** none · **Risk:** ranking change: the leaderboard (UPG-84) must use averages consistently everywhere.
- **Acceptance criteria:**
  1. Test: a conflicted judge's score for that team is refused.
  2. Test: a team with 2 of 3 judges scoring ranks by the average, the same on every board and export.
  3. Test: the organiser sees each declared conflict.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO; the judging code is unchanged by Phase 1. UPG-194 (finale judging) should build on it.

#### UPG-167 — Volunteer sign-up and shift rota
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Whova, Sched and Hasgeek run volunteer sign-ups and shifts (9 of 38 mention volunteer tools). SapthaEvent's volunteers are appointed by staff only (UPG-120); there's no application, shift or volunteer-hours flow.
- **Who benefits:** fest and event organisers, student volunteers (activity points/NSS hours).
- **What to build:** a volunteer call per event with roles and shifts (time, place, count); students apply; the organiser approves and assigns; volunteers see their shifts and get reminders; shift check-in on the scanner; hours and points credited to the UPG-11 ledger; a volunteer certificate type.
- **Effort:** M · **Depends on:** none · **Risk:** volunteer accounts get check-in rights only for their assigned event and shifts (BLK-18).
- **Acceptance criteria:**
  1. Test: a full shift refuses more volunteers.
  2. Test: an approved volunteer can check in only at their event, during their shift window.
  3. Test: attended shifts credit hours to the ledger once.
  4. Test: a rejected applicant has no staff access.

#### UPG-168 — Event budget, expenses and approval
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Cvent, Whova, EventMobi and EventsAir track budgets. Colleges approve an event's budget with its proposal; SapthaEvent has income reporting (`services_finance.py`) but no budget or expenses.
- **Who benefits:** SPOCs, department heads, the finance office, IQAC.
- **What to build:** a budget (heads: venue, prizes, food, travel, printing, guest honorarium; income: fees, sponsors, grants) entered in the wizard and reviewed with the event; expenses with bill uploads (private storage) after approval; budget vs actual on the event report and a finance export; overspend over a set percentage needs approval.
- **Effort:** M · **Depends on:** none · **Risk:** bills are finance records: keep them with the payment-order retention (D-7).
- **Acceptance criteria:**
  1. Test: the review page shows the budget; approving the event approves its budget.
  2. Test: an expense over the overspend limit stays pending until approved.
  3. Test: budget vs actual totals match the expenses and the event's real fee income.
  4. Test: only the event's owner and finance roles can see the bills (others 403).

#### UPG-169 — Sponsor tiers, deliverables and sponsor reports
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: 17 of 38 platforms manage sponsors and exhibitors. SapthaEvent has an admin sponsor list (`routes_sponsors.py:33-116`) shown on event pages (`templates/public/_event_content.html:113`), with no tiers, deliverables or reporting.
- **Who benefits:** fest organisers raising money; sponsors who need proof of reach.
- **What to build:** sponsors attached to events with a tier (title, gold, silver, partner), amount and deliverables (logo on page, banner, stall, certificate logo, mention); logos placed by tier on the event page, share cards and (optionally) certificates; a sponsor report PDF from real counts (page views, registrations, attendance, source links from UPG-162); sponsorship income feeds UPG-168.
- **Effort:** M · **Depends on:** UPG-168 for income totals (the rest works without) · **Risk:** only real counts in the report (UPG-65's rule).
- **Acceptance criteria:**
  1. Test: logos appear on the event page ordered by tier.
  2. Test: the sponsor report's numbers equal the event's real counts.
  3. Test: a sponsor with `certificate_logo` appears on that event's certificates and no others.

#### UPG-170 — Event photo gallery
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: KonfHub (AI gallery), Whova, Accelevents and District show event photos. SapthaEvent lets coordinators paste media URLs only (`routes_coordinator.py:928-940`, corrected 2026-11-12 by the rule 8 check for UPG-239 to UPG-241; it cited `:310-322`, which no longer pointed at it).
- **Who benefits:** attendees, the college's social media team, IQAC (geotagged photos are NAAC evidence).
- **What to build:** photo upload by the event's staff (resized, re-encoded, EXIF stripped except date, private bucket with signed links, UPG-21); a gallery on the event page after the event; attendees download and share; selected photos attach to the NAAC post-event report (UPG-144); staff can remove any photo; a takedown request link.
- **Effort:** M · **Depends on:** none · **Risk:** faces of students are personal data: organiser-only uploads, takedown, no face recognition (DPDP).
- **Acceptance criteria:**
  1. Test: an uploaded photo is re-encoded with GPS removed and served through a signed link.
  2. Test: only the event's staff can upload or delete (others 403).
  3. Test: a photo selected as evidence appears in the NAAC report export.
  4. Test: a takedown request reaches the organiser and hides the photo once accepted.

#### UPG-171 — Outgoing webhooks and a Google Sheets sync
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: 14 of 38 offer API/webhooks and 24 integrations (Zapier, n8n). SapthaEvent receives webhooks (Razorpay, WhatsApp) but sends none; API v1 exists but isn't documented for outsiders (inventory: NOT CONNECTED).
- **Who benefits:** departments and clubs that already use Sheets, the IT cell.
- **What to build:** per event or org unit: webhook URLs with a signing secret for `registration.created`, `checkin.created`, `payment.captured`, `results.published`; delivery through the outbox with retries (UPG-18); a delivery log; a Google Sheets sync that appends rows (service account); documented API v1 with per-unit API keys.
- **Effort:** M · **Depends on:** none · **Risk:** outgoing data is personal data: only the event's owner sets webhooks; HTTPS only; no private IPs (SSRF).
- **Acceptance criteria:**
  1. Test: a registration sends one signed webhook; the signature verifies with the secret.
  2. Test: a failing endpoint is retried through the outbox and logged.
  3. Test: a webhook URL to localhost or a private IP is refused.
  4. Test (Sheets mocked): a check-in appends one row to the event's sheet.

#### UPG-172 — A registration widget for other websites
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: KonfHub, Luma, Ticket Tailor and Eventzilla offer embed widgets. SapthaEvent has no embed.
- **Who benefits:** departments, clubs, partner colleges.
- **What to build:** an embed page per event (card: title, date, seats left, register button) and per org unit (its upcoming events), loaded in an iframe from a copy-paste snippet; the register button opens the full form in a new tab (no form inside the iframe, to keep CSRF and cookies simple); CSP `frame-ancestors` allows only the embed pages to be framed.
- **Effort:** S · **Depends on:** none · **Risk:** clickjacking: only the read-only embed pages may be framed; every other page keeps `frame-ancestors 'none'`.
- **Acceptance criteria:**
  1. Test: the embed page answers with a `frame-ancestors *` (or allow-list) policy and other pages still deny framing.
  2. Test: a campus-only event's embed shows nothing to anonymous visitors.
  3. Test: the unit embed lists only that unit's open events.

#### UPG-173 — Kannada and Hindi interface
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: 11 of 38 platforms offer several languages; almost no Indian campus platform offers Kannada. SapthaEvent has `i18n.py` with `hi` and `kn` dictionaries (`i18n.py:146,212`) but only `en` is enabled (`SUPPORTED_LOCALES`, `i18n.py:12`).
- **Who benefits:** students and parents more comfortable in Kannada or Hindi; outreach events.
- **What to build:** enable `kn` and `hi`; translate the student journey (home, event page, registration form, ticket, feedback, certificates page, emails' fixed text); a language switch in the app bar; event content stays in the organiser's language; dates and numbers formatted per locale.
- **Effort:** M · **Depends on:** none · **Risk:** layout: Kannada text is longer; check 375px pages (UPG-28).
- **Acceptance criteria:**
  1. Test: choosing Kannada shows the registration form's labels in Kannada and keeps the choice across pages.
  2. Test: every string key in `en` exists in `kn` and `hi` for the student journey templates.
  3. Test (headless, 375px): the Kannada registration form has no sideways scroll.

#### UPG-174 — Teammate matching on real profiles
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: 18 of 38 platforms advertise networking or matchmaking; Devfolio matches hackers into teams. SapthaEvent's matchmaker suggests hard-coded `MOCK_STUDENTS` (`routes_matchmaker.py:19,122`) and is hidden behind `FEATURE_MATCHMAKER`.
- **Who benefits:** students looking for teammates for hackathons and competitions.
- **What to build:** opt-in "looking for a team" per event with skills and a short line; suggestions from other opted-in registrants by complementary skills (rule-based; AI ranking optional); a contact request that shares details only when accepted; delete `MOCK_STUDENTS`; remove the flag once real.
- **Effort:** M · **Depends on:** none · **Risk:** privacy: nobody is listed without opting in; no email or phone shown before acceptance.
- **Acceptance criteria:**
  1. Test: only opted-in registrants of the same event are suggested.
  2. Test: contact details are shown only after the other person accepts.
  3. Test: no mock student appears anywhere (grep and page).

#### UPG-175 — AI writing help for organisers
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Airmeet, Goldcast, Glue Up and EventsAir generate event copy, summaries and social posts. SapthaEvent has a generator endpoint (`routes_ai_features.py:32` `/generate_event_details`) that no page calls, and a post-event debrief with a fallback (`routes_spoc.py:1137-1156`); UPG-85 (results summaries) was dropped.
  - **Corrected 2026-11-02 (found building UPG-155):** the wizard already has a "Write with AI" button for the description and rules (`templates/spoc/create_event.html:141-148`; `static/js/pages/spoc__create_event.js:163-180`) calling `POST /spoc/marketing/event_writer` (`routes_spoc.py:2448`). It writes straight into both fields (no accept step), and with no `GEMINI_API_KEY` it fills them with a fixed generic text instead of hiding. So this item changes that button rather than adding one.
- **Who benefits:** SPOCs and coordinators writing every event from scratch.
- **What to build:** the wizard's existing "Write with AI" button shows its draft for the organiser to accept before it fills the description and rules, and is hidden with no AI key (no fixed text); social post drafts (Instagram, LinkedIn, WhatsApp) from the event page; the post-event summary from real counts; every AI call has a timeout, a plain fallback and never invents facts (UPG-108's rule); off when no AI key is set.
- **Effort:** S · **Depends on:** none · **Risk:** AI text is a draft: never saved or published without the organiser's edit/accept.
- **Acceptance criteria:**
  1. Test (AI mocked): the wizard button fills the field only after accept.
  2. Test: with no AI key the button is hidden and nothing errors (UPG-109).
  3. Test: the prompt contains only the event's real fields; the summary's numbers equal the report's.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the event writer route is now `routes_spoc.py:2448` (corrected).

#### UPG-176 — Live stream and recordings on the event page (replaces the invented live pages)
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: 24 of 38 support virtual or hybrid events with streams and recordings. SapthaEvent's webinars show a meeting link (UPG-73), and `/live/streams` and `/live/reels` (`routes_live.py:190`) show invented viewer and like counts (open decision D-8).
- **Who benefits:** remote attendees, outstation students, alumni.
- **What to build:** a stream URL (YouTube Live or Meet) per event or session, embedded on the event page while live (campus-only events only to logged-in campus users); the recording URL afterwards; online attendance counted from "Join" clicks; retire `/live/streams` and `/live/reels` once this exists.
- **Effort:** S · **Depends on:** D-8 (the owner's decision on the invented pages) · **Risk:** only real counts (UPG-65).
- **Acceptance criteria:**
  1. Test: the embed shows during the event window and the recording after.
  2. Test: a campus-only event's stream isn't shown to anonymous visitors.
  3. Test: `/live/streams` and `/live/reels` no longer show invented numbers (removed or redirected).

#### UPG-177 — Reserved seating for auditorium events
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Ticket Tailor, Luma, Swapcard and vFairs offer seat maps (8 of 38). SapthaEvent has rooms with capacity (UPG-09) but no seats.
- **Who benefits:** cultural nights, convocations, guest lectures in the auditorium.
- **What to build:** a seat map per room (rows, seat numbers, blocked and VIP seats); events in that room can turn on reserved seating; the form shows free seats; a seat is held while paying (UPG-30) and released on failure; the ticket, badge (UPG-158) and scanner show the seat.
- **Effort:** L · **Depends on:** UPG-155 for priced seat sections · **Risk:** two people taking one seat: hold with a database constraint, not a read-then-write.
- **Acceptance criteria:**
  1. Test: two registrations for the same seat at the same instant: one wins, one is told to pick again.
  2. Test: a held seat is released when the payment fails or times out.
  3. Test: the ticket and the scanner show the seat.

#### UPG-178 — Merchandise and add-ons at checkout
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Ticket Tailor, Whova and Eventzilla sell add-ons and merchandise with tickets. SapthaEvent's checkout sells only the registration.
- **Who benefits:** fest organisers (income), participants.
- **What to build:** add-ons per event (name, price, stock, sizes); chosen on the form and added to the server price; a collection counter on the scanner ("T-shirt M — collected"); stock and sales in the finance export.
- **Effort:** M · **Depends on:** UPG-155 (line items at checkout) · **Risk:** money: server-side totals only (BLK-03); stock decremented atomically.
- **Acceptance criteria:**
  1. Test: the order total equals ticket + add-ons, computed on the server.
  2. Test: an out-of-stock add-on is refused at completion.
  3. Test: collection is recorded once per item.

#### UPG-179 — A verified co-curricular transcript for every student
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Beyond the Indian market: CampusGroups and Anthology Engage offer co-curricular transcripts in the US; Indian platforms don't. SapthaEvent already has the parts: the ledger (UPG-11), certificates and verification (UPG-122–UPG-128) and the portfolio page (`routes_portfolio.py:38`).
- **Who benefits:** students (placements, higher studies), placement cell, IQAC.
- **What to build:** a transcript PDF per student and academic year: events attended, roles (participant, volunteer, organiser, winner), hours and points by category, certificates with numbers; a verification QR/URL like `/verify`; the student chooses what's public; the placement cell can download transcripts of shortlisted students with consent.
- **Effort:** M · **Depends on:** none · **Risk:** only verified records (checked-in, issued certificates); no self-reported entries.
- **Acceptance criteria:**
  1. Test: the transcript lists exactly the student's attended events, ledger hours and issued certificates.
  2. Test: its verification URL shows valid and the same totals; a tampered number shows not found.
  3. Test: another student can't download it (403).

#### UPG-180 — Inter-college championship points for fests
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Beyond the market: Indian fests award an overall championship by college; no platform read does this. SapthaEvent has fests with sub-events (UPG-74, `parent_event_id`, `app.py:1009`) and external colleges (UPG-146), but no points per college.
- **Who benefits:** fest organisers, visiting colleges.
- **What to build:** per fest: points for 1st/2nd/3rd (and participation) per sub-event, set in the wizard; points go to the winner's college from published results; a college leaderboard page and projector view (reuse `routes_live.py`); an overall-champion certificate type; college names normalised (pick from a list, not free text).
- **Effort:** M · **Depends on:** none · **Risk:** college name spelling: use a managed list so points aren't split.
- **Acceptance criteria:**
  1. Test: publishing a sub-event's results adds the configured points to each winner's college once.
  2. Test: re-publishing or correcting results updates the table, not double-counts.
  3. Test: the college table sums correctly across sub-events and ties share points as configured.

#### UPG-181 — Accommodation and travel desk for outstation participants
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Beyond the market: Indian inter-college fests and conferences house outstation students; no platform read handles it. SapthaEvent only suggests an "accommodation" question in the form builder (`routes_forms.py:1355`; was `:1251` before Phase 1).
- **Who benefits:** outstation and external participants, fest hospitality teams.
- **What to build:** an accommodation option per event (dates, fee or free, gender-wise blocks); participants request it at registration; the hospitality team allots rooms/beds and marks check-in/out; details on the ticket and confirmation; exports for the hostel office.
- **Effort:** M · **Depends on:** UPG-155 for a priced stay (free stays work without) · **Risk:** personal safety: gender-wise allotment and contact details only to the hospitality team.
- **Acceptance criteria:**
  1. Test: a request is stored with the registration and listed for the hospitality team only.
  2. Test: a full block refuses more allotments.
  3. Test: the ticket shows the allotted room after allotment.

#### UPG-182 — Clubs: members, office-bearers and club pages
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: campus platforms (CampusGroups, Anthology Engage, Presence) are built around clubs and memberships. SapthaEvent's org units can be clubs (`routes_admin.py`), but the event-type table notes "Membership not yet listed".
- **Who benefits:** club coordinators, students, student affairs.
- **What to build:** a public club page (about, office-bearers, upcoming and past events); join requests approved by the club's coordinator; members get club-only events and announcements; office-bearer roles per academic year; a yearly club activity report for IQAC.
- **Effort:** M · **Depends on:** none · **Risk:** members-only events must respect the existing visibility checks (UPG-73).
- **Acceptance criteria:**
  1. Test: a join request becomes a membership only when the club coordinator approves.
  2. Test: a members-only event is hidden from and refuses non-members.
  3. Test: the club report counts the club's events and attendance correctly.

#### UPG-183 — On-duty (OD) attendance letters for participants
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Beyond the market: Indian colleges grant on-duty attendance for official events; it is done on paper today. No platform read offers it; SapthaEvent has no OD flow.
- **Who benefits:** students (attendance shortage), faculty mentors, HoDs.
- **What to build:** per event: "OD eligible" with its hours; after the event, OD lists by department, year and section from real check-ins (and session check-ins, UPG-159); signed PDF letters for HoDs and class teachers; students see their OD record; an export for the attendance system.
- **Effort:** S · **Depends on:** none · **Risk:** only checked-in students; the organiser certifies the list before it's sent.
- **Acceptance criteria:**
  1. Test: the OD list contains exactly the checked-in students, grouped by department and section.
  2. Test: nothing is sent until the organiser certifies the list.
  3. Test: a student sees their own OD records only.

#### UPG-184 — Accessibility check to WCAG 2.1 AA
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: 12 of 38 platforms state accessibility compliance (Cvent, Eventbrite, Humanitix, Ticket Tailor). SapthaEvent has skip links and visible focus (UPG-27, `templates/base_classic.html:31`) but no audit.
- **Who benefits:** students with disabilities; government and accreditation requirements.
- **What to build:** run axe-core on every public and student page in the browser pass; fix contrast, labels, landmarks and keyboard traps; check the registration form and scanner with a screen reader; add an accessibility statement page.
- **Effort:** M · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. Test (headless with axe-core): no serious or critical violations on home, event page, registration form, ticket and certificates page.
  2. Test: the registration form can be completed with the keyboard only.
  3. Test: the accessibility statement page is linked from the footer.

#### UPG-185 — A weekly "what's on" digest
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Luma sends calendar newsletters; Meetup and Bevy send group digests. SapthaEvent sends per-event notices only.
- **Who benefits:** students (discovery), organisers (more registrations without spamming).
- **What to build:** a weekly digest job (cron, UPG-07) listing the next 7 days' open events the student can register for (visibility rules), ordered by department and interests; opt-in and one-click unsubscribe; counted against `EMAIL_DAILY_LIMIT` and the WhatsApp cap (UPG-147), skipping when over.
- **Effort:** S · **Depends on:** none · **Risk:** the email limit (UPG-152): send in batches within the daily limit, never starve ticket emails.
- **Acceptance criteria:**
  1. Test: a student gets only events they can see and register for.
  2. Test: unsubscribed students get nothing; the link unsubscribes without login.
  3. Test: when the daily limit is near, the digest stops and ticket emails still go.

#### UPG-186 — Recurring events (weekly club meetings, lecture series)
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Market: Accelevents, Cvent, EventsAir, Glue Up, Luma and Ticket Tailor support recurring or repeatable events. SapthaEvent can clone an event (`routes_spoc.py:1301`; was `:1285` before Phase 1) but has no series.
- **Who benefits:** clubs, departments running lecture series, NSS weekly activities.
- **What to build:** a repeat rule in the wizard (weekly/monthly, count or end date); occurrences created as linked events with one approval for the series; register for one or all; series attendance on the student's record and ledger.
- **Effort:** M · **Depends on:** none · **Risk:** approval: one approval covers the series; edits to one occurrence don't change others unless chosen.
- **Acceptance criteria:**
  1. Test: a weekly series of 6 creates 6 linked occurrences on the right dates (IST).
  2. Test: approving the series opens all occurrences.
  3. Test: cancelling one occurrence notifies only its registrants.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the clone route is now `routes_spoc.py:1301` (corrected).

#### UPG-187 — Personalised event recommendations for students
- **Status:** TODO
- **Last verified:** 2026-11-02, on `57a5922` plus UPG-152's uncommitted work [C, market analysis 2026-11-02]
- **Problem:** Beyond the market for colleges: discovery sites (AllEvents, KnowAFest) recommend by city; campus platforms don't personalise well. SapthaEvent's home page lists events by date only.
- **Who benefits:** students (find events they'd attend), organisers (fill seats).
- **What to build:** a "For you" list from rules: own department's events, categories the student attended or saved, friends' (teammates') registrations; explained ("because you attended X"); no AI needed; the student can hide a category.
- **Effort:** S · **Depends on:** none · **Risk:** privacy: never reveal who registered; only use the student's own history.
- **Acceptance criteria:**
  1. Test: a CSE student who attended two hackathons sees an upcoming hackathon first.
  2. Test: events the student can't see (department-only, campus-only) never appear.
  3. Test: a hidden category stops appearing.

#### UPG-188 — A waitlist promotion ignores group fees
- **Status:** TODO
- **Last verified:** 2026-11-02, uncommitted on `57a5922` [C, found building UPG-155]
- **Problem:** `routes_waitlist.promotion_terms` (`routes_waitlist.py:209`) decides whether a promotion is paid from the event's `fee` or `entry_fee` only. On an event without ticket types priced per group (`fees`, UPG-73: e.g. students free, faculty Rs 500), a promoted faculty member is confirmed free, and a promoted student is held for payment when `fee` is set although their group's fee is 0. The registration form prices the same person with `services_payments.registration_fee` (`routes_forms.py:1027` after UPG-244; cited as `:834`, `:833` before). Events with ticket types already use the type's price (UPG-155).
- **Who benefits:** the finance office; organisers of group-priced events with a waitlist.
- **What to build:** decide with `registration_fee(event, participant_type, ticket_type_id, members)` from the waitlist entry's `reg_data`, as the form does.
- **Effort:** S · **Depends on:** none · **Risk:** money: the server-side price stays the only price (BLK-03).
- **Acceptance criteria:**
  1. Test: on a group-priced event, a promoted faculty member is held for payment and a promoted student whose group fee is 0 is confirmed free.
  2. Test: an event with ticket types, and one with a single fee, promote exactly as before.

#### UPG-189 — After a transfer, the ticket record and its wallet page keep the old holder
- **Status:** TODO
- **Last verified:** 2026-11-02, uncommitted on `57a5922` [C, found building UPG-161]
- **Problem:** A free registration and a free waitlist promotion also get a `tickets` record from `TicketService.issue_ticket` (`routes_forms.py:1125` after UPG-244, `routes_waitlist.py:333` after UPG-243, was `:292` before UPG-230; `services_ticket.py:139`) holding the lead's email and name and its own signed QR. `services_transfer.transfer` (`services_transfer.py:128`) updates only the registration. After a transfer the old holder can still open `/ticket/wallet/<ticket id>` (owner by the record's email, `routes_ticket.py:831-853`) and sees a pass whose QR every scanner refuses (that token has no ticket generation, so `token_is_current` is false); the new holder can't open it. Entry stays safe; the page and the record are wrong.
- **Who benefits:** both people in a transfer; organisers reading the `tickets` counts (`services_analytics.py:106`).
- **What to build:** on transfer, move the registration's `tickets` records to the new holder and give them a current QR (or mark the old one replaced and issue a new one); the wallet page tells the old holder the ticket was transferred.
- **Effort:** S · **Depends on:** UPG-161 (DONE) · **Risk:** a QR from the old record must stay refused.
- **Acceptance criteria:**
  1. Test: after a transfer the old holder's `/ticket/wallet/<id>` says the ticket was transferred (or 403) and shows no QR; the new holder's shows a QR the scanner accepts.
  2. Test: the old record's QR is still refused at check-in.

#### UPG-198 — Hackathon rehearsal and browser checks before going live
- **Status:** IN PROGRESS (criteria 1 and 2 met; criterion 3 needs the owner's devices)
- **Last verified:** 2026-11-06, uncommitted on `57a5922` [T]
- **Problem:** Phase 1 was tested over HTTP; nobody had used the pages in a browser, on a phone, or end to end with real timing.
- **What was built:**
  - **The rehearsal** (`tests/test_hackathon_rehearsal.py`, real database layer, Gemini replaced): 10 teams register through the public form `/forms/submit/<id>` (each lead a new account with a team member); one problem statement released now and one at 12:00 IST that appears when the clock passes it; the form opens; 9 teams submit, one edits before the deadline (2 versions, the edit is what gets scored); a late team is refused, the SPOC extends by an hour with a reason the team sees, the late team submits; after the new deadline an edit is refused; AI scores all 10 through the page's batches; the top 4 are shortlisted; an eliminated team sees it is out; the judge lists exactly the 4 finalists and scores them; the SPOC publishes. 20 emails in all: the registration email and the result email to each lead, none to a member; publishing again sends none; each team's page shows its outcome and the podium.
  - **The browser pass** (`tests/test_hackathon_browser.py`, headless Chromium against the app on a local server, outside requests blocked): the login page, the SPOC's hackathon page (before and after "Add field", then the extension form submitted from the page) and the team's page (the countdown running), each measured at 375 and 1280 with UPG-23's measure, the pinned-footer and the heading-contrast checks, with screenshots (`$HACK_SHOTS`); no page error and no console error.
  - **iOS Safari:** Safari ignores `hidden` on an `<optgroup>`. A script that took the group out of the menu was tried first; the owner's Safari still showed the three roles, and the owner asked for the five only, so the group, the button and the script are gone (UPG-204).
  - **The home page** is in the browser pass since UPG-205: no chat widget, no script error after the old 2-second prompt time.
- **Effort:** S · **Depends on:** UPG-192, UPG-193, UPG-194 (DONE) · **Risk:** none (checks).
- **Acceptance criteria:**
  1. ✅ The rehearsal completes with the expected emails only: one at registration per lead and one result per lead (`tests/test_hackathon_rehearsal.py::test_ten_teams_run_the_whole_hackathon_with_two_emails_each`).
  2. ✅ Screenshots at 375 and 1280 of the three pages with no layout overflow and no console errors (`tests/test_hackathon_browser.py::test_the_hackathon_pages_work_and_fit_a_phone_and_a_desktop`; checked by eye on 2026-11-06).
  3. ◐ The login menu shows five roles: tested in Chromium (same test). On 2026-11-06 the owner's Safari showed the three hidden roles indented under the five, and asked for the five only; the menu now has no other option, group or button (UPG-204), so nothing depends on a browser honouring `hidden`. **Left for the owner:** Firefox, Safari on a Mac, and Safari on an iPhone: open `/login`; the menu lists Admin, SPOC, Event coordinator, Judge and Student, nothing else.

#### UPG-199 — Deploy the hackathon release
- **Status:** IN PROGRESS (deployed; smoke checks 3 to 8 left for the owner)
- **Last verified:** 2026-11-06, `406f952` live as revision `saptha-00007-j48` [T for criterion 1; R for checks 1 and 2]
- **Problem:** The owner asked for the hackathon flow to be deployed after approval. The live service runs on Cloud Run (`saptha-event-261017`), deployed by the owner from Cloud Shell; the agent doesn't deploy.
- **What was built:** "Hackathon release (UPG-199)" in `docs/DEPLOY.md`: commit and push first (Cloud Shell builds from GitHub); note the current revision as the rollback target; a manual Cloud SQL backup; build; update and run the `saptha-migrate` job (every migration not yet applied: `0009` if missing, `0010` to `0014`, all additive, so the old revision keeps working); the Gemini key as a Secret Manager secret (typed without echo, never pasted elsewhere), `EMAIL_DAILY_LIMIT`, and checks that `STORAGE_TYPE=gcs`, `GCS_BUCKET_NAME` and fine-grained bucket access are in place for private PDFs; `gcloud run deploy` with `--update-env-vars` / `--update-secrets` (not `--set-…`, which would drop the other settings); eight smoke checks on the live URL (health, the login menu including on an iPhone, a test hackathon end to end with one registration email, a PDF, an extension, AI scoring and an undone shortlist, the email count, then cancel the test event); the rollback command. No new setting, so `.env.example` is unchanged.
- **Effort:** S · **Depends on:** UPG-198; the owner's approval to deploy · **Risk:** migrations before traffic; the rollback revision is noted in step 1.
- **Acceptance criteria:**
  1. ✅ `docs/DEPLOY.md` lists the steps, variables and smoke checks; `tests/test_production_boot.py` passes (6 passed, 1 skipped, 2026-11-06).
  2. ◐ The owner runs it; the smoke checks pass on the live URL (recorded with the revision name). **Deployed 2026-11-06** by the owner from Cloud Shell: `406f952` as revision `saptha-00007-j48`, 100% of traffic (rollback: `saptha-00006-rmz`); a manual Cloud SQL backup of `saptha-db` first; `saptha-migrate` execution `saptha-migrate-564kt` succeeded (1 succeeded); `EMAIL_DAILY_LIMIT=270`; `GEMINI_API_KEY` from Secret Manager (`:latest`; version 1 was exposed in a terminal command and replaced). Checked from here on the live URL [R]: check 1 (`/health/ready` → `{"ready":true}`) and check 2 (the login menu is the five roles; the home page answers 200 with no chat widget; the live `login.js` has no hidden-role code). **Left for the owner:** the iPhone look at the login menu (UPG-198) and checks 3 to 8 (a test hackathon end to end: one registration email, a PDF submission, an extension, AI scoring, an undone shortlist, `/diag/email`, then cancel the test event).

#### UPG-200 — The SPOC's blast email puts the SPOC's text into HTML unescaped
- **Status:** TODO
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [C, found building UPG-195]
- **Problem:** `blast_email` builds the email with `{name}` (the registrant's `lead_name`, typed by the participant) and `{body}` (the SPOC's text) straight into the HTML (`routes_spoc.py:1277-1278`; the preview builds `{body}` the same way, `:1216`). A lead's name like `<a href=…>` becomes a link in the email the SPOC sends, and the SPOC's own text renders as HTML. In portal mode (UPG-195) the blast becomes a portal update, which the page escapes; for every other event the email is still built this way.
- **What to build:** escape `name` and `body` with `utils_email._e` (keeping line breaks with `white-space:pre-wrap`, as now); escape the subject in the wrapper's title.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a lead named `<b>x</b>` and a body with `<script>` arrive escaped in the sent HTML; line breaks are kept.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the blast builds `{name}` and `{body}` into the HTML at `routes_spoc.py:1277-1278` and the preview at `:1216` (corrected). Portal-mode hackathons still post it as an escaped update.

#### UPG-201 — A paid hackathon in portal mode still emails the ticket and receipt
- **Status:** TODO
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [C, found building UPG-195]
- **Problem:** UPG-195 assumed the hackathon is free (owner's default). After a verified payment, `routes_payment.py:474-482` still sends the ticket email and the receipt, unchecked by `email_allowed`. A new account at a paid portal-mode hackathon gets three emails (the set-password email at submit, then the ticket and the receipt, which carry no "check the portal" instructions), as UPG-153 describes for every paid event.
- **What to build:** in portal mode, after payment send one email: the receipt with the instructions block (and the set-password link for a new account, with UPG-153); no ticket email (the ticket is on the portal).
- **Effort:** S · **Depends on:** UPG-153, UPG-30 (the same code) · **Risk:** the receipt is a finance record; keep its content.
- **Acceptance criteria:**
  1. Test (Razorpay mocked): a paid portal-mode hackathon registration sends one email after payment, with the receipt and the instructions; no ticket email.

#### UPG-202 — The old project submission stores a session ID as its submission time
- **Status:** TODO
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [C, found building UPG-191]
- **Problem:** The old fixed submission form (still used by a hackathon without a SPOC-built form) writes `'submitted_at': session.get('_id', str(uuid.uuid4()))` (`routes_hackathon.py:93`; the same at `57a5922`, `:86`), so `submitted_at` holds a session or random ID, not a time. Anything sorting or showing submissions by time gets nonsense for those rows.
- **What to build:** store the UTC time, as UPG-191's form does; leave existing rows (or show them as "unknown").
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a submission through the old form has an ISO time as `submitted_at`.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the old form's `submitted_at` is now `routes_hackathon.py:93` (corrected). The Phase 2 ranking reads only the SPOC-built form's submissions, which store a real time.

#### UPG-203 — The AI summaries after the coordinator publishes results never run
- **Status:** TODO
- **Last verified:** 2026-11-05, uncommitted on `57a5922` [R, found by `tests/test_hackathon_portal.py` while building UPG-195]
- **Problem:** `routes_coordinator.publish_results` starts a background thread whose function opens `current_app.app_context()` (`routes_coordinator.py:1215-1227` after UPG-246, `:1293-1305` after UPG-239/240, `:1094-1106` after UPG-234/235, `:1033-1045` after UPG-230; cited as `:591-594` before, the same code at `57a5922`, `:455`). `current_app` is a request-bound proxy, so inside the thread it raises "Working outside of application context." and the summaries are never generated (the exception only shows as a pytest thread warning). The session values it copies are read inside the thread too.
- **What to build:** capture `current_app._get_current_object()` and the session values before starting the thread (or queue the job through the outbox), and log a failure.
- **Effort:** S · **Depends on:** none · **Risk:** low; it is best-effort today.
- **Acceptance criteria:**
  1. Test: publishing results starts the summary job with the app and the coordinator's details, and no thread exception is raised.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the thread now starts at `routes_coordinator.py:591-594` (corrected), after the new portal-mode result step (UPG-194), which runs in the request and is unaffected.

#### UPG-208 — The organiser's certificate correction can't change a certificate's email
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [C, found building UPG-207]
- **Problem:** A correction (UPG-127) makes a new version with a new name only (`services_certificate_changes.new_version`, `services_certificate_changes.py:110`, keeps `recipient_email=old['email']` at `:126`). Since UPG-207 the team page refuses to change a member's email once a certificate was issued to it and sends the lead to the organiser, but the organiser can only revoke it and issue it again (a new number).
- **What to build:** on the certificate page, the organiser corrects the email of a certificate (and of the team member it came from), keeping the number as a new version, emailing the new address, audit-logged.
- **Effort:** S · **Depends on:** UPG-127, UPG-207 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the organiser changes a certificate's email; the number stays with the next version; it appears in the new email's "My certificates" and no longer in the old one's; audit-logged; another SPOC gets 403.

#### UPG-209 — A team promoted from the waitlist gets no member confirmation links
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [C, found building UPG-207]
- **Problem:** `routes_waitlist.promote_entry` (used by `auto_promote` and, since UPG-230, by the SPOC's Accept on the registrations page) writes the registration itself (`routes_waitlist.py:313` after UPG-243; `:270` before UPG-230), not through the form or payment paths that now call `services_team_confirm.after_registration`, so a promoted team's members get no link. The organiser's "Send confirmation links to waiting members" covers them, by hand.
- **What to build:** call `after_registration` after a promotion (after payment, for a paid seat).
- **Effort:** S · **Depends on:** UPG-207 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a team promoted from the waitlist sends each listed member one confirmation link; with the switch off, none.

#### UPG-210 — A coordinator dashboard test fails when the random event title contains "645"
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [R, found running the full suite for UPG-207]
- **Problem:** `tests/test_builder_and_coordinator_view.py::test_coordinator_view_counts_registrations_not_the_cached_counter` (`:131-140`) sets the cached counter to 645 and asserts `'645' not in` the whole page, but the event title is `_unique(...)`, 8 random hex characters, and the page shows it (the search box). A title such as `Event-d47645d2` fails the test about 1 run in 200; it passed when run again. The app is not at fault.
- **What to build:** check the count where it is shown (the event's row or its count element), not the whole page; keep the assertion that the cached 645 is not shown and the real count 2 is.
- **Effort:** XS · **Depends on:** — · **Risk:** none (test only).
- **Acceptance criteria:**
  1. The test passes with a title that contains "645", and still fails if the dashboard shows the cached counter.

#### UPG-213 — On the SQL database a saved form loses its title, description and any key but the fields
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [T, a probe test run while building UPG-212, then removed]
- **Problem:** `event_forms` has one data column, `fieldsJson` (`models_pg.py:563`). A new record stores the whole dictionary (`db_adapter.py:1214-1217`), but saving over an existing one goes through `_update_record_fields` (`db_adapter.py:1441`) and the key map, which knows only `'fields': 'fields_json'` (`db_adapter.py:75`): the field list is written and every other key is dropped. Reading then fills in `form_title` "Registration Form" and `form_desc` "" (`db_adapter.py:1054-1067`). The probe saved a title and description through `/forms/save` and read back `{'form_title': 'Registration Form', 'form_desc': ''}`. So the builder's form title and description are never kept, and any setting stored on the form is lost; UPG-212 keeps its settings on the event (`form_chosen`, `form_member_fields`) for this reason.
- **What to build:** keep the whole form dictionary when an `event_forms` record is updated (write `{fields, form_title, form_desc, ...}` into `fieldsJson`, as the create path does); old rows holding a bare list still read as today.
- **Effort:** S · **Depends on:** — · **Risk:** low (`db_adapter.py` is shared: run the early rule 8 pass).
- **Acceptance criteria:**
  1. On the real database layer, a form saved twice with a title and description reads back that title and description and the same fields.
  2. A row holding only a list of fields still reads as the default title, empty description and those fields.

#### UPG-215 — Self check-in and the manual attendance marks let a cancelled team in
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [R, found building UPG-214]
- **Problem:** The shared check-in refuses a cancelled or refunded registration (`routes_ticket.py:205`), so the scanners and the kiosk do. Three other ways to mark someone present don't look at the status: student self check-in (`submit_self_checkin`, `routes_checkin.py:89`: it finds the registration by the student's email and marks it Present), the coordinator's per-member tick (`mark_attendance_granular`, `routes_coordinator.py:1518` after UPG-246, `:1596` after UPG-239/240, `:1397` before) and the admin's attendance setting (`set_attendance`, `routes_admin.py:1678`). A team the SPOC cancelled with UPG-211 can still self check-in, be ticked present, and then count as attended (certificates, reports).
- **What to build:** refuse "Present" for a cancelled or refunded registration on all three paths, with the same message as the scanner; self check-in shows "Please see the registration desk"; marking absent stays allowed.
- **Effort:** S · **Depends on:** — · **Risk:** low.
- **Acceptance criteria:**
  1. On the real database layer, a cancelled registration can't be marked present by self check-in, the coordinator's tick or the admin's setting; each answer says so; attendance is unchanged.
  2. An active registration is still checked in by each path as today.

#### UPG-217 — The SQL store keeps only a form's fields
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [R, found building UPG-216]
- **Problem:** `event_forms` has one column, `fieldsJson`, and the adapter maps the key `fields` onto it (`db_adapter.py:75`), so `set()` writes only the list of fields: everything else in the form document (`form_title`, `form_desc`, `form_type`, the wizard's `source`, `created_by`, `updated_at`) is dropped, even on the first save; reading gives back "Registration Form" (`db_adapter.py:1054`). UPG-212 and UPG-216 work around it for the builder by keeping those settings on the event; other writers still lose theirs: `services_event.py:183` (a cloned event's title "X Registration"), `routes_spoc.py:328` (the wizard's `source`), `services_copilot.py:346`, `routes_api_v1.py:326`.
- **What to build:** store the whole form document in `fieldsJson` (reading already accepts a list or a document), merged on `set(merge=True)`; then `_get_form` can stop reading the title from the event (keeping the event's values as the fallback for forms saved before).
- **Effort:** S · **Depends on:** — · **Risk:** medium: `db_adapter.py` is shared, so a full re-verification of open items comes with it (CLAUDE.md rule 8).
- **Acceptance criteria:**
  1. On the real database layer, a form saved with a title, description, type and source reads back with all of them, after a first save and after a second one.
  2. A form stored as a bare list (every form saved before) still reads back with its fields.

#### UPG-221 — The walk-in desk registers a person differently from the online form
- **Last verified:** 2026-11-10, on `6a2638c` [C]
- **Problem:** Owner, 2026-11-10: "does on spot register work for SAPTHAHACKS the same as the actual register". It doesn't. `/coordinator/on_spot` (`templates/coordinator/on_spot.html`, `routes_coordinator.py:1269` after UPG-246, `:1347` after UPG-239/240, `:1148` before) asks a fixed name, USN, email and phone with USN and phone required, then saves the person as a team of one named after them, with no members and no team code (nobody can join), none of the event's questions, no seat-limit check and no `registration_count` increase (later online sign-ups see too many free seats), `payment_status` "Paid" at `fees.regular` with Cash or UPI asked even for a free event, and no participant type, ticket type or privacy consent.
- **What to build:** the desk shows the chosen event's registration form (its questions, team name and members within the team size, as on the page), checks and counts seats as online, asks payment only for a paid event and records it at the registrant's fee, records the privacy consent the person gives at the desk, and keeps what the desk does now: checked in on the spot, the ticket and set-password emails, assigned coordinators only.
- **Effort:** M · **Depends on:** — · **Risk:** medium (event-day desk).
- **Acceptance criteria:**
  1. A walk-in for a team event gives the team name and members within the team size, gets a team code, and answers every question on the event's form, saved as online.
  2. A full event refuses a walk-in (or offers the waitlist) and a walk-in adds one to the count.
  3. A free event's walk-in is "Free" with no payment asked; a paid one records the mode and the registrant's fee.
  4. The walk-in is checked in at once and gets the ticket email (and the set-password link when new), as now.

#### UPG-223 — A USN or phone question added by hand isn't saved as the lead's USN or phone
- **Last verified:** 2026-11-10, on `6a2638c` [C, and the live SAPTHAHACKS'26 page]
- **Problem:** `submit_form` takes the lead's USN and phone from answers named `usn`, `phone` and a few synonyms (`routes_forms.py:450`). A question the SPOC adds in the builder gets a random id (`templates/coordinator/form_builder.html:473`), so SAPTHAHACKS'26's "USN" (`f_g9oz1z`) and "Phone Number" (`f_voc3qf`) are saved only in `form_answers`; `lead_usn` and `lead_phone` stay empty. UPG-222 shows them in the export, but the rest of the app reads `lead_usn`/`lead_phone`: the WhatsApp ticket, the certificate's USN, the check-in search, the team page.
- **What to build:** at submit, a question whose label asks the USN or the phone (as UPG-222's `USN_LABEL`/`PHONE_LABEL`) fills `lead_usn`/`lead_phone` when the standard ids are absent; and the builder offers "USN" and "Phone" as ready questions with the standard ids. Registrations already saved get theirs once, from their answers (a one-off script the owner runs).
- **Effort:** S · **Depends on:** UPG-222 · **Risk:** low.
- **Acceptance criteria:**
  1. Registering on a form with a hand-added "USN" and "Phone Number" saves `lead_usn` (upper case) and `lead_phone`, and the lead's member row has them.
  2. The builder's ready USN and Phone questions use the ids `usn` and `phone`.
  3. The one-off script fills empty `lead_usn`/`lead_phone` from the answers, changes nothing else, and running it twice changes nothing more.

#### UPG-228 — The activity points page and the privacy export read every registration to find a member's teams
- **Last verified:** 2026-11-10, uncommitted on `6b62490` [C]
- **Problem:** Found building UPG-227. `participation_ledger` (`routes_participant.py:1104` after UPG-246, `:1157` with UPG-238, `:1103` after UPG-239) and `services_privacy.registrations_of` (`services_privacy.py:79`) stream the whole `registrations` collection on each request to find the teams a person is a member of; with thousands of registrations this is slow and grows with every event.
- **What to build:** both use UPG-227's `member_registrations` (`routes_participant.py:88`, moved to a service), which finds them through the `team_members` rows by email.
- **Effort:** S · **Depends on:** UPG-227 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. The activity points page and the privacy export list the same registrations as before, a member's teams included, without reading every registration.

#### UPG-247 — A cancelled team that came off the waitlist still shows "Accepted" on its waitlist card
- **Status:** TODO
- **Last verified:** 2026-11-12, uncommitted on `ddcc1a8` [C, found building UPG-245]
- **Problem:** `services_waitlist.standing` shows a promoted entry by the registration the promotion made (`services_waitlist.py:133-144`). `_registration` (`:74-79`) prefers a live one but falls back to a cancelled or refunded one, so when the SPOC cancels a team that came off the waitlist (UPG-211), the lead's and members' waitlist card still says "Accepted: registered" with "See your registration". UPG-245 handled the deleted case (no registration left: the card goes).
- **What to build:** a promoted entry whose registration is cancelled or refunded shows "No longer registered" (or is left out, as a deleted one is), not "Accepted".
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a team accepted from the waitlist, then cancelled by the SPOC, no longer shows "Accepted" on the lead's or a member's waitlist card.

#### UPG-248 — A team the SPOC cancelled can't sign up again or be added by hand
- **Status:** TODO
- **Last verified:** 2026-11-12, uncommitted on `ddcc1a8` [C, found building UPG-245]
- **Problem:** The SPOC's Cancel (UPG-211) keeps the registration with status Cancelled. The duplicate check at submit (`routes_forms.py:922-934`) looks for any registration of the lead at the event, whatever its status, so the lead is told "You have already registered for this event" and the SPOC's Add a team (UPG-244) says they're already registered. Delete (UPG-245) removes the row, so a deleted team can come back; a cancelled one can't.
- **Decision needed (owner):** should a cancelled team be able to register again (a new registration, the cancelled one kept for the record), or does Cancel mean they stay out of this event?
- **What to build:** if they may come back, the duplicate check ignores cancelled and refunded registrations; otherwise the message says the organiser cancelled their registration.
- **Effort:** S · **Depends on:** the owner's answer · **Risk:** low.
- **Acceptance criteria:**
  1. Test: after the SPOC cancels a team, its lead signing up again gets the decided result, and so does the SPOC's Add a team.

## Open decisions

| ID | Decision | Blocks | Status |
|---|---|---|---|
| D-2 | **BLK-01 owner actions:** force-push the rewritten `master`, delete the remote `main` and `claude/busy-davinci-6nkabi`, and ask GitHub Support to purge the 47 PR refs (commands in the 2026-09-29 changelog). The agent never pushes. | BLK-01 criteria 0 and 4 (CI green on GitHub); BLK-11 criterion 2 | **Done (owner, 2026-10-01):** `master` force-pushed, `main` and `claude/busy-davinci-6nkabi` deleted, `production-ready` pushed, GitHub Support contacted. Verified with `git ls-remote`; BLK-01 criterion 4 is met on GitHub. **Left:** Support removing the 47 PR refs (BLK-01 criterion 0). Nothing else waits on it. |
| D-7 | **UPG-22: what is kept after an account is deleted?** Built: the account and the person's name, email, phone, USN and answers go; registration rows stay without them (attendance and payment totals for reports). Still holding the email: payment orders (finance records) and the audit log. Also: should API v1 registrations (the apps) require consent once the apps are updated? | UPG-22 (policy, not code) | Open (2026-10-10). Proposed: keep payment orders and the audit log for the finance and audit retention period (e.g. 8 years), then anonymise; require consent in API v1 after the next app release. |
| D-8 | **Keep `/live/reels` and `/live/streams` public?** Both are demo pages: made-up like and viewer counts, a "Live" badge, and (until UPG-60) cartoon sample videos. UPG-60 replaced the videos with event images; the counts are still invented. | none (content, not code) | Open (2026-10-10). Proposed: hide both until there's real event media, as UPG-53 did for the home page's fake hackathon. |
| D-10 | **Confirm the exact AQAR table layout with the IQAC coordinator.** UPG-144 builds a sensible default in `config/naac_layout.json`; the columns and sheets follow that file, so a confirmed layout needs no code change. | UPG-144 (layout only) | Open |
| D-11 | **Hackathon defaults (Phase 1, 2026-11-05).** Built as: "Admin" on the login page is the Super Admin; the registration email goes to the team lead only; each team picks one problem statement; portal mode is on for every hackathon (switchable per event); an extension adds time to the current deadline for the whole event, also after it has passed; the team page refreshes by a 60-second poll; the hackathon is free (a paid one still emails the ticket and receipt, UPG-201). Phase 2, built 2026-11-06: Gemini (`gemini-2.5-flash`) scores and judges don't see the AI score; AI scoring runs while the SPOC's hackathon page is open (Cloud Run has no background worker), at most 500 calls per event; the SPOC's own score overrides the AI total; a team without a submission can't be shortlisted; undo until a judge scores a finalist; eliminated teams' leads also get one result email ("Participant"). | UPG-192, UPG-193, UPG-194 (only if changed) | Open: the owner confirms or changes any of these. |
| D-12 | **Certificate design and member confirmation defaults (2026-11-09).** Proposed for UPG-206: own design for participation certificates only; the number and a small QR always printed (corner chosen); the name box defaults to 47% from the top, centred, 60% wide, 40 pt bold. Proposed for UPG-207: on by default for team events, including portal-mode hackathons (one extra email per member); a waiting member's certificate is still issued; 3 resends per member per 24 hours. | UPG-206, UPG-207 (only if changed) | Open: the owner confirms or changes any of these. **Built with these defaults (2026-11-09)**, except that the design is used for the event's attendance certificate (completion or extension for workshops and NSS events, participation elsewhere); the organiser turns member confirmation off per event on the registrations page. |
| D-13 | **UPG-238, the waitlist's screening round.** (a) Questions: multiple choice scored automatically only, or also short answers the SPOC marks by hand? (b) People not accepted after the round: stay waiting, or told they weren't selected and taken off? (c) Team events: the lead answers for the team, or each member answers and the team's score is the average? (d) Watch for tab switching (as `/exams` does) or not? (e) Ties at the Nth place: all tied accepted, or the earlier joiner? | UPG-238 | **Decided (owner, 2026-11-12):** the proposed defaults: (a) multiple choice only; (b) stay waiting, nobody told; (c) the lead answers; (d) no; (e) the earlier joiner. Built in UPG-238. The round was removed at the owner's request on 2026-11-12 (UPG-246). |

*Decided decisions: `docs/archive/FEATURE_REVIEW_DONE.md` ("Decisions needed").*

## Changelog (last 20)

| Date | Commit | Item ID | What changed |
|---|---|---|---|
| 2026-11-09 | (docs, uncommitted, on `a700892`) | UPG-206, UPG-207, D-12 | **New items (owner's request):** UPG-206 (the organiser uploads their own participation certificate design and places the name on it; the number and QR stay) and UPG-207 (team members confirm their email and get a portal login, so they see their own certificate; today members typed by the lead get no account, and portal mode sends no certificate email). Defaults proposed in D-12. No code changed. |
| 2026-11-06 | (docs) | UPG-199 | **Deployed** by the owner from Cloud Shell: `406f952` live as revision `saptha-00007-j48` (rollback `saptha-00006-rmz`) after a Cloud SQL backup and the `saptha-migrate` job (0010 to 0014); `EMAIL_DAILY_LIMIT=270`, `GEMINI_API_KEY` from Secret Manager. Health and the five-role login menu checked on the live URL; the owner's smoke checks 3 to 8 remain. |
| 2026-11-09 | (uncommitted, on `a700892`) | UPG-206, UPG-207, UPG-208, UPG-209, UPG-210, D-12 | **Own certificate design and team members' logins (owner's request):** UPG-206: the organiser uploads their participation certificate design (PNG, JPG or one-page PDF, signatures already on it), places the name (and optionally team, USN, college) by top, left, width, size, colour, alignment and bold, with a preview using the longest registered name; the number and QR stay in a chosen corner; each certificate keeps a snapshot of the design it was issued with. UPG-207: each member the lead lists gets one email to confirm and set a password (or sign in), in portal-mode hackathons too; the lead sees each member's status, resends (3 a day) and corrects a mistyped email (refused once a certificate is issued); the organiser sees counts, sends links to waiting members and can switch it off per event; the export marks [Confirmed]/[Waiting]; a confirmed member sees their own certificate in "My certificates". Defaults as proposed in D-12. New tests: `tests/test_certificate_design.py`, `tests/test_team_member_confirm.py` (14). **Tests changed to the new requirement** (each with a comment naming UPG-207): `test_hackathon_portal.py` registration email (now lead plus one link per member), `test_hackathon_rehearsal.py` (each member one confirmation email, 30 emails, was 20), and the two UPG-152 lead-only tests in `test_low_email_auth.py` (switch off for their event, assertions unchanged). **New items:** UPG-208 (a certificate's email can't be corrected), UPG-209 (waitlist promotions send no member links), UPG-210 (a flaky dashboard test: a random title containing "645"; failed once, passed on rerun). Rule 8 check of open items citing the changed files: none changed status; line numbers updated for UPG-30, UPG-170, UPG-181, UPG-203 and BLK-01. Full pytest on SQLite: 1,430 passed, 8 skipped; ruff clean. Not deployed; run locally for the owner's manual test. |
| 2026-11-09 | (uncommitted, on `a700892`) | UPG-211, UPG-212, UPG-213 | **The SPOC cancels a team (owner's request):** UPG-211, the hosting SPOC cancels a team's registration with a reason until it is checked in (seat freed, waitlist promoted, ticket refused at the scanner, a portal notice to each person and an email to the lead, none in portal mode); another SPOC and the coordinators get 403; the SPOC dashboard links to the registrations page. **The form is what the SPOC built (owner's request):** UPG-212, a form saved from the builder shows exactly its questions, only name and email added and always required; choices checked against the options; the SPOC chooses member USN and phone (off, optional, required); the builder refuses forms it couldn't show. Forms saved before keep phone and USN. New tests: `tests/test_spoc_cancel_team.py` (4), `tests/test_form_builder_choices.py` (7). **Test changed to the new requirement:** `test_builder_and_coordinator_view.py:82` (the builder's note; comment names UPG-212). **New item UPG-213** (found building UPG-212): on the SQL database, saving over an existing form keeps only its fields, so the title and description are lost; UPG-212's settings are kept on the event for this reason. No shared files changed (`db_adapter.py` untouched), so no early rule 8 pass. Full pytest on SQLite: 1,441 passed, 8 skipped; ruff clean. Not deployed. |
| 2026-11-09 | (uncommitted, on `a700892`) | UPG-214, UPG-215, UPG-216, UPG-217, UPG-218 | **The SPOC's entry list (owner's request):** UPG-214, with the event's entry list on only the teams the hosting SPOC selected get in (scanners, kiosk, self check-in, the coordinator's and admin's marks), teams not selected are never told and get no more reminders or broadcasts, reports don't count them absent, and the scan screen keeps the list for offline scans; 8 tests. **The form the SPOC built (owner's request):** UPG-216, the builder's title and description are kept (the SQL store dropped them on every save) and the page keeps the builder's order, name and email first in both; walked through in a browser; 4 tests. New: UPG-215 (self check-in and manual marks ignore a cancelled team), UPG-217 (the SQL store keeps only a form's fields), UPG-218 (polls made in the same second swap; `tests/test_live_polls.py` fails now and then). Full pytest: 1,452 passed, 8 skipped, 1 failed (that UPG-218 test, which passes alone). Tests changed: none. |
| 2026-11-10 | (docs) | UPG-206, UPG-207, UPG-211, UPG-212, UPG-214, UPG-216 | **Deployed** by the owner from Cloud Shell: `a5da346` (code `3031a1b`) live as revision `saptha-00008-bup`, 100% of traffic (rollback `saptha-00007-j48`), after a Cloud SQL backup; no migration, no setting changed. Checked from here on the live URL: `/health/ready` → `{"ready":true}`, the home and login pages answer 200. The owner's checks on the form builder, the entry list, team cancel, certificate design and member confirmation remain. |
| 2026-11-10 | (uncommitted, on `55d4736`) | UPG-219, UPG-220 | **The form made in step 6 is the one people register with (owner's request, with screenshots):** UPG-219, step 6 of the event wizard lists the whole form (name and email fixed; phone and USN as ordinary questions; the SPOC's questions, reordered with up and down) and the wizard saves exactly that as the SPOC's form; the event type's catalogue questions are only suggested (a Hackathon no longer gets GitHub, tech stack, T-shirt and diet unseen); "Checkboxes" shows its choices; "Also ask for", which nothing read, is replaced by the builder's Member USN and Member phone; editing lists the form and leaves it to the builder; step 7 lists the questions. Requests without step 6's list (API, scripts) keep the catalogue form. Walked through in Chromium at 1300 and 390 wide. 7 tests (`tests/test_wizard_form.py`). UPG-220: the builder's preview title is white on the navy header; 1 test. Tests changed: none. Full pytest: 1,460 passed, 8 skipped, 1 failed (`tests/test_live_polls.py`, UPG-218, which passes alone). |
| 2026-11-10 | (uncommitted, on `6a2638c`) | UPG-221, UPG-222, UPG-223 | **The registrations export shows every detail (owner's request, with the SAPTHAHACKS'26 sheet):** UPG-222, the lead's USN and phone come from a question the SPOC added by hand (label USN, roll or register number; phone, mobile, WhatsApp), else the account; department and year from the university's USNs (25SUUBEAML231 → AML, 2025); each member has Name, USN, Email, Phone and Confirmed columns; each question on the form has a column in the form's order, then answers to questions since removed; the Members cell drops "()"; the CSV reads columns and rows once; the all-events export keeps its fixed columns. Saved registrations are unchanged. 5 tests (`tests/test_export_details.py`). Tests changed: none. Full pytest: 1,466 passed, 8 skipped. **New items** UPG-221 (the walk-in desk registers differently from the online form) and UPG-223 (a hand-added USN or phone isn't saved as the lead's). |
| 2026-11-10 | (uncommitted, on `6a2638c`) | UPG-224 | **A backup Brevo account (owner's request: the daily email limit is near):** `BREVO_BACKUP_API_KEY` sends what the main account can't, once it reaches `EMAIL_DAILY_LIMIT` or when Brevo refuses an email, with its own `EMAIL_BACKUP_DAILY_LIMIT` (270) counted in `email_quota` under `YYYYMMDD-b` (no migration) and its own sender (`MAIL_FROM_BACKUP`, else `MAIL_FROM`); "contact the organizer" only when both are full; `/diag/email?via=backup` tests it alone and shows its count. Without the key nothing changes. 6 tests (`tests/test_email_backup.py`). Tests changed: none. Full pytest: 1,472 passed, 8 skipped. |
| 2026-11-10 | (docs) | UPG-219, UPG-220, UPG-222, UPG-224 | **Deployed** by the owner from Cloud Shell: `ecf1bc0` live as revision `saptha-00016-den`, 100% of traffic (rollback `saptha-00008-bup`), after a Cloud SQL backup; no migration. The live mail turned out to be **Gmail SMTP** (`MAIL_USER`/`MAIL_PASS`, `BREVO_API_KEY` unset), so the main limit is `EMAIL_DAILY_LIMIT=496` (owner's choice, Gmail allows about 500) and a second Brevo account is the backup: secret `BREVO_BACKUP_API_KEY` (an API key, `xkeysib-`; Transactional email All, Account Read; the first try was an SMTP key, 401 "Key not found"), runtime service account granted access, `EMAIL_BACKUP_DAILY_LIMIT=270`. `/diag/email?via=backup` sent on the stage; live login, registration page and the new step 6 script answer. Revisions 00010 and 00013 to 00015 were stage-only. Left: the owner presses the resend buttons for held-back members and leads. |
| 2026-11-10 | (uncommitted, on `6b62490`) | UPG-225, UPG-226 | **The SPOC and the team lead correct a registration's details (owner's request):** one edit page (`services_registration_edit.py`, `templates/registration_edit.html`) for the lead (own registration, until check-in or the event's end; dashboard and team page) and the organisers (`manage_registrations`, any time, from the registrations list); only changed values are checked, with the form's own rules, and each is written to every copy (registration, member rows and columns, answers incl. hand-added USN/phone and `member_N_*`, form responses); members changed under the registration lock (`services_team_confirm.update_members`); the lead's email stays; a waiting member's email through UPG-207's correction; audit log, and a portal notice to the lead when an organiser edits; old QR tickets still scan. Found: UPG-226 (the list's USN line reads `usn`). 9 tests (`tests/test_registration_edit.py`). Tests changed: none. |
| 2026-11-10 | (uncommitted, on `6b62490`) | UPG-227, UPG-228 | **A team member sees their team (owner's request: the member's dashboard showed nothing):** the dashboard and My events also list registrations the person is a member of, found through the `team_members` rows (`member_registrations`, no migration): event, team and lead, ticket, team page, badge, round status, results, with the member's own attendance deciding their chip and certificate; cancel, edit and the hackathon page stay the lead's; members are told to ask the lead to correct details. Found: UPG-228 (activity points and privacy export scan every registration). 6 tests (`tests/test_member_dashboard.py`). Tests changed: none. Full pytest: 1,487 passed, 8 skipped (one new test's line, which depended on other tests' events, was dropped and re-run). |
| 2026-11-10 | (docs) | UPG-225, UPG-227 | **Deployed** by the owner from Cloud Shell: `b10f553` live as revision `saptha-00015-h7z` (the name's number is lower than the previous `saptha-00016-den`, which is the rollback), 100% of traffic, after a Cloud SQL backup; no migration, no new setting. Both service URLs answer: login 200, `/health/ready` ready, the lead's and the organisers' edit pages exist (302 to login when signed out). |
| 2026-11-10 | (uncommitted, on `3a07c55`) | UPG-229, UPG-226 | **The SPOC's registrations list as a clear table, with Edit, Cancel and Delete (owner's request, with a screenshot; owner chose both Cancel and a permanent Delete):** one thing per column (team with lead and USN, members with short confirmation badges, contact, status badges, login, actions); Cancel in a dialog asking the reason (UPG-211 unchanged); Delete, the hosting SPOC only, in a dialog with a confirming tick, refused for a team checked in, paid, certified or with hackathon work; a team not yet cancelled is cancelled first (seat, count, waitlist) and told; its records go with it, the audit log keeps who deleted what, accounts stay. UPG-226: the list shows and searches `lead_usn` and members' USNs. 7 tests (`tests/test_registration_table.py`). Tests changed: none. Full pytest: 1,494 passed, 8 skipped. |
| 2026-11-10 | (docs) | UPG-229, UPG-226 | **Deployed** by the owner from Cloud Shell: `2555456` live as revision `saptha-00016-k2b`, 100% of traffic (rollback `saptha-00015-h7z`), after a Cloud SQL backup; no migration. Both service URLs answer: login 200, `/health/ready` ready, the new `delete_team` action exists (405 to a GET; an unknown action 404). |
| 2026-11-11 | (uncommitted, on `89c4cf9`) | UPG-230, UPG-231, UPG-232 | **The waitlist on the SPOC's page, and every detail the form asked (owner's request):** UPG-230, the registrations page shows a Waitlist card (a count in the header, the seats and whether full; each person waiting in line order with place, team or name, USN, members, contact, when they joined and whether accepting asks a fee) and the hosting SPOC accepts anyone on it, whatever their place, in a dialog that warns when no seat is free; accepting registers them as the automatic promotion does (now one shared `promote_entry`: a free event confirms with a ticket, a paid one holds the seat with a pay link; a portal notice and, outside portal mode, an email), audit-logged; coordinators see the list without Accept, another SPOC gets 403; the SPOC dashboard's link reads "Registrations, Waitlist & Teams". UPG-231, each registration and each waitlist entry has a Details button (and "Show or hide all details") opening everything the form gave: the lead (name, USN and phone, also from questions added by hand, department, year, type, ticket type, team code), each member's name, USN, email and phone, and every question on the form by its label with its answer ("Not answered" when blank; answers to questions since removed are labelled so), read with the export's rules (`services_export.FormDetails`). **New items UPG-232** (the old JSON waitlist routes check the role, not the event) and UPG-233 (below). Rule 8 check of open items citing the changed files: none changed status; UPG-209 now also covers the SPOC's Accept; line numbers updated for UPG-189, UPG-203, UPG-209, UPG-215 and UPG-221. 10 tests (`tests/test_spoc_waitlist.py`). Tests changed: none. Full pytest on SQLite: 1,495 passed, 8 skipped; 7 errors were the run's own `-p no:logging` (no `caplog`), passing when rerun normally; the phone-width layout test caught the new header badge pushing Export CSV off a 375px screen, fixed (the header wraps) and passing; `test_entry_selection`'s admin login fails on `89c4cf9` too: **new item UPG-233**. Ruff clean. Not deployed. |
| 2026-11-12 | (uncommitted, on `b9c98a3`) | UPG-234, UPG-235, UPG-236, UPG-237, UPG-238, D-13 | **The SPOC's registrations page, the acceptance email, and the waitlist in the person's portal (owner's requests):** UPG-234, the page's layout loads no Bootstrap script, so Details, Show all and the Cancel, Delete and Accept dialogs did nothing: now native (`<details>`, `<dialog>`) with the page's own script and CSS; the waitlist (and the entry list) fold away until opened and stay as left; Search, Clear, the filters and the pages come back to the list (`#registrations`, an optional anchor in the shared search and pagination includes); a summary of registered, seats (free, full or over the limit), waiting and checked in; headings, captions, screen-reader names on every button and badge. UPG-235, the SPOC's Accept emails the lead "Accepted: you're registered" or "pay to confirm" (also in portal mode), one notice per person, and says how far past the seat limit the event now is. UPG-236, a person waiting (lead or team member) sees their place, or that they were accepted (pay link), already registered or left, on the dashboard and in My events (whose Waitlisted tab was always empty) and its JSON. **New items** UPG-237 (an automatic promotion sends no email in portal mode) and UPG-238 (an online screening round for the waitlist, owner's request; needs D-13). Rule 8 check of open items citing the changed files: none changed status; line numbers updated for UPG-203, UPG-215, UPG-221 and UPG-228. 15 new tests (`tests/test_registrations_page.py` 9, the browser ones in headless Chromium; `tests/test_waitlist_standing.py` 6). Tests changed: `tests/test_spoc_waitlist.py:107`, the seats wording (to the new requirement). Full pytest on SQLite: 1,518 passed, 8 skipped, 1 failed (`test_entry_selection`, UPG-233, fails at `b9c98a3` too). Ruff clean. Not deployed. |
| 2026-11-12 | (uncommitted, on `d4d14de`) | UPG-239, UPG-240, UPG-241, UPG-237 | **Documents for teams, one "you're in" email, and the lead adds members (owner's requests):** UPG-239, the hosting SPOC adds a document on the registrations page (a folded "Documents for teams" section): a title, their own instructions, a PDF up to 10 MB, or instructions or PDF alone; each registered lead gets a portal notice; the lead and the members see it on their dashboard ("From the organisers") and download the PDF (private, for people on a registration that isn't cancelled and the event's staff); the SPOC removes it; the app adds nothing to the SPOC's instructions (signing, a room number are theirs to write). UPG-240, a cancelled or deleted team already took the count down by one and moved the first in line up; now that person gets ONE email (registered, or the pay link; the event; and a fresh set-password link in the same email when their account has no password), as a registration email so a portal-mode hackathon sends it too (closes UPG-237), their team a portal notice each; the SPOC's Accept sends the same email; one reminder 24 hours later from the hourly `reminders` job if the password or the fee is still outstanding, never two (`seat_reminders`, no migration). UPG-241, the lead adds a member (name, email, USN, phone) from the team page up to the event's limit, atomically; the new member gets the confirm-and-set-password link (UPG-207) and a portal notice; replacing = remove, then add; refused when full, already registered, after registration closes or check-in, or with a per-person fee. 18 new tests; one assertion moved to the new email (`tests/test_payments_secure.py`, the pay link is now in the registration email, not the old generic task). Full run: 1,535 passed, 8 skipped, 2 failed: the known UPG-233 (fails at `d4d14de` too) and the known UPG-218 poll-order flake (`tests/test_live_polls.py` passes 3 of 3 on its own); ruff clean. Rule 8: citations corrected for UPG-170, UPG-203, UPG-215, UPG-221, UPG-228. |
| 2026-11-12 | (uncommitted, on `570d0d4`) | UPG-238, UPG-242, UPG-243, UPG-232, UPG-233, UPG-218, D-13 | **The waitlist's screening round, the event's own ticket guidelines and support email, and a switch to stop the waitlist moving up on its own (owner's requests):** D-13 decided with the proposed defaults. UPG-238, the hosting SPOC writes multiple-choice questions (with the right answer and points) and the times on the registrations page, opens the round and each waiting lead is told (portal notice and email); the lead answers once between the times (late answers kept but score 0; the right answers never reach the page); the waitlist shows each score and rank, sorts by it, and "Accept the top N" accepts the best N through the same Accept (a tie to the earlier joiner); the rest stay waiting, not told (`screening_answers`, no migration). UPG-242, the edit page takes the ticket's guidelines (numbering taken off, up to 12) and a support email; the ticket's back shows them, and the registration, set-password, ticket and waitlist seat emails say "Questions? Write to …". UPG-243, a switch on the waitlist (on by default, as before): off, a freed seat waits for the SPOC's Accept and new sign-ups join the waitlist while anyone waits. UPG-232, the waitlist's JSON list and "promote next" check the event. UPG-233, the test helper's SuperAdmin login sends the test master key (helper only, no assertion changed). UPG-218, poll and question times to the microsecond, never the same twice. 19 new tests. First full run: 1,555 passed, 8 skipped, 1 failed: `tests/test_waitlist_promotion.py::test_the_task_and_the_spoc_route_share_one_promotion`, because UPG-243 first gave `auto_promote` a `manual` flag; the switch is now checked in the cancel task instead (`tasks/waitlist_tasks.py:33`), so both still call the same `auto_promote(db, event_id)`, test unchanged; the waitlist suites pass (57). Second full run: see the next line. ruff clean. Rule 8 (the change touched files many open items cite): citations corrected for UPG-151, UPG-153, UPG-170, UPG-181, UPG-188, UPG-189, UPG-203, UPG-209, UPG-215, UPG-221, UPG-228; none changed status. |
| 2026-11-12 | (uncommitted, on `ddcc1a8`) | UPG-244, UPG-245, UPG-246, UPG-247, UPG-248, UPG-154 | **Deployed** by the owner from Cloud Shell: `ddcc1a8` live as revision `saptha-00019-w46` (rollback `saptha-00016-k2b`); its second full run: 1,556 passed, 8 skipped, 0 failed. **The SPOC adds a team, a deleted team can come back, the screening round goes (owner's requests):** UPG-244, "Add a team" on the registrations page (hosting SPOC only) opens the event's own form in organiser mode; the team is saved as an online sign-up (members, team code, answers, consent, `added_by`), straight into the list even when full, closed or teams wait, never the waitlist; the lead (not the SPOC) gets the registration email, with a set-password link for a new account; a lead already registered isn't added twice; a paid event can't be added by hand (the team pays online); audit-logged. UPG-245, Delete already removed the registration and kept the accounts (checked by running; the lead signs up again, also for another event, or is added by hand); now a team accepted from the waitlist and then deleted no longer shows "Accepted" on its waitlist card (entry `removed`). UPG-246, UPG-238's screening round removed (code, page, routes, `tests/test_screening_round.py` with the feature); Accept and the UPG-243 switch stay. **New items** UPG-247 (a cancelled team still shows "Accepted" on its card) and UPG-248 (a cancelled team can't sign up again; needs the owner's answer). 10 new tests (`tests/test_spoc_add_team.py` 5, `tests/test_deleted_team.py` 4, `tests/test_screening_removed.py` 1); no existing test changed. Full run: 1,558 passed, 8 skipped, 1 failed: UPG-154 (`tests/test_admin_users.py`, order-dependent), set off because the new file was first named `tests/test_add_team.py` and ran before it; renamed `tests/test_spoc_add_team.py`, the files around it pass again (UPG-154 updated, its test unchanged). Ruff clean. Rule 8 (the change touched `routes_forms.py`, `routes_coordinator.py`, `routes_participant.py`): citations corrected for UPG-151, UPG-153, UPG-170, UPG-181, UPG-188, UPG-189, UPG-203, UPG-209, UPG-221, UPG-228; none changed status. |
