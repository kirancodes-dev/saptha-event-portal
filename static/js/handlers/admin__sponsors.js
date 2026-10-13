/* Event handlers from templates/admin/sponsors.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "admin/sponsors:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.src='/static/snpsu-logo.png';
  } } } },
  "admin/sponsors:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Remove ' + this.dataset.hA0 + '?');
  } } } },
});
