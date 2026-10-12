/* Analytics page (UPG-83): draws templates/analytics/hub.html from the JSON that
   services_insights.build() produced. Charts go through SE_EC (static/js/se-echarts.js). */
(function () {
  'use strict';
  var raw = document.getElementById('analytics-data');
  if (!raw || !window.SE_EC) return;
  var D = JSON.parse(raw.textContent);
  var EC = window.SE_EC;
  var fmt = EC.fmt;   // values go into HTML through escapeHtml (static/js/escape.js)

  // Filters apply as soon as they change
  var filters = document.getElementById('an-filters');
  if (filters) filters.addEventListener('change', function () { filters.submit(); });

  function link(id) { return '/spoc/event/' + encodeURIComponent(id) + '/review'; }
  function short(s, n) { s = String(s || ''); return s.length > n ? s.slice(0, n - 1) + '…' : s; }
  function money(n) { return '₹' + Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 }); }

  // ── 1. Compare events ──────────────────────────────────────────────────
  // At most four measures at once: the four hues pass the validator on every pair.
  var MEASURES = [
    { key: 'registered', name: 'Registered', slot: 0, on: true },
    { key: 'attended', name: 'Attended', slot: 2, on: true },
    { key: 'no_show', name: 'No-show', slot: 3, on: true },
    { key: 'waitlisted', name: 'Waitlisted', slot: 1, on: false },
  ];
  var measureBox = document.getElementById('cmp-measures');
  var sortSel = document.getElementById('cmp-sort');
  var limitSel = document.getElementById('cmp-limit');
  var stackSel = document.getElementById('cmp-stack');
  var findBox = document.getElementById('cmp-find');
  var compare = null;

  if (measureBox) {
    var t0 = EC.theme();
    MEASURES.forEach(function (m) {
      var label = document.createElement('label');
      var box = document.createElement('input');
      box.type = 'checkbox'; box.checked = m.on; box.value = m.key;
      var sw = document.createElement('span');
      sw.className = 'sw'; sw.style.background = t0.palette[m.slot]; sw.setAttribute('aria-hidden', 'true');
      label.appendChild(box); label.appendChild(sw); label.appendChild(document.createTextNode(m.name));
      box.addEventListener('change', function () { m.on = box.checked; drawCompare(); });
      measureBox.appendChild(label);
    });
    // Dark mode can shift the swatches
    new MutationObserver(function () {
      var t = EC.theme();
      measureBox.querySelectorAll('.sw').forEach(function (sw, i) { sw.style.background = t.palette[MEASURES[i].slot]; });
    }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }

  function sortedEvents() {
    var key = sortSel ? sortSel.value : 'registered';
    var q = findBox ? findBox.value.trim().toLowerCase() : '';
    var rows = D.events.filter(function (e) { return !q || e.title.toLowerCase().indexOf(q) !== -1; });
    rows = rows.slice().sort(function (a, b) {
      if (key === 'title') return a.title.localeCompare(b.title);
      if (key === 'date') return String(b.date).localeCompare(String(a.date));
      var av = a[key] == null ? -1 : a[key], bv = b[key] == null ? -1 : b[key];
      return bv - av || a.title.localeCompare(b.title);
    });
    var n = limitSel ? parseInt(limitSel.value, 10) : 10;
    return n ? rows.slice(0, n) : rows;
  }

  // "Breakdown" stacks parts that add up to the registrations, never measures
  // that overlap (attended is part of registered)
  var PARTS = [
    { key: 'attended', name: 'Attended', slot: 2 },
    { key: 'no_show', name: 'No-show', slot: 3 },
    { key: 'upcoming', name: 'Not held yet', slot: 0 },
    { key: 'other', name: 'Waitlisted, pending or cancelled', other: true },
  ];
  function compareOption(t) {
    var rows = sortedEvents();
    var breakdown = stackSel && stackSel.value === 'stack';
    var shown = breakdown ? PARTS : MEASURES.filter(function (m) { return m.on; });
    // Top of the list at the top of the chart
    var cats = rows.map(function (e) { return e.title; }).reverse();
    var series = shown.map(function (m, i) {
      var last = i === shown.length - 1;
      return {
        name: m.name, type: 'bar', stack: breakdown ? 'all' : undefined,
        itemStyle: { color: m.other ? t.other : t.palette[m.slot],
                     borderRadius: breakdown ? (last ? [0, 4, 4, 0] : 0) : [0, 4, 4, 0],
                     borderColor: t.surface, borderWidth: breakdown ? 1 : 0 },
        barMaxWidth: breakdown ? 20 : 16, barGap: '20%', emphasis: { focus: 'series' },
        data: rows.map(function (e) { return e[m.key]; }).reverse(),
      };
    });
    var visible = 14;
    var many = cats.length > visible;
    var o = EC.base(t, {
      grid: { left: 14, right: many ? 40 : 16, top: 36, bottom: 8, containLabel: true },
      legend: Object.assign(EC.base(t).legend, { data: shown.map(function (m) { return m.name; }) }),
      tooltip: Object.assign(EC.base(t).tooltip, {
        trigger: 'axis', axisPointer: { type: 'shadow', shadowStyle: { color: t.dark ? 'rgba(255,255,255,.05)' : 'rgba(0,24,94,.05)' } },
        formatter: function (items) {
          if (!items.length) return '';
          var e = rows[rows.length - 1 - items[0].dataIndex];
          var html = '<div style="font-weight:700;margin-bottom:4px;max-width:280px;white-space:normal">' + escapeHtml(e.title) + '</div>' +
            '<div style="opacity:.75;margin-bottom:6px">' + escapeHtml(e.category) + ' · ' + escapeHtml(e.date || 'no date') + ' · ' + escapeHtml(String(e.status).replace(/_/g, ' ')) + '</div>';
          if (breakdown) html += 'Registered: <b>' + escapeHtml(fmt(e.registered)) + '</b><br>';
          items.forEach(function (it) { var markerHtml = it.marker; html += markerHtml + escapeHtml(it.seriesName) + ': <b>' + escapeHtml(fmt(it.value)) + '</b><br>'; });
          html += '<div style="margin-top:6px;opacity:.85">Attendance ' + escapeHtml(e.attendance_rate == null ? '—' : e.attendance_rate + '%') +
                  ' · Cancelled ' + escapeHtml(e.cancelled) + ' · Revenue ' + escapeHtml(money(e.revenue)) +
                  escapeHtml(e.capacity ? ' · Filled ' + e.fill_rate + '% of ' + e.capacity : '') + '</div>' +
                  '<div style="margin-top:4px;opacity:.6">Click to open the event</div>';
          return html;
        },
      }),
      xAxis: EC.valueAxis(t, { minInterval: 1 }),
      yAxis: EC.categoryAxis(t, cats, {
        axisLabel: { color: t.inkStrong, width: t.narrow ? Math.round(t.width * 0.34) : 200, overflow: 'truncate',
                     fontSize: t.narrow ? 11 : 12, formatter: function (v) { return short(v, t.narrow ? 18 : 34); } },
        triggerEvent: true,
      }),
      series: series,
    });
    if (many) {
      o.dataZoom = [
        { type: 'slider', yAxisIndex: 0, right: 4, width: 14, start: 100 - (visible / cats.length) * 100, end: 100,
          zoomLock: false, brushSelect: false, showDetail: false, handleSize: '120%',
          fillerColor: t.dark ? 'rgba(74,105,214,.25)' : 'rgba(59,91,201,.15)', borderColor: t.axis,
          backgroundColor: t.sunken, dataBackground: { lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 } } },
        { type: 'inside', yAxisIndex: 0, zoomOnMouseWheel: false, moveOnMouseWheel: true, moveOnMouseMove: false },
      ];
    }
    return o;
  }

  function drawCompare() {
    if (!compare) return;
    // The measure picker applies to side-by-side bars only
    if (measureBox) {
      var breakdown = stackSel && stackSel.value === 'stack';
      measureBox.querySelectorAll('input').forEach(function (b) { b.disabled = breakdown; });
      measureBox.style.opacity = breakdown ? 0.5 : '';
    }
    compare.update();
    drawTable();
  }

  var cmpEl = document.getElementById('ch-compare');
  if (cmpEl) {
    compare = EC.mount(cmpEl, compareOption);
    compare.chart.on('click', function (p) {
      var rows = sortedEvents();
      var idx = p.componentType === 'yAxis' ? rows.length - 1 - rows.map(function (e) { return e.title; }).reverse().indexOf(p.value) : rows.length - 1 - p.dataIndex;
      if (rows[idx]) window.location.href = link(rows[idx].id);
    });
    [sortSel, limitSel, stackSel].forEach(function (el) { if (el) el.addEventListener('change', drawCompare); });
    if (findBox) findBox.addEventListener('input', drawCompare);
  }

  // Chart / table views
  document.querySelectorAll('[data-view]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var view = btn.getAttribute('data-view');
      document.querySelectorAll('[data-view]').forEach(function (b) { b.setAttribute('aria-pressed', String(b === btn)); });
      document.querySelectorAll('[data-pane]').forEach(function (p) { p.hidden = p.getAttribute('data-pane') !== view; });
      if (view === 'chart' && compare) compare.chart.resize();
    });
  });

  // Sortable table of every event (the accessible view of the comparison)
  var COLS = [
    { key: 'title', name: 'Event' }, { key: 'category', name: 'Category' }, { key: 'date', name: 'Date' },
    { key: 'status', name: 'Status' }, { key: 'registered', name: 'Registered', num: true },
    { key: 'confirmed', name: 'Confirmed', num: true }, { key: 'attended', name: 'Attended', num: true },
    { key: 'attendance_rate', name: 'Attendance', num: true, pct: true }, { key: 'no_show', name: 'No-show', num: true },
    { key: 'waitlisted', name: 'Waitlisted', num: true }, { key: 'cancelled', name: 'Cancelled', num: true },
    { key: 'fill_rate', name: 'Capacity filled', num: true, pct: true }, { key: 'revenue', name: 'Revenue', num: true, money: true },
  ];
  var tableSort = { key: 'registered', dir: -1 };
  function drawTable() {
    var table = document.getElementById('cmp-table');
    if (!table) return;
    var q = findBox ? findBox.value.trim().toLowerCase() : '';
    var rows = D.events.filter(function (e) { return !q || e.title.toLowerCase().indexOf(q) !== -1; }).slice();
    rows.sort(function (a, b) {
      var av = a[tableSort.key], bv = b[tableSort.key];
      if (typeof av === 'string' || typeof bv === 'string') return tableSort.dir * String(av || '').localeCompare(String(bv || ''));
      return tableSort.dir * ((av == null ? -1 : av) - (bv == null ? -1 : bv));
    });
    var headHtml = '<tr>' + COLS.map(function (c) {
      var state = tableSort.key === c.key ? (tableSort.dir > 0 ? 'ascending' : 'descending') : 'none';
      return '<th scope="col" class="' + (c.num ? 'num' : '') + '" aria-sort="' + escapeHtml(state) + '"><button type="button" data-sort="' + escapeHtml(c.key) + '">' +
        escapeHtml(c.name + (state === 'none' ? '' : (state === 'ascending' ? ' ▲' : ' ▼'))) + '</button></th>';
    }).join('') + '</tr>';
    table.tHead.innerHTML = headHtml;
    table.tBodies[0].innerHTML = rows.map(function (e) {
      return '<tr>' + COLS.map(function (c) {
        var v = e[c.key];
        if (c.key === 'title') return '<td><a href="' + safeUrl(link(e.id)) + '">' + escapeHtml(v) + '</a></td>';
        if (c.key === 'status') return '<td>' + escapeHtml(String(v || '').replace(/_/g, ' ')) + '</td>';
        var text = v == null ? '—' : c.money ? money(v) : c.pct ? v + '%' : fmt(v);
        return '<td class="' + (c.num ? 'num' : '') + '">' + escapeHtml(text) + '</td>';
      }).join('') + '</tr>';
    }).join('');
    table.tHead.querySelectorAll('button[data-sort]').forEach(function (b) {
      b.addEventListener('click', function () {
        var k = b.getAttribute('data-sort');
        tableSort = { key: k, dir: tableSort.key === k ? -tableSort.dir : (k === 'title' || k === 'category' || k === 'status' ? 1 : -1) };
        drawTable();
      });
    });
  }
  drawTable();

  // ── 2. Registrations over time ─────────────────────────────────────────
  var split = 'total';
  function trendOption(t) {
    var T = D.trend;
    var labels = T.labels.map(function (d) { return d.slice(5); });
    var series;
    if (split === 'category' && T.by_category.length) {
      // Colour follows the category: the server's fixed list of four keeps its
      // colours whatever the period or filter; any other category is "Other"
      var order = D.colour_categories, groups = [], other = null;
      T.by_category.forEach(function (c) {
        var slot = order.indexOf(c.name);
        if (slot > -1) groups.push({ name: c.name, data: c.data, color: t.palette[slot], slot: slot });
        else if (!other) other = { name: 'Other', data: c.data.slice(), color: t.other, slot: 9 };
        else other.data = other.data.map(function (v, i) { return v + c.data[i]; });
      });
      groups.sort(function (a, b) { return a.slot - b.slot; });
      if (other) groups.push(other);
      series = groups.map(function (c) {
        return { name: c.name, type: 'line', stack: 'all', smooth: 0.2, showSymbol: false, data: c.data,
                 lineStyle: { width: 1.5, color: c.color }, itemStyle: { color: c.color },
                 areaStyle: { color: c.color, opacity: 0.55 }, emphasis: { focus: 'series' } };
      });
    } else {
      series = [{ name: 'Registrations', type: 'line', smooth: 0.2, showSymbol: false, symbolSize: 8, data: T.total,
                  lineStyle: { width: 2, color: t.palette[0] }, itemStyle: { color: t.palette[0] },
                  areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: t.dark ? 'rgba(59,91,201,.35)' : 'rgba(59,91,201,.22)' },
                    { offset: 1, color: 'rgba(59,91,201,0)' }]) } }];
    }
    var o = EC.base(t, {
      grid: { left: 14, right: 16, top: 36, bottom: 44, containLabel: true },
      legend: Object.assign(EC.base(t).legend, { show: split === 'category' }),
      tooltip: Object.assign(EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.axis } },
        formatter: function (items) {
          var day = T.labels[items[0].dataIndex];
          var html = '<b>' + escapeHtml(T.weekly ? 'Week of ' + day : day) + '</b><br>';
          var total = 0;
          items.forEach(function (it) { var markerHtml = it.marker; total += it.value || 0; html += markerHtml + escapeHtml(it.seriesName) + ': <b>' + escapeHtml(fmt(it.value)) + '</b><br>'; });
          if (items.length > 1) html += 'Total: <b>' + escapeHtml(fmt(total)) + '</b>';
          return html;
        } }),
      xAxis: EC.categoryAxis(t, labels, { boundaryGap: false }),
      yAxis: EC.valueAxis(t, { minInterval: 1 }),
      dataZoom: [
        { type: 'slider', xAxisIndex: 0, bottom: 4, height: 18, showDetail: false, brushSelect: false, borderColor: t.axis,
          backgroundColor: t.sunken, fillerColor: t.dark ? 'rgba(74,105,214,.25)' : 'rgba(59,91,201,.15)',
          dataBackground: { lineStyle: { color: t.axis }, areaStyle: { color: t.grid } } },
        { type: 'inside', xAxisIndex: 0 },
      ],
      series: series,
    });
    return o;
  }
  var trend = EC.mount(document.getElementById('ch-trend'), trendOption);
  document.querySelectorAll('[data-split]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      split = btn.getAttribute('data-split');
      document.querySelectorAll('[data-split]').forEach(function (b) { b.setAttribute('aria-pressed', String(b === btn)); });
      if (trend) trend.update();
    });
  });

  // ── 3. Categories ──────────────────────────────────────────────────────
  EC.mount(document.getElementById('ch-category'), function (t) {
    var rows = D.categories.slice().reverse();
    return EC.base(t, {
      legend: { show: false },
      grid: { left: 14, right: 40, top: 36, bottom: 8, containLabel: true },
      tooltip: Object.assign(EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (items) {
          var c = rows[items[0].dataIndex];
          return '<b>' + escapeHtml(c.name) + '</b><br>' + escapeHtml(fmt(c.registrations)) + ' registrations<br>' +
                 escapeHtml(c.events) + ' event' + (c.events === 1 ? '' : 's') + ' · ' + escapeHtml(fmt(c.attended)) + ' attended<br>Revenue ' + escapeHtml(money(c.revenue));
        } }),
      xAxis: EC.valueAxis(t, { minInterval: 1 }),
      yAxis: EC.categoryAxis(t, rows.map(function (c) { return c.name; }), { axisLabel: { color: t.inkStrong } }),
      series: [{ name: 'Registrations', type: 'bar', barMaxWidth: 22, data: rows.map(function (c) { return c.registrations; }),
                 itemStyle: { color: t.palette[0], borderRadius: [0, 4, 4, 0] },
                 label: { show: true, position: 'right', color: t.ink, formatter: function (p) { return fmt(p.value); } } }],
    });
  });

  // ── 4. Funnel ──────────────────────────────────────────────────────────
  EC.mount(document.getElementById('ch-funnel'), function (t) {
    var F = D.funnel, top = F[0].value || 0;
    var rows = F.slice().reverse();
    return EC.base(t, {
      legend: { show: false },
      grid: { left: 14, right: 90, top: 30, bottom: 8, containLabel: true },
      tooltip: Object.assign(EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (items) {
          var i = F.length - 1 - items[0].dataIndex, cur = F[i], prev = F[i - 1];
          return '<b>' + escapeHtml(cur.stage) + '</b>: ' + escapeHtml(fmt(cur.value)) + '<br>' +
                 escapeHtml(top ? (cur.value * 100 / top).toFixed(1) + '% of registrations' : '') +
                 (prev && prev.value ? '<br>' : '') + escapeHtml(prev && prev.value ? (cur.value * 100 / prev.value).toFixed(1) + '% of ' + prev.stage.toLowerCase() : '');
        } }),
      xAxis: EC.valueAxis(t, { minInterval: 1 }),
      yAxis: EC.categoryAxis(t, rows.map(function (f) { return f.stage; }), { axisLabel: { color: t.inkStrong, fontWeight: 600 } }),
      series: [{ name: 'People', type: 'bar', barMaxWidth: 26, data: rows.map(function (f) { return f.value; }),
                 itemStyle: { color: t.palette[0], borderRadius: [0, 4, 4, 0] },
                 label: { show: true, position: 'right', color: t.ink,
                          formatter: function (p) { return fmt(p.value) + (top ? '  ·  ' + (p.value * 100 / top).toFixed(0) + '%' : ''); } } }],
    });
  });

  // ── 5. Weekday × hour heatmap ──────────────────────────────────────────
  EC.mount(document.getElementById('ch-heat'), function (t) {
    var hours = []; for (var h = 0; h < 24; h++) hours.push((h < 10 ? '0' : '') + h);
    var max = 0; D.heatmap.forEach(function (c) { if (c[2] > max) max = c[2]; });
    var cells = D.heatmap.map(function (c) { return c[2] ? c : { value: c, itemStyle: { color: t.sunken } }; });
    return EC.base(t, {
      legend: { show: false },
      grid: { left: 14, right: 8, top: 30, bottom: 48, containLabel: true },
      tooltip: Object.assign(EC.base(t).tooltip, { formatter: function (p) {
        var v = p.value || p.data.value;
        return '<b>' + escapeHtml(D.weekdays[v[1]]) + ' ' + escapeHtml(hours[v[0]]) + ':00–' + escapeHtml(hours[v[0]]) + ':59</b><br>' + escapeHtml(fmt(v[2])) + ' registration' + (v[2] === 1 ? '' : 's');
      } }),
      xAxis: EC.categoryAxis(t, hours, { splitArea: { show: false }, axisLabel: { color: t.ink, interval: 1 } }),
      yAxis: EC.categoryAxis(t, D.weekdays, { inverse: true, axisLine: { show: false } }),
      visualMap: { min: 1, max: Math.max(max, 1), calculable: false, orient: 'horizontal', left: 'center', bottom: 0,
                   itemWidth: 10, itemHeight: 120, text: ['More', 'Fewer'], textStyle: { color: t.ink }, inRange: { color: t.ramp } },
      series: [{ name: 'Registrations', type: 'heatmap', data: cells, itemStyle: { borderColor: t.surface, borderWidth: 2, borderRadius: 3 },
                 emphasis: { itemStyle: { borderColor: t.inkStrong, borderWidth: 1 } } }],
    });
  });

  // ── 6. Revenue by event ────────────────────────────────────────────────
  var paid = D.events.filter(function (e) { return e.revenue > 0; }).sort(function (a, b) { return b.revenue - a.revenue; });
  var revEl = document.getElementById('ch-revenue');
  if (revEl && !paid.length) {
    revEl.outerHTML = '<p class="text-muted text-center py-5 mb-0"><i class="fas fa-indian-rupee-sign d-block mb-2 fs-3 opacity-50" aria-hidden="true"></i>No fees collected in this period.</p>';
  } else {
    EC.mount(revEl, function (t) {
      var rows = paid.slice().reverse(), visible = 10, many = rows.length > visible;
      var o = EC.base(t, {
        legend: { show: false },
        grid: { left: 14, right: many ? 70 : 56, top: 36, bottom: 8, containLabel: true },
        tooltip: Object.assign(EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: function (items) { var e = rows[items[0].dataIndex];
            return '<b>' + escapeHtml(e.title) + '</b><br>' + escapeHtml(money(e.revenue)) + ' from ' + escapeHtml(fmt(e.registered)) + ' registrations'; } }),
        xAxis: EC.valueAxis(t, { axisLabel: { color: t.ink, formatter: function (v) { return v >= 1000 ? '₹' + v / 1000 + 'k' : '₹' + v; } } }),
        yAxis: EC.categoryAxis(t, rows.map(function (e) { return e.title; }), { axisLabel: { color: t.inkStrong, width: t.narrow ? Math.round(t.width * 0.3) : 170, overflow: 'truncate' } }),
        series: [{ name: 'Revenue', type: 'bar', barMaxWidth: 18, data: rows.map(function (e) { return e.revenue; }),
                   itemStyle: { color: t.palette[0], borderRadius: [0, 4, 4, 0] },
                   label: { show: true, position: 'right', color: t.ink, formatter: function (p) { return money(p.value); } } }],
      });
      if (many) o.dataZoom = [{ type: 'slider', yAxisIndex: 0, right: 4, width: 12, start: 100 - visible / rows.length * 100, end: 100,
                                 showDetail: false, brushSelect: false, borderColor: t.axis, backgroundColor: t.sunken },
                               { type: 'inside', yAxisIndex: 0, zoomOnMouseWheel: false, moveOnMouseWheel: true }];
      return o;
    }).chart.on('click', function (p) { var rows = paid.slice().reverse(); if (rows[p.dataIndex]) window.location.href = link(rows[p.dataIndex].id); });
  }

  // ── 7. No-show rate ────────────────────────────────────────────────────
  var ns = D.no_shows;
  var nsEl = document.getElementById('ch-noshow');
  if (nsEl && !ns.length) {
    nsEl.outerHTML = '<p class="text-muted text-center py-5 mb-0"><i class="fas fa-user-check d-block mb-2 fs-3 opacity-50" aria-hidden="true"></i>No event in this period has happened yet.</p>';
  } else {
    EC.mount(nsEl, function (t) {
      var rows = ns.slice().reverse(), visible = 10, many = rows.length > visible;
      // Status colours are reserved for this kind of judgement and always carry a text label
      function level(r) { return r > 30 ? ['critical', 'High'] : r > 15 ? ['warning', 'Watch'] : ['good', 'OK']; }
      var o = EC.base(t, {
        legend: { show: false },
        grid: { left: 14, right: many ? 96 : 84, top: 36, bottom: 8, containLabel: true },
        tooltip: Object.assign(EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: function (items) { var e = rows[items[0].dataIndex];
            return '<b>' + escapeHtml(e.title) + '</b><br>' + escapeHtml(e.rate) + '% no-show (' + escapeHtml(level(e.rate)[1]) + ')<br>' +
                   escapeHtml(fmt(e.no_show)) + ' of ' + escapeHtml(fmt(e.confirmed)) + ' confirmed didn\'t attend'; } }),
        xAxis: EC.valueAxis(t, { max: 100, axisLabel: { color: t.ink, formatter: '{value}%' } }),
        yAxis: EC.categoryAxis(t, rows.map(function (e) { return e.title; }), { axisLabel: { color: t.inkStrong, width: t.narrow ? Math.round(t.width * 0.3) : 170, overflow: 'truncate' } }),
        series: [{ name: 'No-show %', type: 'bar', barMaxWidth: 18,
                   data: rows.map(function (e) { return { value: e.rate, itemStyle: { color: t.status[level(e.rate)[0]], borderRadius: [0, 4, 4, 0] } }; }),
                   label: { show: true, position: 'right', color: t.ink,
                            formatter: function (p) { return p.value + '% · ' + level(p.value)[1]; } },
                   markLine: { silent: true, symbol: 'none', label: { formatter: '30%', color: t.ink }, lineStyle: { color: t.status.critical, type: 'dashed', opacity: 0.6 },
                               data: [{ xAxis: 30 }] } }],
      });
      if (many) o.dataZoom = [{ type: 'slider', yAxisIndex: 0, right: 4, width: 12, start: 100 - visible / rows.length * 100, end: 100,
                                 showDetail: false, brushSelect: false, borderColor: t.axis, backgroundColor: t.sunken },
                               { type: 'inside', yAxisIndex: 0, zoomOnMouseWheel: false, moveOnMouseWheel: true }];
      return o;
    }).chart.on('click', function (p) { var rows = ns.slice().reverse(); if (rows[p.dataIndex]) window.location.href = link(rows[p.dataIndex].id); });
  }
})();
