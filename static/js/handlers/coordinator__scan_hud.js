/* Event handlers from templates/coordinator/scan_hud.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "coordinator/scan_hud:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    promptManualEntry()
  } } } },
  "coordinator/scan_hud:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    syncLocalQueue()
  } } } },
});
