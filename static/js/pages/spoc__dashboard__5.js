/* Moved unchanged from an inline <script> in templates/spoc/dashboard.html so the CSP
   needs no inline script (UPG-25). */
const tourSteps = [
  {
    element: '#tour-global-btn',
    title: 'Global Overview Hub 🌐',
    content: 'Click this button to see the cumulative statistics across all your events, active room allocations, and visual charts.'
  },
  {
    element: '#event-search',
    title: 'Instant Search 🔍',
    content: 'Type any title, category, or venue to search and filter your events list in real-time as you type.'
  },
  {
    element: '.filter-pill-btn[data-filter="active"]',
    title: 'Event Filters 📊',
    content: 'Quickly narrow down your events to view only Active or Completed configurations.'
  },
  {
    element: '.sidebar-event-card',
    title: 'Master Event Cards 📇',
    content: 'Select an event from the list to load its dedicated Event Command Center details.'
  },
  {
    element: '#tour-stats-row',
    title: 'Live Statistics Gauge 📈',
    content: 'Monitor real-time registrations, present attendees count, revenue, and staff assigned specifically to this event.',
    requiresEvent: true
  },
  {
    element: '#tour-tabs-nav',
    title: 'Event Management Tabs 🛠️',
    content: 'Switch tabs to access QR scanning, logistical maps, communication tools, judge configurations, and settings.',
    requiresEvent: true
  },
  {
    element: '.tab-btn[data-tab="logistics"]',
    title: 'Logistics & QR Scanning 🎫',
    content: 'Manage real-time ticket scanning, venue codes, round qualifications, NFC simulations, and room setups here.',
    requiresEvent: true
  },
  {
    element: '.tab-btn[data-tab="certs"]',
    title: 'Judges & Certifications 🎓',
    content: 'Manage judge rosters, open-hall grading modes, visual certificate templates, and bulk certificate delivery.',
    requiresEvent: true
  },
  {
    element: '#theme-toggle',
    title: 'Adaptive Themes 🌓',
    content: 'Toggle between dark and light modes. The dashboard is optimized to remain clear and high-contrast in either setting.'
  }
];

let currentTourStep = 0;

function startTour() {
  currentTourStep = 0;
  document.getElementById('tour-overlay').style.display = 'block';
  document.getElementById('tour-tooltip').style.display = 'block';
  setTimeout(() => {
    document.getElementById('tour-overlay').style.opacity = '1';
    document.getElementById('tour-tooltip').style.opacity = '1';
  }, 50);
  showTourStep();
}

function exitTour() {
  document.getElementById('tour-overlay').style.opacity = '0';
  document.getElementById('tour-tooltip').style.opacity = '0';
  document.querySelectorAll('.tour-highlight').forEach(el => el.classList.remove('tour-highlight'));
  setTimeout(() => {
    document.getElementById('tour-overlay').style.display = 'none';
    document.getElementById('tour-tooltip').style.display = 'none';
  }, 300);
  localStorage.setItem('spoc-dashboard-tour-completed', 'true');
}

function showTourStep() {
  const step = tourSteps[currentTourStep];
  if (!step) {
    exitTour();
    return;
  }
  
  // If step requires active event, make sure one is selected
  if (step.requiresEvent && !activeEventId) {
    const firstCard = document.querySelector('.sidebar-event-card');
    if (firstCard) {
      const firstEventId = firstCard.id.replace('card-', '');
      selectEvent(firstEventId);
    } else {
      currentTourStep++;
      showTourStep();
      return;
    }
  }
  
  // Handle tab switching for specific steps
  if (step.element === '.tab-btn[data-tab="logistics"]') {
    const tabEl = document.querySelector(`#detail-panel-${activeEventId} .tab-btn[data-tab="logistics"]`);
    if (tabEl) switchTab('logistics', tabEl);
  } else if (step.element === '.tab-btn[data-tab="certs"]') {
    const tabEl = document.querySelector(`#detail-panel-${activeEventId} .tab-btn[data-tab="certs"]`);
    if (tabEl) switchTab('certs', tabEl);
  }
  
  const el = document.querySelector(step.element);
  if (!el || el.offsetParent === null) {
    currentTourStep++;
    showTourStep();
    return;
  }
  
  document.querySelectorAll('.tour-highlight').forEach(x => x.classList.remove('tour-highlight'));
  el.classList.add('tour-highlight');
  
  document.getElementById('tour-title').textContent = step.title;
  document.getElementById('tour-content').textContent = step.content;
  
  document.getElementById('tour-btn-prev').style.visibility = currentTourStep === 0 ? 'hidden' : 'visible';
  document.getElementById('tour-btn-next').textContent = currentTourStep === tourSteps.length - 1 ? 'Finish' : 'Next';
  
  // Position tooltip
  const rect = el.getBoundingClientRect();
  const tooltip = document.getElementById('tour-tooltip');
  
  let top = rect.bottom + window.scrollY + 12;
  let left = rect.left + window.scrollX;
  
  if (left + 320 > window.innerWidth) {
    left = window.innerWidth - 340;
  }
  if (left < 10) left = 10;
  
  if (rect.bottom + 180 > window.innerHeight) {
    top = rect.top + window.scrollY - tooltip.offsetHeight - 12;
  }
  
  tooltip.style.top = top + 'px';
  tooltip.style.left = left + 'px';
  
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function nextTourStep() {
  if (currentTourStep < tourSteps.length - 1) {
    currentTourStep++;
    showTourStep();
  } else {
    exitTour();
    if (window.showToast) {
      showToast('Tour completed! Let us know if you need anything else.', 'success', 3000);
    }
  }
}

function prevTourStep() {
  if (currentTourStep > 0) {
    currentTourStep--;
    showTourStep();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  if (!localStorage.getItem('spoc-dashboard-tour-completed')) {
    setTimeout(startTour, 1500);
  }
});
