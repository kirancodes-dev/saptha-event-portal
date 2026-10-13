/* Event handlers from templates/coordinator/results_summary.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "coordinator/results_summary:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateAll()
  } } } },
  "coordinator/results_summary:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleCard('' + this.dataset.hA0 + '')
  } } } },
  "coordinator/results_summary:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    regenOne(event,'' + this.dataset.hA1 + '','' + this.dataset.hA2 + '')
  } } } },
});
