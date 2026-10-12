/* se-echarts.js — the portal's Apache ECharts layer (UPG-83). Load right after echarts.min.js.

   - Theme from the design tokens; redrawn when the header's dark-mode toggle flips.
   - Categorical colours: four hues that pass the dataviz validator on EVERY pair
     (--pairs all), on the light surface #ffffff and the dark surface #121a30
     (dark: the blue is a contrast WARN, relieved by the legend and the table view).
     Four is the most any chart shows at once; a fifth series folds into "Other"
     (neutral grey). Assign by the entity, never by rank.
   - Every chart gets "download as PNG" and "show as table" (the table is the
     accessible view of the same numbers); charts resize with their card.

   SE_EC.mount(el, buildOption) — buildOption(theme) returns an ECharts option;
   it is called again on theme change. Returns { chart, update(buildOption) }. */
(function () {
  'use strict';
  if (!window.echarts) return;

  var LIGHT = ['#3b5bc9', '#b7791f', '#0f8fb0', '#db2777'];
  var DARK  = ['#3b5bc9', '#b7791f', '#0f8fb0', '#db2777'];
  var OTHER = '#94a3b8';
  var mounted = [];

  function tok(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name);
    return (v || '').trim() || fallback;
  }
  function isDark() { return document.documentElement.getAttribute('data-theme') === 'dark'; }

  function theme() {
    var dark = isDark();
    return {
      dark: dark,
      palette: dark ? DARK : LIGHT,
      other: OTHER,
      /* sequential ramp (one hue, light to dark) for the heatmap */
      ramp: dark ? ['#3350a6', '#4a69d6', '#7f97ec', '#c3cffb'] : ['#9aabe8', '#6b82d8', '#3b5bc9', '#00185e'],
      ink: tok('--text-muted', dark ? '#b6c2d4' : '#475569'),
      inkStrong: tok('--text-strong', dark ? '#f1f5f9' : '#0b1530'),
      grid: tok('--divider', dark ? '#1c2640' : '#edf0f5'),
      axis: tok('--border', dark ? '#243049' : '#e2e8f0'),
      surface: tok('--surface-card', dark ? '#121a30' : '#ffffff'),
      sunken: tok('--surface-sunken', dark ? '#0f1629' : '#f8fafc'),
      navy: dark ? '#4a69d6' : '#00185e',
      gold: '#c69d67',
      status: { good: '#16a34a', warning: '#d97706', critical: '#dc2626', neutral: '#94a3b8' },
      font: "'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif",
    };
  }

  function fmt(n) {
    if (n == null || n === '') return '—';
    return typeof n === 'number' ? n.toLocaleString('en-IN', { maximumFractionDigits: 1 }) : String(n);
  }

  /* "Show as table": the same numbers as a table, built from DOM nodes (text
     only, so nothing in the data can become markup). */
  function cell(tag, text, cls, scope) {
    var el = document.createElement(tag);
    el.textContent = text == null ? '' : String(text);
    if (cls) el.className = cls;
    if (scope) el.setAttribute('scope', scope);
    return el;
  }
  function tableFrom(headers, rows) {
    var wrap = document.createElement('div');
    wrap.className = 'se-ec-table';
    var table = document.createElement('table');
    table.className = 'table table-sm';
    var tr = document.createElement('tr');
    headers.forEach(function (h, i) { tr.appendChild(cell('th', h, i ? 'text-end' : '', 'col')); });
    table.appendChild(document.createElement('thead')).appendChild(tr);
    var body = table.appendChild(document.createElement('tbody'));
    rows.forEach(function (r) {
      var row = document.createElement('tr');
      r.forEach(function (v, i) { row.appendChild(i ? cell('td', v, 'text-end') : cell('th', v, '', 'row')); });
      body.appendChild(row);
    });
    wrap.appendChild(table);
    return wrap;
  }
  function optionToTable(opt) {
    var series = (opt.series || []).filter(function (s) { return s.type !== 'heatmap'; });
    var axis = [].concat(opt.yAxis || [], opt.xAxis || []).filter(function (a) { return a && a.type === 'category'; })[0];
    var cats = axis ? axis.data : (series[0] && series[0].data || []).map(function (d) { return d.name; });
    var rows = (cats || []).map(function (c, i) {
      return [c && c.value !== undefined ? c.value : c].concat(series.map(function (s) {
        var d = (s.data || [])[i];
        var v = d && typeof d === 'object' && !Array.isArray(d) ? d.value : d;
        return fmt(Array.isArray(v) ? v[v.length - 1] : v);
      }));
    });
    return tableFrom([''].concat(series.map(function (s) { return s.name || ''; })), rows);
  }
  function heatmapTable(opt) {
    // getOption() gives every component as a list
    var x = [].concat(opt.xAxis)[0].data, y = [].concat(opt.yAxis)[0].data, cells = {};
    (opt.series[0].data || []).forEach(function (d) { var v = d.value || d; cells[v[1] + ':' + v[0]] = v[2]; });
    return tableFrom([''].concat(x), y.map(function (day, yi) {
      return [day].concat(x.map(function (_, xi) { return cells[yi + ':' + xi] || 0; }));
    }));
  }

  /* Shared pieces every chart option starts from. */
  function base(t, extra) {
    var o = {
      color: t.palette,
      backgroundColor: 'transparent',
      textStyle: { fontFamily: t.font, color: t.ink, fontSize: 12 },
      animationDuration: 500,
      grid: { left: 14, right: 16, top: 36, bottom: 8, containLabel: true },
      tooltip: {
        backgroundColor: t.dark ? '#0b1530' : '#0b1530', borderWidth: 0, padding: [8, 12],
        textStyle: { color: '#f1f5f9', fontFamily: t.font, fontSize: 12 },
        extraCssText: 'border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25);',
      },
      legend: { top: 0, left: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 10,
                textStyle: { color: t.ink, fontSize: 12 }, inactiveColor: t.axis },
      toolbox: {
        right: 0, top: -4, itemSize: 14, itemGap: 10,
        iconStyle: { borderColor: t.ink }, emphasis: { iconStyle: { borderColor: t.inkStrong } },
        feature: {
          dataView: { show: true, readOnly: true, title: 'Show as table', lang: ['Data', 'Close', 'Refresh'],
                      backgroundColor: t.surface, textColor: t.inkStrong, buttonColor: t.navy,
                      optionToContent: function (opt) {
                        return opt.series && opt.series[0] && opt.series[0].type === 'heatmap'
                          ? heatmapTable(opt) : optionToTable(opt);
                      } },
          saveAsImage: { show: true, title: 'Download PNG', pixelRatio: 2, backgroundColor: t.surface },
        },
      },
    };
    return Object.assign(o, extra || {});
  }

  function valueAxis(t, extra) {
    extra = extra || {};
    if (extra.axisLabel) extra = Object.assign({}, extra, { axisLabel: Object.assign({ color: t.ink, hideOverlap: true }, extra.axisLabel) });
    return Object.assign({
      type: 'value', axisLine: { show: false }, axisTick: { show: false }, splitNumber: t.narrow ? 3 : 5,
      axisLabel: { color: t.ink, hideOverlap: true }, splitLine: { lineStyle: { color: t.grid } },
    }, extra || {});
  }
  function categoryAxis(t, data, extra) {
    return Object.assign({
      type: 'category', data: data, axisTick: { show: false },
      axisLine: { lineStyle: { color: t.axis } }, axisLabel: { color: t.ink },
    }, extra || {});
  }

  function mount(el, build) {
    if (!el) return null;
    var chart = echarts.init(el, null, { renderer: 'canvas' });
    var entry = { el: el, chart: chart, build: build, narrow: null };
    entry.update = function (nextBuild) {
      if (nextBuild) entry.build = nextBuild;
      var t = theme();
      t.width = el.clientWidth || 600;
      t.narrow = entry.narrow = t.width < 560;   // phones: shorter labels, fewer ticks
      chart.setOption(entry.build(t), { notMerge: true });
    };
    entry.update();
    function resized() {
      chart.resize();
      if ((el.clientWidth < 560) !== entry.narrow) entry.update();
    }
    if (window.ResizeObserver) new ResizeObserver(resized).observe(el);
    else window.addEventListener('resize', resized);
    mounted.push(entry);
    return entry;
  }

  // Redraw every chart when the dark-mode toggle flips
  new MutationObserver(function () {
    mounted.forEach(function (m) { m.update(); });
  }).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

  window.SE_EC = { mount: mount, theme: theme, base: base, valueAxis: valueAxis,
                   categoryAxis: categoryAxis, fmt: fmt };
})();
