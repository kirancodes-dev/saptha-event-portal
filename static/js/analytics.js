/**
 * analytics.js — Analytics dashboard script mapping stats and rendering Chart.js graphs
 * ===================================================================================
 */

(function () {
  'use strict';

  var _charts = {};

  document.addEventListener('DOMContentLoaded', function () {
    loadDashboardData();
    
    // Auto-refresh every 30 seconds
    setInterval(loadDashboardData, 30000);
  });

  // 1. FETCH & PROCESS DATA
  function loadDashboardData() {
    toggleSkeletons(true);

    fetch('/analytics/api/stats')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        if (data.error) throw new Error(data.error);

        updateKPICards(data);
        renderCharts(data);
        renderRecentRegistrations(data.recent);
        
        toggleSkeletons(false);
      })
      .catch(function (err) {
        console.error('[Analytics] Error loading dashboard telemetry:', err);
        showDashboardError(err.message);
      });
  }

  // Toggle Loading Skeletons
  function toggleSkeletons(show) {
    var canvasWraps = document.querySelectorAll('.chart-canvas-wrap');
    canvasWraps.forEach(function (wrap) {
      var canvas = wrap.querySelector('canvas');
      var skeleton = wrap.querySelector('.chart-skeleton');
      if (show) {
        if (canvas) canvas.classList.add('d-none');
        if (skeleton) skeleton.classList.remove('d-none');
      } else {
        if (canvas) canvas.classList.remove('d-none');
        if (skeleton) skeleton.classList.add('d-none');
      }
    });
  }

  // Update metrics counters
  function updateKPICards(data) {
    animateValue('kpi-events-val', data.total_events || 0);
    animateValue('kpi-regs-val', data.total_registrations || 0);
    animateValue('kpi-revenue-val', data.total_revenue || 0, true);
    animateValue('kpi-attendance-val', data.attendance_rate || 0, false, '%');
  }

  function animateValue(id, value, isCurrency, suffix) {
    var obj = document.getElementById(id);
    if (!obj) return;
    
    var start = 0;
    var duration = 800; // ms
    var startTime = null;

    function step(timestamp) {
      if (!startTime) startTime = timestamp;
      var progress = Math.min((timestamp - startTime) / duration, 1);
      var current = start + progress * (value - start);
      
      var formatted = isCurrency ? '₹' + Math.floor(current).toLocaleString() : Math.floor(current).toLocaleString();
      if (suffix) formatted += suffix;
      
      obj.textContent = formatted;
      if (progress < 1) {
        window.requestAnimationFrame(step);
      } else {
        var final = isCurrency ? '₹' + value.toLocaleString() : value.toLocaleString();
        if (suffix) final += suffix;
        obj.textContent = final;
      }
    }
    
    window.requestAnimationFrame(step);
  }

  // 2. RENDER THE 6 CHARTS
  function renderCharts(data) {
    // Shared chart colors
    var themeColors = {
      blue: '#3b82f6',
      green: '#10b981',
      orange: '#f59e0b',
      purple: '#8b5cf6',
      cyan: '#06b6d4',
      pink: '#ec4899',
      red: '#ef4444'
    };

    // Chart 1: Trend line (Registrations over time)
    var trendKeys = Object.keys(data.reg_trend || {});
    var trendValues = Object.values(data.reg_trend || {});
    if (trendKeys.length === 0) {
      trendKeys = ['No Data'];
      trendValues = [0];
    }
    createOrUpdateChart('trendChart', 'line', {
      labels: trendKeys,
      datasets: [{
        label: 'Registrations',
        data: trendValues,
        borderColor: themeColors.green,
        backgroundColor: 'rgba(16, 185, 129, 0.1)',
        fill: true,
        tension: 0.3
      }]
    });

    // Chart 2: Doughnut (Events by category)
    var catKeys = Object.keys(data.categories || {});
    var catValues = Object.values(data.categories || {});
    createOrUpdateChart('categoryChart', 'doughnut', {
      labels: catKeys,
      datasets: [{
        data: catValues,
        backgroundColor: [themeColors.blue, themeColors.orange, themeColors.purple, themeColors.pink]
      }]
    });

    // Chart 3: Bar (Top 10 events by registrations)
    var topTitles = (data.top_events || []).map(x => x.title);
    var topCounts = (data.top_events || []).map(x => x.count);
    createOrUpdateChart('topEventsChart', 'bar', {
      labels: topTitles,
      datasets: [{
        label: 'Candidates Registered',
        data: topCounts,
        backgroundColor: themeColors.blue
      }]
    });

    // Chart 4: Pie (Payment status)
    var payStats = data.payment_stats || { paid: 0, unpaid: 0, waived: 0 };
    createOrUpdateChart('paymentStatusChart', 'pie', {
      labels: ['Paid', 'Unpaid', 'Waived'],
      datasets: [{
        data: [payStats.paid, payStats.unpaid, payStats.waived],
        backgroundColor: [themeColors.green, themeColors.red, themeColors.orange]
      }]
    });
  }

  function createOrUpdateChart(id, type, configData) {
    var canvas = document.getElementById(id);
    if (!canvas) return;

    if (_charts[id]) {
      _charts[id].destroy();
    }

    // Chart JS standard configs
    var ctx = canvas.getContext('2d');
    _charts[id] = new Chart(ctx, {
      type: type,
      data: configData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            labels: { color: '#94a3b8' }
          }
        },
        scales: type === 'line' || type === 'bar' ? {
          x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } },
          y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#94a3b8' } }
        } : {}
      }
    });
  }

  // 3. RENDER RECENT TABLE GRID
  function renderRecentRegistrations(recentList) {
    var tbody = document.getElementById('recent-regs-body');
    if (!tbody) return;

    tbody.innerHTML = '';
    if (!recentList || recentList.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No recent registrations.</td></tr>';
      return;
    }

    recentList.forEach(function (r) {
      var badgeClass = 'bg-secondary';
      var payClass = 'text-white';
      
      if (r.status === 'Confirmed' || r.status === 'confirmed') badgeClass = 'bg-success';
      if (r.status === 'Pending' || r.status === 'pending') badgeClass = 'bg-warning text-dark';
      
      if (r.payment === 'paid') payClass = 'text-success';
      if (r.payment === 'unpaid') payClass = 'text-danger';

      var row = '<tr>' +
                '<td>' + (r.name || 'Unknown') + '</td>' +
                '<td>' + (r.event_title || 'Unknown') + '</td>' +
                '<td>' + (r.date || 'Unknown') + '</td>' +
                '<td><span class="badge ' + badgeClass + '">' + r.status + '</span></td>' +
                '<td class="fw-bold ' + payClass + '">' + (r.payment || 'unpaid').toUpperCase() + '</td>' +
                '</tr>';
      tbody.innerHTML += row;
    });
  }

  function showDashboardError(msg) {
    var errorBanner = document.getElementById('analytics-error-banner');
    if (errorBanner) {
      errorBanner.classList.remove('d-none');
      errorBanner.querySelector('.error-msg-text').textContent = msg;
    }
  }

  // Global Exports Mapping
  window.exportDashboardCSV = function() {
    // Generate simple mock-CSV downloader trigger
    var csvContent = "data:text/csv;charset=utf-8,KPI,Value\n";
    csvContent += "Total Events," + document.getElementById('kpi-events-val').textContent + "\n";
    csvContent += "Total Registrations," + document.getElementById('kpi-regs-val').textContent + "\n";
    csvContent += "Total Revenue," + document.getElementById('kpi-revenue-val').textContent + "\n";
    csvContent += "Attendance Rate," + document.getElementById('kpi-attendance-val').textContent + "\n";

    var encodedUri = encodeURI(csvContent);
    var link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "sapthaevent_analytics_report.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

})();
