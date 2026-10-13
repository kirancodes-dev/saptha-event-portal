/* Event handlers from templates/login.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "login:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    spTogglePw('passwordInput',this)
  } } } },
  "login:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.showPwaInstallModal ? window.showPwaInstallModal() : alert('Coming soon!');
  } } } },
  "login:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    if(event.target===this) window.closePwaModal()
  } } } },
  "login:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.closePwaModal()
  } } } },
  "login:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.triggerNativeInstall()
  } } } },
  "login:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.closePwaModal();localStorage.setItem('pwa_banner_dismissed','1');
  } } } },
});
