/* Event handlers from templates/public/wayfinder.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "public/wayfinder:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    zoomToVenue('auditorium')
  } } } },
  "public/wayfinder:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    zoomToVenue('lab1')
  } } } },
  "public/wayfinder:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    zoomToVenue('seminar')
  } } } },
  "public/wayfinder:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    zoomToVenue('ground')
  } } } },
});
