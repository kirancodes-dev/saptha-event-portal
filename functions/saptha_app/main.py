"""
functions/saptha_app/main.py — Zoho Catalyst Advanced I/O Function Handler
========================================================================
Routes all incoming HTTP requests on Zoho Catalyst to the Flask application.
"""

import sys
import os

# Ensure current function directory is on python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import app

def handler(request, response):
    """
    Zoho Catalyst Advanced I/O Entrypoint
    Delegates HTTP request processing to Flask app WSGI.
    """
    with app.request_context(request.environ if hasattr(request, 'environ') else {}):
        try:
            return app(request.environ, response.start_response)
        except Exception:
            return app.full_dispatch_request()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
