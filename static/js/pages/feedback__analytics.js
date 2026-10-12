/* Star distribution on Apache ECharts via SE_EC (UPG-83). Ratings are ordered, so one
   hue with labelled counts; no red-to-green scale (status colours mean status). */
(function () {
  var dist = JSON.parse(document.getElementById('dist-data').textContent);
  if (!window.SE_EC) return;
  var total = dist.reduce(function (a, b) { return a + b; }, 0);
  var labels = ['1 star', '2 stars', '3 stars', '4 stars', '5 stars'];
  SE_EC.mount(document.getElementById('distChart'), function (t) {
    return SE_EC.base(t, {
      legend: { show: false }, toolbox: { show: false },
      grid: { left: 14, right: 70, top: 8, bottom: 8, containLabel: true },
      tooltip: Object.assign(SE_EC.base(t).tooltip, { trigger: 'axis', axisPointer: { type: 'shadow' },
        formatter: function (items) { var v = items[0].value;
          return '<b>' + escapeHtml(labels[items[0].dataIndex]) + '</b><br>' + escapeHtml(v) + ' review' + (v === 1 ? '' : 's') +
                 escapeHtml(total ? ' · ' + Math.round(v * 100 / total) + '%' : ''); } }),
      xAxis: SE_EC.valueAxis(t, { minInterval: 1 }),
      yAxis: SE_EC.categoryAxis(t, labels, { inverse: true, axisLabel: { color: t.inkStrong, fontWeight: 600 } }),
      series: [{ name: 'Reviews', type: 'bar', barMaxWidth: 22, data: dist,
                 itemStyle: { color: t.palette[0], borderRadius: [0, 4, 4, 0] },
                 label: { show: true, position: 'right', color: t.ink,
                          formatter: function (p) { return p.value + (total ? '  ·  ' + Math.round(p.value * 100 / total) + '%' : ''); } } }],
    });
  });
})();
