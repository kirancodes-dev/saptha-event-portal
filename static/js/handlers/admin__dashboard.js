/* Event handlers from templates/admin/dashboard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "admin/dashboard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleTheme()
  } } } },
  "admin/dashboard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.form.submit()
  } } } },
  "admin/dashboard:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Delete ' + this.dataset.hA0 + '?')
  } } } },
  "admin/dashboard:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    addMediaField('createAdminMediaContainer')
  } } } },
  "admin/dashboard:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCopilotPrompt('2-day AI & GenAI Hackathon for 300 students with GitHub repo submissions and multi-judge rubrics.')
  } } } },
  "admin/dashboard:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCopilotPrompt('IEEE International Conference on Quantum Cryptography for 200 delegates with VIP & Student tickets.')
  } } } },
  "admin/dashboard:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCopilotPrompt('Hands-on Cloud Kubernetes & Docker Workshop for 60 participants with practical lab quiz.')
  } } } },
  "admin/dashboard:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCopilotPrompt('Inter-University Badminton Championship with 64 knockout teams, referee scorecards, and podium awards.')
  } } } },
  "admin/dashboard:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateAiProposal()
  } } } },
  "admin/dashboard:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateAiProposal()
  } } } },
  "admin/dashboard:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    approveAiProposal()
  } } } },
  "admin/dashboard:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Permanently eliminate teams below cut-off?')
  } } } },
  "admin/dashboard:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    addRoomField('roomContainer' + this.dataset.hA1 + '')
  } } } },
});
