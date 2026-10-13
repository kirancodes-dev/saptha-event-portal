/* Moved unchanged from an inline <script> in templates/spoc/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// ── COORDINATOR AUTOCOMPLETE ──
var _coordCache = [];
(function loadCoordinators() {
  fetch('/spoc/api/coordinators')
    .then(function(r) { return r.ok ? r.json() : []; })
    .then(function(list) {
      _coordCache = list;
      var dl = document.getElementById('coordSuggestions');
      if (!dl) return;
      dl.innerHTML = '';
      list.forEach(function(c) {
        var opt = document.createElement('option');
        opt.value = c.email;
        opt.label = c.name ? c.name + ' (' + c.email + ')' : c.email;
        dl.appendChild(opt);
      });
    })
    .catch(function() {});
})();

function autoFillCoordName(email, nameFieldId) {
  var match = _coordCache.find(function(c) { return c.email === email; });
  if (match && match.name) {
    var f = document.getElementById(nameFieldId);
    if (f && !f.value) f.value = match.name;
  }
}

// ── TOAST NOTIFICATION UTILITY ──
function showToast(message, type = 'success', duration = 3500) {
  var container = document.getElementById('toast-container-holder');
  if (!container) return;
  
  var toast = document.createElement('div');
  toast.className = `custom-toast toast-${type}`;
  
  var icon = 'fa-check-circle';
  if (type === 'error') icon = 'fa-exclamation-circle';
  if (type === 'info') icon = 'fa-info-circle';
  
  toast.innerHTML = `
    <div class="toast-icon">
      <i class="fas ${escapeHtml(icon)}"></i>
    </div>
    <div class="toast-content">${escapeHtml(message)}</div>
  `;
  
  container.appendChild(toast);
  
  // Trigger animation next frame
  requestAnimationFrame(function() {
    toast.classList.add('show');
  });
  
  // Autoclose
  setTimeout(function() {
    toast.classList.remove('show');
    setTimeout(function() {
      toast.remove();
    }, 400);
  }, duration);
}

// ── FLOATING SPEED DIAL INTERACTION ──
function toggleSpeedDial() {
  var sd = document.getElementById('dashboard-speed-dial');
  var icon = document.getElementById('speed-dial-trigger-icon');
  if (!sd) return;
  
  var isOpen = sd.classList.contains('open');
  if (isOpen) {
    sd.classList.remove('open');
    if (icon) icon.className = 'fas fa-bolt';
  } else {
    sd.classList.add('open');
    if (icon) icon.className = 'fas fa-times';
  }
}

// Close speed dial when clicking outside
document.addEventListener('click', function(e) {
  var sd = document.getElementById('dashboard-speed-dial');
  if (sd && sd.classList.contains('open') && !sd.contains(e.target)) {
    toggleSpeedDial();
  }
});

// ── LIVE STATS AUTO-REFRESH ──
var _syncIcon = document.getElementById('stats-sync-icon');
function refreshStats() {
  if (_syncIcon) _syncIcon.style.animation = 'spin 1s linear infinite';
  fetch('/spoc/api/stats')
    .then(function(r) { return r.ok ? r.json() : null; })
    .then(function(data) {
      if (!data) return;
      var te = document.getElementById('stat-total-events');
      var tr = document.getElementById('stat-total-regs');
      var pr = document.getElementById('stat-present');
      if (te) te.textContent = data.total_events;
      if (tr) tr.textContent = data.total_regs;
      if (pr) pr.textContent = data.present_count;
      
      // Update Live Activity Feed
      var feedContainer = document.getElementById('live-activity-feed');
      if (feedContainer && data.recent_activity) {
        if (data.recent_activity.length === 0) {
          feedContainer.innerHTML = '<div class="text-center py-3 text-muted small"><i class="fas fa-info-circle me-1"></i>No recent activity logged.</div>';
          return;
        }
        
        feedContainer.innerHTML = '';
        data.recent_activity.forEach(function(act) {
          var item = document.createElement('div');
          item.className = 'activity-item';
          
          var badgeClass = act.type === 'checkin' ? 'activity-icon-checkin' : 'activity-icon-reg';
          var iconClass = act.type === 'checkin' ? 'fa-user-check' : 'fa-user-plus';
          
          item.innerHTML = `
            <div class="activity-icon-badge ${escapeHtml(badgeClass)}">
              <i class="fas ${escapeHtml(iconClass)}"></i>
            </div>
            <div class="activity-details">
              <div class="fw-bold text-white" style="color: var(--ink-900) !important;">${escapeHtml(act.name)}</div>
              <div class="text-muted small">${escapeHtml(act.details)} in <span class="fw-semibold text-primary" style="color: var(--snpsu-blue-lighter) !important;">${escapeHtml(act.event)}</span></div>
            </div>
            <div class="activity-time">${escapeHtml(act.time)}</div>
          `;
          feedContainer.appendChild(item);
        });
      }
    })
    .catch(function() {})
    .finally(function() {
      if (_syncIcon) _syncIcon.style.animation = '';
    });
}
setInterval(refreshStats, 30000);
window.addEventListener('DOMContentLoaded', refreshStats);

// ── INTERACTIVE COMMAND PALETTE (SPOTLIGHT) JS ──
let paletteOpen = false;
let paletteItems = [];
let highlightedIndex = 0;

function openCommandPalette() {
  paletteOpen = true;
  var backdrop = document.getElementById('cmd-palette');
  backdrop.classList.add('open');
  var input = document.getElementById('cmd-palette-input');
  input.value = '';
  input.focus();
  
  buildPaletteCommands();
  filterPaletteCommands();
}

function closeCommandPalette() {
  paletteOpen = false;
  var backdrop = document.getElementById('cmd-palette');
  backdrop.classList.remove('open');
}

function handlePaletteBackdropClick(e) {
  if (e.target.id === 'cmd-palette') {
    closeCommandPalette();
  }
}

// Build list of all commands dynamically
function buildPaletteCommands() {
  paletteItems = [];
  
  // 1. Navigation items (Events)
  document.querySelectorAll('.sidebar-event-card').forEach(function(card) {
    var id = card.id.replace('card-', '');
    var title = card.dataset.title;
    var category = card.dataset.category;
    paletteItems.push({
      type: 'event',
      title: 'Switch to: ' + title,
      category: category,
      icon: 'fa-calendar-alt',
      action: function() { selectEvent(id); }
    });
  });
  
  // 2. Event context-specific actions (only if an event is currently active)
  if (activeEventId) {
    var activeCard = document.getElementById('card-' + activeEventId);
    var activeTitle = activeCard ? activeCard.dataset.title : 'Selected Event';
    
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Export Registrations (CSV)`,
      icon: 'fa-file-csv',
      action: function() { window.location.href = '/spoc/export_csv/' + activeEventId; }
    });
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Launch Live Leaderboard`,
      icon: 'fa-tv',
      action: function() { window.open('/live/' + activeEventId, '_blank'); }
    });
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Open Check-in Scanner`,
      icon: 'fa-qrcode',
      action: function() { window.location.href = '/spoc/scan/' + activeEventId; }
    });
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Broadcast Alert Email`,
      icon: 'fa-paper-plane',
      action: function() { openBlastModal(activeEventId, activeTitle); }
    });
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Manage Judges & Round Scoring`,
      icon: 'fa-gavel',
      action: function() {
        var pane = document.getElementById('detail-panel-' + activeEventId);
        if (pane) {
          var btn = pane.querySelector('.tab-btn[data-tab="certs"]');
          if (btn) switchTab('certs', btn);
        }
      }
    });
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Manage Rooms & Wayfinder`,
      icon: 'fa-building',
      action: function() {
        var pane = document.getElementById('detail-panel-' + activeEventId);
        if (pane) {
          var btn = pane.querySelector('.tab-btn[data-tab="logistics"]');
          if (btn) switchTab('logistics', btn);
        }
      }
    });
    paletteItems.push({
      type: 'context',
      title: `[${activeTitle}] Show Event Settings`,
      icon: 'fa-cog',
      action: function() {
        var pane = document.getElementById('detail-panel-' + activeEventId);
        if (pane) {
          var btn = pane.querySelector('.tab-btn[data-tab="settings"]');
          if (btn) switchTab('settings', btn);
        }
      }
    });
  }
  
  // 3. Global settings and utilities
  paletteItems.push({
    type: 'global',
    title: 'Show Global Overview Hub',
    icon: 'fa-chart-line',
    action: function() { selectGlobalOverview(); }
  });
  paletteItems.push({
    type: 'global',
    title: 'Create New Event',
    icon: 'fa-plus',
    action: function() { window.location.href = '/spoc/create_event'; }
  });
  paletteItems.push({
    type: 'global',
    title: 'Toggle Dark / Light Mode',
    icon: 'fa-circle-half-stroke',
    action: function() { toggleTheme(); }
  });
  paletteItems.push({
    type: 'global',
    title: 'Launch Onboarding Tour Guide',
    icon: 'fa-flag',
    action: function() { startTour(); }
  });
  paletteItems.push({
    type: 'global',
    title: 'Sync Live Console Stats',
    icon: 'fa-sync-alt',
    action: function() { refreshStats(); showToast('Statistics sync completed!', 'success'); }
  });
  paletteItems.push({
    type: 'global',
    title: 'System Log Out',
    icon: 'fa-sign-out-alt',
    action: function() { window.location.href = '/logout'; }
  });
}

function filterPaletteCommands() {
  var query = document.getElementById('cmd-palette-input').value.toLowerCase().trim();
  var container = document.getElementById('cmd-palette-results');
  if (!container) return;
  
  var filtered = paletteItems.filter(function(item) {
    return item.title.toLowerCase().includes(query) || (item.category && item.category.toLowerCase().includes(query));
  });
  
  if (filtered.length === 0) {
    container.innerHTML = '<div class="text-center py-4 text-muted small"><i class="fas fa-info-circle me-1"></i>No commands match your query.</div>';
    highlightedIndex = 0;
    return;
  }
  
  container.innerHTML = '';
  
  // Group by type for visual headers
  var lastType = '';
  var itemIndex = 0;
  
  filtered.forEach(function(item) {
    var typeTitle = '';
    if (item.type !== lastType) {
      if (item.type === 'event') typeTitle = 'Events Directory';
      if (item.type === 'context') typeTitle = 'Selected Event Actions';
      if (item.type === 'global') typeTitle = 'System Commands';
      
      var header = document.createElement('div');
      header.className = 'cmd-section-header';
      header.textContent = typeTitle;
      container.appendChild(header);
      lastType = item.type;
    }
    
    var el = document.createElement('button');
    el.className = 'cmd-item';
    el.dataset.index = itemIndex;
    if (itemIndex === highlightedIndex) el.classList.add('active');
    
    el.innerHTML = `
      <div class="cmd-item-left">
        <i class="fas ${escapeHtml(item.icon)} cmd-item-icon"></i>
        <span class="cmd-item-title">${escapeHtml(item.title)}</span>
      </div>
      <div>
        ${item.category ? `<span class="cmd-item-badge">${escapeHtml(item.category)}</span>` : ''}
        ${itemIndex === 0 ? '<span class="cmd-item-shortcut">Enter</span>' : ''}
      </div>
    `;
    
    var curIdx = itemIndex;
    el.onclick = function() {
      item.action();
      closeCommandPalette();
    };
    
    container.appendChild(el);
    itemIndex++;
  });
  
  // Keep index within bounds
  if (highlightedIndex >= itemIndex) {
    highlightedIndex = 0;
    var firstEl = container.querySelector('.cmd-item');
    if (firstEl) firstEl.classList.add('active');
  }
}

// Keyboard shortcuts and navigation listeners
document.addEventListener('keydown', function(e) {
  // 1. Toggle Palette: Cmd+K / Ctrl+K
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    if (paletteOpen) {
      closeCommandPalette();
    } else {
      openCommandPalette();
    }
    return;
  }
  
  if (!paletteOpen) return;
  
  // 2. Navigation keys inside open palette
  var results = document.getElementById('cmd-palette-results');
  if (!results) return;
  var items = results.querySelectorAll('.cmd-item');
  if (items.length === 0) return;
  
  if (e.key === 'Escape') {
    e.preventDefault();
    closeCommandPalette();
  } else if (e.key === 'ArrowDown') {
    e.preventDefault();
    items[highlightedIndex].classList.remove('active');
    highlightedIndex = (highlightedIndex + 1) % items.length;
    items[highlightedIndex].classList.add('active');
    items[highlightedIndex].scrollIntoView({ block: 'nearest' });
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    items[highlightedIndex].classList.remove('active');
    highlightedIndex = (highlightedIndex - 1 + items.length) % items.length;
    items[highlightedIndex].classList.add('active');
    items[highlightedIndex].scrollIntoView({ block: 'nearest' });
  } else if (e.key === 'Enter') {
    e.preventDefault();
    items[highlightedIndex].click();
  }
});
