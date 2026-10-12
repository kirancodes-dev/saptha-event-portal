/* Charts on Apache ECharts via SE_EC (UPG-83). Otherwise moved unchanged from an inline <script> in templates/admin/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// ── CHARTS (Apache ECharts via SE_EC, UPG-83) ──
var _chartData = JSON.parse(document.getElementById('adminChartData').textContent);
if (window.SE_EC && _chartData.labels.length) {
  // The ten events with the most registrations (counted from registrations, UPG-81)
  var _topEvents = _chartData.labels.map(function (l, i) { return { title: l, id: _chartData.ids[i], regs: _chartData.regs[i] || 0 }; })
    .sort(function (a, b) { return b.regs - a.regs; }).slice(0, 10).reverse();
  var regChart = SE_EC.mount(document.getElementById('adminRegChart'), function (t) {
    return SE_EC.base(t, {
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 14, right: 44, top: 12, bottom: 8, containLabel: true },
      tooltip: Object.assign(SE_EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (items) { var e = _topEvents[items[0].dataIndex];
          return '<b>' + escapeHtml(e.title) + '</b><br>' + escapeHtml(SE_EC.fmt(e.regs)) + ' registrations<br><span style="opacity:.6">Click to open</span>'; } }),
      xAxis: SE_EC.valueAxis(t, { minInterval: 1 }),
      yAxis: SE_EC.categoryAxis(t, _topEvents.map(function (e) { return e.title; }),
        { axisLabel: { color: t.inkStrong, width: t.narrow ? 110 : 170, overflow: 'truncate' } }),
      series: [{ name: 'Registrations', type: 'bar', barMaxWidth: 16, data: _topEvents.map(function (e) { return e.regs; }),
                 itemStyle: { color: t.palette[0], borderRadius: [0, 4, 4, 0] },
                 label: { show: true, position: 'right', color: t.ink } }],
    });
  });
  if (regChart) regChart.chart.on('click', function (p) {
    var e = _topEvents[p.dataIndex]; if (e) window.location.href = '/spoc/event/' + encodeURIComponent(e.id) + '/review';
  });
  // Events per category: bars, largest first (easier to compare than slices)
  var cats = Object.keys(_chartData.cats).map(function (k) { return [k, _chartData.cats[k]]; })
    .sort(function (a, b) { return a[1] - b[1]; });
  if (cats.length) SE_EC.mount(document.getElementById('adminCatChart'), function (t) {
    return SE_EC.base(t, {
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 14, right: 36, top: 12, bottom: 8, containLabel: true },
      tooltip: Object.assign(SE_EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' } }),
      xAxis: SE_EC.valueAxis(t, { minInterval: 1 }),
      yAxis: SE_EC.categoryAxis(t, cats.map(function (c) { return c[0]; }), { axisLabel: { color: t.inkStrong } }),
      series: [{ name: 'Events', type: 'bar', barMaxWidth: 18, data: cats.map(function (c) { return c[1]; }),
                 itemStyle: { color: t.palette[0], borderRadius: [0, 4, 4, 0] },
                 label: { show: true, position: 'right', color: t.ink } }],
    });
  });
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
