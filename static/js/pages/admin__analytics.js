/* Moved unchanged from an inline <script> in templates/admin/analytics.html so the CSP
   needs no inline script (UPG-25). */
// ── Data from Flask (read from data attributes — no Jinja inside JS) ──
const _d           = document.getElementById('chart-data').dataset;
const regsOverTime     = JSON.parse(_d.regsOverTime     || '{}');
const categoryData     = JSON.parse(_d.category         || '{}');
const revenueData      = JSON.parse(_d.revenue          || '{}');
const peakHoursData    = JSON.parse(_d.peakHours        || '{}');
const regsPerEventData = JSON.parse(_d.regsPerEvent     || '{}');
const funnelData       = JSON.parse(_d.funnel           || '{}');
const noShowData       = JSON.parse(_d.noShow           || '{}');

// ── Shared chart defaults ──────────────────────────────────────────
Chart.defaults.font.family  = "'Inter', sans-serif";
Chart.defaults.font.size    = 12;
Chart.defaults.color        = '#64748b';
Chart.defaults.plugins.legend.labels.boxWidth = 12;
Chart.defaults.plugins.legend.labels.padding  = 14;

// Palette
const BLUE    = '#1a2557';
const ORANGE  = '#c9a45e';
const GREEN   = '#10b981';
const PURPLE  = '#7c3aed';
const TEAL    = '#0891b2';
const PIE_COLORS = [ORANGE, BLUE, GREEN, PURPLE, TEAL,
                    '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#84cc16'];

// Helper — abbreviated labels for long event names
function abbrev(labels, max) {
  return labels.map(l => l.length > max ? l.slice(0, max) + '…' : l);
}

// ── 1. Registrations over time (line) ─────────────────────────────
(function() {
  const ctx = document.getElementById('chartRegsTime');
  if (!ctx || !regsOverTime.labels) return;
  // Show only every 5th label to avoid crowding
  const thinLabels = regsOverTime.labels.map((l, i) => i % 5 === 0 ? l.slice(5) : '');
  new Chart(ctx, {
    type: 'line',
    data: {
      labels: thinLabels,
      datasets: [{
        label: 'Registrations',
        data: regsOverTime.data,
        borderColor: ORANGE,
        backgroundColor: 'rgba(201,164,94,.08)',
        borderWidth: 2.5,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: ORANGE,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0 } },
        y: { beginAtZero: true, ticks: { precision: 0 },
             grid: { color: 'rgba(0,0,0,.05)' } }
      }
    }
  });
})();

// ── 2. Category breakdown (doughnut) ──────────────────────────────
(function() {
  const ctx = document.getElementById('chartCategory');
  if (!ctx || !categoryData.labels || !categoryData.labels.length) {
    ctx && (ctx.parentElement.innerHTML = '<div class="no-data"><i class="fas fa-chart-pie"></i>No data yet</div>');
    return;
  }
  new Chart(ctx, {
    type: 'doughnut',
    data: {
      labels: categoryData.labels,
      datasets: [{
        data: categoryData.data,
        backgroundColor: PIE_COLORS,
        borderWidth: 2,
        borderColor: '#fff',
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'bottom', labels: { padding: 12 } },
        tooltip: {
          callbacks: {
            label: ctx => ` ${ctx.label}: ${ctx.parsed} registrations`
          }
        }
      },
      cutout: '60%',
    }
  });
})();

