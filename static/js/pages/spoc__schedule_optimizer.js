/* Moved unchanged from an inline <script> in templates/spoc/schedule_optimizer.html so the CSP
   needs no inline script (UPG-25). */
        function optimizeAgenda() {
            var myModal = new bootstrap.Modal(document.getElementById('optModal'));
            myModal.show();
            
            // visually update stats to perfect clash-free state
            document.getElementById('clash-counter').innerText = "0 Students";
            document.getElementById('resolved-counter').innerText = "18 Students";
            document.getElementById('ratio-counter').innerText = "100%";
        }
    
