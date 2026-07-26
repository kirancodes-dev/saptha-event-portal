document.addEventListener('DOMContentLoaded', () => {
    // Inject command palette HTML to body if not already present
    if (!document.getElementById('command-palette')) {
        const overlay = document.createElement('div');
        overlay.id = 'command-palette';
        overlay.className = 'command-palette-overlay';
        overlay.innerHTML = `
            <div class="command-palette-box">
                <div class="command-palette-input-wrap">
                    <i class="fas fa-search me-3 text-muted"></i>
                    <input type="text" class="command-palette-input" placeholder="Type a command or page (e.g., 'profile', 'tickets', 'scanner')..." id="command-palette-search">
                    <button class="btn-close btn-close-white ms-2" id="command-palette-close" style="filter: invert(1);"></button>
                </div>
                <div class="command-palette-results" id="command-palette-results"></div>
            </div>
        `;
        document.body.appendChild(overlay);
    }

    const searchInput = document.getElementById('command-palette-search');
    const resultsContainer = document.getElementById('command-palette-results');
    const palette = document.getElementById('command-palette');
    const closeBtn = document.getElementById('command-palette-close');

    // Predefined commands and page list
    const commands = [
        { name: "🏠 Home Page", url: "/" },
        { name: "👤 User Profile", url: "/profile/" },
        { name: "🎫 Event Tickets & Registrations", url: "/participant/" },
        { name: "🏆 Leaderboard & XP Progress", url: "/gamification/leaderboard" },
        { name: "🗺️ Campus Wayfinder Map", url: "/platform/wayfinder" },
        { name: "📹 Live Event Streams", url: "/live/streams" },
        { name: "🎬 Highlight Reels", url: "/live/reels" },
        { name: "👥 Teammate Matchmaker", url: "/participant/matchmaker/" },
        { name: "📊 Analytics & SLA Uptime", url: "/compliance/sla" },
        { name: "⚖️ Compliance & Privacy Settings", url: "/compliance/consent" },
        { name: "📱 Event QR/NFC Scanner Terminal", url: "/spoc/ticket/nfc-verify/evt_test_001" },
        { name: "🔑 Logout Account", url: "/logout" }
    ];

    function togglePalette() {
        palette.classList.toggle('show');
        if (palette.classList.contains('show')) {
            searchInput.value = '';
            searchInput.focus();
            renderResults(commands);
        }
    }

    function renderResults(list) {
        resultsContainer.innerHTML = '';
        if (list.length === 0) {
            resultsContainer.innerHTML = '<div class="p-3 text-center text-muted">No commands or pages found.</div>';
            return;
        }
        list.forEach((item, index) => {
            const el = document.createElement('a');
            el.href = item.url;
            el.className = `command-palette-item ${index === 0 ? 'active' : ''}`;
            el.innerHTML = `<span>${item.name}</span> <span class="ms-auto text-muted small" style="font-size: 0.75rem;">Go to →</span>`;
            resultsContainer.appendChild(el);
        });
    }

    // Keydown listeners
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
        if (!query) {
            renderResults(commands);
            return;
        }
        const filtered = commands.filter(item => item.name.toLowerCase().includes(query) || item.url.toLowerCase().includes(query));
        renderResults(filtered);
    });

    if (closeBtn) closeBtn.addEventListener('click', togglePalette);
    if (palette) palette.addEventListener('click', (e) => {
        if (e.target === palette) togglePalette();
    });
});
