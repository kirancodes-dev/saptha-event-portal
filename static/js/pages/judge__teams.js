/* Moved unchanged from an inline <script> in templates/judge/teams.html so the CSP
   needs no inline script (UPG-25). */
(function(){var m=document.querySelector('meta[name="csrf-token"]');var t=m?m.getAttribute('content'):'';
if(!t||!window.fetch)return;var of_=window.fetch.bind(window);window.fetch=function(i,n){n=n||{};
var mth=(n.method||(typeof i==='object'&&i.method)||'GET').toUpperCase();
if(['POST','PUT','DELETE','PATCH'].indexOf(mth)===-1)return of_(i,n);
var u=typeof i==='string'?i:(i&&i.url)||'';try{var U=new URL(u,location.origin);if(U.origin!==location.origin)return of_(i,n);}catch(_){}
var h=new Headers(n.headers||{});if(!h.has('X-CSRFToken'))h.set('X-CSRFToken',t);n.headers=h;
if(!n.credentials)n.credentials='same-origin';return of_(i,n);};})();
