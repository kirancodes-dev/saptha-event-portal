/* Event handlers from templates/spoc/dashboard.html, moved out of on* attributes so the CSP
   needs no inline script (UPG-25). static/js/handlers.js binds them to the
   elements marked data-h-<event>="<key>"; `this` and `event` are as before. */
Object.assign(window.SE_H = window.SE_H || {}, {
  "spoc/dashboard:1": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='translateY(-1px)'; this.style.boxShadow='0 4px 12px rgba(201, 164, 94, 0.4)';
  } } } },
  "spoc/dashboard:2": function (event) { with (document) { with (this.form || {}) { with (this) {
    this.style.transform='none'; this.style.boxShadow='none';
  } } } },
  "spoc/dashboard:3": function (event) { with (document) { with (this.form || {}) { with (this) {
    openCommandPalette()
  } } } },
  "spoc/dashboard:4": function (event) { with (document) { with (this.form || {}) { with (this) {
    startTour()
  } } } },
  "spoc/dashboard:5": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleTheme()
  } } } },
  "spoc/dashboard:6": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectGlobalOverview()
  } } } },
  "spoc/dashboard:7": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectEvent('' + this.dataset.hA0 + '')
  } } } },
  "spoc/dashboard:8": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleWayfinderMap(this, 'global-wayfinder-content')
  } } } },
  "spoc/dashboard:9": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('Main Auditorium', 310, 400, this)
  } } } },
  "spoc/dashboard:10": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('CS Lab', 48, 50, this)
  } } } },
  "spoc/dashboard:11": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('Seminar Hall', 120, 150, this)
  } } } },
  "spoc/dashboard:12": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('Sports Arena', 85, 200, this)
  } } } },
  "spoc/dashboard:13": function (event) { with (document) { with (this.form || {}) { with (this) {
    document.getElementById('ann-form').action='/spoc/announce/'+this.value
  } } } },
  "spoc/dashboard:14": function (event) { with (document) { with (this.form || {}) { with (this) {
    showMasterList()
  } } } },
  "spoc/dashboard:15": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchTab('overview', this)
  } } } },
  "spoc/dashboard:16": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchTab('logistics', this)
  } } } },
  "spoc/dashboard:17": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchTab('comms', this)
  } } } },
  "spoc/dashboard:18": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchTab('certs', this)
  } } } },
  "spoc/dashboard:19": function (event) { with (document) { with (this.form || {}) { with (this) {
    switchTab('settings', this)
  } } } },
  "spoc/dashboard:20": function (event) { with (document) { with (this.form || {}) { with (this) {
    openModal('assignCoordModal-' + this.dataset.hA1 + '')
  } } } },
  "spoc/dashboard:21": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleWayfinderMap(this, 'event-wayfinder-content-' + this.dataset.hA2 + '')
  } } } },
  "spoc/dashboard:22": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('Main Auditorium', 310, 400, this)
  } } } },
  "spoc/dashboard:23": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('CS Lab', 48, 50, this)
  } } } },
  "spoc/dashboard:24": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('Seminar Hall', 120, 150, this)
  } } } },
  "spoc/dashboard:25": function (event) { with (document) { with (this.form || {}) { with (this) {
    selectRoom('Sports Arena', 85, 200, this)
  } } } },
  "spoc/dashboard:26": function (event) { with (document) { with (this.form || {}) { with (this) {
    openModal('roomModal-' + this.dataset.hA3 + '')
  } } } },
  "spoc/dashboard:27": function (event) { with (document) { with (this.form || {}) { with (this) {
    openBlastModal('' + this.dataset.hA4 + '', '' + this.dataset.hA5 + '')
  } } } },
  "spoc/dashboard:28": function (event) { with (document) { with (this.form || {}) { with (this) {
    openModal('judgeModal-' + this.dataset.hA6 + '')
  } } } },
  "spoc/dashboard:29": function (event) { with (document) { with (this.form || {}) { with (this) {
    openModal('certModal-' + this.dataset.hA7 + '')
  } } } },
  "spoc/dashboard:30": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Send participation certificates to all checked-in attendees of \'' + this.dataset.hA8 + '\'?')
  } } } },
  "spoc/dashboard:31": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Clone \'' + this.dataset.hA9 + '\'? You can edit the date and details after.')
  } } } },
  "spoc/dashboard:32": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm(this.dataset.msg)
  } } } },
  "spoc/dashboard:33": function (event) { with (document) { with (this.form || {}) { with (this) {
    confirmEndEvent('' + this.dataset.hA10 + '', '' + this.dataset.hA11 + '')
  } } } },
  "spoc/dashboard:34": function (event) { with (document) { with (this.form || {}) { with (this) {
    return confirm('Delete \'' + this.dataset.hA12 + '\' and all its data? This cannot be undone.')
  } } } },
  "spoc/dashboard:35": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('assignCoordModal-' + this.dataset.hA13 + '')
  } } } },
  "spoc/dashboard:36": function (event) { with (document) { with (this.form || {}) { with (this) {
    autoFillCoordName(this.value, 'coordName-' + this.dataset.hA14 + '')
  } } } },
  "spoc/dashboard:37": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('assignCoordModal-' + this.dataset.hA15 + '')
  } } } },
  "spoc/dashboard:38": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('judgeModal-' + this.dataset.hA16 + '')
  } } } },
  "spoc/dashboard:39": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('roomModal-' + this.dataset.hA17 + '')
  } } } },
  "spoc/dashboard:40": function (event) { with (document) { with (this.form || {}) { with (this) {
    addRoomRow('' + this.dataset.hA18 + '')
  } } } },
  "spoc/dashboard:41": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('certModal-' + this.dataset.hA19 + '')
  } } } },
  "spoc/dashboard:42": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('endEventModal')
  } } } },
  "spoc/dashboard:43": function (event) { with (document) { with (this.form || {}) { with (this) {
    updateCertPreview()
  } } } },
  "spoc/dashboard:44": function (event) { with (document) { with (this.form || {}) { with (this) {
    updateCertPreview()
  } } } },
  "spoc/dashboard:45": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('endEventModal')
  } } } },
  "spoc/dashboard:46": function (event) { with (document) { with (this.form || {}) { with (this) {
    submitEndEvent()
  } } } },
  "spoc/dashboard:47": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeBlastModal()
  } } } },
  "spoc/dashboard:48": function (event) { with (document) { with (this.form || {}) { with (this) {
    generateAICopy()
  } } } },
  "spoc/dashboard:49": function (event) { with (document) { with (this.form || {}) { with (this) {
    previewBlastEmail()
  } } } },
  "spoc/dashboard:50": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeBlastModal()
  } } } },
  "spoc/dashboard:51": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('blastPreviewModal')
  } } } },
  "spoc/dashboard:52": function (event) { with (document) { with (this.form || {}) { with (this) {
    closeModal('blastPreviewModal')
  } } } },
  "spoc/dashboard:53": function (event) { with (document) { with (this.form || {}) { with (this) {
    exitTour()
  } } } },
  "spoc/dashboard:54": function (event) { with (document) { with (this.form || {}) { with (this) {
    prevTourStep()
  } } } },
  "spoc/dashboard:55": function (event) { with (document) { with (this.form || {}) { with (this) {
    exitTour()
  } } } },
  "spoc/dashboard:56": function (event) { with (document) { with (this.form || {}) { with (this) {
    nextTourStep()
  } } } },
  "spoc/dashboard:57": function (event) { with (document) { with (this.form || {}) { with (this) {
    toggleSpeedDial()
  } } } },
  "spoc/dashboard:58": function (event) { with (document) { with (this.form || {}) { with (this) {
    startTour()
  } } } },
  "spoc/dashboard:59": function (event) { with (document) { with (this.form || {}) { with (this) {
    refreshStats()
  } } } },
  "spoc/dashboard:60": function (event) { with (document) { with (this.form || {}) { with (this) {
    handlePaletteBackdropClick(event)
  } } } },
  "spoc/dashboard:61": function (event) { with (document) { with (this.form || {}) { with (this) {
    filterPaletteCommands()
  } } } },
});
