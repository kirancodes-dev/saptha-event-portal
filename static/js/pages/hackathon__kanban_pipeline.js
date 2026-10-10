/* Moved unchanged from an inline <script> in templates/hackathon/kanban_pipeline.html so the CSP
   needs no inline script (UPG-25). */
function updateStage(subId, stage) {
    fetch(`/api/hackathon/stage/${subId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ stage: stage })
    })
    .then(r => r.json())
    .then(d => {
        if (d.status === 'ok') {
            location.reload();
        } else {
            alert(d.message || 'Failed to update stage');
        }
    });
}
