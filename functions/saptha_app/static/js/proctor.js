/**
 * SapthaEvent Proctoring & Anti-Cheat Engine (proctor.js)
 * Enterprise-grade client guard for online exams and competitive assessments.
 */
(function() {
    'use strict';

    const ProctorGuard = {
        eventId: null,
        violationCount: 0,
        maxViolations: 5,
        isActive: false,

        init(config) {
            this.eventId = config.eventId || '';
            this.maxViolations = config.maxViolations || 5;
            this.isActive = true;

            this.bindEvents();
            console.log('[ProctorGuard] Real-time anti-cheat monitoring initialized for event:', this.eventId);
        },

        bindEvents() {
            // 1. Tab Switching & Page Visibility
            document.addEventListener('visibilitychange', () => {
                if (document.hidden && this.isActive) {
                    this.logViolation('TAB_SWITCH', 'Candidate switched browser tab or minimized window');
                }
            });

            // 2. Window Blur / Focus Loss
            window.addEventListener('blur', () => {
                if (this.isActive) {
                    this.logViolation('WINDOW_BLUR', 'Candidate lost browser focus');
                }
            });

            // 3. Right-Click Context Menu Prevention
            document.addEventListener('contextmenu', (e) => {
                e.preventDefault();
                this.showToast('Right-click context menu is disabled during exams.', 'warning');
            });

            // 4. Disable Copy, Cut, Paste
            ['copy', 'cut', 'paste'].forEach(eventType => {
                document.addEventListener(eventType, (e) => {
                    e.preventDefault();
                    this.logViolation('COPY_PASTE_ATTEMPT', `Attempted to ${eventType} text`);
                });
            });

            // 5. Intercept DevTools & Inspection Shortcuts
            document.addEventListener('keydown', (e) => {
                if (!this.isActive) return;

                // F12 key
                if (e.key === 'F12') {
                    e.preventDefault();
                    this.logViolation('DEVTOOLS_KEY', 'Attempted F12 inspect shortcut');
                }
                // Ctrl+Shift+I / Cmd+Opt+I (Developer Tools)
                if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'I' || e.key === 'i' || e.key === 'C' || e.key === 'c')) {
                    e.preventDefault();
                    this.logViolation('DEVTOOLS_KEY', 'Attempted inspect shortcut');
                }
                // Ctrl+U / Cmd+U (View Source)
                if ((e.ctrlKey || e.metaKey) && (e.key === 'U' || e.key === 'u')) {
                    e.preventDefault();
                    this.logViolation('VIEW_SOURCE', 'Attempted view source shortcut');
                }
            });
        },

        logViolation(type, detail) {
            this.violationCount++;
            this.updateBadgeUI();

            this.showToast(`⚠️ Warning (${this.violationCount}/${this.maxViolations}): ${detail}`, 'danger');

            // Send violation log to server
            fetch('/api/proctor/log_violation', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    event_id: this.eventId,
                    violation_type: type,
                    detail: detail,
                    timestamp: new Date().toISOString()
                })
            }).catch(err => console.error('[ProctorGuard] Failed to log violation to server:', err));

            if (this.violationCount >= this.maxViolations) {
                this.isActive = false;
                alert(`🚨 Maximum proctoring violations reached (${this.maxViolations}). Your exam will now be force-submitted.`);
                const examForm = document.getElementById('examForm');
                if (examForm) {
                    examForm.submit();
                }
            }
        },

        updateBadgeUI() {
            const badge = document.getElementById('proctorViolationBadge');
            if (badge) {
                badge.textContent = `${this.violationCount} / ${this.maxViolations} Warnings`;
                badge.className = `badge ${this.violationCount > 2 ? 'bg-danger' : 'bg-warning'} px-3 py-2 fs-6`;
            }
        },

        showToast(message, type = 'warning') {
            const container = document.getElementById('proctorToastContainer') || this.createToastContainer();
            const toast = document.createElement('div');
            toast.className = `toast align-items-center text-white bg-${type === 'danger' ? 'danger' : 'warning'} border-0 show mb-2`;
            toast.setAttribute('role', 'alert');
            toast.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body font-weight-bold">
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" onclick="this.parentElement.parentElement.remove()"></button>
                </div>
            `;
            container.appendChild(toast);

            setTimeout(() => {
                if (toast.parentElement) {
                    toast.remove();
                }
            }, 5000);
        },

        createToastContainer() {
            const container = document.createElement('div');
            container.id = 'proctorToastContainer';
            container.style.position = 'fixed';
            container.style.top = '20px';
            container.style.right = '20px';
            container.style.zIndex = '99999';
            document.body.appendChild(container);
            return container;
        }
    };

    window.ProctorGuard = ProctorGuard;
})();
