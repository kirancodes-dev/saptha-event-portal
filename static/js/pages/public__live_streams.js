/* Moved unchanged from an inline <script> in templates/public/live_streams.html so the CSP
   needs no inline script (UPG-25). */
        var botNames = ["Shubham Sharma", "Vikram Patel", "Sneha Roy", "Deepika G.", "Abhishek P.", "Anjali Nair", "Arjun Gowda", "Nisha Das", "Siddharth Rao"];
        var botMessages = [
            "This livestream quality is brilliant! SNPSU rocks!",
            "OMG! Team Zenith just got a perfect 10 score!",
            "Where can I find the wayfinder map? I'm lost near Seminar Block.",
            "Certificates issued with cryptographic hashes are super cool.",
            "Let's go team Cosmic! Break a leg!",
            "Who won the robo combat round 1?",
            "Is the food court still open? I am starving.",
            "The choreography was absolutely stellar!",
            "Hackathon pitches start in 10 minutes at CS lab block."
        ];

        var viewCounterVal = 1420;
        var likesCounterVal = 854;

        // Fluctuating viewers and random chat simulation
        setInterval(function() {
            // Viewers
            viewCounterVal += Math.floor(Math.random() * 21) - 10;
            document.getElementById('view-counter').innerText = viewCounterVal.toLocaleString();

            // Bot likes increments
            if (Math.random() > 0.4) {
                likesCounterVal += Math.floor(Math.random() * 4) + 1;
                document.getElementById('likes-counter').innerText = likesCounterVal;
                // occasional bubble
                if (Math.random() > 0.7) {
                    spawnLikeBubble();
                }
            }

            // Append bot chats occasionally
            if (Math.random() > 0.7) {
                var randomName = botNames[Math.floor(Math.random() * botNames.length)];
                var randomMsg = botMessages[Math.floor(Math.random() * botMessages.length)];
                appendChatMessage(randomName, randomMsg);
            }
        }, 3000);

        function appendChatMessage(user, msg, isSelf = false) {
            var container = document.getElementById('chat-messages-container');
            var div = document.createElement('div');
            div.className = 'chat-msg';
            
            var userClass = isSelf ? 'text-primary fw-bold' : '';
            div.innerHTML = `<div class="chat-msg-user ${escapeHtml(userClass)}">${escapeHtml(user)}</div>
                             <div class="chat-msg-text">${escapeHtml(msg)}</div>`;
            
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;

            // Cap chats to 40 max to save memory
            while (container.childNodes.length > 40) {
                container.removeChild(container.firstChild);
            }
        }

        // Live Chat Submit
        document.getElementById('chat-form').addEventListener('submit', function(e) {
            e.preventDefault();
            var input = document.getElementById('chat-input');
            var val = input.value.trim();
            if (val) {
                appendChatMessage("You", val, true);
                input.value = "";
            }
        });

        // Like Button click logic
        document.getElementById('like-btn').addEventListener('click', function() {
            likesCounterVal += 1;
            document.getElementById('likes-counter').innerText = likesCounterVal;
            spawnLikeBubble();
        });

        function spawnLikeBubble() {
            var container = document.getElementById('bubble-box');
            var icon = document.createElement('i');
            icon.className = 'fas fa-heart like-bubble';
            
            // Randomize styling properties slightly
            var drift = (Math.random() * 60 - 30) + 'px';
            icon.style.setProperty('--drift', drift);
            
            // random color variation
            var colors = ["#ec4899", "#f43f5e", "#d946ef", "#a855f7"];
            icon.style.color = colors[Math.floor(Math.random() * colors.length)];
            
            container.appendChild(icon);
            
            // Remove after animation completes
            setTimeout(function() {
                icon.remove();
            }, 2500);
        }

        // Switch Channels
        function switchChannel(type, title, videoUrl) {
            // update stream title
            document.getElementById('stream-title').innerText = title;
            
            // update video source and load
            var video = document.getElementById('main-video');
            video.src = videoUrl;
            video.load();
            video.play();

            // adjust view numbers simulation
            if (type === 'cultural') {
                viewCounterVal = 1420;
            } else if (type === 'hackathon') {
                viewCounterVal = 520;
            } else {
                viewCounterVal = 0;
            }
            document.getElementById('view-counter').innerText = viewCounterVal;

            // Highlight card
            var cards = document.querySelectorAll('.stream-card');
            cards.forEach(c => c.classList.remove('active'));
            event.currentTarget.classList.add('active');
        }
    
