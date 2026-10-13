/* Event handlers from templates/public/verify_certificate.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "public/verify_certificate:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    copyVerificationLink()
  } } } },
});
