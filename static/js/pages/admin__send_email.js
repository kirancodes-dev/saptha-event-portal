/* Moved unchanged from an inline <script> in templates/admin/send_email.html so the CSP
   needs no inline script (UPG-25). */
    // Show/hide audience sub-pickers
    document.querySelectorAll('input[name="audience"]').forEach(function(radio) {
        radio.addEventListener('change', function() {
            document.getElementById('eventPicker').style.display =
                this.value === 'event_regs' ? 'block' : 'none';
            document.getElementById('rolePicker').style.display =
                this.value === 'role_filter' ? 'block' : 'none';
        });
    });

    // Live message preview + char counter
    const msgBody   = document.getElementById('msgBody');
    const preview   = document.getElementById('previewText');
    const charCount = document.getElementById('charCount');

    msgBody.addEventListener('input', function() {
        preview.textContent  = this.value || 'Your message will appear here…';
        charCount.textContent = this.value.length + ' characters';
    });

    // Confirm before sending to all
    document.getElementById('emailForm').addEventListener('submit', function(e) {
        const audience = document.querySelector('input[name="audience"]:checked').value;
        const label    = audience === 'all_users'   ? 'ALL users in the system'
                       : audience === 'event_regs'  ? 'all registrants of the selected event'
                       : 'all users with the selected role';
        if (!confirm('Send "' + document.querySelector('[name=subject]').value + '" to ' + label + '?')) {
            e.preventDefault();
        } else {
            document.getElementById('sendBtn').innerHTML =
                '<i class="fas fa-spinner fa-spin me-2"></i> Sending…';
            document.getElementById('sendBtn').disabled = true;
        }
    });
