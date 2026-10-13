// tests/js/offline_sync_harness.js — runs static/js/offline-sync.js in Node
// against a live copy of the app (tests/test_checkin_unified.py, UPG-02).
//
// stdin: the scanned tokens to queue, one per line (duplicates allowed).
// env:   BASE_URL, LOGIN_EMAIL, LOGIN_PASSWORD, LOGIN_ROLE, EVENT_ID.
// stdout: key=value lines the test reads.
'use strict';
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const BASE = process.env.BASE_URL;
const CHECKIN = '/ticket/api/checkin';

// ── A minimal IndexedDB: one database, object stores with auto-increment keys ──
function makeIndexedDB() {
  const stores = {};
  let created = false;
  const db = {
    objectStoreNames: { contains: (name) => name in stores },
    createObjectStore(name, opts) {
      stores[name] = { keyPath: opts.keyPath, next: 1, rows: new Map() };
    },
    transaction(names, mode) {
      const ops = [];
      const tx = {
        objectStore(name) {
          const st = stores[name];
          const op = (fn) => { const request = {}; ops.push(() => { request.result = fn(); }); return request; };
          return {
            getAll: () => op(() => [...st.rows.values()].map((row) => ({ ...row }))),
            count: () => op(() => st.rows.size),
            add: (value) => op(() => {
              if (mode !== 'readwrite') throw new Error('read-only transaction');
              const key = st.next++;
              st.rows.set(key, { ...value, [st.keyPath]: key });
              return key;
            }),
            delete: (key) => op(() => {
              if (mode !== 'readwrite') throw new Error('read-only transaction');
              st.rows.delete(key);
            }),
          };
        },
      };
      setTimeout(() => { ops.forEach((run) => run()); if (tx.oncomplete) tx.oncomplete(); }, 0);
      return tx;
    },
  };
  return {
    open() {
      const request = {};
      setTimeout(() => {
        request.result = db;
        if (!created) {
          created = true;
          if (request.onupgradeneeded) request.onupgradeneeded({ target: request });
        }
        if (request.onsuccess) request.onsuccess({ target: request });
      }, 0);
      return request;
    },
  };
}

// ── fetch against the live app, with the staff member's session cookie ──
let cookie = '';
let posts = 0;
let unreachable = false;

async function appFetch(url, opts = {}) {
  if (unreachable) throw new TypeError('Failed to fetch');
  if (url === CHECKIN) posts += 1;
  const headers = { ...(opts.headers || {}), ...(cookie ? { Cookie: cookie } : {}) };
  return fetch(BASE + url, { method: opts.method, body: opts.body, headers, redirect: 'manual' });
}

async function logIn() {
  const resp = await fetch(BASE + '/login', {
    method: 'POST',
    redirect: 'manual',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      role: process.env.LOGIN_ROLE, email: process.env.LOGIN_EMAIL, password: process.env.LOGIN_PASSWORD,
    }).toString(),
  });
  cookie = resp.headers.getSetCookie().map((c) => c.split(';')[0]).join('; ');
  if (resp.status !== 302 || (resp.headers.get('location') || '').endsWith('/login') || !cookie) {
    throw new Error(`login failed: ${resp.status} ${resp.headers.get('location')}`);
  }
}

async function main() {
  const tokens = fs.readFileSync(0, 'utf8').split('\n').map((t) => t.trim()).filter(Boolean);
  const window = new EventTarget();
  const context = vm.createContext({
    window,
    document: { querySelector: () => null },
    navigator: { onLine: true },
    indexedDB: makeIndexedDB(),
    fetch: appFetch,
    console,
    setTimeout,
    CustomEvent,
  });
  const source = fs.readFileSync(path.join(__dirname, '..', '..', 'static', 'js', 'offline-sync.js'), 'utf8');
  vm.runInContext(source, context, { filename: 'offline-sync.js' });
  const queue = (token) => window.queueOfflineCheckin(token, process.env.EVENT_ID);
  const fmt = (s) => `sent:${s.sent},alreadyIn:${s.alreadyIn},refused:${s.refused},kept:${s.kept}`;

  await logIn();

  // Scans made offline, one ticket scanned twice
  for (const token of tokens) await queue(token);
  console.log(`queued_first=${await window.countOfflineCheckins()}`);
  const first = await window.syncOfflineCheckins();
  console.log(`posts_first=${posts}`);
  console.log(`first=${fmt(first)}`);
  console.log(`left_first=${await window.countOfflineCheckins()}`);

  // The same queue again (e.g. a second device's copy): nothing changes
  for (const token of new Set(tokens)) await queue(token);
  const second = await window.syncOfflineCheckins();
  console.log(`second=${fmt(second)}`);
  console.log(`left_second=${await window.countOfflineCheckins()}`);

  // A scan made while the server can't be reached stays queued
  await queue(tokens[0]);
  unreachable = true;
  await window.syncOfflineCheckins();
  console.log(`offline_kept=${await window.countOfflineCheckins()}`);
}

main().catch((err) => { console.error(err && err.stack || err); process.exit(1); });
