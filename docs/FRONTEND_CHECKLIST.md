# Frontend checklist (UPG-63)

Per-template status for the portal redesign (UPG-63 in `docs/FEATURE_REVIEW.md`).
Generated on 2026-10-12 from the working tree on top of `0fd9f3a` (not committed).
The UPG-63 redesign changed only `templates/`, `static/` and `docs/`. The one
backend change is `routes_profile.py`, for UPG-71 (profile photos), which the owner
approved on 2026-10-12. Its tests are in `tests/test_profile_avatar.py`. No schema,
permission or configuration file changed.

## How to read the table

- **Before:** the layout the template extended at `0fd9f3a`, plus what was off-system
  (its own top bar or sidebar, dark slate colours, many inline styles, emoji used as UI).
- **Status:**
  - *Rebuilt on app/status layout*: moved from a standalone page with its own header onto
    `base_classic.html` (app bar, page head, flash) or `layouts/status.html`.
  - *Restyled*: kept its layout (full-screen scanners, tickets, certificate, projector board,
    marketing pages) and moved onto the design-system tokens.
  - *Brand pass only*: colour and font tokens only (under 15 changed lines).
  - *New*: created for UPG-63.
  - *Shared partial*: an include or layout piece styled by `global.css`; not edited.
  - *Not rendered*: never rendered by any route (UPG-64); left unchanged on purpose.
- **Verified by:**
  - *Screenshot + render check*: loaded in headless Chromium with seeded data, as the role
    that uses it, at 1280px and/or 360px. Each page was checked for HTTP status, horizontal
    scroll, page errors, console errors and failed `/static/` requests. It also passed the
    render check.
  - *Render check*: rendered with a stand-in context (`render_check.py`, every template),
    without seeded data.
  - No pytest was run (the owner asked for a development-only run).

## Summary

| | Count |
|---|---|
| Templates | 132 (126 rendered or included, 6 never rendered) |
| Rebuilt on the app or status layout | 56 |
| Restyled on their own layout | 49 |
| Brand pass only | 6 |
| New | 3 (`includes/ui.html`, `includes/flash_messages.html`, `layouts/status.html`) |
| Shared partials not edited / already on the system | 8 / 4 |
| Not rendered (UPG-64), unchanged | 6 |
| Checked in Chromium with seeded data | 60 templates (two sweeps of 45 and 48 page loads at 1280px and 360px, plus targeted checks of scanners, tickets and certificate pages) |
| Render check | 125 / 132 pass; the other 7 need real data and all 7 were checked in Chromium |

Roles covered: anonymous visitor, Student/Participant, Club SPOC, Event Coordinator,
Volunteer (scanner), Judge and Super Admin, plus the tenant/marketing pages.

## Checks run on 2026-10-12

- **Desktop sweep, 1280px:** 45 pages across the six roles. Every page answered 200 at its own
  URL. No page error, console error or failed `/static/` request.
- **Phone sweep, 360px:** 48 pages. No page scrolls horizontally (document width = 360 on all).
  Every 404 in the first pass was a wrong URL I'd guessed; it was re-run with the real route.
  Two pages are unreachable with the seed data: the matchmaker (feature-gated, D-9) and
  placement (no placement event is seeded). The tournament admin page was checked as
  Super Admin.
- **Dark theme:** the admin dashboard, admin analytics, coordinator dashboard and student
  dashboard were checked in dark mode. Navy text moved to `--brand-ink`, which stays legible
  on dark surfaces.
- **Keyboard focus:** `:focus-visible` uses `--brand-gold-700`, which is at least 3:1 on white
  and on navy. Custom inputs that set `outline: none` still get the outline (`global.css`, end).
  `--focus-ring` is a two-tone ring.
- **Charts:** Apache ECharts 5.5.1 through `static/js/se-echarts.js` (UPG-83; Chart.js and
  `chart-theme.js` are gone). Four categorical hues that pass the dataviz validator on every
  pair, in light and dark mode; a chart shows at most four series and folds the rest into a
  neutral "Other". Colour follows the entity (measure or category), never its rank. Magnitude
  uses a single-hue ramp validated as ordinal; status colours are used only for status and
  always carry a text label. Every chart has a table view and PNG download, and redraws when
  the dark-mode toggle flips.
