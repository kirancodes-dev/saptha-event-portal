/* Event handlers from templates/public/reels.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "public/reels:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    slidePrev()
  } } } },
  "public/reels:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    slideNext()
  } } } },
  "public/reels:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    togglePlay(this)
  } } } },
  "public/reels:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleLike(this)
  } } } },
  "public/reels:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    togglePlay(this)
  } } } },
  "public/reels:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleLike(this)
  } } } },
  "public/reels:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    togglePlay(this)
  } } } },
  "public/reels:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleLike(this)
  } } } },
});
