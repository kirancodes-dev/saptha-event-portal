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
| UPG-29 | Coordinator and judge assignment by a SPOC, end to end | DONE | Assignment works since BLK-09 (routes_spoc.py:1180-1261 coordinators, :1379-1435 judges), and one test covers… |
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
| UPG-200 | The SPOC's blast email puts the SPOC's text into HTML unescaped | TODO | Found building UPG-195. `{name}` (participant-typed) and `{body}` go into the email HTML as is (`routes_spoc.py:1295-1296`). |
| UPG-201 | A paid hackathon in portal mode still emails the ticket and receipt | TODO | Found building UPG-195. `routes_payment.py:474-482` isn't gated by the email mode. |
| UPG-202 | The old project submission stores a session ID as its submission time | TODO | Found building UPG-191. `submitted_at` is `session.get('_id', uuid4())` (`routes_hackathon.py:93`). |
| UPG-203 | The AI summaries after the coordinator publishes results never run | TODO | Found building UPG-195. The thread uses `current_app` outside the request (`routes_coordinator.py:1402-1417` after UPG-317), so it raises and nothing is generated. |
| UPG-204 | The login menu has the five roles only | DONE | Owner, 2026-11-06, after Safari listed the hidden roles: Volunteer, IQAC coordinator and Department admin are off the menu, with no "Other staff role". Those accounts can't pick their role until the options come back. |
| UPG-205 | No AI chat widget on the home page | DONE | Owner, 2026-11-06: the "Sparky" button, window and "Ask Sparky" prompt are gone from the home page and its script; `/chatbot/ask` is unchanged. |
| UPG-206 | The organiser's own certificate design, with the name placed on it | DONE | Owner, 2026-11-09: upload a finished certificate design (A4, signatures already on it), drag the name box, set size and colour; the app writes each name, the number and a small QR; no signatory needed for that certificate. |
| UPG-207 | Team members confirm their email and get their own portal login | DONE | Owner, 2026-11-09: each member the lead types gets one email to confirm and set a password; the lead sees who confirmed, resends and fixes an email; organisers send links to earlier teams; members then see their own certificate. |
| UPG-208 | The organiser's certificate correction can't change a certificate's email | TODO | Found building UPG-207: a correction changes only the name, so a certificate issued to a mistyped email must be revoked and issued again. |
| UPG-209 | A team promoted from the waitlist gets no member confirmation links | DONE | Found building UPG-207: `auto_promote` creates the registration directly; the organiser's "send to waiting members" button is the only way. |
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
| UPG-228 | The activity points page and the privacy export read every registration to find a member's teams | TODO | Found building UPG-227: `routes_participant.py:1150` (`participation_ledger`, `:1149` before UPG-336, `:1132` before UPG-335, `:1036` before UPG-236) and `services_privacy.py:79` (`registrations_of`) stream the whole `registrations` collection on each request; UPG-227's `member_registrations` (`routes_participant.py:101`) finds them through the member rows. |
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
| UPG-247 | A cancelled team that came off the waitlist still shows "Accepted" on its waitlist card | TODO | Found building UPG-245: `services_waitlist._registration` falls back to a cancelled registration (`services_waitlist.py:90` after UPG-317), so `standing` (`:144-155`) shows "Accepted: registered" with a link for a team the SPOC cancelled. |
| UPG-248 | A team the SPOC cancelled can't sign up again or be added by hand | TODO | Found building UPG-245: the duplicate check at submit (`routes_forms.py:922-934`) counts a cancelled registration, so its lead is told they already registered; deleting (UPG-245) lets them back. Needs the owner to say which is wanted. |
| UPG-249 | The repository has no LICENSE file though the README says MIT | DONE | Owner, 2026-11-12, applying to the Claude for Open Source Program: "licence also". `README.md:261` printed part of the MIT text with no file, so GitHub showed no licence and the code wasn't open source in law. |
| UPG-250 | After registration closes, the SPOC opens a time-limited window for teams to add and remove members | DONE | Owner, 2026-11-14 (screenshot of a lead's team page: "Registration for this event has closed, so the team can't grow"): "the SPOC turns on that registered teams can still add members for an hour or some duration; the lead can also remove a member in that time". |
| UPG-251 | A member added by the lead fills in their own USN and phone when they confirm | DONE | Owner, 2026-11-14: "that new member needs to give his details". The lead may know only a name and email; the confirm page asks only for a password. |
| UPG-252 | The SPOC sees which members were added in the window, and gets a summary when it closes | DONE | Owner, 2026-11-14, with UPG-250: the SPOC's list doesn't show who joined late or whether they confirmed. |
| UPG-253 | The SPOC's event panel: what to do now first, every tool kept but grouped | DONE | Owner, 2026-11-14: "the SPOC dashboard for an event shows many details, and they're needed, but make it more user-friendly". Registrations, the most-used page, sits in the "Judges & Certs" tab among ~15 buttons; ~30 actions show for every kind of event. |
| UPG-254 | The SPOC's event panel shows an invented venue map and an "estimated revenue" | DONE | Found 2026-11-14 reviewing the panel for UPG-253: the "Venue Wayfinder Map" prints fixed made-up figures ("310 / 400", "48 / 50 (96% FULL)") for every event, and Est. Revenue is the fee × registrations. |
| UPG-255 | Mail on a paid plan: a monthly limit, this month's use, Gmail SMTP as the backup | DONE | Owner, 2026-11-14: "I thought to use the paid SMTP starter version for mail". Paid plans count per month; the app counts only per day, and only a second Brevo account can be the backup. |
| UPG-256 | The SPOC corrects a team lead's email, and the right address gets the login | DONE | Owner, 2026-11-14: "some entered the wrong email; give a way to type a corrected email, then they get their login details". A lead's email is the login and nothing changes it (`services_registration_edit.py:19`), so a lead who mistyped it can't get in. |
| UPG-257 | A teammate who hasn't confirmed is easy to spot and their email easy to correct | DONE | Owner, 2026-11-14: "later they can edit their team member's email in their portal". The lead can (UPG-207's "Correct the email"), but it's folded away and nothing points to it. |
| UPG-258 | An email that bounces marks the member "wrong address?" for the lead and the SPOC | TODO | Proposed 2026-11-14 with UPG-255: Brevo reports bounces to a webhook; Gmail SMTP can't. |
| UPG-259 | The lead can remove members after check-in and after the event | DONE | Found 2026-11-14 reading the code for UPG-250: `remove_member` (`routes_teams.py:310-330`) checks only that the caller leads the team, unlike adding (`lead_may_edit`). |
| UPG-260 | An account that exists always gets its password-reset link | DONE | Owner, 2026-11-14: "if the account exists then send the password link; no need to ask the organisation". |
| UPG-261 | The SPOC's "Send password link" reaches every member of the team, not only the lead | DONE | Owner, 2026-11-14: "all members need to receive their login details, not only the team lead". |
| UPG-262 | A team member saved with no email can be given one, by the lead and the SPOC | DONE | Owner, 2026-11-14 (screenshot of the edit page: Member 4, "Email: —", "Waiting: no link sent"): "no option to change the email of the team member; allow adding the email also for an existing team, and the SPOC too". Every email form found a member by their email, so one with none couldn't get one. |
| UPG-263 | `tests/test_email_paid_plan.py` writes a made-up MAIL_PASS value, which the repo's hygiene scan refuses | DONE | Found 2026-11-14 in UPG-262's full run: the scan reads committed files only, so the test passed before `49647da` committed it and failed after. |
| UPG-264 | The SPOC's registrations list: filters that combine, and a sort | DONE | Owner, 2026-11-14: "add sorting, all confirmed and all that, a filter system with everything possible to make it easy" (for the SPOC). The list had one filter at a time (entry, payment, members) and only newest first. |
| UPG-265 | The SPOC downloads the filtered list with what to fix, and sends it on WhatsApp | DONE (untested, owner's instruction) | Owner, 2026-11-14: "download the full details of that and send to WhatsApp, like all teams still not confirmed, so we can fix things; don't test anything, just add and deploy". |
| UPG-266 | One answer to "can I register?", shown the same on every page | DONE | Every page reads `services_registration_state.state`; the form's gate is the same rule; each state says why. |
| UPG-267 | A page that is already open follows registration changes | DONE | `/live/state.json` and `/live/ops.json`, polled every 30 seconds by `static/js/live-refresh.js`; says when it is stale. |
| UPG-268 | Setting a deployment up for an institution: details, first administrators, a readiness list | DONE | `/admin/institution` (Super Admin), `services_institution.py`, `docs/INSTITUTION_SETUP.md`; one deployment per institution, no public sign-up. |
| UPG-269 | Check-in that survives a lost connection, and says what happened | DONE | Offline scans count for the day they were made, belong to the account that made them, are cleared at sync and sign-out, and are reported back. |
| UPG-270 | Who can register: this institution, invited institutions, or everyone | DONE | Three modes with an invited-domains list; one eligibility sentence on every page; outside registrations marked for the organiser. |
| UPG-271 | The student roster comes in with a check first; the integration documents say only what exists | DONE | `services_roster.py` (check, preview, confirm); `docs/INTEGRATIONS.md`; `docs/API.md` lists exactly the routes served. |
| UPG-272 | The run sheet: who is responsible, what is running, clashes refused, changes announced | DONE | `services_runsheet.py`, `/coordinator/runsheet/<event>`; owner and note kept off public pages; changes announced in the app only. |
| UPG-273 | An event summary report whose figures are defined and match the lists | DONE | `/reports/events` with 14 defined columns, date/category/event filters, CSV and Excel; not an accreditation format. |
| UPG-274 | The privacy and security documents say what the code does; the download and the deletion reach feedback and certificates | DONE | Notice, `docs/SECURITY.md`, `docs/PWA.md` corrected; `docs/DATA_HANDLING.md` new; legal questions in D-15. |
| UPG-275 | An About page a university buyer can read, and a demo that says it is a demo | DONE | `/about`; `DEMO_ENVIRONMENT=1` puts a Demo banner on every page; the invented platform pages are gone. |
| UPG-276 | The event's calendar file checks who may see the event | TODO | `/events/<slug>/calendar.ics` answers for any event, whatever its status or visibility (`app.py:893`). |
| UPG-277 | The check-in time is written in IST, like the attendance day | TODO | `routes_ticket._now()` is the server's clock; the attendance day is IST. |
| UPG-278 | The public API's event answer holds only public fields, and only for listed events | TODO | `GET /api/v1/events/<id>` needs no login and returns the whole document, staff emails and drafts included. Privacy: propose doing first. |
| UPG-279 | The event popup, the open-events page and the student dashboard follow changes too | TODO | These three show the state when loaded but don't refresh (left by UPG-267). |
| UPG-280 | "This institution only" checks that the person is from the institution | TODO | The mode refuses outside participant types but doesn't check a campus domain or the roster. Needs D-17. |
| UPG-281 | Microsoft sign-in: verify it or take its routes out | TODO | `auth_oauth.py` has Microsoft routes, never run against a tenant and not offered. |
| UPG-282 | The one-request roster upload for scripts gets a dry run | TODO | `POST /admin/users/import_csv` checks like the page but writes at once. |
| UPG-283 | Remove `CLOSED_STATUSES` from routes_forms.py | TODO | `routes_forms.py:83` defines a name nothing reads since UPG-266. |
| UPG-284 | The API's role checks use the role names accounts really have | TODO | `routes_api_v1.py` asks for `Admin`, `Coordinator`, `SPOC`; accounts are `SuperAdmin`, `EventCoordinator`, `ClubSPOC`. Not run. |
| UPG-285 | Schedule items have a day | TODO | Items have a time and no day, so on a multi-day event every clash is only a warning. |
| UPG-286 | The data download and the deletion reach the remaining records | TODO | Session stars, live votes and questions, push subscriptions, submissions, exam attempts, waitlist, tickets, check-ins and uploaded files aren't reached. Needs D-15. |
| UPG-287 | The `/pricing` page: remove it or replace it with real terms | TODO | `templates/marketing/pricing.html` (hidden by default) states invented prices, a platform fee and Stripe. Needs D-16. |
| UPG-288 | Three public statements the code doesn't back | TODO | The notice's "retained for 5 years", the home page's "Email & WhatsApp updates", and `docs/DEPLOY.md`'s 15-minute export links. |
| UPG-289 | Two pagination tests fail at `a4809a8`, before this change | TODO | Both `[coordinator registrations]` cases of `tests/test_pagination_lists.py` fail on a clean `a4809a8` (list last changed by UPG-264/265). |
| UPG-290 | Ticket signing has no key written in the code | TODO | `services_ticket._get_signing_key` falls back to a fixed text when no key is set (development only). |
| UPG-291 | The audit log shows when it has been altered | TODO | Audit entries are ordinary rows; a change or deletion can't be seen. |
| UPG-292 | A calendar feed of the institution's public events | TODO | A person has a feed and an event has a file; there is no feed of every public event. |
| UPG-293 | `tests/test_certificate_delivery.py` has lost its first 65 lines in the working tree | TODO | An uncommitted change of 2026-11-13 broke the file; 3 test files can't be collected, 1 hygiene test and ruff fail on it. Owner's action. |
| UPG-294 | The home page and each role's first page are easier to use | DONE | Events open for registration first; dates as "25 Nov 2026"; organisers see "Event over", not `Registration_open`; the student's tickets before the profile card; a coordinator with no events is pointed to the scanner. |
| UPG-295 | The NAAC reminder goes out twice between midnight and 05:30 IST | TODO | `services_naac.daily_reminders` compares today's date in IST with the last reminder's time in UTC (`services_naac.py:332-337`). |
| UPG-296 | Tests with fixed event dates that are about to pass | TODO | Since UPG-266 an event that is over takes no registrations; tests that register for an event dated 2026-11-20 to 2026-12-25 may start failing on those days. |
| UPG-297 | Usability findings from the first-pages review | DONE | (a) the admin's Recent activity in words, at the time in India, without sign-ins, with each entry's details; (b) the page's name whole at 1280 px; (c) "Hello, Asha" and no second empty card; (d) the campus photo a 140 px banner (96 px on a phone); (e) no stored status beside "Visitors see"; (f) a note that events that are over aren't counted; (g) the home page's next 6 events and "See all events". `services_activity.py:1-92`, `routes_admin.py:94-101`, `app.py:314-316`, `templates/admin/dashboard.html:529-539` (a); `static/css/global.css:492-498,564-565` (b); `templates/participant/dashboard.html:111-113,441-451` (c); `templates/includes/ui.html:203-205`, `static/css/global.css:2607-2609` (d); `templates/spoc/dashboard.html:1432-1439` (e); `routes_coordinator.py:84,124`, `templates/coordinator/dashboard.html:68-70` (f); `templates/index.html:653-661`, `static/js/pages/index.js:229-231,480-481` (g); tests `tests/test_first_pages_review.py` (18, two in Chromium). |
| UPG-298 | A hackathon's submission round is scored by AI or by judges, as the SPOC chooses | DONE | "Who scores the submissions" on the hackathon page; in a judges round every judge sees each team that submitted after the deadline (no check-in), the SPOC ranks by the judges' average and shortlists; the finale is judged as before. |
| UPG-299 | AI criteria have a description for the AI and marks that add up to 100 | DONE | Each criterion: name, what it means, marks; all marks or none (equal weights); the AI total is weighted; fixed once a submission is scored. |
| UPG-300 | Every leaderboard is hidden from the public until the SPOC makes it public | DONE | A switch on the results page, the round panel and the hackathon page; the public, students and the projector see "Not public yet", the API answers 403 `not_public`; the event's staff always see it, marked as not public. |
| UPG-301 | A copied hackathon keeps the old event's shortlist, AI run, updates and extensions | TODO | `clone_event` copies the whole `hackathon` block (`routes_spoc.py:1458`), and `active_round`, `total_rounds`, `shortlist_published`, `scoring_locked` too. |
| UPG-302 | The SPOC finds someone on the waitlist with a search that ignores capitals | DONE | A "Find on the waitlist" box on the waitlist card (any part of the team, the lead's name, email, USN or phone, a member's name, USN or email, in any case); places stay the places in the whole line; a long line scrolls inside the card with its headings in view; accepting from a search keeps it. |
| UPG-303 | On an individual event every waitlist entry is titled "Individual" | TODO | The form saves `team_name` "Individual" when there is no team (`routes_forms.py:450`); the waitlist card and the Accept message show it instead of the person's name. |
| UPG-304 | The Super Admin asks every participant for website feedback, in rounds, until they answer | DONE | Two sample forms (now, and mid-event) the Super Admin edits; one round on at a time, for everyone registered or chosen events; a participant is sent to the form from every page at every sign-in until they send it (ticket, sign out, privacy and help stay open; staff never asked); anonymous answers, quotes only when allowed; results, a search and a CSV with no names. |
| UPG-305 | Participants who only use the phone app are never asked the website feedback round | TODO | The gate is on web sessions (`app.py:1429`); the phone app signs in with a Firebase token through `/api/auth/login` and keeps no session, so it shows nothing and such people never answer. |
| UPG-306 | Rooms: a draft only the SPOC sees, a final check, then "Allocate final" by email to the lead, on the website, or both | DONE | Rooms with capacity in people; Auto-fill in registration order, teams kept whole, cancelled left out; the draft is the SPOC's alone; a final check (per room, what to fix, print, CSV); Allocate final by email to the lead, the website (lead and members), or both; later changes reach only the teams they change. |
| UPG-307 | The coordinator's room-and-judge allocation and AI judge matching skip the room draft | TODO | `/coordinator/allocate_rooms` (`routes_coordinator.py:1202-1235` after UPG-317; `:1164-1198` before) and AI matching (`routes_ai_matching.py:388`) write `assigned_room` directly: teams see it at once, with no final check. |
| UPG-308 | Round 1 marked outside the portal: a file for the evaluators with the team code, then upload "Team code, Score" and Submit picks the top N | DONE | A "Team code" column in the registrations export; a third way to score the round, "Outside evaluators"; their file (Excel/CSV) with each team's code and an empty Score; their marks uploaded back, checked (what to fix, who's missing) and submitted, which saves the marks and sends the top N (10, ties together) to round 2 in one step; an old code still matches. |
| UPG-309 | The finale: every judge sees every finalist, finds a team by name or code, and a judge's score is the sum of the marks | DONE | After the evaluators' marks every judge sees every finalist (a switch for other rounds); the team code and a search on the judge's page; a judge's score is the marks added up ("80 / 100"); a team's score is the average of the judges who scored it; the finale ranking and the results use only the finale judges; the criteria total, with a warning when it isn't 100. |
| UPG-310 | Participation certificates: who gets one, and the portal only or email too, chosen per event | DONE | On the certificates page the SPOC chooses who gets the participation certificate (checked in, every member of a team that submitted, everyone registered) and "in the portal only" or "by email too"; an event that never chose is as before. |
| UPG-311 | The coordinator's event edit turns the judges' criteria into names, each out of 100 | TODO | `routes_coordinator.py:1108-1120` (after UPG-317; `:1070-1082` before) saves `criteria` as a comma-split list of names, losing each criterion's marks. |
| UPG-312 | Rooms: a seat can be a whole team, not each person | DONE | "One seat is: a person / a whole team" in the room setup; with teams, a team of 4 takes 1 seat in Auto-fill, the room cards, the final check and its over-capacity problem; an event that never chose counts people. |
| UPG-313 | Rooms: the SPOC types a room number for a team | DONE | "+ Type a room no." in each team's room list; a typed room in the list (any capitals) is that room, a new one joins the list with seats for that team, so the final check and Allocate final accept it. |
| UPG-314 | A dashboard test fails when a random ID contains "645" | TODO | `tests/test_analytics_and_leaderboards.py:221` looks for "645" in text that also holds a random UUID, so it fails by chance. |
| UPG-315 | Certificate design: the QR code in a box the organiser places, and the number in its own box | DONE | "Where I place it (your design's QR box)": the QR dragged and resized on the design, printed there alone; the certificate number an optional box; corners and older designs as before. |
| UPG-316 | Rooms: teams of 3 and teams of 4 in separate rooms, or mixed, as the SPOC chooses | DONE | "Teams of different sizes: Mixed / Separate" before Auto-fill, and per room "As chosen below / Mixed (any size) / Only teams of N"; Separate never mixes sizes (the biggest teams first, a Mixed room takes any), hand moves still allowed and noted in the final check (`services_rooms.py:139-168`, `tests/test_room_team_sizes.py`). |
| UPG-317 | The SPOC deletes one person or the whole waitlist | DONE | A red Delete on each waiting row and "Delete the whole waitlist (N)" on the card, each with a dialog and a tick to confirm; only entries still waiting go (accepted teams, other events and accounts stay); nobody is told; they can sign up again (`services_waitlist.py:44`, `routes_coordinator.py:745`). |
| UPG-318 | The scanner lists everyone on a team, lead first, and saves each person ticked | DONE | The coordinator's scanner hid anyone without a USN (often the lead, whose USN a custom question asked), so a team of 4 showed 3, and the save marked them Absent; now everyone is listed, the lead first and marked Lead, "No USN" where none, and the save goes by each person's place on the team (`routes_ticket.py:175`, `routes_coordinator.py:1824-1843`). |
| UPG-319 | Enough database connections for heavy traffic and for a deploy | DONE | The 2026-11-19 deploy answered "Internal Server Error" to everything, pictures too: the database (db-f1-micro, 25 slots) ran out of connections, with every request reading the session and each process allowed 30; now files and health checks never touch the database, each process keeps 2 and opens at most 3 more (waiting, not failing), one process with 8 threads per copy, and the deploy guide sizes Cloud Run to the database (`session_store.py:57-63`, `:82`, `db_pg.py:50-53`, `gunicorn.conf.py:21-22`, `docs/DEPLOY.md:68`). |
| UPG-320 | The Super Admin's "Public pages" switch opens | DONE | `/reach/settings` answered 500: its on/off value was named `powered_by`, hiding the footer's `powered_by()` function; renamed (`routes_reach.py:74`, `templates/reach/settings.html:7-9`). |
| UPG-321 | Teams choose a problem statement in a set time, then it is locked | DONE | The SPOC sets when team leads choose (with an optional cap of teams per problem statement, first come, first served), locks, reopens and extends it, sees who chose what and assigns one to a team that didn't; each lead chooses or changes on the team's hackathon page only while it is open (the server's clock), and the submission is for the locked choice (`services_hackathon.py:322-623`, `:812-817`, `routes_hackathon.py:268-280`, `:312-320`, `:540-602`, `templates/hackathon/portal.html:121-153`, `templates/hackathon/manage.html:90-165`). |
| UPG-322 | The hackathon browser test fails now and then when the machine is busy | TODO | `tests/test_hackathon_browser.py:90` times out clicking "Extend deadline" ("not stable" while scrolling) when other test runs share the machine, on `fb34d9c` too; alone it passes. |
| UPG-323 | The SPOC deletes an update from "Updates for teams" | DONE | Each update on the SPOC's hackathon page has a Delete button that asks first; it comes off the teams' page (open pages refresh), audited (`services_hackathon.py:210-227`, `routes_hackathon.py:621-633`, `templates/hackathon/manage.html:232`). |
| UPG-324 | The evaluators' marks upload is always on the page, with when it opens | DONE | With outside evaluators, step 3 "Upload the evaluators' file here" is always shown (and an "Upload marks" button at the top); before the deadline it is greyed out with the closing time and a link to Deadline; after, it works (`services_hackathon_marks.py:229-234`, `routes_hackathon.py:426`, `templates/hackathon/manage.html:32`, `:287-305`). |
| UPG-325 | Every Excel/CSV download lets the person choose the columns | DONE | A download button opens "Choose the columns to download", all ticked, with Select all / Select none; the file has only the ticked columns, in its own order; the evaluators' file always keeps the team code and score (`services_export.py:331-390`, `app.py:1499-1502`, `static/js/global.js:281-382`, `routes_admin.py:158-163`, `routes_forms.py:1345-1348`; 28 buttons on 16 pages). |
| UPG-326 | Claude scores the submissions, 25 teams per step | DONE | With `ANTHROPIC_API_KEY` set, Claude (`claude-opus-5-5`, low effort, JSON held to the criteria) scores instead of Gemini, 25 teams per step with their calls at the same time; a failed call says why (busy, no credits, key refused) without the key; Gemini unchanged when only its key is set (`services_hackathon_eval.py:36-39`, `:72-110`, `:344-366`, `:408-528`, `routes_hackathon.py:421`, `templates/hackathon/manage.html:319`, `docs/DEPLOY.md:764`). |
| UPG-327 | Two conference/workshop acceptance tests fail on a ticket's foreign key | TODO | `tests/test_universal_acceptance.py:159` (conference) and the workshop lifecycle fail with `FOREIGN KEY constraint failed` inserting into `tickets` (registration id `reg-…` vs the stored registration's id), on `92d0eea` too; they passed in UPG-325's full run. |
| UPG-328 | Gemini scores with gemini-3.8-flash; busy is tried again | DONE | New Gemini keys can't use `gemini-2.5-flash` (404), so hackathon AI scoring uses `gemini-3.8-flash`, or the model `GEMINI_MODEL` names; Gemini 3 thinks a little (level low) within a 4,096-token reply, 2.5 keeps its old settings; a busy Gemini (429/503) is tried again twice (1 s, then 2 s) while the call is under 6 s old, then the team reads "busy" and "Score the rest again" retries it; a model the key can't use says so (`services_hackathon_eval.py:33-38`, `:432-445`, `:533-570`, `.env.example:201-202`, `docs/DEPLOY.md:803`). |
| UPG-329 | The portal's other Gemini features still ask for gemini-2.5-flash | TODO | 16 calls outside hackathon scoring (chatbot, AI features, matching, forms, judge, matchmaker, participant, SPOC, copilot) hard-code `gemini-2.5-flash`, which new keys can't use (404), so they fail with the new key (`chatbot_routes.py:177`, `routes_spoc.py:1317`, `services_copilot.py:85`, …). |
| UPG-330 | A font for each box of the own certificate design, ready or uploaded | DONE | Each box (name, team, USN, college, number) has a Font list: Noto Sans (default, as before), Poppins, Montserrat, Playfair Display, Cinzel, Tinos, Great Vibes, Dancing Script (OFL, bundled), or a TrueType font the organiser uploads (e.g. the font their design uses); the preview shows it; a letter the font lacks prints in Noto, Kannada and Devanagari keep theirs; issued certificates keep their font (`certificate_pdf.py:46-120`, `:448`, `services_certificate_design.py:60-86`, `:283-347`, `routes_certificates.py:315-357`, `templates/certificates/manage.html:187-197`, `:220-250`, `static/js/pages/certificates__design.js:41-46`, `:170-185`). |
| UPG-331 | Issue only the participation certificates | DONE | "Issue certificates" has a "Which certificates" list that starts on "Participation certificates only (N)" (completion or extension for those event types), or "Every certificate the event owes" (also winners, staff, organiser, speakers); a later "every" gives nobody one twice (`routes_certificates.py:380-396`, `:86-87`, `templates/certificates/manage.html:45-54`). |
| UPG-332 | The NAAC overdue-reminder test sends two reminders in the early IST morning | TODO | `tests/test_naac.py:178` expects one "report due" reminder a day and gets two; it fails on `e108d68` too, at 04:35 IST (still the day before in UTC), and passed in the 2026-11-19 runs. |
| UPG-333 | The seminar lifecycle test finds no registration in the early IST morning | TODO | `tests/test_seminar_e2e.py:178` (`assert len(alice_regs) == 1`, gets 0); fails on `e108d68` too, at 04:35 IST, and passed in the 2026-11-19 runs. |
| UPG-334 | The phone's "Results" tab opened a page that doesn't exist (404) | DONE | The phone bar's "Results" tab linked to `/live/streams`, a demo page that answers 404 in production (about 30 taps in 12 hours on 2026-11-20, the only 404s in the live log); it is now "Certificates" and opens My certificates (the owner's choice), marked current there (`templates/components/mobile_nav.html:43-47`). |
| UPG-335 | A running two-day event showed under "Past events" on the student dashboard | DONE | The dashboard counted an event past once its start date had gone, in the server's UTC date; now it stays in "My active tickets" until its last day (end date) has passed in India's date, or while it is in progress, marked "Happening now"; a lead's past hackathon card keeps the Hackathon page button (`routes_participant.py:57-77`, `:214-218`, `templates/participant/dashboard.html:216-218`, `:362-364`). |
| UPG-336 | Teams never see scores, only their place; the SPOC changes a judge's mark | DONE | The student dashboard showed "Your score" and every judge's marks as soon as a judge scored; now a team sees no score or marks, and once the results are out only its place (dashboard, hackathon page, result email and WhatsApp for a hackathon). On the hackathon page's ranking the SPOC sees each judge's mark for each team and changes it until the results are out ("edited (was N)"); the team's score, rank and results follow (`routes_participant.py:169-171`, `templates/participant/dashboard.html:259-270`, `services_hackathon_eval.py:721`, `:754-805`, `:1056`, `:1075`, `routes_hackathon.py:749-761`, `templates/hackathon/manage.html:403`, `:425-437`, `routes_coordinator.py:1390`, `utils_whatsapp.py:270-281`). |
| UPG-337 | The SPOC changes a judge's mark on the Round panel too | DONE | The owner watches round 2 on the Round panel (`/spoc/round_panel/<id>`), where UPG-336's edit boxes weren't; each team's Avg Score now lists every judge's mark with a box and Save (read-only after results), back to the same page; only the event's own SPOC opens it (`routes_spoc.py:2029`, `templates/spoc/round_panel.html:153-166`, `routes_hackathon.py:760-761`). |
| UPG-338 | A two-day hackathon owed no participation certificates to people checked in once | DONE | With "Checked in", a two-day event needs 80% of its days, so both scans; a hackathon runs straight through and nobody is scanned on day two, so SAPTHAHACKS'26 showed "Participation certificates only (0)". On a hackathon one check-in now counts as the whole event; a member marked absent at the scanner still gets none; other multi-day events keep the 80% rule (`services_certificates.py:116-120`). |
| UPG-339 | The student's Certificate button showed the built-in certificate, not the SPOC's own design | DONE | `/participant/certificate/<reg>` (the dashboard's, My events' and the ledger's Certificate button) drew a fixed HTML certificate ("This is proudly presented to", "Division SPOC") whatever the SPOC uploaded. On an event with its own design it now shows the certificate actually issued to that person, as an image with PDF and image downloads; before it's issued the student is told it isn't out yet. Events without their own design keep the built-in page (`routes_participant.py:398-409`, `templates/participant/certificate.html:167-215`). |
| UPG-340 | A team member opening the built-in certificate page sees the lead's name | TODO | `routes_participant.py:407` passes `lead_name` for whoever opens `/participant/certificate/<reg>`; a member who is allowed in (and attended) sees a certificate with the lead's name. Events with their own design are not affected (UPG-339). |
| UPG-341 | The SPOC gives one person the participation certificate by hand (a winner who wasn't checked in) | DONE | After issuing 560 participation certificates to those checked in, the owner had no way to give one to the winning teams, judged without a check-in. The Award row's Certificate list now has "Participation (your design)": it issues that person's participation certificate on the SPOC's design, once ("already has this certificate" otherwise), and touches no one else; the Award button no longer waits for a signatory when the design covers it (`services_certificates.py:245-275`, `routes_certificates.py:90-91`, `templates/certificates/manage.html:96`). |
| UPG-342 | A tournament's result becomes the event's result | DONE | A tournament published no places, no result and owed no winner certificate. `services_sports.placings` gives 1st and 2nd from the final, 3rd from the third-place match (else both losing semi-finalists) or a finished league's top three; "Publish results" on the tournament page (and the SPOC's or coordinator's generic Publish on a tournament) writes each team's place, completes the event, emails the placed leads (place only), pushes, and starts position certificates (`services_sports.py:351-433`, `routes_sports.py:146-160`, `services_certificates.py:219-220`, `routes_spoc.py:1165`, `routes_coordinator.py:1352`). |
| UPG-343 | "One check-in counts" for any multi-day event, as the SPOC's choice | TODO | UPG-338 made one check-in count on a hackathon only; a two-day tournament or fest still needs 80% of its days for a participation certificate. |
| UPG-344 | A team's own tournament page (next match, schedule, results, table) | TODO | A sports team has only the public fixtures page; nothing shows "your next match: vs X, 3 pm, Court 2", like the hackathon page does. |
| UPG-345 | Teams are told when fixtures come out, a match moves, or a result is in | TODO | Fixtures, schedule changes and results send nothing to the teams (`routes_sports.py` generate, schedule, result). |
| UPG-346 | Athletics results: heats and finals, times or distances, top 3 per discipline | TODO | The athletics type has no results at all; only knockout and league fixtures exist. |
| UPG-347 | Cultural stage order: slots, report time, "Now on stage" screen | TODO | No running order for a cultural competition; done on paper. |
| UPG-348 | A cultural performer's own page: slot, status, place, certificate | TODO | Performers have no page like the hackathon page. |
| UPG-349 | A start-to-finish test for sports, athletics and cultural events | TODO | Only the hackathon and seminar have full-journey tests. |
| UPG-350 | Kabaddi points and the "League then knockout" format | DONE | Kabaddi points (5 win, 3 tie, 1 for a loss by 7 or fewer, 0), chosen when the event's sport is Kabaddi, ranked on points then score difference; "League then knockout": the league, then "Make the playoffs" (top 4: semi-finals 1 v 4 and 2 v 3, final, optional third-place match; or top 2: final); stage names; the form defaults to the event's own format and sport (`services_sports.py:40-41`, `:69-112`, `:152-237`, `:303-333`, `routes_sports.py:57-83`, `:125-144`, `templates/spoc/tournament.html:86-120`). |
| UPG-351 | Live kabaddi match scoring and a live scoreboard | DONE | A phone scorer's page per match (raid 1–7, bonus, tackle, super tackle, all out, technical point, per team and player; undo; halves and a pausable clock; full time saves the result), each match in its own document with idempotent taps; a public scoreboard that refreshes itself every 3 s (cached 3 s) and a LIVE link on the fixtures (`services_live_match.py:40-334`, `routes_sports.py:163-248`, `templates/spoc/live_scorer.html`, `templates/public/live_match.html`, `static/js/live_match.js`). |
| UPG-352 | Kabaddi player stats: top raiders and top defenders | DONE | From the live logs: each player's raid, tackle and total points and matches, Super 10s and High 5s; top raiders and defenders on the public fixtures page, and who scored on each match's scoreboard (`services_live_match.py:336-385`, `routes_sports.py:269-280`, `templates/public/tournament_fixtures.html:38`, `templates/public/live_match.html:57-67`). |
| UPG-353 | Match scores can't be read on the staff tournament page | DONE | The staff page's scores are dark badges (`bg-dark`), and a walkover shows W/O (`templates/spoc/tournament.html:321`, `:325`). |
| UPG-354 | Two results saved at the same moment can undo each other | DONE | Every change to a tournament goes through `services_sports.change`: a lock in each copy of the app plus a lease shared by every copy (one conditional UPDATE in the counter table; a lease older than 10 s is taken over; after 8 s of waiting "Someone else is saving…"), reading the tournament afresh inside it (`services_sports.py:63-120`, `routes_sports.py:42-55`, `services_live_match.py:243-247`). |
| UPG-355 | A wrong result, or a match ended live too early, is undone from the page | DONE | "Clear the result" on any match (a knockout's winner comes back out of the next match; refused while the next match is played, with which one to clear); a correction that would change who went through says the same; "Reopen the match" on the scorer after full time; any point in the live log can be removed, not only the last (`services_sports.py:332-406`, `services_live_match.py:259-302`, `routes_sports.py:168-181`, `:332-366`, `templates/spoc/live_scorer.html:58`, `:97-102`, `static/js/live_match.js:176-186`). |
| UPG-356 | Walkovers and withdrawn teams | DONE | "Give walkover" on a match (the SPOC or a coordinator); Withdraw a team: its matches still to play become walkovers, also later knockout rounds it would reach; Bring back; a league walkover gives the win points and the loser 0, no score; W/O on both pages (`services_sports.py:408-477`, `:609-638`, `routes_sports.py:183-194`, `:215-243`, `templates/includes/tournament.html:70`, `:74`). |
| UPG-357 | A team renamed, replaced or added late; a match's teams changed | DONE | Teams card on the tournament page: rename; replace with another confirmed team (its results and live records move with it); add a late team to a league (a match against every team); "Fix this match" sets home and away of a match not yet played (a playoff seeding by toss), refused while it is scored live (`services_sports.py:479-563`, `services_live_match.py:304-333`, `routes_sports.py:196-257`, `templates/spoc/tournament.html:247-296`, `:400-435`). |
| UPG-358 | The points rule changed, the playoffs undone | DONE | "Change the points rule" under the table re-ranks it from the results (before the playoffs); "Undo the playoffs" while none is played takes the playoff matches and their live records away, so the league can be corrected; making the fixtures again forgets the old live records (`services_sports.py:565-592`, `routes_sports.py:93-118`, `:259-287`, `templates/spoc/tournament.html:137-147`, `:227-245`). |
| UPG-359 | Corrected results published again | DONE | When the fixtures no longer match the published places the result card says so and offers "Publish the corrected results": only the teams whose place changed are told, the old places' position certificates are revoked, the event's winners and ranks are rewritten; pressed with nothing changed it says so (`services_sports.py:686-783`, `routes_sports.py:289-304`, `templates/spoc/tournament.html:150-183`). |
| UPG-360 | A team corrected back to a place it once had gets no certificate for it | TODO | A revoked certificate stays the person's current one for that type (`services_certificates.py:350-375`, `services_certificate_changes.py:146-162`), so a place taken away and given back can't be issued again, and nothing on a page restores it. |
| UPG-361 | The NAAC daily reminder can go twice between midnight and 05:30 IST | TODO | `daily_reminders` compares today's IST date with the UTC date of the last reminder (`services_naac.py:52-53`, `:321`, `:332-337`), so a run after IST midnight but before UTC midnight sends again; its test failed when the suite ran across 05:30 IST. |
| UPG-362 | The coordinator's dashboard calls upcoming events "Closed" and "Event concluded" | DONE | Each card's badge is the SPOC console's status (Opens soon, Registration open, Registration closed, Event over…); "Export final data" and "Event concluded" only once the event is over; no "Delete event" on the card. `templates/coordinator/dashboard.html:79-80,95,257-262,277-281`; tests `tests/test_coordinator_card_status.py` (2). |
| UPG-363 | The welcome pop-up covers the page title on a phone | DONE | On a phone every message after an action ("Welcome back…" and the rest) sits at the bottom, above the bottom menu, and goes after 6 seconds; on a computer it stays top right, clear of the title. `static/css/global.css:1235-1245`; tests `tests/test_welcome_toast.py` (2, in Chromium). |
| UPG-364 | Buttons and labels too small to tap or read on a phone | DONE | On a phone the header's buttons, logo and profile, the sign-in page's eye, "Keep me signed in" and links, and the home page's category chips are at least 44×44 px; the bottom menu's words and the chips are at least 12 px. `static/css/global.css:2403-2420`; tests `tests/test_tap_targets.py` (1, in Chromium). |
| UPG-365 | Dates are shown as 2026-11-26 in many places | DONE | The event page's header, Key dates and share text, the admin's dashboard and events list and the coordinator's "Deadline:" say "26 Nov 2026", with the `day` filter the student's dashboard already used. `templates/public/_event_content.html:27,222,230,287`, `templates/admin/dashboard.html:6`, `templates/admin/events.html:35,75`, `templates/coordinator/dashboard.html:128`; tests `tests/test_dates_in_words.py` (1). |
| UPG-366 | The student's ticket card has five buttons in a row, Cancel among them | DONE | The card shows View ticket (and Hackathon page or Certificate when there is one) and "More"; under More: Edit details, Team page, Badge, Event info, Leaderboard, then Cancel registration below a line, still asking first. `templates/participant/dashboard.html:60-66` (style), `:299-331` (the actions); tests `tests/test_ticket_card_more.py` (2). |
| UPG-367 | Prize amounts are shown without ₹ | DONE | On the event page a prize typed as a plain amount ("3000", "Rs. 3000", "3000/-") shows as "₹3,000", grouped the Indian way; any other text as typed. `services_registration_state.py:185-204`, `app.py:313`, `templates/public/_event_content.html:171,176,181`; tests `tests/test_prize_rupees.py` (14). |
| UPG-368 | The round help button covers the bottom menu on a phone | DONE | On a phone the SPOC console's round quick-actions button sits 16 px above the bottom menu instead of on its last item; back to top was already above it. `templates/spoc/dashboard.html:824-827`; tests `tests/test_round_buttons.py` (1, in Chromium). |
| UPG-369 | The admin's lists are wider than a phone | TODO | "All events" is 815 px wide on a 390 px screen: the event name, kind, date and "Visitors see" are squeezed into one narrow column, one word a line, and status and registrations are off the screen. |
| UPG-370 | The admin dashboard's numbers fill a whole phone screen | TODO | The six number cards (events, registrations, revenue, staff, SPOCs, students) are one per row on a phone, about 1,100 px before anything else. |
| UPG-371 | The coordinator's event cards start with a large empty banner | TODO | With no event image, each card on the coordinator's dashboard begins with a 130 px dark block holding only an icon. |
| UPG-372 | The tournament page's fields have no labels | TODO | The score, winner, date, time, venue and home/away fields on the SPOC's tournament page have no label a screen reader can read (`templates/spoc/tournament.html`, the match forms). |
| UPG-373 | A What's new page with every version | DONE | `/whats-new` lists every version from v1.0 (20 Oct 2026) to this one, each with its date, a title and what changed in plain words, newest first, from `config/releases.json`; the footer on every page shows "What's new · v1.16"; a test fails if a finished item is in no version (`services_releases.py`, `routes_marketing.py:45-49`, `templates/public/whats_new.html`, `templates/includes/site_footer.html:8-9`, `app.py:402`). |
| UPG-374 | The SPOC's console on a phone opens with no heading | TODO | On a 390 px screen `/spoc/dashboard` opens on the search box and event list; its only heading ("…'s console", `templates/spoc/dashboard.html:1257`) is in the overview column, hidden on a phone until an event or Global Overview is picked (`:770-776`). Found building UPG-363. |
| UPG-375 | The coordinator's page hides a running two-day event on its second day | TODO | `routes_coordinator.py:96-101` hides an event once its first `date` is before today (the server's date, UTC on Cloud Run), not its `end_date` in India: a two-day hackathon leaves the coordinator's page on day 2. |
| UPG-376 | `ruff check .` fails on the problem-selection tests | TODO | `tests/test_hackathon_problem_selection.py` (UPG-321): an unused `datetime` import (line 12) and 10 F811 "redefinition of `hack`" (the fixture imported at line 16 and taken as an argument); the full-repo lint the gap-closure plan asks for fails. |
| UPG-377 | The result email says "Team Team Phoenix" | DONE | "Team" is written only when the name doesn't already start with it (any case): the result email, the badge, the student's ticket and waitlist cards; a `team` filter. `services_registration_state.py:243-249`, `app.py:314`, `utils_email.py:1075-1077,1094`, `services_badges.py:53-54`, `templates/participant/dashboard.html:159`, `templates/participant/_waitlist.html:12`; tests `tests/test_team_label.py` (11). |
| UPG-378 | Check-in after the event and on day two | DONE | Check-in is open from the event's first day to its last, in India (it was the first day only, by the server's UTC clock); before it "Check-in opens on 19 Nov 2026". After the event the SPOC's list says "Mark present": a confirm, then present for every day of the event, `checkin_late`, who marked them, `LATE_CHECKIN` in the audit log; not a cancelled team or one off the entry list. A note links to issuing certificates again (only the newly present get one). `services_registration_state.py:252-264` (the window); `routes_spoc.py:780-791` (the scan page), `:811-830` (the check-in), `:880-911` (`_late_checkin`); `templates/spoc/scan.html:194-200,233-241,286,385,405-406,420`; `routes_coordinator.py:1647-1650`, `templates/coordinator/scan.html:50-54`; tests `tests/test_late_checkin.py` (13). |
| UPG-379 | The SPOC's scanner lets a cancelled team in and records no day | TODO | `routes_spoc.py:822-878` (the in-window check-in) doesn't refuse a cancelled registration or one left off the entry list (`services_entry`), and writes no `attendance_days`, so on a multi-day event that isn't a hackathon a SPOC-scanned person has 1 day and can miss the 80% certificate rule. |

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
  - **Receipt.** A completed payment with an amount queues one receipt email: amount, event, registration, payment ID (`routes_payment.py:351`, `utils_email.send_payment_receipt_email`, `utils_email.py:927`).
  - **Completion never overbooks or loses money** (`routes_payment.py:306`). It re-checks capacity; a held waitlist seat is already counted.
    - When completion fails after the order is claimed (full, already registered, an error), the order stays paid with its reason recorded (`:208`).
    - The payer gets 202 and `RECORDED_MESSAGE` (`:18`): the payment is recorded and will be completed or refunded. The checkout page shows it.
  - **Webhook: `POST /payment/webhook/razorpay` (`:397`).** It is CSRF-exempt and authenticated by `X-Razorpay-Signature` with `RAZORPAY_WEBHOOK_SECRET`; without the secret it answers 503.
    - On `payment.captured` it claims the order atomically, but only if Razorpay's amount is the order's (`claim_paid_order`, `services_payments.py:239`). It then completes the stored registration once.
    - If the browser's `/payment/verify` arrives after the webhook, it is sent to the ticket (`routes_payment.py:180`).
    - Replays, unknown orders and wrong amounts change nothing.
  - **The admin's payments page `/admin/payments`** (Super Admin only, 403 otherwise; `routes_admin.py:599`), linked from both admin navigations:
    - paid orders with no registration, each with a Razorpay refund that needs a ticked confirmation. The refund moves the order to `refunding` atomically, so only one request calls the API; it records refund ID, time and admin, audit-logs it, and undoes the claim if the API fails (`:527`, `start_refund` `services_payments.py:265`).
    - paid registrations, each markable refunded (money returned another way) or cancelled with a reason, audit-logged (`:736`). Both set the registration `cancelled`, refunded also sets the payment `Refunded`, and check-in refuses either (`routes_ticket.py:248` after UPG-318; `:169` before).
  - **Finance export.** `/admin/analytics/export/payments`: one row per order with payment, amount, status, registration and refund (`routes_admin.py:203`).
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
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still IN PROGRESS. The receipt email is now `utils_email.py:927` (it had moved before Phase 2; corrected). Phase 2 didn't touch payments; a paid portal-mode hackathon is still UPG-201.

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
- **Re-verified 2026-10-19 (rule 8, end of Part 3, at `221cef3`):** still TODO. `pyrefly check` now reports 1,081 errors (1,044 when written): 7 are in the new certificate code (`certificate_pdf.py:172`, `services_certificates.py:405`, `services_signatories.py:53-67`), all of the noise kinds above (PIL's `load()` typed as optional, qrcode's image factory, SQLAlchemy's `Result.rowcount`); the rest come from Parts 2–3.
- **Re-verified 2026-10-19 (rule 8, end of the certificate phase, at `71c2f09`):** still TODO. `pyrefly check` reports 1,119 errors (1,081 at the end of Part 3). The certificate code adds 9, all of the known noise kinds (PIL's `load()` typed as optional, qrcode's image factory, SQLAlchemy's `Result.rowcount`, a lookup that can't be `None` after an update in `services_certificate_changes.revoke`); the one real finding (the fallback limiter without `shared_limit`) is fixed as a UPG-126 follow-up. `routes_coordinator.py` stays at 0 (`tests/test_type_check_config.py`).
- **Re-verified 2026-10-20 (end of the NAAC / reach / WhatsApp run, at `3a8fb29`):** still TODO; `pyrefly check` reports 1,139 errors (1,119 before this run), the new ones in the new modules and of the known noise kinds; `routes_coordinator.py` stays at 0.
- **Re-verified 2026-10-31 (rule 8, after UPG-149 and UPG-150, on `f6fcf99`):** still TODO. `pyrefly check` reports 1,136 errors (1,139 before); the new `services_rounds.py` has 0, `routes_coordinator.py` stays at 0, and the new `routes_forms` helpers add none (its 13 are the known optional-import and placement noise).
- **Re-verified 2026-10-31 (rule 8, early pass during UPG-152, because `tests/conftest.py` and `models_pg.py` changed; on `57a5922` plus UPG-152):** still TODO. `pyrefly check` reports 1,145 errors (1,136 before). In the changed files the new ones are: two `unbound-name` for `send_set_password_link` in `routes_participant.py` (a false positive: it is imported at `:509` and both calls, `:551` and `:573`, sit under the same `is_new_user`), SQLAlchemy's `Result.rowcount` in `services_email_quota.py`, and an unpacked `**kwargs` at `routes_admin.py:496` against the new `from_registration` parameter, all known noise kinds; the rest are in the new test file. `routes_coordinator.py` stays at 0.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO. `pyrefly check` reports 1,196 errors, the same as before Phase 1; the new `services_hackathon.py`, `routes_hackathon.py` and `tests/test_hackathon_portal.py` have 0 (two found in Phase 1's own code were fixed), and `routes_coordinator.py` stays at 0.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO. `pyrefly check` reports 1,196 errors, the same as at the end of Phase 1; the new `services_hackathon_eval.py` and the three new test files have 0 (four found in Phase 2's own code were fixed), `services_rounds.py` and `routes_hackathon.py` stay at 0, and `routes_coordinator.py` stays at 0.

#### UPG-151 — Writing an empty `scores` map keeps the old scores (postgres mode)
- **Status:** TODO
- **Last verified:** 2026-10-31, commit `f6fcf99` [R, found by `tests/test_multi_round.py` while building UPG-149]
- **Problem:** In the SQL adapter, a registration's judge scores live in their own `Score` table. `update({'scores': {...}})` adds or changes one row per judge in the map (`db_adapter.py:1530-1532`), so `update({'scores': {}})` deletes nothing; only `firestore.DELETE_FIELD` clears the rows. Firestore would replace the map with an empty one. The round panel's old advance relied on `{}` (`routes_spoc.py:1989` at `f6fcf99`), so in postgres mode round 1's scores were still counted in round 2. UPG-149 now uses `DELETE_FIELD` (`services_rounds.py:193`). No other code writes an empty map to an existing registration: `demo_reset.py:630` writes `{}` only when it creates a new one. Any future "reset the scores" code would hit the same trap.
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
- **Problem:** `::test_the_super_admin_sees_who_is_waiting_and_a_resend_button_only_for_them` (and one more in the file) look for a just-made account on the first page of `/admin/users`, which shows 25 a page in email order (`routes_admin.py:372`). When enough earlier tests in the same run have made accounts that sort before it, the row is on page 2 and the test fails. It fails the same way on the unchanged code with the same test selection (checked with `git stash`); it passes alone and in the normal full run, so it depends on test order, not on a bug in the page.
  - The same happens on PostgreSQL whenever `TEST_DATABASE_URL` isn't an empty database: a reused test database had 1,873 accounts left from earlier runs (328 sorting before the test's), and all three page tests in the file failed; on a fresh database they pass.
  - **Seen again 2026-11-14:** `tests/test_add_members_window.py` (UPG-250) sorted before this file and made accounts sorting before its own; both page tests failed in the full run and passed alone. Renamed `tests/test_team_add_members_window.py`, as `tests/test_spoc_add_team.py` was.
- **What to build:** find the row with the page's search (`?q=<email>`) instead of assuming page 1, or give the test's accounts addresses that sort first. Don't change the page.
- **Effort:** S · **Depends on:** none · **Risk:** none (tests only).
- **Acceptance criteria:**
  1. Test: the file passes after a test that makes 30 accounts sorting before its own.
- **Re-verified 2026-11-05 (rule 8, end of hackathon Phase 1, UPG-190/191/195/196/197; uncommitted on `57a5922`):** still TODO; `tests/test_admin_users.py` and `routes_admin.py` are unchanged. Phase 1's tests add accounts (`hklead…`, `hkspoc…`, `role…`), so the order dependence can still show.
- **Re-verified 2026-11-12 (UPG-244, uncommitted on `ddcc1a8`):** still TODO and showed again: in the full run, `::test_the_super_admin_sees_who_is_waiting_and_a_resend_button_only_for_them` failed ("waiting-…@test.edu listed 0 times") because UPG-244's new test file, then named `tests/test_add_team.py`, ran before it and with `tests/test_account_emails.py` made enough accounts sorting before its own; it passes alone and without either file. The new file is now `tests/test_spoc_add_team.py` (it runs after, with the other SPOC tests); `tests/test_admin_users.py` is unchanged. Any new test file sorting before `test_admin_users.py` that makes accounts can bring it back until this item is built.
- **Re-verified 2026-11-15 (rule 8, end of the ten-gaps change, UPG-266 to UPG-275; uncommitted on `a4809a8`):** still TODO and showed again: in the full run the first page test failed ("waiting-…@test.edu listed 0 times") because a new test file, then named `tests/test_access_modes.py` (UPG-270), ran before it; it passed alone. Renamed `tests/test_audience_modes.py`, as the earlier ones were; `tests/test_admin_users.py` is unchanged.

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
- **Problem:** Market: KonfHub (AI gallery), Whova, Accelevents and District show event photos. SapthaEvent lets coordinators paste media URLs only (`routes_coordinator.py:1041-1053`, corrected 2026-11-12 by the rule 8 check for UPG-239 to UPG-241; it cited `:310-322`, which no longer pointed at it).
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
- **Problem:** Market: Airmeet, Goldcast, Glue Up and EventsAir generate event copy, summaries and social posts. SapthaEvent has a generator endpoint (`routes_ai_features.py:32` `/generate_event_details`) that no page calls, and a post-event debrief with a fallback (`routes_spoc.py:1276-1325`, corrected 2026-11-17); UPG-85 (results summaries) was dropped.
  - **Corrected 2026-11-02 (found building UPG-155):** the wizard already has a "Write with AI" button for the description and rules (`templates/spoc/create_event.html:141-148`; `static/js/pages/spoc__create_event.js:163-180`) calling `POST /spoc/marketing/event_writer` (`routes_spoc.py:2569`, corrected 2026-11-17). It writes straight into both fields (no accept step), and with no `GEMINI_API_KEY` it fills them with a fixed generic text instead of hiding. So this item changes that button rather than adding one.
- **Who benefits:** SPOCs and coordinators writing every event from scratch.
- **What to build:** the wizard's existing "Write with AI" button shows its draft for the organiser to accept before it fills the description and rules, and is hidden with no AI key (no fixed text); social post drafts (Instagram, LinkedIn, WhatsApp) from the event page; the post-event summary from real counts; every AI call has a timeout, a plain fallback and never invents facts (UPG-108's rule); off when no AI key is set.
- **Effort:** S · **Depends on:** none · **Risk:** AI text is a draft: never saved or published without the organiser's edit/accept.
- **Acceptance criteria:**
  1. Test (AI mocked): the wizard button fills the field only after accept.
  2. Test: with no AI key the button is hidden and nothing errors (UPG-109).
  3. Test: the prompt contains only the event's real fields; the summary's numbers equal the report's.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the event writer route is now `routes_spoc.py:2466` (corrected).

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
- **Problem:** Beyond the market: Indian fests award an overall championship by college; no platform read does this. SapthaEvent has fests with sub-events (UPG-74, `parent_event_id`, `app.py:1056`) and external colleges (UPG-146), but no points per college.
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
- **Problem:** Market: Accelevents, Cvent, EventsAir, Glue Up, Luma and Ticket Tailor support recurring or repeatable events. SapthaEvent can clone an event (`routes_spoc.py:1319`; was `:1285` before Phase 1) but has no series.
- **Who benefits:** clubs, departments running lecture series, NSS weekly activities.
- **What to build:** a repeat rule in the wizard (weekly/monthly, count or end date); occurrences created as linked events with one approval for the series; register for one or all; series attendance on the student's record and ledger.
- **Effort:** M · **Depends on:** none · **Risk:** approval: one approval covers the series; edits to one occurrence don't change others unless chosen.
- **Acceptance criteria:**
  1. Test: a weekly series of 6 creates 6 linked occurrences on the right dates (IST).
  2. Test: approving the series opens all occurrences.
  3. Test: cancelling one occurrence notifies only its registrants.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the clone route is now `routes_spoc.py:1319` (corrected).

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
- **Problem:** A free registration and a free waitlist promotion also get a `tickets` record from `TicketService.issue_ticket` (`routes_forms.py:1125` after UPG-244, `routes_waitlist.py:333` after UPG-243, was `:292` before UPG-230; `services_ticket.py:139`) holding the lead's email and name and its own signed QR. `services_transfer.transfer` (`services_transfer.py:128`) updates only the registration. After a transfer the old holder can still open `/ticket/wallet/<ticket id>` (owner by the record's email, `routes_ticket.py:885-910` after UPG-318; `:831-853` before) and sees a pass whose QR every scanner refuses (that token has no ticket generation, so `token_is_current` is false); the new holder can't open it. Entry stays safe; the page and the record are wrong.
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
- **Problem:** `blast_email` builds the email with `{name}` (the registrant's `lead_name`, typed by the participant) and `{body}` (the SPOC's text) straight into the HTML (`routes_spoc.py:1295-1296`; the preview builds `{body}` the same way, `:1216`). A lead's name like `<a href=…>` becomes a link in the email the SPOC sends, and the SPOC's own text renders as HTML. In portal mode (UPG-195) the blast becomes a portal update, which the page escapes; for every other event the email is still built this way.
- **What to build:** escape `name` and `body` with `utils_email._e` (keeping line breaks with `white-space:pre-wrap`, as now); escape the subject in the wrapper's title.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a lead named `<b>x</b>` and a body with `<script>` arrive escaped in the sent HTML; line breaks are kept.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the blast builds `{name}` and `{body}` into the HTML at `routes_spoc.py:1295-1296` and the preview at `:1216` (corrected). Portal-mode hackathons still post it as an escaped update.

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
- **Problem:** `routes_coordinator.publish_results` starts a background thread whose function opens `current_app.app_context()` (`routes_coordinator.py:1402-1417` after UPG-317, `:1328-1340` after UPG-246, `:1293-1305` after UPG-239/240, `:1094-1106` after UPG-234/235, `:1033-1045` after UPG-230; cited as `:591-594` before, the same code at `57a5922`, `:455`). `current_app` is a request-bound proxy, so inside the thread it raises "Working outside of application context." and the summaries are never generated (the exception only shows as a pytest thread warning). The session values it copies are read inside the thread too.
- **What to build:** capture `current_app._get_current_object()` and the session values before starting the thread (or queue the job through the outbox), and log a failure.
- **Effort:** S · **Depends on:** none · **Risk:** low; it is best-effort today.
- **Acceptance criteria:**
  1. Test: publishing results starts the summary job with the app and the coordinator's details, and no thread exception is raised.
