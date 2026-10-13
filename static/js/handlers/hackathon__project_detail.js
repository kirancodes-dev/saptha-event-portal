/* Event handlers from templates/hackathon/project_detail.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "hackathon/project_detail:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    updateRubric()
  } } } },
  "hackathon/project_detail:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    updateRubric()
  } } } },
  "hackathon/project_detail:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    updateRubric()
  } } } },
  "hackathon/project_detail:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    updateRubric()
  } } } },
  "hackathon/project_detail:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    saveRubricScore()
  } } } },
});
