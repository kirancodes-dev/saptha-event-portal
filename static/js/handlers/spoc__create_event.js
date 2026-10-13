/* Event handlers from templates/spoc/create_event.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "spoc/create_event:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    goToStep(1)
  } } } },
  "spoc/create_event:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    goToStep(2)
  } } } },
  "spoc/create_event:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    goToStep(3)
  } } } },
  "spoc/create_event:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    goToStep(4)
  } } } },
  "spoc/create_event:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    goToStep(5)
  } } } },
  "spoc/create_event:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    goToStep(6)
  } } } },
  "spoc/create_event:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectTemplate('hackathon')
  } } } },
  "spoc/create_event:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectTemplate('seminar')
  } } } },
  "spoc/create_event:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectTemplate('workshop')
  } } } },
  "spoc/create_event:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectTemplate('custom')
  } } } },
  "spoc/create_event:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    changeStep(1)
  } } } },
  "spoc/create_event:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleAIGenerator()
  } } } },
  "spoc/create_event:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleAIGenerator()
  } } } },
  "spoc/create_event:14": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateEventOutline()
  } } } },
  "spoc/create_event:15": function (event) { with (document) { with (this.form || {}) { with (this) {
    addCriteria('','',10)
  } } } },
  "spoc/create_event:16": function (event) { with (document) { with (this.form || {}) { with (this) {
    loadDefaultCriteria()
  } } } },
  "spoc/create_event:17": function (event) { with (document) { with (this.form || {}) { with (this) {
    clearCriteria()
  } } } },
  "spoc/create_event:18": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleTeams()
  } } } },
  "spoc/create_event:19": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('text')
  } } } },
  "spoc/create_event:20": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('email')
  } } } },
  "spoc/create_event:21": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('tel')
  } } } },
  "spoc/create_event:22": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('number')
  } } } },
  "spoc/create_event:23": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('textarea')
  } } } },
  "spoc/create_event:24": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('select')
  } } } },
  "spoc/create_event:25": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('radio')
  } } } },
  "spoc/create_event:26": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('checkbox')
  } } } },
  "spoc/create_event:27": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('date')
  } } } },
  "spoc/create_event:28": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('url')
  } } } },
  "spoc/create_event:29": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('heading')
  } } } },
  "spoc/create_event:30": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_addField('divider')
  } } } },
  "spoc/create_event:31": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_closeProps()
  } } } },
  "spoc/create_event:32": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_loadTemplate()
  } } } },
  "spoc/create_event:33": function (event) { with (document) { with (this.form || {}) { with (this) {
    fb_clearAll()
  } } } },
  "spoc/create_event:34": function (event) { with (document) { with (this.form || {}) { with (this) {
    previewBanner(this.value)
  } } } },
  "spoc/create_event:35": function (event) { with (document) { with (this.form || {}) { with (this) {
    addSponsorRow()
  } } } },
  "spoc/create_event:36": function (event) { with (document) { with (this.form || {}) { with (this) {
    changeStep(-1)
  } } } },
  "spoc/create_event:37": function (event) { with (document) { with (this.form || {}) { with (this) {
    changeStep(1)
  } } } },
  "spoc/create_event:38": function (event) { with (document) { with (this.form || {}) { with (this) {
    submitForm()
  } } } },
});

/* Handlers on rows and fields the page draws at run time (UPG-25). */
Object.assign(window.SE_H, {
  'spoc/create_event:remove-criterion': function () { this.closest('.criteria-row').remove(); syncCriteria(); },
  'spoc/create_event:set-prop': function () { fb_setProp(this.dataset.prop, this.value); },
  'spoc/create_event:set-prop-checked': function () { fb_setProp(this.dataset.prop, this.checked); },
  'spoc/create_event:set-opt': function () { fb_setOpt(Number(this.dataset.i), this.value); }
});
