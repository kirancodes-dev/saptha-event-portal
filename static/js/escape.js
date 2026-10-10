// static/js/escape.js — put values into HTML that a script builds (BLK-19).
// Names, titles and messages come from other people; inserted as HTML they
// could run as script in whoever views the page.
(function (root) {
    'use strict';

    // Text in an element or a quoted attribute.
    function escapeHtml(value) {
        if (value === null || value === undefined) return '';
        return String(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;')
            .replace(/`/g, '&#96;');
    }

    // A value inside an on…="…" attribute: the browser decodes entities
    // before running the handler, so it must be a JavaScript literal first.
    function escapeJsAttr(value) {
        return escapeHtml(JSON.stringify(value === undefined ? null : value));
    }

    // A link or image address: web, mail and phone links and relative
    // paths; anything else (javascript:, data:, …) becomes '#'.
    function safeUrl(value) {
        var url = String(value === null || value === undefined ? '' : value).trim();
        // Browsers ignore control characters and spaces inside a scheme
        var scheme = /^([a-z][a-z0-9+.\-]*):/i.exec(url.replace(/[\u0000- \u007f]+/g, ''));
        if (scheme && !/^(https?|mailto|tel)$/i.test(scheme[1])) return '#';
        return escapeHtml(url);
    }

    root.escapeHtml = escapeHtml;
    root.escapeJsAttr = escapeJsAttr;
    root.safeUrl = safeUrl;
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = { escapeHtml: escapeHtml, escapeJsAttr: escapeJsAttr, safeUrl: safeUrl };
    }
})(typeof window !== 'undefined' ? window : this);
