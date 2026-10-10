/* Event handlers from templates/onboarding/wizard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "onboarding/wizard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(2)
  } } } },
  "onboarding/wizard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    addDept()
  } } } },
  "onboarding/wizard:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.remove()
  } } } },
  "onboarding/wizard:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.remove()
  } } } },
  "onboarding/wizard:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(1)
  } } } },
  "onboarding/wizard:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(3)
  } } } },
  "onboarding/wizard:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextStep(2)
  } } } },
  "onboarding/wizard:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    submitWizard()
  } } } },
});
