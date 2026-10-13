/* Event handlers from templates/compliance/privacy_settings.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "compliance/privacy_settings:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    saveConsent()
  } } } },
  "compliance/privacy_settings:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    exportData()
  } } } },
  "compliance/privacy_settings:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    requestDeletion()
  } } } },
});
