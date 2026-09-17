# SapthaEvent REST API v1 Specification

## 1. Overview
The SapthaEvent REST API v1 (`/api/v1`) provides programmatic access to event management, ticketing, workflow state transitions, rubric scoring, certificates, and the AI Copilot.

### Base URL
```
https://events.snpsu.edu.in/api/v1
```

### Authentication
All non-public endpoints require an RFC 6750 Bearer token:
```http
Authorization: Bearer <jwt_access_token>
```
Obtain tokens via `POST /api/v1/auth/login`.

---

## 2. Universal Event Endpoints

### 2.1 List Events
`GET /api/v1/events`
- Query parameters:
  - `q`: Text search across title, description, and venue.
  - `category`: Filter by category (e.g., `Technical`, `Cultural`).
  - `type`: Filter by template type (e.g., `hackathon`, `conference`).
  - `mode`: Filter by mode (`offline`, `online`, `hybrid`).
  - `page`: Page index (default: `1`).
  - `per_page`: Page size (default: `20`, max: `100`).

### 2.2 Get Event by Slug or ID
`GET /api/v1/events/<slug_or_id>`
- Response:
```json
{
  "status": "success",
  "data": {
    "id": "c784f47b-...",
    "slug": "quantum-computing-symposium-2026",
    "title": "Quantum Computing Symposium 2026",
    "category": "Technical",
    "event_type": "conference",
    "capacity": 300,
    "fee": 500.0,
    "ticket_tiers": [...]
  }
}
```

### 2.3 Create Event
`POST /api/v1/events` (Admin / SPOC only)
- Request body:
```json
{
  "title": "Cyber Warfare CTF 2026",
  "category": "Technical",
  "event_type": "hackathon",
  "event_mode": "hybrid",
  "venue": "Lab 401, CSE Block",
  "capacity": 150,
  "fee": 200.0,
  "date_str": "2026-11-25"
}
```

---

## 3. Workflow & Lifecycle Endpoints

### 3.1 Transition Workflow Stage
`POST /api/v1/events/<event_id>/workflow/transition` (Admin / Coordinator)
- Request body:
```json
{
  "target_step": "evaluation",
  "notes": "Closing submissions and dispatching rubric sheets to judges."
}
```

---

## 4. Ticketing & Verification Endpoints

### 4.1 Issue Digital Pass
`POST /api/v1/events/<event_id>/tickets/issue`
- Request body:
```json
{
  "registration_id": "reg-12345",
  "tier_id": "vip-delegate",
  "attendee_name": "Dr. Alan Turing",
  "attendee_email": "turing@cam.ac.uk"
}
```

### 4.2 Verify QR Token (Coordinator Scanner)
`POST /api/v1/tickets/verify`
- Request body:
```json
{
  "signed_token": "eyJh...hmac_token"
}
```

### 4.3 Batch Offline Sync
`POST /api/v1/tickets/sync-offline`
- Request body:
```json
{
  "event_id": "evt-12345",
  "scans": [
    {
      "token": "token-abc",
      "scanned_at": "2026-11-20T08:45:00Z",
      "gate_id": "Gate-2"
    }
  ]
}
```

---

## 5. AI Copilot Endpoints

### 5.1 Propose Event Schema
`POST /api/v1/ai/copilot/propose` (Admin only)
- Request body:
```json
{
  "prompt": "Create a 3-day aerospace engineering design hackathon with CFD simulation rubrics."
}
```

### 5.2 Get Proposal Status
`GET /api/v1/ai/copilot/proposals/<proposal_id>`

### 5.3 Approve & Instatiate Proposal
`POST /api/v1/ai/copilot/proposals/<proposal_id>/approve`

---

## 6. Standard Error Schema

```json
{
  "status": "error",
  "code": "permission_denied",
  "message": "You do not have the required role to perform this action.",
  "timestamp": "2026-09-17T11:20:00Z"
}
```
Common HTTP Status Codes:
- `200 OK`: Request succeeded.
- `201 Created`: Resource created.
- `400 Bad Request`: Invalid parameters or validation failure.
- `401 Unauthorized`: Missing or expired Bearer token.
- `403 Forbidden`: Insufficient role permissions.
- `404 Not Found`: Resource does not exist.
- `429 Too Many Requests`: Rate limit threshold exceeded.
- `500 Internal Error`: Server encountered an unexpected error.
