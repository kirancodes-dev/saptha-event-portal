/* The schedule builder's rows (templates/spoc/agenda.html). A new row is a copy
   of the page's blank row (<template id="agenda-row-template">), so the two
   can't differ (UPG-272). No inline script: the CSP allows none (UPG-25). */
function renumberRows() {
  document.querySelectorAll('#rows-container .row-num').forEach(function (n, i) { n.textContent = i + 1; });
}

function addRow() {
  var container = document.getElementById('rows-container');
  var empty = container.querySelector('[data-empty]');
  if (empty) empty.remove();
  var blank = document.getElementById('agenda-row-template').content.cloneNode(true);
  container.appendChild(blank);
  renumberRows();
  if (window.SE_bindHandlers) window.SE_bindHandlers(container);
  var rows = container.querySelectorAll('.agenda-row');
  var first = rows[rows.length - 1].querySelector('input[name="time[]"]');
  if (first) first.focus();
}

function removeRow(btn) {
  btn.closest('.agenda-row').remove();
  renumberRows();
}
