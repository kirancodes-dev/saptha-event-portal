/* Moved unchanged from an inline <script> in templates/login.html so the CSP
   needs no inline script (UPG-25). */
        // ── SKELETON LOADER ────
        document.addEventListener('DOMContentLoaded', function(){
            setTimeout(function(){
                const skeleton = document.getElementById('formSkeleton');
                const form = document.getElementById('main-content');
                if(skeleton) skeleton.style.display = 'none';
                if(form) form.style.display = '';
            }, 250);
        });

        // ── PWA modal logic (mirrors mobile_nav.html) ────
            const isIOS      = /iPad|iPhone|iPod/.test(navigator.userAgent);
            const isAndroid  = /Android/.test(navigator.userAgent);
            const isChrome   = /Chrome/.test(navigator.userAgent) && !/Edg/.test(navigator.userAgent);
            const isSafari   = /Safari/.test(navigator.userAgent) && !isChrome;
            const isInstalled = window.matchMedia('(display-mode: standalone)').matches
                             || navigator.standalone
                             || localStorage.getItem('pwa_installed') === '1';

            window.showPwaInstallModal = function() {
                const modal = document.getElementById('pwaInstallModal');
                const sheet = document.getElementById('pwaModalSheet');
                const androidSec = document.getElementById('pwaAndroidSection');
                const iosSec     = document.getElementById('pwaIosSection');
                const chromeFb   = document.getElementById('pwaChromeFallback');
                if (isIOS || isSafari) {
                    androidSec.style.display = 'none'; iosSec.style.display = 'block';
                } else if (window.__pwaPrompt) {
                    androidSec.style.display = 'block'; iosSec.style.display = 'none';
                } else {
                    androidSec.style.display = 'none'; iosSec.style.display = 'block';
                    if (isAndroid && chromeFb) chromeFb.style.display = 'flex';
                }
                modal.style.display = 'flex';
                requestAnimationFrame(() => requestAnimationFrame(() => { sheet.style.transform = 'translateY(0)'; }));
            };
            window.closePwaModal = function() {
                const sheet = document.getElementById('pwaModalSheet');
                const modal = document.getElementById('pwaInstallModal');
                sheet.style.transform = 'translateY(100%)';
                setTimeout(() => { modal.style.display = 'none'; }, 350);
            };
            window.triggerNativeInstall = async function() {
                if (!window.__pwaPrompt) {
                    document.getElementById('pwaAndroidSection').style.display = 'none';
                    document.getElementById('pwaIosSection').style.display = 'block';
                    const fb = document.getElementById('pwaChromeFallback');
                    if (fb) fb.style.display = 'flex';
                    return;
                }
                window.__pwaPrompt.prompt();
                const { outcome } = await window.__pwaPrompt.userChoice;
                window.__pwaPrompt = null;
                window.closePwaModal();
                if (outcome === 'accepted') localStorage.setItem('pwa_banner_dismissed','1');
            };

            window.addEventListener('beforeinstallprompt', (e) => {
                e.preventDefault();
                window.__pwaPrompt = e;
            });

            // Hide install button if already installed and no update is pending
            if (isInstalled && !window.pwaUpdateAvailable) {
                const b = document.getElementById('loginInstallBtn');
                if (b) b.style.display = 'none';
            }

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

        // ── ROLE SELECTION HANDLER ────
        document.getElementById('roleSelect').addEventListener('change', function() {
            const secretDiv   = document.getElementById('secretKeyDiv');
            const secretInput = document.getElementById('secretKeyInput');
            const forgotWrap  = document.getElementById('forgotPasswordWrap');

            if (this.value === 'SuperAdmin') {
                secretDiv.classList.add('show');
                if (forgotWrap) forgotWrap.style.display = 'none';
                document.body.classList.add('super-admin-selected');
            } else {
                secretDiv.classList.remove('show');
                secretInput.value = '';
                if (forgotWrap) forgotWrap.style.display = '';
                document.body.classList.remove('super-admin-selected');
            }
        });
    
