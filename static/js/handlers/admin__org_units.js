/* Event handlers from templates/admin/org_units.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "admin/org_units:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Apply the role and unit migration shown in the preview? Existing events will be backfilled to Central.');
  } } } },
  "admin/org_units:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Revoke this role assignment?');
  } } } },
  "admin/org_units:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    handleScopeChange()
  } } } },
});
