/* Event handlers from templates/public/live_streams.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "public/live_streams:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchChannel('cultural', 'Cultural Night Main Stage - SNPSU Campus', 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/BigBuckBunny.mp4')
  } } } },
  "public/live_streams:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchChannel('hackathon', 'AI Hackathon Final Pitch Deck Arena', 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ElephantsDream.mp4')
  } } } },
  "public/live_streams:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchChannel('sports', 'RoboWars Arena - Tech Center Room 3', 'https://commondatastorage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4')
  } } } },
});
