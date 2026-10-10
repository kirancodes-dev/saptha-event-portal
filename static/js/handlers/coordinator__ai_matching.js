/* Event handlers from templates/coordinator/ai_matching.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "coordinator/ai_matching:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    saveExpertise('' + this.dataset.hA0 + '', JSON.parse(this.dataset.hA1))
  } } } },
  "coordinator/ai_matching:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    runMatching()
  } } } },
  "coordinator/ai_matching:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    applyMatch()
  } } } },
});
