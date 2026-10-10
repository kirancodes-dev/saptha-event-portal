/* Event handlers from templates/spoc/scan.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "spoc/scan:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    setTab('scan')
  } } } },
  "spoc/scan:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    setTab('manual')
  } } } },
  "spoc/scan:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    startScanner()
  } } } },
  "spoc/scan:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    stopScanner()
  } } } },
  "spoc/scan:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    onSearchChange()
  } } } },
  "spoc/scan:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    setFilter('all')
  } } } },
  "spoc/scan:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    setFilter('absent')
  } } } },
  "spoc/scan:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    setFilter('present')
  } } } },
});
