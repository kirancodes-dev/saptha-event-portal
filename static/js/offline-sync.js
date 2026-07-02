// static/js/offline-sync.js — IndexedDB Offline Synchronization Engine

const DB_NAME = 'SapthaOfflineCheckin';
const DB_VERSION = 1;
const STORE_NAME = 'pending_checkins';

let dbInstance = null;

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

// Queue check-in offline
window.queueOfflineCheckin = async function(regId, eventId, round = 1) {
    try {
        const db = await getDB();
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        
        const checkinData = {
            regId: regId,
            eventId: eventId,
            round: round,
            timestamp: new Date().toISOString()
        };

        store.add(checkinData);
        console.log("Check-in queued offline successfully:", checkinData);
        if (window.showToast) {
            window.showToast("Offline mode: Check-in saved locally.", "warning", 3000);
        }
        return true;
    } catch (err) {
        console.error("Failed to queue check-in offline:", err);
        return false;
    }
};

// Sync queued check-ins to server
window.syncOfflineCheckins = async function() {
    if (!navigator.onLine) return;
    
    try {
        const db = await getDB();
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        
        const request = store.getAll();
        
        request.onsuccess = async (e) => {
            const list = e.target.result;
            if (list.length === 0) return;
            
            console.log(`Found ${list.length} offline check-ins to sync...`);
            if (window.showToast) {
                window.showToast(`Syncing ${list.length} offline check-ins...`, "info", 2000);
            }

            for (const item of list) {
                try {
                    const resp = await fetch(`/checkin/kiosk/confirm/${item.regId}`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            event_id: item.eventId,
                            round: item.round,
                            offline_time: item.timestamp
                        })
                    });
                    
                    if (resp.ok) {
                        // Success -> remove from store
                        const deleteTx = db.transaction([STORE_NAME], 'readwrite');
                        deleteTx.objectStore(STORE_NAME).delete(item.id);
                        console.log(`Synced & deleted offline check-in ID: ${item.id}`);
                    }
                } catch (fetchErr) {
                    console.error("Failed to sync item:", item, fetchErr);
                }
            }
            
            if (window.showToast) {
                window.showToast("Offline check-ins synced successfully!", "success", 3000);
            }
        };
    } catch (err) {
        console.error("Error in syncOfflineCheckins:", err);
    }
};

// Auto-sync when system changes online state
window.addEventListener('online', window.syncOfflineCheckins);

// Check immediately on load if online
window.addEventListener('load', () => {
    if (navigator.onLine) {
        setTimeout(window.syncOfflineCheckins, 3000);
    }
});
