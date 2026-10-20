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
| UPG-117 | The JSON waitlist join only takes events in the old "active" status | TODO | Found in UPG-114. POST /waitlist/join/<event_id> (routes_waitlist.join_waitlist) answers "Event is not… |
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
| UPG-143 | Tests that make an event "today" fail when a run crosses midnight | TODO | Found in the final PostgreSQL run of the certificate phase.… |

## Open items

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
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** unchanged; criterion 4 (the owner's checkout with Razorpay test keys) goes on Part 3's go-live checklist.
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still IN PROGRESS; `routes_payment.py` unchanged since UPG-115. Criterion 4 is the owner's Test Mode checkout and refund (go-live checklist).
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still IN PROGRESS; `routes_payment.py` untouched by the certificate work. Criterion 4 is the owner's Test Mode checkout and refund.

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
- **Re-verified 2026-10-19 (rule 8, end of Part 2):** unchanged; only GitHub Support's removal of the PR refs is left (owner).
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still IN PROGRESS; nothing in the code changes it. Only GitHub Support's removal of the old pull-request refs is left (owner; on the go-live checklist).
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still IN PROGRESS; only GitHub Support's removal of the old pull-request refs is left (owner).

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

#### UPG-117 — The JSON waitlist join only takes events in the old "active" status
- **Status:** TODO
- **Last verified:** 2026-10-19 [T]
- **Problem:** Found in UPG-114. `POST /waitlist/join/<event_id>` (`routes_waitlist.join_waitlist`) answers "Event is not active" (400) unless the event's status is `active`. Since UPG-73, an event that is taking registrations is `registration_open` (or `published`), so the endpoint refuses every new event. No page calls it today: the registration form puts people on the waitlist itself when an event is full.
- **What to build:** accept the statuses in which registration is open (as the form does), and refuse the rest with the same message the form gives; or remove the endpoint if nothing will call it.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: joining a full `registration_open` event through the endpoint adds the person to the waitlist; a cancelled or completed event is refused.
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO; `routes_waitlist.py:44` still refuses any status but `active`.
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still TODO; `routes_waitlist.py:44` still refuses any status but `active`.

#### UPG-143 — Tests that make an event "today" fail when a run crosses midnight
- **Status:** TODO
- **Last verified:** 2026-10-20, at `8666965` [T]
- **Problem:** Found in the final PostgreSQL run of the certificate phase. `tests/test_teams.py::test_joining_by_code_adds_the_member_and_they_can_open_the_ticket` builds its event for `datetime.date.today()`; the run created it at 23:53 and joined at 00:09, when the event was in the past and closed, so the join was refused. Re-run the next day it passes on both databases (6 of 6). Other fixtures that use "today" (`tests/test_certificates.py`, `tests/test_phone_journey.py`) can fail the same way.
- **What to build:** those fixtures use a date a day or more ahead where "today" isn't the point, or fix the clock for the test.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. Test: the team-join test passes with the clock set to 23:59 at the start and 00:01 by the join.

## Open decisions

| ID | Decision | Blocks | Status |
|---|---|---|---|
| D-2 | **BLK-01 owner actions:** force-push the rewritten `master`, delete the remote `main` and `claude/busy-davinci-6nkabi`, and ask GitHub Support to purge the 47 PR refs (commands in the 2026-09-29 changelog). The agent never pushes. | BLK-01 criteria 0 and 4 (CI green on GitHub); BLK-11 criterion 2 | **Done (owner, 2026-10-01):** `master` force-pushed, `main` and `claude/busy-davinci-6nkabi` deleted, `production-ready` pushed, GitHub Support contacted. Verified with `git ls-remote`; BLK-01 criterion 4 is met on GitHub. **Left:** Support removing the 47 PR refs (BLK-01 criterion 0). Nothing else waits on it. |
| D-7 | **UPG-22: what is kept after an account is deleted?** Built: the account and the person's name, email, phone, USN and answers go; registration rows stay without them (attendance and payment totals for reports). Still holding the email: payment orders (finance records) and the audit log. Also: should API v1 registrations (the apps) require consent once the apps are updated? | UPG-22 (policy, not code) | Open (2026-10-10). Proposed: keep payment orders and the audit log for the finance and audit retention period (e.g. 8 years), then anonymise; require consent in API v1 after the next app release. |
| D-8 | **Keep `/live/reels` and `/live/streams` public?** Both are demo pages: made-up like and viewer counts, a "Live" badge, and (until UPG-60) cartoon sample videos. UPG-60 replaced the videos with event images; the counts are still invented. | none (content, not code) | Open (2026-10-10). Proposed: hide both until there's real event media, as UPG-53 did for the home page's fake hackathon. |

*Decided decisions: `docs/archive/FEATURE_REVIEW_DONE.md` ("Decisions needed").*

## Changelog (last 20)

| Date | Commit | Item ID | What changed |
|---|---|---|---|
| 2026-10-19 | "UPG-125: …" (parent `9b1be9f`) | UPG-125 | Delivery: one email per certificate with a signed link that expires (30 days) and refuses alteration, sent once through the outbox; "My certificates" for students and faculty with PDF, LinkedIn image and share links; the ledger links each event's certificate; checked at 375px and 1280px in headless Chromium with a real download. 6 new tests, passing on SQLite and PostgreSQL. |
| 2026-10-19 | "UPG-132: …" (parent `d72ae12`) | UPG-132 | UPG-28's certificate part: the participant's certificate page fits a 375px phone (it hung off both sides before); "My certificates" downloads on a phone (UPG-125). |
| 2026-10-19 | "UPG-133: …" (parent `77e843b`) | UPG-133 | UPG-50's deferred part: the certificate email shows a name or event title with markup as text. |
| 2026-10-19 | "UPG-124/125/126 follow-up: ..." (parent `cb0e937`) | UPG-124, UPG-125, UPG-126 | The full SQLite run at `45899bf` (1,234 passed, 7 skipped) failed one check: `CERT_CHUNK_SIZE`, `CERT_LINK_DAYS` and `VERIFY_RATE_LIMIT` were not in `.env.example`. Added. |
| 2026-10-19 | "docs: ..." (parent `47fd4f0`) | UPG-140, UPG-141 | **Two new items.** UPG-140 (found building UPG-127): `log_action` drops every audit row written outside a request. UPG-141 (found building UPG-132): the participant's certificate page prints "at ." for an event without a venue. |
| 2026-10-19 | "UPG-140: …" (parent `2368312`) | UPG-140 | Audit rows written outside a request (background tasks, scheduled jobs, certificate runs) are kept, as "system"; before, every one was dropped with a warning. |
| 2026-10-19 | "UPG-127: …" (parent `979a228`) | UPG-127 | Corrections and revocation: a student asks for a name correction, the organiser approves (version 2, same number, emailed; version 1's file then checks as replaced) or rejects (nothing changes); revoking needs a reason and shows on verification with the date; every issue, correction and revocation is audit-logged. 2 new tests, passing on SQLite and PostgreSQL. |
| 2026-10-19 | "UPG-141: …" (parent `020cb88`) | UPG-141 | The participant's certificate page says "at Venue to be announced" or "at Online" for an event without a venue, not "at .". |
| 2026-10-19 | "UPG-128: …" (parent `cb8772c`) | UPG-128 | The event's certificate list (25 a page, search by name, number or type) with CSV and Excel exports of the same rows; college-wide counts per department, event type and month for Super Admins, with CSV. 2 new tests, passing on SQLite and PostgreSQL. |
| 2026-10-19 | "UPG-129: …" (parent `3396622`) | UPG-129 | The certificate permissions tested for 8 roles (owner, another SPOC, the event's coordinator, judge and volunteer, a student, Super Admin, and an EventOrganizer on that event only): only the owner, Super Admin and the holder of `issue_certificates` issue, revoke or approve; students download only their own. No code change needed. |
| 2026-10-19 | "UPG-137: …" (parent `27d081f`) | UPG-137 | UPG-112's "two certificate stores": API v1 issues into and verifies from the web's `certificates` table (older API IDs still verify); a SPOC token can now issue (its role was missing from the list), with the per-event permission check. |
| 2026-10-19 | "UPG-138: …" (parent `161d0a8`) | UPG-138 | One issuing path again: end-event, the bulk button and the queued task start runs of the new issuing; the old `issue_event_certificates` is retired; registrations keep their certificate number and link; the participant's certificate page links the new certificate and still opens older ones. UPG-06's tests moved check by check (winners now from published results, per the brief). |
| 2026-10-19 | "UPG-124 follow-up: ..." (parent `3456f1a`) | UPG-124 | Final headless pass of issuing: the organiser signs, issues 31 certificates and opens the list in the browser, measured at 375px and 1280px with no problem found (the student's download and the verification page were measured with UPG-125). |
| 2026-10-19 | "UPG-126 follow-up: ..." (parent `34d69ac`) | UPG-126 | Pyrefly found that the fallback limiter (no flask-limiter installed) lacked `shared_limit`, which the verification routes use; added, with a test. |
| 2026-10-19 | "docs: ..." (parent `71c2f09`) | ALL open (re-verification at the end of the certificate phase) | **Rule 8 re-verification of the 4 open items at `71c2f09`** (BLK-01, UPG-30, UPG-102, UPG-117); none changed status. Every certificate item, UPG-122 to UPG-141, is DONE. |
| 2026-10-19 | "docs: ..." (parent `e8351d0`) | UPG-142 | **New item, found making the sample emails:** merit and special-mention certificates exist as types but nothing in the app awards them. |
| 2026-10-20 | "docs: ..." (parent `8666965`) | UPG-143 | **Final full run of the certificate phase, at `3456f1a`:** SQLite 1,264 passed, 7 skipped; PostgreSQL 1,270 passed, 1 failed, the team-join test, because the run crossed midnight with an event made for "today" (re-run: 6 of 6 on both). New item UPG-143. The tests changed after `3456f1a` pass on both databases. |
| 2026-10-20 | (deploy, no commit) | Deploy | **Deployed `dfce764` to Cloud Run** (owner's request): service `saptha`, project `saptha-event-261017`, region asia-south1, from Cloud Shell as queserateam07@gmail.com. Image built with Cloud Build (`web:dfce764`); migration 0008 ran first as the job `saptha-migrate` (completed); revision `saptha-00005-jlg` serves 100% at https://saptha-967997581752.asia-south1.run.app with the existing settings and secrets. Checked: `/health`, `/`, `/events`, `/login`, `/verify` 200; `/certificates/mine` redirects to login; an unknown certificate number is a 404; HSTS and CSP present. Rollback: `gcloud run services update-traffic saptha --region asia-south1 --to-revisions saptha-00004-q58=100`. |
| 2026-10-20 | "docs: …" (parent `06da54d`) | ALL | Split this file: index, open items, open decisions and the last 20 changelog lines stay; done items and reference sections moved to docs/archive/FEATURE_REVIEW_DONE.md, older changelog to docs/archive/CHANGELOG.md. Nothing deleted. |
| 2026-10-20 | "UPG-142: …" (parent `c9571df`) | UPG-142 | Organisers award merit and special-mention certificates to registered people from the certificate page, with optional wording; issued once, emailed, audit-logged; 403 without issue_certificates. |
