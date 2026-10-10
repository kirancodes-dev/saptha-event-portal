/* Moved unchanged from an inline <script> in templates/public/leaderboard.html so the CSP
   needs no inline script (UPG-25). */
async function refresh() {
  try {
    const res  = await fetch(window.location.href, {
      headers: { 'Accept': 'application/json' }
    });
    const data = await res.json();
    // Simple auto-reload approach — full page refresh every 15s
    document.getElementById('updated-ts').textContent =
      'Last updated: ' + new Date().toLocaleTimeString([], {hour:'2-digit', minute:'2-digit', second:'2-digit'});
  } catch(e){}
}
// Full reload every 15 seconds for simplicity — projector use
setTimeout(() => window.location.reload(), 15000);
document.getElementById('updated-ts').textContent =
  'Auto-refreshes every 15 seconds · ' + new Date().toLocaleTimeString();
