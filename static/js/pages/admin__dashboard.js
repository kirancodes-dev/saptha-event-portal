/* Moved unchanged from an inline <script> in templates/admin/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// ── CHARTS ──
var _chartData = JSON.parse(document.getElementById('adminChartData').textContent);

if (_chartData.labels.length) {
  var labels = _chartData.labels.map(function(l){ return l.length>18?l.slice(0,18)+'…':l; });
  var rc = document.getElementById('adminRegChart');
  
  // Theme check
  var isDark = document.documentElement.getAttribute('data-theme') === 'dark';
  var gridColor = isDark ? 'rgba(255, 255, 255, 0.08)' : 'rgba(11, 21, 48, 0.06)';
  var textColor = isDark ? '#cbd5e1' : '#64748b';
  
  if (rc) {
    new Chart(rc, {
      type: 'bar',
      data: { labels: labels, datasets: [{
        label: 'Registrations', data: _chartData.regs,
        backgroundColor: labels.map(function(_,i){ return i%2===0?'rgba(26,37,87,.85)':'rgba(201,164,94,.85)'; }),
        borderRadius: 6, borderSkipped: false
      }]},
      options: { responsive:true, plugins:{legend:{display:false}},
        scales:{
          x:{grid:{display:false},ticks:{color:textColor,font:{size:10}}},
          y:{grid:{color:gridColor},ticks:{color:textColor,stepSize:1,font:{size:10}},beginAtZero:true}
        } }
    });
  }
  var cc = document.getElementById('adminCatChart');
  if (cc && Object.keys(_chartData.cats).length) {
    var catLabels = Object.keys(_chartData.cats);
    var catVals   = Object.values(_chartData.cats);
    new Chart(cc, {
      type: 'doughnut',
      data: { labels: catLabels, datasets: [{
        data: catVals,
        backgroundColor: ['#1a2557','#c9a45e','#10b981','#6366f1','#0891b2'],
        borderWidth: 0, hoverOffset: 4
      }]},
      options: { responsive:true, cutout:'68%',
        plugins:{legend:{position:'bottom',labels:{color:textColor,font:{size:11},boxWidth:10}}} }
    });
  }
}

// Search and the status filter run on the server (UPG-19).

// ── MEDIA FIELD ──
function addMediaField(containerId) {
  var c = document.getElementById(containerId);
  var d = document.createElement('div');
  d.className = 'input-group mb-2';
  d.innerHTML = '<input type="url" name="media_urls[]" class="form-control" placeholder="Image URL" required>' +
    '<button class="btn btn-outline-danger" type="button" data-h-click="se:remove-parent"><i class="fas fa-trash"></i></button>';
  c.appendChild(d);
}

// ── ROOM FIELD ──
function addRoomField(containerId) {
  var c = document.getElementById(containerId);
  var d = document.createElement('div');
  d.className = 'row g-2 mb-3 align-items-end room-row';
  d.innerHTML = '<div class="col-7"><input type="text" name="room_name[]" class="form-control" placeholder="Room 102" required></div>' +
    '<div class="col-4"><input type="number" name="capacity[]" class="form-control" placeholder="25" required></div>' +
    '<div class="col-1 pb-1"><button type="button" class="btn btn-outline-danger w-100" data-h-click="se:remove-grandparent"><i class="fas fa-trash"></i></button></div>';
  c.appendChild(d);
}

// ── MOBILE SIDEBAR TOGGLE ──
document.addEventListener('DOMContentLoaded', function() {
  var menuToggle = document.querySelector('.menu-toggle');
  var sidebar = document.querySelector('.sidebar');
  var overlay = document.querySelector('.sidebar-overlay');
  if (menuToggle && sidebar) {
    menuToggle.addEventListener('click', function() {
      sidebar.classList.toggle('active');
      if (overlay) overlay.classList.toggle('active');
    });
  }
  if (overlay) {
    overlay.addEventListener('click', function() {
      sidebar.classList.remove('active');
      overlay.classList.remove('active');
    });
  }
});
