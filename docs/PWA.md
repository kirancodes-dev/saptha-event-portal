# SapthaEvent Progressive Web App (PWA) Specification

## 1. Overview
SapthaEvent functions as an installable Progressive Web App (PWA) compliant with W3C Web App standards. It provides full offline usability for ticket viewing, campus wayfinding, and gate check-in scanning even in subterranean auditoriums or areas with intermittent cellular coverage.

---

## 2. Web App Manifest (`/manifest.json`)
The manifest (`static/manifest.json`) controls branding and device integration:
```json
{
  "name": "SapthaEvent Universal Portal",
  "short_name": "SapthaEvent",
  "description": "Enterprise Event Operating System for SNPSU",
  "start_url": "/?source=pwa",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait-primary",
  "background_color": "#0f172a",
  "theme_color": "#f37021",
  "icons": [
    {
      "src": "/static/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any maskable"
    },
    {
      "src": "/static/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any maskable"
    }
  ]
}
```

---

## 3. Service Worker & Caching Strategies (`/sw.js`)
The Service Worker (`static/sw.js`) implements tiered caching policies:

### 3.1 Cache First, Network Fallback (Static Shell)
- Pre-caches core CSS, JavaScript bundles, Google Fonts, Bootstrap icons, and logos.
- Guarantees immediate sub-second visual shell rendering even with zero network connectivity.

### 3.2 Network First with Offline Vault Fallback (Dynamic Content)
- Applied to event agendas, registered user ticket passes, and leaderboards.
- If network request fails or times out (after 3 seconds), serves the most recently cached snapshot from the IndexedDB store.

### 3.3 Custom Offline Page (`/offline.html`)
- If an un-cached resource is requested while offline, serves an interactive offline fallback page detailing cached capabilities.

---

## 4. Offline Queue & Background Sync
For Gate Coordinators operating without Internet:
1. Scanned ticket tokens are recorded into an IndexedDB table (`offline_scan_queue`).
2. Scans are cryptographically pre-verified against cached event public keys.
3. When connectivity is re-established, the Service Worker triggers Background Sync to call `/api/v1/tickets/sync-offline`.
4. Reconciles batch scans, detecting duplicates and alerting the coordinator.