- **Re-verified 2026-11-06 (rule 8, end of hackathon Phase 2, UPG-192/193/194; uncommitted on `57a5922`):** still TODO; the thread now starts at `routes_coordinator.py:673-676` (corrected), after the new portal-mode result step (UPG-194), which runs in the request and is unaffected.
- **Re-verified 2026-11-15 (rule 8, end of the ten-gaps change, UPG-266 to UPG-275; uncommitted on `a4809a8`):** still TODO; the thread's function is at `routes_coordinator.py:1335`, and "Working outside of application context" is in the full run's log. `publish_results` was not changed.

#### UPG-208 — The organiser's certificate correction can't change a certificate's email
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [C, found building UPG-207]
- **Problem:** A correction (UPG-127) makes a new version with a new name only (`services_certificate_changes.new_version`, `services_certificate_changes.py:110`, keeps `recipient_email=old['email']` at `:126`). Since UPG-207 the team page refuses to change a member's email once a certificate was issued to it and sends the lead to the organiser, but the organiser can only revoke it and issue it again (a new number).
- **What to build:** on the certificate page, the organiser corrects the email of a certificate (and of the team member it came from), keeping the number as a new version, emailing the new address, audit-logged.
- **Effort:** S · **Depends on:** UPG-127, UPG-207 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the organiser changes a certificate's email; the number stays with the next version; it appears in the new email's "My certificates" and no longer in the old one's; audit-logged; another SPOC gets 403.

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
- **Problem:** The shared check-in refuses a cancelled or refunded registration (`routes_ticket.py:248` after UPG-318; `:205` before), so the scanners and the kiosk do. Three other ways to mark someone present don't look at the status: student self check-in (`submit_self_checkin`, `routes_checkin.py:89`: it finds the registration by the student's email and marks it Present), the coordinator's per-member tick (`mark_attendance_granular`, `routes_coordinator.py:1809` after UPG-317, `:1665` after UPG-246, `:1596` after UPG-239/240, `:1397` before) and the admin's attendance setting (`set_attendance`, `routes_admin.py:1693`). A team the SPOC cancelled with UPG-211 can still self check-in, be ticked present, and then count as attended (certificates, reports).
- **What to build:** refuse "Present" for a cancelled or refunded registration on all three paths, with the same message as the scanner; self check-in shows "Please see the registration desk"; marking absent stays allowed.
- **Effort:** S · **Depends on:** — · **Risk:** low.
- **Acceptance criteria:**
  1. On the real database layer, a cancelled registration can't be marked present by self check-in, the coordinator's tick or the admin's setting; each answer says so; attendance is unchanged.
  2. An active registration is still checked in by each path as today.

