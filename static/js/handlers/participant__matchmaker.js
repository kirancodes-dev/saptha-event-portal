/* Event handlers from templates/participant/matchmaker.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "participant/matchmaker:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    recalculateMatches()
  } } } },
  "participant/matchmaker:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    swipeLeft()
  } } } },
  "participant/matchmaker:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    swipeRight()
  } } } },
  "participant/matchmaker:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeChat()
  } } } },
});
