/* Event handlers from templates/spoc/edit_event.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "spoc/edit_event:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleAIGenerator()
  } } } },
  "spoc/edit_event:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleAIGenerator()
  } } } },
  "spoc/edit_event:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateEventOutline()
  } } } },
});
