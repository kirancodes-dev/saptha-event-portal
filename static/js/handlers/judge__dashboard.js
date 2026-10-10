/* Event handlers from templates/judge/dashboard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "judge/dashboard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(201, 164, 94, 0.4)';
  } } } },
  "judge/dashboard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='none'; this.style.boxShadow='none';
  } } } },
});
