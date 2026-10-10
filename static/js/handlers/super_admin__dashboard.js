/* Event handlers from templates/super_admin/dashboard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "super_admin/dashboard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleSidebar()
  } } } },
  "super_admin/dashboard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleSidebar()
  } } } },
  "super_admin/dashboard:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Revoke access?')
  } } } },
});
