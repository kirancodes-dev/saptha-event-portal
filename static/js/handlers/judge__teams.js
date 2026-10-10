/* Event handlers from templates/judge/teams.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "judge/teams:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    openScoreModal('' + this.dataset.hA0 + '')
  } } } },
  "judge/teams:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    openScoreModal('' + this.dataset.hA1 + '')
  } } } },
  "judge/teams:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    fetchLeaderboard()
  } } } },
  "judge/teams:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    submitScore()
  } } } },
});

/* Handlers on the score sliders the page draws at run time (UPG-25). */
Object.assign(window.SE_H, {
  'judge/teams:sync-slider': function () { syncSlider(this, this.dataset.target); }
});
