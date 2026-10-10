/* Moved unchanged from an inline <script> in templates/spoc/create_event.html so the CSP
   needs no inline script (UPG-25). */
        let currentStep = 1;
        const totalSteps = 6;
        const visitedSteps = new Set([1]);
        let cr_step2_init = false;
        let fb_step4_init = false;

        // ── Template selection logic ──────────────────────────
        function selectTemplate(templateId) {
            document.querySelectorAll('.template-card').forEach(el => el.classList.remove('selected'));
            const card = document.getElementById('tpl-card-' + templateId);
            if (card) card.classList.add('selected');

            const hiddenInput = document.getElementById('selectedTemplateId');
            if (hiddenInput) hiddenInput.value = templateId;
            const eventTypeInput = document.getElementById('selectedEventType');
            if (eventTypeInput) eventTypeInput.value = templateId;

            const labelEl = document.getElementById('selectedTemplateLabel');
            if (labelEl) {
                const names = {
                    'hackathon': 'Hackathon',
                    'seminar': 'Seminar',
                    'workshop': 'Workshop',
                    'custom': 'Custom'
                };
                labelEl.textContent = names[templateId] || 'Hackathon';
            }

            const isNonCompetition = (templateId === 'seminar' || templateId === 'workshop');

            // Hide or show judging criteria
            const criteriaCard = document.getElementById('judgingCriteriaCard');
            if (criteriaCard) {
                criteriaCard.style.display = isNonCompetition ? 'none' : 'block';
            }

            // Hide or show participation logic & team fields
            const partContainer = document.getElementById('partStyleContainer');
            const teamFields = document.querySelectorAll('.team-field');
            if (partContainer) {
                partContainer.style.display = isNonCompetition ? 'none' : 'block';
            }
            teamFields.forEach(el => {
                el.style.display = isNonCompetition ? 'none' : (document.getElementById('partType')?.value !== 'Individual' ? 'block' : 'none');
            });

            // Set Individual defaults for non-competition
            if (isNonCompetition) {
                const partSelect = document.getElementById('partType');
                if (partSelect) partSelect.value = 'Individual';
                const teamMin = document.querySelector('input[name="team_min"]');
                const teamMax = document.querySelector('input[name="team_max"]');
                if (teamMin) teamMin.value = 1;
                if (teamMax) teamMax.value = 1;

                // Clear criteria for non-competitions
                const critRows = document.getElementById('criteriaRows');
                if (critRows) critRows.innerHTML = '';
                const critJson = document.getElementById('judgingCriteriaJson');
                if (critJson) critJson.value = '[]';
            }
        }

        // ── Toast ─────────────────────────────────────────────
        function showToast(msg, type) {
            const t = document.createElement('div');
            t.textContent = msg;
            t.style.cssText = `position:fixed;bottom:90px;left:50%;transform:translateX(-50%);
                background:${type==='error'?'#dc2626':'#10b981'};color:#fff;padding:10px 22px;
                border-radius:8px;font-weight:600;font-size:14px;z-index:9999;
                box-shadow:0 4px 16px rgba(0,0,0,.4);opacity:1;transition:.3s;`;
            document.body.appendChild(t);
            setTimeout(() => t.remove(), 2800);
        }

        // ── Navigate to a specific step directly ─────────────
        function goToStep(n) {
            if (n === currentStep) return;
            currentStep = n;
            _updateUI();
        }

        // ── Next / Back buttons ───────────────────────────────
        function changeStep(direction) {
            if (direction === -1 && currentStep === 1) {
                window.location.href = '/spoc/dashboard';
                return;
            }
            const next = currentStep + direction;
            if (next < 1 || next > totalSteps) return;
            currentStep = next;
            _updateUI();
        }

        // ── Central UI updater ────────────────────────────────
        function _updateUI() {
            visitedSteps.add(currentStep);

            // Show correct step content
            document.querySelectorAll('.wizard-step-content').forEach(el => el.classList.remove('active'));
            document.getElementById('step-' + currentStep).classList.add('active');

            // Step indicator states
            for (let i = 1; i <= totalSteps; i++) {
                const el = document.getElementById('ind-' + i);
                el.classList.remove('active', 'visited');
                if (i === currentStep) el.classList.add('active');
                else if (visitedSteps.has(i)) el.classList.add('visited');
            }

            // Footer buttons
            const btnNext    = document.getElementById('btnNext');
            const btnPrev    = document.getElementById('btnPrev');
            const btnPublish = document.getElementById('btnPublish');
            btnPrev.innerText = currentStep === 1 ? 'Cancel' : 'Back';
            if (currentStep === totalSteps) {
                btnNext.style.display    = 'none';
                btnPublish.style.display = 'block';
            } else {
                btnNext.style.display    = 'block';
                btnPublish.style.display = 'none';
            }

            // Auto-init judging criteria on first visit to step 3 (Logistics)
            if (currentStep === 3 && !cr_step2_init) {
                cr_step2_init = true;
                const tpl = document.getElementById('selectedTemplateId')?.value;
                if (tpl !== 'seminar' && tpl !== 'workshop') {
                    if (document.querySelectorAll('#criteriaRows .criteria-row').length === 0) {
                        loadDefaultCriteria();
                    }
                }
            }
            // Auto-init form builder with default template on first visit to step 5 (Form)
            if (currentStep === 5 && !fb_step4_init) {
                fb_step4_init = true;
                if (fb_fields.length === 0) fb_loadTemplate();
            }

            window.scrollTo(0, 0);
        }

        // 3. Dynamic Rows: SPONSORS
        function addSponsorRow() {
            const tbody = document.getElementById('sponsorBody');
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><input type="text" class="form-control sp-name" placeholder="Company Name"></td>
                <td><select class="form-select sp-tier"><option>Gold</option><option>Silver</option><option>Bronze</option></select></td>
                <td><input type="url" class="form-control sp-logo" placeholder="Logo URL"></td>
                <td><button type="button" class="btn-remove" data-h-click="se:remove-closest" data-closest="tr"><i class="fas fa-trash"></i></button></td>
            `;
            tbody.appendChild(row);
        }

        // ── Data Aggregation & Submit ─────────────────────────
        function submitForm() {
            // Collect sponsors
            const sponsors = [];
            document.querySelectorAll('#sponsorBody tr').forEach(tr => {
                sponsors.push({
                    name: tr.querySelector('.sp-name').value,
                    tier: tr.querySelector('.sp-tier').value,
                    logo: tr.querySelector('.sp-logo').value
                });
            });
            document.getElementById('sponsorsJson').value = JSON.stringify(sponsors);
            // Sync form builder fields
            document.getElementById('autoFormJson').value = JSON.stringify(fb_fields);
            document.getElementById('mainForm').submit();
        }

        // ── Judging Criteria ──────────────────────────────────
        let cr_step2_init = false;

        function addCriteria(name, desc, maxScore) {
            const container = document.getElementById('criteriaRows');
            const uid = 'cr_' + Date.now() + '_' + Math.random().toString(36).slice(2,5);
            const row = document.createElement('div');
            row.className = 'criteria-row';
            row.id = uid;
            row.innerHTML = `
                <i class="fas fa-grip-vertical" style="color:#cbd5e1;flex-shrink:0;"></i>
                <input type="text" class="form-control cr-input criteria-name"
                       placeholder="Criterion name (e.g. Innovation)" value="${escapeHtml(name || '')}"
                       data-h-input="se:call" data-call="syncCriteria" style="flex:2;">
                <input type="text" class="form-control cr-input criteria-desc"
                       placeholder="What judges look for (optional)" value="${escapeHtml(desc || '')}"
                       data-h-input="se:call" data-call="syncCriteria" style="flex:3;">
                <div class="input-group cr-pts-group" style="max-width:120px;flex-shrink:0;">
                    <input type="number" class="form-control cr-input criteria-max"
                           value="${escapeHtml(maxScore || 10)}" min="1" max="100" data-h-input="se:call" data-call="syncCriteria">
                    <span class="input-group-text" style="background:#f8fafc;border:1.5px solid #e2e8f0;color:#64748b;font-size:11px;font-weight:700;">pts</span>
                </div>
                <button type="button" class="fb-type-btn danger" style="padding:7px 12px;flex-shrink:0;"
                        data-h-click="spoc/create_event:remove-criterion">
                    <i class="fas fa-trash"></i>
                </button>`;
            container.appendChild(row);
            syncCriteria();
        }

        function syncCriteria() {
            const criteria = [];
            document.querySelectorAll('#criteriaRows .criteria-row').forEach(function(row) {
                const name = row.querySelector('.criteria-name').value.trim();
                const desc = row.querySelector('.criteria-desc').value.trim();
                const max  = parseInt(row.querySelector('.criteria-max').value) || 10;
                if (name) criteria.push({ name: name, description: desc, max_score: max });
            });
            document.getElementById('judgingCriteriaJson').value = JSON.stringify(criteria);
        }

        function loadDefaultCriteria() {
            document.getElementById('criteriaRows').innerHTML = '';
            addCriteria('Innovation',      'Originality and creativity of the idea',          10);
            addCriteria('Technical Depth', 'Quality and complexity of implementation',         10);
            addCriteria('Presentation',    'Clarity and quality of demo or pitch',              5);
            addCriteria('Impact',          'Real-world usefulness and potential scalability',   5);
        }

        function clearCriteria() {
            if (document.querySelectorAll('#criteriaRows .criteria-row').length === 0) return;
            if (!confirm('Remove all judging criteria?')) return;
            document.getElementById('criteriaRows').innerHTML = '';
            syncCriteria();
        }

        // 5. Helpers
        function previewBanner(url) {
            const img = document.getElementById('bannerPreview');
            if(url.length > 5) { img.src = url; img.style.display = 'block'; }
            else img.style.display = 'none';
        }

        function toggleTeams() {
            const val = document.getElementById('partType').value;
            const fields = document.querySelectorAll('.team-field');
            fields.forEach(f => f.style.display = (val === 'Individual') ? 'none' : 'block');
        }

        toggleTeams();

        // ── MANUAL FORM BUILDER ──────────────────────────────
        let fb_fields = [];
        let fb_selectedId = null;

        const FB_TYPE_LABELS = {
            text:'Short Text', textarea:'Long Text', email:'Email', tel:'Phone',
            number:'Number', date:'Date', url:'URL', select:'Dropdown',
            radio:'Multiple Choice', checkbox:'Checkbox', heading:'Heading', divider:'Divider'
        };
        const FB_DEFAULTS = {
            text:     { label:'Short Answer',    placeholder:'Type your answer' },
            textarea: { label:'Long Answer',     placeholder:'Type your answer here...' },
            email:    { label:'Email Address',   placeholder:'you@example.com' },
            tel:      { label:'Phone Number',    placeholder:'e.g. 9876543210' },
            number:   { label:'Number',          placeholder:'Enter a number' },
            date:     { label:'Date',            placeholder:'' },
            url:      { label:'Website / Link',  placeholder:'https://' },
            select:   { label:'Dropdown',        placeholder:'Select option', options:['Option 1','Option 2','Option 3'] },
            radio:    { label:'Multiple Choice', placeholder:'', options:['Option 1','Option 2','Option 3'] },
            checkbox: { label:'I agree to the terms', placeholder:'' },
            heading:  { label:'Section Heading', placeholder:'' },
            divider:  { label:'', placeholder:'' },
        };

        function fb_uid() { return 'f_' + Math.random().toString(36).slice(2, 8); }

        function fb_addField(type) {
            const def = FB_DEFAULTS[type] || {};
            fb_fields.push({
                id: fb_uid(), type, required: false,
                label: def.label || type,
                placeholder: def.placeholder || '',
                options: (def.options || []).slice(),
                help_text: ''
            });
            fb_renderCanvas();
            fb_selectField(fb_fields[fb_fields.length - 1].id);
            fb_sync();
        }

        function fb_renderCanvas() {
            const canvas = document.getElementById('fb_canvas');
            canvas.querySelectorAll('.fb-field-row').forEach(el => el.remove());
            document.getElementById('fb_empty').style.display = fb_fields.length ? 'none' : 'block';
            fb_fields.forEach((f, idx) => {
                const row = document.createElement('div');
                row.className = 'fb-field-row' + (f.id === fb_selectedId ? ' fb-selected' : '');
                row.dataset.id = f.id;
                row.draggable = true;
                row.addEventListener('dragstart', e => { e.dataTransfer.setData('text/plain', String(idx)); setTimeout(() => row.style.opacity = '0.5', 0); });
                row.addEventListener('dragend', () => { row.style.opacity = '1'; });
                row.addEventListener('dragover', e => { e.preventDefault(); row.style.borderColor = 'var(--orange)'; });
                row.addEventListener('dragleave', () => { row.style.borderColor = ''; });
                row.addEventListener('drop', e => {
                    e.preventDefault(); row.style.borderColor = '';
                    const from = parseInt(e.dataTransfer.getData('text/plain'));
                    if (from !== idx) { const m = fb_fields.splice(from, 1)[0]; fb_fields.splice(idx, 0, m); fb_renderCanvas(); fb_sync(); }
                });
                row.innerHTML = `
                    <span class="fb-drag-handle"><i class="fas fa-grip-vertical"></i></span>
                    <div class="fb-field-info" style="cursor:pointer;" data-h-click="se:call" data-call="fb_selectField" data-args="${escapeHtml(JSON.stringify([f.id]))}">
                        <span class="fb-field-lbl">${escapeHtml(f.label || f.type)}</span>
                        <span class="fb-field-typ">${escapeHtml(FB_TYPE_LABELS[f.type] || f.type)}</span>
                    </div>
                    ${f.required ? '<span class="fb-req-badge">Required</span>' : ''}
                    <div class="fb-actions">
                        <button type="button" title="Edit" data-h-click="se:call" data-call="fb_selectField" data-args="${escapeHtml(JSON.stringify([f.id]))}"><i class="fas fa-edit"></i></button>
                        <button type="button" title="Delete" class="fb-del" data-h-click="se:call" data-call="fb_deleteField" data-args="${escapeHtml(JSON.stringify([f.id]))}"><i class="fas fa-trash"></i></button>
                    </div>`;
                canvas.appendChild(row);
            });
            const countEl = document.getElementById('fb_field_count');
            if (countEl) countEl.textContent = fb_fields.length + ' field' + (fb_fields.length !== 1 ? 's' : '');
        }

        function fb_selectField(id) {
            fb_selectedId = id;
            fb_renderCanvas();
            fb_renderProps();
        }

        function fb_closeProps() {
            fb_selectedId = null;
            document.getElementById('fb_props_wrap').style.display = 'none';
            fb_renderCanvas();
        }

        function fb_renderProps() {
            const f = fb_fields.find(x => x.id === fb_selectedId);
            if (!f) { document.getElementById('fb_props_wrap').style.display = 'none'; return; }
            document.getElementById('fb_props_wrap').style.display = 'block';
            const needsOptions = ['select','radio','checkbox_group'].includes(f.type);
            const isLayout = ['heading','divider'].includes(f.type);
            let html = '<div class="row g-3">';
            if (f.type !== 'divider') {
                html += `<div class="col-md-6"><label class="form-label">Label</label><input type="text" class="form-control" value="${escapeHtml(f.label)}" data-h-input="spoc/create_event:set-prop" data-prop="label" placeholder="Field label"></div>`;
            }
            if (!isLayout && f.type !== 'checkbox') {
                html += `<div class="col-md-6"><label class="form-label">Placeholder</label><input type="text" class="form-control" value="${escapeHtml(f.placeholder)}" data-h-input="spoc/create_event:set-prop" data-prop="placeholder" placeholder="Hint shown inside field"></div>`;
            }
            if (!isLayout) {
                html += `<div class="col-md-6"><label class="form-label">Help Text</label><input type="text" class="form-control" value="${escapeHtml(f.help_text || '')}" data-h-input="spoc/create_event:set-prop" data-prop="help_text" placeholder="Optional description"></div>`;
                html += `<div class="col-md-6 d-flex align-items-end pb-1">
                           <div class="form-check form-switch mb-0">
                             <input type="checkbox" id="fb_req_chk" class="form-check-input" style="width:40px;height:22px;cursor:pointer;" ${f.required?'checked':''} data-h-change="spoc/create_event:set-prop-checked" data-prop="required">
                             <label for="fb_req_chk" class="fb-req-label ms-2">Required field</label>
                           </div>
                         </div>`;
            }
            html += '</div>';
            if (needsOptions) {
                html += `<div class="mt-3"><label class="form-label d-block" style="font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.4px;color:#475569;">Options</label><div id="fb_opt_list">`;
                f.options.forEach((opt, i) => {
                    html += `<div class="d-flex gap-2 mb-2"><input type="text" class="form-control form-control-sm" style="background:#fff!important;color:#1e293b!important;border-color:#e2e8f0!important;" value="${escapeHtml(opt)}" data-h-input="spoc/create_event:set-opt" data-i="${escapeHtml(String(i))}"><button type="button" class="fb-type-btn danger" style="padding:4px 10px;" data-h-click="se:call" data-call="fb_removeOpt" data-args="${escapeHtml(JSON.stringify([i]))}"><i class="fas fa-times"></i></button></div>`;
                });
                html += `</div><button type="button" class="fb-type-btn info mt-1" data-h-click="se:call" data-call="fb_addOpt"><i class="fas fa-plus me-1"></i>Add Option</button></div>`;
            }
            document.getElementById('fb_props_body').innerHTML = html;
        }

        function fb_setProp(key, val) {
            const f = fb_fields.find(x => x.id === fb_selectedId); if (!f) return;
            f[key] = val; fb_renderCanvas(); fb_sync();
        }
        function fb_addOpt() {
            const f = fb_fields.find(x => x.id === fb_selectedId); if (!f) return;
            f.options.push('Option ' + (f.options.length + 1)); fb_renderProps(); fb_sync();
        }
        function fb_removeOpt(idx) {
            const f = fb_fields.find(x => x.id === fb_selectedId); if (!f) return;
            f.options.splice(idx, 1); fb_renderProps(); fb_sync();
        }
        function fb_setOpt(idx, val) {
            const f = fb_fields.find(x => x.id === fb_selectedId); if (!f) return;
            f.options[idx] = val; fb_sync();
        }
        function fb_deleteField(id) {
            fb_fields = fb_fields.filter(f => f.id !== id);
            if (fb_selectedId === id) { fb_selectedId = null; document.getElementById('fb_props_wrap').style.display = 'none'; }
            fb_renderCanvas(); fb_sync();
        }
        function fb_clearAll() {
            if (fb_fields.length && !confirm('Remove all fields?')) return;
            fb_fields = []; fb_selectedId = null;
            fb_renderCanvas();
            document.getElementById('fb_props_wrap').style.display = 'none';
            fb_sync();
        }
        function fb_loadTemplate() {
            fb_fields = [
                { id:'full_name', type:'text',  label:'Full Name',    placeholder:'Enter your full name', required:true,  options:[], help_text:'' },
                { id:'email',     type:'email', label:'Email Address', placeholder:'you@example.com',    required:true,  options:[], help_text:'' },
                { id:'phone',     type:'tel',   label:'Phone Number',  placeholder:'10-digit mobile',    required:true,  options:[], help_text:'' },
                { id:'usn',       type:'text',  label:'USN / Roll No', placeholder:'e.g. 1SN21CS001',    required:false, options:[], help_text:'' },
            ];
            fb_renderCanvas(); fb_sync();
            showToast('Template loaded!', 'success');
        }
        function fb_sync() {
            document.getElementById('autoFormJson').value = JSON.stringify(fb_fields);
        }
        // ── GEMINI AI EVENT WRITER JS ──
        function toggleAIGenerator() {
            var card = document.getElementById('ai-generator-card');
            if (card) {
                card.classList.toggle('d-none');
            }
        }

        function generateEventOutline() {
            var titleInput = document.getElementById('event-title-input');
            var promptInput = document.getElementById('ai-prompt-input');
            var submitBtn = document.getElementById('ai-gen-submit-btn');
            
            var title = titleInput ? titleInput.value.trim() : '';
            var prompt = promptInput ? promptInput.value.trim() : '';
            
            if (!title) {
                showToast('Please enter an Event Title first!', 'error');
                return;
            }
            
            var oldHtml = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
            
            var csrfToken = document.querySelector('input[name="csrf_token"]').value;
            
            fetch('/spoc/marketing/event_writer', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ title: title, prompt: prompt })
            })
            .then(function(r) { return r.json(); })
            .then(function(data) {
                if (data.description && data.rules) {
                    var descArea = document.querySelector('textarea[name="description"]');
                    var rulesArea = document.querySelector('textarea[name="rules"]');
                    if (descArea) descArea.value = data.description;
                    if (rulesArea) rulesArea.value = data.rules;
                    
                    showToast('Event details generated successfully!', 'success');
                    toggleAIGenerator();
                } else {
                    showToast(data.error || 'Failed to generate details', 'error');
                }
            })
            .catch(function() {
                showToast('Network error generating details', 'error');
            })
            .finally(function() {
                submitBtn.disabled = false;
                submitBtn.innerHTML = oldHtml;
            });
        }
    
