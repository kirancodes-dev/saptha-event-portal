/* Moved unchanged from an inline <script> in templates/index.html so the CSP
   needs no inline script (UPG-25). */
// ── SKELETON LOADER & INITIALIZATION ────
document.addEventListener('DOMContentLoaded',function(){
  const skeleton=document.getElementById('evGridSkeleton');
  const grid=document.getElementById('evGrid');
  if(grid){
    grid.style.display='';
    if(skeleton)skeleton.remove();
  }
  initVoiceSearch();
  initChatPrompt();
});

// ── INTERSECTION OBSERVER FOR SCROLL ANIMATIONS ────
function initScrollAnimations(){
  const options = { threshold: 0.1, rootMargin: '0px 0px -50px 0px' };
  const observer = new IntersectionObserver(function(entries){
    entries.forEach(function(entry){
      if(entry.isIntersecting){
        entry.target.classList.add('animate');
        if(entry.target.classList.contains('stat-counter') && !entry.target.dataset.counted){
          animateCounter(entry.target);
        }
      }
    });
  }, options);
  document.querySelectorAll('.scroll-animator, .stat-counter').forEach(function(el){
    observer.observe(el);
  });
}

// ── COUNTER ANIMATION ──────────────────────────
function animateCounter(el){
  el.dataset.counted = 'true';
  const target = parseInt(el.dataset.count) || 0;
  const duration = 2000;
  const start = Date.now();
  
  function update(){
    const elapsed = Date.now() - start;
    const progress = Math.min(elapsed / duration, 1);
    const current = Math.floor(target * progress);
    el.textContent = current.toLocaleString();
    
    if(progress < 1) requestAnimationFrame(update);
    else el.textContent = target.toLocaleString();
  }
  update();
}

// ── SMOOTH SCROLL (fixes anchor buttons) ──────
document.querySelectorAll('a[href^="#"]').forEach(function(a){
  a.addEventListener('click', function(e){
    var id = this.getAttribute('href').slice(1);
    if(!id) return;
    var el = document.getElementById(id);
    if(el){ e.preventDefault(); el.scrollIntoView({behavior:'smooth',block:'start'}); }
  });
});

// ── DEBUG TOAST (shows errors visibly on screen) ───────────────────────────
function _dbgToast(msg, isErr){
  var t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);z-index:99999;padding:12px 20px;border-radius:10px;font-size:13px;font-weight:700;max-width:90vw;word-break:break-all;box-shadow:0 4px 20px rgba(0,0,0,.4);';
  t.style.background = isErr ? '#ef4444' : '#10b981';
  t.style.color = '#fff';
  t.textContent = (isErr ? '❌ ERROR: ' : '✅ ') + msg;
  document.body.appendChild(t);
  setTimeout(function(){ t.remove(); }, 8000);
  console.log(isErr ? 'ERROR:' : 'DEBUG:', msg);
}
window.onerror = function(msg, src, line, col, err){
  _dbgToast(msg + ' (line ' + line + ')', true);
};

// ── EVENT CARD CLICK (event delegation) ────────────────────────────────────
document.addEventListener('click', function(e){
  // Don't trigger if clicking the Register/View Ticket button
  if(e.target.closest('.btn-reg')) return;
  
  var card = e.target.closest('.ev-card-clickable');
  if(!card) return;
  
  // Walk up to the .ev-col to read all data attributes
  var col = card.closest('.ev-col');
  if(!col){ _dbgToast('Could not find .ev-col parent', true); return; }
  
  if(col.dataset.regClosed === 'true'){
    alert('Registration is closed for this event.');
    return;
  }
  
  _dbgToast('Clicked event: ' + (col.dataset.id || 'NO-ID'));
  
  try {
    showEventModalFromCol(col);
  } catch(err) {
    _dbgToast(err.message + ' at ' + (err.stack ? err.stack.split('\n')[1] : '?'), true);
  }
});
document.addEventListener('keydown', function(e){
  if(e.key !== 'Enter' && e.key !== ' ') return;
  if(e.target.closest('.btn-reg')) return;
  var card = e.target.closest('.ev-card-clickable');
  if(!card) return;
  var col = card.closest('.ev-col');
  if(col){
    if(col.dataset.regClosed === 'true'){
      e.preventDefault();
      alert('Registration is closed for this event.');
      return;
    }
    e.preventDefault();
    showEventModalFromCol(col);
  }
});

