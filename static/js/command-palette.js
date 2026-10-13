/* Command palette (Cmd/Ctrl+K) on every app page (UPG-63). Pages may add
   their own entries by setting window.SE_PALETTE_EXTRA = [{name, url}, ...]
   before DOMContentLoaded (the student dashboard adds its tickets). Names are
   inserted as text. */
document.addEventListener('DOMContentLoaded', () => {
    if (!document.getElementById('command-palette')) {
        const overlay = document.createElement('div');
        overlay.id = 'command-palette';
        overlay.className = 'command-palette-overlay';
        overlay.setAttribute('role', 'dialog');
        overlay.setAttribute('aria-modal', 'true');
        overlay.setAttribute('aria-label', 'Go to a page');
        overlay.innerHTML = `
            <div class="command-palette-box">
                <div class="command-palette-input-wrap">
                    <i class="fas fa-search" aria-hidden="true"></i>
                    <input type="text" class="command-palette-input" placeholder="Go to a page or event…" id="command-palette-search" aria-label="Search pages" autocomplete="off">
                    <button type="button" class="btn-close" id="command-palette-close" aria-label="Close"></button>
                </div>
                <div class="command-palette-results" id="command-palette-results" role="listbox"></div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    const searchInput = document.getElementById('command-palette-search');
    const resultsContainer = document.getElementById('command-palette-results');
    const palette = document.getElementById('command-palette');
    const closeBtn = document.getElementById('command-palette-close');

    const commands = (window.SE_PALETTE_EXTRA || []).concat([
        { name: 'Home', url: '/' },
        { name: 'Browse events', url: '/events' },
        { name: 'University calendar', url: '/calendar' },
        { name: 'My profile', url: '/profile/' },
        { name: 'My tickets and registrations', url: '/participant/dashboard' },
        { name: 'Leaderboard and activity points', url: '/gamification/leaderboard' },
        { name: 'Campus wayfinder', url: '/platform/wayfinder' },
        { name: 'Live event streams', url: '/live/streams' },
        { name: 'Highlight reels', url: '/live/reels' },
        { name: 'Service status', url: '/compliance/sla' },
        { name: 'Privacy settings', url: '/compliance/settings' },
        { name: 'Log out', url: '/logout' }
    ]);

    function togglePalette() {
        palette.classList.toggle('show');
        if (palette.classList.contains('show')) {
            searchInput.value = '';
            searchInput.focus();
            renderResults(commands);
        }
    }
    window.openCommandPalette = () => { if (!palette.classList.contains('show')) togglePalette(); };

    function renderResults(list) {
        resultsContainer.replaceChildren();
        if (list.length === 0) {
            const empty = document.createElement('div');
            empty.className = 'p-3 text-center text-muted';
            empty.textContent = 'No matching pages.';
            resultsContainer.appendChild(empty);
            return;
        }
        list.forEach((item, index) => {
            const el = document.createElement('a');
            el.href = item.url;
            el.setAttribute('role', 'option');
            el.className = 'command-palette-item' + (index === 0 ? ' active' : '');
            const name = document.createElement('span');
            name.textContent = item.name;
            const hint = document.createElement('span');
            hint.className = 'ms-auto text-muted small';
            hint.textContent = 'Go to →';
            el.appendChild(name);
            el.appendChild(hint);
            resultsContainer.appendChild(el);
        });
    }

    document.addEventListener('keydown', (e) => {
        if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
            e.preventDefault();
            togglePalette();
        }
        if (e.key === 'Escape' && palette.classList.contains('show')) {
            togglePalette();
        }
    });

    searchInput.addEventListener('input', (e) => {
        const query = e.target.value.toLowerCase().trim();
        if (!query) { renderResults(commands); return; }
        renderResults(commands.filter(item => item.name.toLowerCase().includes(query) || item.url.toLowerCase().includes(query)));
    });

    if (closeBtn) closeBtn.addEventListener('click', togglePalette);
    if (palette) palette.addEventListener('click', (e) => { if (e.target === palette) togglePalette(); });
});

// Registered now (not on DOMContentLoaded) so handlers.js finds it when it binds
Object.assign(window.SE_H = window.SE_H || {}, { 'palette:open': function () { if (window.openCommandPalette) window.openCommandPalette(); } });
