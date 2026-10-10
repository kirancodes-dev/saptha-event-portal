/* Moved unchanged from an inline <script> in templates/spoc/edit_event.html so the CSP
   needs no inline script (UPG-25). */
    function toggleAIGenerator() {
        var card = document.getElementById('ai-generator-card');
        if (card) {
            card.classList.toggle('d-none');
        }
    }

    function generateEventOutline() {
        var titleInput = document.getElementById('event-title-input');
        var promptInput = document.getElementById('ai-prompt-input');
        var submitBtn = document.getElementById('ai-gen-submit-btn');
        
        var title = titleInput ? titleInput.value.trim() : '';
        var prompt = promptInput ? promptInput.value.trim() : '';
        
        if (!title) {
            showToast('Please enter an Event Title first!', 'error');
            return;
        }
        
        var oldHtml = submitBtn.innerHTML;
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        
        var csrfToken = document.querySelector('input[name="csrf_token"]').value;
        
        fetch('/spoc/marketing/event_writer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ title: title, prompt: prompt })
        })
        .then(function(r) { return r.json(); })
        .then(function(data) {
            if (data.description && data.rules) {
                var descArea = document.querySelector('textarea[name="description"]');
                var rulesArea = document.querySelector('textarea[name="rules"]');
                if (descArea) descArea.value = data.description;
                if (rulesArea) rulesArea.value = data.rules;
                
                showToast('Event details generated successfully!', 'success');
                toggleAIGenerator();
            } else {
                showToast(data.error || 'Failed to generate details', 'error');
            }
        })
        .catch(function() {
            showToast('Network error generating details', 'error');
        })
        .finally(function() {
            submitBtn.disabled = false;
            submitBtn.innerHTML = oldHtml;
        });
    }
