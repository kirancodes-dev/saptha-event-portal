/* Event handlers from templates/404.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "404:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
});
