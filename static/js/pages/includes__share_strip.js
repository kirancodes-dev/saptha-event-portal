/* Moved unchanged from an inline <script> in templates/includes/share_strip.html so the CSP
   needs no inline script (UPG-25). */
(function(){
  var base = window.location.href;
  document.querySelectorAll('.share-strip-wrap .shr-btn').forEach(function(btn){
    var u   = encodeURIComponent(btn.dataset.url || base);
    var t   = encodeURIComponent(btn.dataset.title || document.title);
    if(btn.classList.contains('shr-li')) btn.href = 'https://www.linkedin.com/sharing/share-offsite/?url=' + u;
    if(btn.classList.contains('shr-wa')) btn.href = 'https://api.whatsapp.com/send?text=' + t + '%20' + u;
    if(btn.classList.contains('shr-tw')) btn.href = 'https://twitter.com/intent/tweet?text=' + t + '&url=' + u;
    if(btn.classList.contains('shr-fb')) btn.href = 'https://www.facebook.com/sharer/sharer.php?u=' + u;
    // Show native share button on mobile if API available
    if(btn.classList.contains('shr-native') && navigator.share) btn.style.display = 'inline-flex';
  });
})();

function shareCopy(btn){
  var url = btn.dataset.url || window.location.href;
  navigator.clipboard.writeText(url).then(function(){
    var origHtml = btn.innerHTML;
    btn.style.background = '#d1fae5'; btn.style.color = '#065f46';
    btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
    setTimeout(function(){ btn.style.background=''; btn.style.color=''; btn.innerHTML=origHtml; }, 2000);
  });
}

function sharNative(btn){
  if(navigator.share) navigator.share({ title: btn.dataset.title, url: btn.dataset.url || window.location.href }).catch(function(){});
}
