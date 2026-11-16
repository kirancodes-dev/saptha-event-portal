// static/js/offline-sync.js — scans made without a connection wait in IndexedDB
// and are sent to the shared check-in endpoint later (UPG-02). The server
// answers a repeat with "already checked in", so replaying never double-counts.
//
// What is kept on the device, and for how long (UPG-269):
//   * per waiting scan: the ticket's own signed text, the event, the time it
//     was scanned, and an opaque key for the account that scanned it. No
//     server secret is here, and a ticket can't be verified or forged offline.
//   * per event: the registration IDs the door turns away (the entry list).
//   A scan is deleted as soon as the server gives a final answer. Signing out
//   deletes that account's waiting scans (after trying to send them, and asking
//   if some still can't be sent) and every saved entry list. Another account
//   signed in on the same device can neither see nor send them.

const DB_NAME = 'SapthaOfflineCheckin';
const DB_VERSION = 1;
const STORE_NAME = 'pending_checkins';
const CHECKIN_URL = '/ticket/api/checkin';

let dbInstance = null;
let syncing = false;

function getDB() {
    return new Promise((resolve, reject) => {
        if (dbInstance) {
            resolve(dbInstance);
            return;
        }
        const request = indexedDB.open(DB_NAME, DB_VERSION);

        request.onupgradeneeded = (e) => {
            const db = e.target.result;
            if (!db.objectStoreNames.contains(STORE_NAME)) {
                db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
            }
        };

        request.onsuccess = (e) => {
            dbInstance = e.target.result;
            resolve(dbInstance);
        };

        request.onerror = (e) => {
            reject(e.target.error);
        };
    });
}

// Run fn(store) in one transaction; resolves with its request's result
function withStore(mode, fn) {
    return getDB().then((db) => new Promise((resolve, reject) => {
        const tx = db.transaction([STORE_NAME], mode);
        const request = fn(tx.objectStore(STORE_NAME));
        tx.oncomplete = () => resolve(request ? request.result : undefined);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
    }));
}

// Queued items before UPG-02 kept the scanned text under regId
function tokenOf(item) {
    return item.token || item.regId || '';
}

// The signed-in account's opaque key, from the page (<meta name="checkin-staff">):
// null when the page has no such tag, '' when nobody is signed in.
function staffKey() {
    if (typeof document === 'undefined') return null;
    const meta = document.querySelector('meta[name="checkin-staff"]');
    return meta ? (meta.getAttribute('content') || '') : null;
}

// A waiting scan belongs to the account that made it. Scans queued before
// accounts were recorded belong to whoever is signed in.
function isMine(item) {
    const me = staffKey();
    if (me === null) return true;
    if (me === '') return false;
    return !item.staff || item.staff === me;
}

async function myPending() {
    return (await withStore('readonly', (store) => store.getAll())).filter(isMine);
}

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// The SPOC's entry list (UPG-214), kept on this device so a scan made without
// a connection can still turn away a team that isn't on it.
const ENTRY_KEY = 'sapthaEntryList:';

window.saveEntryList = function(eventId, list) {
    try {
        localStorage.setItem(ENTRY_KEY + eventId, JSON.stringify({ on: !!list.on, blocked: list.blocked || [] }));
    } catch (err) { /* storage full or off: online checks still apply */ }
};

// The registration ID a scanned ticket carries: the signed token is
// base64url(JSON [reg_id, event_id, name]) + "." + signature.
function ticketPayload(scanned) {
    let token = String(scanned || '').trim();
    const at = token.indexOf('/ticket/verify/');
    if (at !== -1) token = token.slice(at + '/ticket/verify/'.length).split(/[?#/]/)[0];
    const dot = token.lastIndexOf('.');
    if (dot <= 0 || token.startsWith('.')) return null;   // no payload, or a compressed one
    let payload = token.slice(0, dot).replace(/-/g, '+').replace(/_/g, '/');
    while (payload.length % 4) payload += '=';
    try {
        const bytes = Uint8Array.from(atob(payload), (c) => c.charCodeAt(0));
        const data = JSON.parse(new TextDecoder().decode(bytes));
        return Array.isArray(data) && data.length ? data : null;
    } catch (err) {
        return null;
    }
}

function ticketRegId(scanned) {
    const data = ticketPayload(scanned);
    return data ? String(data[0]) : '';
}

// The event a scanned ticket says it is for ('' when it can't be read offline).
// Only a hint for the person at the door: the server checks the signature.
window.offlineTicketEventId = function(scanned) {
    const data = ticketPayload(scanned);
    return data && data.length > 1 && data[1] ? String(data[1]) : '';
};

window.offlineEntryBlocked = function(scanned, eventId) {
    let list = null;
    try { list = JSON.parse(localStorage.getItem(ENTRY_KEY + eventId) || 'null'); } catch (err) { list = null; }
    if (!list || !list.on || !Array.isArray(list.blocked)) return false;
    const regId = ticketRegId(scanned);
    return !!regId && list.blocked.indexOf(regId) !== -1;
};

// Keep a scan for later; the same ticket is queued once. Answers 'queued',
// 'duplicate' (this device already holds that ticket's scan) or false.
window.queueOfflineCheckin = async function(token, eventId) {
    try {
        const pending = await myPending();
        const repeat = pending.some((item) => tokenOf(item) === token);
        if (!repeat) {
            await withStore('readwrite', (store) => store.add({
                token: token,
                eventId: eventId,
                staff: staffKey() || '',
                queuedAt: new Date().toISOString()
            }));
        }
        if (window.showToast) {
            window.showToast(repeat ? "Already scanned on this device; waiting to be sent."
                                    : "Offline: scan saved on this device.", "warning", 3000);
        }
        return repeat ? 'duplicate' : 'queued';
    } catch (err) {
        console.error("Failed to queue check-in offline:", err);
        return false;
    }
};

// Scans waiting on this device for the signed-in account
window.countOfflineCheckins = async function() {
    try {
        return (await myPending()).length;
    } catch (err) {
        return 0;
    }
};

// Scans another account left on this device: never shown, never sent from here
window.countOtherOfflineCheckins = async function() {
    try {
        const all = await withStore('readonly', (store) => store.getAll());
        return all.filter((item) => !isMine(item)).length;
    } catch (err) {
        return 0;
    }
};

window.discardOtherOfflineCheckins = async function() {
    const all = await withStore('readonly', (store) => store.getAll());
    for (const item of all.filter((row) => !isMine(row))) {
        await withStore('readwrite', (store) => store.delete(item.id));
    }
};

// Delete what this account keeps on the device: its waiting scans and every
// saved entry list. Used when signing out.
window.clearOfflineCheckinData = async function() {
    try {
        for (const item of await myPending()) {
            await withStore('readwrite', (store) => store.delete(item.id));
        }
    } catch (err) { /* nothing was stored */ }
    try {
        const keys = [];
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key && key.indexOf(ENTRY_KEY) === 0) keys.push(key);
        }
        keys.forEach((key) => localStorage.removeItem(key));
    } catch (err) { /* storage off */ }
};

