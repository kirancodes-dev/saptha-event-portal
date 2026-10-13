/* Moved unchanged from an inline <script> in templates/spoc/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// ── EMAIL BROADCAST (BLAST) CONTROLS ──
function openBlastModal(eventId, eventTitle) {
  document.getElementById('blastForm').action = '/spoc/blast_email/' + eventId;
  document.getElementById('blastEventName').textContent = eventTitle;
  openModal('blastModal');
}
function closeBlastModal() {
  closeModal('blastModal');
  document.getElementById('blastForm').reset();
}
function previewBlastEmail() {
  const form = document.getElementById('blastForm');
  const actionParts = form.action.split('/');
  const eventId = actionParts[actionParts.length - 1];
  const subject = form.querySelector('input[name="subject"]').value.trim();
  const body = form.querySelector('textarea[name="body"]').value.trim();
  
  if (!subject || !body) {
    showToast("Subject and Message body are required for preview.", "error");
    return;
  }
  
  fetch('/spoc/blast_preview/' + eventId, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': CSRF_TOKEN || ''
    },
    body: JSON.stringify({ subject: subject, body: body })
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.html) {
      const iframe = document.getElementById('blastPreviewIframe');
      iframe.srcdoc = data.html;
      openModal('blastPreviewModal');
    } else {
      showToast("Error generating preview: " + (data.error || "unknown error"), "error");
    }
  })
  .catch(err => {
    showToast("Network error. Could not load preview.", "error");
  });
}

function generateAICopy() {
  const promptInput = document.getElementById('ai-copy-prompt');
  const prompt = promptInput.value.trim();
  const form = document.getElementById('blastForm');
  const actionParts = form.action.split('/');
  const eventId = actionParts[actionParts.length - 1];

  if (!prompt) {
    showToast("Please enter a copywriting prompt description.", "error");
    return;
  }

  const btn = document.querySelector('button[onclick="generateAICopy()"]');
  const oldHtml = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';

  fetch('/spoc/marketing/copywriter', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRFToken': CSRF_TOKEN || ''
    },
    body: JSON.stringify({ prompt: prompt, event_id: eventId })
  })
  .then(resp => resp.json())
  .then(data => {
    if (data.subject && data.body) {
      document.getElementById('blast-subject-input').value = data.subject;
      document.getElementById('blast-body-input').value = data.body;
      promptInput.value = '';
      showToast("AI copy generated successfully!", "success");
    } else {
      showToast("Error: " + (data.error || "failed to generate"), "error");
    }
  })
  .catch(err => {
    showToast("Network error.", "error");
  })
  .finally(() => {
    btn.disabled = false;
    btn.innerHTML = oldHtml;
  });
}
