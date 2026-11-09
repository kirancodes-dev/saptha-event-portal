// The organiser's own certificate design (UPG-206): drag the name box (and the
// other boxes switched on) over the design, pull a box's right edge to change
// its width, or type the numbers; the boxes and the form stay in step. The
// server draws the real certificate; this only shows where things go.
(function () {
    'use strict';

    var stage = document.getElementById('cdStage');
    var form = document.getElementById('cdForm');
    if (!stage || !form) { return; }
    var image = document.getElementById('cdImage');
    var qr = document.getElementById('cdQr');
    // The page in points: A4 landscape or portrait (as the PDF is drawn)
    var pageW = stage.getAttribute('data-orientation') === 'portrait' ? 595.28 : 841.89;
    var pageH = stage.getAttribute('data-orientation') === 'portrait' ? 841.89 : 595.28;

    function input(field, name) { return form.querySelector('[name="' + field + '_' + name + '"]'); }
    function num(field, name, fallback) {
        var el = input(field, name);
        var v = el ? parseFloat(el.value) : NaN;
        return isNaN(v) ? fallback : v;
    }
    function clamp(v, lo, hi) { return Math.min(Math.max(v, lo), hi); }
    function round(v) { return Math.round(v * 10) / 10; }

    function place(box) {
        var field = box.getAttribute('data-field');
        var on = input(field, 'on');
        box.hidden = on ? !on.checked : false;
        var w = stage.clientWidth;
        var scale = w / pageW;                                   // px per point
        var size = num(field, 'size', 20);
        var height = size * 1.3 * scale;
        var x = num(field, 'x', 20), y = num(field, 'y', 50), width = num(field, 'w', 60);
        box.style.left = x + '%';
        box.style.width = width + '%';
        box.style.height = height + 'px';
        box.style.top = (y / 100 * stage.clientHeight - height / 2) + 'px';
        var text = box.querySelector('[data-text]');
        text.style.fontSize = (size * scale) + 'px';
        text.style.fontWeight = input(field, 'bold') && input(field, 'bold').checked ? '700' : '400';
        text.style.color = input(field, 'color') ? input(field, 'color').value : '#1a1a1a';
        var align = input(field, 'align') ? input(field, 'align').value : 'center';
        text.style.textAlign = align === 'center' ? 'center' : align;
    }

    function placeQr() {
        var select = form.querySelector('[name="qr_corner"]');
        var corner = select ? select.value : 'br';
        var margin = 24 / pageW * 100;                          // as certificate_pdf.QR_MARGIN
        qr.style.left = qr.style.right = qr.style.top = qr.style.bottom = '';
        qr.style.width = (62 / pageW * 100) + '%';
        if (corner.charAt(1) === 'l') { qr.style.left = margin + '%'; } else { qr.style.right = margin + '%'; }
        if (corner.charAt(0) === 't') { qr.style.top = (24 / pageH * 100) + '%'; }
        else { qr.style.bottom = (34 / pageH * 100) + '%'; }
    }

    function all() {
        stage.querySelectorAll('[data-field]').forEach(place);
        placeQr();
    }

    function set(field, name, value) {
        var el = input(field, name);
        if (el) { el.value = round(value); }
    }

    // Dragging a box moves it; dragging its handle changes its width
    stage.querySelectorAll('[data-field]').forEach(function (box) {
        var field = box.getAttribute('data-field');
        box.addEventListener('pointerdown', function (e) {
            e.preventDefault();
            var resizing = !!e.target.closest('[data-handle]');
            var startX = e.clientX, startY = e.clientY;
            var x0 = num(field, 'x', 20), y0 = num(field, 'y', 50), w0 = num(field, 'w', 60);
            box.classList.add('is-active');
            box.setPointerCapture(e.pointerId);

            function move(ev) {
                var dx = (ev.clientX - startX) / stage.clientWidth * 100;
                var dy = (ev.clientY - startY) / stage.clientHeight * 100;
                if (resizing) {
                    set(field, 'w', clamp(w0 + dx, 5, 100 - x0));
                } else {
                    set(field, 'x', clamp(x0 + dx, 0, 100 - w0));
                    set(field, 'y', clamp(y0 + dy, 2, 98));
                }
                place(box);
            }
            function up(ev) {
                box.classList.remove('is-active');
                box.releasePointerCapture(ev.pointerId);
                box.removeEventListener('pointermove', move);
                box.removeEventListener('pointerup', up);
                box.removeEventListener('pointercancel', up);
            }
            box.addEventListener('pointermove', move);
            box.addEventListener('pointerup', up);
            box.addEventListener('pointercancel', up);
        });
    });

    form.addEventListener('input', all);
    form.addEventListener('change', all);
    window.addEventListener('resize', all);
    if (image.complete) { all(); } else { image.addEventListener('load', all); }
}());
