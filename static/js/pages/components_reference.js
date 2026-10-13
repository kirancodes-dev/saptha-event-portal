/* Moved unchanged from an inline <script> in templates/components_reference.html so the CSP
   needs no inline script (UPG-25). */
        function copyHex(hex) {
            navigator.clipboard.writeText(hex).then(() => {
                showToast(`Copied ${hex} to clipboard!`, 'info', 2000);
            });
        }

        function triggerDemoToast() {
            showToast('Form validated and submitted successfully!', 'success', 3000);
            const announcer = document.getElementById('a11y-announcer');
            if (announcer) announcer.textContent = 'Form submitted successfully.';
        }
    
