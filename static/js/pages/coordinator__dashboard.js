/* Moved unchanged from an inline <script> in templates/coordinator/dashboard.html so the CSP
   needs no inline script (UPG-25). */
// ── WIZARD NAV ───────────────────────────────────────────
function nextStep(current) {
    document.getElementById('step' + current).classList.remove('active');
    document.getElementById('step' + (current + 1)).classList.add('active');
    document.getElementById('dot' + current).classList.replace('active', 'completed');
    document.getElementById('dot' + (current + 1)).classList.add('active');
}
function prevStep(current) {
    document.getElementById('step' + current).classList.remove('active');
    document.getElementById('step' + (current - 1)).classList.add('active');
    document.getElementById('dot' + current).classList.remove('active');
    document.getElementById('dot' + (current - 1)).classList.replace('completed', 'active');
}

// ── FORM TYPE SELECTION (Step 4) ─────────────────────────
function selectFormType(type) {
    document.getElementById('form_type_input').value = type;
    document.getElementById('card-simple').classList.toggle('selected', type === 'simple');
    document.getElementById('card-custom').classList.toggle('selected', type === 'custom');
    document.getElementById('type-info-simple').style.display = type === 'simple' ? '' : 'none';
    document.getElementById('type-info-custom').style.display = type === 'custom' ? '' : 'none';
}

// ── MEDIA GALLERY ────────────────────────────────────────
function addMediaField(containerId) {
    const container = document.getElementById(containerId);
    const div = document.createElement('div');
    div.className = 'input-group mb-2';
    div.innerHTML = `
        <input type="url" name="media_urls[]" class="form-control"
               placeholder="Image or Video URL (.mp4)" required>
        <button class="btn btn-outline-danger px-4" type="button"
                data-h-click="se:remove-parent">
            <i class="fas fa-trash"></i>
        </button>`;
    container.appendChild(div);
}

// ── ROOM ALLOCATION ──────────────────────────────────────
function addRoomField(containerId) {
    const container = document.getElementById(containerId);
    const div = document.createElement('div');
    div.className = 'row g-2 mb-3 align-items-end room-row';
    div.innerHTML = `
        <div class="col-md-7">
            <input type="text" name="room_name[]" class="form-control border-dark"
                   placeholder="e.g. Room 102" required>
        </div>
        <div class="col-md-4">
            <input type="number" name="capacity[]" class="form-control border-dark"
                   placeholder="e.g. 25" required>
        </div>
        <div class="col-md-1 pb-1">
            <button type="button" class="btn btn-outline-danger w-100"
                    data-h-click="se:remove-grandparent">
                <i class="fas fa-trash"></i>
            </button>
        </div>`;
    container.appendChild(div);
}
