"""
utils_logging.py — one JSON object per log line in production (UPG-20)

Cloud Run (and Cloud Logging) read `severity`, `message` and, when present,
`logging.googleapis.com/trace` from each line, so logs keep their level and
group by request. Development keeps plain text.
"""
import datetime
import json
import logging
import os

# Python level name → Cloud Logging severity
_SEVERITY = {'DEBUG': 'DEBUG', 'INFO': 'INFO', 'WARNING': 'WARNING', 'ERROR': 'ERROR', 'CRITICAL': 'CRITICAL'}


class CloudRunJsonFormatter(logging.Formatter):
    def format(self, record):
        entry = {
            'severity': _SEVERITY.get(record.levelname, 'DEFAULT'),
            'message': record.getMessage(),
            'logger': record.name,
            'time': datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat(),
            'logging.googleapis.com/sourceLocation': {
                'file': record.pathname, 'line': record.lineno, 'function': record.funcName},
        }
        if record.exc_info:
            entry['message'] += '\n' + self.formatException(record.exc_info)
        trace = _trace()
        if trace:
            entry['logging.googleapis.com/trace'] = trace
        return json.dumps(entry, default=str)


def _trace():
    """The Cloud Run request's trace, from X-Cloud-Trace-Context, when known."""
    project = os.environ.get('GOOGLE_CLOUD_PROJECT', '')
    if not project:
        return ''
    try:
        from flask import has_request_context, request
        if not has_request_context():
            return ''
        header = request.headers.get('X-Cloud-Trace-Context', '')
    except Exception:
        return ''
    trace_id = header.split('/', 1)[0]
    return f'projects/{project}/traces/{trace_id}' if trace_id else ''


def configure_logging():
    """Root logger: JSON lines in production, plain text elsewhere."""
    root = logging.getLogger()
    root.setLevel(os.environ.get('LOG_LEVEL', 'INFO').upper())
    for handler in list(root.handlers):   # reloaders must not double-log
        root.removeHandler(handler)
    handler = logging.StreamHandler()
    if os.environ.get('FLASK_ENV') == 'production':
        handler.setFormatter(CloudRunJsonFormatter())
    else:
        handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    root.addHandler(handler)
