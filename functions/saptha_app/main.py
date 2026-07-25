"""
functions/saptha_app/main.py — Zoho Catalyst Advanced I/O Python WSGI Handler for Flask app.py
"""

import sys
import os
from io import BytesIO

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import app

def handler(event, context):
    """
    Zoho Catalyst Serverless Advanced I/O function entrypoint.
    Converts Catalyst HTTP event into a Flask WSGI request and returns response.
    """
    environ = {
        'REQUEST_METHOD': event.get('httpMethod', 'GET'),
        'SCRIPT_NAME': '',
        'PATH_INFO': event.get('path', '/'),
        'QUERY_STRING': event.get('queryString', ''),
        'SERVER_NAME': 'catalyst',
        'SERVER_PORT': '443',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'HTTP_HOST': event.get('headers', {}).get('Host', ''),
        'wsgi.input': BytesIO((event.get('body') or '').encode('utf-8')),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'wsgi.url_scheme': 'https',
    }
    
    headers = event.get('headers') or {}
    for k, v in headers.items():
        environ[f'HTTP_{k.upper().replace("-", "_")}'] = str(v)

    # Call Flask WSGI app
    response = app(environ, lambda status, headers: None)
    
    return {
        'statusCode': response.status_code,
        'headers': dict(response.headers),
        'body': response.get_data(as_text=True)
    }
