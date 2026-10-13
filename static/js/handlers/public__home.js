/* Event handlers from templates/public/home.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "public/home:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    window.location.href='/event/' + this.dataset.hA0 + ''
  } } } },
  "public/home:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='translateY(-6px) scale(1.02)'; this.style.borderColor='rgba(255,255,255,0.2)';
  } } } },
  "public/home:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='none'; this.style.borderColor='rgba(255,255,255,0.08)';
  } } } },
  "public/home:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.src='https://images.unsplash.com/photo-1540575467063-178a50c2df87?auto=format&fit=crop&w=600&q=60';
  } } } },
  "public/home:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    showDetails('' + this.dataset.hA1 + '')
  } } } },
  "public/home:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    resetFilter()
  } } } },
  "public/home:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.06)'
  } } } },
  "public/home:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.02)'
  } } } },
  "public/home:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.06)'
  } } } },
  "public/home:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.02)'
  } } } },
  "public/home:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.06)'
  } } } },
  "public/home:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.02)'
  } } } },
  "public/home:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.06)'
  } } } },
  "public/home:14": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.02)'
  } } } },
  "public/home:15": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.06)'
  } } } },
  "public/home:16": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.background='rgba(255,255,255,0.02)'
  } } } },
  "public/home:17": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleChat()
  } } } },
  "public/home:18": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleChat()
  } } } },
  "public/home:19": function (event) { with (document) { with (this.form || {}) { with (this) {
    handleEnter(event)
  } } } },
  "public/home:20": function (event) { with (document) { with (this.form || {}) { with (this) {
    sendMessage()
  } } } },
});
