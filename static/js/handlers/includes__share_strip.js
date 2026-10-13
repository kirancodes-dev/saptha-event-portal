/* Event handlers from templates/includes/share_strip.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "includes/share_strip:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    shareCopy(this)
  } } } },
  "includes/share_strip:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    sharNative(this)
  } } } },
});