// ── EVENT MODAL ────────────────────────────────────────────────────────────
function showEventModalFromCol(col){
  var modalEl = document.getElementById('eventModal');
  var body    = document.getElementById('eventModalBody');
  
  // STEP 1: Reset spinner and show modal immediately
  // This ensures the page is NEVER left frozen with backdrop
  if(body) body.innerHTML = '<div class="text-center py-4"><div class="spinner-border text-primary"></div><p class="mt-3 text-muted">Loading...</p></div>';
  
  if(typeof bootstrap === 'undefined' || !modalEl){
    // Bootstrap not loaded — just navigate to register page
    var eid = col ? col.dataset.id : '';
    if(eid) window.location.href = '/forms/register/' + eid;
    return;
  }
  
  
  
  // Show modal NOW (with spinner) — user sees it opening immediately
  var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
  modal.show();
  
  // STEP 2: Populate content (safely, after modal is visible)
  try {
    if(!col){ body.innerHTML = '<p class="text-danger">Error: event data not found.</p>'; return; }
    
    var evId    = col.dataset.id    || '';
    var evCat   = col.dataset.cat   || 'General';
    var evDate  = col.dataset.date  || '';
    var evReg   = col.dataset.registered === 'true';
    var evRegId = col.dataset.regId || '';
    
    var title       = (col.querySelector('.ev-title')?.textContent || 'Event').trim();
    var description = (col.querySelector('.ev-desc')?.textContent  || 'No description available.').trim();
    var dateText    = (col.querySelector('[data-info="date"]')?.textContent  || evDate || 'TBA').trim();
    var venue       = (col.querySelector('[data-info="venue"]')?.textContent || 'TBA').trim();
    var fee         = (col.querySelector('[data-info="fee"]')?.textContent   || 'Free').trim();
    var regCount    = (col.querySelector('.ev-reg-count')?.textContent       || '0 registered').trim();
    var bannerSrc   = col.querySelector('.ev-banner img')?.src || '';
    
    // Update modal title
    var titleEl = document.getElementById('eventModalLabel');
    if(titleEl) titleEl.textContent = title;
    
    // Banner image
    var bannerHtml = bannerSrc
      ? '<div style="margin:-24px -24px 20px;border-radius:12px 12px 0 0;overflow:hidden;max-height:200px;"><img src="' + safeUrl(bannerSrc) + '" style="width:100%;height:200px;object-fit:cover;display:block;" alt=""></div>'
      : '';
    
    // Category badge colour
    var catColour = {technical:'#3b82f6',cultural:'#a855f7',sports:'#10b981',management:'#f59e0b'};
    var badgeBg = catColour[evCat.toLowerCase()] || '#6b7280';
    
    // Register button (the card's text and IDs are escaped into the HTML: BLK-19)
    var regBtnHtml = evReg && evRegId
      ? '<button class="modal-btn" style="background:#10b981;color:#fff;border:none;" data-h-click="se:go" data-href="' + safeUrl('/ticket/' + encodeURIComponent(evRegId)) + '"><i class="fas fa-ticket-alt me-1"></i>View My Ticket</button>'
      : '<button class="modal-btn modal-btn-primary" data-h-click="se:go" data-href="' + safeUrl('/forms/register/' + encodeURIComponent(evId)) + '"><i class="fas fa-arrow-right me-1"></i>Register Now</button>';
    
    // Calendar section (only if we have a valid date)
    var calHtml = '';
    if(evDate && /^\d{4}-\d{2}-\d{2}$/.test(evDate)){
      var gUrl = 'https://calendar.google.com/calendar/render?action=TEMPLATE&text=' + encodeURIComponent(title) + '&dates=' + evDate.replace(/-/g,'') + '&location=' + encodeURIComponent(venue);
      calHtml = '<div class="event-modal-section">'
        + '<h5>Add to Calendar</h5>'
        + '<div class="d-flex flex-wrap gap-2">'
        + '<a href="' + safeUrl(gUrl) + '" target="_blank" class="btn btn-sm btn-outline-primary"><i class="fab fa-google me-1"></i>Google Calendar</a>'
        + '</div></div>';
    }
    
    body.innerHTML =
      bannerHtml +
      '<div class="event-modal-meta">'
        + '<div class="event-modal-meta-item"><i class="fas fa-calendar-alt"></i><span>' + escapeHtml(dateText) + '</span></div>'
        + '<div class="event-modal-meta-item"><i class="fas fa-map-marker-alt"></i><span>' + escapeHtml(venue) + '</span></div>'
        + '<div class="event-modal-meta-item"><i class="fas fa-tag"></i><span style="text-transform:capitalize;color:' + escapeHtml(badgeBg) + ';font-weight:700;">' + escapeHtml(evCat) + '</span></div>'
        + '<div class="event-modal-meta-item"><i class="fas fa-users"></i><span>' + escapeHtml(regCount) + '</span></div>'
      + '</div>'
      + '<div class="event-modal-section"><h5>About This Event</h5><p>' + escapeHtml(description) + '</p></div>'
      + '<div class="event-modal-section"><h5>Entry Fee</h5><p style="font-size:18px;font-weight:800;color:var(--orange);">' + escapeHtml(fee) + '</p></div>'
      + calHtml
      + '<div class="event-modal-section"><h5>Event Highlights</h5><p>\uD83C\uDFAF Competitive spirit \u2022 \uD83C\uDFC6 Amazing prizes \u2022 \uD83E\uDD1D Networking opportunities \u2022 \uD83C\uDF93 Skill development</p></div>'
      + '<div class="modal-btn-group">' + regBtnHtml + '<button class="modal-btn modal-btn-secondary" data-bs-dismiss="modal">Close</button></div>';
      
  } catch(err) {
    // Safety net — show error in modal so page is NEVER frozen
    if(body) body.innerHTML = '<div class="alert alert-danger"><strong>Could not load event details.</strong><br><small>' + escapeHtml(err.message) + '</small></div><div class="modal-btn-group"><button class="modal-btn modal-btn-secondary" data-bs-dismiss="modal">Close</button></div>';
    console.error('showEventModalFromCol error:', err);
  }
}

