// static/js/offline-sync.js — scans made without a connection wait in IndexedDB
// and are sent to the shared check-in endpoint later (UPG-02). The server
// answers a repeat with "already checked in", so replaying never double-counts.

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

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
}

// Keep a scan for later; the same ticket is queued once
window.queueOfflineCheckin = async function(token, eventId) {
    try {
        const pending = await withStore('readonly', (store) => store.getAll());
        if (!pending.some((item) => tokenOf(item) === token)) {
            await withStore('readwrite', (store) => store.add({
                token: token,
                eventId: eventId,
                queuedAt: new Date().toISOString()
            }));
        }
        if (window.showToast) {
            window.showToast("Offline: scan saved on this device.", "warning", 3000);
        }
        return true;
    } catch (err) {
        console.error("Failed to queue check-in offline:", err);
        return false;
    }
};

window.countOfflineCheckins = async function() {
    try {
        return await withStore('readonly', (store) => store.count());
    } catch (err) {
        return 0;
    }
};

// Send queued scans. An item leaves the queue once the server has given a
// final answer (checked in, already in, or refused); it stays after a network
// error, an expired login (401) or a server error (5xx), to be tried again.
window.syncOfflineCheckins = async function() {
    const summary = { sent: 0, alreadyIn: 0, refused: 0, kept: 0 };
    if (!navigator.onLine || syncing) return summary;
    syncing = true;
    try {
        const pending = await withStore('readonly', (store) => store.getAll());
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
                    body: JSON.stringify({ token: tokenOf(item), event_id: item.eventId, source: 'offline queue' })
                });
                data = await resp.json().catch(() => ({}));
            } catch (fetchErr) {
                summary.kept += pending.length - i;  // offline again: this one and the rest wait
                break;
            }
            if (resp.status === 401 || resp.status >= 500) {
                summary.kept += 1;
                continue;
            }
            await withStore('readwrite', (store) => store.delete(item.id));
            if (data.status === 'success') summary.sent += 1;
            else if (data.status === 'already_in') summary.alreadyIn += 1;
            else summary.refused += 1;
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

// Send as soon as the connection comes back, and shortly after each page load
window.addEventListener('online', window.syncOfflineCheckins);
window.addEventListener('load', () => {
    if (navigator.onLine) {
        setTimeout(window.syncOfflineCheckins, 3000);
    }
});
