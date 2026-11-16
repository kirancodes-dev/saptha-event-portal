# The installable app and what works offline

SapthaEvent can be installed from the browser ("Add to Home Screen"). This
page says what that gives, what works without a connection, and what is kept
on the device. It describes `static/sw.js`, `static/js/offline-sync.js` and
`static/manifest.webmanifest` as they are.

## Installing

The manifest is served at `/manifest.webmanifest`. Installed, the site opens
in its own window. There is no separate app-store app in this repository's
web deployment.

## What the service worker does

| Request | Rule |
|---|---|
| `/static/*` | Answered from the cache, refreshed in the background. |
| Pages (`GET`) | The network first; if it fails, the copy from the last visit, if there is one; otherwise the offline page. |
| `/offline` | From the cache: "You're offline". |
| `/live/state.json`, `/live/ops.json` | Never cached: a registration state must be current or absent. |
| `POST` and other writes, streams, other sites | Not intercepted. |

So, offline, a person can re-open a page they already opened on that device
(their ticket, for instance) and nothing else. Forms cannot be submitted
offline. A cached page can be out of date; the registration state on it is
refreshed only when the connection is back.

Push notifications are shown when the person has allowed them and the
deployment has push keys configured.

## Check-in without a connection

The full-screen scanner (`/coordinator/scan-hud/<event>`) keeps working when
the connection drops:

1. A scan made offline is stored on the device and shown as "kept, not yet
   checked". The scanner cannot say whether the ticket is valid: only the
   server can.
2. When the connection returns, each kept scan is sent with the time it was
   made. The server checks it exactly as a live scan and answers checked in,
   already in, or refused, and the scanner shows a count of each. A scan the
   server could not answer stays in the queue.
3. If two devices scanned the same ticket, the first to reach the server
   checks it in; the other is told "already in".
4. A scan's own time is used for the attendance day when it is within 72
   hours and not in the future; otherwise the time it arrived.

Not possible offline: looking a person up by name, checking in a ticket whose
payment is not confirmed (the server refuses it at sync), and walk-in
registration.

## What is kept on the device

| Data | Where | Removed |
|---|---|---|
| Scans waiting to be sent: the ticket token, the event, the time, and a short account marker | IndexedDB | When the server has answered; at sign-out (after a warning if any are unsent) |
| The entry list for the event being scanned (which tickets may enter) | `localStorage` | At sign-out |
| Pages and static files already visited | Cache Storage | When the cache version changes; by clearing site data |

The queue is per account: a second person signing in on the same device
cannot see or send the first person's scans. No names, phone numbers, signing
keys or passwords are stored for check-in. A shared phone should still be
signed out after the event; clearing the browser's site data removes
everything above.

## Tested

`tests/test_offline_checkin.py` drives a headless browser through the offline
queue, the sync report, two accounts on one device and sign-out.
`tests/test_live_refresh.py` covers the never-cached state requests.
