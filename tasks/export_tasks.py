"""
tasks/export_tasks.py — Async data exports
==========================================
Excel/CSV generation is I/O + CPU heavy. Running it in the web worker
can exhaust gunicorn's timeout on large events. These tasks run on the
'exports' queue with an extended time limit.

Queued on: 'exports'
"""

import logging
import io
import datetime
from celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    bind=True,
    queue='exports',
    max_retries=2,
    default_retry_delay=60,
    name='tasks.export_tasks.export_registrations_excel',
    time_limit=600,
    soft_time_limit=540,
)
def export_registrations_excel(self, event_id: str, requested_by: str = ''):
    """
    Export all registrations for an event to an Excel file and upload to GCS.
    Returns the GCS download URL stored in Firestore under events/{event_id}.export_url.
    """
    try:
        import pandas as pd
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter

        event_doc = db.collection('events').document(event_id).get()
        event_title = (event_doc.to_dict() or {}).get('title', event_id) if event_doc.exists else event_id

        regs = list(db.collection('registrations')
                    .where(filter=FieldFilter('event_id', '==', event_id))
                    .stream())

        rows = []
        for doc in regs:
            d = doc.to_dict()
            rows.append({
                'Registration ID': doc.id,
                'Name':            d.get('lead_name', ''),
                'Email':           d.get('lead_email', ''),
                'Phone':           d.get('lead_phone', ''),
                'USN':             d.get('usn', ''),
                'Team Name':       d.get('team_name', ''),
                'Status':          d.get('status', ''),
                'Attendance':      d.get('attendance', ''),
                'Payment':         d.get('payment_status', ''),
                'Amount':          d.get('amount_paid', 0),
                'Registered At':   d.get('registered_at', ''),
            })

        df = pd.DataFrame(rows)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Registrations', index=False)
        buf.seek(0)

        url = _upload_export(buf.getvalue(), f"exports/{event_id}_registrations.xlsx")

        db.collection('events').document(event_id).update({
            'export_url':         url,
            'export_generated_at': datetime.datetime.utcnow().isoformat(),
            'export_requested_by': requested_by,
        })
        logger.info("registrations exported for event=%s rows=%d by=%s", event_id, len(rows), requested_by)
        return {'url': url, 'rows': len(rows)}

    except Exception as exc:
        logger.error("export_registrations_excel failed event=%s: %s", event_id, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='exports',
    max_retries=2,
    default_retry_delay=60,
    name='tasks.export_tasks.export_scoresheet',
    time_limit=600,
    soft_time_limit=540,
)
def export_scoresheet(self, event_id: str, requested_by: str = ''):
    """
    Export judge scores for an event to Excel.
    Merges registrations with scores from the scores sub-collection.
    """
    try:
        import pandas as pd
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter

        regs = list(db.collection('registrations')
                    .where(filter=FieldFilter('event_id', '==', event_id))
                    .stream())

        rows = []
        for doc in regs:
            d = doc.to_dict()
            scores_docs = db.collection('registrations').document(doc.id) \
                           .collection('scores').stream()
            scores = {s.id: s.to_dict() for s in scores_docs}
            total  = sum((v or {}).get('total', 0) for v in scores.values())
            rows.append({
                'Registration ID': doc.id,
                'Team / Name':     d.get('team_name') or d.get('lead_name', ''),
                'Email':           d.get('lead_email', ''),
                'Scores JSON':     str(scores),
                'Total Score':     total,
                'Attendance':      d.get('attendance', ''),
            })

        df = pd.DataFrame(rows).sort_values('Total Score', ascending=False)
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Scores', index=False)
        buf.seek(0)

        url = _upload_export(buf.getvalue(), f"exports/{event_id}_scoresheet.xlsx")
        logger.info("scoresheet exported event=%s rows=%d", event_id, len(rows))
        return {'url': url, 'rows': len(rows)}

    except Exception as exc:
        logger.error("export_scoresheet failed event=%s: %s", event_id, exc)
        raise self.retry(exc=exc)


@celery.task(
    bind=True,
    queue='exports',
    max_retries=2,
    default_retry_delay=60,
    name='tasks.export_tasks.export_attendance_qr_list',
    time_limit=300,
)
def export_attendance_qr_list(self, event_id: str):
    """
    Export a CSV of all reg_ids + QR data for offline attendance scanning.
    """
    try:
        import csv
        from models import db
        from google.cloud.firestore_v1.base_query import FieldFilter

        regs = list(db.collection('registrations')
                    .where(filter=FieldFilter('event_id', '==', event_id))
                    .stream())

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(['reg_id', 'name', 'email', 'team', 'status'])
        for doc in regs:
            d = doc.to_dict()
            writer.writerow([
                doc.id,
                d.get('lead_name', ''),
                d.get('lead_email', ''),
                d.get('team_name', ''),
                d.get('status', ''),
            ])

        url = _upload_export(buf.getvalue().encode(), f"exports/{event_id}_attendance_qr.csv",
                             content_type='text/csv')
        logger.info("attendance QR list exported event=%s rows=%d", event_id, len(regs))
        return {'url': url, 'rows': len(regs)}

    except Exception as exc:
        raise self.retry(exc=exc)


# ── Upload helper ─────────────────────────────────────────

def _upload_export(data: bytes, gcs_path: str,
                   content_type: str = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet') -> str:
    """Upload data export to cloud/local storage; return public URL."""
    try:
        from utils_storage import upload_file
        return upload_file(data, gcs_path, content_type)
    except Exception as exc:
        logger.warning("Storage upload failed: %s — returning empty URL", exc)
        return ''
