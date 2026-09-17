# SapthaEvent Security Architecture & Threat Model

## 1. Zero-Trust Security Paradigm
SapthaEvent operates on a strict **Zero-Trust** security model ("Never trust, always verify"). Every request across edge proxies, web portals, native mobile apps, and internal service calls is authenticated, authorized, and cryptographically verified.

```
       [Client Request]
              │
              ▼
   [1. Edge IP Threat Filter] ─── (Fail) ───► 429 / 403 Forbidden
              │ (Pass)
              ▼
   [2. Talisman CSP & HTTPS]
              │
              ▼
   [3. Flask-Limiter Tiered Storage]
              │ (Pass)
              ▼
   [4. JWT & Role RBAC Guard] ─── (Fail) ───► 401 / 403
              │ (Pass)
              ▼
   [5. Anti-CSRF Validation]  ─── (Non-API) ─► Token Check
              │ (Pass)
              ▼
   [6. Parameter Sanitizer]   ─── (Strip Null, SQLi, XSS)
              │
              ▼
   [7. Application Engine]
              │
              ▼
   [8. Tamper-Evident Audit Log]
```

---

## 2. Role-Based Access Control (RBAC) Hierarchy

The system defines 6 formal roles arranged in strict operational tiers:

| Role | Scope | Permitted Operations |
|------|-------|----------------------|
| **SuperAdmin** | Global Platform | Manage all tenants, rotate platform secrets, manage global configs, view system logs. |
| **Admin** | Tenant / Institution | Create/manage events, approve AI proposals, manage staff, view all analytics. |
| **SPOC** | Department / Club | Configure department events, assign judges and coordinators, manage submissions. |
| **Judge** | Assigned Event(s) | Score teams using multi-criteria rubrics, submit evaluation feedback, view live rubric. |
| **Coordinator** | Event Operations | Scan ticket QR codes, verify offline attendance passes, manage on-spot walk-ins. |
| **Participant** | Personal Profile | Register for events, form teams, submit project repositories, download certificates. |

---

## 3. Cryptographic Ticketing & Anti-Replay Tokens
Tickets generate a cryptographically signed HMAC-SHA256 token encoding:
```
payload = {
    "reg_id": "REG-12345",
    "event_id": "EVT-8849",
    "tier_id": "vip-delegate",
    "issued_at": 1726569600,
    "nonce": "random_hex_16"
}
signature = HMAC-SHA256(payload, MASTER_SECRET_KEY)
token = Base64URL(payload) + "." + Base64URL(signature)
```

### Protection Guarantees:
- **Anti-Counterfeit**: Any modification of `reg_id` or `tier_id` breaks the HMAC signature.
- **Anti-Replay**: Scanned passes record `checked_in_at` timestamp with optimistic concurrency locks in the database. Subsequent scans instantly return:
  ```json
  {"valid": false, "reason": "already_checked_in", "checked_in_at": "2026-11-20T09:12:00Z"}
  ```
- **Time-Window Enforced**: Passes cannot be verified prior to event gate open window.

---

## 4. Rate Limiting & Denial-of-Service Defense
Powered by `Flask-Limiter` with fallback to Redis:
- **Public Catalog**: 100 requests / minute per IP.
- **Authentication**: 10 attempts / minute per IP (locks IP after 5 failed attempts).
- **Scanner HUD**: 300 scans / minute per authenticated Coordinator.
- **AI Proposal Generator**: 5 proposals / minute per Admin.

---

## 5. Security Headers (Flask-Talisman)
- `Content-Security-Policy`: Disables unsafe-eval; whitelists trusted Google Fonts, CDNJS, and Firebase endpoints.
- `X-Content-Type-Options: nosniff`: Prevents MIME-type sniffing.
- `X-Frame-Options: SAMEORIGIN`: Eliminates clickjacking attacks.
- `Strict-Transport-Security (HSTS)`: 1-year max-age with preload directive in production.
