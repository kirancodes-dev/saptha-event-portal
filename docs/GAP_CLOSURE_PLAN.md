# SapthaEvent: Master Gap-Closure Plan and Coding-Agent Prompt

**Prepared:** 21 November 2026  
**Use:** Save this file, then give its **Agent Prompt** section to a coding agent from the SapthaEvent repository. Fill in the work-item form before each implementation run.  
**Important:** This is a plan based on a repository snapshot. Before work, the agent must reread the current `AGENTS.md` and `docs/FEATURE_REVIEW.md`; statuses and dependencies may have changed.

## 1. Product outcome

Build SapthaEvent into the trusted, institution-owned campus engagement system that:

- helps students find relevant campus activities and register easily;
- helps organizers plan, approve, run and report on events;
- turns verified participation, roles, hours and results into a student-controlled record;
- produces traceable institutional evidence from the same event data;
- reduces reliance on disconnected forms, spreadsheets, messages and certificate workflows.

### Product position to test

> Run campus events in one place. Give every real contribution a verified record. Give the university its evidence without spreadsheet chasing.

### Where the product can win

The target is not “another ticketing site.” Ticketing, registration, QR entry, basic analytics and certificates are common. The strongest potential distinction is the connection between **campus operations → verified attendance and outcomes → student achievement record → institutional reporting**.

Start with one university and three representative event shapes: a workshop, a judged competition/hackathon and a multi-event fest. Prove operational and student value there. Add cross-campus discovery only after multiple campuses can supply active events. Integrate or syndicate public events outward instead of trying to recreate Eventbrite or Unstop’s audience network.

### Initial customer hypothesis

Target universities and colleges with many departments/clubs, recurring festivals and competitions, and staff who spend time reconciling registrations, check-in, certificates and annual evidence. Likely buyers are student affairs/university administration; likely champions are IQAC, event-office, placement and club coordinators. Validate the buyer and budget with interviews; do not treat this hypothesis as confirmed market demand.

## 2. Repository rules the agent must follow

These rules come from the repository’s `AGENTS.md` and are mandatory for code work:

1. Read `AGENTS.md` and `docs/FEATURE_REVIEW.md` before every item. Use `docs/FEATURE_REVIEW.md` as the backlog source of truth. Read the archive only for the selected item.
2. Work on **one exact item ID per run** (`BLK-XX` or `UPG-XX`). Do not combine nearby fixes or implement the whole roadmap in one change. If the work-item form has no ID, ask which item to work on or propose a new backlog item.
3. Do not start a UPG item while any BLK item is marked TODO, unless the owner explicitly says to proceed.
4. Check the selected item against current code and its “Last verified” commit. If code has changed since then, update the item’s evidence/status before building.
5. Stop if a dependency is not DONE or a required owner decision is unresolved. Report the specific blocker; do not guess.
6. Build only the acceptance criteria in the selected item. Every criterion needs a passing test. Run the full pytest suite and `ruff check .` before finishing. Never delete, skip or weaken tests to get a pass.
7. Update `docs/FEATURE_REVIEW.md` exactly as required: status, evidence (`file:line`), verification date/commit, index row and changelog. Move completed item details to the archive and update affected inventory/event-type rows.
8. Record newly found problems as new backlog items with the next free ID. Do not repair them inside the selected item unless they are required by its acceptance criteria.
9. At each phase end, re-verify every open item once. Run an early re-verification if shared infrastructure such as `db_adapter.py`, `models_pg.py`, `services_permission.py` or `tests/conftest.py` changes.
10. Do not push, deploy, contact GitHub Support, change production settings or use real attendee data. Prepare the steps and evidence for owner-only actions. Never put secrets or personal data into this plan, logs or test fixtures.

The repository instructions take precedence over this roadmap. If they change, follow the current instructions and update this plan’s execution order accordingly.

## 3. Execution gates and roadmap

The feature review snapshot inspected for this plan contained the items below. The agent must recheck their current status first; do not assume any remain open.

### Gate 0 — Trust and release readiness

| Work item | Snapshot status | Required outcome / boundary |
|---|---|---|
| `BLK-01` — public GitHub history cleanup | IN PROGRESS | Tracker says owner/GitHub Support cleanup of old PR refs remains. Agent may inspect read-only status and prepare a checklist, but must not force-push, rewrite remote history, contact support or claim it is closed. Owner verifies closure. |
| `UPG-30` — paid events end to end | IN PROGRESS | Complete code criteria and prepare owner checkout validation. Prove receipts, refund/cancellation state, finance export and provider-confirmed payments. Do not take live money or change production payment keys. |
| `UPG-198` — hackathon rehearsal and browser checks | IN PROGRESS | Finish only the checks assigned to the agent. Firefox/Safari/iPhone checks listed as owner-device work remain owner acceptance until recorded. |
| `UPG-199` — deploy hackathon release | IN PROGRESS | Code/docs and owner runbook may be prepared. Owner runs live smoke checks and approves deployment; agent does not deploy. |
| `D-8` — invented live pages | OPEN | Resolve with owner. If no real media/metrics exist, keep the pages hidden as proposed; never invent view/like counts. |
| `D-14` — paid email plan/sender domain | OPEN | Owner chooses the plan and verified sender domain. Do not switch mail providers or send production mail without this decision. |
| `D-10` — AQAR layout | OPEN | IQAC coordinator confirms the layout. Agent may prepare a mapping for review; do not declare institutional compliance before confirmation. |

