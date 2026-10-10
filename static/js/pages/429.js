/* Moved unchanged from an inline <script> in templates/429.html so the CSP
   needs no inline script (UPG-25). */
let t = 60;
const el = document.getElementById('timer');
const iv = setInterval(() => {
  t--;
  el.textContent = t;
  if (t <= 0) { clearInterval(iv); window.location.href = '/'; }
}, 1000);
