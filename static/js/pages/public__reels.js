/* Moved unchanged from an inline <script> in templates/public/reels.html so the CSP
   needs no inline script (UPG-25). */
        var curIdx = 0;
        var totalReels = 3;
        var slider = document.getElementById('reel-slider');
        var videos = document.querySelectorAll('.reel-video');

        // Play the first video on start
        window.addEventListener('load', function() {
            setTimeout(function() {
                playVideo(0);
            }, 600);
        });

        function slideTo(idx) {
            if (idx < 0 || idx >= totalReels) return;
            
            // Pause current video
            videos[curIdx].pause();
            
            curIdx = idx;
            slider.style.transform = `translateY(-${curIdx * 100}%)`;
            
            // Play new video
            setTimeout(function() {
                playVideo(curIdx);
            }, 300);
        }

        function slideNext() {
            if (curIdx < totalReels - 1) {
                slideTo(curIdx + 1);
            } else {
                // Loop back to start
                slideTo(0);
            }
        }

        function slidePrev() {
            if (curIdx > 0) {
                slideTo(curIdx - 1);
            }
        }

        function playVideo(idx) {
            var v = videos[idx];
            v.currentTime = 0;
            v.play().catch(function(err) {
                console.log("Auto play prevented, waiting for user click.", err);
            });
        }

        function togglePlay(video) {
            var splash = document.getElementById('play-splash');
            var icon = splash.querySelector('i');
            
            if (video.paused) {
                video.play();
                icon.className = "fas fa-play";
            } else {
                video.pause();
                icon.className = "fas fa-pause";
            }
            
            splash.classList.remove('trigger');
            void splash.offsetWidth; // trigger reflow
            splash.classList.add('trigger');
        }

        function toggleLike(btn) {
            btn.classList.toggle('active');
            var label = btn.nextElementSibling;
            var currentVal = parseFloat(label.innerText.replace('K', ''));
            
            if (btn.classList.contains('active')) {
                if (label.innerText.includes('K')) {
                    label.innerText = (currentVal + 0.1).toFixed(1) + 'K';
                } else {
                    label.innerText = parseInt(label.innerText) + 1;
                }
            } else {
                if (label.innerText.includes('K')) {
                    label.innerText = (currentVal - 0.1).toFixed(1) + 'K';
                } else {
                    label.innerText = parseInt(label.innerText) - 1;
                }
            }
        }

        // Gesture slider support (touch events)
        var startY = 0;
        document.querySelector('.reel-viewport').addEventListener('touchstart', function(e) {
            startY = e.touches[0].clientY;
        }, { passive: true });

        document.querySelector('.reel-viewport').addEventListener('touchend', function(e) {
            var endY = e.changedTouches[0].clientY;
            var deltaY = startY - endY;
            if (Math.abs(deltaY) > 60) {
                if (deltaY > 0) {
                    slideNext();
                } else {
                    slidePrev();
                }
            }
        }, { passive: true });

        // Keyboard navigation (up/down arrow keys)
        window.addEventListener('keydown', function(e) {
            if (e.key === "ArrowDown") {
                slideNext();
            } else if (e.key === "ArrowUp") {
                slidePrev();
            }
        });
    
