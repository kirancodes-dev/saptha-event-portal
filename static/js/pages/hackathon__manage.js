// The SPOC's hackathon page: "Add field" in the submission form builder
// (UPG-191) and the AI scoring run, a few submissions per request (UPG-192).
(function () {
    'use strict';

    function formBuilder() {
        var add = document.getElementById('hkAddField');
        var list = document.getElementById('hkFields');
        var tpl = document.getElementById('hkFieldTemplate');
        if (!add || !list || !tpl) { return; }
        add.addEventListener('click', function () {
            var n = list.querySelectorAll('[data-field-row]').length;
            while (list.querySelector('[name="field_' + n + '_label"]')) { n += 1; }
            var row = tpl.content.firstElementChild.cloneNode(true);
            row.querySelectorAll('[data-name]').forEach(function (el) {
                el.name = 'field_' + n + '_' + el.getAttribute('data-name');
            });
            list.appendChild(row);
            var label = row.querySelector('[data-name="label"]');
            if (label) { label.focus(); }
        });
    }

    // While a run is going, ask for the next few until the server says it's
    // finished, then reload to show the scores. Without script, the
    // "Continue scoring" button does the same one step at a time.
    function aiRun() {
        var box = document.getElementById('hkAi');
        if (!box || box.getAttribute('data-status') !== 'running') { return; }
        var out = document.getElementById('hkAiProgress');
        var button = document.getElementById('hkAiContinue');
        var meta = document.querySelector('meta[name="csrf-token"]');
        var url = box.getAttribute('data-next-url');
        if (button) { button.disabled = true; button.textContent = 'Scoring…'; }
        var failures = 0;

        function step() {
            fetch(url, {
                method: 'POST', credentials: 'same-origin',
                headers: {'Content-Type': 'application/json', 'Accept': 'application/json',
                          'X-CSRFToken': meta ? meta.content : ''},
                body: '{}'
            }).then(function (r) {
                if (!r.ok) { throw new Error('HTTP ' + r.status); }
                return r.json();
            }).then(function (p) {
                failures = 0;
                if (out) {
                    out.textContent = p.scored + ' of ' + p.total + ' scored' +
                        (p.not_scored ? ', ' + p.not_scored + ' not scored' : '') +
                        (p.finished ? '. ' + (p.message || 'Done.') : ' · ' + p.pending + ' to go…');
                }
                if (p.finished) { window.location.reload(); } else { step(); }
            }).catch(function () {
                failures += 1;
                if (failures >= 3) {
                    if (out) { out.textContent += ' The connection failed; press Continue scoring to resume.'; }
                    if (button) { button.disabled = false; button.textContent = 'Continue scoring'; }
                    return;
                }
                window.setTimeout(step, 3000);
            });
        }
        step();
    }

    formBuilder();
    aiRun();
})();
