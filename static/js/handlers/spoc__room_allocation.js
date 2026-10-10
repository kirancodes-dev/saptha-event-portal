/* Event handlers from templates/spoc/room_allocation.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "spoc/room_allocation:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
  "spoc/room_allocation:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Send room assignment emails to all ' + this.dataset.hA0 + ' assigned participant(s)?')
  } } } },
  "spoc/room_allocation:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterTable()
  } } } },
  "spoc/room_allocation:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.borderColor='var(--blue)'
  } } } },
  "spoc/room_allocation:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.borderColor='#e2e8f0'
  } } } },
  "spoc/room_allocation:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    reassignRoom(this)
  } } } },
});
