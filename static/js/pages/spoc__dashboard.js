/* Moved unchanged from an inline <script> in templates/spoc/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// CSRF configuration for ajax requests
const CSRF_TOKEN = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

// ── CHARTS (Apache ECharts via SE_EC, UPG-83) ──
// Each event's registrations split into parts that add up: attended, no-show,
// not held yet, and waitlisted / pending / cancelled.
var _cd = JSON.parse(document.getElementById('spoc-chart-data').textContent);
var SPOC_PARTS = [
  { key: 'attended', name: 'Attended', slot: 2 },
  { key: 'no_show', name: 'No-show', slot: 3 },
  { key: 'upcoming', name: 'Not held yet', slot: 0 },
  { key: 'other', name: 'Waitlisted, pending or cancelled', other: true },
];
if (_cd.hasEvents && window.SE_EC && _cd.breakdown.length) {
  var _top = _cd.breakdown.slice(0, 8).reverse();     // most registrations at the top
  var _regChart = SE_EC.mount(document.getElementById('regChart'), function (t) {
    return SE_EC.base(t, {
      toolbox: { show: false },
      grid: { left: 14, right: 16, top: 52, bottom: 8, containLabel: true },
      tooltip: Object.assign(SE_EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (items) {
          var e = _top[items[0].dataIndex];
          var html = '<b>' + escapeHtml(e.title) + '</b><br>Registered: <b>' + escapeHtml(SE_EC.fmt(e.registered)) + '</b><br>';
          items.forEach(function (it) { var markerHtml = it.marker; html += markerHtml + escapeHtml(it.seriesName) + ': ' + escapeHtml(SE_EC.fmt(it.value)) + '<br>'; });
          return html;
        } }),
      xAxis: SE_EC.valueAxis(t, { minInterval: 1 }),
      yAxis: SE_EC.categoryAxis(t, _top.map(function (e) { return e.title; }),
        { axisLabel: { color: t.inkStrong, width: t.narrow ? 100 : 150, overflow: 'truncate' } }),
      series: SPOC_PARTS.map(function (m, i) {
        return { name: m.name, type: 'bar', stack: 'all', barMaxWidth: 18,
                 itemStyle: { color: m.other ? t.other : t.palette[m.slot], borderColor: t.surface, borderWidth: 1,
                              borderRadius: i === SPOC_PARTS.length - 1 ? [0, 4, 4, 0] : 0 },
                 data: _top.map(function (e) { return e[m.key]; }) };
      }),
    });
  });
  if (_regChart) _regChart.chart.on('click', function (p) {
    var e = _top[p.dataIndex]; if (e) window.location.href = '/spoc/event/' + encodeURIComponent(e.id) + '/review';
  });

  // Totals across every event, as one labelled bar per part
  var _sum = SPOC_PARTS.map(function (m) {
    return _cd.breakdown.reduce(function (t, e) { return t + (e[m.key] || 0); }, 0);
  });
  var _all = _sum.reduce(function (a, b) { return a + b; }, 0);
  SE_EC.mount(document.getElementById('attChart'), function (t) {
    var names = SPOC_PARTS.map(function (m) { return m.name === 'Waitlisted, pending or cancelled' ? 'Other' : m.name; });
    return SE_EC.base(t, {
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 14, right: 70, top: 12, bottom: 8, containLabel: true },
      tooltip: Object.assign(SE_EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (items) { var i = items[0].dataIndex;
          return '<b>' + escapeHtml(SPOC_PARTS[i].name) + '</b><br>' + escapeHtml(SE_EC.fmt(_sum[i])) + ' of ' + escapeHtml(SE_EC.fmt(_all)) + ' registrations'; } }),
      xAxis: SE_EC.valueAxis(t, { minInterval: 1 }),
      yAxis: SE_EC.categoryAxis(t, names, { inverse: true, axisLabel: { color: t.inkStrong, fontWeight: 600 } }),
      series: [{ name: 'Registrations', type: 'bar', barMaxWidth: 24,
                 data: SPOC_PARTS.map(function (m, i) { return { value: _sum[i], itemStyle: { color: m.other ? t.other : t.palette[m.slot], borderRadius: [0, 4, 4, 0] } }; }),
                 label: { show: true, position: 'right', color: t.ink,
                          formatter: function (p) { return SE_EC.fmt(p.value) + (_all ? '  ·  ' + Math.round(p.value * 100 / _all) + '%' : ''); } } }],
    });
  });
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