- **Scripts:** every edited `static/js` file passes `node --check`.

## Found during the redesign (new items in FEATURE_REVIEW, not fixed here)

- **UPG-65:** fabricated figures and simulated features on live pages.
- **UPG-66:** two forms post without a CSRF token.
- **UPG-67:** the coordinator scanner throws a script error when locked.
- **UPG-68:** the coordinator dashboard links to a form builder that coordinators can't open.
- **UPG-69:** the legacy certificate check and the digital ticket lose the lead's name and
  email on the SQL adapter.
- **UPG-70:** the confetti library's worker is blocked by the CSP.

Fixed here because they were frontend-only and part of the redesign (see the UPG-63 entry):
- Invented values on the digital wallet pass.
- The fake certificate status tracker.
- An inaccurate "cryptographically signed" claim.
- Personal-looking fallback details on the student dashboard.
- Emoji used as UI.
- A role-blind mobile bottom bar.

## Profile photos and the campus photo (2026-10-12)

- **Campus photo:** the whole photo now shows at its own ratio, in the shared `profile_hero`
  (`includes/ui.html`) on the student dashboard and on `/profile/`, the page every role uses.
  It's served as WebP: 158 KB, and 59 KB on phones.
- **Profile photos (UPG-71):** every role can upload a photo or choose one of 8 brand avatars
  (`static/img/avatars/`) at `/profile/#photo`. The app bar shows it everywhere. This was
  checked end to end in headless Chromium.

## Existing tests

No pytest was run. Instead, every string the tests assert (289 positive, 59 negative) was
compared with the old and new templates. Where the redesign had changed the wording on a page
a test reads, the exact text is back, for example "Verification Failed",
"QR Scanner & Check-in" and "Student PASS". No test was changed.

## Per-template status

