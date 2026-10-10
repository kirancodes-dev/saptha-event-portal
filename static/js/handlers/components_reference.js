/* Event handlers from templates/components_reference.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "components_reference:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleTheme()
  } } } },
  "components_reference:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyHex('#0f1c4d')
  } } } },
  "components_reference:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyHex('#c9a45e')
  } } } },
  "components_reference:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyHex('#6366f1')
  } } } },
  "components_reference:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyHex('#10b981')
  } } } },
  "components_reference:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyHex('#ef4444')
  } } } },
  "components_reference:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyHex('#f59e0b')
  } } } },
  "components_reference:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    event.preventDefault(); triggerDemoToast();
  } } } },
  "components_reference:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    showToast('Event successfully registered!', 'success')
  } } } },
  "components_reference:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    showToast('Registration deadline closing in 2 hours', 'warning')
  } } } },
  "components_reference:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    showToast('Payment gateway temporarily unreachable', 'danger')
  } } } },
});
