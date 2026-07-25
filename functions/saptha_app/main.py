"""
functions/saptha_app/main.py — Zoho Catalyst Advanced I/O Python WSGI Handler for Flask app.py
"""

import sys
import os
from io import BytesIO

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from app import app

def handler(req, res=None):
    """
    Zoho Catalyst Serverless Advanced I/O function entrypoint.
    Handles both (request, response) and (event, context) Catalyst signatures.
    """
    # Extract path, method, headers, and body from Catalyst request
    if hasattr(req, 'get_path'):
        path = req.get_path() or '/'
        method = req.get_http_method() or 'GET'
        query_str = req.get_query_string() or ''
        headers = req.get_headers() or {}
        body_data = req.get_request_body() or ''
    elif isinstance(req, dict):
        path = req.get('path') or req.get('url') or '/'
        method = req.get('httpMethod') or req.get('method') or 'GET'
        query_str = req.get('queryString') or ''
        headers = req.get('headers') or {}
        body_data = req.get('body') or ''
    else:
        path = '/'
        method = 'GET'
        query_str = ''
        headers = {}
        body_data = ''

    # Normalize path if Catalyst includes function prefix (/server/saptha_app/...)
    if path.startswith('/server/saptha_app'):
        path = path[len('/server/saptha_app'):] or '/'

    environ = {
        'REQUEST_METHOD': method,
        'SCRIPT_NAME': '',
        'PATH_INFO': path,
        'QUERY_STRING': query_str,
        'SERVER_NAME': 'catalyst',
        'SERVER_PORT': '443',
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'HTTP_HOST': headers.get('Host', headers.get('host', '')),
        'wsgi.input': BytesIO(body_data.encode('utf-8') if isinstance(body_data, str) else body_data),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'wsgi.url_scheme': 'https',
    }
    
    for k, v in headers.items():
        environ[f'HTTP_{k.upper().replace("-", "_")}'] = str(v)

    # Execute Flask app WSGI
    flask_res = app(environ, lambda status, headers: None)
    body_content = flask_res.get_data(as_text=True)

    if res and hasattr(res, 'send'):
        res.set_status_code(flask_res.status_code)
        for k, v in flask_res.headers:
            res.set_header(k, v)
        res.send(body_content)
        return

    return {
        'statusCode': flask_res.status_code,
        'headers': dict(flask_res.headers),
        'body': body_content
    }
