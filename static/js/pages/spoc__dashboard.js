/* Moved unchanged from an inline <script> in templates/spoc/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// CSRF configuration for ajax requests
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

// Load initial chart data
var _cd = JSON.parse(document.getElementById('spoc-chart-data').textContent);

if (_cd.hasEvents) {
  // ── REGISTRATION BAR CHART ──
  var regCtx = document.getElementById('regChart');
  if (regCtx) {
    const ctx = regCtx.getContext('2d');
    // Create blue gradient
    const gradientBlue = ctx.createLinearGradient(0, 0, 0, 200);
    gradientBlue.addColorStop(0, 'rgba(59, 130, 246, 0.9)');
    gradientBlue.addColorStop(1, 'rgba(26, 37, 87, 0.7)');
    
    // Create gold gradient
    const gradientGold = ctx.createLinearGradient(0, 0, 0, 200);
    gradientGold.addColorStop(0, 'rgba(245, 158, 11, 0.9)');
    gradientGold.addColorStop(1, 'rgba(201, 164, 94, 0.7)');

    new Chart(regCtx, {
      type: 'bar',
      data: {
        labels: _cd.labels,
        datasets: [{
          label: 'Registrations',
          data: _cd.regs,
          backgroundColor: _cd.labels.map(function(_, i) {
            return i % 2 === 0 ? gradientBlue : gradientGold;
          }),
          borderRadius: 8,
          borderSkipped: false,
        }]
      },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { display: false }, ticks: { font: { size: 11 } } },
          y: { grid: { color: 'rgba(226, 232, 240, 0.4)' }, ticks: { stepSize: 1, font: { size: 11 } }, beginAtZero: true }
        }
      }
    });
  }

  // ── ATTENDANCE DONUT ──
  var present = _cd.present;
  var pending  = Math.max(0, _cd.totalRegs - present);
  var attCtx   = document.getElementById('attChart');
  if (attCtx) {
    const ctx = attCtx.getContext('2d');
    // Create green gradient
    const gradientGreen = ctx.createLinearGradient(0, 0, 0, 200);
    gradientGreen.addColorStop(0, 'rgba(16, 185, 129, 0.95)');
    gradientGreen.addColorStop(1, 'rgba(4, 120, 87, 0.8)');

    // Create grey gradient
    const gradientGrey = ctx.createLinearGradient(0, 0, 0, 200);
    gradientGrey.addColorStop(0, 'rgba(226, 232, 240, 0.9)');
    gradientGrey.addColorStop(1, 'rgba(203, 213, 225, 0.8)');

    new Chart(attCtx, {
      type: 'doughnut',
      data: {
        labels: ['Present', 'Pending'],
        datasets: [{
          data: [present, pending],
          backgroundColor: [gradientGreen, gradientGrey],
          borderWidth: 0,
          hoverOffset: 4
        }]
      },
      options: {
        responsive: true,
        cutout: '72%',
        plugins: { legend: { position: 'bottom', labels: { font: { size: 12 }, boxWidth: 12 } } }
      }
    });
  }
}

// ── MASTER-DETAIL & TAB LOGIC ──
let activeEventId = null;

function selectEvent(eventId) {
  activeEventId = eventId;
  
  // Hide global panel
  document.getElementById('global-panel').style.display = 'none';
  document.getElementById('tour-global-btn').classList.remove('active');
  
  // Hide all details panels
  document.querySelectorAll('.event-detail-panel').forEach(pane => {
    pane.style.display = 'none';
  });
  
  // Show target panel
  const panel = document.getElementById('detail-panel-' + eventId);
  if (panel) {
    panel.style.display = 'block';
    
    // Highlight venue on map automatically
    const venueTextEl = panel.querySelector('.event-venue-text');
    if (venueTextEl) {
      highlightEventVenue(venueTextEl.textContent, panel);
    }
  }
  
  // Highlight card in list
  document.querySelectorAll('.sidebar-event-card').forEach(card => {
    card.classList.remove('active');
  });
  const card = document.getElementById('card-' + eventId);
  if (card) {
    card.classList.add('active');
  }
  
  // Update URL hash
  window.location.hash = 'event-' + eventId;
  
  // Toggle detail view in CSS via class
  const layout = document.querySelector('.dashboard-layout');
  if (layout) layout.classList.add('show-detail');
}

function selectGlobalOverview() {
  activeEventId = null;
  
  // Hide all panels
  document.querySelectorAll('.event-detail-panel').forEach(pane => {
    pane.style.display = 'none';
  });
  
  // Show global panel
  document.getElementById('global-panel').style.display = 'block';
  
  // Update active card selections
  document.getElementById('tour-global-btn').classList.add('active');
  document.querySelectorAll('.sidebar-event-card').forEach(card => {
    card.classList.remove('active');
  });
  
  // Update URL hash
  window.location.hash = 'overview';
  
  // Toggle detail view in CSS via class
  const layout = document.querySelector('.dashboard-layout');
  if (layout) layout.classList.add('show-detail');
}

function showMasterList() {
  const layout = document.querySelector('.dashboard-layout');
  if (layout) layout.classList.remove('show-detail');
}

function switchTab(tabName, btnElement) {
  const container = btnElement.closest('.event-detail-panel');
  if (!container) return;
  
  // Reset tab buttons
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.remove('active');
  });
  btnElement.classList.add('active');
  
  // Reset tab panes
  container.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.remove('active');
  });
  const pane = container.querySelector(`.tab-pane[data-tab-pane="${tabName}"]`);
  if (pane) {
    pane.classList.add('active');
  }
}

// ── SEARCH & FILTER LOGIC ──
let activeFilter = 'all';

function setFilter(btn) {
  document.querySelectorAll('.filter-pill-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  activeFilter = btn.dataset.filter;
  applySearchAndFilter();
}

function applySearchAndFilter() {
  const query = document.getElementById('event-search').value.toLowerCase().trim();
  
  document.querySelectorAll('.sidebar-event-card').forEach(card => {
    const title = card.dataset.title.toLowerCase();
    const category = card.dataset.category.toLowerCase();
    const venue = card.dataset.venue.toLowerCase();
    const status = card.dataset.status; // 'active', 'completed'
    
    const matchesSearch = title.includes(query) || category.includes(query) || venue.includes(query);
    const matchesFilter = activeFilter === 'all' || status === activeFilter;
    
    if (matchesSearch && matchesFilter) {
      card.style.setProperty('display', 'flex', 'important');
    } else {
      card.style.setProperty('display', 'none', 'important');
    }
  });
}

// ── WAYFINDER CAPACITY MAP LOGIC ──
function selectRoom(name, cap, max, element) {
  const pct = Math.round((cap / max) * 100);
  let statusClass = "text-success";
  let statusMsg = "Optimized Capacity. No action needed.";
  if (pct >= 95) {
    statusClass = "text-danger fw-bold";
    statusMsg = "Critical Level. Shift overflowing participants to Seminar Hall.";
  } else if (pct >= 80) {
    statusClass = "text-warning";
    statusMsg = "Warning: Approaching max capacity bounds soon.";
  }
  
  const container = element.closest('.wayfinder-card-wrapper');
  if (container) {
    const detailsContent = container.querySelector('.room-details-content');
    if (detailsContent) {
      detailsContent.innerHTML = `
        <div class="mb-2"><strong class="text-white" style="color:var(--ink-900)!important;">Zone ID:</strong> ${escapeHtml(name)}</div>
        <div class="mb-2"><strong class="text-white" style="color:var(--ink-900)!important;">Live Capacity:</strong> ${escapeHtml(cap)} / ${escapeHtml(max)} (${escapeHtml(pct)}%)</div>
        <div class="mb-2"><strong class="text-white" style="color:var(--ink-900)!important;">Status:</strong> <span class="${escapeHtml(statusClass)}">${escapeHtml(pct)}% Filled</span></div>
        <div class="mb-2"><strong class="text-white" style="color:var(--ink-900)!important;">Recommendation:</strong><br>${escapeHtml(statusMsg)}</div>
      `;
    }
    
    container.querySelectorAll('.wayfinder-room-g').forEach(g => {
      g.classList.remove('active');
    });
    element.classList.add('active');
  }
}

function highlightEventVenue(venueName, panel) {
  if (!venueName) return;
  const name = venueName.toLowerCase();
  let roomName = '';
  let cap = 0;
  let max = 0;
  
  if (name.includes('auditorium')) {
    roomName = 'Main Auditorium'; cap = 310; max = 400;
  } else if (name.includes('lab') || name.includes('cs')) {
    roomName = 'CS Lab'; cap = 48; max = 50;
  } else if (name.includes('seminar') || name.includes('hall')) {
    roomName = 'Seminar Hall'; cap = 120; max = 150;
  } else if (name.includes('sports') || name.includes('arena')) {
    roomName = 'Sports Arena'; cap = 85; max = 200;
  }
  
  if (roomName) {
    const roomG = panel.querySelector(`.wayfinder-room-g[data-room-name="${roomName}"]`);
    if (roomG) {
      selectRoom(roomName, cap, max, roomG);
    }
  }
}

function toggleWayfinderMap(btn, contentId) {
  const content = document.getElementById(contentId);
  if (!content) return;
  const isExpanded = content.classList.contains('show');
  
  if (isExpanded) {
    content.classList.remove('show');
    btn.querySelector('.toggle-text').textContent = btn.getAttribute('data-show-text');
    btn.querySelector('.toggle-icon').className = 'fas fa-chevron-down toggle-icon ms-2';
  } else {
    content.classList.add('show');
    btn.querySelector('.toggle-text').textContent = btn.getAttribute('data-hide-text');
    btn.querySelector('.toggle-icon').className = 'fas fa-chevron-up toggle-icon ms-2';
  }
}

// Initialize layout on load
window.addEventListener('DOMContentLoaded', () => {
  const hash = window.location.hash;
  if (hash && hash.startsWith('#event-')) {
    const eventId = hash.replace('#event-', '');
    selectEvent(eventId);
  } else {
    if (window.innerWidth <= 992) {
      showMasterList();
    } else {
      selectGlobalOverview();
    }
  }
});
