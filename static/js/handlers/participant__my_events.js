/* Event handlers from templates/participant/my_events.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "participant/my_events:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Reset your calendar link? Calendars subscribed with the old link stop updating.');
  } } } },
});
