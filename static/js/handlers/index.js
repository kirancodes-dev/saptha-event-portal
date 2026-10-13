/* Event handlers from templates/index.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "index:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none';document.getElementById('nav-logo-fallback').style.display='flex';
  } } } },
  "index:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterByCategory('Technical')
  } } } },
  "index:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterByCategory('Cultural')
  } } } },
  "index:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterByCategory('Sports')
  } } } },
  "index:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterByCategory('Management')
  } } } },
  "index:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterEvs()
  } } } },
  "index:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    startVoiceSearch()
  } } } },
  "index:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    clearSearch()
  } } } },
  "index:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCategoryFilter('all',this)
  } } } },
  "index:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCategoryFilter('Technical',this)
  } } } },
  "index:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCategoryFilter('Cultural',this)
  } } } },
  "index:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCategoryFilter('Sports',this)
  } } } },
  "index:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    setCategoryFilter('Management',this)
  } } } },
  "index:14": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleQuickFilter('free')
  } } } },
  "index:15": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleQuickFilter('team')
  } } } },
  "index:16": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleQuickFilter('individual')
  } } } },
  "index:17": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleQuickFilter('soon')
  } } } },
  "index:18": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.display='none'
  } } } },
  "index:19": function (event) { with (document) { with (this.form || {}) { with (this) {
    event.stopPropagation();
  } } } },
  "index:20": function (event) { with (document) { with (this.form || {}) { with (this) {
    event.stopPropagation(); alert('Registration is closed for this event.'); return false;  // the link is href="#"
  } } } },
  "index:21": function (event) { with (document) { with (this.form || {}) { with (this) {
    event.stopPropagation();
  } } } },
  "index:22": function (event) { with (document) { with (this.form || {}) { with (this) {
    loadMoreEvents()
  } } } },
  "index:23": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:24": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:25": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:26": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:27": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:28": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:29": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:30": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:31": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:32": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:33": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:34": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:35": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:36": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:37": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:38": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:39": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:40": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:41": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:42": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:43": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:44": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:45": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:46": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:47": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:48": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:49": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:50": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:51": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:52": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:53": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:54": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.parentElement.style.display='none'
  } } } },
  "index:55": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleChat()
  } } } },
  "index:56": function (event) { with (document) { with (this.form || {}) { with (this) {
    if(event.key==='Enter')sendChat()
  } } } },
  "index:57": function (event) { with (document) { with (this.form || {}) { with (this) {
    sendChat()
  } } } },
  "index:58": function (event) { with (document) { with (this.form || {}) { with (this) {
    dismissChatPrompt(event)
  } } } },
  "index:59": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleChat()
  } } } },
});
