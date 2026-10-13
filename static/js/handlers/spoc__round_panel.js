/* Event handlers from templates/spoc/round_panel.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "spoc/round_panel:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
  "spoc/round_panel:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchMode('top_n', this)
  } } } },
  "spoc/round_panel:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchMode('cutoff', this)
  } } } },
  "spoc/round_panel:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirmAdvance()
  } } } },
  "spoc/round_panel:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.borderColor='var(--blue)'
  } } } },
  "spoc/round_panel:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.borderColor='#e2e8f0'
  } } } },
  "spoc/round_panel:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.borderColor='var(--blue)'
  } } } },
  "spoc/round_panel:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.borderColor='#e2e8f0'
  } } } },
});
