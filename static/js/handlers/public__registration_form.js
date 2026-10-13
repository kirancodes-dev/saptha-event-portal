/* Registration form handlers (UPG-12): the designation and institution
   fields appear for faculty and external participants. Bound by
   static/js/handlers.js to elements marked data-h-change. */
Object.assign(window.SE_H = window.SE_H || {}, {
  'public/registration_form:participant-type': function () {
    var box = document.getElementById('affiliation-fields');
    if (!box) return;
    var needs = this.value === 'faculty' || this.value === 'external';
    box.hidden = !needs;
    box.querySelectorAll('input').forEach(function (i) { i.required = needs; });
  }
});
