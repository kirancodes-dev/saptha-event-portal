/* Moved unchanged from an inline <script> in templates/onboarding/wizard.html so the CSP
   needs no inline script (UPG-25). */
    function nextStep(step) {
      // Hide all steps
      document.querySelectorAll('.wizard-step').forEach(function(el) {
        el.classList.remove('active');
      });
      // Show requested step
      document.getElementById('step-' + step).classList.add('active');

      // Update dot styles
      document.querySelectorAll('.step-dot').forEach(function(dot, idx) {
        var num = idx + 1;
        dot.className = 'step-dot';
        if (num < step) {
          dot.classList.add('completed');
        } else if (num === step) {
          dot.classList.add('active');
        }
      });

      // Update progress bar width
      var pct = ((step - 1) / 2) * 100;
      document.getElementById('progressBar').style.width = pct + '%';
    }

    function addDept() {
      var input = document.getElementById('deptInput');
      var val = input.value.trim();
      if (!val) return;

      var wrap = document.getElementById('deptTags');
      var tag = document.createElement('span');
      tag.className = 'badge bg-secondary p-2 d-flex align-items-center gap-2';
      tag.innerHTML = escapeHtml(val) + ' <i class="fas fa-times cursor-pointer" data-h-click="se:remove-parent"></i>';
      wrap.appendChild(tag);
      
      input.value = '';
    }

    function submitWizard() {
      var depts = [];
      document.querySelectorAll('#deptTags span').forEach(function(span) {
        depts.push(span.textContent.trim().split(' ')[0]);
      });

      var payload = {
        primary_color: document.getElementById('primaryColor').value,
        logo_url: document.getElementById('logoUrl').value,
        departments: depts
      };

      fetch('/onboarding/wizard', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).content || ''
        },
        body: JSON.stringify(payload)
      })
      .then(r => r.json())
      .then(d => {
        if(d.redirect) {
          window.location.href = d.redirect;
        } else if(d.error) {
          alert('Error: ' + d.error);
        }
      })
      .catch(err => {
        alert('Network Error: ' + err.message);
      });
    }
  
