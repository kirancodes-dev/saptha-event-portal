/* Moved unchanged from an inline <script> in templates/public/verify_success.html so the CSP
   needs no inline script (UPG-25). */
  // Shoot confetti on load
  window.addEventListener('DOMContentLoaded', () => {
    const duration = 4 * 1000;
    const animationEnd = Date.now() + duration;
    const defaults = { startVelocity: 28, spread: 360, ticks: 60, zIndex: 1000 };

    function randomInRange(min, max) {
      return Math.random() * (max - min) + min;
    }

    const interval = setInterval(() => {
      const timeLeft = animationEnd - Date.now();

      if (timeLeft <= 0) {
        return clearInterval(interval);
      }

      const particleCount = 45 * (timeLeft / duration);
      confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.1, 0.3), y: Math.random() - 0.2 } }));
      confetti(Object.assign({}, defaults, { particleCount, origin: { x: randomInRange(0.7, 0.9), y: Math.random() - 0.2 } }));
    }, 250);
  });

  // Copy URL Script
  function copyVerificationLink() {
    const copyText = document.getElementById("verify-url-text").textContent;
    navigator.clipboard.writeText(copyText).then(() => {
      const toast = document.getElementById("copy-toast");
      const icon = document.getElementById("copy-icon");
      
      icon.className = "fas fa-check text-success";
      toast.classList.add("show");
      
      setTimeout(() => {
        toast.classList.remove("show");
        icon.className = "far fa-copy";
      }, 2500);
    });
  }
