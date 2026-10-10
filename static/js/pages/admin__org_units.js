/* Moved unchanged from an inline <script> in templates/admin/org_units.html so the CSP
   needs no inline script (UPG-25). */
        function handleScopeChange() {
            const st = document.getElementById('scope_type_select').value;
            const si = document.getElementById('scope_id_input');
            const sh = document.getElementById('scope_help_text');
            if (st === 'university') {
                si.value = 'default';
                sh.innerText = "Scope applies campus-wide across all units and events.";
            } else if (st === 'unit') {
                si.value = '';
                si.placeholder = "e.g. cse, ece, cultural-club";
                sh.innerText = "Select or type the target OrgUnit slug.";
            } else if (st === 'event') {
                si.value = '';
                si.placeholder = "e.g. evt_test_001";
                sh.innerText = "Select or type the target Event ID.";
            }
        }
    
