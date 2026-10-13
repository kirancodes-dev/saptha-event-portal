/* Moved unchanged from an inline <script> in templates/reset_password.html so the CSP
   needs no inline script (UPG-25). */
        // ── PASSWORD TOGGLE ────
        function spTogglePw(id, btn) {
            const inp = document.getElementById(id);
            const icon = btn.querySelector('i');
            if (inp.type === 'password') {
                inp.type = 'text';
                icon.classList.replace('fa-eye', 'fa-eye-slash');
            } else {
                inp.type = 'password';
                icon.classList.replace('fa-eye-slash', 'fa-eye');
            }
        }
    