// The server's final answers: the scan leaves the device once it has one
const FINAL_ANSWERS = ['success', 'already_in', 'invalid', 'wrong_event', 'transferred',
                       'cancelled', 'not_selected', 'unpaid'];

// Send this account's waiting scans. A scan leaves the device only when the
// server gives a final answer about the ticket (checked in, already in, or
// refused for a stated reason). It stays after a network error, an expired
// login or page (401, a refused form token), a server error, or "you're not on
// this event's staff" (the organiser can fix that), to be tried again.
// The summary's `results` lists each answer, for the scanner to show.
window.syncOfflineCheckins = async function() {
    const summary = { sent: 0, alreadyIn: 0, refused: 0, kept: 0, results: [] };
    if (!navigator.onLine || syncing) return summary;
    syncing = true;
    try {
        const pending = await myPending();
        if (pending.length === 0) return summary;
        if (window.showToast) {
            window.showToast(`Sending ${pending.length} offline scans...`, "info", 2000);
        }

        for (let i = 0; i < pending.length; i++) {
            const item = pending[i];
            let resp, data;
            try {
                resp = await fetch(CHECKIN_URL, {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken() },
                    body: JSON.stringify({ token: tokenOf(item), event_id: item.eventId, source: 'offline queue',
                                           scanned_at: item.queuedAt || '' })
                });
                data = await resp.json().catch(() => ({}));
            } catch (fetchErr) {
                summary.kept += pending.length - i;  // offline again: this one and the rest wait
                break;
            }
            if (FINAL_ANSWERS.indexOf(data.status) === -1) {
                summary.kept += 1;
                summary.results.push({ status: 'kept', name: '', team: '',
                                       message: data.message || 'Not sent yet; it will be tried again.' });
                continue;
            }
            await withStore('readwrite', (store) => store.delete(item.id));
            if (data.status === 'success') summary.sent += 1;
            else if (data.status === 'already_in') summary.alreadyIn += 1;
            else summary.refused += 1;
            summary.results.push({ status: data.status, name: data.name || '', team: data.team || '',
                                   message: data.message || '' });
        }

        if (window.showToast) {
            window.showToast(`Offline scans: ${summary.sent} checked in, ${summary.alreadyIn} already in, ` +
                             `${summary.refused} refused, ${summary.kept} still waiting.`,
                             summary.refused || summary.kept ? "warning" : "success", 4000);
        }
        window.dispatchEvent(new CustomEvent('offline-checkins-synced', { detail: summary }));
        return summary;
    } catch (err) {
        console.error("Error in syncOfflineCheckins:", err);
        return summary;
    } finally {
        syncing = false;
    }
};

// Signing out: send what is waiting, then delete what this account kept here.
// If some scans still can't be sent, ask first: deleting them means those
// people are not checked in.
async function signOut(href) {
    let left = await window.countOfflineCheckins();
    if (left && navigator.onLine) {
        await window.syncOfflineCheckins();
        left = await window.countOfflineCheckins();
    }
    if (left && !window.confirm(`${left} check-in scan${left === 1 ? '' : 's'} saved on this device ` +
            `${left === 1 ? "hasn't" : "haven't"} reached the server. Signing out deletes ` +
            `${left === 1 ? 'it' : 'them'}, and ${left === 1 ? 'that person' : 'those people'} will not be ` +
            'checked in. Sign out anyway?')) {
        return false;
    }
    await window.clearOfflineCheckinData();
    window.location.href = href;
    return true;
}
window.signOutClearingOfflineData = signOut;

if (typeof document !== 'undefined' && typeof document.addEventListener === 'function') {
    document.addEventListener('click', (event) => {
        const link = event.target && event.target.closest ? event.target.closest('a[href]') : null;
        if (!link) return;
        const path = (link.getAttribute('href') || '').split(/[?#]/)[0];
        if (path !== '/logout' && path !== '/auth/logout') return;
        event.preventDefault();
        signOut(link.getAttribute('href'));
    });
}

// Send as soon as the connection comes back, and shortly after each page load
window.addEventListener('online', window.syncOfflineCheckins);
window.addEventListener('load', () => {
    if (navigator.onLine) {
        setTimeout(window.syncOfflineCheckins, 3000);
    }
});
