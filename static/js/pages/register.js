/* Moved unchanged from an inline <script> in templates/register.html so the CSP
   needs no inline script (UPG-25). */
        // ── SKELETON LOADER INITIALIZATION ────
        document.addEventListener('DOMContentLoaded', function(){
            setTimeout(function(){
                const skeleton = document.getElementById('formSkeleton');
                const form = document.getElementById('main-content');
                if(skeleton) skeleton.style.display = 'none';
                if(form) form.style.display = '';
            }, 250);
        });

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
    
