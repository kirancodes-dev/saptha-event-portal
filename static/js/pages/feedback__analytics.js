/* Moved unchanged from an inline <script> in templates/feedback/analytics.html so the CSP
   needs no inline script (UPG-25). */
var dist = JSON.parse(document.getElementById('dist-data').textContent);
new Chart(document.getElementById('distChart'), {
  type: 'bar',
  data: {
    labels: ['1 ★','2 ★','3 ★','4 ★','5 ★'],
    datasets:[{
      data: dist,
      backgroundColor:['#ef4444','#f97316','#eab308','#84cc16','#22c55e'],
      borderRadius: 8, borderSkipped: false,
    }]
  },
  options:{
    responsive:true,
    plugins:{legend:{display:false}},
    scales:{
      x:{grid:{display:false}},
      y:{grid:{color:'#f1f5f9'},ticks:{stepSize:1},beginAtZero:true}
    }
  }
});