**Gate condition:** Do not market production payment flows, accessibility/localization claims, release completeness or historical-secret cleanup as done until their acceptance evidence is recorded. If a blocker requires an owner account or external confirmation, produce a concise checklist and stop at that boundary.

### Gate 1 — Existing correctness and data-integrity backlog

Fix these one at a time, in dependency order, before broad feature expansion. Revalidate every item against current code before starting.

| Item | Gap from the tracker |
|---|---|
| `UPG-151` | Clearing an empty judging score map leaves old scores in PostgreSQL mode. |
| `UPG-153` | Paid registration sends redundant setup/ticket/receipt emails. |
| `UPG-154` | Admin-user test assumes a new user appears on page one and is order/database dependent. |
| `UPG-188` | Waitlist promotion uses event-level price instead of the participant/team’s actual group fee. |
| `UPG-189` | Registration transfer leaves the old ticket wallet holder in place. |
| `UPG-200` | Organizer blast email inserts user text into HTML without escaping. Treat as security-sensitive. |
| `UPG-201` | Paid hackathon in portal mode still sends ticket/receipt emails that should be suppressed. |
| `UPG-202` | Hackathon project submission records a session identifier instead of a timestamp. |
| `UPG-203` | AI result summaries fail after the request context ends. |
| `UPG-208` | Certificate correction cannot update the recipient email. |
| `UPG-210` | Coordinator dashboard test is brittle when random event text contains “645.” |
| `UPG-213` | SQL save of an existing form loses its title, description and keys other than fields. |
| `UPG-215` | Self/manual check-in can admit a cancelled team. |
| `UPG-217` | SQL store preserves only form fields and drops form metadata. |
| `UPG-221` | Walk-in desk does not follow the normal event form/team/capacity/payment workflow. |
| `UPG-223` | Custom USN/phone fields do not persist to the participant’s canonical fields. |
| `UPG-228` | Activity ledger and privacy export scan all registrations to find a member’s teams. |
| `UPG-247` | Cancelled team from a waitlist still appears accepted. |
| `UPG-248` | Cancelled team cannot register again; tracker says owner decision is required. Stop until that decision is resolved. |
| `UPG-258` | Email bounce does not tell the team lead/SPOC that a member address failed. Depends on `D-14` and provider webhook setup. |

`UPG-102` (type errors) is a separate reliability-debt item. Recheck the current error count and dependency on `UPG-100`; only pick it when its dependency is DONE. Do not fix type warnings opportunistically inside unrelated features.

### Gate 2 — Differentiated student and institutional outcome

| Item | Product outcome | Priority |
|---|---|---|
| `UPG-179` | Verified co-curricular transcript by academic year: attended event, verified role, rank, hours/points, certificate and QR verification. Student controls external sharing; only verified records count. | **First product-differentiation build** after blockers/data correctness. |
| `UPG-144` / `D-10` | NAAC/AQAR report from event data; confirm the exact layout with IQAC, preserve source links/evidence and make local category mapping configurable. | Sign off with institution before claiming readiness. |
| `UPG-183` | On-duty attendance letters for verified participants who miss class for an event. | Add after institution policy/approval workflow is confirmed. |
| `UPG-173` | Finish Kannada and Hindi student journeys using existing translations; preserve language selection and verify mobile layout. | Must match actual UI before README claims. |
| `UPG-184` | Complete automated/manual accessibility check to WCAG 2.1 AA scope in the item, keyboard-only registration, screen-reader check and linked accessibility statement. | Must match actual UI before accessibility claims. |

### Gate 3 — Make students and clubs return

| Item | Product outcome |
|---|---|
| `UPG-182` | Club pages, membership requests, office-bearers and club activity report. |
| `UPG-186` | Recurring event series where each occurrence has its own registration and attendance. |
| `UPG-185` | Opt-in weekly “what’s on” digest with visibility filters, unsubscribing and email/WhatsApp quotas. |
| `UPG-187` | Explainable “For you” recommendations using allowed department/interests/own history; never reveal another student’s attendance or registration. |
| `UPG-174` | Real, opt-in teammate matching based on disclosed skills; contact details only after mutual acceptance; remove mock student records. |

