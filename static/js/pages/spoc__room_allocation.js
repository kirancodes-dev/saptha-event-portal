/* Moved unchanged from an inline <script> in templates/spoc/room_allocation.html so the CSP
   needs no inline script (UPG-25). */
const CSRF = document.querySelector('meta[name="csrf-token"]').content;

function reassignRoom(sel) {
  const regId   = sel.dataset.reg;
  const eventId = sel.dataset.event;
  const room    = sel.value;
  const orig    = sel.getAttribute('data-orig') || '';

  fetch(`/spoc/reassign_room/${eventId}/${regId}`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': CSRF},
    body: JSON.stringify({room: room}),
  })
  .then(r => r.json())
  .then(data => {
    if (data.status === 'ok') {
      sel.style.background = '#f0fdf4';
      sel.style.borderColor = '#86efac';
      setTimeout(() => { sel.style.background = '#f8fafc'; sel.style.borderColor = '#e2e8f0'; }, 1800);
      // Update search data
      const row = sel.closest('tr');
      const cur = row.dataset.search || '';
      row.dataset.search = cur.replace(orig, room);
      sel.setAttribute('data-orig', room);
    } else {
      alert('Error: ' + (data.message || 'unknown'));
      sel.value = orig;
    }
  })
  .catch(() => { alert('Network error. Try again.'); sel.value = orig; });
}

function filterTable() {
  const q = document.getElementById('searchBox').value.toLowerCase();
  document.querySelectorAll('#allocBody tr').forEach(row => {
    row.style.display = (!q || (row.dataset.search || '').includes(q)) ? '' : 'none';
  });
}