// Legacy alias
function showEventModal(eventId){
  var col = document.querySelector('.ev-col[data-id="' + CSS.escape(eventId) + '"]');
  if(col) {
    if(col.dataset.regClosed === 'true'){
      alert('Registration is closed for this event.');
      return;
    }
    showEventModalFromCol(col);
  }
  else if(eventId) window.location.href = '/forms/register/' + eventId;
}

// ── CALENDAR HELPER FUNCTIONS ──────────────────
function getGoogleCalendarUrl(title, dateStr, description, venue) {
  const cleanDate = dateStr.replace(/-/g, '').trim();
  if (cleanDate.length !== 8) return '';
  const dateObj = new Date(dateStr);
  dateObj.setDate(dateObj.getDate() + 1);
  const nextDayStr = dateObj.toISOString().slice(0, 10).replace(/-/g, '');
  return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${cleanDate}/${nextDayStr}&details=${encodeURIComponent(description)}&location=${encodeURIComponent(venue)}`;
}

function downloadiCal(title, dateStr, description, venue) {
  const cleanDate = dateStr.replace(/-/g, '').trim();
  if (cleanDate.length !== 8) return;
  const dateObj = new Date(dateStr);
  dateObj.setDate(dateObj.getDate() + 1);
  const nextDayStr = dateObj.toISOString().slice(0, 10).replace(/-/g, '');
  
  const icsContent = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//SapthaEvent//Event Calendar//EN',
    'BEGIN:VEVENT',
    `SUMMARY:${title}`,
    `DTSTART;VALUE=DATE:${cleanDate}`,
    `DTEND;VALUE=DATE:${nextDayStr}`,
    `DESCRIPTION:${description}`,
    `LOCATION:${venue}`,
    'END:VEVENT',
    'END:VCALENDAR'
  ].join('\r\n');
  
  const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.setAttribute('download', `${title.replace(/[^a-z0-9]/gi, '_').toLowerCase()}.ics`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ── VOICE SEARCH HELPER FUNCTIONS ──────────────
let recognition = null;
function initVoiceSearch() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (SpeechRecognition) {
    const voiceBtn = document.getElementById('evVoiceSearch');
    if (voiceBtn) {
      voiceBtn.style.display = 'block';
      recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'en-US';
      
      recognition.onstart = function() {
        voiceBtn.classList.add('listening');
        document.getElementById('evSearch').placeholder = "Listening...";
      };
      
      recognition.onerror = function(event) {
        console.error("Speech recognition error", event.error);
        stopListening();
      };
      
      recognition.onend = function() {
        stopListening();
      };
      
      recognition.onresult = function(event) {
        const resultText = event.results[0][0].transcript;
        const searchInput = document.getElementById('evSearch');
        searchInput.value = resultText;
        filterEvs();
      };
    }
  }
}

function startVoiceSearch() {
  if (!recognition) return;
  const voiceBtn = document.getElementById('evVoiceSearch');
  if (voiceBtn.classList.contains('listening')) {
    recognition.stop();
  } else {
    try {
      recognition.start();
    } catch (e) {
      console.error(e);
    }
  }
}

function stopListening() {
  const voiceBtn = document.getElementById('evVoiceSearch');
  if (voiceBtn) {
    voiceBtn.classList.remove('listening');
  }
  const searchInput = document.getElementById('evSearch');
  if (searchInput) {
    searchInput.placeholder = "Search events...";
  }
}

// ── CHATBOT PROMPT HELPER FUNCTIONS ────────────
function initChatPrompt() {
  if (localStorage.getItem('sparky_prompt_dismissed') === 'true') {
    return;
  }
  setTimeout(function() {
    const bubble = document.getElementById('chatPromptBubble');
    const chatWin = document.getElementById('chatWin');
    if (bubble && chatWin && !chatWin.classList.contains('open')) {
      bubble.style.display = 'flex';
    }
  }, 2000);
}

function dismissChatPrompt(e) {
  if (e) e.stopPropagation();
  const bubble = document.getElementById('chatPromptBubble');
  if (bubble) {
    bubble.style.opacity = '0';
    bubble.style.transform = 'scale(0.8)';
    bubble.style.transition = 'all 0.3s ease';
    setTimeout(() => {
      bubble.style.display = 'none';
    }, 300);
  }
  localStorage.setItem('sparky_prompt_dismissed', 'true');
}

// ── UNIFIED FILTERING, SEARCH, AND PAGINATION ──
let activeCategory = 'all';
let searchKeyword = '';
let visibleCount = 9; // Show 9 initially

// Quick filter states
let filterFree = false;
let filterTeam = false;
let filterIndividual = false;
let filterSoon = false;

function setCategoryFilter(cat, btn) {
  document.querySelectorAll('.ftab').forEach(function(b){ 
    b.classList.remove('active'); 
    b.setAttribute('aria-pressed', 'false'); 
  });
  btn.classList.add('active');
  btn.setAttribute('aria-pressed', 'true');
  activeCategory = cat;
  visibleCount = 9; // Reset pagination
  applyFiltersAndPagination();
}

function filterEvs() {
  const searchInput = document.getElementById('evSearch');
  const clearBtn = document.getElementById('evSearchClear');
  searchKeyword = searchInput.value.trim().toLowerCase();
  
  if (searchKeyword) {
    clearBtn.classList.remove('d-none');
  } else {
    clearBtn.classList.add('d-none');
  }
  
  visibleCount = 9; // Reset pagination
  applyFiltersAndPagination();
}

function clearSearch() {
  const searchInput = document.getElementById('evSearch');
  searchInput.value = '';
  document.getElementById('evSearchClear').classList.add('d-none');
  searchKeyword = '';
  visibleCount = 9;
  applyFiltersAndPagination();
  searchInput.focus();
}

function toggleQuickFilter(type) {
  const pill = document.getElementById('qf' + type.charAt(0).toUpperCase() + type.slice(1));
  if (!pill) return;
  
  if (type === 'free') {
    filterFree = !filterFree;
    pill.classList.toggle('active', filterFree);
    pill.setAttribute('aria-pressed', filterFree ? 'true' : 'false');
  } else if (type === 'team') {
    filterTeam = !filterTeam;
    pill.classList.toggle('active', filterTeam);
    pill.setAttribute('aria-pressed', filterTeam ? 'true' : 'false');
    // Mutually exclusive with individual
    if (filterTeam && filterIndividual) {
      filterIndividual = false;
      const indPill = document.getElementById('qfIndividual');
      if (indPill) {
        indPill.classList.remove('active');
        indPill.setAttribute('aria-pressed', 'false');
      }
    }
  } else if (type === 'individual') {
    filterIndividual = !filterIndividual;
    pill.classList.toggle('active', filterIndividual);
    pill.setAttribute('aria-pressed', filterIndividual ? 'true' : 'false');
    // Mutually exclusive with team
    if (filterIndividual && filterTeam) {
      filterTeam = false;
      const teamPill = document.getElementById('qfTeam');
      if (teamPill) {
        teamPill.classList.remove('active');
        teamPill.setAttribute('aria-pressed', 'false');
      }
    }
  } else if (type === 'soon') {
    filterSoon = !filterSoon;
    pill.classList.toggle('active', filterSoon);
    pill.setAttribute('aria-pressed', filterSoon ? 'true' : 'false');
  }
  
  visibleCount = 9; // Reset pagination
  applyFiltersAndPagination();
}

function loadMoreEvents() {
  visibleCount += 9;
  applyFiltersAndPagination();
}

function applyFiltersAndPagination() {
  const cards = document.querySelectorAll('.ev-col');
  let matchCount = 0;
  
  cards.forEach(function(card) {
    const cardCat = card.dataset.cat || '';
    const cardSearch = card.dataset.search || '';
    const cardFree = card.dataset.free === 'true';
    const cardTeam = card.dataset.team === 'true';
    const cardDateStr = card.dataset.date || '';
    
    const catMatch = (activeCategory === 'all' || cardCat === activeCategory.toLowerCase());
    const searchMatch = (!searchKeyword || cardSearch.includes(searchKeyword));
    const freeMatch = (!filterFree || cardFree);
    const teamMatch = (!filterTeam || cardTeam);
    const individualMatch = (!filterIndividual || !cardTeam);
    
    // Check if event is happening in the next 7 days, excluding past events
    let soonMatch = true;
    if (filterSoon) {
      if (!cardDateStr) soonMatch = false;
      else {
        const eventDate = new Date(cardDateStr);
        const today = new Date();
        today.setHours(0,0,0,0);
        eventDate.setHours(0,0,0,0);
        const diffDays = Math.ceil((eventDate.getTime() - today.getTime()) / (1000 * 60 * 60 * 24));
        soonMatch = diffDays >= 0 && diffDays <= 7;
      }
    }
    
    const isMatch = catMatch && searchMatch && freeMatch && teamMatch && individualMatch && soonMatch;
    
    if (isMatch) {
      matchCount++;
      if (matchCount <= visibleCount) {
        card.style.setProperty('display', '', 'important');
        if (!card.classList.contains('animate')) {
          card.classList.add('animate');
        }
      } else {
        card.style.setProperty('display', 'none', 'important');
      }
    } else {
      card.style.setProperty('display', 'none', 'important');
    }
  });
  
  // Toggle No Results State
  const noResults = document.getElementById('noSearchResults');
  if (noResults) {
    if (matchCount === 0) {
      noResults.classList.remove('d-none');
    } else {
      noResults.classList.add('d-none');
    }
  }
  
  // Toggle Load More Button
  const loadMoreContainer = document.getElementById('loadMoreContainer');
  if (loadMoreContainer) {
    if (matchCount > visibleCount) {
      loadMoreContainer.classList.remove('d-none');
    } else {
      loadMoreContainer.classList.add('d-none');
    }
  }
}

// ── STICKY CONTROL SCROLL HANDLER ─────────────
function initStickyControls() {
  const wrapper = document.querySelector('.sticky-controls-wrapper');
  if (!wrapper) return;
  
  // Toggle is-sticky styling based on scroll position
  window.addEventListener('scroll', function() {
    if (window.scrollY > 300) {
      wrapper.classList.add('is-sticky');
    } else {
      wrapper.classList.remove('is-sticky');
    }
  });
}

// ── CATEGORY TAB SCROLL AFFORDANCE ────────────
function initCategoryScrollAffordance() {
  const ftabs = document.querySelector('.ftabs');
  const container = document.querySelector('.ftabs-scroll-container');
  if (!ftabs || !container) return;
  
  function updateScrollHints() {
    const scrollLeft = ftabs.scrollLeft;
    const maxScrollLeft = ftabs.scrollWidth - ftabs.clientWidth;
    
    container.classList.toggle('can-scroll-left', scrollLeft > 2);
    container.classList.toggle('can-scroll-right', scrollLeft < maxScrollLeft - 2);
  }
  
  ftabs.addEventListener('scroll', updateScrollHints);
  window.addEventListener('resize', updateScrollHints);
  
  // Initial run after render completes
  setTimeout(updateScrollHints, 500);
}

// ── CHATBOT ────────────────────────────────────
var chatOpen = false;
function toggleChat(){
  chatOpen = !chatOpen;
  document.getElementById('chatWin').classList.toggle('open', chatOpen);
  document.getElementById('chatIcon').className = chatOpen ? 'fas fa-times' : 'fas fa-robot';
  if(chatOpen) {
    document.getElementById('chatInp').focus();
    dismissChatPrompt();
  }
}
async function sendChat(){
  var inp = document.getElementById('chatInp');
  var msg = inp.value.trim();
  if(!msg) return;
  inp.value = '';
  addBubble(msg, 'user');
  var t = addTyping();
  try{
    var r = await fetch('/chatbot/ask', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message:msg})
    });
    var d = await r.json();
    t.remove();
    addBubble(d.reply || 'Sorry, I could not get a response. Please try again.', 'bot');
  } catch(err){
    t.remove();
    addBubble('Something went wrong. Please try again in a moment.', 'bot');
  }
}
function addBubble(text, role){
  var msgs = document.getElementById('chatMsgs');
  var wrap = document.createElement('div');
  wrap.className = 'bw ' + role;
  // The visitor's message and the AI's reply are text (BLK-19)
  wrap.innerHTML = '<div class="bb ' + escapeHtml(role) + '">' + escapeHtml(text) + '</div>';
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
  return wrap;
}
function addTyping(){
  var msgs = document.getElementById('chatMsgs');
  var wrap = document.createElement('div');
  wrap.className = 'bw';
  wrap.innerHTML = '<div class="bb bot"><div class="tdots"><span></span><span></span><span></span></div></div>';
  msgs.appendChild(wrap);
  msgs.scrollTop = msgs.scrollHeight;
  return wrap;
}

// ── FORM VALIDATION ENHANCEMENT ────────────────
function setupFormValidation(){
  var inputs = document.querySelectorAll('input[type="email"], input[type="text"], textarea');
  inputs.forEach(function(input){
    input.addEventListener('blur', function(){
      validateInput(this);
    });
    input.addEventListener('input', function(){
      if(this.classList.contains('is-invalid')){
        validateInput(this);
      }
    });
  });
}

function validateInput(input){
  var value = input.value.trim();
  var container = input.closest('.input-group') || input.parentElement;
  var feedback = container.querySelector('.input-feedback');
  var icon = container.querySelector('.input-icon');
  
  if(!value) {
    input.classList.remove('is-valid');
    input.classList.add('is-invalid');
    if(feedback) feedback.textContent = 'This field is required';
    if(feedback) feedback.classList.remove('success');
    if(feedback) feedback.classList.add('error');
    if(icon) { icon.classList.remove('success'); icon.classList.add('error'); icon.innerHTML = '<i class="fas fa-exclamation-circle"></i>'; }
    return false;
  }
  
  input.classList.remove('is-invalid');
  input.classList.add('is-valid');
  if(feedback) feedback.textContent = '✓ Looks good!';
  if(feedback) feedback.classList.remove('error');
  if(feedback) feedback.classList.add('success');
  if(icon) { icon.classList.remove('error'); icon.classList.add('success'); icon.innerHTML = '<i class="fas fa-check-circle"></i>'; }
  return true;
}

// ── INITIALIZE ON PAGE LOAD ────────────────────
document.addEventListener('DOMContentLoaded', function(){
  initScrollAnimations();
  setupFormValidation();
  initStickyControls();
  initCategoryScrollAffordance();
  
  // Initialize unified filtering & pagination once skeletal loader starts disappearing
  setTimeout(applyFiltersAndPagination, 350);
});
