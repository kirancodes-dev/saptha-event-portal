/* Projector view of live polls and questions (UPG-160). Updates over SSE from
   /interact/<event>/stream; every piece of text is set with textContent, so a
   question typed as HTML shows as text. */
(function () {
  var root = document.getElementById('screen');
  if (!root || !window.EventSource) return;
  var eventId = root.getAttribute('data-event-id');

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = String(text);
    return e;
  }

  function drawPolls(polls) {
    var box = document.getElementById('polls');
    box.replaceChildren();
    if (!polls.length) { box.appendChild(el('p', 'muted', 'No poll yet.')); return; }
    polls.forEach(function (p) {
      var card = el('div', 'poll');
      card.appendChild(el('div', 'poll-q', p.question));
      p.options.forEach(function (option, i) {
        var n = p.counts[i] || 0;
        var bar = el('div', 'bar');
        var fill = el('div', 'bar-fill');
        fill.style.width = (p.votes ? Math.round(100 * n / p.votes) : 0) + '%';
        var text = el('div', 'bar-text');
        text.appendChild(el('span', '', option));
        text.appendChild(el('span', '', n));
        bar.appendChild(fill);
        bar.appendChild(text);
        card.appendChild(bar);
      });
      card.appendChild(el('div', 'muted', p.votes + ' answered'));
      box.appendChild(card);
    });
  }

  function drawQuestions(questions) {
    var box = document.getElementById('questions');
    box.replaceChildren();
    if (!questions.length) { box.appendChild(el('p', 'muted', 'No questions yet.')); return; }
    questions.forEach(function (q) {
      var row = el('div', 'q' + (q.status === 'answered' ? ' answered' : ''));
      row.appendChild(el('span', '', q.text));
      row.appendChild(el('span', 'q-votes', '▲ ' + q.votes));
      box.appendChild(row);
    });
  }

  function connect() {
    var source = new EventSource('/interact/' + encodeURIComponent(eventId) + '/stream');
    source.onmessage = function (msg) {
      try {
        var data = JSON.parse(msg.data);
        if (data.error) return;
        drawPolls(data.polls || []);
        drawQuestions(data.questions || []);
      } catch (e) { /* keep the last good view */ }
    };
    source.addEventListener('reconnect', function () { source.close(); setTimeout(connect, 500); });
    source.onerror = function () { source.close(); setTimeout(connect, 5000); };
  }
  connect();
})();
