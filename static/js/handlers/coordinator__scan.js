/* Event handlers from templates/coordinator/scan.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "coordinator/scan:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    startCamera()
  } } } },
  "coordinator/scan:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    fetchTicket(document.getElementById('manual_id').value)
  } } } },
  "coordinator/scan:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    resetScanner()
  } } } },
  "coordinator/scan:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    submitGranularAttendance()
  } } } },
});
