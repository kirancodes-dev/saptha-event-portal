/* Moved unchanged from an inline <script> in templates/public/registration_form.html so the CSP
   needs no inline script (UPG-25). */
document.getElementById('reg-form') &&
document.getElementById('reg-form').addEventListener('submit', function(e) {
  // Client-side: mark required radio groups
  let ok = true;
  this.querySelectorAll('[data-required-radio]').forEach(function(grp) {
    const name = grp.dataset.requiredRadio;
    if (!document.querySelector('[name="'+name+'"]:checked')) {
      grp.style.borderColor = '#ef4444';
      ok = false;
    }
  });
  if (!ok) {
    e.preventDefault();
    if (typeof showToast === 'function') showToast('Please answer all required questions.', 'warning', 4000);
    return;
  }
  const btn = document.getElementById('submit-btn');
  if (btn) {
    btn.disabled = true;
    btn.innerHTML = '<span class="sp-spinner"></span> Submitting…';
  }
});

// Highlight selected radio/checkbox visually
document.querySelectorAll('.choice-item input').forEach(function(inp) {
  inp.addEventListener('change', function() {
    if (this.type === 'radio') {
      document.querySelectorAll('[name="'+this.name+'"]').forEach(function(r) {
        r.closest('.choice-item').style.borderColor = '';
      });
    }
    this.closest('.choice-item').style.borderColor = 'var(--orange)';
  });
});
