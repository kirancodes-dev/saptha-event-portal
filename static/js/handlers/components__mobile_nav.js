/* Event handlers from templates/components/mobile_nav.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "components/mobile_nav:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.showPwaInstallModal()
  } } } },
  "components/mobile_nav:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    if(event.target===this) window.closePwaModal()
  } } } },
  "components/mobile_nav:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.closePwaModal()
  } } } },
  "components/mobile_nav:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.triggerNativeInstall()
  } } } },
  "components/mobile_nav:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.closePwaModal();localStorage.setItem('pwa_banner_dismissed','1');
  } } } },
});