// ── 3. Revenue per event (horizontal bar) ─────────────────────────
(function() {
  const ctx = document.getElementById('chartRevenue');
  if (!ctx || !revenueData.labels || !revenueData.labels.length) {
    ctx && (ctx.parentElement.innerHTML = '<div class="no-data"><i class="fas fa-rupee-sign"></i>No paid events yet</div>');
    return;
  }
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: abbrev(revenueData.labels, 22),
      datasets: [{
        label: 'Revenue (₹)',
        data: revenueData.data,
        backgroundColor: revenueData.data.map((_, i) =>
          i === 0 ? ORANGE : i === 1 ? '#f59e0b' : 'rgba(26, 37, 87,.18)'),
        borderColor:  'transparent',
        borderRadius: 6,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ₹${c.parsed.x.toLocaleString()}` } }
      },
      scales: {
        x: { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' },
             ticks: { callback: v => '₹' + (v >= 1000 ? (v/1000)+'k' : v) } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } }
      }
    }
  });
})();

// ── 4. Registrations per event (horizontal bar) ───────────────────
(function() {
  const ctx = document.getElementById('chartRegsEvent');
  if (!ctx || !regsPerEventData.labels || !regsPerEventData.labels.length) {
    ctx && (ctx.parentElement.innerHTML = '<div class="no-data"><i class="fas fa-calendar-alt"></i>No registrations yet</div>');
    return;
  }
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: abbrev(regsPerEventData.labels, 22),
      datasets: [{
        label: 'Registrations',
        data: regsPerEventData.data,
        backgroundColor: regsPerEventData.data.map((_, i) =>
          i === 0 ? BLUE : i === 1 ? '#185fa5' : 'rgba(26, 37, 87,.18)'),
        borderColor: 'transparent',
        borderRadius: 6,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 },
             grid: { color: 'rgba(0,0,0,.05)' } },
        y: { grid: { display: false }, ticks: { font: { size: 11 } } }
      }
    }
  });
})();

// ── 5. Peak hours (bar) ───────────────────────────────────────────
(function() {
  const ctx = document.getElementById('chartPeakHours');
  if (!ctx || !peakHoursData.labels) return;
  const maxVal = Math.max(...peakHoursData.data, 1);
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: peakHoursData.labels,
      datasets: [{
        label: 'Registrations',
        data: peakHoursData.data,
        backgroundColor: peakHoursData.data.map(v => {
          const ratio = v / maxVal;
          if (ratio > 0.7) return ORANGE;
          if (ratio > 0.4) return '#f59e0b';
          return 'rgba(26, 37, 87,.15)';
        }),
        borderColor: 'transparent',
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          title: items => `Hour: ${items[0].label}`,
          label: c => ` ${c.parsed.y} registration${c.parsed.y !== 1 ? 's' : ''}`
        }}
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 0, font: { size: 10 } } },
        y: { beginAtZero: true, ticks: { precision: 0 },
             grid: { color: 'rgba(0,0,0,.05)' } }
      }
    }
  });
})();

// ── 6. Conversion funnel (horizontal bar) ─────────────────────────
(function() {
  const ctx = document.getElementById('chartFunnel');
  if (!ctx || !funnelData.labels) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: funnelData.labels,
      datasets: [{
        label: 'Count',
        data: funnelData.data,
        backgroundColor: [BLUE, '#1a4fa0', GREEN, ORANGE],
        borderRadius: 6,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: {
          label: c => {
            const total = funnelData.data[0] || 1;
            const pct = ((c.parsed.x / total) * 100).toFixed(1);
            return ` ${c.parsed.x} (${pct}%)`;
          }
        }}
      },
      scales: {
        x: { beginAtZero: true, ticks: { precision: 0 },
             grid: { color: 'rgba(0,0,0,.05)' } },
        y: { grid: { display: false } }
      }
    }
  });
})();

// ── 7. No-show rate (bar) ─────────────────────────────────────────
(function() {
  const ctx = document.getElementById('chartNoShow');
  if (!ctx || !noShowData.labels || !noShowData.labels.length) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels: noShowData.labels,
      datasets: [{
        label: 'No-show %',
        data: noShowData.data,
        backgroundColor: noShowData.data.map(v =>
          v > 30 ? '#ef4444' : v > 15 ? '#f59e0b' : GREEN),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${c.parsed.y}%` } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 10 }, maxRotation: 35, minRotation: 25 } },
        y: { beginAtZero: true, max: 100, ticks: { callback: v => v + '%' },
             grid: { color: 'rgba(0,0,0,.05)' } }
      }
    }
  });
})();
