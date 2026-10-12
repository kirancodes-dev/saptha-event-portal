/* Create-event wizard (UPG-73, UPG-74). The page works without this script (all
   steps show and the server checks everything); with it, the steps show one at a
   time, each kind of event shows only its own fields, and the judging, sponsor and
   question builders fill their hidden JSON fields. Every node is built with the
   DOM, never from HTML strings (BLK-19). */
(function () {
  'use strict';
  var form = document.getElementById('wz-form');
  if (!form) return;
  var root = form.closest('.wz');
  var TYPES = JSON.parse(document.getElementById('wz-types').textContent || '{}');
  var steps = Array.prototype.slice.call(form.querySelectorAll('.wz-step'));
  var nav = document.getElementById('wz-nav');
  var pager = document.getElementById('wz-pager');
  var back = document.getElementById('wz-back');
  var next = document.getElementById('wz-next');
  var current = 1;
  var hadErrors = !!document.getElementById('wz-errors');

  function $(sel, scope) { return (scope || form).querySelector(sel); }
  function $$(sel, scope) { return Array.prototype.slice.call((scope || form).querySelectorAll(sel)); }
  function el(tag, attrs, children) {
    var n = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === 'text') n.textContent = attrs[k];
      else if (k === 'value') n.value = attrs[k];
      else if (k === 'checked') n.checked = !!attrs[k];
      else n.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { if (c) n.appendChild(c); });
    return n;
  }
  function toast(msg, type) { if (window.showToast) window.showToast(msg, type || 'info'); }
  function selectedType() {
    var r = $('input[name="event_type"]:checked');
    return r ? r.value : '';
  }
  function spec() { return TYPES[selectedType()] || TYPES.custom || {}; }

  // ── Steps ──────────────────────────────────────────────────────────────
  root.classList.add('js');
  nav.hidden = false;
  pager.hidden = false;

  function show(n) {
    current = Math.max(1, Math.min(steps.length, n));
    steps.forEach(function (s) { s.classList.toggle('is-active', +s.dataset.step === current); });
    $$('[data-step-go]', nav).forEach(function (b) {
      var i = +b.dataset.stepGo;
      if (i === current) b.setAttribute('aria-current', 'step'); else b.removeAttribute('aria-current');
      b.classList.toggle('is-done', i < current);
    });
    back.disabled = current === 1;
    next.hidden = current === steps.length;
    if (current === steps.length) buildSummary();
    var h = steps[current - 1].querySelector('h2');
    if (h) { h.setAttribute('tabindex', '-1'); h.focus({ preventScroll: true }); }
    window.scrollTo({ top: Math.max(0, root.getBoundingClientRect().top + window.scrollY - 90), behavior: 'smooth' });
  }

  function problem(field, msg) {
    toast(msg, 'warning');
    if (field) field.focus();
    return false;
  }

  function stepOk(n) {
    var s = spec();
    if (n === 1 && !selectedType()) return problem($('input[name="event_type"]'), 'Choose the kind of event.');
    if (n === 2 && !$('#f-title').value.trim()) return problem($('#f-title'), 'Give the event a title.');
    if (n === 3) {
      if (!$('#f-date').value) return problem($('#f-date'), 'Choose the date it starts.');
      if (!s.fest && !$('#f-deadline').value) return problem($('#f-deadline'), 'Choose the last date to register.');
      var mode = ($('input[name="event_mode"]:checked') || {}).value || 'offline';
      if (mode !== 'online' && !$('#f-venue').value.trim() && !$('#f-room').value)
        return problem($('#f-venue'), 'Add a venue or pick a room.');
    }
    if (n === 5) {
      var missing = $$('.type-details:not([disabled]) [required]').filter(function (f) { return !f.value.trim(); })[0];
      if (missing) return problem(missing, 'Fill in the required details for this kind of event.');
    }
    return true;
  }

  back.addEventListener('click', function () { show(current - 1); });
  next.addEventListener('click', function () { if (stepOk(current)) show(current + 1); });
  $$('[data-step-go]', nav).forEach(function (b) {
    b.addEventListener('click', function () {
      var target = +b.dataset.stepGo;
      for (var i = current; i < target; i++) { if (!stepOk(i)) { show(i); return; } }
      show(target);
    });
  });

  // ── The kind of event ──────────────────────────────────────────────────
  function setIf(sel, value, force) {
    var f = $(sel);
    if (f && (force || !f.value)) f.value = value;
  }

  function applyType(initial) {
    var key = selectedType();
    var s = spec();
    // Each type's own fields; the others are disabled so they don't submit
    $$('.type-details').forEach(function (fs) {
      var on = fs.dataset.forType === key;
      fs.hidden = !on;
      fs.disabled = !on;
    });
    var hasDetails = !!$('.type-details[data-for-type="' + key + '"]');
    var fest = !!s.fest;
    $$('[data-hide-for-fest]').forEach(function (n) { n.hidden = fest; });
    $$('[data-show-for-fest]').forEach(function (n) { n.hidden = !fest; });
    var competitive = !!s.competitive || key === 'custom';
    $('#competition-block').hidden = !competitive || fest;
    $('#judging-block').hidden = s.group === 'sports';
    $('#nothing-specific').hidden = hasDetails || competitive;
    if (!initial) {
      // Defaults for the newly chosen kind; the SPOC can change them
      setIf('#f-category', s.category, true);
      setIf('#f-participation', s.participation, true);
      setIf('#f-team-min', (s.team || [1, 1])[0], true);
      setIf('#f-team-max', (s.team || [1, 1])[1], true);
      setIf('#f-submission', s.submission || 'none', true);
      var mode = $('#mode-' + (s.mode || 'offline'));
      if (mode) mode.checked = true;
      $$('input[name="allowed_participants"]').forEach(function (c) {
        c.checked = (s.audience || ['student']).indexOf(c.value) !== -1;
      });
    }
    applyMode();
    applyParticipation();
  }

  function applyMode() {
    var mode = ($('input[name="event_mode"]:checked') || {}).value || 'offline';
    $$('[data-mode]').forEach(function (n) { n.hidden = n.dataset.mode.split(' ').indexOf(mode) === -1; });
  }
  function applyParticipation() {
    var p = $('#f-participation').value;
    $('#team-row').hidden = p === 'Individual';
  }

  $$('input[name="event_type"]').forEach(function (r) { r.addEventListener('change', function () { applyType(false); }); });
  $$('input[name="event_mode"]').forEach(function (r) { r.addEventListener('change', applyMode); });
  $('#f-participation').addEventListener('change', applyParticipation);

  // ── Banner preview (https only) ────────────────────────────────────────
  var banner = $('#f-banner');
  var preview = document.getElementById('banner-preview');
  function previewBanner() {
    var u = banner.value.trim();
    var ok = /^https:\/\//i.test(u);
    preview.hidden = !ok;
    if (ok) preview.src = u; else preview.removeAttribute('src');
  }
  banner.addEventListener('change', previewBanner);
  preview.addEventListener('error', function () { preview.hidden = true; });

  // ── AI writer (description and rules) ──────────────────────────────────
  var aiBox = document.getElementById('ai-box');
  document.getElementById('ai-toggle').addEventListener('click', function () { aiBox.hidden = !aiBox.hidden; });
  document.getElementById('ai-go').addEventListener('click', function () {
    var btn = this;
    var title = $('#f-title').value.trim();
    if (!title) return problem($('#f-title'), 'Enter the event title first.');
    btn.disabled = true;
    var csrf = (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
    fetch('/spoc/marketing/event_writer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify({ title: title, prompt: document.getElementById('ai-prompt').value.trim(),
                             event_type: spec().name || '' })
    }).then(function (r) { return r.json(); }).then(function (d) {
      if (d.description) $('#f-description').value = d.description;
      if (d.rules) $('#f-rules').value = d.rules;
      if (d.description || d.rules) { toast('Written. Read it through and edit before saving.', 'success'); aiBox.hidden = true; }
      else toast(d.error || "The assistant couldn't write this now.", 'danger');
    }).catch(function () { toast("The assistant couldn't be reached.", 'danger'); })
      .finally(function () { btn.disabled = false; });
  });

  // ── Builders: judging criteria, sponsors, extra questions ──────────────
  function readJson(id) {
    try { var v = JSON.parse(document.getElementById(id).value || '[]'); return Array.isArray(v) ? v : []; }
    catch (e) { return []; }
  }
  function removeBtn(label, onClick) {
    var b = el('button', { type: 'button', 'class': 'btn btn-outline-danger btn-sm', 'aria-label': label },
               [el('i', { 'class': 'fas fa-xmark', 'aria-hidden': 'true' })]);
    b.addEventListener('click', onClick);
    return b;
  }

  // Judging criteria
  var crit = readJson('crit-json');
  var critRows = document.getElementById('crit-rows');
  function syncCrit() { document.getElementById('crit-json').value = JSON.stringify(crit.filter(function (c) { return (c.name || '').trim(); })); }
  function drawCrit() {
    critRows.textContent = '';
    crit.forEach(function (c, i) {
      var name = el('input', { 'class': 'form-control', placeholder: 'Criterion, e.g. Innovation', 'aria-label': 'Criterion ' + (i + 1), value: c.name || '' });
      var max = el('input', { 'class': 'form-control', type: 'number', min: '1', max: '1000', 'aria-label': 'Maximum score', value: c.max_score || 10 });
      var desc = el('input', { 'class': 'form-control', placeholder: 'What judges look for', 'aria-label': 'Description', value: c.description || '' });
      name.addEventListener('input', function () { c.name = name.value; syncCrit(); });
      max.addEventListener('input', function () { c.max_score = +max.value || 10; syncCrit(); });
      desc.addEventListener('input', function () { c.description = desc.value; syncCrit(); });
      critRows.appendChild(el('div', { 'class': 'builder-row' }, [name, max, desc,
        removeBtn('Remove criterion', function () { crit.splice(i, 1); drawCrit(); syncCrit(); })]));
    });
  }
  var RUBRICS = {
    competition: [['Innovation', 10], ['Technical execution', 10], ['Impact', 10], ['Presentation', 10]],
    cultural: [['Performance', 10], ['Creativity', 10], ['Stage presence', 10], ['Overall impression', 10]],
    learning: [['Content', 10], ['Delivery', 10]],
    other: [['Overall', 10]]
  };
  document.getElementById('crit-add').addEventListener('click', function () { crit.push({ name: '', max_score: 10, description: '' }); drawCrit(); critRows.lastChild.querySelector('input').focus(); });
  document.getElementById('crit-defaults').addEventListener('click', function () {
    var set = RUBRICS[spec().group] || RUBRICS.competition;
    crit = set.map(function (p) { return { name: p[0], max_score: p[1], description: '' }; });
    drawCrit(); syncCrit();
  });

  // Sponsors
  var sponsors = readJson('sponsors-json');
  var sponsorRows = document.getElementById('sponsor-rows');
  function syncSponsors() { document.getElementById('sponsors-json').value = JSON.stringify(sponsors.filter(function (s) { return (s.name || '').trim(); })); }
  function drawSponsors() {
    sponsorRows.textContent = '';
    sponsors.forEach(function (s, i) {
      var name = el('input', { 'class': 'form-control', placeholder: 'Sponsor name', 'aria-label': 'Sponsor ' + (i + 1), value: s.name || '' });
      var tier = el('select', { 'class': 'form-select', 'aria-label': 'Tier' }, ['Title', 'Gold', 'Silver', 'Partner', 'Media'].map(function (t) {
        return el('option', { value: t, text: t });
      }));
      tier.value = s.tier || 'Partner';
      var logo = el('input', { 'class': 'form-control', type: 'url', placeholder: 'Logo https://…', 'aria-label': 'Logo address', value: s.logo_url || '' });
      var site = el('input', { 'class': 'form-control', type: 'url', placeholder: 'Website https://…', 'aria-label': 'Website', value: s.website || '' });
      [[name, 'name'], [tier, 'tier'], [logo, 'logo_url'], [site, 'website']].forEach(function (p) {
        p[0].addEventListener('input', function () { s[p[1]] = p[0].value; syncSponsors(); });
        p[0].addEventListener('change', function () { s[p[1]] = p[0].value; syncSponsors(); });
      });
      sponsorRows.appendChild(el('div', { 'class': 'builder-row sponsor' }, [name, tier, logo, site,
        removeBtn('Remove sponsor', function () { sponsors.splice(i, 1); drawSponsors(); syncSponsors(); })]));
    });
  }
  document.getElementById('sponsor-add').addEventListener('click', function () { sponsors.push({ tier: 'Partner' }); drawSponsors(); syncSponsors(); sponsorRows.lastChild.querySelector('input').focus(); });

  // Extra registration questions (the standard four are always first)
  var BASE = [
    { id: 'full_name', type: 'text', label: 'Full Name', placeholder: 'Enter your full name', required: true, options: [], help_text: '' },
    { id: 'email', type: 'email', label: 'Email Address', placeholder: 'you@example.com', required: true, options: [], help_text: '' },
    { id: 'phone', type: 'tel', label: 'Phone Number', placeholder: '10-digit mobile', required: true, options: [], help_text: '' },
    { id: 'usn', type: 'text', label: 'USN / Roll Number', placeholder: 'e.g. 1SN21CS001', required: false, options: [], help_text: '' }
  ];
  var baseIds = BASE.map(function (f) { return f.id; });
  var extras = readJson('form-json').filter(function (f) { return baseIds.indexOf(f.id) === -1; });
  var fieldRows = document.getElementById('field-rows');
  var KINDS = [['text', 'Short answer'], ['textarea', 'Long answer'], ['number', 'Number'], ['url', 'Link'],
               ['select', 'Dropdown'], ['radio', 'One choice'], ['checkbox', 'Checkboxes'], ['date', 'Date']];
  function syncFields() {
    var real = extras.filter(function (f) { return (f.label || '').trim(); });
    document.getElementById('form-json').value = real.length ? JSON.stringify(BASE.concat(real)) : '';
  }
  function drawFields() {
    fieldRows.textContent = '';
    extras.forEach(function (f, i) {
      var label = el('input', { 'class': 'form-control', placeholder: 'Question, e.g. T-shirt size', 'aria-label': 'Question ' + (i + 1), value: f.label || '' });
      var kind = el('select', { 'class': 'form-select', 'aria-label': 'Answer type' }, KINDS.map(function (k) { return el('option', { value: k[0], text: k[1] }); }));
      kind.value = f.type || 'text';
      var opts = el('input', { 'class': 'form-control', placeholder: 'Choices, comma-separated', 'aria-label': 'Choices', value: (f.options || []).join(', ') });
      var reqId = 'req-' + f.id;
      var req = el('input', { type: 'checkbox', 'class': 'form-check-input', id: reqId, checked: f.required });
      var reqWrap = el('div', { 'class': 'form-check pt-2' }, [req, el('label', { 'class': 'form-check-label', 'for': reqId, text: 'Required' })]);
      function needOpts() { opts.hidden = ['select', 'radio', 'checkbox'].indexOf(kind.value) === -1; }
      label.addEventListener('input', function () { f.label = label.value; syncFields(); });
      kind.addEventListener('change', function () { f.type = kind.value; needOpts(); syncFields(); });
      opts.addEventListener('input', function () { f.options = opts.value.split(',').map(function (o) { return o.trim(); }).filter(Boolean); syncFields(); });
      req.addEventListener('change', function () { f.required = req.checked; syncFields(); });
      needOpts();
      fieldRows.appendChild(el('div', { 'class': 'builder-row field' }, [label, kind, opts, reqWrap,
        removeBtn('Remove question', function () { extras.splice(i, 1); drawFields(); syncFields(); })]));
    });
  }
  document.getElementById('field-add').addEventListener('click', function () {
    extras.push({ id: 'q_' + Math.random().toString(36).slice(2, 8), type: 'text', label: '', placeholder: '', required: false, options: [], help_text: '' });
    drawFields(); fieldRows.lastChild.querySelector('input').focus();
  });

  // ── Summary (step 7) ───────────────────────────────────────────────────
  function buildSummary() {
    var s = spec();
    var dl = document.getElementById('summary');
    dl.textContent = '';
    function row(label, value) {
      if (value === undefined || value === null || value === '') return;
      dl.appendChild(el('dt', { text: label }));
      dl.appendChild(el('dd', { text: String(value) }));
    }
    function v(id) { var f = document.getElementById(id); return f ? f.value.trim() : ''; }
    var mode = ($('input[name="event_mode"]:checked') || {}).value || 'offline';
    var start = v('f-date') + (v('f-time') ? ' ' + v('f-time') : '');
    var end = v('f-end-date') ? v('f-end-date') + (v('f-end-time') ? ' ' + v('f-end-time') : '') : '';
    row('Kind', s.name);
    row('Title', v('f-title') || '(missing)');
    row('Category', v('f-category'));
    row('When', end && end !== start ? start + ' to ' + end : start || '(missing)');
    row('How', { offline: 'In person', online: 'Online', hybrid: 'In person and online' }[mode]);
    row('Where', mode === 'online' ? 'Online' : (v('f-venue') || ($('#f-room').selectedOptions[0] || {}).textContent || '(missing)'));
    if (!s.fest) {
      row('Registration', (v('f-reg-opens') ? 'From ' + v('f-reg-opens') + ' ' : '') + 'until ' + (v('f-deadline') || '(missing)'));
      var who = $$('input[name="allowed_participants"]:checked').map(function (c) { return c.nextElementSibling.textContent; });
      row('Who can register', who.length ? who.join(', ') : 'Default for this kind');
      row('Seats', v('f-capacity') && v('f-capacity') !== '0' ? v('f-capacity') : 'No limit');
      var p = v('f-participation');
      row('Taking part as', p === 'Individual' ? 'Individuals' : p + ' (' + v('f-team-min') + '–' + v('f-team-max') + ' members)');
      row('Fee', +v('f-fee') > 0 ? '₹' + v('f-fee') : 'Free');
      var crits = readJson('crit-json');
      if (!$('#competition-block').hidden) {
        row('Rounds', v('f-rounds'));
        row('Judging', crits.length ? crits.map(function (c) { return c.name + ' (/' + c.max_score + ')'; }).join(', ') : 'No criteria yet');
        row('Prizes', [v('f-prize1'), v('f-prize2'), v('f-prize3')].filter(Boolean).join(' · '));
      }
      row('Extra questions', extras.filter(function (f) { return (f.label || '').trim(); }).length || 'None');
    } else {
      row('Registration', 'None for the fest itself; add its events after saving.');
    }
    row('Sponsors', sponsors.filter(function (x) { return (x.name || '').trim(); }).map(function (x) { return x.name; }).join(', '));
  }

  form.addEventListener('submit', function (e) {
    syncCrit(); syncSponsors(); syncFields();
    for (var i = 1; i < steps.length; i++) {
      if (!stepOk(i)) { e.preventDefault(); show(i); return; }
    }
  });

  // ── Start ──────────────────────────────────────────────────────────────
  drawCrit(); drawSponsors(); drawFields(); previewBanner();
  applyType(true);
  if (!hadErrors && !$('#f-team-min').value) applyType(false);
  show(hadErrors ? 2 : (selectedType() && selectedType() !== 'custom' && /[?&]type=/.test(location.search) ? 2 : 1));
  if (hadErrors) { var box = document.getElementById('wz-errors'); if (box) box.focus(); }
})();