| Template | Role | Route(s) | Before | Status | Verified by |
|---|---|---|---|---|---|
| `404` | Public | /checkin/<event_id>, /event/<event_id>, /forms/register/<event_id> | standalone | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `429` | Public | /verify | standalone | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `500` | Public | /event/<event_id>, /gamification/leaderboard, /verify | standalone | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/analytics` | Admin | /admin/analytics | standalone; own top bar/sidebar; dark/slate colours; 17 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/audit_log` | Admin | /admin/audit_log | standalone; own top bar/sidebar; dark/slate colours; 11 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/dashboard` | Admin | /admin/dashboard | standalone; own top bar/sidebar; 39 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/event_refunds` | Admin | /admin/events/<event_id>/refunds | base_classic | Brand pass only (colours/fonts) | Render check |
| `admin/leaderboard` | Admin | — | partial; emoji UI | Not rendered by any route (UPG-64), untouched | — |
| `admin/org_units` | Admin | /admin/org_units | standalone; own top bar/sidebar; dark/slate colours; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/payments` | Admin | /admin/payments | base_classic | Brand pass only (colours/fonts) | Screenshot + render check |
| `admin/report` | Admin | /admin/report | standalone; 36 inline styles | Restyled (UPG-63) | Screenshot + render check |
| `admin/send_email` | Admin | /admin/send_email | standalone; own top bar/sidebar; 11 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/sponsors` | Admin | /admin/sponsors | standalone; own top bar/sidebar; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `admin/user_academics` | Admin | /admin/users/<path:email>/academics | base_classic | Brand pass only (colours/fonts) | Render check |
| `admin/users` | Admin | /admin/users | base_classic | Brand pass only (colours/fonts) | Screenshot + render check |
| `admin/venues` | Admin | /admin/venues | standalone; own top bar/sidebar; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `analytics/dashboard` | SPOC / admin | /analytics | standalone | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `base_classic` | Public | — | document; own top bar/sidebar | Restyled (UPG-63) | Render check |
| `compliance/privacy_settings` | Signed-in user | /compliance/settings | base_classic; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `compliance/sla` | Signed-in user | /compliance/sla | base_classic | Restyled (UPG-63) | Render check |
| `components/language_selector` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `components/mobile_nav` | Shared | include | partial; 49 inline styles; emoji UI | Restyled (UPG-63) | Render check |
| `components_reference` | Public | /components-reference | standalone; 69 inline styles | Restyled (UPG-63) | Render check |
| `coordinator/ai_matching` | Coordinator / volunteer | /ai/match_page/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 44 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `coordinator/dashboard` | Coordinator / volunteer | /coordinator/dashboard | standalone; own top bar/sidebar; dark/slate colours; 52 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `coordinator/form_builder` | Coordinator / volunteer | /forms/builder/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 28 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `coordinator/form_responses` | Coordinator / volunteer | /forms/responses/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 11 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `coordinator/on_spot` | Coordinator / volunteer | /coordinator/on_spot | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `coordinator/registrations` | Coordinator / volunteer | /coordinator/registrations/<event_id> | base_classic | Already on system, checked | Screenshot + render check |
| `coordinator/results_summary` | Coordinator / volunteer | /ai/results_page/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 35 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `coordinator/scan` | Coordinator / volunteer | /coordinator/scan/<event_id> | fullscreen; dark/slate colours; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `coordinator/scan_hud` | Coordinator / volunteer | /coordinator/scan-hud/<event_id> | fullscreen | Restyled (UPG-63) | Screenshot + render check |
| `coordinator/scanner_selector` | Coordinator / volunteer | /coordinator/scanner | standalone; own top bar/sidebar; dark/slate colours; 12 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `coordinator/verify_result` | Coordinator / volunteer | /ticket/verify/<token> | standalone; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `developer/api_docs` | Developer (public) | /developer/docs | standalone; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `events/catalog` | Public | /events | base_classic; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `feedback/analytics` | SPOC / student | /feedback/analytics/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 26 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `forgot_password` | Public | /forgot_password | standalone | Restyled (UPG-63) | Screenshot + render check |
| `gamification/leaderboard` | Student | /gamification/leaderboard | base_classic; dark/slate colours; 17 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `hackathon/kanban_pipeline` | Student / SPOC | /hackathon/pipeline/<event_id> | base_classic; dark/slate colours | Restyled (UPG-63) | Render check |
| `hackathon/project_detail` | Student / SPOC | /hackathon/project/<submission_id> | base_classic; dark/slate colours | Restyled (UPG-63) | Render check |
| `hackathon/submit_project` | Student / SPOC | /hackathon/submit/<event_id> | base_classic; dark/slate colours | Restyled (UPG-63) | Render check |
| `includes/chatbot` | Shared | include | partial; dark/slate colours; emoji UI | Not rendered by any route (UPG-64), untouched | — |
| `includes/csrf_fetch` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `includes/flash_messages` | Shared | include | new in UPG-63 | New (UPG-63) | Render check |
| `includes/list_search` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `includes/pagination` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `includes/pwa_head` | Shared | include | partial | Brand pass only (colours/fonts) | Render check |
| `includes/share_strip` | Shared | include | partial | Restyled (UPG-63) | Render check |
| `includes/site_footer` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `includes/tournament` | Shared | include | partial; 11 inline styles; emoji UI | Restyled (UPG-63) | Render check |
| `includes/ui` | Shared | include | new in UPG-63 | New (UPG-63) | Render check |
| `index` | Public | / | standalone; own top bar/sidebar; dark/slate colours; 52 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `judge/dashboard` | Judge | /judge/dashboard | standalone; own top bar/sidebar; dark/slate colours; 15 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `judge/teams` | Judge | /judge/event/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 35 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `layouts/_bootstrap_css` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `layouts/_bootstrap_js` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `layouts/_fontawesome` | Shared | include | partial | Shared partial, styled by global.css | Render check |
| `layouts/document` | Shared | include | partial | Already on system, checked | Render check |
| `layouts/fullscreen` | Shared | include | document | Already on system, checked | Render check |
| `layouts/standalone` | Shared | include | document | Already on system, checked | Render check |
| `layouts/status` | Shared | include | new in UPG-63 | New (UPG-63) | Render check |
| `live/leaderboard` | Public (projector) | /live/<event_id> | fullscreen; emoji UI | Restyled (UPG-63) | Render check |
| `login` | Public | /login | standalone; 53 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `marketing/features` | Public | /features | standalone; own top bar/sidebar; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `marketing/landing` | Public | /platform | standalone; own top bar/sidebar; dark/slate colours; 13 inline styles | Restyled (UPG-63) | Screenshot + render check |
| `marketing/pricing` | Public | /pricing | standalone; own top bar/sidebar; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `offline` | Public | /offline | standalone | Rebuilt on app/status layout (UPG-63) | Render check |
| `onboarding/signup` | Public / new tenant | /onboarding/signup | standalone; dark/slate colours | Restyled (UPG-63) | Render check |
| `onboarding/wizard` | Public / new tenant | /onboarding/wizard | standalone; dark/slate colours | Restyled (UPG-63) | Render check |
| `participant/badge` | Student | /participant/badge/<reg_id> | fullscreen | Restyled (UPG-63) | Render check |
| `participant/certificate` | Student | /coordinator/certificate/<reg_id>/<usn>, /participant/certificate/<reg_id> | fullscreen; dark/slate colours; emoji UI | Restyled (UPG-63) | Render check |
| `participant/dashboard` | Student | /participant/dashboard | standalone; dark/slate colours; 104 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `participant/feedback_form` | Student | /participant/feedback/<reg_id> | standalone | Rebuilt on app/status layout (UPG-63) | Render check |
| `participant/ledger` | Student | /participant/api/ledger | standalone; own top bar/sidebar; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `participant/matchmaker` | Student | /participant/matchmaker/ | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `participant/my_events` | Student | /participant/my_events | standalone; own top bar/sidebar; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `participant/registration_confirmed` | Student | /registration/confirmed | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `participant/success` | Student | — | partial | Not rendered by any route (UPG-64), untouched | — |
| `participant/ticket` | Student | /ticket/<reg_id> | standalone; dark/slate colours; 22 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `payment/checkout` | Student | /payment/checkout/<event_id> | standalone; dark/slate colours; 11 inline styles | Rebuilt on app/status layout (UPG-63) | Render check |
| `payment/failed` | Student | /payment/failed | base_classic; 15 inline styles; emoji UI | Restyled (UPG-63) | Render check |
| `payment/success` | Student | — | partial; dark/slate colours | Not rendered by any route (UPG-64), untouched | — |
| `portfolio/public_profile` | Public | /u/<usn> | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `profile/dashboard` | Signed-in user | /profile/ | standalone; own top bar/sidebar; dark/slate colours; 13 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/calendar` | Public | /calendar | standalone; own top bar/sidebar; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/certificate_preview_embed` | Public | /verify/<cert_hash>/preview | fullscreen; dark/slate colours | Restyled (UPG-63) | Render check |
| `public/checkin_already` | Public | /checkin/<event_id>/submit | standalone | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/checkin_closed` | Public | /checkin/<event_id> | standalone | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/checkin_disabled` | Public | /checkin/<event_id> | standalone; emoji UI | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/checkin_success` | Public | /checkin/<event_id>/submit | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/event_details` | Public | /event/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 24 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/exam_interface` | Public | /exams/<event_id> | fullscreen; dark/slate colours | Restyled (UPG-63) | Render check |
| `public/kiosk` | Public | /checkin/kiosk | fullscreen; dark/slate colours | Restyled (UPG-63) | Render check |
| `public/leaderboard` | Public | /participant/leaderboard/<event_id> | standalone; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/live_streams` | Public | /live/streams | standalone; dark/slate colours; emoji UI | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/login` | Public | — | partial | Not rendered by any route (UPG-64), untouched | — |
| `public/privacy` | Public | /privacy | base_classic; 20 inline styles | Restyled (UPG-63) | Screenshot + render check |
| `public/reels` | Public | /live/reels | fullscreen; dark/slate colours; emoji UI | Restyled (UPG-63) | Render check |
| `public/register` | Public | — | partial | Not rendered by any route (UPG-64), untouched | — |
| `public/registration_closed` | Public | /forms/register/<event_id> | standalone; emoji UI | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/registration_form` | Public | /forms/register/<event_id> | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/self_checkin` | Public | /checkin/<event_id> | standalone; emoji UI | Rebuilt on app/status layout (UPG-63) | Render check |
| `public/terms` | Public | /terms | base_classic; 16 inline styles | Restyled (UPG-63) | Screenshot + render check |
| `public/tournament_fixtures` | Public | /tournament/fixtures/<event_id> | standalone; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/verify_certificate` | Public | /verify/<cert_hash> | standalone; dark/slate colours; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `public/verify_fail` | Public | /verify/<cert_hash> | standalone | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/verify_lookup` | Public | /verify | standalone | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `public/verify_success` | Public | /verify/<cert_hash> | standalone; dark/slate colours; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `public/wayfinder` | Public | /platform/wayfinder | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `register` | Public | /register | standalone; 12 inline styles | Restyled (UPG-63) | Screenshot + render check |
| `reset_password` | Public | /reset_password | standalone | Restyled (UPG-63) | Render check |
| `reset_password_token` | Public | /reset_token/<token>, /set_password/<token> | standalone | Restyled (UPG-63) | Render check |
| `spoc/agenda` | SPOC | /spoc/agenda/<event_id> | standalone; own top bar/sidebar | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/ai_report` | SPOC | /spoc/ai_report/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 30 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/create_event` | SPOC | /spoc/create_event | standalone; dark/slate colours; 47 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `spoc/dashboard` | SPOC | /spoc/dashboard | standalone; own top bar/sidebar; dark/slate colours; 240 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `spoc/edit_event` | SPOC | /spoc/edit_event/<event_id> | standalone; own top bar/sidebar | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/judging_audit` | SPOC | /spoc/judging/audit/<event_id> | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/nfc_scanner` | SPOC | /spoc/ticket/nfc-verify/<event_id> | fullscreen; dark/slate colours | Restyled (UPG-63) | Screenshot + render check |
| `spoc/placement` | SPOC | /placement/<event_id> | base_classic | Brand pass only (colours/fonts) | Render check |
| `spoc/proctor_monitor` | SPOC | /spoc/proctor/<event_id> | base_classic; dark/slate colours | Restyled (UPG-63) | Render check |
| `spoc/profile` | SPOC | /spoc/profile | standalone; own top bar/sidebar; dark/slate colours; 12 inline styles | Rebuilt on app/status layout (UPG-63) | Screenshot + render check |
| `spoc/results` | SPOC | /spoc/results/<event_id> | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/room_allocation` | SPOC | /spoc/room_allocation/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 25 inline styles | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/round_panel` | SPOC | /spoc/round_panel/<event_id> | standalone; own top bar/sidebar; dark/slate colours; 41 inline styles; emoji UI | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/scan` | SPOC | /spoc/scan/<event_id> | fullscreen; own top bar/sidebar; dark/slate colours; 19 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `spoc/schedule_optimizer` | SPOC | /spoc/schedule/optimize/<event_id> | standalone; dark/slate colours | Rebuilt on app/status layout (UPG-63) | Render check |
| `spoc/tournament` | SPOC | /tournament/<event_id> | base_classic; dark/slate colours; 13 inline styles; emoji UI | Restyled (UPG-63) | Screenshot + render check |
| `teams/join` | Student | /teams/join | base_classic | Restyled (UPG-63) | Render check |
| `teams/view` | Student | /teams/<reg_id> | base_classic | Restyled (UPG-63) | Render check |
| `tickets/digital_wallet` | Student | /ticket/wallet/<ticket_code_or_id> | standalone; dark/slate colours; emoji UI | Restyled (UPG-63) | Render check |
