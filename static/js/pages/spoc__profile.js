/* Moved unchanged from an inline <script> in templates/spoc/profile.html so the CSP
   needs no inline script (UPG-25). */
fetch('/spoc/api/stats')
  .then(function(r) { return r.ok ? r.json() : null; })
  .then(function(d) {
    if (!d) return;
    document.getElementById('prof-total-events').textContent = d.total_events;
    document.getElementById('prof-total-regs').textContent   = d.total_regs;
    document.getElementById('prof-present').textContent      = d.present_count;
  })
  .catch(function() {});