#### UPG-217 — The SQL store keeps only a form's fields
- **Status:** TODO
- **Last verified:** 2026-11-09, uncommitted on `a700892` [R, found building UPG-216]
- **Problem:** `event_forms` has one column, `fieldsJson`, and the adapter maps the key `fields` onto it (`db_adapter.py:75`), so `set()` writes only the list of fields: everything else in the form document (`form_title`, `form_desc`, `form_type`, the wizard's `source`, `created_by`, `updated_at`) is dropped, even on the first save; reading gives back "Registration Form" (`db_adapter.py:1054`). UPG-212 and UPG-216 work around it for the builder by keeping those settings on the event; other writers still lose theirs: `services_event.py:183` (a cloned event's title "X Registration"), `routes_spoc.py:337` (the wizard's `source`), `services_copilot.py:346`, `routes_api_v1.py:326`.
- **What to build:** store the whole form document in `fieldsJson` (reading already accepts a list or a document), merged on `set(merge=True)`; then `_get_form` can stop reading the title from the event (keeping the event's values as the fallback for forms saved before).
- **Effort:** S · **Depends on:** — · **Risk:** medium: `db_adapter.py` is shared, so a full re-verification of open items comes with it (CLAUDE.md rule 8).
- **Acceptance criteria:**
  1. On the real database layer, a form saved with a title, description, type and source reads back with all of them, after a first save and after a second one.
  2. A form stored as a bare list (every form saved before) still reads back with its fields.

#### UPG-221 — The walk-in desk registers a person differently from the online form
- **Last verified:** 2026-11-10, on `6a2638c` [C]
- **Problem:** Owner, 2026-11-10: "does on spot register work for SAPTHAHACKS the same as the actual register". It doesn't. `/coordinator/on_spot` (`templates/coordinator/on_spot.html`, `routes_coordinator.py:1493` after UPG-317, `:1416` after UPG-246, `:1347` after UPG-239/240, `:1148` before) asks a fixed name, USN, email and phone with USN and phone required, then saves the person as a team of one named after them, with no members and no team code (nobody can join), none of the event's questions, no seat-limit check and no `registration_count` increase (later online sign-ups see too many free seats), `payment_status` "Paid" at `fees.regular` with Cash or UPI asked even for a free event, and no participant type, ticket type or privacy consent.
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
- **Problem:** Found building UPG-227. `participation_ledger` (`routes_participant.py:1150` after UPG-336, `:1149` after UPG-335, `:1132` after UPG-306, `:1118` after UPG-246, `:1157` with UPG-238, `:1103` after UPG-239) and `services_privacy.registrations_of` (`services_privacy.py:79`) stream the whole `registrations` collection on each request to find the teams a person is a member of; with thousands of registrations this is slow and grows with every event.
- **What to build:** both use UPG-227's `member_registrations` (`routes_participant.py:101`, moved to a service), which finds them through the `team_members` rows by email.
- **Effort:** S · **Depends on:** UPG-227 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. The activity points page and the privacy export list the same registrations as before, a member's teams included, without reading every registration.

#### UPG-247 — A cancelled team that came off the waitlist still shows "Accepted" on its waitlist card
- **Status:** TODO
- **Last verified:** 2026-11-12, uncommitted on `ddcc1a8` [C, found building UPG-245]
- **Problem:** `services_waitlist.standing` shows a promoted entry by the registration the promotion made (`services_waitlist.py:144-155` after UPG-317; `:133-144` before). `_registration` (`:85-90`) prefers a live one but falls back to a cancelled or refunded one, so when the SPOC cancels a team that came off the waitlist (UPG-211), the lead's and members' waitlist card still says "Accepted: registered" with "See your registration". UPG-245 handled the deleted case (no registration left: the card goes).
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

#### UPG-258 — An email that bounces marks the member "wrong address?" for the lead and the SPOC
- **Status:** TODO
- **Last verified:** 2026-11-14, commit `e7afca9` [C]
- **Problem:** A link sent to a mistyped address just never gets used; nobody learns it bounced.
- **What to build:** a signed Brevo webhook endpoint; a hard bounce or invalid address marks the person's registration or member row `email_bounced`, shown as "Email bounced. Wrong address?" on the team page and the SPOC's list, with a portal notice to the lead.
- **Effort:** S · **Depends on:** UPG-255 (DONE), and Brevo as the main sender (D-14) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a bounce event for a member's address marks the member and notifies the lead; a request without the shared secret is refused.

### Found while closing the ten gaps (2026-11-15)

#### UPG-276 — The event's calendar file checks who may see the event
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-271. `GET /events/<slug>/calendar.ics` (`app.py:893-921`) returns the title, time and venue of any event by slug or ID, with no check of its status or visibility: a draft or a department-only event can be read by anyone who has the address.
- **Who benefits:** organisers of events that aren't public yet.
- **What to build:** apply the event page's own visibility rule before answering; 404 otherwise.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the file of a public, open event downloads; a draft, a cancelled-and-hidden or a department-only event answers 404 to a visitor.

#### UPG-277 — The check-in time is written in IST, like the attendance day
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-269. `routes_ticket._now()` (`routes_ticket.py:110`) is the server's local time, while the attendance day is IST (`:243`). On Cloud Run (UTC) the saved check-in time is 5½ hours behind the gate's clock.
- **Who benefits:** organisers reading check-in times.
- **What to build:** write the time in IST (the same clock as the day), for online and offline scans.
- **Effort:** S · **Depends on:** none · **Risk:** low (existing rows keep their old times).
- **Acceptance criteria:**
  1. Test: with the server's clock on UTC, a check-in at 10:00 IST is saved as 10:00.

#### UPG-278 — The public API's event answer holds only public fields, and only for listed events
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-271 and seen in the browser check. `GET /api/v1/events/<id>` (`routes_api_v1.py:254-267`) needs no login and returns the whole event document, for any event whatever its status: the `staff` list with each person's email, and drafts. The run sheet's owner and note are not in it (UPG-272 keeps them apart).
- **Who benefits:** the event's staff (their emails), and organisers of unpublished events.
- **What to build:** answer with an allow-list of public fields, and 404 for an event the public pages wouldn't list; the full document only to a signed-in person who manages the event. Privacy: propose doing this before other UPG work.
- **Effort:** S · **Depends on:** none · **Risk:** medium (a client reading other fields would lose them; none is known).
- **Acceptance criteria:**
  1. Test: a visitor's answer has no `staff`, no email address and none of the organiser-only fields; a draft answers 404.
  2. Test: the event's SPOC still gets the full document.

#### UPG-279 — The event popup, the open-events page and the student dashboard follow changes too
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-267. These three show UPG-266's state when loaded but have no live region, so they stay as they were until reloaded.
- **Who benefits:** students and visitors with one of these pages open.
- **What to build:** add the `data-live-event` regions and load `static/js/live-refresh.js` on them.
- **Effort:** S · **Depends on:** UPG-267 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. Test (browser): each of the three follows a change from open to waitlist without a reload.

#### UPG-280 — "This institution only" checks that the person is from the institution
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-270. The mode refuses the outside participant types, but a person who picks "student" isn't checked against a campus email domain or the roster (`services_reach.refusal`, `:167`).
- **Who benefits:** organisers of campus-only events.
- **What to build:** needs the owner's rule first (D-17): the campus email domain (`GOOGLE_ALLOWED_DOMAIN` or a new setting on the institution page), the roster, or both.
- **Effort:** M · **Depends on:** D-17 · **Risk:** medium (a wrong rule locks real students out).
- **Acceptance criteria:**
  1. Test: with the rule on, an address outside it is refused with the reason; one inside registers.

#### UPG-281 — Microsoft sign-in: verify it or take its routes out
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-271. `auth_oauth.py` has Microsoft routes; the login page doesn't offer them, they have never been run against a Microsoft tenant, and `docs/INTEGRATIONS.md` says so.
- **Who benefits:** the owner (less unused sign-in code), or institutions on Microsoft 365 if it is finished.
- **What to build:** owner's choice: finish and test against a Microsoft tenant (needs credentials), or remove the routes.
- **Effort:** S to M · **Depends on:** Microsoft credentials or the owner's decision · **Risk:** low.
- **Acceptance criteria:**
  1. Test: either a sign-in round trip with the provider stubbed and the button shown only when configured, or the routes answer 404.

#### UPG-282 — The one-request roster upload for scripts gets a dry run
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-271. `POST /admin/users/import_csv` (`routes_admin.py:384`) runs the same checks as the page but writes at once; a script can't see what a file would do first.
- **Who benefits:** administrators who upload the roster from a script.
- **What to build:** a `dry_run=1` argument that returns the check's counts and problems and writes nothing.
- **Effort:** S · **Depends on:** UPG-271 (DONE) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: with `dry_run=1` nothing changes and the answer has the counts; without it, as today.

#### UPG-283 — Remove `CLOSED_STATUSES` from routes_forms.py
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-266. `routes_forms.py:83` still defines `CLOSED_STATUSES`; nothing reads it since the gate moved to `services_registration_state`.
- **Who benefits:** whoever reads the form's code next.
- **What to build:** delete it.
- **Effort:** S · **Depends on:** none · **Risk:** none.
- **Acceptance criteria:**
  1. The name appears nowhere; the full suite passes.

#### UPG-284 — The API's role checks use the role names accounts really have
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-271. `routes_api_v1.py` asks for `Admin`, `Coordinator`, `SPOC` and `Organizer` (`:339`, `:351`, `:747`), while accounts are stored as `SuperAdmin`, `EventCoordinator` and `ClubSPOC`. Not run: whether `jwt_roles_required` maps one to the other wasn't checked.
- **Who benefits:** anyone using the API as a coordinator or SPOC.
- **What to build:** check with a token for each stored role; make the lists use the stored names (or one mapping).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: a token for each stored role reaches exactly the endpoints its role should, and no other.

#### UPG-285 — Schedule items have a day
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-272. An agenda item has a time but no day, so for an event longer than a day every room or owner clash can only be a warning (`services_runsheet.py:89`).
- **Who benefits:** organisers of multi-day events.
- **What to build:** an optional day on each item (within the event's dates); clash checks per day; the schedule pages grouped by day.
- **Effort:** M · **Depends on:** UPG-272 (DONE) · **Risk:** medium (session check-in and "My agenda" read the same items).
- **Acceptance criteria:**
  1. Test: on a two-day event, the same room at the same time on one day is refused, on different days it saves with no warning.

#### UPG-286 — The data download and the deletion reach the remaining records
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-274, listed in `docs/DATA_HANDLING.md` ("Not reached by the download or the deletion today"): session stars, live votes and questions, push subscriptions, session attendance, project submissions, exam attempts, waitlist entries, the `tickets` and `checkins` records, and uploaded files.
- **Who benefits:** anyone using their right to a copy or to deletion.
- **What to build:** add each to `services_privacy.own_data` and `anonymise_account`, one collection at a time; what is kept for reports follows D-7 and D-15.
- **Effort:** M · **Depends on:** D-15 for what must be kept · **Risk:** medium (deleting too much breaks event reports).
- **Acceptance criteria:**
  1. Test, per collection: the download holds the person's rows and nobody else's; after deletion the person's details are gone and the event's counts are unchanged.

#### UPG-287 — The `/pricing` page: remove it or replace it with real terms
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Left by UPG-275. `templates/marketing/pricing.html` (behind `DEMO_PAGES_ENABLED`, off by default) states prices, a platform fee and Stripe checkout (`:90`, `:121`); none of it exists. Not edited in UPG-275 because it is fees copy.
- **Who benefits:** any buyer who is shown the page.
- **What to build:** owner's decision (D-16): delete the route and template, or write the real terms.
- **Effort:** S · **Depends on:** D-16 · **Risk:** none while the flag is off.
- **Acceptance criteria:**
  1. Test: `/pricing` answers 404 with the flag on or off, or the page states only what D-16 decides.

#### UPG-288 — Three public statements the code doesn't back
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-274 and UPG-275. (a) The privacy notice says registration and attendance data is "retained for 5 years" (`templates/public/privacy.html:51`); no job deletes anything after five years. (b) The home page's chip says "Email & WhatsApp updates" (`templates/index.html:405`); WhatsApp is sent only when a provider is configured. (c) `docs/DEPLOY.md:540-542` (`:488-490` before UPG-319) says exports are handed out through links that expire after 15 minutes; no code calls `utils_storage.signed_url`, exports are built on request and not kept.
- **Who benefits:** people reading the notice, the home page or the deploy guide.
- **What to build:** (a) follows D-15 (the period is a policy question); (b) say "Email updates" unless a WhatsApp provider is set; (c) correct the paragraph.
- **Effort:** S · **Depends on:** D-15 for (a) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the chip names WhatsApp only when a provider is configured.
  2. The deploy guide and the notice say what the code does.

#### UPG-289 — Two pagination tests fail at `a4809a8`, before this change
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [R]
- **Problem:** Found in the baseline run on a clean copy of `a4809a8`, and the same in this change's full runs: `tests/test_pagination_lists.py::test_each_list_shows_25_and_page_5_holds_the_last_20[coordinator registrations]` and `::test_search_narrows_each_list_and_combines_with_the_page[coordinator registrations]` fail. Both are about the coordinator's registrations list, last changed by UPG-264 and UPG-265 (built without a test run, owner's instruction). (The baseline copy also failed `tests/test_type_check_config.py`, only because that copy had no Python environment for Pyrefly; it passes in the repository.)
- **Who benefits:** everyone running the suite.
- **What to build:** find what UPG-264/265 changed in the list's paging with the filters; fix the code, not the tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. The two tests pass, unchanged.

#### UPG-290 — Ticket signing has no key written in the code
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-269. `services_ticket._get_signing_key` (`services_ticket.py:29-32`) falls back to a fixed text when neither `SECRET_KEY` nor `JWT_SECRET_KEY` is set. Production refuses to start without `SECRET_KEY`, so the fallback is reachable only in development, but a ticket signed there could be forged by anyone who reads the repository.
- **Who benefits:** the gate.
- **What to build:** take the key from the app's configuration and fail when there is none.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: with no key configured, signing raises; with one, tickets verify as today.

#### UPG-291 — The audit log shows when it has been altered
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-274. The audit log is ordinary rows; an administrator with database access can change or delete one unseen. `docs/SECURITY.md` ("Known limits") says so.
- **Who benefits:** the institution, when an action is disputed.
- **What to build:** chain each entry to the one before with a hash, and a check that reports the first broken link. How long entries and their IP addresses are kept is D-15.
- **Effort:** M · **Depends on:** none · **Risk:** medium (`db_adapter.py` and `utils.log_action` are used everywhere).
- **Acceptance criteria:**
  1. Test: changing or deleting an entry makes the check report it.

#### UPG-292 — A calendar feed of the institution's public events
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found in UPG-271. A person has their own feed (`/calendar/feed.ics`) and each event has a file, but there is no one address a department or a notice board can subscribe to for every public event. `docs/INTEGRATIONS.md` says so.
- **Who benefits:** departments, notice boards and students who want every event in their calendar.
- **What to build:** `/calendar/public.ics`: the events the catalogue lists, nothing else.
- **Effort:** S · **Depends on:** UPG-276 (the same visibility rule) · **Risk:** low.
- **Acceptance criteria:**
  1. Test: the feed holds the catalogue's events and no draft, cancelled or department-only event.

#### UPG-293 — `tests/test_certificate_delivery.py` has lost its first 65 lines in the working tree
- **Status:** TODO
- **Last verified:** 2026-11-15, uncommitted on `a4809a8` [C]
- **Problem:** Found before UPG-266 began. An uncommitted change dated 2026-11-13 removed the file's docstring, imports and its `mail` and `site` fixtures (`git diff HEAD -- tests/test_certificate_delivery.py`: 65 lines deleted). The file no longer parses, so it and the two files that import from it (`tests/test_certificate_awards.py`, `tests/test_certificate_changes.py`) can't be collected, `tests/test_repo_hygiene.py::test_no_mail_password_in_tracked_files` fails on it, and ruff reports one error. The committed copy is whole. Not touched: it is the owner's uncommitted change.
- **Who benefits:** everyone running the suite.
- **What to build:** owner: `git checkout -- tests/test_certificate_delivery.py` (unless the change was meant).
- **Effort:** S · **Depends on:** the owner · **Risk:** none.
- **Acceptance criteria:**
  1. The three files collect and pass; the hygiene test passes; ruff is clean.

### Found on 2026-11-16 (the final run and the first-pages review)

#### UPG-295 — The NAAC reminder goes out twice between midnight and 05:30 IST
- **Status:** TODO
- **Last verified:** 2026-11-16, uncommitted on `a4809a8` [R, C]
- **Problem:** Found in the final full run of the ten-gaps change, which reached `tests/test_naac.py` at 05:03 IST: `test_overdue_reports_get_one_reminder_a_day_and_the_iqac_coordinator_can_remind` got two emails where it expects one. `services_naac.daily_reminders` (`services_naac.py:329-341`) takes today's date in IST (`_today`, `:53`) and compares it with the first ten characters of the last reminder's time, which `remind` stores in UTC (`:321`, `_now`, `:48`). From 00:00 to 05:30 IST the two dates differ, so a second run of the job the same day sends again. The test passes after 05:30 (run alone at 05:32: passed). `services_naac.py` and the test were not changed.
- **Who benefits:** event owners with an overdue report (one reminder a day, as promised), and anyone running the suite before 05:30.
- **What to build:** compare the same day on both sides (turn the stored time into an IST date before comparing).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: with the clock at 01:00 IST, two runs of the job send one reminder; the existing test passes, unchanged, at any hour.

#### UPG-296 — Tests with fixed event dates that are about to pass
- **Status:** TODO
- **Last verified:** 2026-11-16, uncommitted on `a4809a8` [C]
- **Problem:** Found in the same run. Since UPG-266 the registration form refuses an event whose last day has passed (before, only the status and the deadline were checked), so a test that registers for an event with a fixed date starts failing the day after that date. One did on 2026-11-16 (`tests/test_ticketing_and_forms.py:440`, dated 2026-11-15; its date is now 30 days ahead, UPG-266's changelog line). Others hold fixed dates from 2026-11-20 to 2026-12-25: `tests/test_seminar_e2e.py:83,321,424`, `tests/test_venues_and_calendar_e2e.py:523,534,679,710,733`, `tests/test_scoped_roles_e2e.py:43,59`, `tests/test_ticketing_and_forms.py:337`, `tests/test_workflow_engine.py:371`, `tests/test_db_adapter.py:366`. Not checked one by one: some never reach the registration form and will keep passing.
- **Who benefits:** everyone running the suite after 2026-11-20.
- **What to build:** for each, see whether it registers through the form (or reads a page that shows the registration state); where it does, make the date relative to today. Change nothing else in those tests.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. The suite passes with the clock set to 2027-01-15 for these files (`services_registration_state.today` patched), with no assertion removed.

#### UPG-301 — A copied hackathon keeps the old event's shortlist, AI run, updates and extensions
- **Status:** TODO
- **Last verified:** 2026-11-16, uncommitted on `a4809a8` [C]
- **Problem:** Found while building UPG-300 (a copied event must start with its leaderboard hidden). `clone_event` (`routes_spoc.py:1440-1483`) drops a short list of run-specific fields and copies the rest. The `hackathon` block goes across whole: the confirmed shortlist (`shortlist`, with its `before` snapshot of the old teams), the AI run's state and call count (`ai_eval`), posted updates, deadline extensions and the submission form's old open and close times; so do `active_round`, `total_rounds`, `shortlist_published` and `scoring_locked`. A copy can open on round 2 with "Finalists announced" naming another event's teams, and with the old event's AI calls counted against its limit. Not run.
- **Who benefits:** SPOCs who copy last year's hackathon.
- **What to build:** a copy keeps the hackathon's set-up (problem statements unreleased, the submission form's fields, criteria, who scores the round, email mode) and drops what belongs to a run (shortlist, AI state, updates, extensions, the form's times, the round fields).
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: copying a hackathon that has a shortlist, AI scores, updates and an extension gives an event on round 1 with none of them, and the same form fields and criteria.
- **Re-verified 2026-11-17 (rule 8, UPG-308 to UPG-313; uncommitted on `25640b5`):** still TODO; `clone_event` is still `routes_spoc.py:1440-1483`. The copied `hackathon` block now also carries UPG-308's kept upload (`marks_upload`), the record of submitted marks (`marks_submitted`) and UPG-309's `finale_open`: the copy should drop all three (and keep the mode `evaluation_mode`).
- **Re-verified 2026-11-18 (rule 8, UPG-316; uncommitted on `88afa47`):** still TODO; `clone_event` is still `routes_spoc.py:1440-1483` and still copies every field but `_STRIP`. That includes the whole `room_plan` (UPG-306): the copy keeps the old event's rooms (fine) but also its `draft`, `final` and `told`, which name the old event's registrations, and the Mixed/Separate choice (`by_size`, UPG-316). The fix should keep the rooms and the choice and drop the rest.

#### UPG-303 — On an individual event every waitlist entry is titled "Individual"
- **Status:** TODO
- **Last verified:** 2026-11-16, uncommitted on `6a132b9` [R over HTTP on a throwaway local database, C]
- **Problem:** Found while building UPG-302. The registration form saves `team_name: 'Individual'` when an event has no teams (`routes_forms.py:450`), and a waitlist entry keeps that in its `reg_data`. The SPOC's waitlist card shows `w.reg.team_name or w.reg.lead_name` (`templates/coordinator/registrations.html`, the `data-waitlist-entry` row), so on an individual event every row is headed "Individual" with "Lead: <name>" under it, the Accept button and dialog say "Accept Individual", and `accept_waitlist` flashes "Individual is accepted and registered" (`routes_coordinator.py`, `who = …team_name…`). A waitlist search for "individual" matches everyone. The form itself already treats `''` and `'Individual'` as no team (`routes_forms.py:916`, `:1221`).
- **Who benefits:** SPOCs of individual events with a waitlist.
- **What to build:** treat `team_name` "Individual" (and empty) as no team on the waitlist card, its Accept dialog and the accept message, so the person's name shows; leave what is stored unchanged.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. Test: on an individual event, a waitlist row, its Accept dialog and the message after accepting name the person, not "Individual"; a team event still shows the team's name.

### Found on 2026-11-17 (building UPG-304)

#### UPG-305 — Participants who only use the phone app are never asked the website feedback round
- **Status:** TODO
- **Last verified:** 2026-11-17, uncommitted on `4a2c16b` [C]
- **Problem:** Found while building UPG-304. The website feedback gate (`app.py:1429-1452`) works on the web session (`session['user_id']`, role `Student`). The phone app (`saptha_app/lib/services/api_service.dart:25`) signs in through `/api/auth/login` and then with a Firebase custom token, and keeps no Flask session, so the gate never runs for it and the app has no screen for the form. A participant who uses only the app is never asked, and the Super Admin's "X of Y people have answered" counts them as not answered. Not run on a phone.
- **Who benefits:** the Super Admin (feedback from everyone, not only web users); participants on the app.
- **What to build:** decide first (owner): either the app opens the form (a web view of `/website-feedback` after a sign-in that gives it a session, or a native screen backed by two API calls: the round due and send the answers), or the round page says plainly that app-only users aren't asked.
- **Depends on:** UPG-304 (DONE).
- **Acceptance criteria:**
  1. A participant signed in only on the app, while a round is on and they haven't answered, is shown the form (or the owner's chosen alternative), and can still open their ticket.
  2. Their answer counts once and is anonymous as on the web.

#### UPG-307 — The coordinator's room-and-judge allocation and AI judge matching skip the room draft
- **Status:** TODO
- **Last verified:** 2026-11-17, `fb20296` [C]
- **Problem:** Found while planning UPG-306 (the owner kept these out of it). `/coordinator/allocate_rooms` (`routes_coordinator.py:1202-1235` after UPG-317; `:1164-1198` before) shuffles teams into rooms with a judge each, and AI judge matching (`routes_ai_matching.py:363-392`) labels each judge's teams with a room; both write `assigned_room` straight onto registrations, so teams see it at once, with none of UPG-306's draft, final check or choice of email and website, and a later UPG-306 "Allocate final" overwrites them. Not run.
- **Who benefits:** SPOCs and coordinators running judged rooms.
- **What to build:** decide first (owner): either both write into UPG-306's draft (judges carried with the room) and go out through "Allocate final", or they stay as they are and the allocation page says so.
- **Depends on:** UPG-306 (DONE).
- **Acceptance criteria:**
  1. Test: after the coordinator's allocation, participants see no room until the SPOC's Allocate final (or the owner's chosen alternative).

#### UPG-311 — The coordinator's event edit turns the judges' criteria into names, each out of 100
- **Status:** TODO
- **Last verified:** 2026-11-17, `25640b5` [C]
- **Problem:** Found while planning UPG-309. `edit_event` in `routes_coordinator.py:1108-1120` (after UPG-317; `:1070-1082` before) saves `judging_criteria` as names split on commas, so criteria like Innovation /40, Tech /30, Demo /30 become three criteria each out of 100 once a coordinator saves the event's details. Not run.
- **Who benefits:** SPOCs and judges.
- **What to build:** keep each criterion's marks when the coordinator saves the event (or leave the criteria alone when the form doesn't change them).
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: a coordinator saving the event's details keeps each criterion's marks.

#### UPG-314 — A dashboard test fails when a random ID contains "645"
- **Status:** TODO
- **Last verified:** 2026-11-17, uncommitted on `25640b5` [R]
- **Problem:** Found in the full run for UPG-308 to UPG-313. `tests/test_analytics_and_leaderboards.py::test_dashboards_count_registrations_not_the_cached_counter` sets a cached counter of 645 (`:159`) and then checks that "645" isn't in the first 400 characters of the SPOC page's chart data (`:221`). That data also holds the event's random UUID, so the test fails whenever the UUID contains "645" (seen once; it passed three times on a re-run).
- **Who benefits:** whoever runs the tests.
- **What to build:** check the parsed chart data's registration count instead of searching the text.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: the check reads the registered count from the parsed chart data; it fails on the old code only if the counter is used.

### Found on 2026-11-19 (building UPG-321)

#### UPG-322 — The hackathon browser test fails now and then when the machine is busy
- **Status:** TODO
- **Last verified:** 2026-11-19, `fb34d9c` [T]
- **Problem:** Found in UPG-321's full run (four test runs at once). `tests/test_hackathon_browser.py:90` clicks "Extend deadline" on the SPOC's page and times out after 30 s: Playwright keeps finding the button "not stable" while scrolling to it. Alone it passes every time; with three other test runs going it failed 1 in 3 on `fb34d9c` itself (before UPG-321), and 1 in 4 with UPG-321. Nothing is wrong on the page; the test depends on the machine's speed.
- **Who benefits:** whoever runs the full test suite (a failure that isn't a bug hides real ones).
- **What to build:** make the click independent of speed without weakening what it checks, e.g. scroll the form into view and wait for it to settle before clicking, or submit the extend form directly, still checking the new deadline and the reason on both pages.
- **Depends on:** none.
- **Acceptance criteria:**
  1. The test passes 10 times in a row with three other test runs going at once.
  2. It still checks the new deadline and "Lab power cut" on the SPOC's and the team's pages.

#### UPG-327 — Two conference/workshop acceptance tests fail on a ticket's foreign key
- **Status:** TODO
- **Last verified:** 2026-11-19, `92d0eea` [T]
- **Problem:** Found in UPG-326's full run. `TestConferenceUniversalFlow::test_full_conference_lifecycle` (`tests/test_universal_acceptance.py:159`, `TicketService.issue_ticket`) and `TestWorkshopUniversalFlow::test_full_workshop_lifecycle` fail with `sqlite3.IntegrityError: FOREIGN KEY constraint failed` on the INSERT into `tickets`: the ticket's `registrationId` doesn't match a stored registration (the ticket's data says `reg-…`). They fail the same way on `92d0eea` with UPG-326 set aside, alone or in the full run, and passed in UPG-325's full run earlier the same day, so something outside the code (the date, or test data) changed.
- **Who benefits:** whoever runs the full test suite; and conference/workshop ticketing, if the cause is in `TicketService` rather than the test.
- **What to build:** find why the registration id doesn't match (test data or the service's id mapping) and fix that cause, keeping what the tests check.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Both lifecycle tests pass, alone and in the full run.
  2. If the cause is in the app, a test shows a ticket issued for a stored registration saves.
- **Seen again 2026-11-19 (UPG-328's full run, on `cf7305a`):** both passed, so they fail only some of the time (order, timing or test data), not on every run.
- **Seen again 2026-11-20 (UPG-330/331's full run, on `e108d68`):** both passed.

#### UPG-329 — The portal's other Gemini features still ask for gemini-2.5-flash
- **Status:** TODO
- **Last verified:** 2026-11-19, uncommitted on `cf7305a` [C]
- **Problem:** Found in UPG-328. The owner's new Gemini key (a new project, 2026-11-19) gets 404 "models/gemini-2.5-flash is no longer available to new users" for `gemini-2.5-flash`. UPG-328 moved hackathon scoring to `gemini-3.8-flash`, but 16 other calls hard-code `gemini-2.5-flash`, so with the new key they fail: `chatbot_routes.py:177`; `routes_ai_features.py:70`, `:126`; `routes_ai_matching.py:268`, `:654`, `:812`; `routes_forms.py:1548`; `routes_judge.py:508`; `routes_matchmaker.py:206`; `routes_participant.py:509`; `routes_spoc.py:1317`, `:2420`, `:2553`, `:2610`; `services_copilot.py:85`, `:92` (the model name it stores); and `docs/AI.md:33`. Some may also send `thinking_budget=0` or a low output limit that suits only 2.5.
- **Who benefits:** everyone using the portal's other AI features (chatbot, matching, form and SPOC helpers, the copilot) once the new key is live.
- **What to build:** one place that names the Gemini model (the `GEMINI_MODEL` setting from UPG-328, default `gemini-3.8-flash`) used by every call, with each call's settings checked for Gemini 3; `docs/AI.md` updated.
- **Depends on:** UPG-328.
- **Acceptance criteria:**
  1. A test: no code outside the shared setting names a Gemini model; each feature's call uses the shared model.
  2. A test: with `GEMINI_MODEL` set, a sample of the features (chatbot, SPOC, copilot) call that model.

#### UPG-332 — The NAAC overdue-reminder test sends two reminders in the early IST morning
- **Status:** TODO
- **Last verified:** 2026-11-20, `e108d68` [T]
- **Problem:** Found in UPG-330/331's full run. `tests/test_naac.py::test_overdue_reports_get_one_reminder_a_day_and_the_iqac_coordinator_can_remind` (`:178`) counts two "NAAC report due" emails for one overdue report where it expects one. It fails the same way on `e108d68` without UPG-330/331 (alone, 2026-11-20 04:35 IST = 2026-11-19 23:05 UTC) and passed in the 2026-11-19 full runs, so "one a day" likely mixes the IST and UTC dates when they differ.
- **Who benefits:** IQAC coordinators (one reminder a day, whatever the hour), whoever runs the suite.
- **What to build:** find which "today" the reminder and the test use, and use the same day for both (the app's, if the app is the one mixing them).
- **Depends on:** none.
- **Acceptance criteria:**
  1. The test passes at any hour, shown with the clock set between 00:00 and 05:30 IST.
  2. If the app sends two reminders in that window, a test shows it sends one.

#### UPG-333 — The seminar lifecycle test finds no registration in the early IST morning
- **Status:** TODO
- **Last verified:** 2026-11-20, `e108d68` [T]
- **Problem:** Found in UPG-330/331's full run. `tests/test_seminar_e2e.py::test_seminar_full_lifecycle_and_certificate_guards` (`:178`, `assert len(alice_regs) == 1`) finds no registration for Alice. It fails the same way on `e108d68` without UPG-330/331 (2026-11-20 04:35 IST) and passed in the 2026-11-19 full runs; likely a date the test or the registration check takes in one timezone and compares in the other.
- **Who benefits:** whoever runs the suite; seminar registrants, if the app refuses a registration in that window.
- **What to build:** find why the registration isn't there (refused, or filtered out) and fix that cause, keeping what the test checks.
- **Depends on:** none.
- **Acceptance criteria:**
  1. The test passes at any hour, shown with the clock set between 00:00 and 05:30 IST.
  2. If the app refuses or hides the registration in that window, a test shows it no longer does.

### Found on 2026-11-20 (building UPG-339)

#### UPG-340 — A team member opening the built-in certificate page sees the lead's name
- **Status:** TODO
- **Last verified:** 2026-11-20, on `f36219a` plus UPG-339 [C]
- **Problem:** `view_certificate` (`routes_participant.py:360`) lets the lead or any member open `/participant/certificate/<reg_id>` but renders `student_name=reg_data.get('lead_name')` (`:407`), and checks only the registration's attendance, not the member's. A member sees the lead's name on the built-in certificate. Events with their own design show the issued certificate instead (UPG-339) and are not affected.
- **Who benefits:** team members at events that use the built-in certificate.
- **What to build:** the page shows the viewer's own name, and checks the viewer's own attendance (member's, else the registration's).
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: a member who attended opens the page and sees their own name, not the lead's.
  2. Test: a member marked absent is refused, while the lead who attended still sees theirs.

### Found on 2026-11-21 (building UPG-359)

#### UPG-360 — A team corrected back to a place it once had gets no certificate for it
- **Status:** TODO
- **Last verified:** 2026-11-21, on `57778db` plus this change [C]
- **Problem:** Publishing corrected results (UPG-359) revokes the old places' position certificates. A revoked certificate stays the person's current one for its type (the unique current-certificate index; `services_certificates.claim` returns None, `services_certificates.py:350-375`; `services_certificate_changes.revoke`, `:146-162`). If a later correction gives the team its old place back (winner → runner-up → winner), the winner's certificate can't be issued again, and no page restores a revoked certificate.
- **Who benefits:** the SPOC correcting a result twice, and the team.
- **What to build:** when a place is owed again and the person's current certificate of that type is revoked, issue a new version (or restore it with a note), and a "Restore" button for a revoked certificate on the certificates page (the SPOC or Super Admin).
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: published, corrected, corrected back: the team's winner certificate is valid again.
  2. Test: the SPOC restores a revoked certificate from the page; a student can't.

#### UPG-361 — The NAAC daily reminder can go twice between midnight and 05:30 IST
- **Status:** TODO
- **Last verified:** 2026-11-21, on `57778db` [R]
- **Problem:** `services_naac.daily_reminders` skips a report already reminded "today" by comparing `_today()` (the IST date, `services_naac.py:52-53`) with the first ten characters of the last reminder's `at`, which `remind` writes in UTC (`:321`, `_now()` at `:48-49`). Between 00:00 and 05:30 IST the two dates differ, so a second run in that window sends another reminder the same IST day. Found when `tests/test_naac.py::test_overdue_reports_get_one_reminder_a_day_and_the_iqac_coordinator_can_remind` failed in the full run that crossed 05:30 IST on 2026-11-21 (it passes alone and with its file).
- **Who benefits:** report owners (no double reminders) and the test suite (no failure by time of day).
- **What to build:** compare IST dates on both sides (convert the stored `at` to IST before taking its date).
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: with the clock set to 00:30 IST, a reminder sent at 00:10 IST the same day stops a second one; one sent at 23:50 IST the day before doesn't.

### Easy to use everywhere (owner, 2026-11-21)

The owner asked to "make the full portal user friendly" and chose: walk every role's main pages on a phone and a computer, write each problem down, fix them starting with those most people meet. Walked on 2026-11-21 in Chromium at 390 px and 1280 px as a visitor, student, SPOC, coordinator, judge and Super Admin (about 20 pages each width, with a measuring script: page width, tap-target size, text size, unlabelled fields, codes and raw dates). UPG-373 (a What's new page with versions, the owner's request the same day) came first. Order agreed: UPG-362, UPG-363, UPG-364, UPG-365, UPG-366, UPG-367, UPG-368, UPG-297 (a)–(g), UPG-369, UPG-370, UPG-371, UPG-372.

#### UPG-369 — The admin's lists are wider than a phone
- **Status:** TODO
- **Last verified:** 2026-11-21, on `47abcc9` [R in Chromium, 390 px and 1280 px]
- **Problem:** "All events" is 815 px wide on a 390 px screen: the event name, kind, date and "Visitors see" are squeezed into one narrow column, one word a line, and status and registrations are off the screen.
- **Who benefits:** the Super Admin on a phone.
- **What to build:** on a phone each row becomes a card (name, status, registrations, date); the same for the admin's users list.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: on a 390 px screen the admin's events and users pages are no wider than the screen (browser test).

#### UPG-370 — The admin dashboard's numbers fill a whole phone screen
- **Status:** TODO
- **Last verified:** 2026-11-21, on `47abcc9` [R in Chromium, 390 px and 1280 px]
- **Problem:** The six number cards (events, registrations, revenue, staff, SPOCs, students) are one per row on a phone, about 1,100 px before anything else.
- **Who benefits:** the Super Admin on a phone.
- **What to build:** two cards a row on a phone, each shorter (icon beside the number).
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: on a 390 px screen the six cards take at most three rows (browser test).

#### UPG-371 — The coordinator's event cards start with a large empty banner
- **Status:** TODO
- **Last verified:** 2026-11-21, on `47abcc9` [R in Chromium, 390 px and 1280 px]
- **Problem:** With no event image, each card on the coordinator's dashboard begins with a 130 px dark block holding only an icon.
- **Who benefits:** coordinators on a phone.
- **What to build:** without an image, a thin coloured band with the category instead of the block.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: an event without an image has no banner block on the coordinator's dashboard.

#### UPG-372 — The tournament page's fields have no labels
- **Status:** TODO
- **Last verified:** 2026-11-21, on `47abcc9` [R in Chromium, 390 px and 1280 px]
- **Problem:** The score, winner, date, time, venue and home/away fields on the SPOC's tournament page have no label a screen reader can read (`templates/spoc/tournament.html`, the match forms).
- **Who benefits:** staff using a screen reader, and anyone unsure what a box is for.
- **What to build:** a label (visible or `aria-label`) on each field, naming the team or the field.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: every input and select on the tournament page has a label.

#### UPG-374 — The SPOC's console on a phone opens with no heading
- **Status:** TODO
- **Last verified:** 2026-11-21, on `7146f32` [R in Chromium, 390 px]
- **Problem:** On a phone `/spoc/dashboard` opens on the search box, the filter pills and the event list. The page's only heading ("…'s console", `templates/spoc/dashboard.html:1257`) is in the overview column, which is hidden on a phone until an event or Global Overview is picked (`:770-776`). The SPOC sees no title saying where they are, and a screen reader finds no heading. Found building UPG-363.
- **Who benefits:** SPOCs on a phone; screen-reader users.
- **What to build:** a heading at the top of the list column on a phone (the console's name and "Create event"), with the overview's own heading kept for the computer.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: on a 390 px screen the first thing under the header is a visible heading (browser test).

#### UPG-375 — The coordinator's page hides a running two-day event on its second day
- **Status:** TODO
- **Last verified:** 2026-11-21, on `bd9397b` [C]
- **Problem:** Found building UPG-297 (f). `routes_coordinator.py:96-101` leaves out an event when `date` is before `datetime.date.today()`. That is the event's first day, not its last (`end_date`), and the server's date (UTC on Cloud Run), not India's. On day 2 of a two-day hackathon its coordinators lose it from their page while it is running; between 00:00 and 05:30 IST yesterday's event is still shown.
- **Who benefits:** event coordinators of events longer than a day.
- **What to build:** hide an event only once its last day (`end_date`, else `date`) is before today in India; the same rule the public pages use for "Event over".
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. A two-day event whose first day was yesterday is on the coordinator's page; one that ended yesterday is not.
  2. The figures count the same events the page shows.

#### UPG-376 — `ruff check .` fails on the problem-selection tests
- **Status:** TODO
- **Last verified:** 2026-11-21, on `bd9397b` [C, `ruff check .`]
- **Problem:** Found building UPG-297, running the full-repo lint the owner's gap-closure plan (`docs/GAP_CLOSURE_PLAN.md`) asks for before finishing an item. `tests/test_hackathon_problem_selection.py` (UPG-321) has an unused `datetime` import (line 12) and 10 F811 errors: the `hack` fixture is imported at line 16 and also taken as each test's argument. The checks so far ran ruff only on the changed files, so this passed.
- **Who benefits:** whoever builds the next item: `ruff check .` passes, so a new lint error shows.
- **What to build:** import the fixture the way the other tests do (`from … import hack  # noqa: F401`, or a `conftest`), drop the unused import. No test's behaviour changes.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. `ruff check .` reports nothing for the repository's committed files, and the 11 problem-selection tests still pass.

#### UPG-379 — The SPOC's scanner lets a cancelled team in and records no day
- **Status:** TODO
- **Last verified:** 2026-11-21, uncommitted on `2a065c3` [C]
- **Problem:** Found building UPG-378. The SPOC's check-in during the event (`routes_spoc.py:822-878`, `/spoc/api/checkin`) checks only that the ticket is for the event. It doesn't refuse a cancelled or refunded registration, nor one the entry list leaves out (`services_entry.inactive`, `may_enter`), which the shared ticket check-in does (UPG-215 covers the other paths). It also writes no `attendance_days` (the shared path does, `routes_ticket.py:262-284`), so on a multi-day event that isn't a hackathon someone the SPOC scanned on both days counts as 1 day and can miss the participation certificate's 80% rule (`services_certificates.py:121`). The after-the-event mark (UPG-378) already does both.
- **Who benefits:** SPOCs and the people they check in; the certificate counts every day.
- **What to build:** the same refusals as the shared check-in, and add today (India) to `attendance_days` on each check-in.
- **Effort:** S · **Depends on:** none · **Risk:** low.
- **Acceptance criteria:**
  1. A cancelled registration and one off the entry list are refused at the SPOC's scanner.
  2. A person scanned on both days of a two-day seminar has both days and gets the participation certificate.

### Sports and cultural events up to the hackathon's level (owner, 2026-11-20; Kabaddi first)

The owner asked for every kind of event to work as well as SAPTHAHACKS'26 did, starting with a Kabaddi tournament run like a professional kabaddi league. Order agreed ("go"): UPG-342, UPG-350, UPG-351, UPG-352, UPG-344, UPG-345, UPG-343, then UPG-346 to UPG-349. UPG-342, UPG-350, UPG-351 and UPG-352 are done (archived).

#### UPG-344 — A team's own tournament page
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** A sports team has only the public fixtures page; nothing tells the team its own next match.
- **What to build:** `/tournament/<event_id>/team` for the lead and members: next match (opponent, date, time, court, live link), all its matches and results, its place in the table, its players' stats, its place and certificate once results are out; a "Tournament" button on the student dashboard's ticket for a sports event.
- **Depends on:** UPG-342, UPG-350.
- **Acceptance criteria:**
  1. Test: a member sees their team's next match and results; another team's player sees their own; a stranger is refused.
  2. Test: the dashboard's ticket for a tournament links the page.

#### UPG-345 — Teams are told about fixtures, changes and results
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** `routes_sports.py` generate, schedule and result notify nobody.
- **What to build:** an in-portal notification and a browser push to the teams concerned: fixtures out (all teams), a match scheduled or moved (both teams), a result (both teams), playoffs made (the qualified teams). No email (the daily email limit).
- **Depends on:** UPG-344.
- **Acceptance criteria:**
  1. Test: each of the four sends to exactly the teams concerned, once.

#### UPG-343 — "One check-in counts" for any multi-day event
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** UPG-338 made one check-in count on a hackathon only. A two-day tournament or fest still needs 80% of its days (`DEFAULT_MIN_ATTENDANCE`) for a participation certificate; `cert_min_attendance_pct` has no setting on any page.
- **What to build:** on the Certificates page, for a multi-day event: "Days needed: any one day / half the days / 80% (default) / every day", saved as `cert_min_attendance_pct`; a hackathon defaults to any one day.
- **Depends on:** none.
- **Acceptance criteria:**
  1. Test: each choice changes who is owed on a two-day tournament; only the SPOC may change it.

#### UPG-346 — Athletics results
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** The athletics type lists its disciplines but has no heats, finals or results.
- **What to build:** per discipline: heats and a final, each athlete's time or distance, the top 3 per discipline, and position certificates per discipline.
- **Depends on:** UPG-342.
- **Acceptance criteria:** to be written when it is started.

#### UPG-347 — Cultural stage order
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** No running order for a cultural competition.
- **What to build:** slots in performance order (set or drawn), report time, time on stage, and a "Now on stage / next up" screen.
- **Depends on:** none.
- **Acceptance criteria:** to be written when it is started.

#### UPG-348 — A cultural performer's own page
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** Performers have no page like the hackathon page.
- **What to build:** slot, report time, status, place and certificate, from the dashboard.
- **Depends on:** UPG-347.
- **Acceptance criteria:** to be written when it is started.

#### UPG-349 — Start-to-finish tests for sports, athletics and cultural events
- **Status:** TODO
- **Last verified:** 2026-11-20, on `98b036b` [C]
- **Problem:** Only the hackathon and the seminar have full-journey tests.
- **What to build:** one test per type from creation to certificates.
- **Depends on:** UPG-342 to UPG-348.
- **Acceptance criteria:** to be written when it is started.

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
| D-14 | **UPG-255, the paid mail plan.** Which plan (Brevo Starter assumed), and which domain to send from (a verified domain sender, not a `@gmail.com` address)? | UPG-255's switch-over and UPG-258; not the code | Open (2026-11-14). UPG-255's code is built (DONE); the switch-over steps are in `docs/DEPLOY.md`, "A paid mail plan". |
| D-15 | **Questions for a person with legal authority** (listed in `docs/DATA_HANDLING.md`, "Questions for human review"): how long each kind of record is kept (the notice says 5 years; no code enforces it); the notice's references to the IT Act and the DPDP Act and who the grievance contact is; whether a certificate may stay verifiable after its holder's account is deleted; a minimum age; where the data is stored; the payment provider's lines and the refund terms (not edited); which AI features may send what to Gemini; how long audit entries and their IP addresses are kept. | UPG-286, UPG-288 (a), UPG-291; the wording of `/privacy` and `/terms` | Open (2026-11-15). Nothing in the repository is a legal opinion, a certification or an audit, and the documents now say so. |
| D-16 | **Is the live Cloud Run service a demo or the university's own deployment, and what happens to `/pricing`?** `DEMO_ENVIRONMENT=1` puts a "Demo" banner on every page (UPG-275); it is unset today, so the live service presents itself as the institution's own. `/pricing` (hidden behind `DEMO_PAGES_ENABLED`) still states invented prices, a platform fee and Stripe. | UPG-287; one environment variable on the next deploy | Open (2026-11-15). Proposed: leave the live service unmarked if it holds real registrations, and delete `/pricing`. |
| D-17 | **UPG-280: what makes someone "from this institution"?** The campus email domain, the roster, or both; and what a real student with a personal address does. | UPG-280 | Open (2026-11-15). |

*Decided decisions: `docs/archive/FEATURE_REVIEW_DONE.md` ("Decisions needed").*

## Changelog (last 20)

| Date | Commit | Item ID | What changed |
|---|---|---|---|
| 2026-11-20 | (uncommitted, on `745c447`) | UPG-334 | **The phone's "Results" tab gave 404 (owner, 2026-11-20: "check the submission 404 error").** The owner deployed `745c447` (UPG-330, UPG-331) as `saptha-c745`: two plain deploys printed "revision saptha-00042-lat has been deployed" and created nothing, so it went out with `--revision-suffix=c745`. The live request log for 12 hours had no 404 on a submission; all ~30 were `GET /live/streams`, the phone bar's "Results" tab, a demo page off in production (UPG-65). The tab is now "Certificates" and opens My certificates, as the owner chose. `tests/test_mobile_and_offline.py` checks for "Certificates" where it checked "Results" (the tab's new name). Tests: `tests/test_mobile_nav_links.py` (2). |
| 2026-11-20 | (uncommitted, on `a7552c9`) | UPG-335 | **SAPTHAHACKS'26 showed under "Past events" while it was still running (owner, 2026-11-20, with a screenshot: "event still is running … some are getting like lead and all").** The event runs 19 → 20 Nov; the dashboard counted an event past once its *start* date had gone, in the server's UTC date (a day behind India until 05:30 IST), so on 20 Nov it moved to Past events with 0 active tickets, and students who opened it before 05:30 IST still saw it active. Now an event stays active until its last day (`end_date` / `end_datetime`, else its date) has passed in India's date, or while its status is in progress, with a "Happening now" chip; a past hackathon card shows the lead the Hackathon page button (only the lead opens it, UPG-196, so members see no such button: by design). Tests: `tests/test_participant_dashboard_running.py` (6). |
| 2026-11-20 | (uncommitted, on `fd64791`) | UPG-336 | **Scores stay hidden from teams; the SPOC edits the judges' marks (owner, 2026-11-20: "judges have scored all the teams but we need to edit the score in the SPOC portal only, not displayed to anyone until round 2 is complete … no need to show the score to any team, just provide the place").** The student dashboard showed a team "Your score /100" with a breakdown of every judge's marks the moment a judge scored, during the finale: removed (the box, the breakdown window and its script); after the results a team sees its place ("Your place: 1st", or "Rank #1" on a past card). The hackathon page's result shows the place without a score; the lead's result email and the winners' WhatsApp (for a hackathon) no longer give the score. On the SPOC's hackathon page, the judges' column of the ranking lists each judge's mark (out of the criteria total) with a box to change it until the results are published; the change keeps the judge's own criteria marks, records who changed it and from what ("edited (was 70)"), and the team's average, rank, shortlist and results use it. Only the event's organiser (edit permission) can change a mark; judges and teams get 403. The public leaderboard is unchanged: it shows scores, so it stays hidden unless the SPOC switches it on (UPG-300). Tests: `tests/test_hackathon_score_privacy.py` (5). `tests/test_ux_first_pages.py` checked the dashboard's order ending on the score-breakdown window, which is gone: it now ends on the Event attendance box and checks the window isn't there. Deployed 2026-11-20 as `saptha-e113` (with UPG-334, UPG-335). Full run: every other failure is a known open item (UPG-289's two pagination tests, UPG-333 seminar, UPG-322 hackathon browser, passed on its rerun) or the scratch-copy type check. |
| 2026-11-20 | (uncommitted, on `451fef8`) | UPG-337 | **The judges' marks can be changed on the Round panel (owner, 2026-11-20, screenshot of "Round 2 of 2 · Final" standings: the edit wasn't there; "only SPOC we need it").** UPG-336 put the edit boxes on the hackathon page's ranking; the owner runs round 2 from the Round panel, so its standings now list each judge's mark under the Avg Score with a box and Save (the same route, which returns to the Round panel), "edited (was N)" after a change, read-only once results are out. Only the event's SPOC opens the panel and only someone who can edit the event saves a mark. Tests: `tests/test_hackathon_score_privacy.py` (+1). |
| 2026-11-20 | (uncommitted, on `f36219a`) | UPG-338 | **Everyone checked in at a two-day hackathon is owed the participation certificate (owner, 2026-11-20, screenshot of SAPTHAHACKS'26 certificates: "37 certificates owed, 0 issued", "Participation certificates only (0)"; "all attended need to get, fix this").** "Checked in" asked a two-day event for 80% of its days, so a scan on both days; a hackathon is scanned once. On a hackathon one check-in now counts; a member marked absent at the scanner still gets none; other multi-day events keep the 80% rule (`services_certificates.py:116-120`). New `tests/test_certificate_hackathon_attendance.py` (3). |
| 2026-11-20 | (uncommitted, on `f36219a`) | UPG-339; new UPG-340 | **The student's Certificate button shows the SPOC's own design (owner, 2026-11-20, phone screenshot of the built-in "Certificate of Participation" for SAPTHAHACKS'26: "the participation template added by the SPOC needs to go to all, not this").** On an event with its own design, `/participant/certificate/<reg>` shows the certificate issued to that person (image, PDF, image download, verification link), and before it's issued says so; events without their own design keep the built-in page (`routes_participant.py:398-409`, `templates/participant/certificate.html:167-215`). New `tests/test_certificate_own_design_view.py` (2). Two line references in `routes_participant.py` that moved by 9 were corrected (UPG-228, UPG-329). Full pytest with UPG-338 and UPG-339: 4 failed, 1,886 passed, 8 skipped, all failures logged before (UPG-289 ×2, UPG-333, and `test_type_check_config`, which fails only in the scratch copy). Found: UPG-340 (a member sees the lead's name on the built-in page). |
| 2026-11-20 | (uncommitted, on `51ea502`) | UPG-341 | **The participation certificate by hand, for the winners (owner, 2026-11-20, screenshot after issuing 560 participation certificates: "they also need to get … add a drop down to them separately to send the participation in that only").** The Award row's Certificate list has "Participation (your design)": pick a registered person, Award, and they get it on the SPOC's design, once; nobody else is touched (`services_certificates.py:242-272`, `routes_certificates.py:90-91`, `templates/certificates/manage.html:96`). New `tests/test_certificate_award_participation.py` (2). Three references that moved were corrected (UPG-330, UPG-331). Full pytest: 4 failed, 1,888 passed, 8 skipped, all logged before (UPG-289 ×2, UPG-333, and `test_type_check_config`, which fails only in the scratch copy). |
| 2026-11-20 | (uncommitted, on `98b036b`) | UPG-342, UPG-350, UPG-351, UPG-352; new UPG-353, UPG-354 | **A Kabaddi tournament run like a professional kabaddi league (owner, 2026-11-20: "we are having a kabaddi sports event, like how the PKL and other leagues are happening … test it manually").** UPG-342: a tournament's places become the event's result: "Publish results" on the tournament page (and the SPOC's or coordinator's Publish) writes 1st/2nd from the final and 3rd from the third-place match or both losing semi-finalists (a league's top three), completes the event, emails the placed leads their place (no score), pushes, and owes position certificates by place. UPG-350: kabaddi points 5/3/1 (loss by 7 or fewer)/0 with score difference, chosen by itself on a Kabaddi event; "League then knockout" with "Make the playoffs" (top 4 or top 2, optional third-place match); stage names (Semi-final 1, Final, Third place). UPG-351: "Score live" on each match opens a phone scorer (raid 1–7, bonus, tackle, super tackle, all out, technical point, by player; undo; halves and a pausable clock; full time saves the result and moves the winner on, a knockout tie asks who went through); each match keeps its own record, a repeated tap counts once; anyone opens the match's scoreboard, which refreshes itself every 3 s, and the fixtures show LIVE. UPG-352: top raiders and defenders with Super 10s and High 5s on the public fixtures, and who scored on each scoreboard. No migration (the live records are native documents). 11 new tests (`tests/test_tournament_results.py` 3, `tests/test_tournament_kabaddi.py` 3, `tests/test_live_match.py` 3, `tests/test_live_match_stats.py` 2); no existing test changed. Checked by hand in Chromium at phone width on a throwaway database, from making the league to publishing; fixed there: the LIVE mark and the raid/tackle table were missing on a board opened before kick-off, and two tables were wider than a phone. Rule 8: 26 line references in open items moved by the new lines were corrected. Full pytest: 4 failed, 1,899 passed, 8 skipped, all logged before (UPG-289 ×2, UPG-333 seminar, and `test_type_check_config`, which fails only in the scratch copy; 2 passed in the repo). Found: UPG-353 (scores unreadable on the staff page), UPG-354 (two results at the same moment). |
| 2026-11-21 | (uncommitted, on `57778db`) | UPG-353, UPG-354, UPG-355, UPG-356, UPG-357, UPG-358, UPG-359; new UPG-360 | **Nothing in a tournament needs code to fix (owner, 2026-11-21: "i dont want any gap so the any problem happened spoc or super admin can fix it not alwayes required to code").** UPG-353: the staff page's scores are dark badges. UPG-354: every change to a tournament (a result, full time, a schedule, the playoffs, every fix below) reads it afresh under a lock that every copy of the app shares, so two courts finishing together both keep their result. UPG-355: Clear the result on any match (a knockout's winner comes back out of the next match; a correction past a played match says which match to clear first); Reopen the match on the scorer after full time; remove any point from the live log. UPG-356: Give walkover; Withdraw a team (its matches still to play become walkovers, later knockout rounds too) and Bring back; a walkover scores win points and 0, no score, W/O on the pages. UPG-357: a Teams card: rename, replace with another confirmed team (results and live records move), add a late team to a league; Fix this match sets a match's teams (a playoff seeding by toss), refused while scored live or if the team already plays in that round. UPG-358: change the points rule before the playoffs; Undo the playoffs while none is played; making the fixtures again forgets old live records. UPG-359: when the fixtures no longer match the published places the page says so; Publish the corrected results tells only the teams whose place changed and revokes the old places' certificates. Every fix is logged in the audit log; the Super Admin can use all of them. A help card on the page lists what to do for each mistake. No migration (the lock is a row in the existing counter table). 13 new tests (`tests/test_tournament_fixes.py`); no existing test changed. Checked by hand in Chromium at phone width: a match ended too early reopened, a wrong point removed, a result cleared; fixed there: the Teams table was wider than a phone (now one block per team). Rule 8: no open item cites the changed lines. Full pytest: 5 failed, 1,911 passed, 8 skipped: four logged before (UPG-289 ×2, UPG-333 seminar, `test_type_check_config` in the scratch copy only) and one new, UPG-361 (the NAAC reminder test run across 05:30 IST; passes alone and in its file). Found: UPG-360 (a place given back gets no certificate), UPG-361 (the NAAC daily reminder can go twice between midnight and 05:30 IST). |
| 2026-11-21 | (uncommitted, on `47abcc9`) | UPG-373; new UPG-362, UPG-363, UPG-364, UPG-365, UPG-366, UPG-367, UPG-368, UPG-369, UPG-370, UPG-371, UPG-372 | **The portal's versions (owner, 2026-11-21: "i also need version calculate previous also and in future it need to go").** `config/releases.json` holds every version, newest first: v1.0 (`dfce764`, 20 Oct 2026, the first live deploy) to v1.15 (`51ea502`), worked out from the deploy history, and v1.16 for this code (UPG-341, 342, 350–359, 373). `/whats-new` lists them with the date, a title and what changed in plain words, the top one marked "You're using this version"; every page's footer links it as "What's new · v1.16". `docs/DEPLOY.md` Release check step 10: write the Cloud Run revision into the top entry after a deploy; the next finished item starts a new version. 4 new tests (`tests/test_releases.py`), one of which fails if a finished item in this changelog is left out of every version. **The usability walk (owner, "make the full portal user friendly"):** every role's main pages on a 390 px phone and a 1280 px computer, measured for sideways scroll, small taps, tiny text, unlabelled fields and codes or ISO dates on screen; 11 new items, UPG-362 to UPG-372, to build in the agreed order with UPG-297 (a)–(g). Full pytest: 5 failed, 1,915 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). The NAAC test (UPG-361) passed this time. Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-362 | **The coordinator's cards said "Closed" for events yet to start (usability walk).** The badge is now `organiser_status`, the words the SPOC's console uses (Opens soon, Registration open, Registration closed, Event over, Draft…), so an event five days away says "Opens soon"; "Export final data" and the disabled "Event concluded" show only once the event is over, and an upcoming event's card keeps View students, Excel and form responses. The red one-confirm "Delete event" link is gone from the coordinator's card (the SPOC deletes from the event's own page; the route stays for the admin dashboard). The old "Live (Round N)" badge gave way to the registration state; the round still shows in Next round / eliminate. 2 new tests (`tests/test_coordinator_card_status.py`). v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-363; new UPG-374 | **The welcome message covered the title on a phone (usability walk).** Every flash message becomes a toast (`global.js`), pinned top right under the header; on a 390 px screen it lay across the page's heading. On a phone (under 768 px) the toast now sits at the bottom, full width, 12 px above the 64 px bottom menu, and still goes after 6 seconds; on a computer nothing changed. 2 new browser tests (`tests/test_welcome_toast.py`: student and SPOC, phone and computer). New UPG-374: the SPOC's console has no heading on a phone. v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-364 | **Controls too small for a finger (usability walk).** Under 768 px: the header's icon buttons go from 28×38 to 44×44 px, and the logo and the profile button ("AR", 45×32) to 44 px tall; the bottom menu's words from 10.9 to 12 px; the home page's category chips from 25 to 44 px tall with 13 px words; on the sign-in page the eye is 44×44, "Keep me signed in" (box and words, 18×18 before) and the links "Forgot password?" and "Create an account" (16 px tall) are 44 px tall. Under 480 px, where the bottom menu shows, the header's search button is left out (the bottom menu does the finding) and the logo (24 px) and profile button take less room, so the SPOC's header (search, notifications, theme, Create event, profile, log out) fits 375 px without cutting off the profile. Nothing scrolls sideways at 375 or 390 px. 1 new browser test (`tests/test_tap_targets.py`: sign-in, home, the student's and the SPOC's pages). v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-365 | **Dates as 2026-11-26 (usability walk).** The `day` filter (UPG-294, "26 Nov 2026") now words the public event page's header (start – end), its Key dates (registration deadline, event date) and its WhatsApp/X share text, the admin dashboard's "Platform overview for …", both lines of the admin's events list and the coordinator card's "Deadline:". The item asked for a new filter with the weekday ("Thu, 26 Nov 2026"); the one already used on the first pages is kept so every page says dates the same way. The admin's activity feed times stay for UPG-297 (a). 1 new test (`tests/test_dates_in_words.py`). v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-366 | **Five buttons on each ticket, Cancel among them (usability walk).** The ticket's actions on the student's dashboard are View ticket (the one main button), the Hackathon page and the Certificate when there is one, and a "More" button (`<details>`, no script); under More: Edit details, Team page, Badge, Event info and Leaderboard, then "Cancel registration" alone below a dashed line, still asking to confirm (`data-confirm`). Checked in Chromium at 390 px: no sideways scroll. 2 new tests (`tests/test_ticket_card_more.py`). v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-367 | **Prizes without ₹ (usability walk).** New `prize` filter (`services_registration_state.prize_text`): a plain amount, with or without ₹, "Rs.", "INR", commas or "/-", is shown as ₹ with Indian grouping ("100000" is "₹1,00,000"; paise kept); anything else ("Trophy and goodies", "₹2000 + trophy") exactly as typed. Used on the event page's three prize cards. 14 new tests (`tests/test_prize_rupees.py`). v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `7146f32`) | UPG-368 | **A round button on the bottom menu (usability walk).** Measured: the button was the SPOC console's quick-actions "speed dial" (`bottom: 24px`), whose 56 px button reached 820 px on an 844 px phone over the menu starting at 782 px, on "Install". Under 768 px, with the bottom menu shown, it now sits 16 px above the menu. Back to top and the chat button were already lifted (UPG-63). 1 new browser test (`tests/test_round_buttons.py`: the SPOC console, create event and the student's dashboard, scrolled; fails without the fix). v1.16 lists it. Full pytest (one run for UPG-362 to UPG-368): 5 failed, 1,938 passed, 8 skipped. The 5 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322 (`test_hackathon_browser`, passes alone) and `test_type_check_config` (fails only in the scratch copies). Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `bd9397b`) | UPG-297; new UPG-375, UPG-376, UPG-377 | **The first-pages review, (a) to (g).** (a) New `services_activity.py`: `action_text` ("LOGIN_SUCCESS" is "Signed in"; others as a sentence, "Rooms allocated"), `when_text` (UTC to India, "16 Nov 2026, 05:05"), `dashboard_feed` (no signing in and out, 15 newest, from 80 fetched); filters `action_words` and `ist`; the feed read `log.detail`, which nothing writes, so every entry said "—": it reads `details`. The audit log page keeps every entry. (b) Measured at 1280 px with a long user name: the title was 106 of 112 px; it no longer shrinks and the name ends in "…". (c) The heading is "Hello, <first name>"; the "My registrations" card shows only with tickets. (d) `profile_hero(short=True)` marks the section `data-banner="short"` (an attribute, so `class="profile-hero"` is unchanged): 140 px, 96 px on a phone. (e) The stored-status badge is gone; the organiser's words show only when they differ from "Visitors see" (Draft, Waiting for approval). (f) "Events that are over aren't shown or counted here." for everyone but the Super Admin. (g) 6 events at first instead of 9, filtered at once instead of after 350 ms; "Load more" became "See all events" (/events); search and the category tabs still look through every event. 18 new tests. Full pytest: 4 failed, 1,957 passed, 8 skipped. The 4 are known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests) and `test_type_check_config` (fails only in the scratch copies); UPG-322's browser test passed. `ruff check` on the changed files passes; `ruff check .` fails only on UPG-376's file and the owner's uncommitted test. Rule 8: no open item cites the changed lines. |
| 2026-11-21 | (uncommitted, on `2a065c3`) | UPG-377 | **"Team" once.** New `team_label` ("Phoenix" is "Team Phoenix"; "Team Phoenix", "TEAM X", "team-alpha" stay as they are; "Teamwork Heroes" is "Team Teamwork Heroes"), the `team` filter, and the hackathon result email, the badge's role line, the student's ticket and waitlist cards use it. 11 new tests. Full pytest: 6 failed, 1,979 passed, 8 skipped. Known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322's flaky browser test and `test_type_check_config` (scratch copies only), each passing or known before this change; `test_coordinator_view_counts_registrations_not_the_cached_counter` failed once because a random event id contained "645" and passes on a re-run. `ruff check` on the changed files passes. |
| 2026-11-21 | (uncommitted, on `2a065c3`) | UPG-378; new UPG-379 | **Teams that came but weren't scanned.** The owner's SPOC, on 21 Nov, pressed Check In on an absent team of a hackathon that ran 19–20 Nov and got "Scanning only opens on 2026-11-19": `api_checkin` allowed only `date == today` by the server's clock (UTC), so day two of every multi-day event was refused too, and the coordinator's scanner had the same rule. New `checkin_window` (before / open / over, in India, the days in words); both scanners use it. After the event the SPOC's Manual List says "Mark present" and sends `late: true`; `_late_checkin` refuses cancelled and not-selected registrations, marks the lead and every member present, every day of the event (so the 80% rule of a multi-day certificate counts them), `checkin_late`, `checked_in_by`, and writes `LATE_CHECKIN`. Re-running the certificate run issues only to the newly present. 13 new tests. Full pytest: 6 failed, 1,979 passed, 8 skipped. Known: UPG-333 (`test_seminar_e2e`), UPG-289 (2 `[coordinator registrations]` pagination tests), UPG-322's flaky browser test and `test_type_check_config` (scratch copies only), each passing or known before this change; `test_coordinator_view_counts_registrations_not_the_cached_counter` failed once because a random event id contained "645" and passes on a re-run. `ruff check` on the changed files passes. UPG-379 records what the in-window SPOC check-in still lacks. |
