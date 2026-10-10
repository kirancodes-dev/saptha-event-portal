/* Moved unchanged from an inline <script> in templates/participant/matchmaker.html so the CSP
   needs no inline script (UPG-25). */
        var activeMatches = [];
        var currentMatchIdx = 0;
        var currentPeerId = null;

        // Interactive tag click togglers
        document.querySelectorAll('.skill-tag, .interest-tag').forEach(tag => {
            tag.addEventListener('click', function() {
                tag.classList.toggle('selected');
            });
        });

        function getSelectedSkills() {
            var arr = [];
            document.querySelectorAll('.skill-tag.selected').forEach(t => arr.push(t.getAttribute('data-val')));
            return arr;
        }

        function getSelectedInterests() {
            var arr = [];
            document.querySelectorAll('.interest-tag.selected').forEach(t => arr.push(t.getAttribute('data-val')));
            return arr;
        }

        function recalculateMatches() {
            var container = document.getElementById('cards-container');
            container.innerHTML = `<div class="text-muted small"><i class="fas fa-spinner fa-spin fs-4 mb-2"></i> Recalculating scores...</div>`;
            
            fetch('/participant/matchmaker/api/match', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    skills: getSelectedSkills(),
                    interests: getSelectedInterests()
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success && data.matches.length > 0) {
                    activeMatches = data.matches;
                    currentMatchIdx = 0;
                    renderMatchCards();
                } else {
                    container.innerHTML = `<div class="text-muted small">No potential partners found matching current criteria. Try selecting more interests!</div>`;
                }
            })
            .catch(err => {
                console.error("Match error:", err);
                container.innerHTML = `<div class="text-danger small">Network error matching team profiles.</div>`;
            });
        }

        function getCsrfToken() {
            // Check meta tags or cookie
            var meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }

        function renderMatchCards() {
            var container = document.getElementById('cards-container');
            container.innerHTML = "";

            if (currentMatchIdx >= activeMatches.length) {
                container.innerHTML = `<div class="text-center p-3 text-muted">
                                            <i class="fas fa-circle-check text-success fs-3 mb-2"></i>
                                            <h6 class="fw-bold text-white">All Caught Up!</h6>
                                            <p class="small m-0">You have reviewed all compatible participant matches.</p>
                                        </div>`;
                return;
            }

            // Render matching card
            var m = activeMatches[currentMatchIdx];
            var card = document.createElement('div');
            card.className = 'match-card';
            card.id = 'current-active-card';
            
            // Build Skills list
            var skillsHtml = m.skills.slice(0, 3).map(s => `<span class="badge bg-secondary bg-opacity-25 text-white-50 mr-1" style="font-size:10px;">${escapeHtml(s)}</span>`).join(' ');
            
            var reasonHtml = m.match_reason ? `
                <div class="mt-2 pt-2 border-top border-secondary border-opacity-20" style="font-size: 11px; color: #c084fc;">
                    <i class="fas fa-wand-magic-sparkles me-1"></i><strong>AI Match Insight:</strong> ${escapeHtml(m.match_reason)}
                </div>
            ` : '';
            
            card.innerHTML = `
                <div class="d-flex justify-content-between align-items-start">
                    <span class="match-score-badge"><i class="fas fa-handshake"></i> ${escapeHtml(m.match_score)}% Match</span>
                    <span class="badge bg-dark text-muted font-monospace" style="font-size: 10px;">COLLABORATOR</span>
                </div>

                <div class="text-center my-3">
                    <img class="avatar-circle mb-3" src="${safeUrl(m.avatar)}">
                    <h5 class="fw-bold text-white m-0">${escapeHtml(m.name)}</h5>
                    <p class="text-muted small m-0">${escapeHtml(m.college)}</p>
                </div>

                <div class="text-start bg-dark bg-opacity-40 p-3 rounded border border-secondary border-opacity-10 mb-3" style="min-height: 90px;">
                    <p class="text-light small m-0" style="font-style: italic;">"${escapeHtml(m.bio)}"</p>
                    ${reasonHtml}
                </div>

                <div class="d-flex justify-content-between align-items-center">
                    <div class="text-start">
                        <span class="text-muted block small mb-1" style="font-size: 10px; font-weight: 700; letter-spacing: 0.5px;">EXPERTISE</span>
                        <div>${skillsHtml}</div>
                    </div>
                    <button class="btn btn-primary btn-sm px-3 rounded-pill fw-bold" data-h-click="se:call" data-call="connectChat" data-args="${escapeHtml(JSON.stringify([m.id, m.name, m.avatar]))}">
                        <i class="fas fa-comments me-1"></i> Chat
                    </button>
                </div>
            `;

            container.appendChild(card);
        }

        // Swipe interactions
        function swipeLeft() {
            var card = document.getElementById('current-active-card');
            if (card) {
                card.style.transform = "translateX(-150%) rotate(-20deg)";
                card.style.opacity = 0;
                setTimeout(nextCard, 350);
            }
        }

        function swipeRight() {
            var card = document.getElementById('current-active-card');
            if (card) {
                card.style.transform = "translateX(150%) rotate(20deg)";
                card.style.opacity = 0;
                setTimeout(function() {
                    var m = activeMatches[currentMatchIdx];
                    connectChat(m.id, m.name, m.avatar);
                    nextCard();
                }, 350);
            }
        }

        function nextCard() {
            currentMatchIdx++;
            renderMatchCards();
        }

        // Chat flow
        function connectChat(peerId, name, avatar) {
            currentPeerId = peerId;
            document.getElementById('chat-peer-name').innerText = name;
            document.getElementById('chat-avatar').src = avatar;
            
            // Reset chat messages
            var chatBody = document.getElementById('chat-body-container');
            chatBody.innerHTML = `<div class="chat-bubble incoming">
                                    Hey! I noticed we both registered for the targeted event. Would love to collaborate together!
                                  </div>`;
            
            var drawer = document.getElementById('chat-drawer');
            drawer.classList.add('active');
        }

        function closeChat() {
            document.getElementById('chat-drawer').classList.remove('active');
        }

        document.getElementById('chat-input-form').addEventListener('submit', function(e) {
            e.preventDefault();
            var input = document.getElementById('chat-input-field');
            var val = input.value.trim();
            if (!val) return;

            // Render outgoing message
            var chatBody = document.getElementById('chat-body-container');
            var outDiv = document.createElement('div');
            outDiv.className = "chat-bubble outgoing";
            outDiv.innerText = val;
            chatBody.appendChild(outDiv);
            chatBody.scrollTop = chatBody.scrollHeight;

            input.value = "";

            // Call mock message exchange api for automatic peer response
            fetch('/participant/matchmaker/api/message', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    peer_id: currentPeerId,
                    message: val
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    setTimeout(function() {
                        var inDiv = document.createElement('div');
                        inDiv.className = "chat-bubble incoming";
                        inDiv.innerText = data.reply;
                        chatBody.appendChild(inDiv);
                        chatBody.scrollTop = chatBody.scrollHeight;
                    }, 1500);
                }
            })
            .catch(err => console.error("Message send failure:", err));
        });

        // Initialize on load
        window.addEventListener('load', function() {
            recalculateMatches();
        });
    
