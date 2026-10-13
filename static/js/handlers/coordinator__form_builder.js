/* Event handlers from templates/coordinator/form_builder.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "coordinator/form_builder:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    openPreview()
  } } } },
  "coordinator/form_builder:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    saveForm()
  } } } },
  "coordinator/form_builder:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('text')
  } } } },
  "coordinator/form_builder:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('textarea')
  } } } },
  "coordinator/form_builder:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('email')
  } } } },
  "coordinator/form_builder:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('tel')
  } } } },
  "coordinator/form_builder:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('number')
  } } } },
  "coordinator/form_builder:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('date')
  } } } },
  "coordinator/form_builder:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('url')
  } } } },
  "coordinator/form_builder:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('select')
  } } } },
  "coordinator/form_builder:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('radio')
  } } } },
  "coordinator/form_builder:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('checkbox_group')
  } } } },
  "coordinator/form_builder:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('checkbox')
  } } } },
  "coordinator/form_builder:14": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('heading')
  } } } },
  "coordinator/form_builder:15": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('paragraph')
  } } } },
  "coordinator/form_builder:16": function (event) { with (document) { with (this.form || {}) { with (this) {
    addField('divider')
  } } } },
  "coordinator/form_builder:17": function (event) { with (document) { with (this.form || {}) { with (this) {
    loadSimpleTemplate()
  } } } },
  "coordinator/form_builder:18": function (event) { with (document) { with (this.form || {}) { with (this) {
    setFormType('simple')
  } } } },
  "coordinator/form_builder:19": function (event) { with (document) { with (this.form || {}) { with (this) {
    setFormType('custom')
  } } } },
  "coordinator/form_builder:20": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateFromAI()
  } } } },
  "coordinator/form_builder:21": function (event) { with (document) { with (this.form || {}) { with (this) {
    onDragOver(event)
  } } } },
  "coordinator/form_builder:22": function (event) { with (document) { with (this.form || {}) { with (this) {
    onDrop(event)
  } } } },
  "coordinator/form_builder:23": function (event) { with (document) { with (this.form || {}) { with (this) {
    onDragLeave(event)
  } } } },
  "coordinator/form_builder:24": function (event) { with (document) { with (this.form || {}) { with (this) {
    clearAll()
  } } } },
});

/* Handlers on fields the builder draws at run time (UPG-25). */
Object.assign(window.SE_H, {
  'coordinator/form_builder:prop': function () { updateProp(this.dataset.prop, this.value); },
  'coordinator/form_builder:prop-checked': function () { updateProp(this.dataset.prop, this.checked); },
  'coordinator/form_builder:option': function () { updateOption(Number(this.dataset.i), this.value); }
});
