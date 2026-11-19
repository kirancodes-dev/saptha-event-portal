// The organiser's own certificate design (UPG-206): drag the name box (and the
// other boxes switched on, and a placed QR, UPG-315) over the design, pull a box's right edge to change
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
        // The font picked for the box (UPG-330); one with no bold file prints regular, so show it so
        var font = input(field, 'font');
        var option = font && font.selectedIndex >= 0 ? font.options[font.selectedIndex] : null;
        var hasBold = !option || option.getAttribute('data-bold') !== '0';
        text.style.fontFamily = option ? '"' + option.getAttribute('data-family') + '", "cert-noto", sans-serif' : '';
        text.style.fontWeight = hasBold && input(field, 'bold') && input(field, 'bold').checked ? '700' : '400';
        text.style.color = input(field, 'color') ? input(field, 'color').value : '#1a1a1a';
        var align = input(field, 'align') ? input(field, 'align').value : 'center';
        text.style.textAlign = align === 'center' ? 'center' : align;
    }

    function qrNum(name, fallback) {
        var el = form.querySelector('[name="qr_' + name + '"]');
        var v = el ? parseFloat(el.value) : NaN;
        return isNaN(v) ? fallback : v;
    }
    function setQr(name, value) {
        var el = form.querySelector('[name="qr_' + name + '"]');
        if (el) { el.value = round(value); }
    }
    function placed() {
        var select = form.querySelector('[name="qr_corner"]');
        return !!select && select.value === 'place';
    }

    function placeQr() {
        var select = form.querySelector('[name="qr_corner"]');
        var corner = select ? select.value : 'br';
        var margin = 24 / pageW * 100;                          // as certificate_pdf.QR_MARGIN
        var fields = form.querySelector('[data-qr-place]');
        if (fields) { fields.hidden = !placed(); }
        qr.classList.toggle('is-placed', placed());
        qr.style.left = qr.style.right = qr.style.top = qr.style.bottom = '';
        if (placed()) {                                         // the organiser's box (UPG-315), as certificate_pdf.placed_qr
            qr.style.width = qrNum('size', 11.8) + '%';
            qr.style.left = qrNum('x', 82.2) + '%';
            qr.style.top = qrNum('y', 44.8) + '%';
            return;
        }
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

    // The placed QR (UPG-315): drag to move, drag the round handle to resize; it stays square and on the page
    qr.addEventListener('pointerdown', function (e) {
        if (!placed()) { return; }
        e.preventDefault();
        var resizing = !!e.target.closest('[data-handle]');
        var startX = e.clientX, startY = e.clientY;
        var x0 = qrNum('x', 82.2), y0 = qrNum('y', 44.8), s0 = qrNum('size', 11.8);
        var ratio = stage.clientHeight / stage.clientWidth;    // the page's height over its width
        qr.classList.add('is-active');
        qr.setPointerCapture(e.pointerId);

        function move(ev) {
            var dx = (ev.clientX - startX) / stage.clientWidth * 100;
            var dy = (ev.clientY - startY) / stage.clientHeight * 100;
            if (resizing) {
                var grow = Math.max(dx, dy * ratio);
                setQr('size', clamp(s0 + grow, 5, Math.min(30, 100 - x0, (100 - y0) * ratio)));
            } else {
                setQr('x', clamp(x0 + dx, 0, 100 - s0));
                setQr('y', clamp(y0 + dy, 0, 100 - s0 / ratio));
            }
            placeQr();
        }
        function up(ev) {
            qr.classList.remove('is-active');
            qr.releasePointerCapture(ev.pointerId);
            qr.removeEventListener('pointermove', move);
            qr.removeEventListener('pointerup', up);
            qr.removeEventListener('pointercancel', up);
        }
        qr.addEventListener('pointermove', move);
        qr.addEventListener('pointerup', up);
        qr.addEventListener('pointercancel', up);
    });

    form.addEventListener('input', all);
    form.addEventListener('change', all);
    window.addEventListener('resize', all);
    if (image.complete) { all(); } else { image.addEventListener('load', all); }
    // The certificate fonts (UPG-330), for the preview only: declared here from the
    // first Font list, each file fetched only when a box uses it. The site's own
    // typography stays the three self-hosted families (UPG-24).
    var fontList = form.querySelector('[data-font-select]');
    if (fontList && window.FontFace && document.fonts) {
        Array.prototype.forEach.call(fontList.options, function (o) {
            var family = o.getAttribute('data-family');
            [['400', o.getAttribute('data-url')], ['700', o.getAttribute('data-bold-url')]].forEach(function (w) {
                if (family && w[1]) {
                    document.fonts.add(new FontFace(family, 'url("' + w[1] + '")', { weight: w[0], display: 'swap' }));
                }
            });
        });
        document.fonts.ready.then(all);
        if (document.fonts.addEventListener) { document.fonts.addEventListener('loadingdone', all); }
    }
}());
