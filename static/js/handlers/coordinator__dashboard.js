/* Event handlers from templates/coordinator/dashboard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "coordinator/dashboard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(201, 164, 94, 0.4)';
  } } } },
  "coordinator/dashboard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='none'; this.style.boxShadow='none';
  } } } },
  "coordinator/dashboard:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
  "coordinator/dashboard:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleTheme()
  } } } },
  "coordinator/dashboard:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
  "coordinator/dashboard:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('This will email all allocated teams their room and judge details. Proceed?');
  } } } },
  "coordinator/dashboard:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Delete this event and all its registrations?');
  } } } },
  "coordinator/dashboard:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('WARNING: This will permanently eliminate teams below the cut-off. Proceed?');
  } } } },
  "coordinator/dashboard:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    addRoomField('roomContainer' + this.dataset.hA0 + '')
  } } } },
  "coordinator/dashboard:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    addMediaField('editMediaContainer' + this.dataset.hA1 + '')
  } } } },
  "coordinator/dashboard:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.remove()
  } } } },
  "coordinator/dashboard:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    addMediaField('editMediaContainer' + this.dataset.hA2 + '')
  } } } },
  "coordinator/dashboard:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(1)
  } } } },
  "coordinator/dashboard:14": function (event) { with (document) { with (this.form || {}) { with (this) {
    prevStep(2)
  } } } },
  "coordinator/dashboard:15": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(2)
  } } } },
  "coordinator/dashboard:16": function (event) { with (document) { with (this.form || {}) { with (this) {
    addMediaField('createMediaContainer')
  } } } },
  "coordinator/dashboard:17": function (event) { with (document) { with (this.form || {}) { with (this) {
    prevStep(3)
  } } } },
  "coordinator/dashboard:18": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(3)
  } } } },
  "coordinator/dashboard:19": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectFormType('simple')
  } } } },
  "coordinator/dashboard:20": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectFormType('custom')
  } } } },
  "coordinator/dashboard:21": function (event) { with (document) { with (this.form || {}) { with (this) {
    prevStep(4)
  } } } },
});
