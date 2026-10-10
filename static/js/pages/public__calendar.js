/* Moved unchanged from an inline <script> in templates/public/calendar.html so the CSP
   needs no inline script (UPG-25). */
var allEvents = JSON.parse(document.getElementById('cal-events-data').textContent);
var tooltip = document.getElementById('cal-tooltip');

var isMobile = window.innerWidth < 768;
var cal = new FullCalendar.Calendar(document.getElementById('calendar'), {
  initialView: isMobile ? 'listWeek' : 'dayGridMonth',
  headerToolbar: {
    left: 'prev,next today',
    center: 'title',
    right: 'dayGridMonth,timeGridWeek,listWeek'
  },
  views: {
    dayGridMonth: { buttonText: 'Month' },
    timeGridWeek: { buttonText: 'Week' },
    listWeek:     { buttonText: 'List' }
  },
  events: allEvents,
  height: 'auto',
  handleWindowResize: true,
  eventMouseEnter: function(info) {
    // Organisers typed the title, venue and category (BLK-19)
    var venueHtml = info.event.extendedProps.venue ? '<i class="fas fa-map-marker-alt me-1"></i>' + escapeHtml(info.event.extendedProps.venue) + '<br>' : '';
    var catHtml = info.event.extendedProps.category ? '<span class="badge bg-secondary">' + escapeHtml(info.event.extendedProps.category) + '</span>' : '';
    tooltip.innerHTML = '<strong style="color:#fbbf24;">' + escapeHtml(info.event.title) + '</strong><br>' + venueHtml + catHtml;
    tooltip.style.display = 'block';
  },
  eventMouseLeave: function() { tooltip.style.display = 'none'; },
  eventClick: function(info) {
    if (info.event.url) {
      info.jsEvent.preventDefault();
      window.location.href = info.event.url;
    }
  },
  eventDidMount: function(info) {
    info.el.style.cursor = 'pointer';
  },
  mousemove: function(e) {
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top = (e.clientY + 14) + 'px';
  },
});
cal.render();

document.addEventListener('mousemove', function(e) {
  if (tooltip.style.display !== 'none') {
    tooltip.style.left = (e.clientX + 14) + 'px';
    tooltip.style.top  = (e.clientY + 14) + 'px';
  }
});