Recommended sequence: clubs/recurrence foundation → calendar/discovery → digest/recommendations. Keep all alerts opt-in. Measure repeat participation and no-shows; do not treat sends or page views alone as success.

### Gate 4 — Organizer and fest operations customers actually request

| Item | Product outcome |
|---|---|
| `UPG-167` | Volunteer applications, approvals and shift rota; credit only verified hours. |
| `UPG-168` | Event budget, expense evidence/approval and budget-vs-actual report. |
| `UPG-169` | Sponsor tiers, deliverables and post-event sponsor report. |
| `UPG-166` | Judge conflict-of-interest declarations and conflict-safe assignment/scoring. |
| `UPG-163` | Conference abstract/paper submission, blind reviewer scoring, decisions and proceedings. |
| `UPG-165` | Hackathon mentor office-hour slots, team booking and no-show/load reporting. |
| `UPG-164` | Project gallery and one-person-one-vote people’s choice award. |
| `UPG-170` | Event photo gallery; consent, access control and evidence reuse must be explicit. |
| `UPG-180` | College-wise championship points across fest sub-events, with published scoring rules. |
| `UPG-181` | Accommodation/travel requests and organizer allotment for outstation participants. |
| `UPG-177` | Reserved seats for auditorium events, with capacity and seat-lock rules. |
| `UPG-178` | Merchandise/add-ons tied to ticket and QR collection. |
| `UPG-176` | Real stream/recording embeds; remove/keep hidden any simulated live pages until real media exists. |
| `UPG-175` | AI writing assistance for descriptions/rules/social copy and post-event summaries, always reviewed before publish. Treat as optional support, not the core differentiator. |

Do not implement this whole table as a bundle. Interview organizers, select one exact ID, and ship only that item. Defer seating, merchandise, live streaming and other heavy event-specific capabilities unless pilot customers show they matter.

### Gate 5 — Integration and reach

| Item | Product outcome |
|---|---|
| `UPG-171` | Scoped, authenticated outgoing webhooks and Google Sheets sync for registrations/check-ins/results. Include retries, signatures, replay protection and data minimization. |
| `UPG-172` | Embeddable event card/registration widget for campus and club websites. |

Before hosted multi-campus sales, verify tenant isolation, institution-level branding/domains, identity/roster onboarding, sender domains, payment settlement/refunds, data exports/deletion and support expectations. The repository has a multi-tenancy design note; validate implementation and operational behavior with a second tenant before making SaaS promises. If the work is not represented by an open item, propose a new `UPG-XX` item first rather than silently adding a large new scope.

Build a federated discovery network only after several campuses are live. Then allow organizers to choose which public events are syndicated, preserve the official registration source and eligibility rules, and track external registrations separately.

## 4. Pilot and success measures

Run one pilot with three event shapes: workshop, judged competition/hackathon and multi-event fest. Gather a baseline before launch, then measure:

- **Adoption:** departments/clubs using the portal each term; share of campus events listed; organizers returning for the next event.
- **Student activation:** event view-to-registration conversion; eligible students reached; registrations attributed to calendar/digest/referral; repeat attendance.
- **Event execution:** scan time p50/p95, duplicate/failed scans, registration-to-check-in and no-show rates, time to issue certificates.
- **Institutional outcome:** hours to compile an evidence pack; post-event report completeness; verified student records issued/shared; report traceability back to attendance and evidence.
- **Reliability/trust:** payment reconciliation, notification delivery/bounce, tenant/roster accuracy, accessibility acceptance and backup/restore rehearsal.
- **Business:** paid campus pilots, onboarding time, support hours per campus, renewal and gross margin.

These are measures to collect, not existing product claims. Set numeric targets after the first baseline. A useful hypothesis is to cut evidence-pack preparation time by at least half and issue certificates within one working day; confirm or reject those numbers with pilot data.

## 5. Product and release quality checklist

For every selected item, verify the relevant parts of this checklist:

- Database behavior in SQLite and PostgreSQL where applicable; migrations match models.
- Role permissions, tenant boundary and object-level authorization on every new route/API.
- CSRF, XSS-safe output, rate limits and secure handling of signed links/webhooks.
- Idempotency, capacity/payment correctness, cancellation/refund effects and retry behavior where relevant.
- Privacy notice/consent, minimum necessary data, visibility boundaries, export and deletion behavior.
- Mobile layout at 375px, keyboard operation and screen-reader labels for affected student-facing flows.
- English/Kannada/Hindi localization for affected student screens and messages when localization is enabled.
- Email/WhatsApp/push quotas, opt-in/unsubscribe and delivery-failure states where messages change.
- No fake counts, placeholder event data or “live” states without a real source.
- README, API docs, operator docs, feature review and live-demo claims remain aligned with actual behavior.

