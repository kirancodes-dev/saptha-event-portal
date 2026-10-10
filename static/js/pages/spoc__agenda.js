/* Moved unchanged from an inline <script> in templates/spoc/agenda.html so the CSP
   needs no inline script (UPG-25). */
var rowCount = document.querySelectorAll('.agenda-row').length;
function addRow() {
  rowCount++;
  var c = document.getElementById('rows-container');
  var p = c.querySelector('p');
  if (p) p.remove();
  var div = document.createElement('div');
  div.className = 'd-flex gap-3 align-items-start mb-3 agenda-row';
  div.innerHTML = '<div class="row-num">' + escapeHtml(rowCount) + '</div>' +
    '<div class="row g-2 flex-grow-1">' +
    '<div class="col-auto"><input type="time" name="time[]" class="form-control form-control-sm" style="width:110px;" required></div>' +
    '<div class="col"><input type="text" name="title[]" placeholder="Item title" class="form-control form-control-sm" required></div>' +
    '<div class="col-12"><input type="text" name="desc[]" placeholder="Details (optional)" class="form-control form-control-sm"></div>' +
    '</div>' +
    '<button type="button" class="remove-row" data-h-click="se:call" data-call="removeRow"><i class="fas fa-trash-alt"></i></button>';
  c.appendChild(div);
}

function removeRow(btn) {
  btn.closest('.agenda-row').remove();
  document.querySelectorAll('.row-num').forEach(function(n, i){ n.textContent = i + 1; });
}
