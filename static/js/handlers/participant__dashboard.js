/* Event handlers from templates/participant/dashboard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "participant/dashboard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleTheme()
  } } } },
  "participant/dashboard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    openCmdPalette()
  } } } },
  "participant/dashboard:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleNotifPanel()
  } } } },
  "participant/dashboard:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    markAllRead()
  } } } },
  "participant/dashboard:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    togglePushSubscription(this)
  } } } },
  "participant/dashboard:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyRefLink()
  } } } },
  "participant/dashboard:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    claimPayout()
  } } } },
  "participant/dashboard:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
  "participant/dashboard:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    openScoreModal(this)
  } } } },
  "participant/dashboard:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    if(event.target===this)closeCmdPalette()
  } } } },
});

/* Notification rows the dashboard draws at run time (UPG-25). */
Object.assign(window.SE_H, {
  'participant/dashboard:notif-hover': function () { this.style.background = 'rgba(255,255,255,0.03)'; },
  'participant/dashboard:notif-out': function () { this.style.background = this.dataset.bg; }
});