## 6. Per-run work-item form

Fill this before every coding-agent run:

```text
Repository: saptha-event-portal
Exact work item ID: [BLK-XX or UPG-XX]
Current item status from docs/FEATURE_REVIEW.md: [TODO / IN PROGRESS]
Current item dependencies and their status: [list; all must be DONE]
Owner decisions/external checks required: [list; unresolved ones block the dependent work]
Target outcome: [one sentence copied from the selected item]
Out of scope: [all other roadmap items]
Allowed work: [implementation + tests + required docs for this one ID]
Production/live-system actions allowed: none unless I explicitly authorize them
Finish with: [tests run, evidence, changed files, remaining owner action]
```

## 7. Copy/paste Agent Prompt

Replace the bracketed fields in the form above, then paste this prompt into the coding agent:

```text
You are working in the SapthaEvent repository. Your assignment is exactly [WORK ITEM ID] from docs/FEATURE_REVIEW.md.

Product goal: make SapthaEvent the trusted, institution-owned campus engagement system that connects well-run events to verified student participation and traceable institutional evidence. Do not expand into a generic ticketing marketplace. This assignment must remain limited to the selected item’s acceptance criteria.

Before editing:
1. Read AGENTS.md and the current docs/FEATURE_REVIEW.md. Check the selected item’s status, Last verified commit, acceptance criteria, dependencies and open decisions.
2. Re-verify its code evidence against the current branch. If it has changed since Last verified, update the item before building.
3. Check whether any BLK item is TODO. If so, stop unless the owner explicitly instructed you to proceed. If a dependency is not DONE or an owner decision is unresolved, stop and report the exact blocker.
4. Confirm the selected item is still needed and not already implemented. Do not trust this plan over the live tracker or code.

Implementation rules:
- Work on this one item only. Do not fix adjacent issues, refactor unrelated code, change product positioning, or build another roadmap item.
- Meet every acceptance criterion in the tracker and add/adjust focused tests for this item. Never weaken, skip or delete tests to make them pass.
- Protect role/tenant boundaries, student privacy, payment correctness, accessibility and localization as relevant to the item.
- Do not use production attendee data or expose secrets. Do not push, deploy, contact third parties, change production settings or perform owner-only actions.
- If you find another problem, record it as the next backlog item per AGENTS.md; do not fix it in this change.

Before finishing:
1. Run the item’s focused checks, the full pytest suite and ruff check . as AGENTS.md requires. If a command cannot run, report the reason and do not claim it passed.
2. Update docs/FEATURE_REVIEW.md exactly as AGENTS.md requires: status/evidence with file:line, verification date/commit, index row and changelog; archive completed item text and update affected inventory/event-type tables.
3. If shared infrastructure changed, run the early full re-verification required by AGENTS.md and list any open-item status changes.
4. Do not mark a task DONE based on code alone when its acceptance depends on owner devices, live payment, GitHub Support, production deployment or institution sign-off. Leave it IN PROGRESS and provide the owner’s exact manual checklist.

Return a concise handoff with: item ID and result; files changed; acceptance criteria evidence; commands/checks and outcomes; any newly recorded backlog IDs; owner-only follow-up; and the next recommended item ID. Stop after this item.
```

## 8. Recommended first sequence

Use the current tracker to confirm these are still open, then execute one ID per run:

1. `BLK-01` — owner verifies completion of history/PR-ref cleanup; coding agent prepares evidence only.
2. `UPG-30` — close paid-event flow and prepare owner payment validation.
3. `UPG-198` — complete the remaining browser/device checks.
4. `UPG-199` — finish owner smoke checklist for the already-deployed revision; no agent deployment.
5. Correctness/data integrity items from Gate 1, starting with security/payment/state issues and honoring dependencies/decisions.
6. `UPG-179` — verified co-curricular transcript, the strongest product differentiation candidate.
7. Owner resolves `D-10` with IQAC; if that requires code changes, add a new tracked item rather than reopening completed `UPG-144` without evidence.
8. `UPG-184` and `UPG-173` — accessibility and Kannada/Hindi student journey before making those claims.
9. `UPG-182`, `UPG-186`, `UPG-185`, `UPG-187` — club continuity, recurring events, calendar/discovery and opt-in digest.
10. Pick remaining organizer/fest capabilities only from pilot evidence; integrate before attempting a cross-campus marketplace.

## 9. Source documents

- [Market research and competitor comparison](saptha-event-portal-market-research.md)
- [SapthaEvent repository](https://github.com/kirancodes-dev/saptha-event-portal)
- `AGENTS.md` — implementation constraints
- `docs/FEATURE_REVIEW.md` — live backlog and status source
- `docs/MULTI_TENANCY.md` — tenancy design to validate before SaaS claims
