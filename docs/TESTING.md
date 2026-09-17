# SapthaEvent Testing & Quality Assurance Guide

## 1. Overview & Test Suite Architecture
SapthaEvent incorporates a comprehensive automated test pyramid spanning **271 automated tests** covering security guards, role access, dual-database parity, ticketing HMAC cryptography, workflow DAG transitions, and full end-to-end event lifecycles.

```
                  ┌───────────────────────────────┐
                  │    E2E Universal Acceptance   │  (7 Tests)
                  │   Hackathon, Conference, etc. │
                  ├───────────────────────────────┤
                  │     Integration Services      │  (84 Tests)
                  │  Workflows, Rubrics, Tickets  │
                  ├───────────────────────────────┤
                  │      Zero-Trust Security      │  (92 Tests)
                  │   RBAC, JWT, Rate Limiting    │
                  ├───────────────────────────────┤
                  │      Unit & Core Helpers      │  (88 Tests)
                  │ Models, Slugs, Adapters, I18n │
                  └───────────────────────────────┘
```

---

## 2. Test Execution Commands

### Run Complete Test Suite
```bash
# Execute all 271 tests
FLASK_ENV=testing FORCE_HTTPS=false pytest tests/ -v
```

### Run Universal Acceptance Tests
```bash
FLASK_ENV=testing FORCE_HTTPS=false pytest tests/test_universal_acceptance.py -v
```

### Run Security & Zero-Trust Suite
```bash
FLASK_ENV=testing FORCE_HTTPS=false pytest tests/test_security.py tests/test_zero_trust_security.py -v
```

### Run with Coverage Analysis
```bash
pytest --cov=. --cov-report=term-missing tests/
```

---

## 3. Universal Acceptance Test Coverage (`tests/test_universal_acceptance.py`)

The acceptance test suite confirms that an administrator can execute end-to-end operations across all 5 major event categories without writing custom code:

1. **Hackathon Universal Flow**:
   - Event creation via configuration
   - Team formation & project repo submission
   - Workflow transition to evaluation
   - Multi-criteria weighted rubric scoring
   - Leaderboard publication
   - Cryptographic certificate issuance

2. **Conference Universal Flow**:
   - Multi-tier ticket setup (`General Admission`, `VIP Delegate`)
   - Attendee ticket generation with signed HMAC QR token
   - Session gate check-in & anti-replay verification
   - Post-conference feedback submission & attendance certificate

3. **Workshop Universal Flow**:
   - Registration with prerequisites
   - Coordinator offline scanner HUD check-in sync
   - Assessment / quiz score recording
   - Completion certificate issuance

4. **Sports Tournament Universal Flow**:
   - Bracket fixture generation
   - Match score tracking with points tables
   - Podium results finalization

5. **Cultural Competition Universal Flow**:
   - Preliminary stage auditions
   - Multi-judge rubric scoring with deterministic tie-breaking
   - Winner announcement

6. **Public Discovery Catalog & iCalendar Export**:
   - Multi-facet search query (`/events?q=...`)
   - RFC 5545 standard `.ics` calendar file download (`/events/<slug>/calendar.ics`)

7. **AI Copilot Lifecycle**:
   - Natural language prompt proposal generation via Google Gemini
   - Draft preview in `PENDING_REVIEW` state
   - Explicit administrator approval & database instantiation
