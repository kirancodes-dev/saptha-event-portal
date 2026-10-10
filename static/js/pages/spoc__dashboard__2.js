/* Moved unchanged from an inline <script> in templates/spoc/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// ── END EVENT & CERT SELECTOR MODAL CONFIG ──
const CERT_TEMPLATES = {
  1: { name: 'Classic Navy', desc: 'Navy & orange themed standard design.', primary: '#0d2d62', accent: '#f37021' },
  2: { name: 'Tech Blue', desc: 'Dark slate & cyan themed tech design.', primary: '#0f172a', accent: '#06b6d4' },
  3: { name: 'Cultural Gold', desc: 'Maroon & amber gold themed cultural design.', primary: '#7f1d1d', accent: '#d97706' },
  4: { name: 'Sports Green', desc: 'Forest & emerald green sports design.', primary: '#14532d', accent: '#16a34a' },
  5: { name: 'Management Purple', desc: 'Deep purple & violet business design.', primary: '#3b0764', accent: '#7c3aed' }
};

let currentTargetEventId = null;

function confirmEndEvent(eventId, eventTitle) {
  currentTargetEventId = eventId;
  document.getElementById('modalEventTitle').textContent = eventTitle;
  document.getElementById('previewEventTitle').textContent = eventTitle;
  document.getElementById('certSignatoryInput').value = "Dean of Student Affairs";
  document.getElementById('certTemplateSelect').value = "1";
  updateCertPreview();
  openModal('endEventModal');
}

function updateCertPreview() {
  const tId = document.getElementById('certTemplateSelect').value;
  const signatory = document.getElementById('certSignatoryInput').value.trim() || 'Dean of Student Affairs';
  const theme = CERT_TEMPLATES[tId] || CERT_TEMPLATES[1];
  
  document.getElementById('certTemplateDesc').textContent = theme.desc;
  document.getElementById('previewIssuedBy').textContent = signatory;
  
  const card = document.getElementById('certPreviewCard');
  card.style.borderColor = theme.primary;
  
  const cornerTL = document.getElementById('certCornerTL');
  cornerTL.style.background = `linear-gradient(135deg, ${theme.primary} 50%, transparent 50%)`;
  
  const cornerBR = document.getElementById('certCornerBR');
  cornerBR.style.background = `linear-gradient(-45deg, ${theme.primary} 50%, transparent 50%)`;
  
  document.getElementById('previewCertType').style.color = theme.primary;
  document.getElementById('previewEventTitle').style.color = theme.primary;
}

function submitEndEvent() {
  if (!currentTargetEventId) return;
  const tId = document.getElementById('certTemplateSelect').value;
  const signatory = document.getElementById('certSignatoryInput').value.trim() || 'Dean of Student Affairs';
  
  document.getElementById('end-event-template-id').value = tId;
  document.getElementById('end-event-issued-by').value = signatory;
  
  const form = document.getElementById('end-event-form');
  form.action = '/spoc/end_event/' + currentTargetEventId;
  
  closeModal('endEventModal');
  form.submit();
}

// Modal helper controls
function openModal(id) {
  var m = document.getElementById(id);
  if (m) { m.classList.add('open'); m.style.display = 'flex'; }
}
function closeModal(id) {
  var m = document.getElementById(id);
  if (m) { m.classList.remove('open'); m.style.display = 'none'; }
}
document.addEventListener('click', function(e) {
  if (e.target.classList.contains('spoc-modal')) closeModal(e.target.id);
});

// Dynamic room row adder
function addRoomRow(eventId) {
  var container = document.getElementById('roomRows-' + eventId);
  var row = document.createElement('div');
  row.className = 'room-row';
  row.style.cssText = 'display:grid;grid-template-columns:1fr 90px 32px;gap:8px;margin-bottom:8px;';
  row.innerHTML = '<input type="text" name="room_name[]" placeholder="Room / Hall name" required class="form-control">'
    + '<input type="number" name="capacity[]" placeholder="Capacity" required min="1" class="form-control">'
    + '<button type="button" data-h-click="se:remove-closest" data-closest=".room-row" style="background:#dc2626;color:#fff;border:none;border-radius:7px;font-size:14px;cursor:pointer;">&times;</button>';
  container.appendChild(row);
}
