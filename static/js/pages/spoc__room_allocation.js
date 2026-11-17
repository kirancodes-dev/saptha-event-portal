/* The room allocation page (UPG-306). A change of room is saved to the SPOC's
   draft only; the room cards' counts follow. Kept out of the template so the
   CSP needs no inline script (UPG-25). */
const CSRF = document.querySelector('meta[name="csrf-token"]').content;

function _roomCounts(data) {
  (data.rooms || []).forEach(r => {
    document.querySelectorAll('[data-room-card]').forEach(card => {
      if (card.dataset.roomCard !== r.name) return;
      card.querySelector('[data-room-people]').textContent = r.people;
      card.querySelector('[data-room-teams]').textContent = r.teams;
      card.classList.toggle('over', !!r.over);
    });
  });
  const none = document.querySelector('[data-room-unallocated]');
  if (none && data.unallocated !== undefined) none.textContent = data.unallocated;
}

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
      const row = sel.closest('tr');
      const cur = row.dataset.search || '';
      row.dataset.search = orig ? cur.replace(orig.toLowerCase(), room.toLowerCase()) : cur + ' ' + room.toLowerCase();
      sel.setAttribute('data-orig', room);
      _roomCounts(data);
    } else {
      alert('Error: ' + (data.message || 'unknown'));
      sel.value = orig;
    }
  })
  .catch(() => { alert('Network error. Try again.'); sel.value = orig; });
}

function addRoomRow() {
  const blank = document.querySelector('[data-room-blank]');
  const row = blank.cloneNode(true);
  row.querySelectorAll('input').forEach(i => { i.value = ''; });
  blank.parentNode.appendChild(row);
  row.querySelector('input').focus();
}

function filterTable() {
  const q = document.getElementById('searchBox').value.toLowerCase();
  document.querySelectorAll('#allocBody tr').forEach(row => {
    row.style.display = (!q || (row.dataset.search || '').includes(q)) ? '' : 'none';
  });
}
